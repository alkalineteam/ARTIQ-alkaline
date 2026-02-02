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

# Configure system-level Nix for GPU auto-detection
# This allows nixGL to read /proc/driver/nvidia/version during builds
SYSTEM_NIX_CONF="/etc/nix/nix.conf"
if [ -f "$SYSTEM_NIX_CONF" ]; then
    echo "⚙️  Configuring GPU auto-detection in $SYSTEM_NIX_CONF"
    
    # Add sandbox path for NVIDIA driver detection
    if ! grep -q "extra-sandbox-paths.*=/proc/driver/nvidia" "$SYSTEM_NIX_CONF" 2>/dev/null; then
        echo "   Adding /proc/driver/nvidia to sandbox-paths..."
        echo "extra-sandbox-paths = /proc/driver/nvidia" | sudo tee -a "$SYSTEM_NIX_CONF" > /dev/null
    fi
    
    # Add current user to trusted-users
    if ! grep -q "trusted-users.*$USER" "$SYSTEM_NIX_CONF" 2>/dev/null; then
        echo "   Adding $USER to trusted-users..."
        if grep -q "^trusted-users" "$SYSTEM_NIX_CONF"; then
            # Append to existing trusted-users line
            sudo sed -i "s/^trusted-users.*/& $USER/" "$SYSTEM_NIX_CONF"
        else
            echo "trusted-users = $USER" | sudo tee -a "$SYSTEM_NIX_CONF" > /dev/null
        fi
    fi
    
    # Restart nix-daemon to apply changes
    echo "   Restarting nix-daemon..."
    sudo systemctl restart nix-daemon || echo "   Warning: Failed to restart nix-daemon"
    echo "✅ GPU auto-detection configured"
else
    echo "⚠️  $SYSTEM_NIX_CONF not found - GPU auto-detection may require manual configuration"
fi

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
    echo "Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc" | \
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
