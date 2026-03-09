from artiq.experiment import *


class Toptica698_Monitor(EnvExperiment):

    def build(self):
        self.setattr_device("toptica698")

    def run(self):
        info = self.toptica698.get_laser_info()
        print("System: %s | S/N: %s | FW: %s" % (info["product_name"], info["serial_number"], info["firmware_version"]))
        print("Uptime: %s" % info["uptime"])
        print("")
        print("Emission:      %s" % self.toptica698.get_emission())
        print("Current set:   %.2f mA" % self.toptica698.get_current_setpoint())
        print("Current act:   %.2f mA" % self.toptica698.get_current())
        print("Temp set:      %.4f C" % self.toptica698.get_temperature_setpoint())
        print("Temp act:      %.4f C" % self.toptica698.get_temperature())
        print("Piezo voltage: %.3f V" % self.toptica698.get_piezo_voltage())
        result = self.toptica698.set_emission(True)
        print("set_emission(True) returned: %s" % result)
        print("Emission now: %s" % self.toptica698.get_emission())
