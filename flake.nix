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

    nixgl = {
      url = "github:nix-community/nixGL";
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
    nixgl,
  }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      config.allowUnfree = true;
    };
    
    # nixGL packages
    nixgl-pkgs = nixgl.packages.${system};

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
      exec nix develop --impure
    '';

    # CUDA-enabled Python wrapper using nixGL (optional, not used by default)
    nixglPythonWrapper = pkgs.writeShellScriptBin "python-cuda" ''
      # Try different nixGL variants for NVIDIA
      if command -v nixGL &> /dev/null; then
        exec nixGL python "$@"
      elif command -v nixGLNvidia &> /dev/null; then
        exec nixGLNvidia python "$@"
      elif command -v nixGLIntel &> /dev/null; then
        echo "Warning: Only Intel GL found, CUDA may not work properly"
        exec nixGLIntel python "$@"
      else
        echo ""
        echo "=== nixGL Installation Required ==="
        echo "To enable CUDA support, run this command in a separate terminal:"
        echo ""
        echo "  nix shell github:nix-community/nixGL#auto.nixGLNvidia --impure"
        echo ""
        echo "Then in that shell, run:"
        echo "  nixGLNvidia python $*"
        echo ""
        echo "Alternatively, install nixGL permanently:"
        echo "  nix profile install github:nix-community/nixGL#auto.nixGLNvidia --impure"
        echo ""
        echo "Running python without GPU access for now..."
        exec python "$@"
      fi
    '';

    # Generic nixGL wrapper for any CUDA application
    cudaWrapper = pkgs.writeShellScriptBin "cuda-run" ''
      if [ $# -eq 0 ]; then
        echo "Usage: cuda-run <command> [args...]"
        echo "Example: cuda-run python script.py"
        echo "Example: cuda-run nvidia-smi"
        exit 1
      fi
      
      # Try different nixGL variants
      if command -v nixGL &> /dev/null; then
        exec nixGL "$@"
      elif command -v nixGLNvidia &> /dev/null; then
        exec nixGLNvidia "$@"
      elif command -v nixGLIntel &> /dev/null; then
        echo "Warning: Only Intel GL found, CUDA may not work properly"
        exec nixGLIntel "$@"
      else
        echo ""
        echo "nixGL not found! To enable CUDA support, install nixGL:"
        echo "  nix profile install github:nix-community/nixGL#nixGLNvidia"
        echo "  # or for current session:"
        echo "  nix shell github:nix-community/nixGL#nixGLNvidia"
        echo ""
        echo "Then run: nixGLNvidia $*"
        echo ""
        echo "Running without GPU access..."
        exec "$@"
      fi
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
      exec nix develop --impure
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

    # Overlay to fix NVIDIA CUDA library dependencies
    cudaFixOverlay = final: prev: 
      let
        # Common CUDA libraries that might be missing
        commonCudaDeps = [
          "libmlx5.so.1"
          "librdmacm.so.1" 
          "libibverbs.so.1"
          "libnvJitLink.so.12"
          "libcusparse.so.12"
          "libcublas.so.12"
          "libcublasLt.so.12"
          "libcufft.so.11"
          "libcufile.so.0"
          "libcusparseLt.so.0"
          "libnccl.so.2"
          "libcurand.so.10"
          "libcudnn.so.9"
          "libcudart.so.12"
          "libnvrtc.so.12"
          "libcuda.so.1"
          "libcusolver.so.11"
          "libcupti.so.12"
          # FFmpeg libraries
          "libavutil.so.56"
          "libavutil.so.58" 
          "libavcodec.so.58"
          "libavcodec.so.60"
          "libavformat.so.58"
          "libavformat.so.59"
          "libavformat.so.60"
          "libavdevice.so.58"
          "libavdevice.so.59"
          "libavdevice.so.60"
          "libavfilter.so.7"
          "libavfilter.so.8"
          "libavfilter.so.9"
          # PyTorch internal libraries
          "libtorch_python.so"
          "libtorch.so"
          "libtorch_cpu.so"
          "libtorch_cuda.so"
          "libc10.so"
          "libc10_cuda.so"
        ];
        
        # Helper function to override CUDA packages
        fixCudaPackage = name: pkg: 
          if pkg != null then
            pkg.overrideAttrs (old: {
              autoPatchelfIgnoreMissingDeps = (old.autoPatchelfIgnoreMissingDeps or []) ++ commonCudaDeps;
            })
          else pkg;
      in {
        # NVIDIA CUDA packages
        nvidia-cufile-cu12 = fixCudaPackage "nvidia-cufile-cu12" (prev.nvidia-cufile-cu12 or null);
        nvidia-cusolver-cu12 = fixCudaPackage "nvidia-cusolver-cu12" (prev.nvidia-cusolver-cu12 or null);
        nvidia-cusparse-cu12 = fixCudaPackage "nvidia-cusparse-cu12" (prev.nvidia-cusparse-cu12 or null);
        nvidia-curand-cu12 = fixCudaPackage "nvidia-curand-cu12" (prev.nvidia-curand-cu12 or null);
        nvidia-cublas-cu12 = fixCudaPackage "nvidia-cublas-cu12" (prev.nvidia-cublas-cu12 or null);
        nvidia-cufft-cu12 = fixCudaPackage "nvidia-cufft-cu12" (prev.nvidia-cufft-cu12 or null);
        nvidia-nccl-cu12 = fixCudaPackage "nvidia-nccl-cu12" (prev.nvidia-nccl-cu12 or null);
        nvidia-nvjitlink-cu12 = fixCudaPackage "nvidia-nvjitlink-cu12" (prev.nvidia-nvjitlink-cu12 or null);
        nvidia-nvtx-cu12 = fixCudaPackage "nvidia-nvtx-cu12" (prev.nvidia-nvtx-cu12 or null);
        nvidia-cusparselt-cu12 = fixCudaPackage "nvidia-cusparselt-cu12" (prev.nvidia-cusparselt-cu12 or null);
        # PyTorch and related packages
        torch = fixCudaPackage "torch" (prev.torch or null);
        torchaudio = if prev ? torchaudio then
          prev.torchaudio.overrideAttrs (old: {
            dontAutoPatchelf = true;
          })
        else prev.torchaudio or null;
        torchvision = fixCudaPackage "torchvision" (prev.torchvision or null);
      };

    # Construct Python package set with uv2nix if available
    pythonSet = if workspace != null then
      # uv2nix approach - create enhanced package set
      (pkgs.callPackage pyproject-nix.build.packages {
        inherit python;
      }).overrideScope (
        pkgs.lib.composeManyExtensions [
          pyproject-build-systems.overlays.default
          uv2nixOverlay
          cudaFixOverlay
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
            # RDMA/InfiniBand libraries for CUDA packages
            pkgs.rdma-core
            # nixGL for NVIDIA driver access - now enabled with proper approach
            nixgl-pkgs.nixGLNvidia
            # Add any additional tools you need
          ] ++ (with artiq.packages.${system}; [
            vivado
            openocd-bscanspi
          ]);

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
            
            
            # Add ARTIQ packages to PYTHONPATH so they're available alongside uv2nix packages
            export PYTHONPATH="${editablePythonSet.artiq}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.migen}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.misoc}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.asyncserial}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.microscope}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.sipyco}/${python.sitePackages}:$PYTHONPATH"
            
            # Ensure libstdc++ is available for binary wheels (PyTorch, etc.)
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.rdma-core}/lib:$LD_LIBRARY_PATH"
            
            # CUDA environment setup
            export CUDA_PATH=/usr/local/cuda
            export PATH=$CUDA_PATH/bin:$PATH
            export LD_LIBRARY_PATH=$CUDA_PATH/lib64:$LD_LIBRARY_PATH
            
            # Auto-detect NVIDIA GPU and set up nixGL aliases
            if command -v lspci >/dev/null 2>&1 && lspci | grep -i nvidia > /dev/null 2>&1; then
              # NVIDIA GPU detected
              NIXGL_BIN=$(find ${nixgl-pkgs.nixGLNvidia}/bin -name "nixGLNvidia-*" 2>/dev/null | head -n1)
              GPU_TYPE="NVIDIA"
              
              if [ -n "$NIXGL_BIN" ]; then
                alias python="$NIXGL_BIN python"
                alias python3="$NIXGL_BIN python3"
                alias jupyter="$NIXGL_BIN jupyter"
                alias ipython="$NIXGL_BIN ipython"
                export NIXGL_BIN="$NIXGL_BIN"
              fi
            else
              # No NVIDIA GPU or lspci not available - use CPU-only mode
              NIXGL_BIN=""
              GPU_TYPE="CPU-only"
            fi
            
            # Add ARTIQ executables to PATH
            export PATH="${editablePythonSet.artiq}/bin:$PATH"
            
            echo "ARTIQ Fork development environment with uv2nix (uv.lock detected)"
            echo "Using Nix-managed virtual environment at: ${virtualenv}" 
            echo "Python: $(which python)"
            echo "ARTIQ: $(artiq_master --version 2>/dev/null || echo 'available')"
            echo "✅ PyTorch dev shell with nixGL ($GPU_TYPE) is ready!"
            if [ -n "$NIXGL_BIN" ]; then
              echo "💡 python3 and jupyter use GPU acceleration automatically"
            else
              echo "💡 Running in CPU-only mode (no NVIDIA GPU detected)"
            fi
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
            # RDMA/InfiniBand libraries for CUDA packages
            pkgs.rdma-core
            # nixGL for NVIDIA driver access - now enabled with proper approach
            nixgl-pkgs.nixGLNvidia
          ] ++ (with artiq.packages.${system}; [
            vivadoEnv
            vivado  
            openocd-bscanspi
          ]);
          
          shellHook = ''
            # Ensure libstdc++ is available for binary wheels (PyTorch, etc.)
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.rdma-core}/lib:$LD_LIBRARY_PATH"
            export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
            
            # CUDA environment setup
            export CUDA_PATH=/usr/local/cuda
            export PATH=$CUDA_PATH/bin:$PATH
            export LD_LIBRARY_PATH=$CUDA_PATH/lib64:$LD_LIBRARY_PATH
            
            # Auto-detect NVIDIA GPU and set up nixGL aliases
            if command -v lspci >/dev/null 2>&1 && lspci | grep -i nvidia > /dev/null 2>&1; then
              # NVIDIA GPU detected
              NIXGL_BIN=$(find ${nixgl-pkgs.nixGLNvidia}/bin -name "nixGLNvidia-*" 2>/dev/null | head -n1)
              GPU_TYPE="NVIDIA"
              
              if [ -n "$NIXGL_BIN" ]; then
                alias python="$NIXGL_BIN python"
                alias python3="$NIXGL_BIN python3"
                alias jupyter="$NIXGL_BIN jupyter"
                alias ipython="$NIXGL_BIN ipython"
                export NIXGL_BIN="$NIXGL_BIN"
              fi
            else
              # No NVIDIA GPU or lspci not available - use CPU-only mode
              NIXGL_BIN=""
              GPU_TYPE="CPU-only"
            fi
            
            echo "ARTIQ Fork minimal environment (no uv.lock detected)"
            echo "✅ PyTorch dev shell with nixGL ($GPU_TYPE) is ready!"
            if [ -n "$NIXGL_BIN" ]; then
              echo "💡 python3 and jupyter use GPU acceleration automatically"
            else
              echo "💡 Running in CPU-only mode (no NVIDIA GPU detected)"
            fi
            echo "ARTIQ: $(artiq_master --version 2>/dev/null || echo 'available')"
            echo ""
            echo "For CUDA/GPU applications:"
            echo "  python-cuda script.py - Run Python with GPU access"
            echo "  cuda-run <command>    - Run any command with GPU access"
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