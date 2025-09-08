from artiq.experiment import EnvExperiment, host_only
from ndscan.experiment import Fragment

class TestCore(EnvExperiment):
	def build(self):
		self.setattr_device("core")

	@host_only
	def run(self):
		try:
			import torch
		except RuntimeError as e:
			print("Initial torch import failed (likely double import docstring issue):", e)
			import sys
			sys.modules.pop("torch", None)
			import torch

		print("Hello testbed setup")

		t1 = torch.randn(2, 2)
		t2 = torch.randn(2, 2)

		if hasattr(torch, "compile"):
			@torch.compile 
			def opt_foo2(x, y):
				a = torch.sin(x)
				b = torch.cos(y)
				return a + b
			print(opt_foo2(t1, t2))
		else:
			print("torch.compile unavailable; running uncompiled path")
			print(torch.sin(t1) + torch.cos(t2))