from artiq.experiment import *
from artiq.coredevice.core import Core

class TestCore(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core:Core

    @host_only
    def run(self):
        self.core.reset()

        print("Core tested successfully")