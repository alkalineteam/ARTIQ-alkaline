import time

from artiq.experiment import *


# Highest setpoints this experiment will send.
# TODO: set these to what the coil can take; the supply itself goes to 220 A / 18 V.
MAX_CURRENT_SETPOINT = 10.0  # A
MAX_VOLTAGE_SETPOINT = 18.0  # V
# wait after On/Off before reading back, so the coil current has settled
SETTLE_TIME = 1.0  # s
# after On/Off the measured current must be this close to the setpoint (On) or to 0 (Off),
# otherwise the run fails
CURRENT_READBACK_TOLERANCE = 0.5  # A


class SM18220Control(EnvExperiment):
    """Coil PSU (SM18-220)"""

    def build(self):
        self.setattr_device("sm18220")

        self.setattr_argument("current", NumberValue(default=0.0, unit="A", min=0.0, max=MAX_CURRENT_SETPOINT,
                                                     precision=3, step=0.1),
                              tooltip="Applied when On is pressed (Status and Off ignore it). To change the current "
                                      "while the output is on, enter the new value and press On.")
        self.setattr_argument("voltage", NumberValue(default=MAX_VOLTAGE_SETPOINT, unit="V", min=0.0,
                                                     max=MAX_VOLTAGE_SETPOINT, precision=3, step=0.1),
                              tooltip="Voltage limit, applied with On. A coil normally runs in constant current, "
                                      "so this only caps the voltage.")
        # quickstyle: shown as buttons that submit the experiment immediately when clicked
        self.setattr_argument("output", EnumerationValue(["Status", "On", "Off"], default="Status", quickstyle=True))

    def run(self):
        # the dashboard enforces the argument limits, but artiq_client and artiq_run do not
        if not 0.0 <= self.current <= MAX_CURRENT_SETPOINT:
            raise ValueError("current {} A is outside 0-{} A; nothing sent".format(self.current, MAX_CURRENT_SETPOINT))
        if not 0.0 <= self.voltage <= MAX_VOLTAGE_SETPOINT:
            raise ValueError("voltage {} V is outside 0-{} V; nothing sent".format(self.voltage, MAX_VOLTAGE_SETPOINT))

        if self.output == "On":
            # take the setpoints over Ethernet (refused while the output is on under the front knobs),
            # and set them before switching on, so the output never comes on at an old setpoint
            self.sm18220.set_remote()
            self.sm18220.set_voltage(self.voltage)
            self.sm18220.set_current(self.current)
            self.sm18220.set_output(True)
        elif self.output == "Off":
            self.sm18220.set_output(False)
        if self.output != "Status":
            time.sleep(SETTLE_TIME)

        status = self.sm18220.get_status()
        for key, value in status.items():
            self.set_dataset("sm18220." + key, value, broadcast=True)
        print("SM18-220 {}: {:.3f} V, {:.3f} A, output {}; setpoints {:.3f} V, {:.3f} A "
              "(CV from {}, CC from {})".format(
                  self.output, status["voltage"], status["current"], "ON" if status["output"] else "OFF",
                  status["voltage_set"], status["current_set"], status["cv_source"], status["cc_source"]))

        expected = {"On": self.current, "Off": 0.0}.get(self.output)
        if expected is not None and abs(status["current"] - expected) > CURRENT_READBACK_TOLERANCE:
            raise RuntimeError("SM18-220 reads {:.3f} A after {}, expected {:.3f} A: check the coil wiring, and "
                               "that the voltage limit is high enough for this current".format(
                                   status["current"], self.output, expected))
