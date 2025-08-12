{
  description = "ARTIQ Fork with uv2nix support - using main ARTIQ repository as dependency";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    # Main ARTIQ repository as a dependency
    artiq = {
      url = "github:alkalineteam/ARTIQ-alkaline-fork/master";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # uv2nix inputs for modern Python dependency management
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    artiq,
    pyproject-nix,
    uv2nix,
    pyproject-build-systems,
  }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};

    # Python version to use
    python = pkgs.python313;

    # Create wrapper scripts for uv add/remove that update pyproject.toml and rebuild
    uvAddWrapper = pkgs.writeShellScriptBin "uv-add" ''
      if [ $# -eq 0 ]; then
        echo "Usage: uv-add <package1> [package2] [...]"
        exit 1
      fi
      
      echo "Adding packages to pyproject.toml: $*"
      
      # Use Python with tomli_w to add the dependencies to pyproject.toml
      ${python.withPackages (ps: [ps.tomli-w])}/bin/python3 -c "
      import tomllib, tomli_w
      import sys
      
      with open('pyproject.toml', 'rb') as f:
          data = tomllib.load(f)
      
      if 'project' not in data:
          data['project'] = {}
      if 'dependencies' not in data['project']:
          data['project']['dependencies'] = []
      
      packages_to_add = sys.argv[1:]
      added_packages = []
      
      for package in packages_to_add:
          if package not in data['project']['dependencies']:
              data['project']['dependencies'].append(package)
              added_packages.append(package)
          else:
              print(f'{package} already in dependencies')
      
      if added_packages:
          print(f'Added packages: {', '.join(added_packages)}')
      
      with open('pyproject.toml', 'wb') as f:
          tomli_w.dump(data, f)
      " "$@"
      
      echo "Updating uv.lock..."
      uv lock
      
      echo "Rebuilding environment..."
      exec nix develop
    '';

    uvRemoveWrapper = pkgs.writeShellScriptBin "uv-remove" ''
      if [ $# -eq 0 ]; then
        echo "Usage: uv-remove <package1> [package2] [...]"
        exit 1
      fi
      
      echo "Removing packages from pyproject.toml: $*"
      
      # Use Python with tomli_w to remove the dependencies from pyproject.toml
      ${python.withPackages (ps: [ps.tomli-w])}/bin/python3 -c "
      import tomllib, tomli_w
      import sys
      
      with open('pyproject.toml', 'rb') as f:
          data = tomllib.load(f)
      
      packages_to_remove = sys.argv[1:]
      removed_packages = []
      
      if 'project' in data and 'dependencies' in data['project']:
          original_deps = data['project']['dependencies'][:]
          
          # Filter out all packages to remove in one pass
          new_deps = []
          for dep in original_deps:
              should_remove = False
              for package in packages_to_remove:
                  if (dep == package or dep.startswith(package + '==') or dep.startswith(package + '>=') or dep.startswith(package + '~=') or dep.startswith(package + '!=')):
                      should_remove = True
                      if package not in removed_packages:
                          removed_packages.append(package)
                      break
              
              if not should_remove:
                  new_deps.append(dep)
          
          data['project']['dependencies'] = new_deps
          
          # Check for packages that weren't found
          for package in packages_to_remove:
              if package not in removed_packages:
                  print(f'{package} not found in dependencies')
      
      if removed_packages:
          print(f'Removed packages: {', '.join(removed_packages)}')
      
      with open('pyproject.toml', 'wb') as f:
          tomli_w.dump(data, f)
      " "$@"
      
      echo "Updating uv.lock..."
      uv lock
      
      echo "Rebuilding environment..."
      exec nix develop
    '';

    # Load uv workspace if uv.lock exists
    workspace = if builtins.pathExists ./uv.lock 
      then uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; }
      else null;

    # Create overlay from workspace if it exists
    uv2nixOverlay = if workspace != null 
      then workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      }
      else (_: _: {});

    # Construct Python package set with uv2nix if available
    pythonSet = if workspace != null then
      # uv2nix approach - create enhanced package set
      (pkgs.callPackage pyproject-nix.build.packages {
        inherit python;
      }).overrideScope (
        pkgs.lib.composeManyExtensions [
          pyproject-build-systems.overlays.default
          uv2nixOverlay
          # Add ARTIQ and related packages
          (final: prev: {
            # Just inherit ARTIQ directly - this is simpler and more reliable
            inherit (artiq.packages.${system}) artiq migen misoc asyncserial microscope;
            # sipyco comes from a different input in the ARTIQ flake
            sipyco = artiq.inputs.sipyco.packages.${system}.sipyco;
          })
        ]
      )
    else
      # Traditional approach - use ARTIQ's packages directly
      python.pkgs;

    # Helper to create virtual environments with uv2nix
    mkVirtualEnv = name: deps: 
      if workspace != null 
      then pythonSet.mkVirtualEnv name deps
      else python.withPackages (_: [artiq.packages.${system}.artiq]);

  in {
    packages.${system} = {
      # Default package - virtual environment with all dependencies
      default = 
        if workspace != null 
        then mkVirtualEnv "artiq-fork-env" workspace.deps.default
        else python.withPackages (_: [artiq.packages.${system}.artiq]);

      # Expose individual ARTIQ packages
      inherit (artiq.packages.${system}) artiq migen misoc asyncserial microscope;
      # sipyco comes from ARTIQ's input
      sipyco = artiq.inputs.sipyco.packages.${system}.sipyco;
      inherit (artiq.packages.${system}) vivadoEnv vivado openocd-bscanspi;
    };

    devShells.${system} = {
      # Main development shell with automatic uv.lock detection
      default = if workspace != null then
        # When uv.lock exists, create uv2nix development environment
        let
          # Create editable overlay for local development
          editableOverlay = workspace.mkEditablePyprojectOverlay {
            root = "$REPO_ROOT";
            # Add any local packages here if needed
            # members = [ "your-local-package" ];
          };

          # Override with editable support
          editablePythonSet = pythonSet.overrideScope editableOverlay;

          # Create virtual environment with all dependencies
          virtualenv = editablePythonSet.mkVirtualEnv "artiq-fork-dev-env" workspace.deps.all;

        in pkgs.mkShell {
          name = "artiq-fork-uv2nix-shell";
          packages = [
            virtualenv
            pkgs.uv
            uvAddWrapper
            uvRemoveWrapper
            # Include essential ARTIQ development tools
            pkgs.git
            pkgs.llvm_15
            pkgs.lld_15
            pkgs.llvmPackages_15.clang-unwrapped
            pkgs.stdenv.cc.cc.lib
            # Add any additional tools you need
          ] ++ (with artiq.packages.${system}; [
            vivado
            openocd-bscanspi
          ]) ++ artiq.devShells.${system}.default.nativeBuildInputs;

          env = {
            # Use the uv2nix virtual environment (in /nix/store)
            VIRTUAL_ENV = "${virtualenv}";
            UV_NO_SYNC = "1";
            UV_PYTHON = "${virtualenv}/bin/python";
            UV_PYTHON_DOWNLOADS = "never";
            # Inherit ARTIQ-specific environment variables
            QT_PLUGIN_PATH = artiq.qtPaths.QT_PLUGIN_PATH or "";
            QML2_IMPORT_PATH = artiq.qtPaths.QML2_IMPORT_PATH or "";
          };

          shellHook = ''
            unset PYTHONPATH
            export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
            
            # Activate the uv2nix virtual environment (managed by Nix)
            export PATH="${virtualenv}/bin:$PATH"
            
            # Auto-install PyTorch into a local, user-writable dir if not present
            export REPO_DEPS_DIR="$REPO_ROOT/.pydeps"
            mkdir -p "$REPO_DEPS_DIR"
            export PYTHONPATH="$REPO_DEPS_DIR:$PYTHONPATH"
            if ! python -c "import torch" >/dev/null 2>&1; then
              # Detect CUDA availability
              if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
                echo "NVIDIA GPU detected, installing PyTorch with CUDA support to $REPO_DEPS_DIR..."
                # Install CUDA version (defaults to latest CUDA, e.g., cu124)
                uv pip install --target "$REPO_DEPS_DIR" torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 >/dev/null 2>&1 || {
                  echo "CUDA installation failed, falling back to CPU version..."
                  uv pip install --target "$REPO_DEPS_DIR" torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu >/dev/null 2>&1 || true
                }
              else
                echo "No NVIDIA GPU detected, installing PyTorch CPU-only to $REPO_DEPS_DIR..."
                uv pip install --target "$REPO_DEPS_DIR" torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu >/dev/null 2>&1 || true
              fi
            fi
            
            # Add ARTIQ packages to PYTHONPATH so they're available alongside uv2nix packages
            export PYTHONPATH="${editablePythonSet.artiq}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.migen}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.misoc}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.asyncserial}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.microscope}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.sipyco}/${python.sitePackages}:$PYTHONPATH"
            
            # Ensure libstdc++ is available for binary wheels (PyTorch, etc.)
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH"
            
            # Add ARTIQ executables to PATH
            export PATH="${editablePythonSet.artiq}/bin:$PATH"
            
            echo "ARTIQ Fork development environment with uv2nix (uv.lock detected)"
            echo "Using Nix-managed virtual environment at: ${virtualenv}" 
            echo "Python: $(which python)"
            echo "ARTIQ: $(artiq_master --version 2>/dev/null || echo 'available')"
            echo ""
            echo "To add packages:"
            echo "  uv-add <package>    - Add package and rebuild"
            echo "  uv-remove <package> - Remove package and rebuild"
          '';
        }
      else
        # When no uv.lock exists, provide minimal shell
        pkgs.mkShell {
          name = "artiq-fork-minimal-shell";
          packages = [
            (python.withPackages (_: [artiq.packages.${system}.artiq]))
            pkgs.uv
            pkgs.git
            pkgs.stdenv.cc.cc.lib
          ] ++ (with artiq.packages.${system}; [
            vivadoEnv
            vivado  
            openocd-bscanspi
          ]) ++ artiq.devShells.${system}.default.nativeBuildInputs;
          
          shellHook = ''
            # Ensure libstdc++ is available for binary wheels (PyTorch, etc.)
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH"
            export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
            
            # Auto-install PyTorch into a local, user-writable dir if not present
            export REPO_DEPS_DIR="$REPO_ROOT/.pydeps"
            mkdir -p "$REPO_DEPS_DIR"
            export PYTHONPATH="$REPO_DEPS_DIR:$PYTHONPATH"
            if ! python -c "import torch" >/dev/null 2>&1; then
              # Detect CUDA availability
              if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
                echo "NVIDIA GPU detected, installing PyTorch with CUDA support to $REPO_DEPS_DIR..."
                uv pip install --target "$REPO_DEPS_DIR" torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 >/dev/null 2>&1 || {
                  echo "CUDA installation failed, falling back to CPU version..."
                  uv pip install --target "$REPO_DEPS_DIR" torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu >/dev/null 2>&1 || true
                }
              else
                echo "No NVIDIA GPU detected, installing PyTorch CPU-only to $REPO_DEPS_DIR..."
                uv pip install --target "$REPO_DEPS_DIR" torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu >/dev/null 2>&1 || true
              fi
            fi
            
            echo "ARTIQ Fork minimal environment (no uv.lock detected)"
            echo "ARTIQ: $(artiq_master --version 2>/dev/null || echo 'available')"
            echo ""
            echo "To enable full-stack environment:"
            echo "  1. Run 'uv lock' to generate uv.lock from pyproject.toml"
            echo "  2. Run 'nix develop' again for uv2nix integration with uv-add/uv-remove"
          '';
        };
    };

    # Expose useful utilities for downstream consumers
    lib = {
      inherit mkVirtualEnv pythonSet;
      # Re-export ARTIQ utilities
      inherit (artiq) qtPaths makeArtiqBoardPackage openocd-bscanspi-f;
    };

    # Formatter for nix files
    formatter.${system} = pkgs.alejandra;
  };
}