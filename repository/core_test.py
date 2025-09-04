from artiq.experiment import EnvExperiment, host_only
from ndscan.experiment import Fragment

# NOTE:
# Importing torch at module top-level was triggering a RuntimeError in this
# environment ("function '_has_torch_function' already has a docstring") due to
# ARTIQ's import hook re-executing modules under Python 3.13 + current PyTorch.
# We defer the import to the host-only run() method so it happens only once in
# the actual host runtime context and not during the device analysis/import
# phase. Remove if/when underlying compatibility issue is resolved.

class TestCore(EnvExperiment):
	def build(self):
		self.setattr_device("core")

	@host_only
	def run(self):
		# Lazy import here to avoid double-import issues with ARTIQ import cache
		try:
			import torch  # type: ignore
		except RuntimeError as e:
			print("Initial torch import failed (likely double import docstring issue):", e)
			# Best effort retry after clearing possibly half-initialized module
			import sys
			sys.modules.pop("torch", None)
			import torch  # type: ignore

		print("Hello testbed setup")

		t1 = torch.randn(2, 2)
		t2 = torch.randn(2, 2)

		# torch.compile may exercise additional import/patching paths; guard so we can still run.
		if hasattr(torch, "compile"):
			@torch.compile  # type: ignore[attr-defined]
			def opt_foo2(x, y):
				a = torch.sin(x)
				b = torch.cos(y)
				return a + b
			print(opt_foo2(t1, t2))
		else:
			print("torch.compile unavailable; running uncompiled path")
			print(torch.sin(t1) + torch.cos(t2))