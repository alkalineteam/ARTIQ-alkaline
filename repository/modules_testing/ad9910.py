from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.coredevice.ad9910 import AD9910


@compile
class AD9910Test(EnvExperiment):
    core: KernelInvariant[Core]
    dds: KernelInvariant[AD9910[Auto]]
    Enable_RF: KernelInvariant[bool]
    Frequency: KernelInvariant[float]
    Amplitude: KernelInvariant[float]

    def build(self):
        self.setattr_device("core")
        channels = [name for name, desc in self.get_device_db().items()
                    if isinstance(desc, dict) and desc.get("class") == "AD9910"]
        self.setattr_argument("channel", EnumerationValue(channels, "urukul0_ch0"))
        self.setattr_argument("Enable_RF", BooleanValue(default=False))
        self.setattr_argument("Frequency", NumberValue(default=90*MHz, unit="MHz", min=0., max=400*MHz))
        self.setattr_argument("Amplitude", NumberValue(default=0.0, min=0., max=1.0))
        self.dds = self.get_device(self.channel)

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        self.dds.cpld.init()
        self.dds.init()

        self.core.break_realtime()

        self.dds.set_att(0.0)    # 0 to 31.5 dB
        self.dds.set(frequency=self.Frequency, amplitude=self.Amplitude)  # 0 to 1.0

        if self.Enable_RF:
            self.dds.sw.unwrap().on()
        else:
            self.dds.sw.unwrap().off()

        # for i in range(10):
        #     self.dds.sw.unwrap().on()
        #     self.core.delay(1000.*ms)
        #     self.dds.sw.unwrap().off()
        #     self.core.delay(1000.*ms)

        # for i in range(10):
        #     self.dds.set(frequency=39.*MHz, amplitude=1.0)
        #     self.core.delay(1000.*ms)
        #     self.dds.set(frequency=41.*MHz, amplitude=1.0)
        #     self.core.delay(1000.*ms)


        self.core.wait_until_mu(now_mu())
        print_rpc("AD9910 test is done!")
