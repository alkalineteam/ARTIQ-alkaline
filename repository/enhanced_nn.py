import argparse
import math
import sys
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from artiq.experiment import EnvExperiment, rpc, NumberValue, BooleanValue, EnumerationValue


# ------------------------------
# Model components
# ------------------------------

class PreNormResidual(nn.Module):
    """Pre-Norm residual block: y = x + Dropout(F( LayerNorm(x) ))"""

    def __init__(self, d_model: int, fn: nn.Module, dropout: float = 0.0):
        super().__init__()
        self.norm = nn.LayerNorm(d_model)
        self.fn = fn
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.dropout(self.fn(self.norm(x)))


class FeedForward(nn.Module):
    def __init__(self, d_model: int, d_ff: int, dropout: float = 0.0):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU(),
            nn.Dropout(dropout) if dropout > 0 else nn.Identity(),
            nn.Linear(d_ff, d_model),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ResidualMLPBlock(nn.Module):
    def __init__(self, d_model: int, d_ff: int, dropout: float = 0.0):
        super().__init__()
        self.ff = PreNormResidual(d_model, FeedForward(d_model, d_ff, dropout), dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.ff(x)


class EnhancedMLP(nn.Module):
    """
    A deep residual MLP with large width and depth to achieve huge parameter counts.

    Architecture:
      - Input projection: in_dim -> d_model
      - N x [PreNorm + FF(d_model -> d_ff -> d_model) + Residual]
      - Output projection: d_model -> out_dim
    """

    def __init__(
        self,
        in_dim: int = 1024,
        d_model: int = 2048,
        d_ff: int = 8192,
        depth: int = 24,
        out_dim: int = 10,
        dropout: float = 0.0,
    ):
        super().__init__()
        self.in_proj = nn.Linear(in_dim, d_model)
        self.blocks = nn.Sequential(
            *[ResidualMLPBlock(d_model, d_ff, dropout) for _ in range(depth)]
        )
        self.out_norm = nn.LayerNorm(d_model)
        self.out_proj = nn.Linear(d_model, out_dim)

        # Initialize with a stable scheme
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_uniform_(m.weight, a=math.sqrt(5))
                if m.bias is not None:
                    fan_in, _ = nn.init._calculate_fan_in_and_fan_out(m.weight)
                    bound = 1 / math.sqrt(fan_in)
                    nn.init.uniform_(m.bias, -bound, bound)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.in_proj(x)
        x = self.blocks(x)
        x = self.out_norm(x)
        x = self.out_proj(x)
        return x


# ------------------------------
# Utilities
# ------------------------------

def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def human_bytes(num_elements: int, dtype: torch.dtype = torch.float32) -> str:
    # Memory assuming parameters are materialized at given dtype (no optimizer state)
    bytes_per = torch.tensor([], dtype=dtype).element_size()
    total = num_elements * bytes_per
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while total >= 1024 and i < len(units) - 1:
        total /= 1024.0
        i += 1
    return f"{total:.2f} {units[i]}"


@dataclass
class Config:
    in_dim: int
    d_model: int
    d_ff: int
    depth: int
    out_dim: int
    dropout: float


PRESETS = {
    # ~100M parameters (approx; depends on exact dims)
    "large": Config(in_dim=1024, d_model=2048, d_ff=8192, depth=24, out_dim=10, dropout=0.0),
    # ~500M parameters
    "huge": Config(in_dim=1024, d_model=4096, d_ff=16384, depth=24, out_dim=10, dropout=0.0),
    # ~1B+ parameters (dangerous on typical machines)
    "extreme": Config(in_dim=2048, d_model=6144, d_ff=24576, depth=32, out_dim=10, dropout=0.0),
}


def build_model_from_config(cfg: Config, device: Optional[torch.device] = None, dtype: Optional[torch.dtype] = None) -> EnhancedMLP:
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = EnhancedMLP(
        in_dim=cfg.in_dim,
        d_model=cfg.d_model,
        d_ff=cfg.d_ff,
        depth=cfg.depth,
        out_dim=cfg.out_dim,
        dropout=cfg.dropout,
    )
    model.to(device=device, dtype=dtype if dtype is not None else torch.float32)
    return model


# ------------------------------
# CLI
# ------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a large enhanced neural network and optionally run a forward pass.")
    parser.add_argument("--preset", choices=list(PRESETS.keys()), default="large", help="Size preset to use")
    parser.add_argument("--in-dim", type=int, default=None, help="Override input dimension")
    parser.add_argument("--d-model", type=int, default=None, help="Model width (hidden size)")
    parser.add_argument("--d-ff", type=int, default=None, help="Feed-forward expansion size")
    parser.add_argument("--depth", type=int, default=None, help="Number of residual blocks")
    parser.add_argument("--out-dim", type=int, default=None, help="Number of output classes")
    parser.add_argument("--dropout", type=float, default=None, help="Dropout probability")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32", help="Parameter dtype")
    parser.add_argument("--batch", type=int, default=8, help="Batch size for dummy forward")
    parser.add_argument("--forward", action="store_true", help="Run a dummy forward pass")
    parser.add_argument("--cpu", action="store_true", help="Force CPU even if CUDA is available")

    args = parser.parse_args(argv)

    cfg = PRESETS[args.preset]
    cfg = Config(
        in_dim=args.in_dim or cfg.in_dim,
        d_model=args.d_model or cfg.d_model,
        d_ff=args.d_ff or cfg.d_ff,
        depth=args.depth or cfg.depth,
        out_dim=args.out_dim or cfg.out_dim,
        dropout=args.dropout if args.dropout is not None else cfg.dropout,
    )

    if args.dtype == "fp32":
        dtype = torch.float32
    elif args.dtype == "bf16":
        dtype = torch.bfloat16
    else:
        dtype = torch.float16

    use_cuda = torch.cuda.is_available() and not args.cpu
    device = torch.device("cuda" if use_cuda else "cpu")

    # Safety warning for very large configs on CPU
    est_params = (
        cfg.in_dim * cfg.d_model
        + cfg.depth * (cfg.d_model * cfg.d_ff + cfg.d_ff * cfg.d_model)
        + cfg.d_model * cfg.out_dim
    )
    est_mem = human_bytes(est_params, dtype=dtype)

    print(f"Device: {device}")
    print(f"Config: in={cfg.in_dim}, d_model={cfg.d_model}, d_ff={cfg.d_ff}, depth={cfg.depth}, out={cfg.out_dim}, dropout={cfg.dropout}")
    print(f"Estimated parameters (approx): {est_params:,}")
    print(f"Estimated parameter memory @ {args.dtype}: {est_mem}")

    try:
        model = build_model_from_config(cfg, device=device, dtype=dtype)
    except RuntimeError as e:
        print(f"Model allocation failed: {e}")
        print("Tip: try --dtype bf16 or --dtype fp16, reduce preset/width/depth, or use CUDA.")
        sys.exit(1)

    total = count_params(model)
    print(f"Actual parameter count: {total:,}")

    if args.forward:
        x = torch.randn(args.batch, cfg.in_dim, device=device, dtype=dtype)
        with torch.inference_mode():
            y = model(x)
        print(f"Forward OK: input {tuple(x.shape)} -> output {tuple(y.shape)}")


if __name__ == "__main__":
    main()


# ------------------------------
# ARTIQ Experiment wrapper
# ------------------------------

class EnhancedNNExperiment(EnvExperiment):
    """ARTIQ experiment that instantiates and trains a large residual MLP on the host.

    Notes:
    - All heavy lifting (model/data/training) is done via @rpc on the host Python side.
    - Defaults are chosen to be large but safe without CUDA. Tweak attributes below as needed.
    """

    def build(self):
        self.setattr_device("core")
        # Arguments
        self.setattr_argument("preset", EnumerationValue(["large", "huge", "extreme"], default="large"))
        self.setattr_argument("override_dims", BooleanValue(False))
        self.setattr_argument("arg_in_dim", NumberValue(512, type="int", precision=0, min=1))
        self.setattr_argument("arg_d_model", NumberValue(1024, type="int", precision=0, min=1))
        self.setattr_argument("arg_d_ff", NumberValue(4096, type="int", precision=0, min=1))
        self.setattr_argument("arg_depth", NumberValue(8, type="int", precision=0, min=1))
        self.setattr_argument("arg_out_dim", NumberValue(10, type="int", precision=0, min=2))
        self.setattr_argument("dropout", NumberValue(0.0, precision=2, min=0.0, max=0.9))
        self.setattr_argument("epochs", NumberValue(3, type="int", precision=0, min=1))
        self.setattr_argument("batch_size", NumberValue(256, type="int", precision=0, min=1))
        self.setattr_argument("train_samples", NumberValue(20000, type="int", precision=0, min=1))
        self.setattr_argument("test_samples", NumberValue(4000, type="int", precision=0, min=1))
        self.setattr_argument("dtype", EnumerationValue(["fp32", "bf16", "fp16"], default="fp32"))
        self.setattr_argument("force_cpu", BooleanValue(False))

        # Host-side state containers
        self._model = None
        self._device = torch.device("cpu")
        self._X_train = None
        self._y_train = None
        self._X_test = None
        self._y_test = None

    # Helper: derive config & device/dtype from arguments
    def _derive_cfg(self):
        base = PRESETS.get(self.preset, PRESETS["large"])
        if self.override_dims:
            in_dim = int(self.arg_in_dim)
            d_model = int(self.arg_d_model)
            d_ff = int(self.arg_d_ff)
            depth = int(self.arg_depth)
            out_dim = int(self.arg_out_dim)
        else:
            in_dim = base.in_dim
            d_model = base.d_model
            d_ff = base.d_ff
            depth = base.depth
            out_dim = base.out_dim

        if self.dtype == "bf16":
            dtype = torch.bfloat16
        elif self.dtype == "fp16":
            dtype = torch.float16
        else:
            dtype = torch.float32

        use_cuda = torch.cuda.is_available() and (not bool(self.force_cpu))
        device = torch.device("cuda" if use_cuda else "cpu")

        cfg = Config(
            in_dim=in_dim,
            d_model=d_model,
            d_ff=d_ff,
            depth=depth,
            out_dim=out_dim,
            dropout=float(self.dropout),
        )
        return cfg, device, dtype

    @rpc
    def _host_build_model(self):
    cfg, device, dtype = self._derive_cfg()
    self._device = device
    self._model = build_model_from_config(cfg, device=device, dtype=dtype)
        total = sum(p.numel() for p in self._model.parameters())
        self.set_dataset("enhanced_nn.param_count", int(total))

    @rpc
    def _host_prepare_data(self):
        # Synthetic classification data
    cfg, device, dtype = self._derive_cfg()
    self._X_train = torch.randn(int(self.train_samples), cfg.in_dim, device=device, dtype=dtype)
    self._y_train = torch.randint(0, cfg.out_dim, (int(self.train_samples),), device=device)
    self._X_test = torch.randn(int(self.test_samples), cfg.in_dim, device=device, dtype=dtype)
    self._y_test = torch.randint(0, cfg.out_dim, (int(self.test_samples),), device=device)

    @rpc
    def _host_train(self):
    model = self._model
        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.CrossEntropyLoss()

    N = int(self.train_samples)
    bs = int(self.batch_size)
        steps = (N + bs - 1) // bs
        for epoch in range(self.epochs):
            total_loss = 0.0
            for i in range(0, N, bs):
                xb = self._X_train[i : i + bs]
                yb = self._y_train[i : i + bs]
                optimizer.zero_grad(set_to_none=True)
                out = model(xb)
                loss = criterion(out, yb)
                loss.backward()
                optimizer.step()
                total_loss += float(loss.detach().cpu())
            avg_loss = total_loss / steps
            print(f"Epoch {epoch+1}/{self.epochs} - loss: {avg_loss:.4f}")

    @rpc
    def _host_eval(self):
        model = self._model
        model.eval()
        with torch.no_grad():
            logits = model(self._X_test)
            pred = logits.argmax(dim=1)
            acc = (pred == self._y_test).float().mean().item()
        print(f"Accuracy: {acc:.4f}")
        self.set_dataset("enhanced_nn.accuracy", float(acc))

    def run(self):
        # Host-only flow using RPCs for clarity and potential kernel integration later
        self._host_build_model()
        self._host_prepare_data()
        self._host_train()
        self._host_eval()
