#!/usr/bin/env python3
"""
Andor sCMOS (SDK3) NDSP Controller for ARTIQ.

Wraps an Andor SDK3 camera (Zyla / Neo / Sona / Marana) via pylablib and
exposes acquisition + control over sipyco RPC so ARTIQ experiments and the
Solis-style applet can drive it.

Because the Andor SDK3 (atcore) and the camera live on the Windows acquisition
PC, this controller is meant to run *on that Windows machine* and bind to the
network so the Linux ARTIQ host reaches it over Ethernet:

    # on the Windows PC (with pylablib + Andor SDK3 installed):
    python aqctl_andor.py -p 3287 --bind 0.0.0.0

For development / GUI testing without hardware, run it anywhere in simulation
mode (synthetic "atom cloud" frames, no SDK required):

    python3 aqctl_andor.py -p 3287 --bind ::1 --simulation

Then in ARTIQ experiments:
    self.andor.snap()              # single frame (numpy uint16 array)
    self.andor.set_exposure(0.01)  # seconds

All public methods (without a leading underscore) are exposed as RPCs.
"""

import argparse
import logging
import time

import numpy as np

from sipyco.pc_rpc import simple_server_loop
from sipyco import common_args

logger = logging.getLogger(__name__)

DEFAULT_PORT = 3287

# SDK3 attribute names for the common Solis-style controls.
ATTR_PREAMP_GAIN = "SimplePreAmpGainControl"
ATTR_SHUTTER_MODE = "ElectronicShutteringMode"
ATTR_READOUT_RATE = "PixelReadoutRate"


# =====================================================================
#  Backends
# =====================================================================

class _Backend:
    """Common backend surface used by AndorController.

    Both the real SDK3 backend and the simulation backend implement these
    methods so the RPC layer above stays hardware-agnostic.
    """

    simulation = False

    def close(self): ...
    def get_device_info(self) -> dict: ...
    def get_detector_size(self): ...           # (width, height)

    def get_exposure(self) -> float: ...
    def set_exposure(self, exposure: float) -> float: ...
    def get_frame_period(self) -> float: ...
    def set_frame_period(self, period: float) -> float: ...
    def get_frame_timings(self) -> dict: ...

    def get_roi(self): ...
    def set_roi(self, hstart, hend, vstart, vend, hbin, vbin): ...
    def get_roi_limits(self): ...

    def get_trigger_mode(self) -> str: ...
    def set_trigger_mode(self, mode: str) -> str: ...

    def is_cooler_on(self) -> bool: ...
    def set_cooler(self, on: bool) -> bool: ...
    def get_temperature(self) -> float: ...
    def get_temperature_setpoint(self) -> float: ...
    def set_temperature(self, temperature: float, enable_cooler: bool): ...

    def list_attributes(self): ...
    def get_attribute(self, name): ...
    def set_attribute(self, name, value): ...

    def snap(self) -> np.ndarray: ...
    def start_acquisition(self): ...
    def stop_acquisition(self): ...
    def acquisition_in_progress(self) -> bool: ...
    def read_newest_image(self): ...


