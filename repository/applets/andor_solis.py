#!/usr/bin/env python3
"""
Andor "Solis-style" camera applet for the ARTIQ dashboard.

A live image viewer + control panel that talks directly to the Andor NDSP
controller (``ndsp_config/aqctl_andor.py``) over sipyco RPC. It provides:

  * live streaming view (pyqtgraph ImageView: histogram, colormap/LUT, zoom, ROI)
  * single-shot Snap
  * exposure, trigger mode, sensor cooling / temperature controls
  * SDK3 pre-amp gain / pixel-readout-rate selectors
  * optional mirroring of each frame into an ARTIQ dataset ("Both" data path),
    so experiments and the built-in image applet can use the same frames.

Frame acquisition runs in a background thread (a synchronous sipyco client) and
hands frames to the GUI via Qt signals, so the dashboard never blocks on RPC.

Add it in the dashboard's Applets dock with a command such as:

    python3 repository/applets/andor_solis.py \
        --andor-server 192.168.1.100 --andor-port 3287 --img andor.image

(``--andor-server`` is the Windows PC running the NDSP; ``--img`` is optional and
only needed for the dataset-mirroring path.)
"""

import queue
import time
import logging

import numpy as np
import PyQt6  # ensure pyqtgraph binds to Qt6
import pyqtgraph
from PyQt6 import QtWidgets, QtCore

from artiq.applets.simple import SimpleApplet
from sipyco.pc_rpc import Client

logger = logging.getLogger(__name__)


# =====================================================================
#  Background RPC worker
# =====================================================================

class CameraWorker(QtCore.QObject):
    """Owns the (synchronous) sipyco client and polls frames off the GUI thread.

    The GUI pushes commands via a thread-safe queue; results that produce a
    frame (snap / live) are emitted back through Qt signals.
    """

    frameReady = QtCore.pyqtSignal(object)        # numpy array
    statusReady = QtCore.pyqtSignal(object)       # dict
    connectionChanged = QtCore.pyqtSignal(bool, str)

    def __init__(self, server, port, poll_ms=100):
        super().__init__()
        self._server = server
        self._port = int(port)
        self._poll = max(0.01, poll_ms / 1000.0)
        self._cmds = queue.Queue()
        self._client = None
        self._stop = False
        self.live = False
        self.downsample = 1

    # -- called from GUI thread --
    def send(self, method, *args):
        """Queue an RPC call (executed on the worker thread)."""
        self._cmds.put((method, args))

    def stop(self):
        self._stop = True

    # -- worker thread --
    def _connect(self):
        try:
            self._client = Client(self._server, self._port, "andor")
            sim = self._client.is_simulation()
            info = self._client.get_device_info()
            name = info.get("camera_name") or info.get("model") or "Andor"
            self.connectionChanged.emit(
                True, "%s @ %s:%d%s" % (name, self._server, self._port,
                                        " [SIM]" if sim else ""))
            return True
        except Exception as e:
            self._client = None
            self.connectionChanged.emit(False, "disconnected (%s)" % e)
            return False

    def _drain_commands(self):
        while True:
            try:
                method, args = self._cmds.get_nowait()
            except queue.Empty:
                return
            try:
                result = getattr(self._client, method)(*args)
                if method == "snap" and result is not None:
                    self.frameReady.emit(np.asarray(result))
            except Exception:
                logger.exception("RPC command %s failed", method)
                raise

    def _poll_status(self):
        c = self._client
        status = {
            "temperature": c.get_temperature(),
            "setpoint": c.get_temperature_setpoint(),
            "cooler": c.is_cooler_on(),
            "exposure": c.get_exposure(),
            "trigger": c.get_trigger_mode(),
            "acquiring": c.is_acquiring(),
        }
        self.statusReady.emit(status)

    def run(self):
        last_status = 0.0
        while not self._stop:
            if self._client is None:
                if not self._connect():
                    time.sleep(2.0)
                    continue
            try:
                self._drain_commands()

                if self.live:
                    frame = self._client.get_latest_frame(self.downsample)
                    if frame is not None:
                        self.frameReady.emit(np.asarray(frame))

                now = time.time()
                if now - last_status > 1.0:
                    self._poll_status()
                    last_status = now
            except Exception:
                # Drop the client and retry the connection on the next pass.
                self._client = None
                self.connectionChanged.emit(False, "connection lost; retrying...")
                time.sleep(1.0)
                continue

            time.sleep(self._poll)

        # graceful shutdown
        if self._client is not None:
            try:
                self._client.stop_live()
            except Exception:
                pass
            try:
                self._client.close_rpc()
            except Exception:
                pass


