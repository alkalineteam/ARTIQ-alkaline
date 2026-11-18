from numpy import int32

from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.zotino import Zotino


@compile
class BMOT_detection(EnvExperiment):
    core: KernelInvariant[Core]

    #TTLs
    BMOT_Shutter: KernelInvariant[TTLOut]
    RMOT_Shutter: KernelInvariant[TTLOut]
    ZS_Shutter: KernelInvariant[TTLOut]
    Probe_Shutter: KernelInvariant[TTLOut]
    Clock_shutter: KernelInvariant[TTLOut]
    Repump_shutter: KernelInvariant[TTLOut]
    Camera: KernelInvariant[TTLOut]

    #AD9912 (urukul1)
    BMOT_AOM: KernelInvariant[AD9912]
    ZS_AOM: KernelInvariant[AD9912]
    Probe_AOM: KernelInvariant[AD9912]

    #DAC
    zotino: KernelInvariant[Zotino]

    #Variables
    loading_time: KernelInvariant[float]
    tof: KernelInvariant[float]
    cycles: KernelInvariant[int32]
    detection_time: KernelInvariant[float]


    def build(self):
        self.setattr_device("core")

        #TTLs
        self.BMOT_Shutter = self.get_device("ttl4")
        self.RMOT_Shutter = self.get_device("ttl5")
        self.ZS_Shutter = self.get_device("ttl6")
        self.Probe_Shutter = self.get_device("ttl7")
        self.Clock_shutter = self.get_device("ttl8")
        self.Repump_shutter = self.get_device("ttl9")
        self.Camera = self.get_device("ttl10")

        #AD9912 (urukul1)
        self.BMOT_AOM = self.get_device("urukul1_ch0")
        self.ZS_AOM = self.get_device("urukul1_ch1")
        self.Probe_AOM = self.get_device("urukul1_ch2")

        #DAC
        self.zotino = self.get_device("zotino0")

        self.setattr_argument("cycles", NumberValue(default = 500, unit = "", min = 1, step = 1, precision = 0, type = "int"))
        self.setattr_argument("loading_time", NumberValue(default = 1000.0, unit = "ms", min = 0.0, precision = 1))
        self.setattr_argument("tof", NumberValue(default = 0.0, unit = "ms", min = 0.0, precision = 3),
                              tooltip = "Time of flight: from MOT off to the start of the detection pulse")
        self.setattr_argument("detection_time", NumberValue(default = 5.0, unit = "ms", min = 0.0, precision = 3),
                              tooltip = "Probe pulse and camera trigger length")
        

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

        self.BMOT_AOM.sw.unwrap().on()
        self.ZS_AOM.sw.unwrap().on()
        self.Probe_AOM.sw.unwrap().off()

        self.BMOT_AOM.set(frequency=90.0*MHz)
        self.BMOT_AOM.set_att(21.0)
        self.ZS_AOM.set(frequency=70.0*MHz)
        self.ZS_AOM.set_att(18.3)
        self.Probe_AOM.set(frequency=205.0*MHz)
        self.Probe_AOM.set_att(1.5)

        self.core.delay(10.*us)

        for i in range(self.cycles):

            #*************** Loading ***************
            self.zotino.write_dac(0, 8.5)
            self.zotino.write_dac(1, 8.35)

            with legacy_parallel:
                self.BMOT_Shutter.on()
                self.ZS_Shutter.on()
                self.Repump_shutter.on()
                self.zotino.load()
                self.Probe_Shutter.off()

            self.core.delay(self.loading_time * ms)

            #*************** Holding ***************

            with legacy_parallel:
                self.BMOT_Shutter.off()
                self.ZS_Shutter.off()
                self.Probe_Shutter.on()

            self.core.delay(2.*ms)

            #*************** Detection ***************

            self.zotino.write_dac(0, 5.0)
            self.zotino.write_dac(1, 5.0)
            self.zotino.load()

            self.core.delay(self.tof * ms)

            with legacy_parallel:
                self.Probe_AOM.sw.unwrap().pulse(self.detection_time * ms)
                self.Camera.pulse(self.detection_time * ms)
            self.Probe_Shutter.off()

            self.core.delay(500.*ms)

        print_rpc("BMOT detection done")