class SDK3Backend(_Backend):
    """Real Andor SDK3 camera via pylablib (lazy-imported)."""

    simulation = False

    def __init__(self, idx=0):
        # Imported here (not at module top) so the controller still loads in
        # --simulation mode on machines without the Andor SDK / pylablib.
        from pylablib.devices import Andor

        logger.info("Opening Andor SDK3 camera (idx=%d)...", idx)
        self._cam = Andor.AndorSDK3Camera(idx=idx)
        logger.info("Camera opened: %s", self.get_device_info())

    def close(self):
        try:
            self._cam.close()
        except Exception:
            logger.exception("Error closing camera")

    def get_device_info(self):
        info = self._cam.get_device_info()
        # pylablib returns a namedtuple; make it JSON/pyon-friendly.
        try:
            return dict(info._asdict())
        except AttributeError:
            return {"info": str(info)}

    def get_detector_size(self):
        return list(self._cam.get_detector_size())

    def get_exposure(self):
        return float(self._cam.get_exposure())

    def set_exposure(self, exposure):
        return float(self._cam.set_exposure(float(exposure)))

    def get_frame_period(self):
        return float(self._cam.get_frame_period())

    def set_frame_period(self, period):
        return float(self._cam.set_frame_period(float(period)))

    def get_frame_timings(self):
        t = self._cam.get_frame_timings()
        return {"exposure": float(t.exposure),
                "frame_period": float(t.frame_period),
                "frame_rate": float(1.0 / t.frame_period) if t.frame_period else 0.0}

    def get_roi(self):
        return list(self._cam.get_roi())

    def set_roi(self, hstart, hend, vstart, vend, hbin, vbin):
        self._cam.set_roi(hstart, hend, vstart, vend, hbin, vbin)
        return list(self._cam.get_roi())

    def get_roi_limits(self):
        lims = self._cam.get_roi_limits()
        return [list(l) if hasattr(l, "__iter__") else l for l in lims]

    def get_trigger_mode(self):
        return str(self._cam.get_trigger_mode())

    def set_trigger_mode(self, mode):
        self._cam.set_trigger_mode(mode)
        return str(self._cam.get_trigger_mode())

    def is_cooler_on(self):
        return bool(self._cam.is_cooler_on())

    def set_cooler(self, on):
        self._cam.set_cooler(bool(on))
        return self.is_cooler_on()

    def get_temperature(self):
        return float(self._cam.get_temperature())

    def get_temperature_setpoint(self):
        return float(self._cam.get_temperature_setpoint())

    def set_temperature(self, temperature, enable_cooler=True):
        self._cam.set_temperature(float(temperature), enable_cooler=bool(enable_cooler))
        return self.get_temperature_setpoint()

    def list_attributes(self):
        return sorted(self._cam.get_all_attribute_values().keys())

    def get_attribute(self, name):
        return self._cam.get_attribute_value(name)

    def set_attribute(self, name, value):
        self._cam.set_attribute_value(name, value)
        return self._cam.get_attribute_value(name)

    def snap(self):
        return np.asarray(self._cam.snap())

    def start_acquisition(self):
        self._cam.start_acquisition()

    def stop_acquisition(self):
        self._cam.stop_acquisition()

    def acquisition_in_progress(self):
        return bool(self._cam.acquisition_in_progress())

    def read_newest_image(self):
        img = self._cam.read_newest_image()
        return None if img is None else np.asarray(img)


class SimBackend(_Backend):
    """Synthetic camera: a drifting Gaussian "atom cloud" + readout noise.

    Lets the NDSP, applet and experiments run end-to-end with no hardware.
    """

    simulation = True

    def __init__(self, width=512, height=512):
        self._w = int(width)
        self._h = int(height)
        self._exposure = 0.01
        self._frame_period = 0.05
        self._roi = (0, self._w, 0, self._h, 1, 1)
        self._trigger_mode = "int"
        self._cooler = True
        self._temp_setpoint = -30.0
        self._temp = 20.0          # warms toward setpoint when cooler is on
        self._attrs = {
            ATTR_PREAMP_GAIN: "16-bit (low noise & high well capacity)",
            ATTR_SHUTTER_MODE: "Rolling",
            ATTR_READOUT_RATE: "280 MHz",
        }
        self._acquiring = False
        self._t0 = time.time()
        logger.info("Simulation backend: %dx%d synthetic sensor", self._w, self._h)

    # --- info / sizing ---
    def close(self):
        self._acquiring = False

    def get_device_info(self):
        return {"camera_name": "SIMCAM (simulation)", "serial_number": "SIM-0000",
                "model": "Andor SDK3 simulation", "interface": "none"}

    def get_detector_size(self):
        return [self._w, self._h]

    # --- exposure / timing ---
    def get_exposure(self):
        return self._exposure

    def set_exposure(self, exposure):
        self._exposure = max(1e-5, float(exposure))
        self._frame_period = max(self._frame_period, self._exposure + 1e-3)
        return self._exposure

    def get_frame_period(self):
        return self._frame_period

    def set_frame_period(self, period):
        self._frame_period = max(self._exposure + 1e-3, float(period))
        return self._frame_period

    def get_frame_timings(self):
        return {"exposure": self._exposure, "frame_period": self._frame_period,
                "frame_rate": 1.0 / self._frame_period if self._frame_period else 0.0}

    # --- roi ---
    def _roi_size(self):
        hs, he, vs, ve, hb, vb = self._roi
        return (he - hs) // hb, (ve - vs) // vb

    def get_roi(self):
        return list(self._roi)

    def set_roi(self, hstart, hend, vstart, vend, hbin, vbin):
        hend = self._w if hend is None else hend
        vend = self._h if vend is None else vend
        hstart = max(0, min(int(hstart), self._w - 1))
        hend = max(hstart + 1, min(int(hend), self._w))
        vstart = max(0, min(int(vstart), self._h - 1))
        vend = max(vstart + 1, min(int(vend), self._h))
        self._roi = (hstart, hend, vstart, vend, max(1, int(hbin)), max(1, int(vbin)))
        return list(self._roi)

    def get_roi_limits(self):
        return [[1, self._w, 1], [1, self._h, 1]]

    # --- trigger ---
    def get_trigger_mode(self):
        return self._trigger_mode

    def set_trigger_mode(self, mode):
        self._trigger_mode = str(mode)
        return self._trigger_mode

    # --- cooling ---
    def _update_temp(self):
        target = self._temp_setpoint if self._cooler else 20.0
        self._temp += (target - self._temp) * 0.05

    def is_cooler_on(self):
        return self._cooler

    def set_cooler(self, on):
        self._cooler = bool(on)
        return self._cooler

    def get_temperature(self):
        self._update_temp()
        return round(self._temp, 2)

    def get_temperature_setpoint(self):
        return self._temp_setpoint

    def set_temperature(self, temperature, enable_cooler=True):
        self._temp_setpoint = float(temperature)
        if enable_cooler:
            self._cooler = True
        return self._temp_setpoint

    # --- attributes ---
    def list_attributes(self):
        return sorted(self._attrs.keys())

    def get_attribute(self, name):
        return self._attrs.get(name)

    def set_attribute(self, name, value):
        self._attrs[name] = value
        return value

    # --- acquisition ---
    def _render(self):
        w, h = self._roi_size()
        t = time.time() - self._t0
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        # Cloud drifts in a slow Lissajous and breathes a little.
        cx = w * (0.5 + 0.25 * np.sin(0.6 * t))
        cy = h * (0.5 + 0.20 * np.cos(0.4 * t))
        sigma = 0.10 * min(w, h) * (1.0 + 0.15 * np.sin(0.9 * t))
        peak = 12000.0 * min(1.0, self._exposure / 0.02)
        cloud = peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
        offset = 100.0                                   # readout bias
        frame = cloud + offset
        frame = np.random.poisson(np.clip(frame, 0, None)).astype(np.float32)
        frame += np.random.normal(0.0, 8.0, size=frame.shape)   # read noise
        return np.clip(frame, 0, 65535).astype(np.uint16)

    def snap(self):
        time.sleep(min(self._exposure, 0.2))
        return self._render()

    def start_acquisition(self):
        self._acquiring = True

    def stop_acquisition(self):
        self._acquiring = False

    def acquisition_in_progress(self):
        return self._acquiring

    def read_newest_image(self):
        if not self._acquiring:
            return None
        return self._render()


