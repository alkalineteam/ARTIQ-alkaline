{
  description = "ARTIQ Fork for alkaline team @ University of Birmingham";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    # ARTIQ
    artiq = {
      url = "github:alkalineteam/ARTIQ-alkaline-fork/master";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # uv2nix inputs for Python dependency management
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

    # nixGL for GPU support
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
    
    # Check if NVIDIA GPU is available by looking for NVIDIA devices or driver modules
    # Use only path-based checks to avoid file read errors
    hasNvidiaGpu = builtins.pathExists "/dev/nvidia0" ||
                    builtins.pathExists "/proc/driver/nvidia" ||
                    builtins.pathExists "/sys/module/nvidia";
    
    # nixGL packages - only load if NVIDIA GPU is detected to avoid null driver version errors
    nixgl-pkgs = if hasNvidiaGpu then nixgl.packages.${system} else {};

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
      
      echo "Fixing PyTorch hashes..."
      ./fix-hashes.sh
      
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
      
      echo "Fixing PyTorch hashes..."
      ./fix-hashes.sh
      
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
          # PyTorch internal libraries
          "libtorch_python.so"
          "libtorch.so"
          "libtorch_cpu.so"
          "libtorch_cuda.so"
          "libc10.so"
          "libc10_cuda.so"
          # # FFmpeg libraries
          # "libavutil.so.56"
          # "libavutil.so.58"
          # "libavcodec.so.58"
          # "libavcodec.so.60"
          # "libavformat.so.58"
          # "libavformat.so.59"
          # "libavformat.so.60"
          # "libavdevice.so.58"
          # "libavdevice.so.59"
          # "libavdevice.so.60"
          # "libavfilter.so.7"
          # "libavfilter.so.8"
          # "libavfilter.so.9"
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

    # Wheel-based PyQt6 overlay (disable auto-patchelf, keep runtime deps via env)
    pyqtFixOverlay = final: prev: {
      pyqt6 = if prev ? pyqt6 then prev.pyqt6.overrideAttrs (old: {
        dontAutoPatchelf = true;
        propagatedBuildInputs = (old.propagatedBuildInputs or []) ++ [ final.pkgs.fontconfig final.pkgs.zstd ];
        postInstall = (old.postInstall or "") + ''
          echo "[pyqtFixOverlay] Disabled auto-patchelf for pyqt6 (wheel RPATH)"
        '';
      }) else prev.pyqt6 or null;
      pyqt6-qt6 = if prev ? pyqt6-qt6 then prev.pyqt6-qt6.overrideAttrs (old: {
        dontAutoPatchelf = true;
        propagatedBuildInputs = (old.propagatedBuildInputs or []) ++ [ final.pkgs.fontconfig final.pkgs.zstd ];
        postInstall = (old.postInstall or "") + ''
          echo "[pyqtFixOverlay] Disabled auto-patchelf for pyqt6-qt6 (wheel RPATH)"
        '';
      }) else prev.pyqt6-qt6 or null;
    };

    # Helper scripts for forcing setuptools on selected packages
    bootstrap = final: pkg: ''
      export PYTHONPATH=${final.python.pkgs.setuptools}/${final.python.sitePackages}:${final.python.pkgs.wheel}/${final.python.sitePackages}:$PYTHONPATH
      echo "[overlay:${pkg}] prepended setuptools+wheel to PYTHONPATH"
    '';
    rewritePoetry = name: body: ''
      if [ -f pyproject.toml ] && grep -q '^\[tool.poetry\]' pyproject.toml; then
        echo "[overlay:${name}] rewriting Poetry pyproject to setuptools"
        cat > pyproject.toml <<'EOF'
${body}
EOF
      fi
    '';

    # Overlay to adapt ndscan & oitg build backends to setuptools
    ndscanOitgOverlay = final: prev: {
      ndscan = if prev ? ndscan then prev.ndscan.overrideAttrs (old: {
        # Keep setuptools available but don't mutate upstream pyproject
        nativeBuildInputs = (old.nativeBuildInputs or []) ++ [ final.python.pkgs.setuptools final.python.pkgs.wheel ];
        preBuild = (old.preBuild or "") + (bootstrap final "ndscan");
      }) else prev.ndscan or null;

      oitg = if prev ? oitg then prev.oitg.overrideAttrs (old: {
        nativeBuildInputs = (old.nativeBuildInputs or []) ++ [ final.python.pkgs.setuptools final.python.pkgs.wheel ];
        postPatch = (old.postPatch or "") + (rewritePoetry "oitg" ''
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "oitg"
version = "0.1"
requires-python = ">=3.10"
dependencies = [
  "statsmodels>=0.14.0",
  "scipy>=1.11.4",
  "numpy>=1.24.2",
  "h5py>=3.10.0",
]

[tool.setuptools.packages.find]
include = ["oitg*"]
exclude = ["conda*"]
'');
        preBuild = (old.preBuild or "") + (bootstrap final "oitg");
      }) else prev.oitg or null;

      qasync = if prev ? qasync then prev.qasync.overrideAttrs (old: {
        nativeBuildInputs = (old.nativeBuildInputs or []) ++ [ final.python.pkgs.setuptools final.python.pkgs.wheel ];
        postPatch = (old.postPatch or "") + (rewritePoetry "qasync" ''
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "qasync"
version = "0.27.2"
requires-python = ">=3.9"
dependencies = []

[tool.setuptools.packages.find]
include = ["qasync*"]
'');
        preBuild = (old.preBuild or "") + (bootstrap final "qasync");
      }) else prev.qasync or null;
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
          pyqtFixOverlay
          ndscanOitgOverlay
          # Ensure pythonparser (legacy setup.py, no pyproject) builds under uv2nix by injecting setuptools/wheel
          (final: prev: {
            pythonparser = if prev ? pythonparser then prev.pythonparser.overrideAttrs (old: {
              nativeBuildInputs = (old.nativeBuildInputs or []) ++ [ final.python.pkgs.setuptools final.python.pkgs.wheel ];
              buildInputs = (old.buildInputs or []) ++ [ final.python.pkgs.setuptools ];
              preBuild = (old.preBuild or "") + (bootstrap final "pythonparser");
            }) else prev.pythonparser or null;
          })
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
      # Main development shell - requires uv.lock to exist
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
          packages = builtins.filter (x: x != null) [
            virtualenv
            pkgs.uv
            uvAddWrapper
            uvRemoveWrapper
            # llvmlite needed when invoking ARTIQ frontends via virtualenv python
            python.pkgs.llvmlite
            # Include essential ARTIQ development tools
            pkgs.git
            pkgs.jq
            pkgs.llvm_15
            pkgs.lld_15
            pkgs.llvmPackages_15.clang-unwrapped
            pkgs.stdenv.cc.cc.lib
            # RDMA/InfiniBand libraries for CUDA packages
            pkgs.rdma-core
            # Fontconfig needed at runtime by Qt (PyQt/qasync) for font discovery
            pkgs.fontconfig
            # zstd needed for Qt plugin compression support (provides libzstd.so.1)
            pkgs.zstd
            # Qt Declarative (QML) modules to ensure QML2_IMPORT_PATH exists
            pkgs.qt6.qtdeclarative
            # Also include qtbase explicitly so we can probe its layout
            pkgs.qt6.qtbase
            # OpenGL libraries for non-NVIDIA (and fallback software rendering)
            pkgs.libglvnd
            pkgs.mesa
            # nixGL for NVIDIA driver access - conditionally enabled
            (nixgl-pkgs.nixGLNvidia or null)
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
            
            # Ensure virtualenv site-packages (uv2nix resolved deps like ndscan) are first on PYTHONPATH
            for sp in "${virtualenv}/lib"/python*/site-packages; do
              if [ -d "$sp" ]; then
                export PYTHONPATH="$sp:$PYTHONPATH"
              fi
            done
            
            # Add ARTIQ packages to PYTHONPATH so they're available alongside uv2nix packages
            export PYTHONPATH="${editablePythonSet.artiq}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.migen}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.misoc}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.asyncserial}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.microscope}/${python.sitePackages}:$PYTHONPATH"
            export PYTHONPATH="${editablePythonSet.sipyco}/${python.sitePackages}:$PYTHONPATH"
            # Ensure llvmlite (from nixpkgs) is on PYTHONPATH for ARTIQ JIT components
            if [ -d "${python.pkgs.llvmlite}/${python.sitePackages}" ]; then
              export PYTHONPATH="${python.pkgs.llvmlite}/${python.sitePackages}:$PYTHONPATH"
            fi
            # Dynamically add pythonparser (needed by ARTIQ core compiler) if present in ARTIQ store closure
            if command -v artiq_run >/dev/null 2>&1; then
              _ARTIQ_BIN=$(command -v artiq_run)
              _ARTIQ_ROOT=$(dirname $(dirname "$_ARTIQ_BIN"))
              for sp in "$_ARTIQ_ROOT"/lib/python*/site-packages; do
                if [ -d "$sp/pythonparser" ]; then
                  export PYTHONPATH="$sp:$PYTHONPATH"
                  break
                fi
              done
            fi
            
            # Provide wheel runtime libs for PyQt6/qasync
            ZSTD_LIB="${pkgs.zstd.out or pkgs.zstd}/lib"
            if [ ! -e "$ZSTD_LIB/libzstd.so.1" ]; then
              ZSTD_LIB=$(dirname $(fd -a libzstd.so.1 ${pkgs.zstd} 2>/dev/null | head -n1 || true))
            fi
            export LD_LIBRARY_PATH="${pkgs.fontconfig.lib or pkgs.fontconfig}/lib:${pkgs.zstd.lib or pkgs.zstd}/lib:${pkgs.freetype.out}/lib:${pkgs.libpng}/lib:${pkgs.libjpeg}/lib:${pkgs.dbus.lib or pkgs.dbus}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.rdma-core}/lib:$ZSTD_LIB:${pkgs.glib.out}/lib:${pkgs.libxkbcommon}/lib:${pkgs.alsa-lib}/lib:${pkgs.xorg.libX11}/lib:${pkgs.xorg.libXext}/lib:${pkgs.xorg.libXrender}/lib:${pkgs.xorg.libxcb}/lib:${pkgs.xorg.libXi}/lib:${pkgs.xorg.libXfixes}/lib:${pkgs.xorg.libXcursor}/lib:${pkgs.xorg.libXrandr}/lib:${pkgs.xorg.libXdamage}/lib:${pkgs.xorg.libXcomposite}/lib:${pkgs.xorg.libXau}/lib:${pkgs.xorg.libXdmcp}/lib:${pkgs.xorg.libXtst}/lib:${pkgs.libglvnd}/lib:${pkgs.mesa}/lib:$LD_LIBRARY_PATH"
            # Provide DRI drivers for Mesa (software / non-NVIDIA rendering)
            if [ -d "${pkgs.mesa}/lib/dri" ]; then
              export LIBGL_DRIVERS_PATH="${pkgs.mesa}/lib/dri"
            fi

            # Ensure QML2_IMPORT_PATH points to an existing directory; probe common qt6 locations if unset/invalid
            # Build QML2_IMPORT_PATH from all existing candidate directories (first element previously set may not exist)
            CANDIDATE_QML_DIRS="${pkgs.qt6.qtdeclarative}/lib/qt6/qml ${pkgs.qt6.qtdeclarative}/lib/qt-6/qml ${pkgs.qt6.qtdeclarative}/share/qt6/qml ${pkgs.qt6.qtdeclarative}/share/qt/qml ${pkgs.qt6.qtbase}/lib/qt6/qml ${pkgs.qt6.qtbase}/lib/qt-6/qml ${pkgs.qt6.qtbase}/share/qt6/qml ${pkgs.qt6.qtbase}/share/qt/qml"
            # Also probe inside the PyQt6 wheel (structure varies)
            if [ -d "$VIRTUAL_ENV" ]; then
              for wheelDir in "$(echo $VIRTUAL_ENV)/lib"/python*/site-packages/PyQt6/Qt6/qml; do
                if [ -d "$wheelDir" ]; then
                  CANDIDATE_QML_DIRS="$CANDIDATE_QML_DIRS $wheelDir"
                fi
              done
            fi
            NEW_QML_PATHS=""
            for d in $CANDIDATE_QML_DIRS; do
              if [ -d "$d" ]; then
                if [ -z "$NEW_QML_PATHS" ]; then NEW_QML_PATHS="$d"; else NEW_QML_PATHS="$NEW_QML_PATHS:$d"; fi
              fi
            done
            # Prefer detected directories; fall back to existing value only if it exists
            if [ -n "$NEW_QML_PATHS" ]; then
              export QML2_IMPORT_PATH="$NEW_QML_PATHS"
            elif [ -n "$QML2_IMPORT_PATH" ]; then
              first_qml_dir=$(printf '%s' "$QML2_IMPORT_PATH" | cut -d: -f1)
              if [ ! -d "$first_qml_dir" ]; then
                unset QML2_IMPORT_PATH
              fi
            fi
            
            # CUDA environment setup
            export CUDA_PATH=/usr/local/cuda
            export PATH=$CUDA_PATH/bin:$PATH
            export LD_LIBRARY_PATH=$CUDA_PATH/lib64:$LD_LIBRARY_PATH
            
            # Auto-detect NVIDIA GPU and set up nixGL aliases
            ${if nixgl-pkgs ? nixGLNvidia then ''
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
            '' else ''
              # nixGL not available - use CPU-only mode
              NIXGL_BIN=""
              GPU_TYPE="CPU-only (nixGL unavailable)"
            ''}
            
            # Add ARTIQ store executables first
            export PATH="${editablePythonSet.artiq}/bin:$PATH"

            # Create wrapper scripts ensuring ARTIQ frontends execute with the dev virtualenv python
            DEV_BIN="$REPO_ROOT/.dev-bin"
            mkdir -p "$DEV_BIN"
            FRONTENDS="artiq_run artiq_master artiq_dashboard artiq_client artiq_controller artiq_rpctool"
            for fe in $FRONTENDS; do
              case "$fe" in
                artiq_run)        mod="artiq.frontend.artiq_run" ;;
                artiq_master)     mod="artiq.frontend.artiq_master" ;;
                artiq_dashboard)  mod="artiq.frontend.artiq_dashboard" ;;
                artiq_client)     mod="artiq.frontend.artiq_client" ;;
                artiq_controller) mod="artiq.frontend.artiq_controller" ;;
                artiq_rpctool)    mod="artiq.frontend.artiq_rpctool" ;;
                *) mod="artiq.frontend.$fe" ;;
              esac
              wrapper="$DEV_BIN/$fe"
              # Regenerate if missing or pointing to older virtualenv
              if [ ! -f "$wrapper" ] || ! grep -q "${virtualenv}" "$wrapper"; then
                cat > "$wrapper" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

