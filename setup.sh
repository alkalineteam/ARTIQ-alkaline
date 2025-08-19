#!/usr/bin/env bash
set -euo pipefail

# Install curl if not present
if ! command -v curl &> /dev/null; then
    echo "📦 Installing curl..."
    sudo apt update
    sudo apt install -y curl
else
    echo "✅ curl already installed"
fi

#Install Nix
if ! command -v nix &> /dev/null; then
    echo "📦 Installing Nix..."
    sh <(curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install) --daemon
else
    echo "✅ Nix already installed"
fi

# Ensure config directory exists
mkdir -p ~/.config/nix
mkdir -p ~/.config/nixpkgs

# Add experimental features + sandbox paths
NIX_CONF1=~/.config/nix/nix.conf
NIX_CONF2=~/.config/nixpkgs/config.nix
echo "⚙️  Configuring $NIX_CONF1 & $NIX_CONF2"

# Add only if not already present
grep -qxF "experimental-features = nix-command flakes" "$NIX_CONF1" 2>/dev/null || \
echo "experimental-features = nix-command flakes" >> "$NIX_CONF1"

grep -qxF "extra-sandbox-paths = /opt" "$NIX_CONF1" 2>/dev/null || \
echo "extra-sandbox-paths = /opt" >> "$NIX_CONF1"

grep -qxF "{ allowUnfree = true; }" "$NIX_CONF2" 2>/dev/null || \
echo "{ allowUnfree = true; }" >> "$NIX_CONF2"

echo "✅ Setup complete. You will need to restart your shell for everything to work."
