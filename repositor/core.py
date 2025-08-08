from artiq.experiment import *
from artiq.coredevice.core import Core

# import torch

class TestCore(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core:Core

    # @host_only
    def run(self):
        self.core.reset()

        print("Core tested successfully")

        # print(torch.__version__)
        # print(torch.tensor([1, 2, 3]))
        # print(torch.cuda.is_available())