# Auto-detect nixGL wrapper if not already exported and available.
if [ -z "''${NIXGL_BIN:-}" ]; then
  if command -v nixGL >/dev/null 2>&1; then
    NIXGL_BIN=$(command -v nixGL)
  elif command -v nixGLNvidia >/dev/null 2>&1; then
    NIXGL_BIN=$(command -v nixGLNvidia)
  elif command -v nixGLIntel >/dev/null 2>&1; then
    NIXGL_BIN=$(command -v nixGLIntel)
  fi
fi

if [ -n "''${NIXGL_BIN:-}" ]; then
  exec "''${NIXGL_BIN}" VENV_PY_PLACEHOLDER -m MOD_PLACEHOLDER "$@"
else
  exec VENV_PY_PLACEHOLDER -m MOD_PLACEHOLDER "$@"
fi
EOF
                # Substitute placeholders (avoid variable expansion issues in heredoc)
                sed -i "s|MOD_PLACEHOLDER|$mod|g" "$wrapper"
                sed -i "s|VENV_PY_PLACEHOLDER|${virtualenv}/bin/python|g" "$wrapper"
                chmod +x "$wrapper"
              fi
            done
            # Prepend wrapper directory so it overrides store binaries
            export PATH="$DEV_BIN:$PATH"

            # Optional detailed GPU/CUDA probe (disable with CUDA_PROBE=0)
            if [ "''${CUDA_PROBE:-1}" = "1" ]; then
              echo "[GPU Probe] Starting CUDA/Torch diagnostics..."
              # Basic NVIDIA presence info
              if command -v nvidia-smi >/dev/null 2>&1; then
                echo "[GPU Probe] nvidia-smi detected; summary:"
                nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/[GPU]/'
              else
                echo "[GPU Probe] nvidia-smi not found (driver or PATH missing)"
              fi
              if [ -e /proc/driver/nvidia/version ]; then
                echo "[GPU Probe] /proc/driver/nvidia/version: $(head -n1 /proc/driver/nvidia/version)"
              fi
              # Torch probe
              python <<'PY' 2>/dev/null || true
