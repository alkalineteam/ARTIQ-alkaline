from artiq.experiment import *


class BMOT461_Monitor(EnvExperiment):

    def build(self):
        self.setattr_device("bmot461")

    def run(self):
        info = self.bmot461.get_laser_info()
        print("System: %s | S/N: %s | FW: %s" % (info["product_name"], info["serial_number"], info["firmware_version"]))
        print("Uptime: %s" % info["uptime"])
        print("")
        print("Emission:      %s" % self.bmot461.get_emission())
        print("Current set:   %.2f mA" % self.bmot461.get_current_setpoint())
        print("Current act:   %.2f mA" % self.bmot461.get_current())
        print("Temp set:      %.4f C" % self.bmot461.get_temperature_setpoint())
        print("Temp act:      %.4f C" % self.bmot461.get_temperature())
        print("Piezo voltage: %.3f V" % self.bmot461.get_piezo_voltage())
        result = self.bmot461.set_emission(True)
        print("set_emission(True) returned: %s" % result)
        print("Emission now: %s" % self.bmot461.get_emission())
