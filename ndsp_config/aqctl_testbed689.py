#!/usr/bin/env python3
"""
Toptica DLC Pro NDSP Controller for ARTIQ (testbed689).

Wraps the Toptica Laser SDK and exposes DLC Pro laser functionality
via sipyco RPC so ARTIQ experiments can monitor and control the laser.

Usage:
    python3 aqctl_testbed689.py -p 3286 --bind ::1 --ip 172.29.13.247

Then in ARTIQ experiments:
    self.testbed689.get_current()
    self.testbed689.get_temperature()
"""

import argparse
import logging
import struct
import sys

from sipyco.pc_rpc import simple_server_loop
from sipyco import common_args

from toptica.lasersdk.dlcpro.v2_0_3 import DLCpro, NetworkConnection

logger = logging.getLogger(__name__)

DEFAULT_IP = "172.29.13.247"
DEFAULT_PORT = 1998


class TopticaController:
    """
    sipyco RPC interface to the Toptica DLC Pro laser controller.
    All public methods (without leading underscore) are exposed as RPCs.
    """

    def __init__(self, ip=DEFAULT_IP, port=DEFAULT_PORT):
        self._ip = ip
        self._port = port
        self._connection = None
        self._dlc = None
        self._connect()

    def _connect(self):
        """Establish connection to the DLC Pro."""
        try:
            self._connection = NetworkConnection(self._ip, self._port)
            self._dlc = DLCpro(self._connection)
            self._dlc.open()
            logger.info("Connected to DLC Pro at %s:%d", self._ip, self._port)
        except Exception as e:
            raise RuntimeError(
                f"Could not connect to DLC Pro at {self._ip}:{self._port}: {e}"
            )

    def _reconnect(self):
        """Attempt to reconnect if connection was lost."""
        try:
            self.close()
        except Exception:
            pass
        self._connect()

    # =====================================================================
    #  System Information
    # =====================================================================

    def get_system_type(self):
        """Get system type string."""
        return str(self._dlc.system_type.get())

    def get_serial_number(self):
        """Get serial number."""
        return str(self._dlc.serial_number.get())

    def get_firmware_version(self):
        """Get firmware version."""
        return str(self._dlc.fw_ver.get())

    def get_uptime(self):
        """Get uptime string."""
        return str(self._dlc.uptime_txt.get())

    def get_laser_type(self):
        """Get laser1 type."""
        return str(self._dlc.laser1.type.get())

    def get_product_name(self):
        """Get laser1 product name."""
        return str(self._dlc.laser1.product_name.get())

    def get_laser_info(self):
        """Get all laser info as a dict."""
        return {
            "system_type": str(self._dlc.system_type.get()),
            "serial_number": str(self._dlc.serial_number.get()),
            "firmware_version": str(self._dlc.fw_ver.get()),
            "uptime": str(self._dlc.uptime_txt.get()),
            "laser_type": str(self._dlc.laser1.type.get()),
            "product_name": str(self._dlc.laser1.product_name.get()),
        }

    # =====================================================================
    #  Emission
    # =====================================================================

    def get_emission(self):
        """Get emission state (True = on, False = off)."""
        return bool(self._dlc.laser1.emission.get())

    def set_emission(self, enable=True):
        """Turn laser emission on or off."""
        self._dlc.laser1.dl.cc.enabled.set(bool(enable))
        logger.info("Emission set to %s", "ON" if enable else "OFF")
        return self.get_emission()

    # =====================================================================
    #  Current Control
    # =====================================================================

    def get_current(self):
        """Get actual laser current in mA."""
        return float(self._dlc.laser1.dl.cc.current_act.get())

    def get_current_setpoint(self):
        """Get current setpoint in mA."""
        return float(self._dlc.laser1.dl.cc.current_set.get())

    def set_current(self, current_ma):
        """Set laser current setpoint in mA."""
        self._dlc.laser1.dl.cc.current_set.set(float(current_ma))
        logger.info("Current setpoint set to %.1f mA", current_ma)
        return self.get_current_setpoint()

    # =====================================================================
    #  Temperature Control
    # =====================================================================

    def get_temperature(self):
        """Get actual diode temperature in °C."""
        return float(self._dlc.laser1.dl.tc.temp_act.get())

    def get_temperature_setpoint(self):
        """Get temperature setpoint in °C."""
        return float(self._dlc.laser1.dl.tc.temp_set.get())

    def set_temperature(self, temp_c):
        """Set temperature setpoint in °C."""
        self._dlc.laser1.dl.tc.temp_set.set(float(temp_c))
        logger.info("Temperature setpoint set to %.3f °C", temp_c)
        return self.get_temperature_setpoint()

    # =====================================================================
    #  Piezo / Scan
    # =====================================================================

    def get_piezo_voltage(self):
        """Get scan offset (piezo voltage) in V."""
        return float(self._dlc.laser1.scan.offset.get())

    def set_piezo_voltage(self, voltage):
        """Set scan offset (piezo voltage) in V."""
        self._dlc.laser1.scan.offset.set(float(voltage))
        logger.info("Piezo voltage set to %.3f V", voltage)
        return self.get_piezo_voltage()

    def get_scan_enabled(self):
        """Get scan enabled state."""
        return bool(self._dlc.laser1.scan.enabled.get())

    def set_scan_enabled(self, enable=True):
        """Enable or disable scan."""
        self._dlc.laser1.scan.enabled.set(bool(enable))
        logger.info("Scan %s", "enabled" if enable else "disabled")
        return self.get_scan_enabled()

    def get_scan_frequency(self):
        """Get scan frequency in Hz."""
        return float(self._dlc.laser1.scan.frequency.get())

    def set_scan_frequency(self, freq_hz):
        """Set scan frequency in Hz."""
        self._dlc.laser1.scan.frequency.set(float(freq_hz))
        return self.get_scan_frequency()

    def get_scan_amplitude(self):
        """Get scan amplitude in V."""
        return float(self._dlc.laser1.scan.amplitude.get())

    def set_scan_amplitude(self, amplitude):
        """Set scan amplitude in V."""
        self._dlc.laser1.scan.amplitude.set(float(amplitude))
        return self.get_scan_amplitude()

    # =====================================================================
    #  Scope
    # =====================================================================

    def get_scope_data(self, channel=1, signal=4):
        """
        Get scope data.

        Args:
            channel: Scope channel (1 or 2).
            signal: Signal type index.

        Returns:
            list of float values.
        """
        scope_ch = getattr(self._dlc.laser1.scope, f"channel{channel}")
        scope_ch.signal.set(int(signal))
        raw_data = self._dlc.laser1.scope.data.get()
        return self._decode_scope_data(raw_data)

    def get_scope_channel_name(self, channel=1):
        """Get the name of the signal on a scope channel."""
        scope_ch = getattr(self._dlc.laser1.scope, f"channel{channel}")
        return str(scope_ch.name.get())

    def _decode_scope_data(self, raw_data):
        """Decode binary scope data to float values."""
        header_end = raw_data.find(b'\x00') + 1
        data = raw_data[header_end:]
        num_floats = len(data) // 4
        return list(struct.unpack(f'<{num_floats}f', data[:num_floats * 4]))

    # =====================================================================
    #  Generic Parameter Access (full SDK coverage)
    # =====================================================================

    def get_param(self, path):
        """
        Get any SDK parameter by its dot-path.

        Example paths:
            'laser1.dl.cc.current_act'
            'laser1.dl.tc.temp_act'
            'laser1.scan.offset'
            'laser1.emission'
            'system_type'

        Returns the parameter value (type depends on the parameter).
        """
        obj = self._dlc
        for attr in path.split("."):
            obj = getattr(obj, attr)
        result = obj.get()
        # Convert to JSON-safe types
        if isinstance(result, bytes):
            return result.hex()
        return result

    def set_param(self, path, value):
        """
        Set any SDK parameter by its dot-path.

        Example:
            set_param('laser1.dl.cc.current_set', 50.0)
            set_param('laser1.scan.offset', 65.0)
            set_param('laser1.dl.cc.enabled', True)
        """
        obj = self._dlc
        for attr in path.split("."):
            obj = getattr(obj, attr)
        obj.set(value)
        logger.info("Set %s = %s", path, value)
        return obj.get()

    # =====================================================================
    #  Utility
    # =====================================================================

    def ping(self):
        """Health check. Returns True if the controller is running."""
        return True

    def close(self):
        """Clean shutdown."""
        if self._dlc is not None:
            try:
                self._dlc.close()
            except Exception:
                pass
        logger.info("Toptica controller shutting down.")


def get_argparser():
    parser = argparse.ArgumentParser(
        description="ARTIQ NDSP controller for Toptica DLC Pro laser (testbed689)"
    )
    common_args.simple_network_args(parser, 3286)
    parser.add_argument(
        "--ip",
        default=DEFAULT_IP,
        help="IP address of the DLC Pro (default: %(default)s)",
    )
    parser.add_argument(
        "--laser-port",
        type=int,
        default=DEFAULT_PORT,
        help="TCP port of the DLC Pro (default: %(default)s)",
    )
    common_args.verbosity_args(parser)
    return parser


def main():
    args = get_argparser().parse_args()
    common_args.init_logger_from_args(args)

    logger.info("Starting Toptica DLC Pro controller (testbed689)...")
    controller = TopticaController(ip=args.ip, port=args.laser_port)

    info = controller.get_laser_info()
    logger.info("Toptica controller ready. %s (S/N: %s, FW: %s)",
                info["product_name"], info["serial_number"], info["firmware_version"])

    simple_server_loop(
        {"testbed689": controller},
        common_args.bind_address_from_args(args),
        args.port,
    )


if __name__ == "__main__":
    main()
