#!/usr/bin/env python3
"""
Delta Elektronika SM18-220 NDSP Controller for ARTIQ.

The SM18-220 (SM3300 series, 0-18 V / 0-220 A) talks SCPI over its built-in
Ethernet port on TCP port 8462 (fixed). This controller exposes output
switching, setpoints and readback via sipyco RPC so ARTIQ experiments can
control the power supply.

A fresh TCP connection is opened for every call, so nothing is held open
between calls.

Programming source: the supply takes its voltage (CV) and current (CC)
setpoints each from one source: the front panel knobs, the web page, the
sequencer, Ethernet or an interface slot. set_voltage() and set_current() only
work once both come from Ethernet, which set_remote() does. Nothing hands
control back to the front panel on exit (unlike the HMP4040's SYST:LOC): on
this supply that would make the output follow the knobs.

Commands are from the "SM3300 Ethernet & Sequencer Programming" manual
(Delta Elektronika, rev. Aug. 2019).

Usage:
    python3 aqctl_sm18220.py -p 3291 --bind ::1 --ip <supply IP>

Then in ARTIQ experiments:
    self.sm18220.get_status()
    self.sm18220.set_remote()
    self.sm18220.set_current(5.0)
    self.sm18220.set_output(True)
"""

import argparse
import contextlib
import logging
import socket

from sipyco.pc_rpc import simple_server_loop
from sipyco import common_args

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8462          # fixed on the SM3300 series
# V, 101% of the SM18-220's 18 V rating; set_voltage() raises if the supply refuses it
SUPPLY_MAX_VOLTAGE = 18.18
SUPPLY_MAX_CURRENT = 220.0   # A, SM18-220 rating
# SYSTem:REMote:CV?/CC? replies that mean "set over Ethernet". The SM18-220 answers
# "LOC" when the front panel has control and "ETHERNET" when Ethernet has; the
# manual treats Remote and Ethernet as the same, so only the first three letters
# are compared.
ETHERNET_SOURCES = ("REM", "ETH")


def _is_ethernet(source):
    return source.strip().upper()[:3] in ETHERNET_SOURCES