# =====================================================================
#  RPC controller
# =====================================================================

class AndorController:
    """sipyco RPC interface to an Andor SDK3 camera (or its simulation)."""

    def __init__(self, backend: _Backend):
        self._b = backend

    # ---- info ----
    def ping(self):
        """Health check. Returns True if the controller is running."""
        return True

    def is_simulation(self):
        """Whether this controller is serving synthetic frames."""
        return bool(self._b.simulation)

    def get_device_info(self):
        """Camera identity (name, serial, model, ...) as a dict."""
        return self._b.get_device_info()

    def get_detector_size(self):
        """Full sensor size as [width, height] in pixels."""
        return self._b.get_detector_size()

    # ---- exposure / timing ----
    def get_exposure(self):
        """Exposure time in seconds."""
        return self._b.get_exposure()

    def set_exposure(self, exposure):
        """Set exposure time in seconds. Returns the actual value applied."""
        return self._b.set_exposure(exposure)

    def get_frame_period(self):
        """Frame period in seconds (1 / frame rate)."""
        return self._b.get_frame_period()

    def set_frame_period(self, period):
        """Set frame period in seconds. Returns the actual value applied."""
        return self._b.set_frame_period(period)

    def get_frame_timings(self):
        """Dict with exposure, frame_period and frame_rate."""
        return self._b.get_frame_timings()

    # ---- roi / binning ----
    def get_roi(self):
        """Current ROI as [hstart, hend, vstart, vend, hbin, vbin]."""
        return self._b.get_roi()

    def set_roi(self, hstart=0, hend=None, vstart=0, vend=None, hbin=1, vbin=1):
        """Set ROI / binning. Returns the actual ROI applied."""
        return self._b.set_roi(hstart, hend, vstart, vend, hbin, vbin)

    def reset_roi(self):
        """Reset ROI to the full sensor with 1x1 binning."""
        w, h = self._b.get_detector_size()
        return self._b.set_roi(0, w, 0, h, 1, 1)

    def get_roi_limits(self):
        """Allowed ROI / binning limits."""
        return self._b.get_roi_limits()

    # ---- trigger ----
    def get_trigger_mode(self):
        """Current trigger mode (e.g. 'int', 'ext', 'software')."""
        return self._b.get_trigger_mode()

    def set_trigger_mode(self, mode):
        """Set trigger mode. Returns the actual mode applied."""
        return self._b.set_trigger_mode(mode)

    # ---- cooling ----
    def is_cooler_on(self):
        """Whether the sensor cooler is enabled."""
        return self._b.is_cooler_on()

    def set_cooler(self, on=True):
        """Enable/disable the sensor cooler. Returns the cooler state."""
        return self._b.set_cooler(on)

    def get_temperature(self):
        """Current sensor temperature in degrees C."""
        return self._b.get_temperature()

    def get_temperature_setpoint(self):
        """Target sensor temperature in degrees C."""
        return self._b.get_temperature_setpoint()

    def set_temperature(self, temperature, enable_cooler=True):
        """Set the target sensor temperature in degrees C."""
        return self._b.set_temperature(temperature, enable_cooler)

    # ---- generic SDK3 attributes ----
    def list_attributes(self):
        """List available SDK3 attribute names."""
        return self._b.list_attributes()

    def get_attribute(self, name):
        """Get an SDK3 attribute value by name."""
        return self._b.get_attribute(name)

    def set_attribute(self, name, value):
        """Set an SDK3 attribute value by name. Returns the applied value."""
        return self._b.set_attribute(name, value)

    # convenience wrappers for the common Solis controls -----------------
    def get_preamp_gain(self):
        """Get the pre-amp gain / sensitivity mode string."""
        return self._b.get_attribute(ATTR_PREAMP_GAIN)

    def set_preamp_gain(self, value):
        """Set the pre-amp gain / sensitivity mode string."""
        return self._b.set_attribute(ATTR_PREAMP_GAIN, value)

    def get_shutter_mode(self):
        """Get electronic shuttering mode ('Rolling' / 'Global')."""
        return self._b.get_attribute(ATTR_SHUTTER_MODE)

    def set_shutter_mode(self, value):
        """Set electronic shuttering mode ('Rolling' / 'Global')."""
        return self._b.set_attribute(ATTR_SHUTTER_MODE, value)

    def get_readout_rate(self):
        """Get pixel readout rate string."""
        return self._b.get_attribute(ATTR_READOUT_RATE)

    def set_readout_rate(self, value):
        """Set pixel readout rate string."""
        return self._b.set_attribute(ATTR_READOUT_RATE, value)

    # ---- acquisition ----
    def snap(self):
        """Acquire and return a single frame as a numpy array."""
        return self._b.snap()

    def start_live(self):
        """Start continuous (live) acquisition for streaming frames."""
        if not self._b.acquisition_in_progress():
            self._b.start_acquisition()
        return True

    def stop_live(self):
        """Stop continuous acquisition."""
        if self._b.acquisition_in_progress():
            self._b.stop_acquisition()
        return True

    def is_acquiring(self):
        """Whether continuous acquisition is currently running."""
        return self._b.acquisition_in_progress()

    def get_latest_frame(self, downsample=1):
        """Return the newest frame during live acquisition (or None).

        ``downsample`` (>=1) decimates the frame server-side to cut bandwidth
        for live preview without changing the camera ROI.
        """
        img = self._b.read_newest_image()
        if img is None:
            return None
        d = max(1, int(downsample))
        if d > 1:
            img = img[::d, ::d]
        return np.ascontiguousarray(img)

    def close(self):
        """Clean shutdown."""
        logger.info("Andor controller shutting down.")
        try:
            self._b.stop_acquisition()
        except Exception:
            pass
        self._b.close()


