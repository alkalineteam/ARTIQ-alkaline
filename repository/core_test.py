import torch
from artiq.experiment import EnvExperiment, host_only
from ndscan.experiment import Fragment
from numpy import int64, int64

class TestCore(EnvExperiment):
	def build(self):
		self.setattr_device("core")

	@host_only
	def run(self):
		print("Hello testbed setup")

		t1 = torch.randn(2, 2)
		t2 = torch.randn(2, 2)

		@torch.compile
		def opt_foo2(x, y):
			a = torch.sin(x)
			b = torch.cos(y)
			return a + b
		print(opt_foo2(t1, t2))