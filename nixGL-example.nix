{
  description = "nixGL";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixgl.url   = "github:nix-community/nixGL";
  };

  outputs = { self, nixpkgs, nixgl }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      config.allowUnfree = true;
    };
  in {
    devShells.${system}.default = pkgs.mkShell {
      packages = [
        pkgs.python313
      ];

      # Enable GPU OpenGL wrappers
      nativeBuildInputs = [ 
        nixgl.packages.${system}.nixGLNvidia 
      ];

      shellHook = ''
        export CUDA_PATH=/usr/local/cuda
        export PATH=$CUDA_PATH/bin:$PATH
        export LD_LIBRARY_PATH=$CUDA_PATH/lib64:$LD_LIBRARY_PATH

        # Auto-detect GPU and set appropriate nixGL
        if lspci | grep -i nvidia > /dev/null; then
          NIXGL_BIN=$(find ${nixgl.packages.${system}.nixGLNvidia}/bin -name "nixGLNvidia-*" | head -n1)
          GPU_TYPE="NVIDIA"
        elif lspci | grep -i intel > /dev/null; then
          NIXGL_BIN=$(find ${nixgl.packages.${system}.nixGLIntel}/bin -name "nixGLIntel-*" | head -n1)
          GPU_TYPE="Intel"
        else
          NIXGL_BIN=""
          GPU_TYPE="CPU-only"
        fi
        
        if [ -n "$NIXGL_BIN" ]; then
          alias python3="$NIXGL_BIN python3"
          alias jupyter="$NIXGL_BIN jupyter"
        fi
        
        echo "✅ PyTorch dev shell with nixGL ($GPU_TYPE) is ready!"
        echo "💡 python3 and jupyter use GPU acceleration when available"
      '';
    };
  };
}
