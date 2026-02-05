from artiq.experiment import *
from datetime import datetime
import sys
import os

# Add scripts directory to path for MetricLogger import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.Grafana.metric_logger import MetricLogger


class CoilStability(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ccb")
        self.sampler = self.get_device("sampler0")
        self.setattr_argument("sample_rate", NumberValue(default=1))
        self.setattr_argument("total_samples", NumberValue(default=86400))
        self.setattr_argument("log_to_grafana", BooleanValue(default=True))
        
        # Generate run_id for this experiment run
        self.run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.logger = None

    def prepare(self):
        """Initialize Grafana logger before kernel execution."""
        if self.log_to_grafana:
            self.logger = MetricLogger()
            self.logger.__enter__()
            print(f"Grafana logging enabled with run_id: {self.run_id}")

    @rpc(flags={"async"})
    def log_sample(self, value):
        """RPC call to log sample to InfluxDB (non-blocking)."""
        if self.logger:
            self.logger.log_scalar(
                "coil_samples",
                value,
                tags={"run_id": self.run_id, "channel": "0"}
            )

    def analyze(self):
        """Cleanup after kernel execution."""
        if self.logger:
            self.logger.__exit__(None, None, None)
            print(f"Grafana logging complete for run_id: {self.run_id}")

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
                self.log_sample(data[0])  # Log to Grafana
                # self.append_to_dataset("test.samples1", data[7])
                # self.append_to_dataset("test.noise", data[1])
            
            # t2 = self.core.get_rtio_counter_mu()
            # elapsed_time = self.core.mu_to_seconds(t2-t1)
            # print(elapsed_time)
            