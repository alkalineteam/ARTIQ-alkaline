{
  description = "ARTIQ alkaline fork with custom Python packages";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        # Python environment with ARTIQ dependencies
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          # Core ARTIQ dependencies
          numpy
          scipy
          matplotlib
          h5py
          dateutil
          prettytable
          msgpack
          asyncserial
          pyserial
          levenshtein
          pyqt5
          qasync
          sipyco
          jsonschema
          file-magic
          
          # Development tools
          setuptools
          wheel
          pip
          
          # Add your custom packages here
          # Example:
          # requests
          # pandas
          # jupyter
        ]);

        # ARTIQ alkaline fork
        artiq-alkaline = pkgs.python3Packages.buildPythonPackage rec {
          pname = "artiq";
          version = "alkaline-fork";
          
          src = pkgs.fetchFromGitHub {
            owner = "alkalineteam";
            repo = "ARTIQ-alkaline-fork";
            rev = "master"; # or specify a specific commit/tag
            sha256 = ""; # You'll need to update this hash
          };

          nativeBuildInputs = with pkgs; [
            llvm_14
            pkg-config
          ];

          buildInputs = with pkgs; [
            llvm_14
            libffi
            zlib
          ];

          propagatedBuildInputs = with pkgs.python3Packages; [
            numpy
            scipy
            matplotlib
            h5py
            dateutil
            prettytable
            msgpack
            asyncserial
            pyserial
            levenshtein
            pyqt5
            qasync
            sipyco
            jsonschema
            file-magic
          ];

          # Skip tests for now as they might require hardware
          doCheck = false;

          meta = with pkgs.lib; {
            description = "ARTIQ alkaline fork";
            homepage = "https://github.com/alkalineteam/ARTIQ-alkaline-fork";
            license = licenses.lgpl3Plus;
          };
        };

      in
      {
        packages = {
          default = artiq-alkaline;
          artiq = artiq-alkaline;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            pythonEnv
            artiq-alkaline
            
            # Development tools
            git
            llvm_14
            pkg-config
            
            # Optional: GUI support
            qt5.full
            libGL
            xorg.libX11
            xorg.libXext
          ];

          shellHook = ''
            echo "ARTIQ alkaline fork development environment"
            echo "Python: $(python --version)"
            echo "ARTIQ version: $(python -c 'import artiq; print(artiq.__version__)' 2>/dev/null || echo 'Not installed yet')"
            
            # Set environment variables for GUI applications
            export QT_QPA_PLATFORM_PLUGIN_PATH="${pkgs.qt5.qtbase.bin}/lib/qt-${pkgs.qt5.qtbase.version}/plugins"
            export PYTHONPATH="$PWD:$PYTHONPATH"
          '';
        };

        # Alternative shell with additional Python packages
        devShells.extended = pkgs.mkShell {
          buildInputs = with pkgs; [
            (python3.withPackages (ps: with ps; [
              # All the base packages
              numpy scipy matplotlib h5py dateutil prettytable
              msgpack asyncserial pyserial levenshtein pyqt5 qasync
              sipyco jsonschema file-magic setuptools wheel pip
              
              # Extended packages - add yours here
              requests
              pandas
              jupyter
              ipython
              plotly
              seaborn
              scikit-learn
              # Add more packages as needed
            ]))
            artiq-alkaline
            git
            llvm_14
            pkg-config
            qt5.full
            libGL
            xorg.libX11
            xorg.libXext
          ];

          shellHook = ''
            echo "ARTIQ alkaline fork extended development environment"
            echo "Python: $(python --version)"
            echo "Additional packages: pandas, jupyter, plotly, scikit-learn, etc."
            
            export QT_QPA_PLATFORM_PLUGIN_PATH="${pkgs.qt5.qtbase.bin}/lib/qt-${pkgs.qt5.qtbase.version}/plugins"
            export PYTHONPATH="$PWD:$PYTHONPATH"
          '';
        };
      });
}