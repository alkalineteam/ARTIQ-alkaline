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
      inherit (artiq.packages.${system}) vivadoEnv vivado openocd-bscanspi;
    };

    devShells.${system} = {
      # Default development shell - always provides minimal ARTIQ environment
      default = pkgs.mkShell {
        name = "artiq-fork-minimal-shell";
        packages = [
          (python.withPackages (_: [artiq.packages.${system}.artiq]))
          pkgs.uv
          pkgs.git
        ] ++ (with artiq.packages.${system}; [
          vivadoEnv
          vivado  
          openocd-bscanspi
        ]);
        
        shellHook = ''
          echo "Minimal ARTIQ environment"
          echo "ARTIQ: $(artiq_master --version 2>/dev/null || echo 'available')"
          echo "Ready for uv package management and basic ARTIQ functionality"
          echo ""
          echo "Available shells:"
          echo "  nix develop .#minimal     - This minimal environment"  
          echo "  nix develop .#full-stack  - Full uv2nix environment (requires uv.lock)"
        '';
      };

      # Full-stack development shell with uv2nix integration
      full-stack = if workspace != null then
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
            # Include essential ARTIQ development tools
            pkgs.git
            pkgs.llvm_15
            pkgs.lld_15
            pkgs.llvmPackages_15.clang-unwrapped
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
            
            # Add ARTIQ executables to PATH
            export PATH="${editablePythonSet.artiq}/bin:$PATH"
            
            echo "ARTIQ Fork development environment with uv2nix"
            echo "Using Nix-managed virtual environment at: ${virtualenv}" 
            echo "Python: $(which python)"
            echo "ARTIQ: $(artiq_master --version 2>/dev/null || echo 'available')"
            echo ""
            echo "To add packages:"
            echo "  1. Run 'uv add <package>' to update pyproject.toml and uv.lock"
            echo "  2. Run 'nix develop' again to rebuild with new packages"
          '';
        }
      else
        # When no uv.lock exists, show warning and fall back to minimal shell
        self.devShells.${system}.minimal.overrideAttrs (old: {
          name = "artiq-fork-full-stack-fallback";
          shellHook = ''
            echo "WARNING: No uv.lock file detected!"
            echo "Cannot create full-stack environment without uv.lock file."
            echo ""
            echo "To create uv.lock file:"
            echo "  1. Run 'uv lock' to generate uv.lock from pyproject.toml"
            echo "  2. Run 'nix develop .#full-stack' again"
            echo ""
            echo "Falling back to minimal environment..."
            echo ""
          '' + old.shellHook;
        });

      # Alias for the minimal shell for backward compatibility and explicit access
      minimal = self.devShells.${system}.default;
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