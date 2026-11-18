#!/usr/bin/env python3
"""
Rohde & Schwarz HMP4040 NDSP Controller for ARTIQ.

Talks SCPI over the HO732 LAN interface (raw socket, port 5025) and exposes
output switching and readback via sipyco RPC so ARTIQ experiments can
control the power supply.

A fresh TCP connection is opened for every call and the front panel is
returned to local control (SYST:LOC) afterwards, so the panel never stays
locked and other clients can still reach the instrument between calls.

Usage:
    python3 aqctl_hmp4040.py -p 3290 --bind ::1 --ip 172.29.13.241

Then in ARTIQ experiments:
    self.hmp4040.get_status()
    self.hmp4040.set_output(False)
"""

import argparse
import contextlib
import logging
import socket

from sipyco.pc_rpc import simple_server_loop
from sipyco import common_args

logger = logging.getLogger(__name__)

DEFAULT_IP = "172.29.13.241"
DEFAULT_PORT = 5025
CHANNELS = (1, 2, 3, 4)
MAX_VOLTAGE = 32.0   # V, HMP4040 per-channel limit
MAX_CURRENT = 10.0   # A, HMP4040 per-channel limit


class HMP4040Controller:
    """
    sipyco RPC interface to the R&S HMP4040 power supply.
    All public methods (without leading underscore) are exposed as RPCs.

    Output model: a channel delivers power only when it is selected
    (OUTP:SEL) AND the master output (OUTP:GEN) is on.
    """

    def __init__(self, ip=DEFAULT_IP, port=DEFAULT_PORT, timeout=3.0):
        self._ip = ip
        self._port = port
        self._timeout = timeout

    @contextlib.contextmanager
    def _session(self):
        """Open a SCPI session; always hand the front panel back on exit."""
        try:
            sock = socket.create_connection((self._ip, self._port), timeout=self._timeout)
        except OSError as e:
            raise RuntimeError(
                f"Could not connect to HMP4040 at {self._ip}:{self._port}: {e}"
            )
        f = sock.makefile("rwb")
        try:
            yield _Session(f)
        finally:
            try:
                f.write(b"SYST:LOC\n")
                f.flush()
            except OSError:
                pass
            f.close()
            sock.close()

    @staticmethod
    def _check_channel(channel):
        channel = int(channel)
        if channel not in CHANNELS:
            raise ValueError(f"Invalid channel {channel}, must be one of {CHANNELS}")
        return channel

    # =====================================================================
    #  System Information
    # =====================================================================

    def get_idn(self):
        """Get the *IDN? identification string."""
        with self._session() as s:
            return s.query("*IDN?")

    def get_error(self):
        """Pop one entry from the SCPI error queue."""
        with self._session() as s:
            return s.query("SYST:ERR?")

    # =====================================================================
    #  Output Switching
    # =====================================================================

    def get_output(self):
        """Get master output state (True = on)."""
        with self._session() as s:
            return s.query("OUTP:GEN?") == "1"

    def set_output(self, enable=True):
        """
        Switch the master output. Channel selections are kept, so turning
        it back on restores exactly the channels that were on before.
        """
        with self._session() as s:
            s.write(f"OUTP:GEN {1 if enable else 0}")
            state = s.query("OUTP:GEN?") == "1"
        logger.info("Master output set to %s", "ON" if state else "OFF")
        return state

    def get_channel_output(self, channel):
        """Get whether a channel is actually delivering power."""
        channel = self._check_channel(channel)
        with self._session() as s:
            s.write(f"INST:NSEL {channel}")
            return s.query("OUTP:SEL?") == "1" and s.query("OUTP:GEN?") == "1"

    def set_channel_output(self, channel, enable=True):
        """
        Switch one channel on or off without changing the others.

        Turning a channel on while the master output is off would also
        energise every other selected channel, so in that case the other
        channels are deselected first (they were not delivering power
        anyway, so their physical state does not change).
        """
        channel = self._check_channel(channel)
        with self._session() as s:
            if enable:
                if s.query("OUTP:GEN?") != "1":
                    for other in CHANNELS:
                        if other != channel:
                            s.write(f"INST:NSEL {other}")
                            s.write("OUTP:SEL 0")
                s.write(f"INST:NSEL {channel}")
                s.write("OUTP:SEL 1")
                s.write("OUTP:GEN 1")
            else:
                s.write(f"INST:NSEL {channel}")
                s.write("OUTP:SEL 0")
            s.write(f"INST:NSEL {channel}")
            state = s.query("OUTP:SEL?") == "1" and s.query("OUTP:GEN?") == "1"
        logger.info("Channel %d output set to %s", channel, "ON" if state else "OFF")
        return state

    # =====================================================================
    #  Setpoints and Readback
    # =====================================================================

    def get_channel(self, channel):
        """Get setpoints, measurements and output state of one channel as a dict."""
        channel = self._check_channel(channel)
        with self._session() as s:
            return s.channel_info(channel)

    def get_status(self):
        """Get master output state and all four channels in one session."""
        with self._session() as s:
            channels = {str(ch): s.channel_info(ch) for ch in CHANNELS}
            master = s.query("OUTP:GEN?") == "1"
        for info in channels.values():
            info["active"] = info["selected"] and master
        return {"master": master, "channels": channels}

    def set_voltage(self, channel, voltage):
        """Set a channel's voltage setpoint in V."""
        channel = self._check_channel(channel)
        voltage = float(voltage)
        if not 0.0 <= voltage <= MAX_VOLTAGE:
            raise ValueError(f"Voltage {voltage} V outside 0..{MAX_VOLTAGE} V")
        with self._session() as s:
            s.write(f"INST:NSEL {channel}")
            s.write(f"VOLT {voltage:.3f}")
            result = float(s.query("VOLT?"))
        logger.info("Channel %d voltage set to %.3f V", channel, result)
        return result

    def set_current(self, channel, current):
        """Set a channel's current limit in A."""
        channel = self._check_channel(channel)
        current = float(current)
        if not 0.0 <= current <= MAX_CURRENT:
            raise ValueError(f"Current {current} A outside 0..{MAX_CURRENT} A")
        with self._session() as s:
            s.write(f"INST:NSEL {channel}")
            s.write(f"CURR {current:.4f}")
            result = float(s.query("CURR?"))
        logger.info("Channel %d current set to %.4f A", channel, result)
        return result

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
        logger.info("HMP4040 controller shutting down.")


