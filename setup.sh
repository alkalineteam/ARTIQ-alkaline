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

# Install Nix (daemon mode)
if ! command -v nix &> /dev/null; then
    echo "📦 Installing Nix..."
    sh <(curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install) --daemon
else
    echo "✅ Nix already installed"
fi

# Ensure config directory exists
mkdir -p ~/.config/nix

# Add experimental features + sandbox paths
NIX_CONF=~/.config/nix/nix.conf
echo "⚙️  Configuring $NIX_CONF ..."

# Add only if not already present
grep -qxF "experimental-features = nix-command flakes" "$NIX_CONF" 2>/dev/null || \
echo "experimental-features = nix-command flakes" >> "$NIX_CONF"

grep -qxF "extra-sandbox-paths = /opt" "$NIX_CONF" 2>/dev/null || \
echo "extra-sandbox-paths = /opt" >> "$NIX_CONF"

echo "✅ Setup complete. You may need to restart your shell (or log out/in) for Nix to work."
