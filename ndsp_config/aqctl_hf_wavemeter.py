#!/usr/bin/env python3
"""
HighFinesse Wavemeter NDSP Controller for ARTIQ.

Wraps the full HighFinesse wlmData SDK and exposes all functionality
via sipyco RPC so ARTIQ experiments can control the wavemeter.

Usage:
    python3 aqctl_hf_wavemeter.py -p 3284 --bind ::1

Then in ARTIQ experiments:
    self.wavemeter.get_frequency(2)  # Read channel 2 frequency in THz
"""

import argparse
import ctypes
import logging
import sys
import os

from sipyco.pc_rpc import simple_server_loop
from sipyco import common_args

# wlmData.py, wlmConst.py and wlmData.ini are in this same directory
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, SCRIPT_DIR)

# libwlmData.so looks for wlmData.ini in the CWD — always chdir to
# this directory so it finds the ini regardless of where we run from
os.chdir(SCRIPT_DIR)

import wlmData
import wlmConst

logger = logging.getLogger(__name__)

# Default path to the HighFinesse shared library on Linux
DEFAULT_DLL_PATH = "/usr/lib/libwlmData.so"


class WavemeterController:
    """
    sipyco RPC interface to the HighFinesse wavemeter.
    Exposes the full wlmData SDK as RPC methods.

    All public methods (without leading underscore) are exposed as RPCs.
    """

    def __init__(self, dll_path=DEFAULT_DLL_PATH):
        self._dll_path = dll_path
        self._load_dll()
        self._check_server()

    def _load_dll(self):
        """Load the wlmData shared library."""
        try:
            wlmData.LoadDLL(self._dll_path)
            logger.info("Loaded wlmData library from %s", self._dll_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not load wlmData library from {self._dll_path}: {e}"
            )

    def _check_server(self):
        """Verify that a WLM server instance is reachable."""
        count = wlmData.dll.GetWLMCount(0)
        if count == 0:
            logger.warning("No running wlmServer instance found.")
        else:
            ver = [wlmData.dll.GetWLMVersion(i) for i in range(4)]
            logger.info("Connected to WLM Version: [%s.%s.%s.%s]", *ver)

    def _frequency_to_result(self, freq):
        """Convert a raw frequency/wavelength value to a float or error string."""
        if freq == wlmConst.ErrWlmMissing:
            return "WLM inactive"
        elif freq == wlmConst.ErrNoSignal:
            return "No signal"
        elif freq == wlmConst.ErrBadSignal:
            return "Bad signal"
        elif freq == wlmConst.ErrLowSignal:
            return "Low signal"
        elif freq == wlmConst.ErrBigSignal:
            return "High signal"
        elif freq == wlmConst.ErrOutOfRange:
            return "Out of range"
        elif freq == wlmConst.ErrNoValue:
            return "No value"
        elif freq < 0:
            return f"Error code: {int(freq)}"
        return float(freq)

    # =====================================================================
    #  General Information
    # =====================================================================

    def get_wlm_version(self):
        """Get WLM version string (type.ver.rev.build)."""
        ver = [wlmData.dll.GetWLMVersion(i) for i in range(4)]
        return "%s.%s.%s.%s" % tuple(ver)

    def get_wlm_count(self):
        """Get number of running WLM server instances."""
        return int(wlmData.dll.GetWLMCount(0))

    def get_wlm_index(self, ver=0):
        """Get WLM index."""
        return int(wlmData.dll.GetWLMIndex(int(ver)))

    def get_channel_count(self):
        """Get the number of available channels."""
        return int(wlmData.dll.GetChannelsCount(0))

    # =====================================================================
    #  Measurement: Frequency, Wavelength, Linewidth, Power
    # =====================================================================

    def get_frequency(self, channel=1):
        """Get frequency of a channel in THz. Returns float or error string."""
        freq = wlmData.dll.GetFrequencyNum(int(channel), 0.0)
        return self._frequency_to_result(freq)

    def get_wavelength(self, channel=1):
        """Get wavelength of a channel in nm (vacuum). Returns float or error string."""
        wl = wlmData.dll.GetWavelengthNum(int(channel), 0.0)
        if wl <= 0:
            return self._frequency_to_result(wl)
        return float(wl)

    def get_calibration_wavelength(self, ba=0):
        """Get calibration wavelength."""
        return float(wlmData.dll.GetCalWavelength(int(ba), 0.0))

    def get_calibration_effect(self):
        """Get calibration effect value."""
        return float(wlmData.dll.GetCalibrationEffect(0.0))

    def get_linewidth(self, channel=1):
        """Get linewidth of a channel. Returns float or error string."""
        lw = wlmData.dll.GetLinewidthNum(int(channel), 0.0)
        return self._frequency_to_result(lw)

    def get_distance(self):
        """Get distance measurement."""
        return float(wlmData.dll.GetDistance(0.0))

    def get_power(self, channel=1):
        """Get optical power of a channel."""
        return float(wlmData.dll.GetPowerNum(int(channel), 0.0))

    def get_intensity(self, channel=1):
        """Get intensity of a channel."""
        return float(wlmData.dll.GetIntensityNum(int(channel), 0.0))

    def get_amplitude(self, channel=1, index=0):
        """Get amplitude for a channel (index: 0=Min1, 1=Min2, 2=Max1, 3=Max2, 4=Avg1, 5=Avg2)."""
        return int(wlmData.dll.GetAmplitudeNum(int(channel), int(index), 0))

    def get_analog_in(self):
        """Get analog input value."""
        return float(wlmData.dll.GetAnalogIn(0.0))

    def get_multimode_info(self, channel=1, info_type=0, mode=0):
        """Get multimode information for a channel."""
        val = ctypes.c_double(0.0)
        result = float(wlmData.dll.GetMultimodeInfo(int(channel), int(info_type), int(mode), ctypes.byref(val)))
        return {"result": result, "value": val.value}

    # =====================================================================
    #  Temperature & Pressure
    # =====================================================================

    def get_temperature(self):
        """Get internal temperature in °C. Returns float or 'Not available'."""
        temp = wlmData.dll.GetTemperature(0.0)
        if temp <= wlmConst.ErrTemperature:
            return "Not available"
        return float(temp)

    def set_temperature(self, temp):
        """Set temperature value for compensation."""
        return int(wlmData.dll.SetTemperature(float(temp)))

    def get_pressure(self):
        """Get internal pressure in mbar. Returns float or 'Not available'."""
        pressure = wlmData.dll.GetPressure(0.0)
        if pressure <= wlmConst.ErrTemperature:
            return "Not available"
        return float(pressure)

    def set_pressure(self, mode, pressure):
        """Set pressure value (mode: pressure mode)."""
        return int(wlmData.dll.SetPressure(int(mode), float(pressure)))

    def get_air_parameters(self, mode):
        """Get air parameters (temperature, pressure, humidity)."""
        state = ctypes.c_int32(0)
        val = ctypes.c_double(0.0)
        result = int(wlmData.dll.GetAirParameters(int(mode), ctypes.byref(state), ctypes.byref(val)))
        return {"result": result, "state": state.value, "value": val.value}

    def set_air_parameters(self, mode, state, val):
        """Set air parameters."""
        return int(wlmData.dll.SetAirParameters(int(mode), int(state), float(val)))

    def get_external_input(self, index=0):
        """Get external input value."""
        return float(wlmData.dll.GetExternalInput(int(index), 0.0))

    def set_external_input(self, index, value):
        """Set external input value."""
        return int(wlmData.dll.SetExternalInput(int(index), float(value)))

    # =====================================================================
    #  Exposure Control
    # =====================================================================

    def get_exposure(self, channel=1, array_index=1):
        """Get exposure time of a channel in ms."""
        expo = wlmData.dll.GetExposureNum(int(channel), int(array_index), 0)
        if expo == wlmConst.ErrWlmMissing:
            return "WLM not active"
        elif expo == wlmConst.ErrNotAvailable:
            return "Not available"
        return int(expo)

    def set_exposure(self, channel=1, array_index=1, exposure=1):
        """Set exposure time of a channel in ms."""
        return int(wlmData.dll.SetExposureNum(int(channel), int(array_index), int(exposure)))

    def get_exposure_mode(self, channel=1):
        """Get exposure mode for a channel (True=auto, False=manual)."""
        return bool(wlmData.dll.GetExposureModeNum(int(channel), False))

    def set_exposure_mode(self, auto=True, channel=1):
        """Set exposure mode for a channel (True=auto, False=manual)."""
        return int(wlmData.dll.SetExposureModeNum(int(channel), bool(auto)))

    def get_exposure_range(self, index=0):
        """Get exposure range (index: 0=Min, 1=Max, 2=Min2, 3=Max2)."""
        return int(wlmData.dll.GetExposureRange(int(index)))

    def get_auto_exposure_setting(self, channel, setting):
        """Get auto-exposure setting for a channel."""
        ival = ctypes.c_int32(0)
        dval = ctypes.c_double(0.0)
        result = int(wlmData.dll.GetAutoExposureSetting(int(channel), int(setting), ctypes.byref(ival), ctypes.byref(dval)))
        return {"result": result, "int_value": ival.value, "double_value": dval.value}

    def set_auto_exposure_setting(self, channel, setting, ival, dval):
        """Set auto-exposure setting for a channel."""
        return int(wlmData.dll.SetAutoExposureSetting(int(channel), int(setting), int(ival), float(dval)))

    # =====================================================================
    #  Result & Display Mode
    # =====================================================================

    def get_result_mode(self):
        """Get result mode (0=WL vacuum, 1=WL air, 2=frequency, 3=wavenumber, 4=photon energy)."""
        return int(wlmData.dll.GetResultMode(0))

    def set_result_mode(self, mode):
        """Set result mode (0=WL vacuum, 1=WL air, 2=frequency, 3=wavenumber, 4=photon energy)."""
        return int(wlmData.dll.SetResultMode(int(mode)))

    def get_display_mode(self):
        """Get display mode."""
        return int(wlmData.dll.GetDisplayMode(0))

    def set_display_mode(self, mode):
        """Set display mode."""
        return int(wlmData.dll.SetDisplayMode(int(mode)))

    # =====================================================================
    #  Range & Precision
    # =====================================================================

    def get_range(self):
        """Get measurement range."""
        return int(wlmData.dll.GetRange(0))

    def set_range(self, r):
        """Set measurement range."""
        return int(wlmData.dll.SetRange(int(r)))

    def get_wide_mode(self):
        """Get precision mode (0=Fine, 1=Wide)."""
        return int(wlmData.dll.GetWideMode(0))

    def set_wide_mode(self, mode):
        """Set precision mode (0=Fine, 1=Wide)."""
        return int(wlmData.dll.SetWideMode(int(mode)))

    def get_fast_mode(self):
        """Get fast mode state."""
        return bool(wlmData.dll.GetFastMode(False))

    def set_fast_mode(self, enable=True):
        """Set fast mode state."""
        return int(wlmData.dll.SetFastMode(bool(enable)))

    # =====================================================================
    #  Pulse Mode
    # =====================================================================

    def get_pulse_mode(self):
        """Get pulse mode (0=CW, 1=single pulse, 2=double/external)."""
        return int(wlmData.dll.GetPulseMode(0))

    def set_pulse_mode(self, mode):
        """Set pulse mode."""
        return int(wlmData.dll.SetPulseMode(int(mode)))

    def get_pulse_delay(self):
        """Get pulse delay."""
        return int(wlmData.dll.GetPulseDelay(0))

    def set_pulse_delay(self, delay):
        """Set pulse delay."""
        return int(wlmData.dll.SetPulseDelay(int(delay)))

    # =====================================================================
    #  Linewidth Mode
    # =====================================================================

    def get_linewidth_mode(self):
        """Get linewidth mode state."""
        return bool(wlmData.dll.GetLinewidthMode(False))

    def set_linewidth_mode(self, enable=True):
        """Set linewidth mode state."""
        return int(wlmData.dll.SetLinewidthMode(bool(enable)))

    # =====================================================================
    #  Distance Mode
    # =====================================================================

    def get_distance_mode(self):
        """Get distance mode state."""
        return bool(wlmData.dll.GetDistanceMode(False))

    def set_distance_mode(self, enable=True):
        """Set distance mode state."""
        return int(wlmData.dll.SetDistanceMode(bool(enable)))

    # =====================================================================
    #  Multichannel Switcher
    # =====================================================================

    def get_switcher_mode(self):
        """Get switcher mode (0=off, 1=on)."""
        return int(wlmData.dll.GetSwitcherMode(0))

    def set_switcher_mode(self, enable=True):
        """Set switcher mode (True=on, False=off)."""
        return int(wlmData.dll.SetSwitcherMode(int(enable)))

    def get_switcher_channel(self):
        """Get current active switcher channel."""
        return int(wlmData.dll.GetSwitcherChannel(0))

    def set_switcher_channel(self, channel):
        """Set active switcher channel."""
        return int(wlmData.dll.SetSwitcherChannel(int(channel)))

    def get_switcher_signal_states(self, signal):
        """Get switcher signal states (use/show) for a signal."""
        use = ctypes.c_int32(0)
        show = ctypes.c_int32(0)
        result = int(wlmData.dll.GetSwitcherSignalStates(int(signal), ctypes.byref(use), ctypes.byref(show)))
        return {"result": result, "use": use.value, "show": show.value}

    def set_switcher_signal_states(self, signal, use, show):
        """Set switcher signal states."""
        return int(wlmData.dll.SetSwitcherSignalStates(int(signal), int(use), int(show)))

    def set_switcher_signal(self, signal, use, show):
        """Set switcher signal."""
        return int(wlmData.dll.SetSwitcherSignal(int(signal), int(use), int(show)))

    # =====================================================================
    #  Active Channel
    # =====================================================================

    def get_active_channel(self, mode=0):
        """Get active channel."""
        port = ctypes.c_int32(0)
        result = int(wlmData.dll.GetActiveChannel(int(mode), ctypes.byref(port), 0))
        return {"channel": result, "port": port.value}

    def set_active_channel(self, mode, port, channel):
        """Set active channel."""
        return int(wlmData.dll.SetActiveChannel(int(mode), int(port), int(channel), 0))

    # =====================================================================
    #  Operation Control
    # =====================================================================

    def get_operation_state(self):
        """Get operation state (0=stopped, 1=adjustment, 2=measurement)."""
        return int(wlmData.dll.GetOperationState(0))

    def operation(self, op):
        """Control operation (0=stop, 1=adjustment, 2=measurement)."""
        return int(wlmData.dll.Operation(int(op)))

    def calibration(self, cal_type, unit, value, channel):
        """Perform calibration."""
        return int(wlmData.dll.Calibration(int(cal_type), int(unit), float(value), int(channel)))

    # =====================================================================
    #  Auto Calibration
    # =====================================================================

    def get_auto_cal_mode(self):
        """Get auto-calibration mode."""
        return int(wlmData.dll.GetAutoCalMode(0))

    def set_auto_cal_mode(self, mode):
        """Set auto-calibration mode."""
        return int(wlmData.dll.SetAutoCalMode(int(mode)))

    def get_auto_cal_setting(self, setting):
        """Get auto-calibration setting."""
        val = ctypes.c_int32(0)
        res2 = ctypes.c_int32(0)
        result = int(wlmData.dll.GetAutoCalSetting(int(setting), ctypes.byref(val), 0, ctypes.byref(res2)))
        return {"result": result, "value": val.value}

    def set_auto_cal_setting(self, setting, val):
        """Set auto-calibration setting."""
        return int(wlmData.dll.SetAutoCalSetting(int(setting), int(val), 0, 0))

    # =====================================================================
    #  Triggering & Interval
    # =====================================================================

    def trigger_measurement(self, action):
        """Trigger a measurement (0=continue, 1=interrupt, 2=poll, 3=success)."""
        return int(wlmData.dll.TriggerMeasurement(int(action)))

    def get_trigger_state(self):
        """Get trigger state."""
        return int(wlmData.dll.GetTriggerState(0))

    def get_interval(self):
        """Get measurement interval."""
        return int(wlmData.dll.GetInterval(0))

    def set_interval(self, interval):
        """Set measurement interval."""
        return int(wlmData.dll.SetInterval(int(interval)))

    def get_interval_mode(self):
        """Get interval mode state."""
        return bool(wlmData.dll.GetIntervalMode(False))

    def set_interval_mode(self, enable=True):
        """Set interval mode state."""
        return int(wlmData.dll.SetIntervalMode(bool(enable)))

    def get_internal_trigger_rate(self):
        """Get internal trigger rate."""
        return float(wlmData.dll.GetInternalTriggerRate(0.0))

    def set_internal_trigger_rate(self, rate):
        """Set internal trigger rate."""
        return int(wlmData.dll.SetInternalTriggerRate(float(rate)))

    # =====================================================================
    #  Measurement Delay
    # =====================================================================

    def set_measurement_delay_method(self, mode, delay):
        """Set measurement delay method."""
        return int(wlmData.dll.SetMeasurementDelayMethod(int(mode), int(delay)))

    # =====================================================================
    #  Background
    # =====================================================================

    def get_background(self):
        """Get background subtraction state."""
        return int(wlmData.dll.GetBackground(0))

    def set_background(self, bg):
        """Set background subtraction."""
        return int(wlmData.dll.SetBackground(int(bg)))

    # =====================================================================
    #  Averaging
    # =====================================================================

    def get_averaging_setting(self, channel, setting, default=0):
        """Get averaging setting for a channel."""
        return int(wlmData.dll.GetAveragingSettingNum(int(channel), int(setting), int(default)))

    def set_averaging_setting(self, channel, setting, value):
        """Set averaging setting for a channel."""
        return int(wlmData.dll.SetAveragingSettingNum(int(channel), int(setting), int(value)))

    # =====================================================================
    #  Signal Delay & Shift
    # =====================================================================

    def get_delay(self):
        """Get delay value."""
        return int(wlmData.dll.GetDelay(0))

    def set_delay(self, d):
        """Set delay value."""
        return int(wlmData.dll.SetDelay(int(d)))

    def get_shift(self):
        """Get shift value."""
        return int(wlmData.dll.GetShift(0))

    def set_shift(self, s):
        """Set shift value."""
        return int(wlmData.dll.SetShift(int(s)))

    def get_shift2(self):
        """Get shift2 value."""
        return int(wlmData.dll.GetShift2(0))

    def set_shift2(self, s):
        """Set shift2 value."""
        return int(wlmData.dll.SetShift2(int(s)))

    # =====================================================================
    #  Gain
    # =====================================================================

    def get_gain(self, channel, index, mode):
        """Get gain setting."""
        gain_val = ctypes.c_double(0.0)
        result = float(wlmData.dll.GetGain(int(channel), int(index), int(mode), ctypes.byref(gain_val)))
        return {"result": result, "gain": gain_val.value}

    def set_gain(self, channel, index, mode, gain):
        """Set gain setting."""
        return int(wlmData.dll.SetGain(int(channel), int(index), int(mode), float(gain)))

    # =====================================================================
    #  Peak Analysis
    # =====================================================================

    def get_min_peak(self):
        """Get minimum peak value (interferometer 1)."""
        return int(wlmData.dll.GetMinPeak(0))

    def get_min_peak2(self):
        """Get minimum peak value (interferometer 2)."""
        return int(wlmData.dll.GetMinPeak2(0))

    def get_max_peak(self):
        """Get maximum peak value (interferometer 1)."""
        return int(wlmData.dll.GetMaxPeak(0))

    def get_max_peak2(self):
        """Get maximum peak value (interferometer 2)."""
        return int(wlmData.dll.GetMaxPeak2(0))

    def get_avg_peak(self):
        """Get average peak value (interferometer 1)."""
        return int(wlmData.dll.GetAvgPeak(0))

    def get_avg_peak2(self):
        """Get average peak value (interferometer 2)."""
        return int(wlmData.dll.GetAvgPeak2(0))

    def set_avg_peak(self, pa):
        """Set pattern averaging."""
        return int(wlmData.dll.SetAvgPeak(int(pa)))

    # =====================================================================
    #  Pattern & Analysis Data
    # =====================================================================

    def get_pattern_item_size(self, index):
        """Get pattern item size for a given signal index."""
        return int(wlmData.dll.GetPatternItemSize(int(index)))

    def get_pattern_item_count(self, index):
        """Get pattern item count for a given signal index."""
        return int(wlmData.dll.GetPatternItemCount(int(index)))

    def get_pattern_data(self, channel, index):
        """Get pattern data for a channel and signal index. Returns list of int values."""
        count = wlmData.dll.GetPatternItemCount(int(index))
        if count <= 0:
            return []
        array = (ctypes.c_int32 * count)()
        result = wlmData.dll.GetPatternDataNum(int(channel), int(index), ctypes.cast(array, ctypes.c_void_p))
        if result < 0:
            return f"Error code: {result}"
        return list(array)

    def set_pattern(self, index, enable):
        """Enable/disable pattern acquisition (0=disable, 1=enable)."""
        return int(wlmData.dll.SetPattern(int(index), int(enable)))

    def get_analysis_mode(self):
        """Get analysis mode state."""
        return bool(wlmData.dll.GetAnalysisMode(False))

    def set_analysis_mode(self, enable=True):
        """Set analysis mode state."""
        return int(wlmData.dll.SetAnalysisMode(bool(enable)))

    def get_analysis_item_size(self, index):
        """Get analysis item size."""
        return int(wlmData.dll.GetAnalysisItemSize(int(index)))

    def get_analysis_item_count(self, index):
        """Get analysis item count."""
        return int(wlmData.dll.GetAnalysisItemCount(int(index)))

    def set_analysis(self, index, enable):
        """Enable/disable analysis (0=disable, 1=enable)."""
        return int(wlmData.dll.SetAnalysis(int(index), int(enable)))

    # =====================================================================
    #  Link State
    # =====================================================================

    def get_link_state(self):
        """Get link state."""
        return bool(wlmData.dll.GetLinkState(False))

    def set_link_state(self, state):
        """Set link state."""
        return int(wlmData.dll.SetLinkState(bool(state)))

    # =====================================================================
    #  Deviation (Laser Control) & PID
    # =====================================================================

    def get_deviation_mode(self):
        """Get deviation/regulation mode state."""
        return bool(wlmData.dll.GetDeviationMode(False))

    def set_deviation_mode(self, enable=True):
        """Enable/disable deviation/regulation mode."""
        return int(wlmData.dll.SetDeviationMode(bool(enable)))

    def get_deviation_reference(self):
        """Get deviation reference value (target frequency/wavelength)."""
        return float(wlmData.dll.GetDeviationReference(0.0))

    def set_deviation_reference(self, ref):
        """Set deviation reference value (target frequency/wavelength)."""
        return int(wlmData.dll.SetDeviationReference(float(ref)))

    def get_deviation_sensitivity(self):
        """Get deviation sensitivity."""
        return int(wlmData.dll.GetDeviationSensitivity(0))

    def set_deviation_sensitivity(self, ds):
        """Set deviation sensitivity."""
        return int(wlmData.dll.SetDeviationSensitivity(int(ds)))

    def get_deviation_signal(self, port=0):
        """Get deviation signal value (PID output). Use port=0 for default."""
        if port == 0:
            return float(wlmData.dll.GetDeviationSignal(0.0))
        return float(wlmData.dll.GetDeviationSignalNum(int(port), 0.0))

    def set_deviation_signal(self, value, port=0):
        """Set deviation signal value."""
        if port == 0:
            return int(wlmData.dll.SetDeviationSignal(float(value)))
        return int(wlmData.dll.SetDeviationSignalNum(int(port), float(value)))

    def raise_deviation_signal(self, signal_type, signal_value):
        """Raise deviation signal."""
        return float(wlmData.dll.RaiseDeviationSignal(int(signal_type), float(signal_value)))

    def get_pid_setting(self, setting, port):
        """
        Get PID setting.
        Settings: cmiPID_T, cmiPID_P, cmiPID_I, cmiPID_D, etc. (see wlmConst).
        """
        iset = ctypes.c_int32(0)
        dset = ctypes.c_double(0.0)
        result = int(wlmData.dll.GetPIDSetting(int(setting), int(port), ctypes.byref(iset), ctypes.byref(dset)))
        return {"result": result, "int_value": iset.value, "double_value": dset.value}

    def set_pid_setting(self, setting, port, iset=0, dset=0.0):
        """
        Set PID setting.
        Settings: cmiPID_T, cmiPID_P, cmiPID_I, cmiPID_D, etc. (see wlmConst).
        """
        return int(wlmData.dll.SetPIDSetting(int(setting), int(port), int(iset), float(dset)))

    def clear_pid_history(self, port=0):
        """Clear PID history for a port."""
        return int(wlmData.dll.ClearPIDHistory(int(port)))

    # =====================================================================
    #  Unit Conversion
    # =====================================================================

    def convert_unit(self, value, unit_from, unit_to):
        """
        Convert between units.
        Units: 0=WL vacuum, 1=WL air, 2=frequency, 3=wavenumber, 4=photon energy.
        """
        return float(wlmData.dll.ConvertUnit(float(value), int(unit_from), int(unit_to)))

    def convert_delta_unit(self, base, delta, unit_base, unit_from, unit_to):
        """Convert delta between units."""
        return float(wlmData.dll.ConvertDeltaUnit(float(base), float(delta), int(unit_base), int(unit_from), int(unit_to)))

    # =====================================================================
    #  Utility
    # =====================================================================

    def ping(self):
        """Health check. Returns True if the controller is running."""
        return True

    def close(self):
        """Clean shutdown."""
        logger.info("Wavemeter controller shutting down.")


def get_argparser():
    parser = argparse.ArgumentParser(
        description="ARTIQ NDSP controller for HighFinesse wavemeter"
    )
    common_args.simple_network_args(parser, 3284)
    parser.add_argument(
        "--dll-path",
        default=DEFAULT_DLL_PATH,
        help="Path to libwlmData.so (default: %(default)s)",
    )
    common_args.verbosity_args(parser)
    return parser


def main():
    args = get_argparser().parse_args()
    common_args.init_logger_from_args(args)

    logger.info("Starting HighFinesse wavemeter controller...")
    controller = WavemeterController(dll_path=args.dll_path)

    version = controller.get_wlm_version()
    logger.info("Wavemeter controller ready. WLM version: %s", version)

    simple_server_loop(
        {"wavemeter": controller},
        common_args.bind_address_from_args(args),
        args.port,
    )


if __name__ == "__main__":
    main()
