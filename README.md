# ARTIQ Fork

This is a custom ARTIQ fork that uses the main ARTIQ repository as a dependency and provides additional functionality through uv2nix package management.

## Features

- 🚀 Uses main ARTIQ repository as a Nix flake dependency
- 📦 Modern Python dependency management with uv2nix
- 🔧 Maintains compatibility with upstream ARTIQ
- ⚡ Fast development iteration with virtual environments
- 🎯 Clean separation between upstream ARTIQ and custom extensions

## Quick Start

### Using uv2nix (Recommended)

1. Enter development environment (everything is in `/nix/store`):
   ```bash
   cd ARTIQ_fork
   nix develop
   ```

2. Add new Python packages:
   ```bash
   # Use the minimal shell to modify dependencies
   nix develop .#artiq-only --command uv add plotly seaborn
   
   # Rebuild with new packages (now in /nix/store)
   nix develop
   
   # Verify packages are available
   python -c "import artiq; import plotly; print('Success!')"
   ```

3. Add development dependencies:
   ```bash
   nix develop .#artiq-only --command uv add --dev jupyter notebook
   nix develop  # Rebuild environment
   ```

### Fallback Mode

If no `uv.lock` file exists, the flake will automatically fall back to the main ARTIQ development environment:

```bash
nix develop  # Uses main ARTIQ environment
```

## Development Shells

- **`nix develop`** - Full development environment with uv2nix (or ARTIQ fallback)
- **`nix develop .#artiq-only`** - Minimal shell with just ARTIQ packages

## Architecture

This flake demonstrates how to:
- Use another Nix flake (main ARTIQ) as a dependency
- Layer uv2nix on top of existing packages
- Provide graceful fallbacks when uv.lock is missing
- Maintain clean separation between upstream and custom code

## Adding Custom Code

1. Add your Python modules to the `artiq_fork/` directory
2. Add dependencies: `nix develop .#artiq-only --command uv add <package>`
3. Rebuild: `nix develop`
4. All packages now available in `/nix/store` (reproducible and cached)

## Environment Variables

The development shell sets up:
- `VIRTUAL_ENV` - Points to the uv2nix virtual environment
- `UV_PYTHON` - Uses the Nix-provided Python interpreter
- `QT_PLUGIN_PATH` / `QML2_IMPORT_PATH` - For ARTIQ GUI applications

## Dependencies

- **ARTIQ**: Main quantum control system (from upstream repository)
- **uv**: Modern Python package manager
- **Nix**: Reproducible build system

## License

LGPL-3.0-or-later (same as ARTIQ)