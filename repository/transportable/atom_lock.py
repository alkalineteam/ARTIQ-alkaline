from artiq.coredevice.core import Core
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.urukul import CPLD
from artiq.coredevice.zotino import Zotino
from artiq.coredevice.ttl import TTLOut
from artiq.coredevice.sampler import Sampler
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue
from artiq.experiment import legacy_parallel, sequential
from artiq.experiment import rpc
from artiq.experiment import compile, Kernel, KernelInvariant, Auto
from artiq.language.units import ms, MHz
from numpy import int32
import numpy as np

@compile
class atom_lock(EnvExperiment):
    core: KernelInvariant[Core]
    Camera: KernelInvariant[TTLOut]
    Pixelfly: KernelInvariant[TTLOut]
    BMOT_TTL: KernelInvariant[TTLOut]
    Probe_TTL: KernelInvariant[TTLOut]
    Broadband_On: KernelInvariant[TTLOut]
    Broadband_Off: KernelInvariant[TTLOut]
    Zeeman_Slower_TTL: KernelInvariant[TTLOut]
    clock_shutter: KernelInvariant[TTLOut]
    Repump679: KernelInvariant[TTLOut]
    BMOT_AOM: KernelInvariant[AD9910[Auto]]
    ZeemanSlower: KernelInvariant[AD9910[Auto]]
    Single_Freq: KernelInvariant[AD9910[Auto]]
    Probe: KernelInvariant[AD9910[Auto]]
    Clock: KernelInvariant[AD9912]
    Clock_Feedback: KernelInvariant[AD9912]
    MOT_Coil_1: KernelInvariant[Zotino]
    MOT_Coil_2: KernelInvariant[Zotino]
    sampler: KernelInvariant[Sampler]
    Ref: KernelInvariant[AD9912]

    Loading_Time: KernelInvariant[float]
    Transfer_Time: KernelInvariant[float]
    Holding_Time: KernelInvariant[float]
    Compression_Time: KernelInvariant[float]
    Single_Freq_Time: KernelInvariant[float]
    State_Preparation_Time: KernelInvariant[float]
    Clock_Interrogation_Time: KernelInvariant[float]
    Center_Frequency: KernelInvariant[float]
    linewidth: KernelInvariant[float]

    n: KernelInvariant[int32]
    high_side: Kernel[float]
    low_side: Kernel[float]
    thue_morse: KernelInvariant[list[int32]]
    sample_duration: KernelInvariant[float]
    sampling_period: KernelInvariant[float]
    num_samples: KernelInvariant[int32]
    samples: Kernel[list[list[float]]]
    excitation_fraction_list: Kernel[list[float]]
    error_signal_list: Kernel[list[float]]
    feedback_frequency_list: Kernel[list[float]]

    def build(self):
        self.core = self.get_device("core")
        self.setattr_device("ccb")
        self.cpld: CPLD = self.get_device("urukul0_cpld")
        self.Camera=self.get_device("ttl10")
        self.Pixelfly=self.get_device("ttl15")
        self.BMOT_TTL=self.get_device("ttl6")
        self.Probe_TTL=self.get_device("ttl8")
        self.Broadband_On=self.get_device("ttl5")
        self.Broadband_Off=self.get_device("ttl7")
        self.Zeeman_Slower_TTL=self.get_device("ttl12")
        self.clock_shutter=self.get_device("ttl4")
        self.Repump679=self.get_device("ttl9")
        self.BMOT_AOM = self.get_device("urukul1_ch0")
        self.ZeemanSlower = self.get_device("urukul1_ch1")
        self.Single_Freq = self.get_device("urukul1_ch2")
        self.Probe = self.get_device("urukul1_ch3")
        self.Clock = self.get_device("urukul0_ch0")
        self.Clock_Feedback = self.get_device("urukul0_ch1")
        self.MOT_Coil_1 = self.get_device("zotino0")
        self.MOT_Coil_2 = self.get_device("zotino0")
        self.sampler = self.get_device("sampler0")
        self.Ref = self.get_device("urukul0_ch3")

        self.setattr_argument("Loading_Time", NumberValue(default=1500))
        self.setattr_argument("Transfer_Time", NumberValue(default=80))
        self.setattr_argument("Holding_Time", NumberValue(default=80))
        self.setattr_argument("Compression_Time", NumberValue(default=8))
        self.setattr_argument("Single_Freq_Time", NumberValue(default=80))
        self.setattr_argument("State_Preparation_Time", NumberValue(default=30))
        self.setattr_argument("Clock_Interrogation_Time", NumberValue(default=300))

        self.setattr_argument("Center_Frequency", NumberValue(default=79.42, precision=4, unit="MHz"))
        self.setattr_argument("linewidth", NumberValue(default=100, precision=4, unit="Hz"))

    def prepare(self):
        self.n = 10000
        self.high_side = 0.0
        self.low_side = 0.0

        # Generate Thue-Morse sequence
        self.thue_morse = [0]
        while len(self.thue_morse) < self.n:
            self.thue_morse += [1 - bit for bit in self.thue_morse]
        self.thue_morse = self.thue_morse[:self.n]

        # Sampler params
        self.sample_duration = 70.  # 60 ms detection window
        self.sampling_period = 0.04  # in ms = 25 kHz
        self.num_samples = int(self.sample_duration / self.sampling_period)

        # Pre-allocate arrays
        self.samples = [[0.0 for i in range(8)] for _ in range(self.num_samples)]
        self.excitation_fraction_list = [0.0 for _ in range(self.n)]
        self.error_signal_list = [0.0 for _ in range(self.n)]
        self.feedback_frequency_list = [0.0 for _ in range(self.n)]

    @rpc
    def save_dataset(self, key: str, values: list[float]):
        self.set_dataset(key, values, broadcast=True, archive=True)

    @rpc
    def create_applet(self, name: str, command: str, group: str):
        self.ccb.issue("create_applet", name, command, group=group)

    @rpc(flags={"async"})
    def log_value(self, label: str, value: float):
        print(label, value)

    @rpc(flags={"async"})
    def log_averages(self, gs_avg: float, es_avg: float, bg_avg: float):
        print("GS avg:", gs_avg, ", ES avg:", es_avg, ", BG avg:", bg_avg)

    @rpc(flags={"async"})
    def log_excitation(self, excitation_fraction: float, j: int32):
        print("Excitation Fraction:", excitation_fraction, ", Cycle:", j)

    @kernel
    def rabi_clock_spectroscopy(self, frequency: float):
        self.clock_shutter.on()
        self.core.delay(4.*ms)

        self.Clock.set(frequency=frequency*MHz)
        self.log_value("Clock Frequency (MHz):", frequency)

        self.core.delay(self.Clock_Interrogation_Time*ms)

        self.clock_shutter.off()
        self.core.delay(4.*ms)

    @kernel
    def probe_init(self, camera: bool):
        self.Probe.set(frequency=65.*MHz, amplitude=0.02)
        self.core.delay(5.*ms)
        self.Probe.set(frequency=65.*MHz, amplitude=0.00)
        self.Probe_TTL.on()
        self.core.delay(3.0*ms)

        if camera:
            with legacy_parallel:
                self.Camera.on()
                self.Probe.set(frequency=65.*MHz, amplitude=0.02)
        else:
            self.Probe.set(frequency=65.*MHz, amplitude=0.02)

        self.core.delay(0.5*ms)

        if camera:
            with legacy_parallel:
                self.Camera.off()
                self.Probe.set(frequency=65.*MHz, amplitude=0.00)
                self.Probe_TTL.off()
        else:
            with legacy_parallel:
                self.Probe.set(frequency=65.*MHz, amplitude=0.00)
                self.Probe_TTL.off()

    @kernel
    def detection(self, j: int32) -> float:
        self.MOT_Coil_1.write_dac(0, 4.08)
        self.MOT_Coil_2.write_dac(1, 4.11)
        with legacy_parallel:
            self.MOT_Coil_1.load()
            self.MOT_Coil_2.load()

        self.BMOT_AOM.set(frequency=10.*MHz, amplitude=0.08)

        with legacy_parallel:
            with sequential:
                # **************************** Ground State **************************
                self.probe_init(camera=True)
                self.core.delay(5.*ms)

                # ***************************** Repumping ****************************
                self.Repump679.pulse(30.*ms)

                # *************************** Excited State **************************
                self.probe_init(camera=False)
                self.core.delay(20.*ms)

                # ************************* Background State *************************
                self.probe_init(camera=False)
                self.core.delay(5.*ms)

            with sequential:
                for k in range(self.num_samples):
                    self.sampler.sample(self.samples[k])
                    self.core.delay(self.sampling_period * ms)

        self.Probe.set(frequency=65.*MHz, amplitude=0.02)
        self.BMOT_AOM.set(frequency=90.*MHz, amplitude=0.08)
        self.Single_Freq.set(frequency=80.*MHz, amplitude=0.35)
        self.Broadband_On.pulse(10.*ms)
        self.core.delay(100.*ms)

        detection = [i[0] for i in self.samples]

        self.save_dataset("excitation.detection", detection)
        self.create_applet(
                    "PMT Detection",
                    "${artiq_applet}plot_xy excitation.detection --title PMT_detection",
                    "excitation"
                )
        ground_state = detection[164:175]
        excited_state = detection[1053:1064]
        background = detection[1634:1645]

        gs_sum = 0.0
        for _ in ground_state:
            gs_sum+=_

        es_sum = 0.0
        for _ in excited_state:
            es_sum+=_

        bg_sum = 0.0
        for _ in background:
            bg_sum+=_

        gs_avg = gs_sum/float(len(ground_state))
        es_avg = es_sum/float(len(excited_state))
        bg_avg = bg_sum/float(len(background))
        self.log_averages(gs_avg, es_avg, bg_avg)

        numerator = es_avg - bg_avg
        denominator = es_avg + gs_avg - 2.*bg_avg

        # excitation_fraction = min(max(numerator / denominator if denominator != 0.0 else 0.0, 0.0), 1.0)
        excitation_fraction = numerator / denominator
        self.log_excitation(excitation_fraction, j)

        self.excitation_fraction_list[j] = excitation_fraction

        self.save_dataset("excitation.excitation_fraction_list", self.excitation_fraction_list)
        # self.save_dataset("excitation.frequencies_MHz", frequencies_MHz)

        self.create_applet(
                    "Excitation Fraction Plot",
                    # " --x excitation.frequencies_MHz"
                    "${artiq_applet}plot_xy excitation.excitation_fraction_list --title Excitation_Fraction",
                    "excitation"
                )
        return excitation_fraction


    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()

        # Initialize the modules
        self.Pixelfly.output()
        self.Camera.output()
        self.BMOT_TTL.output()
        self.Probe_TTL.output()
        self.Zeeman_Slower_TTL.output()
        self.clock_shutter.output()
        self.MOT_Coil_1.init()
        self.MOT_Coil_2.init()
        self.sampler.init()
        self.BMOT_AOM.cpld.init()
        self.BMOT_AOM.init()
        self.ZeemanSlower.cpld.init()
        self.ZeemanSlower.init()
        self.Probe.cpld.init()
        self.Probe.init()
        self.Single_Freq.cpld.init()
        self.Single_Freq.init()
        self.Clock.cpld.init()
        self.Clock.init()
        self.Clock_Feedback.cpld.init()
        self.Clock_Feedback.init()

        self.Ref.cpld.init()
        self.Ref.init()

        # Set the RF channels ON
        self.BMOT_AOM.sw.unwrap().on()
        self.ZeemanSlower.sw.unwrap().on()
        self.Probe.sw.unwrap().on()
        self.Clock.sw.unwrap().on()
        self.Clock_Feedback.sw.unwrap().on()

        # Set the RF attenuation
        self.BMOT_AOM.set_att(0.0)
        self.ZeemanSlower.set_att(0.0)
        self.Probe.set_att(0.0)
        self.Single_Freq.set_att(0.0)
        self.Clock.set_att(0.0)
        self.Clock_Feedback.set_att(0.0)

        Clock_Feedback_Freq = 66.*MHz
        self.Clock_Feedback.set(frequency=Clock_Feedback_Freq)
        self.Clock_Feedback.set_att(0.0)
        self.Ref.set(frequency=80. * MHz)
        self.Ref.set_att(0.0)

        for j in range(self.n):
            # **************************** Slice 1: Loading ****************************
            self.core.delay(100.*ms)
            self.BMOT_AOM.set(frequency=90. * MHz, amplitude=0.08)
            self.ZeemanSlower.set(frequency=180. * MHz, amplitude=0.35)
            self.Probe.set(frequency= 65. * MHz, amplitude=0.02)
            self.Single_Freq.set(frequency= 80. * MHz, amplitude=0.35)

            voltage_1 = 1.045
            voltage_2 = 0.547
            self.MOT_Coil_1.write_dac(0, voltage_1)
            self.MOT_Coil_2.write_dac(1, voltage_2)

            with legacy_parallel:
                self.MOT_Coil_1.load()
                self.MOT_Coil_2.load()
                self.BMOT_TTL.on()
                self.Probe_TTL.off()
                self.Broadband_On.pulse(10.*ms)
                self.Single_Freq.sw.unwrap().off()
                self.Zeeman_Slower_TTL.on()
                self.clock_shutter.off()
                self.Repump679.on()

            self.core.delay(self.Loading_Time*ms)

            # **************************** Slice 2: Transfer ****************************
            self.ZeemanSlower.set(frequency=180. * MHz, amplitude=0.00)
            self.Zeeman_Slower_TTL.off()
            self.core.delay(4.0*ms)

            steps_tr = self.Transfer_Time
            t_tr = self.Transfer_Time/steps_tr

            for i in range(int32(steps_tr)):
                amp_steps = (0.08 - 0.003)/steps_tr
                amp = 0.08 - (float(i+1) * amp_steps)
                self.BMOT_AOM.set(frequency=90.*MHz, amplitude=amp)
                self.core.delay(t_tr*ms)

            self.core.delay(200.*ms)

            with legacy_parallel:
                self.BMOT_TTL.off()
                self.Repump679.off()

            self.core.delay(4.*ms)
            self.BMOT_AOM.set(frequency=90.*MHz, amplitude=0.08)

            voltage_1_Tr = 4.012
            voltage_2_Tr = 4.027
            self.MOT_Coil_1.write_dac(0, voltage_1_Tr)
            self.MOT_Coil_2.write_dac(1, voltage_2_Tr)
            with legacy_parallel:
                self.MOT_Coil_1.load()
                self.MOT_Coil_2.load()

            # **************************** Slice 3: Holding ****************************
            self.core.delay(self.Holding_Time*ms)

            # **************************** Slice 4: Compression ****************************
            with legacy_parallel:
                self.Broadband_Off.pulse(10.*ms)
                self.Single_Freq.sw.unwrap().on()

            voltage_1_com = 2.585
            voltage_2_com = 2.286
            red_amp = 0.35
            amp_com = 0.03
            red_freq = 75.0
            red_freq_com = 75.3
            steps_com = self.Compression_Time
            t_com = self.Compression_Time/steps_com
            volt_1_steps = (voltage_1_Tr - voltage_1_com)/steps_com
            volt_2_steps = (voltage_2_Tr - voltage_2_com)/steps_com
            amp_steps = (red_amp-amp_com)/steps_com
            freq_steps = (red_freq_com - red_freq)/steps_com

            with legacy_parallel:
                for i in range(int32(steps_com)):
                    voltage_1 = voltage_1 - volt_1_steps
                    voltage_2 = voltage_2 - volt_2_steps
                    self.MOT_Coil_1.write_dac(0, voltage_1)
                    self.MOT_Coil_2.write_dac(1, voltage_2)
                    with legacy_parallel:
                        self.MOT_Coil_1.load()
                        self.MOT_Coil_2.load()
                    self.core.delay(t_com*ms)

                for i in range(int32(steps_com)):
                    amp = red_amp - (float(i+1) * amp_steps)
                    freq = red_freq + (float(i+1) * freq_steps)
                    self.Single_Freq.set(frequency=freq*MHz, amplitude=amp)
                    self.core.delay(t_com*ms)

            # **************************** Slice 5: Single Frequency ****************************
            self.Single_Freq.set(frequency=75.3*MHz, amplitude=amp_com)
            self.core.delay(self.Single_Freq_Time*ms)
            self.Single_Freq.sw.unwrap().off()

            # **************************** Slice 5: State Preparation *****************************
            self.MOT_Coil_1.write_dac(0, 7.04)# 4.7/3.32 = 0.8; 4.898/3.14 = 1; 5.07/2.93 = 1.2; 5.64/2.27 = 1.85; 7.176/0.439 = 3.5;
            self.MOT_Coil_2.write_dac(1, 0.565)
            with legacy_parallel:
                self.MOT_Coil_1.load()
                self.MOT_Coil_2.load()

            self.core.delay(self.State_Preparation_Time*ms)

            # **************************** Slice 6: Atom Lock ****************************
            if self.thue_morse[j] == 0:
                self.rabi_clock_spectroscopy(
                    frequency = self.Center_Frequency - (self.linewidth/2.)
                )
                self.low_side = self.detection(j)
                self.log_value("Low Side:", self.low_side)

                # self.atom_lock_ex(self.low_side)

            elif self.thue_morse[j] == 1:
                self.rabi_clock_spectroscopy(
                    frequency = self.Center_Frequency + (self.linewidth/2.)
                )
                self.high_side = self.detection(j)
                self.log_value("High Side:", self.high_side)

                # self.atom_lock_ex(self.high_side)

            if j % 2 == 0:              # Every other cycle generate correction
                error_signal = 0.0
                if self.high_side > 1.0 or self.low_side > 1.0:        #prevents bad excitation fraction from destabilising the lock
                    error_signal = 0.0
                elif self.high_side < 0.2 or self.low_side < 0.2:
                    error_signal = 0.0
                else:
                    error_signal = self.high_side - self.low_side

                self.error_signal_list[j] = error_signal

                frequency_correction = 0.0
                if error_signal == 0.0:
                    frequency_correction = 0.0
                #     # print("No correction made")
                # elif self.high_side+self.low_side <= 0.05:
                #     frequency_correction = 0.0
                #     # print("No correction made - too low")
                # elif self.high_side+self.low_side >= 1.0:
                #     frequency_correction = 0.0
                #     # print("No correction made - too high")
                else:
                    # frequency_correction =  - (self.servo_gain * error_signal * self.linewidth) / (2* (2 * contrast))
                    frequency_correction =  - (0.3 * error_signal * self.linewidth) / (2.*(2.*0.6))
                    # frequency_correction =  0.0

                # double_integrator_correction = self.servo_gain_2 * sum(self.previous_correction_values) *self.linewidth / (2 * (2 * contrast))

                Clock_Feedback_Freq -= frequency_correction
                self.feedback_frequency_list[j] = Clock_Feedback_Freq - 66.*MHz
                self.Clock_Feedback.set(frequency = Clock_Feedback_Freq)

                self.save_dataset("lock.error_signal_list", self.error_signal_list)
                self.create_applet(
                            "Error Signal",
                            "${artiq_applet}plot_xy lock.error_signal_list --title Error_Signal",
                            "lock"
                        )
                self.save_dataset("lock.feedback_frequency_list", self.feedback_frequency_list)
                self.create_applet(
                            "Feedback Frequency",
                            "${artiq_applet}plot_xy lock.feedback_frequency_list --title Feedback_Frequency",
                            "lock"
                        )

                self.core.delay(100.*ms)
