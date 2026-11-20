from artiq.experiment import *


class TestCore(EnvExperiment):
	def build(self):
		self.setattr_device("core")

	@kernel
	def run(self):
		print("BEC is ready, we will show it in December")
