from numpy import int32

from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.zotino import Zotino


@compile
class continuous_mode(EnvExperiment):
    core: KernelInvariant[Core]

    #TTLs
    BMOT_Shutter: KernelInvariant[TTLOut]
    RMOT_Shutter: KernelInvariant[TTLOut]
    ZS_Shutter: KernelInvariant[TTLOut]
    Probe_Shutter: KernelInvariant[TTLOut]
    Clock_shutter: KernelInvariant[TTLOut]
    Repump_shutter: KernelInvariant[TTLOut]

    #AD9912 (urukul1)
    BMOT_AOM: KernelInvariant[AD9912]
    ZS_AOM: KernelInvariant[AD9912]
    Probe_AOM: KernelInvariant[AD9912]

    #DAC
    zotino: KernelInvariant[Zotino]

    #Variables
    BMOT_Frequency: KernelInvariant[float]
    BMOT_Attenuation: KernelInvariant[float]
    ZS_Frequency: KernelInvariant[float]
    ZS_Attenuation: KernelInvariant[float]
    Probe_Frequency: KernelInvariant[float]
    Probe_Attenuation: KernelInvariant[float]
    Coil1_Voltage: KernelInvariant[float]
    Coil2_Voltage: KernelInvariant[float]


    def build(self):
        self.setattr_device("core")

        #TTLs
        self.BMOT_Shutter = self.get_device("ttl4")
        self.RMOT_Shutter = self.get_device("ttl5")
        self.ZS_Shutter = self.get_device("ttl6")
        self.Probe_Shutter = self.get_device("ttl7")
        self.Clock_shutter = self.get_device("ttl8")
        self.Repump_shutter = self.get_device("ttl9")

        #AD9912 (urukul1)
        self.BMOT_AOM = self.get_device("urukul1_ch0")
        self.ZS_AOM = self.get_device("urukul1_ch1")
        self.Probe_AOM = self.get_device("urukul1_ch2")

        #DAC
        self.zotino = self.get_device("zotino0")

        # frequencies are entered in MHz but arrive here in Hz; Urukul attenuators span 0-31.5 dB
        self.setattr_argument("BMOT_Frequency", NumberValue(default = 90.0*MHz, unit = "MHz", min = 0.0))
        self.setattr_argument("BMOT_Attenuation", NumberValue(default = 21.0, unit = "dB", min = 0.0, max = 31.5))
        self.setattr_argument("ZS_Frequency", NumberValue(default = 70.0*MHz, unit = "MHz", min = 0.0))
        self.setattr_argument("ZS_Attenuation", NumberValue(default = 18.3, unit = "dB", min = 0.0, max = 31.5))
        self.setattr_argument("Probe_Frequency", NumberValue(default = 205.0*MHz, unit = "MHz", min = 0.0))
        self.setattr_argument("Probe_Attenuation", NumberValue(default = 1.5, unit = "dB", min = 0.0, max = 31.5))
        # Zotino range is -10 V to +10 V minus one LSB (~0.3 mV); exactly +10 V is rejected
        self.setattr_argument("Coil1_Voltage", NumberValue(default = 1.0, unit = "V", min = 0.0, max = 9.999, precision = 3))
        self.setattr_argument("Coil2_Voltage", NumberValue(default = 1.0, unit = "V", min = 0.0, max = 9.999, precision = 3))

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        # initialise the Urukul CPLD (all three AOMs share urukul1) and DDS chips
        self.BMOT_AOM.cpld.init()
        self.BMOT_AOM.init()
        self.ZS_AOM.init()
        self.Probe_AOM.init()
        self.zotino.init()
        self.core.break_realtime()


        # Switch on all DDS channels
        self.BMOT_AOM.sw.unwrap().on()
        self.ZS_AOM.sw.unwrap().on()
        self.Probe_AOM.sw.unwrap().on()

        self.BMOT_Shutter.on()
        self.ZS_Shutter.on()
        self.Probe_Shutter.on()
        self.Repump_shutter.on()

        # SPI writes on the same Urukul can't overlap, so these run sequentially
        self.BMOT_AOM.set(frequency=self.BMOT_Frequency)
        self.BMOT_AOM.set_att(self.BMOT_Attenuation)
        self.ZS_AOM.set(frequency=self.ZS_Frequency) 
        self.ZS_AOM.set_att(self.ZS_Attenuation)
        self.Probe_AOM.set(frequency=self.Probe_Frequency)
        self.Probe_AOM.set_att(self.Probe_Attenuation)

        # for i in range(500):
        #     self.BMOT_AOM.sw.unwrap().on()
        #     self.core.delay(1000.*ms)
        #     self.BMOT_AOM.sw.unwrap().off()
        #     self.core.delay(1000.*ms)

        # for i in range(500):
        #     self.ZS_AOM.sw.unwrap().on()
        #     self.core.delay(1000.*ms)
        #     self.ZS_AOM.sw.unwrap().off()
        #     self.core.delay(1000.*ms)

        # for i in range(500):
        #     self.Probe_AOM.sw.unwrap().on()
        #     self.core.delay(1000.*ms)
        #     self.Probe_AOM.sw.unwrap().off()
        #     self.core.delay(1000.*ms)

        self.zotino.write_dac(0, self.Coil1_Voltage)
        self.zotino.write_dac(1, self.Coil2_Voltage)
        self.zotino.load()

        # for i in range(500):
        #     self.zotino.write_dac(self.Zotino_Channel, self.Zotino_Voltage)
        #     self.zotino.load()
        #     self.core.delay(1000*ms)
        #     self.zotino.write_dac(self.Zotino_Channel, 0.0)
        #     self.zotino.load()
        #     self.core.delay(1000*ms)

        print_rpc("Parameters are set")