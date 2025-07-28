{
  description = "ARTIQ from alkaline fork with uv2nix dependency management";
  
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    
    # uv2nix for Python dependency management
    uv2nix = {
      url = "github:adisbladis/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    
    # Rust overlay for specific Rust version
    rust-overlay = {
      url = "github:oxalica/rust-overlay?ref=snapshot/2024-08-01";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    
    # Your ARTIQ fork
    artiq-src = {
      url = "github:alkalineteam/ARTIQ-alkaline-fork/master";
      #flake = false;
      inputs.nixpkgs.follows = "nixpkgs";
    };
    
    # ARTIQ dependencies
    sipyco = {
      url = "github:m-labs/sipyco";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    
    pythonparser-src = {
      url = "github:m-labs/pythonparser";
      flake = false;
    };
    
    artiq-comtools = {
      url = "github:m-labs/artiq-comtools";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.sipyco.follows = "sipyco";
    };
    
    migen-src = {
      url = "github:m-labs/migen";
      flake = false;
    };
    
    misoc-src = {
      type = "git";
      url = "https://github.com/m-labs/misoc.git";
      submodules = true;
      flake = false;
    };
  };
  
  outputs = { self, nixpkgs, flake-utils, uv2nix, rust-overlay, artiq-src, sipyco, pythonparser-src, artiq-comtools, migen-src, misoc-src }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ (import rust-overlay) ];
        };
        
        lib = nixpkgs.lib;
        python = pkgs.python313;
        
        # ARTIQ version info
        artiqVersionMajor = 9;
        artiqVersionMinor = self.sourceInfo.revCount or 0;
        artiqVersionId = self.sourceInfo.shortRev or "unknown";
        artiqVersion = "${toString artiqVersionMajor}.${toString artiqVersionMinor}+${artiqVersionId}";
        artiqRev = self.sourceInfo.rev or "unknown";
        
        # Rust toolchain for ARTIQ
        rust = pkgs.rust-bin.nightly."2021-09-01".default.override {
          extensions = [ "rust-src" ];
          targets = [ ];
        };
        
        rustPlatform = pkgs.makeRustPlatform {
          rustc = rust;
          cargo = rust;
        };
        
        # Build pythonparser
        pythonparser = python.pkgs.buildPythonPackage {
          pname = "pythonparser";
          version = "1.4";
          src = pythonparser-src;
          pyproject = true;
          
          build-system = with python.pkgs; [
            setuptools
            wheel
          ];
          
          dependencies = with python.pkgs; [ regex ];
          doCheck = false;
        };
        
        # Build qasync
        qasync = python.pkgs.buildPythonPackage rec {
          pname = "qasync";
          version = "0.27.1";
          format = "pyproject";
          
          src = pkgs.fetchFromGitHub {
            owner = "CabbageDevelopment";
            repo = "qasync";
            rev = "refs/tags/v${version}";
            sha256 = "sha256-oXzwilhJ1PhodQpOZjnV9gFuoDy/zXWva9LhhK3T00g=";
          };
          
          postPatch = ''
            rm -f qasync/_windows.py
          '';
          
          build-system = [ python.pkgs.poetry-core ];
          dependencies = [ python.pkgs.pyqt6 ];
          
          pythonImportsCheck = [ "qasync" ];
          doCheck = false;
        };
        
        # Build llvmlite for ARTIQ
        llvmlite-artiq = python.pkgs.buildPythonPackage rec {
          pname = "llvmlite";
          version = "0.43.0";
          pyproject = true;
          
          src = pkgs.fetchFromGitHub {
            owner = "numba";
            repo = "llvmlite";
            rev = "v${version}";
            sha256 = "sha256-5QBSRDb28Bui9IOhGofj+c7Rk7J5fNv5nPksEPY/O5o=";
          };
          
          build-system = with python.pkgs; [
            setuptools
            wheel
          ];
          
          nativeBuildInputs = [ pkgs.llvm_15 ];
          
          postPatch = ''
            substituteInPlace ffi/Makefile.linux --replace "-static-libstdc++" ""
            substituteInPlace llvmlite/tests/test_binding.py --replace "test_linux" "nope"
          '';
          
          preConfigure = ''
            export LLVM_CONFIG=${pkgs.llvm_15.dev}/bin/llvm-config
          '';
          
          # Disable cmake configure
          dontUseCmakeConfigure = true;
        };
        
        # Build migen
        migen = python.pkgs.buildPythonPackage rec {
          pname = "migen";
          version = "git";
          src = migen-src;
          format = "pyproject";
          
          nativeBuildInputs = [ python.pkgs.setuptools ];
          propagatedBuildInputs = [ python.pkgs.colorama ];
        };
        
        # Build asyncserial
        asyncserial = python.pkgs.buildPythonPackage rec {
          pname = "asyncserial";
          version = "1.0";
          pyproject = true;
          
          src = pkgs.fetchFromGitHub {
            owner = "m-labs";
            repo = "asyncserial";
            rev = version;
            sha256 = "sha256-ZHzgJnbsDVxVcp09LXq9JZp46+dorgdP8bAiTB59K28=";
          };
          
          build-system = with python.pkgs; [
            setuptools
            wheel
          ];
          
          dependencies = [ python.pkgs.pyserial ];
        };
        
        # Build misoc
        misoc = python.pkgs.buildPythonPackage {
          pname = "misoc";
          version = "git";
          src = misoc-src;
          pyproject = true;
          
          build-system = with python.pkgs; [
            setuptools
            wheel
          ];
          
          dependencies = with python.pkgs; [
            jinja2
            numpy
            migen
            pyserial
            asyncserial
          ];
        };
        
        # libartiq-support for tests
        libartiq-support = pkgs.stdenv.mkDerivation {
          name = "libartiq-support";
          src = artiq-src;
          buildInputs = [ rust ];
          buildPhase = ''
            rustc $src/artiq/test/libartiq_support/lib.rs -Cpanic=unwind -g
          '';
          installPhase = ''
            mkdir -p $out/lib $out/bin
            cp libartiq_support.so $out/lib
            cat > $out/bin/libartiq-support << EOF
            #!/bin/sh
            echo $out/lib/libartiq_support.so
            EOF
            chmod 755 $out/bin/libartiq-support
          '';
        };
        
        # Main ARTIQ package
        artiq = python.pkgs.buildPythonPackage rec {
          pname = "artiq";
          version = artiqVersion;
          src = artiq-src;
          pyproject = true;
          
          build-system = with python.pkgs; [
            setuptools
            setuptools-scm
            wheel
            versioneer
          ];
          
          nativeBuildInputs = [
            pkgs.qt6.wrapQtAppsHook
            pkgs.pkg-config
            pkgs.git
          ];
          
          buildInputs = [
            pkgs.llvm_15
            pkgs.lld_15
            pkgs.qt6.qtsvg
          ];
          
          dependencies = [
            # From other flakes
            sipyco.packages.${system}.sipyco
            artiq-comtools.packages.${system}.artiq-comtools
            
            # Local builds
            pythonparser
            llvmlite-artiq
            qasync
            asyncserial
            
            # From nixpkgs
            python.pkgs.pyqtgraph
            python.pkgs.pygit2
            python.pkgs.numpy
            python.pkgs.python-dateutil
            python.pkgs.scipy
            python.pkgs.prettytable
            python.pkgs.pyserial
            python.pkgs.python-Levenshtein
            python.pkgs.h5py
            python.pkgs.pyqt6
            python.pkgs.tqdm
            python.pkgs.lmdb
            python.pkgs.jsonschema
            python.pkgs.platformdirs
          ];
          
          preBuild = ''
            export VERSIONEER_OVERRIDE=${version}
            export VERSIONEER_REV=${artiqRev}
          '';
          
          dontWrapQtApps = true;
          
          postFixup = ''
            # Wrap Qt applications
            wrapQtApp "$out/bin/artiq_dashboard"
            wrapQtApp "$out/bin/artiq_browser"
            wrapQtApp "$out/bin/artiq_session"
            
            # Ensure proper environment for all ARTIQ commands
            for prog in $out/bin/artiq_*; do
              if [ -f "$prog" ] && [ ! -L "$prog" ]; then
                wrapProgram "$prog" \
                  --prefix PATH : ${lib.makeBinPath [ pkgs.llvm_15 pkgs.lld_15 ]} \
                  --run 'if [ ! -z "$NIX_PYTHONPREFIX" ]; then export PATH=$NIX_PYTHONPREFIX/bin:$PATH;fi' \
                  --set FONTCONFIG_FILE ${pkgs.fontconfig.out}/etc/fonts/fonts.conf
              fi
            done
          '';
          
          preFixup = ''
            # Use makeShellWrapper for --run support
            wrapProgram() { wrapProgramShell "$@"; }
          '';
          
          # Testing
          nativeCheckInputs = [
            pkgs.lld_15
            pkgs.llvm_15
            pkgs.lit
            pkgs.outputcheck
            pkgs.cacert
            libartiq-support
          ];
          
          # Skip tests for now as you mentioned
          doCheck = false;
          
          pythonImportsCheck = [ "artiq" ];
        };
        
        # Complete ARTIQ environment
        artiqEnv = pkgs.buildEnv {
          name = "artiq-alkaline-env";
          paths = [
            artiq
            pkgs.llvm_15
            pkgs.lld_15
            pkgs.openocd
            rust
          ];
        };
        
        # Development wrappers for ARTIQ frontend scripts
        artiq-frontend-dev-wrappers = pkgs.runCommandNoCC "artiq-frontend-dev-wrappers" {} ''
          mkdir -p $out/bin
          for program in ${artiq-src}/artiq/frontend/*.py; do
            if [ -x $program ]; then
              progname=`basename -s .py $program`
              outname=$out/bin/$progname
              echo "#!${pkgs.bash}/bin/bash" >> $outname
              echo "exec python3 -m artiq.frontend.$progname \"\$@\"" >> $outname
              chmod 755 $outname
            fi
          done
        '';
        
      in {
        packages = {
          default = artiqEnv;
          artiq = artiq;
          artiq-env = artiqEnv;
          pythonparser = pythonparser;
          llvmlite = llvmlite-artiq;
          migen = migen;
          misoc = misoc;
          asyncserial = asyncserial;
          
          # For development
          artiq-dev-wrappers = artiq-frontend-dev-wrappers;
        };
        
        devShells = {
          # Comprehensive ARTIQ development shell combining all functionality
          default = pkgs.mkShell {
            name = "artiq-complete-dev-shell";
            
            packages = [
              # Core Python with just the essential packages first
              (python.withPackages (ps: [
                # Core scientific stack that should definitely work
                ps.numpy
                ps.scipy
                ps.matplotlib
                ps.jupyter
                ps.ipython
                ps.requests
                ps.pandas
                
                # Development tools
                ps.pytest
                ps.black
                ps.flake8
                
                # Basic ARTIQ dependencies that exist in nixpkgs
                ps.pyqtgraph
                ps.python-dateutil
                ps.prettytable
                ps.pyserial
                ps.h5py
                ps.pyqt6
                ps.tqdm
                ps.lmdb
                ps.jsonschema
                ps.platformdirs
                ps.python-Levenshtein
                
                # Board development
                ps.packaging
                ps.paramiko
                ps.jinja2
                ps.colorama
              ]))
              
              # Add the custom-built packages separately
              artiq
              migen
              misoc
              pythonparser
              llvmlite-artiq
              qasync
              asyncserial
              
              # Try to add additional scientific packages if they exist
              # You can uncomment these one by one to see which ones work:
              (python.withPackages (ps: [ ps.scikit-learn ]))
              (python.withPackages (ps: [ ps.torch ]))
              (python.withPackages (ps: [ ps.pandas ]))
              (python.withPackages (ps: [ ps.matplotlib ]))
              (python.withPackages (ps: [ ps.scipy ]))
              (python.withPackages (ps: [ ps.jupyter ]))
              (python.withPackages (ps: [ ps.requests ]))
              (python.withPackages (ps: [ ps.plotly ]))
              (python.withPackages (ps: [ ps.seaborn ]))
              (python.withPackages (ps: [ ps.mypy ]))
              (python.withPackages (ps: [ ps.pygit2 ]))
              
              # Rust toolchain
              rust
              
              # LLVM/Clang tools
              pkgs.llvmPackages_15.clang-unwrapped
              pkgs.llvm_15
              pkgs.lld_15
              
              # Development tools
              pkgs.git
              pkgs.uv
              artiq-frontend-dev-wrappers
              
              # Testing tools
              pkgs.lit
              pkgs.outputcheck
              libartiq-support
              
              # Hardware tools
              pkgs.openocd
              
              # Additional useful tools
              pkgs.htop
              pkgs.tree
              pkgs.ripgrep
              pkgs.fd
            ];
            
            shellHook = ''
              echo "=== Complete ARTIQ Development Environment ==="
              echo "ARTIQ ${artiqVersion} from alkaline fork"
              echo ""
              echo "📦 Includes:"
              echo "  • Full ARTIQ development environment"
              echo "  • Board/gateware development tools"
              echo "  • Scientific Python stack (numpy, scipy, matplotlib, jupyter, etc.)"
              echo "  • Machine learning tools (scikit-learn, torch, pandas)"
              echo "  • Development tools (pytest, black, flake8, mypy)"
              echo "  • Hardware debugging (openocd)"
              echo ""
              
              # Set up environment
              export LIBARTIQ_SUPPORT=`libartiq-support`
              export QT_PLUGIN_PATH=${pkgs.qt6.qtbase}/${pkgs.qt6.qtbase.dev.qtPluginPrefix}:${pkgs.qt6.qtsvg}/${pkgs.qt6.qtbase.dev.qtPluginPrefix}
              export QML2_IMPORT_PATH=${pkgs.qt6.qtbase}/${pkgs.qt6.qtbase.dev.qtQmlPrefix}
              
              # For development, add current directory to PYTHONPATH
              if [ -d "artiq" ]; then
                export PYTHONPATH=$PWD:$PYTHONPATH
                echo "✓ Added current directory to PYTHONPATH for development"
              fi
              
              echo ""
              echo "🚀 Ready for ARTIQ development, board work, and scientific computing!"
              echo "   Try: artiq_run --version"
              echo "   Try: jupyter lab"
              echo "   Try: python -c 'import artiq; print(artiq.__version__)'"
            '';
          };
        };
        
        # Helper function to make board packages (can be extended)
        makeArtiqBoardPackage = { target, variant, experimentalFeatures ? [] }: 
          pkgs.stdenv.mkDerivation {
            name = "artiq-board-${target}-${variant}";
            # Implementation would go here
            # This is a placeholder for the board building logic
          };
      });
}