class SM18220Controller:
    """
    sipyco RPC interface to the Delta Elektronika SM18-220 power supply.
    All public methods (without leading underscore) are exposed as RPCs.
    """

    def __init__(self, ip, port=DEFAULT_PORT, max_voltage=SUPPLY_MAX_VOLTAGE,
                 max_current=SUPPLY_MAX_CURRENT, timeout=3.0):
        if not 0.0 < max_voltage <= SUPPLY_MAX_VOLTAGE:
            raise ValueError(f"max_voltage {max_voltage} V outside 0..{SUPPLY_MAX_VOLTAGE} V")
        if not 0.0 < max_current <= SUPPLY_MAX_CURRENT:
            raise ValueError(f"max_current {max_current} A outside 0..{SUPPLY_MAX_CURRENT} A")
        self._ip = ip
        self._port = port
        self._max_voltage = max_voltage
        self._max_current = max_current
        self._timeout = timeout

    @contextlib.contextmanager
    def _session(self):
        """Open a SCPI session for one call."""
        try:
            sock = socket.create_connection((self._ip, self._port), timeout=self._timeout)
        except OSError as e:
            raise RuntimeError(
                f"Could not connect to SM18-220 at {self._ip}:{self._port}: {e}"
            )
        f = sock.makefile("rwb")
        try:
            yield _Session(f)
        finally:
            f.close()
            sock.close()

    # =====================================================================
    #  System Information
    # =====================================================================

    def get_idn(self):
        """Get the *IDN? string: manufacturer, model, serial number, firmware."""
        with self._session() as s:
            return s.query("*IDN?")

    def get_error(self):
        """Pop one entry from the error queue ("0,None" when empty)."""
        with self._session() as s:
            return s.query("SYSTem:ERRor?")

    def get_limits(self):
        """Get the highest voltage and current setpoints this controller accepts."""
        return {"max_voltage": self._max_voltage, "max_current": self._max_current}

    # =====================================================================
    #  Programming Source
    # =====================================================================

    def get_source(self):
        """Get where the CV and CC setpoints come from, e.g. Front or Ethernet."""
        with self._session() as s:
            return s.sources()

    def set_remote(self):
        """
        Take the CV and CC setpoints over Ethernet. Does nothing if both
        already come from Ethernet.

        Refused while the output is on and set from another source: switching
        then would make the output jump from the knob setpoints to whatever
        was last sent over Ethernet. Switch the output off first.
        """
        with self._session() as s:
            sources = s.sources()
            if _is_ethernet(sources["cv_source"]) and _is_ethernet(sources["cc_source"]):
                return sources
            if s.output_on():
                raise RuntimeError(
                    "Output is on with setpoints from CV {cv_source} / CC {cc_source}; "
                    "switch the output off before handing them to Ethernet".format(**sources)
                )
            s.clear_errors()
            s.write_checked("SYSTem:REMote:CV Remote")
            s.write_checked("SYSTem:REMote:CC Remote")
            sources = s.sources()
        logger.info("Programming source set to CV %s, CC %s",
                    sources["cv_source"], sources["cc_source"])
        return sources

    def set_local(self):
        """
        Hand the CV and CC setpoints back to the front panel knobs.

        Refused while the output is on, for the same reason as set_remote().
        """
        with self._session() as s:
            if s.output_on():
                raise RuntimeError(
                    "Output is on; switch it off before handing the setpoints to the front panel"
                )
            s.clear_errors()
            s.write_checked("SYSTem:REMote:CV Local")
            s.write_checked("SYSTem:REMote:CC Local")
            sources = s.sources()
        logger.info("Programming source set to CV %s, CC %s",
                    sources["cv_source"], sources["cc_source"])
        return sources

    # =====================================================================
    #  Output Switching
    # =====================================================================

    def get_output(self):
        """Get output state (True = on)."""
        with self._session() as s:
            return s.output_on()

    def set_output(self, enable=True):
        """Switch the output on or off. Returns the new state."""
        with self._session() as s:
            s.clear_errors()
            s.write_checked("OUTPut ON" if enable else "OUTPut OFF")
            state = s.output_on()
        logger.info("Output set to %s", "ON" if state else "OFF")
        return state

    # =====================================================================
    #  Setpoints and Readback
    # =====================================================================

    def set_voltage(self, voltage):
        """Set the voltage setpoint in V. Needs CV programming on Ethernet (set_remote)."""
        voltage = float(voltage)
        if not 0.0 <= voltage <= self._max_voltage:
            raise ValueError(f"Voltage {voltage} V outside 0..{self._max_voltage} V")
        with self._session() as s:
            s.require_ethernet("CV")
            s.clear_errors()
            s.write_checked(f"SOURce:VOLtage {voltage:.4f}")
            result = float(s.query("SOURce:VOLtage?"))
        logger.info("Voltage set to %.4f V", result)
        return result

    def set_current(self, current):
        """Set the current setpoint in A. Needs CC programming on Ethernet (set_remote)."""
        current = float(current)
        if not 0.0 <= current <= self._max_current:
            raise ValueError(f"Current {current} A outside 0..{self._max_current} A")
        with self._session() as s:
            s.require_ethernet("CC")
            s.clear_errors()
            s.write_checked(f"SOURce:CURrent {current:.4f}")
            result = float(s.query("SOURce:CURrent?"))
        logger.info("Current set to %.4f A", result)
        return result

    def get_status(self):
        """Get setpoints, measurements, output state and programming sources as a dict."""
        with self._session() as s:
            status = {
                "voltage_set": float(s.query("SOURce:VOLtage?")),
                "current_set": float(s.query("SOURce:CURrent?")),
                "voltage": float(s.query("MEASure:VOLtage?")),
                "current": float(s.query("MEASure:CURrent?")),
                "output": s.output_on(),
            }
            status.update(s.sources())
        return status

    # =====================================================================
    #  Generic SCPI Access
    # =====================================================================

    def scpi_query(self, command):
        """Send any SCPI query and return the response string."""
        with self._session() as s:
            return s.query(command)

    def scpi_write(self, command):
        """Send any SCPI command that has no response."""
        with self._session() as s:
            s.write(command)
        logger.info("SCPI write: %s", command)

    # =====================================================================
    #  Utility
    # =====================================================================

    def ping(self):
        """Health check. Returns True if the controller is running."""
        return True

    def close(self):
        """Clean shutdown (connections are per-call, nothing to release)."""
        logger.info("SM18-220 controller shutting down.")


