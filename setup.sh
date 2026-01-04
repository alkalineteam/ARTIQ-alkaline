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

sudo chmod +x fix-hashes.sh

# Docker Installation Check
if ! command -v docker &> /dev/null; then
    echo "📦 Docker is Installing..."
    
    # Add Docker's official GPG key:
    sudo apt update
    sudo apt install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    # Add the repository to Apt sources:
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null

    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    echo "✅ Docker installed successfully."
else
    echo "✅ Docker available."
fi

# Add user to docker group if not already added
if ! groups $USER | grep &>/dev/null 'docker'; then
  echo "👤 Adding $USER to docker group..."
  sudo usermod -aG docker $USER
fi

echo "✅ Setup complete. You will need to RESTART YOUR SESSION (logout/login) for docker permissions to apply."
