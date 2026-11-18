from artiq.experiment import *


class MOT_Coil_Control(EnvExperiment):
    def build(self):
        self.setattr_device("hmp4040")

        # the target is a dropdown: quickstyle buttons submit on click, so choose it before pressing an action
        self.setattr_argument("target", EnumerationValue(["All channels", "Ch1", "Ch2", "Ch3", "Ch4"], default="All channels"),
                              tooltip="Choose this first, then press an action button.")
        # quickstyle: shown as buttons that submit the experiment immediately when clicked
        self.setattr_argument("action", EnumerationValue(["Status", "On", "Off"], default="Status", quickstyle=True))

    def run(self):
        if self.action != "Status":
            enable = self.action == "On"
            if self.target == "All channels":
                state = self.hmp4040.set_output(enable)
                print("Master output -> %s" % ("ON" if state else "OFF"))
            else:
                channel = int(self.target[2:])
                state = self.hmp4040.set_channel_output(channel, enable)
                print("Ch%d output -> %s" % (channel, "ON" if state else "OFF"))

        status = self.hmp4040.get_status()
        print("Master output: %s" % ("ON" if status["master"] else "OFF"))
        for ch in sorted(status["channels"]):
            info = status["channels"][ch]
            print("Ch%s: %-3s | set %6.3f V / %6.4f A | meas %6.3f V / %6.4f A | OVP %.2f V" % (
                ch, "ON" if info["active"] else "OFF",
                info["voltage_set"], info["current_set"],
                info["voltage"], info["current"], info["ovp"]))
            self.set_dataset("hmp4040.ch%s.voltage" % ch, info["voltage"], broadcast=True)
            self.set_dataset("hmp4040.ch%s.current" % ch, info["current"], broadcast=True)
            self.set_dataset("hmp4040.ch%s.on" % ch, info["active"], broadcast=True)
