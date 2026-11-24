import time

from artiq.experiment import *


# Highest setpoints this experiment will send (the supply itself goes to 220 A / 18 V, but maybe lowered due to resistance).
# The controller is started with the same current cap: SM18220_MAX_CURRENT in flake.nix
# and --max-current in device_db.py.
MAX_CURRENT_SETPOINT = 125.0  # A
MAX_VOLTAGE_SETPOINT = 18.0  # V, the supply's maximum (it refuses 18.18 V)
# wait after On/Off before reading back, so the coil current has settled
SETTLE_TIME = 1.0  # s
# after On/Off the measured current must be this close to the setpoint (On) or to 0 (Off),
# otherwise the run fails
CURRENT_READBACK_TOLERANCE = 0.5  # A


class Coil_Control(EnvExperiment):
    # """Coil PSU (SM18-220)"""

    def build(self):
        self.setattr_device("sm18220")

        self.setattr_argument("current", NumberValue(default=0.0, unit="A", min=0.0, max=MAX_CURRENT_SETPOINT,
                                                     precision=3, step=0.1),
                              tooltip="Applied by On and Set (Status and Off ignore it).")
        self.setattr_argument("voltage", NumberValue(default=MAX_VOLTAGE_SETPOINT, unit="V", min=0.0,
                                                     max=MAX_VOLTAGE_SETPOINT, precision=3, step=0.1),
                              tooltip="Voltage limit, applied by On and Set. A coil normally runs in constant "
                                      "current, so this only caps the voltage.")
        # quickstyle: shown as buttons that submit the experiment immediately when clicked,
        # so enter the current and voltage first
        self.setattr_argument("output", EnumerationValue(["Status", "On", "Set", "Off"], default="Status",
                                                         quickstyle=True),
                              tooltip="On: apply current and voltage, then switch the output on. "
                                      "Set: apply current and voltage, leave the output as it is. "
                                      "Off: switch the output off. Status: read only.")

    def run(self):
        # the dashboard enforces the argument limits, but artiq_client and artiq_run do not
        if not 0.0 <= self.current <= MAX_CURRENT_SETPOINT:
            raise ValueError("current {} A is outside 0-{} A; nothing sent".format(self.current, MAX_CURRENT_SETPOINT))
        if not 0.0 <= self.voltage <= MAX_VOLTAGE_SETPOINT:
            raise ValueError("voltage {} V is outside 0-{} V; nothing sent".format(self.voltage, MAX_VOLTAGE_SETPOINT))

        if self.output in ("On", "Set"):
            # take the setpoints over Ethernet (refused while the output is on under the front knobs),
            # and set them before switching on, so the output never comes on at an old setpoint
            self.sm18220.set_remote()
            self.sm18220.set_voltage(self.voltage)
            self.sm18220.set_current(self.current)
        if self.output == "On":
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

        # with the output on (after On, or Set while on) the current must follow the setpoint; after Off it must be 0
        if self.output == "Off":
            expected = 0.0
        elif self.output in ("On", "Set") and status["output"]:
            expected = self.current
        else:
            expected = None
        if expected is not None and abs(status["current"] - expected) > CURRENT_READBACK_TOLERANCE:
            raise RuntimeError("SM18-220 reads {:.3f} A after {}, expected {:.3f} A: check the coil wiring, and "
                               "that the voltage limit is high enough for this current".format(
                                   status["current"], self.output, expected))
