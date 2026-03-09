from artiq.experiment import *


class Testbed689_Monitor(EnvExperiment):

    def build(self):
        self.setattr_device("testbed689")

    def run(self):
        info = self.testbed689.get_laser_info()
        print("System: %s | S/N: %s | FW: %s" % (info["product_name"], info["serial_number"], info["firmware_version"]))
        print("Uptime: %s" % info["uptime"])
        print("")
        print("Emission:      %s" % self.testbed689.get_emission())
        print("Current set:   %.2f mA" % self.testbed689.get_current_setpoint())
        print("Current act:   %.2f mA" % self.testbed689.get_current())
        print("Temp set:      %.4f C" % self.testbed689.get_temperature_setpoint())
        print("Temp act:      %.4f C" % self.testbed689.get_temperature())
        print("Piezo voltage: %.3f V" % self.testbed689.get_piezo_voltage())
        # result = self.testbed689.set_emission(True)
        # print("set_emission(True) returned: %s" % result)
        # print("Emission now: %s" % self.testbed689.get_emission())
