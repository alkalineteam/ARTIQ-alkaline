from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from numpy import int64

class RF_on(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core:Core

        self.BMOT=self.get_device("urukul1_ch0")
        self.ZeemanSlower=self.get_device("urukul1_ch1")
        self.Probe=self.get_device("urukul1_ch3")
        self.Ref = self.get_device("urukul0_ch3")

        self.setattr_argument("RF_on", BooleanValue(default=False))


        self.setattr_argument("BMOT_Frequency", NumberValue(default = 80.0))
        self.setattr_argument("BMOT_Amplitude", NumberValue(default = 0.01))
        # self.setattr_argument("BMOT_Attenuation", NumberValue(default = 0.0))

        self.setattr_argument("Zeeman_Frequency", NumberValue(default = 190.0))
        self.setattr_argument("Zeeman_Amplitude", NumberValue(default = 0.01)) 
        # self.setattr_argument("Zeeman_Attenuation", NumberValue(default = 0.0))


        self.setattr_argument("Probe_Frequency", NumberValue(default = 110.0))
        self.setattr_argument("Probe_Amplitude", NumberValue(default = 0.01)) 
        # self.setattr_argument("Probe_Attenuation", NumberValue(default = 0.0))
    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        self.BMOT.cpld.init()
        self.BMOT.init()

        self.ZeemanSlower.cpld.init()
        self.ZeemanSlower.init()

        self.Probe.cpld.init()
        self.Probe.init()

        self.BMOT.sw.on()
        self.ZeemanSlower.sw.on()
        self.Probe.sw.on()

        self.BMOT.set_att(0.0)
        self.ZeemanSlower.set_att(0.0)
        self.Probe.set_att(0.0)

        self.Ref.set(frequency=10 * MHz)

        delay(1000*ms)

        if self.RF_on == True:
            self.BMOT.set(frequency= self.BMOT_Frequency * MHz, amplitude=self.BMOT_Amplitude)

            self.ZeemanSlower.set(frequency=self.Zeeman_Frequency * MHz, amplitude=self.Zeeman_Amplitude)

            self.Probe.set(frequency=self.Probe_Frequency * MHz, amplitude=self.Probe_Amplitude)
        print("weeewaaaweeewaaa")