# =====================================================================
#  Main widget
# =====================================================================

class AndorSolis(QtWidgets.QWidget):
    def __init__(self, args, req):
        super().__init__()
        self.args = args
        self.req = req
        self._auto_levels = True
        self._last_publish = 0.0
        self.setWindowTitle("Andor Solis")

        # --- image view (histogram + LUT + colormap + ROI come for free) ---
        self.image_view = pyqtgraph.ImageView()
        self.image_view.getView().invertY(True)   # image origin at top-left

        # --- controls ---
        self.live_btn = QtWidgets.QPushButton("Live")
        self.live_btn.setCheckable(True)
        self.snap_btn = QtWidgets.QPushButton("Snap")
        self.autolevel_btn = QtWidgets.QPushButton("Auto levels")
        self.autolevel_btn.setCheckable(True)
        self.autolevel_btn.setChecked(True)
        self.reset_roi_btn = QtWidgets.QPushButton("Reset ROI")

        self.exposure_spin = QtWidgets.QDoubleSpinBox()
        self.exposure_spin.setDecimals(4)
        self.exposure_spin.setRange(0.0001, 30.0)
        self.exposure_spin.setSingleStep(0.001)
        self.exposure_spin.setSuffix(" s")
        self.exposure_spin.setValue(0.01)
        self.exposure_apply = QtWidgets.QPushButton("Set")

        self.trigger_combo = QtWidgets.QComboBox()
        self.trigger_combo.addItems(["int", "ext", "software"])

        self.gain_combo = QtWidgets.QComboBox()
        self.gain_combo.addItems([
            "16-bit (low noise & high well capacity)",
            "12-bit (high well capacity)",
            "12-bit (low noise)",
        ])
        self.readout_combo = QtWidgets.QComboBox()
        self.readout_combo.addItems(["280 MHz", "100 MHz"])

        self.cooler_check = QtWidgets.QCheckBox("Cooler")
        self.temp_spin = QtWidgets.QDoubleSpinBox()
        self.temp_spin.setRange(-100.0, 30.0)
        self.temp_spin.setSuffix(" °C")
        self.temp_spin.setValue(-30.0)
        self.temp_apply = QtWidgets.QPushButton("Set T")

        self.downsample_spin = QtWidgets.QSpinBox()
        self.downsample_spin.setRange(1, 16)
        self.downsample_spin.setValue(1)
        self.downsample_spin.setPrefix("÷")

        self.publish_check = QtWidgets.QCheckBox("Publish to dataset")
        self.publish_check.setEnabled(self.args.img is not None)
        if self.args.img is not None:
            self.publish_check.setToolTip("Mirror frames into '%s'" % self.args.img)
        else:
            self.publish_check.setToolTip("Pass --img <dataset> to enable")

        self.status_label = QtWidgets.QLabel("connecting...")
        self.status_label.setStyleSheet("color: gray;")

        self._build_layout()
        self._connect_signals()

        # --- background worker ---
        self.thread = QtCore.QThread(self)
        self.worker = CameraWorker(args.andor_server, args.andor_port, args.poll)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.frameReady.connect(self.on_frame)
        self.worker.statusReady.connect(self.on_status)
        self.worker.connectionChanged.connect(self.on_connection)
        self.thread.start()

    # ---- layout ----
    def _build_layout(self):
        controls = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(controls)
        grid.setContentsMargins(6, 6, 6, 6)
        r = 0
        grid.addWidget(self.live_btn, r, 0)
        grid.addWidget(self.snap_btn, r, 1)
        r += 1
        grid.addWidget(self.autolevel_btn, r, 0)
        grid.addWidget(self.reset_roi_btn, r, 1)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Exposure"), r, 0)
        grid.addWidget(self.exposure_spin, r, 1)
        grid.addWidget(self.exposure_apply, r, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Trigger"), r, 0)
        grid.addWidget(self.trigger_combo, r, 1, 1, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Pre-amp gain"), r, 0)
        grid.addWidget(self.gain_combo, r, 1, 1, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Readout rate"), r, 0)
        grid.addWidget(self.readout_combo, r, 1, 1, 2)
        r += 1
        grid.addWidget(self.cooler_check, r, 0)
        grid.addWidget(self.temp_spin, r, 1)
        grid.addWidget(self.temp_apply, r, 2)
        r += 1
        grid.addWidget(QtWidgets.QLabel("Live decimation"), r, 0)
        grid.addWidget(self.downsample_spin, r, 1)
        r += 1
        grid.addWidget(self.publish_check, r, 0, 1, 3)
        r += 1
        grid.setRowStretch(r, 1)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(self.image_view)
        splitter.addWidget(controls)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter, 1)
        outer.addWidget(self.status_label)

    # ---- signal wiring ----
    def _connect_signals(self):
        self.live_btn.toggled.connect(self.on_live_toggled)
        self.snap_btn.clicked.connect(lambda: self.worker.send("snap"))
        self.autolevel_btn.toggled.connect(self._set_autolevels)
        self.reset_roi_btn.clicked.connect(lambda: self.worker.send("reset_roi"))
        self.exposure_apply.clicked.connect(
            lambda: self.worker.send("set_exposure", self.exposure_spin.value()))
        self.trigger_combo.currentTextChanged.connect(
            lambda m: self.worker.send("set_trigger_mode", m))
        self.gain_combo.currentTextChanged.connect(
            lambda v: self.worker.send("set_preamp_gain", v))
        self.readout_combo.currentTextChanged.connect(
            lambda v: self.worker.send("set_readout_rate", v))
        self.cooler_check.toggled.connect(
            lambda on: self.worker.send("set_cooler", on))
        self.temp_apply.clicked.connect(
            lambda: self.worker.send("set_temperature", self.temp_spin.value()))
        self.downsample_spin.valueChanged.connect(self._set_downsample)

    # ---- slots ----
    def _set_autolevels(self, on):
        self._auto_levels = on

    def _set_downsample(self, value):
        self.worker.downsample = int(value)

    def on_live_toggled(self, on):
        self.worker.live = on
        self.worker.send("start_live" if on else "stop_live")
        self.live_btn.setText("Live ●" if on else "Live")

    def on_frame(self, frame):
        self.image_view.setImage(
            frame, autoLevels=self._auto_levels, autoRange=False,
            autoHistogramRange=self._auto_levels, axes={"x": 1, "y": 0})
        self._maybe_publish(frame)

    def on_status(self, status):
        self.cooler_check.blockSignals(True)
        self.cooler_check.setChecked(bool(status.get("cooler")))
        self.cooler_check.blockSignals(False)
        self.status_label.setText(
            "T = %.1f °C (set %.1f) | cooler %s | exp %.4g s | trig %s | %s"
            % (status.get("temperature", float("nan")),
               status.get("setpoint", float("nan")),
               "on" if status.get("cooler") else "off",
               status.get("exposure", float("nan")),
               status.get("trigger", "?"),
               "acquiring" if status.get("acquiring") else "idle"))

    def on_connection(self, ok, msg):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: %s;" % ("green" if ok else "red"))

    def _maybe_publish(self, frame):
        if not (self.publish_check.isChecked() and self.args.img):
            return
        now = time.time()
        if now - self._last_publish < 0.5:    # throttle dataset writes to ~2 Hz
            return
        self._last_publish = now
        try:
            self.req.set_dataset(self.args.img, frame)
        except Exception:
            logger.exception("Failed to publish frame to dataset")

    # ---- dataset path: display frames pushed to the subscribed dataset ----
    def data_changed(self, value, metadata, persist, mods):
        if self.worker.live or self.args.img is None:
            return
        img = value.get(self.args.img)
        if img is not None:
            self.image_view.setImage(
                np.asarray(img), autoLevels=self._auto_levels, autoRange=False,
                axes={"x": 1, "y": 0})

    # ---- teardown ----
    def closeEvent(self, event):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait(2000)
        super().closeEvent(event)


def main():
    applet = SimpleApplet(AndorSolis)
    # Optional dataset to display/mirror (the "Both" data path).
    applet.add_dataset("img", "image dataset to mirror frames into / display",
                       required=False)
    applet.argparser.add_argument(
        "--andor-server", default="localhost",
        help="hostname/IP of the Andor NDSP controller (the Windows PC)")
    applet.argparser.add_argument(
        "--andor-port", type=int, default=3287,
        help="port of the Andor NDSP controller (default: %(default)s)")
    applet.argparser.add_argument(
        "--poll", type=float, default=100.0,
        help="frame poll interval in ms (default: %(default)s)")
    applet.run()


if __name__ == "__main__":
    main()
