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
        # self.set_dataset("test.samples1", [0.0], broadcast=True, archive=True)
        # self.set_dataset("test.noise", [0.0], broadcast=True, archive=True)

        self.ccb.issue("create_applet", 
                        "Sampler0", 
                        "${artiq_applet}plot_xy"
                        " test.samples0"
                        " --title sampler0",
                        group = "test"
                    )
        
        # self.ccb.issue("create_applet", 
        #                 "Sampler1", 
        #                 "${artiq_applet}plot_xy"
        #                 " test.samples1"
        #                 " --title sampler1",
        #                 group = "test"
        #             )
        
        # self.ccb.issue("create_applet", 
        #                 "Noise", 
        #                 "${artiq_applet}plot_xy"
        #                 " test.noise"
        #                 " --title noise",
        #                 group = "test"
        #             )

        sampling_period = 1/self.sample_rate
        data = [0.0] * 8
        delay_in_mu = self.core.seconds_to_mu(sampling_period * s)

        for i in range(int(self.total_samples)):
            # t1 = self.core.get_rtio_counter_mu()
            self.sampler.sample(data)
            
            with parallel:
                delay_mu(delay_in_mu)
                self.append_to_dataset("test.samples0", data[0])
                # self.append_to_dataset("test.samples1", data[7])
                # self.append_to_dataset("test.noise", data[1])
            
            # t2 = self.core.get_rtio_counter_mu()
            # elapsed_time = self.core.mu_to_seconds(t2-t1)
            # print(elapsed_time)
            