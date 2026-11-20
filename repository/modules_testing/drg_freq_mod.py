from artiq.experiment import *
from artiq.coredevice.core import Core
from artiq.coredevice.ad9910 import RAM_MODE_CONT_RAMPUP, RAM_DEST_FTW
from numpy import int32, sin, pi, arange


class DRG_FreqMod(EnvExperiment):
    """AD9910 RAM-mode sinusoidal frequency modulation."""

    def build(self):
        self.setattr_device("core")
        self.core: Core
        self.dds = self.get_device("urukul0_ch0")

        self.setattr_argument("Enable_RF",   BooleanValue(default=True))
        self.setattr_argument("Freq_Low",    NumberValue(default=350.0, unit="MHz"))
        self.setattr_argument("Freq_High",   NumberValue(default=351.0, unit="MHz"))
        self.setattr_argument("Mod_Freq",    NumberValue(default=25.0,  unit="kHz"))
        self.setattr_argument("Attenuation", NumberValue(default=0.0,  unit="dB"))

    def prepare(self):
        # NumberValue with unit="MHz"/"kHz" auto-scales → values are already in Hz
        f_center = (self.Freq_Low + self.Freq_High) / 2.0
        f_dev    = (self.Freq_High - self.Freq_Low) / 2.0

        # SYNC_CLK = SYSCLK/4 → one period = N * step * (4/SYSCLK)
        # N * step = SYSCLK / (4 * Mod_Freq)
        total_clk = int(round(self.dds.sysclk / (4.0 * self.Mod_Freq)))

        # Up to 1000 samples (≤1024 RAM limit); step covers the rest
        self.n_samples = min(1000, total_clk)
        self.ram_step  = max(1, total_clk // self.n_samples)

        # Sine-shaped FTW table: one full period
        phases = 2.0 * pi * arange(self.n_samples) / self.n_samples
        self.ftw_table = [
            int32(self.dds.frequency_to_ftw(f_center + f_dev * sin(p)))
            for p in phases
        ]

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        self.dds.cpld.init()
        self.dds.init()
        self.dds.set_att(self.Attenuation)

        # Disable RAM mode while setting up
        self.dds.set_cfr1(ram_enable=0)
        self.dds.io_update.pulse(1 * us)

        # Configure RAM profile 0: start=0, end=n_samples-1, continuous loop
        self.dds.set_profile_ram(
            start=0,
            end=self.n_samples - 1,
            step=self.ram_step,
            profile=0,
            mode=RAM_MODE_CONT_RAMPUP,
        )

        # Select profile 0 on the CPLD (chip_select 4 → channel 0)
        self.dds.cpld.set_profile(self.dds.chip_select - 4, 0)
        self.dds.io_update.pulse(1 * us)

        # Write sine FTW table into RAM
        self.dds.write_ram(self.ftw_table)

        # set_profile_ram writes step/end data into the profile register's bits [63:48],
        # which the chip also interprets as the ASF (amplitude) field → output is silent.
        # Fix: write the standalone ASF register and tell CFR2 to use it instead.
        self.dds.set_asf(0x3FFF)                 # full amplitude
        self.dds.set_cfr2(asf_profile_enable=0)  # amplitude from ASF register, not profile
        self.dds.set_cfr1(ram_enable=1, ram_destination=RAM_DEST_FTW)
        self.dds.io_update.pulse(1 * us)

        if self.Enable_RF:
            self.dds.sw.on()
        else:
            self.dds.sw.off()

        print("Sine FM active")
