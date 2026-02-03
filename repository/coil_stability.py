from artiq.experiment import *

class CoilStability(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ccb")
        self.sampler = self.get_device("sampler0")
        self.setattr_argument("sample_rate", NumberValue(default=1))
        self.setattr_argument("total_samples", NumberValue(default=86400))

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()
        self.sampler.init()
        delay(100*ms)

        self.set_dataset("test.samples0", [0.0], broadcast=True, archive=True)
        self.set_dataset("test.samples1", [0.0], broadcast=True, archive=True)
        
        self.ccb.issue("create_applet", "Sampler0", "${artiq_applet}plot_xy", " test.samples0", " --title samler0", group="test")
        self.ccb.issue("create_applet", "Sampler1", "${artiq_applet}plot_xy", " test.samples1", " --title samler1", group="test")

        sampling_period = 1/self.sample_rate
        data = [0.0] * 8 

        for i in range(int(self.total_samples)):
            self.core.break_realtime()
            self.sampler.sample(data)
            self.append_to_dataset("test.samples0", data[0])
            self.append_to_dataset("test.samples1", data[7])
            
            print("Iteration:", i)

            delay(sampling_period * s)       