## ARTIQ Alkaline Fork

Custom ARTIQ fork with a reproducible Nix + uv2nix Python 3.13 environment, CUDA / PyTorch support, and convenience wrappers for dependency management.

## Key Features

- Upstream ARTIQ flake consumed directly (inherits core packages: artiq, migen, misoc, asyncserial, microscope, sipyco)
- uv / uv2nix driven Python dependency locking (pure wheels sourced into the Nix store)
- Python 3.13 toolchain (overrideable) with scientific stack (numpy, scipy, h5py, sympy, astropy, plotting libs, sklearn)
- PyTorch + CUDA (cu129 wheels) with automatic nixGL GPU wrapper detection
- Automatic wheel hash repair (`fix-hashes.sh`) for PyTorch CUDA wheels (works around missing hash / % encoding issues in `uv.lock`)
- Wrapper commands: `uv-add` and `uv-remove` (atomic edit -> lock -> hash-fix -> rebuild cycle)
- Optional GPU execution helpers: `python-cuda`, `cuda-run`
- Clean editable overlay for local code without polluting dependencies
- Deterministic virtual environment exposed via Nix (no venv activation scripts needed)

## Prerequisites

- Nix with flakes enabled (`experimental-features = nix-command flakes`)
- (Optional) NVIDIA GPU + drivers; nixGL for graphical / CUDA contexts
- `uv` is provided inside the shell (external install not required)

## Quick Start

Clone (or update) the repository then generate an initial lock file (first time only):

```bash
uv lock          # produces uv.lock
./fix-hashes.sh  # ensure PyTorch wheel hashes present (idempotent)
nix develop --impure
```

You should see shell diagnostics including detected GPU mode and ARTIQ availability.

### Adding Dependencies

Use the provided wrapper (preferred – it updates everything and re-enters the shell):

```bash
uv-add seaborn plotly
```

Under the hood this:
1. Edits `pyproject.toml`
2. Runs `uv lock`
3. Runs `./fix-hashes.sh`
4. Rebuilds (`nix develop --impure`)

### Removing Dependencies

```bash
uv-remove seaborn
```

Follows the same lifecycle (edit -> relock -> hash fix -> rebuild).

### Manual Lock Maintenance (Advanced)

If you run `uv lock` yourself, always follow with:

```bash
./fix-hashes.sh
```

Otherwise Nix evaluation may fail on PyTorch wheels missing a `hash =` attribute.

## PyTorch & Hash Repair

`fix-hashes.sh` injects SHA256 hashes for selected cu129 wheels (PyTorch 2.8.0) that appear without hashes in `uv.lock`. This is a temporary workaround until either:

- uv2nix supports these wheels with proper hash metadata, or
- The wheel set is trimmed to a single target platform, or
- PyTorch packaging normalizes URL encoding / upstream indices provide hashes directly.

Re-running the script is safe and no-op once all targeted hashes exist.

## GPU / CUDA Usage

- On entry the shell attempts to detect an NVIDIA GPU (device files / modules) and, if available, will expose nixGL.
- Aliases may wrap `python`, `python3`, `jupyter` with the appropriate nixGL launcher.
- Use `cuda-run <cmd>` to force execution under nixGL; `python-cuda` provides a convenience Python launcher.
- If no GPU is detected, the environment gracefully falls back to CPU-only mode.

## Project Layout

```
flake.nix          - Nix flake (env, overlays, wrappers)
pyproject.toml     - Project & dependency metadata (managed via uv-add/uv-remove)
uv.lock            - Locked dependency graph (consumed by uv2nix)
fix-hashes.sh      - PyTorch wheel hash injector (idempotent)
scripts/           - Helper scripts & CUDA tests (e.g. test_cuda.py)
setup.sh           - Optional host bootstrap (enables flakes, installs Nix)
artiq_fork.egg-info/ (generated metadata)
```

## Typical Workflow

1. Develop Python modules within this repository (add paths / packages as needed)
2. Add / remove dependencies using wrappers
3. Commit `pyproject.toml` and `uv.lock` together
4. (Optional) Run `./scripts/test_cuda.py` or a simple torch CUDA check inside shell

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| Nix evaluation fails on PyTorch wheel path | Missing hash in `uv.lock` | Run `./fix-hashes.sh` (or use wrappers) |
| GPU not detected | No /dev/nvidia* present at eval time | Ensure driver installed; enter shell after driver load |
| New torch version introduced | Hash script map outdated | Update script or trim to single platform wheels |
| Dependency not added | Manual edit bypassed wrappers | Use `uv-add <pkg>` and commit updated lock |

## Contributing

Pull requests welcome (keep changes reproducible: update both `pyproject.toml` + `uv.lock`). Consider running a smoke test (`python -c "import artiq, torch; print(torch.cuda.is_available())"`).

## License

LGPL-3.0-or-later (inherits ARTIQ licensing)

## Future Improvements (Planned / Suggestions)

- Auto-generate hashes dynamically (fetch + compute) rather than static map
- Reduce lock to target platform only to drop extraneous wheels
- CI: `nix flake check`, import smoke tests, mypy / linting
- Optional separation of dev-only dependencies into a group