import os, ctypes, json, textwrap
report = {}
try:
    import torch
    report['torch_version'] = torch.__version__
    report['compiled_cuda'] = getattr(torch.version, 'cuda', None)
    avail = torch.cuda.is_available()
    report['cuda_available'] = avail
    if avail:
        report['device_count'] = torch.cuda.device_count()
        names = []
        for i in range(torch.cuda.device_count()):
            try:
                names.append(torch.cuda.get_device_name(i))
            except Exception as e: # still list placeholder
                names.append(f"<error:{e}>")
        report['device_names'] = names
    else:
        # Attempt to load libcuda to distinguish missing driver vs torch mismatch
        try:
            ctypes.CDLL('libcuda.so.1')
            report['libcuda'] = 'found (Torch still reports unavailable)'
        except OSError as e:
            report['libcuda'] = f'missing ({e})'
except Exception as e:
    report['torch_error'] = str(e)
print('[GPU Probe] Torch summary:', json.dumps(report))
PY
              echo "[GPU Probe] Done"
            fi
            
            echo "ARTIQ Fork development environment with uv2nix (uv.lock detected)"
            echo "Using Nix-managed virtual environment at: ${virtualenv}"
            echo "Python: $(which python)"
            echo "ARTIQ: $(artiq_master --version 2>/dev/null || echo 'available')"
            echo "✅ PyTorch dev shell with nixGL ($GPU_TYPE) is ready!"
            if [ -n "$NIXGL_BIN" ]; then
              echo "💡 python3 and jupyter use GPU acceleration automatically"
            else
              echo "💡 Running in CPU-only mode"
              # (build-time GPU absence note suppressed to avoid Nix interpolation complexity)
            fi
      # Optional OpenGL probe (set OPENGL_PROBE=1 before entering shell to enable)
            if [ "''${OPENGL_PROBE:-0}" = "1" ]; then
        python - <<'PY' 2>/dev/null || true