def get_argparser():
    parser = argparse.ArgumentParser(
        description="ARTIQ NDSP controller for Andor SDK3 (sCMOS) cameras"
    )
    common_args.simple_network_args(parser, DEFAULT_PORT)
    parser.add_argument(
        "--simulation", action="store_true",
        help="serve synthetic frames; no camera / Andor SDK required",
    )
    parser.add_argument(
        "--idx", type=int, default=0,
        help="camera index for the Andor SDK (default: %(default)s)",
    )
    parser.add_argument(
        "--sim-size", type=int, nargs=2, metavar=("W", "H"), default=(512, 512),
        help="synthetic sensor size in simulation mode (default: 512 512)",
    )
    common_args.verbosity_args(parser)
    return parser


def main():
    args = get_argparser().parse_args()
    common_args.init_logger_from_args(args)

    if args.simulation:
        logger.info("Starting Andor controller in SIMULATION mode...")
        backend = SimBackend(width=args.sim_size[0], height=args.sim_size[1])
    else:
        logger.info("Starting Andor SDK3 controller...")
        backend = SDK3Backend(idx=args.idx)

    controller = AndorController(backend)
    info = controller.get_device_info()
    logger.info("Andor controller ready. %s", info)

    try:
        simple_server_loop(
            {"andor": controller},
            common_args.bind_address_from_args(args),
            args.port,
        )
    finally:
        controller.close()


if __name__ == "__main__":
    main()