class _Session:
    """One SCPI connection: line-based write/query helpers (LF terminator)."""

    def __init__(self, f):
        self._f = f

    def write(self, command):
        self._f.write((command + "\n").encode())
        self._f.flush()

    def query(self, command):
        self.write(command)
        line = self._f.readline()
        if not line:
            raise RuntimeError(f"SM18-220 closed the connection after {command!r}")
        return line.decode().strip()

    @staticmethod
    def _is_no_error(reply):
        return reply.split(",", 1)[0].strip() == "0"

    def clear_errors(self):
        """Empty the error queue (it holds at most 10 entries)."""
        for _ in range(10):
            if self._is_no_error(self.query("SYSTem:ERRor?")):
                return

    def write_checked(self, command):
        """Send a command and raise if the supply put an error in the queue."""
        self.write(command)
        error = self.query("SYSTem:ERRor?")
        if not self._is_no_error(error):
            raise RuntimeError(f"SM18-220 rejected {command!r}: {error}")

    def output_on(self):
        return self.query("OUTPut?").upper() in ("1", "ON")

    def sources(self):
        return {
            "cv_source": self.query("SYSTem:REMote:CV?"),
            "cc_source": self.query("SYSTem:REMote:CC?"),
        }

    def require_ethernet(self, which):
        source = self.query(f"SYSTem:REMote:{which}?")
        if not _is_ethernet(source):
            raise RuntimeError(
                f"{which} setpoint comes from {source}, not Ethernet: "
                "call set_remote() first (with the output off)"
            )


def get_argparser():
    parser = argparse.ArgumentParser(
        description="ARTIQ NDSP controller for Delta Elektronika SM18-220 power supply"
    )
    common_args.simple_network_args(parser, 3291)
    parser.add_argument(
        "--ip",
        required=True,
        help="IP address of the SM18-220",
    )
    parser.add_argument(
        "--scpi-port",
        type=int,
        default=DEFAULT_PORT,
        help="SCPI TCP port of the SM18-220 (default: %(default)s)",
    )
    parser.add_argument(
        "--max-voltage",
        type=float,
        default=SUPPLY_MAX_VOLTAGE,
        help="highest voltage setpoint accepted, in V (default: %(default)s)",
    )
    parser.add_argument(
        "--max-current",
        type=float,
        default=SUPPLY_MAX_CURRENT,
        help="highest current setpoint accepted, in A (default: %(default)s)",
    )
    common_args.verbosity_args(parser)
    return parser


def main():
    args = get_argparser().parse_args()
    common_args.init_logger_from_args(args)

    logger.info("Starting SM18-220 controller...")
    controller = SM18220Controller(
        ip=args.ip, port=args.scpi_port,
        max_voltage=args.max_voltage, max_current=args.max_current,
    )
    idn = controller.get_idn()
    if not idn.upper().startswith("DELTA"):
        raise RuntimeError(
            f"{args.ip}:{args.scpi_port} is not a Delta Elektronika supply (*IDN? gave {idn!r})"
        )
    if "SM18-220" not in idn:
        logger.warning("Expected an SM18-220 but *IDN? gave %r: check the limits", idn)
    logger.info("SM18-220 controller ready. %s", idn)

    simple_server_loop(
        {"sm18220": controller},
        common_args.bind_address_from_args(args),
        args.port,
    )


if __name__ == "__main__":
    main()