class _Session:
    """One SCPI connection: line-based write/query helpers."""

    def __init__(self, f):
        self._f = f

    def write(self, command):
        self._f.write((command + "\n").encode())
        self._f.flush()

    def query(self, command):
        self.write(command)
        line = self._f.readline()
        if not line:
            raise RuntimeError(f"HMP4040 closed the connection after {command!r}")
        return line.decode().strip()

    def channel_info(self, channel):
        self.write(f"INST:NSEL {channel}")
        return {
            "voltage_set": float(self.query("VOLT?")),
            "current_set": float(self.query("CURR?")),
            "voltage": float(self.query("MEAS:VOLT?")),
            "current": float(self.query("MEAS:CURR?")),
            "ovp": float(self.query("VOLT:PROT?")),
            "selected": self.query("OUTP:SEL?") == "1",
        }


def get_argparser():
    parser = argparse.ArgumentParser(
        description="ARTIQ NDSP controller for R&S HMP4040 power supply"
    )
    common_args.simple_network_args(parser, 3290)
    parser.add_argument(
        "--ip",
        default=DEFAULT_IP,
        help="IP address of the HMP4040 (default: %(default)s)",
    )
    parser.add_argument(
        "--scpi-port",
        type=int,
        default=DEFAULT_PORT,
        help="SCPI TCP port of the HMP4040 (default: %(default)s)",
    )
    common_args.verbosity_args(parser)
    return parser


def main():
    args = get_argparser().parse_args()
    common_args.init_logger_from_args(args)

    logger.info("Starting HMP4040 controller...")
    controller = HMP4040Controller(ip=args.ip, port=args.scpi_port)
    logger.info("HMP4040 controller ready. %s", controller.get_idn())

    simple_server_loop(
        {"hmp4040": controller},
        common_args.bind_address_from_args(args),
        args.port,
    )


if __name__ == "__main__":
    main()