import ctypes
try:
  ctypes.CDLL('libGL.so.1')
  print('OpenGL: libGL.so.1 loaded')
except OSError as e:
  print('OpenGL: libGL.so.1 missing ->', e)
PY
      fi
            if [ -z "$(ls ${pkgs.libglvnd}/lib/libGL.so.1 2>/dev/null)" ]; then
              echo "(diagnostic) libGL.so.1 not present in libglvnd store path: ${pkgs.libglvnd}/lib" >&2
            fi
            echo ""
            echo "To add packages:"
            echo "  uv-add <package>    - Add package and rebuild"
            echo "  uv-remove <package> - Remove package and rebuild"

            # ------------------------------------------------------------------
            # VS Code Python interpreter auto-selection
            # Creates/updates .vscode/settings.json so VS Code picks the shell's
            # current virtualenv interpreter automatically. Disable by setting
            #   export VSCODE_AUTO_PY=0
            # before entering the shell. Re-run shell to refresh after rebuilds.
            # ------------------------------------------------------------------
            if [ "''${VSCODE_AUTO_PY:-1}" = "1" ]; then
              vscode_dir="$REPO_ROOT/.vscode"
              settings_file="$vscode_dir/settings.json"
              mkdir -p "$vscode_dir"
              mode="''${VSCODE_INTERPRETER_MODE:-pin}"  # modes: pin (default), auto (clear), off
              current_real_interp="${virtualenv}/bin/python"
              settings_interp="$REPO_ROOT/.venv/bin/python"
              # Ensure stable .venv symlink exists
              if [ ! -L "$REPO_ROOT/.venv" ] || [ "$(readlink -f "$REPO_ROOT/.venv" || true)" != "${virtualenv}" ]; then
                ln -sfn "${virtualenv}" "$REPO_ROOT/.venv"
                echo "[VSCode] Linked .venv -> ${virtualenv}"
              fi
              # Helper: write minimal JSON
              write_minimal_json() {
                cat > "$settings_file" <<EOF_JSON
{
  "_nixShell.lastEnter": $(date +%s),
  "_nixShell.realInterpreter": "$current_real_interp"
}
EOF_JSON
              }
              case "$mode" in
                off)
                  echo "[VSCode] Interpreter automation disabled (mode=off)" ;;
                pin)
                  # Pin to stable .venv path
                  if command -v jq >/dev/null 2>&1 && [ -f "$settings_file" ]; then
                    tmpfile=$(mktemp)
                    if jq --arg p "$settings_interp" --arg real "$current_real_interp" --arg ts "$(date +%s)" '."python.defaultInterpreterPath" = $p | ."python.pythonPath" = $p | ."_nixShell.lastEnter" = ($ts|tonumber) | ."_nixShell.realInterpreter" = $real' "$settings_file" > "$tmpfile" 2>/dev/null; then
                      mv "$tmpfile" "$settings_file"
                      echo "[VSCode] Pinned interpreter -> $settings_interp"
                    else
                      echo "[VSCode] jq update failed; leaving settings.json unchanged" >&2
                      rm -f "$tmpfile"
                    fi
                  else
                    cat > "$settings_file" <<EOF_JSON
{
  "python.defaultInterpreterPath": "$settings_interp",
  "python.pythonPath": "$settings_interp",
  "_nixShell.realInterpreter": "$current_real_interp",
  "_nixShell.lastEnter": $(date +%s)
}
EOF_JSON
                    echo "[VSCode] Created pinned interpreter settings"
                  fi
                  ;;
                auto|*)
                  # Clear any interpreter keys so VS Code auto-detects .venv
                  if [ -f "$settings_file" ]; then
                    if command -v jq >/dev/null 2>&1; then
                      tmpfile=$(mktemp)
                      if jq 'del(."python.defaultInterpreterPath", ."python.pythonPath")' "$settings_file" > "$tmpfile" 2>/dev/null; then
                        mv "$tmpfile" "$settings_file"
                        echo "[VSCode] Cleared python.* interpreter keys (auto mode)"
                      else
                        echo "[VSCode] jq deletion failed; backing up & rewriting minimal settings" >&2
                        cp "$settings_file" "$settings_file.bak.$(date +%s)"
                        write_minimal_json
                      fi
                    else
                      # Fallback sed removal (may leave trailing commas)
                      cp "$settings_file" "$settings_file.bak.$(date +%s)"
                      sed -i '/python.defaultInterpreterPath/d;/python.pythonPath/d' "$settings_file" || true
                      echo "[VSCode] Attempted plain text removal of interpreter keys (jq missing)"
                    fi
                  else
                    write_minimal_json
                    echo "[VSCode] Created settings.json (no interpreter keys; auto mode)"
                  fi
                  ;;
              esac
            fi
          '';
        }
      else
        # When no uv.lock exists, throw an error
        throw "No uv.lock file detected. Please run 'uv lock' to generate the lock file, then try 'nix develop --impure' again.";
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