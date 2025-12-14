#!/usr/bin/env bash
#
# install_docker_ubuntu.sh
# Installs Docker Engine, CLI, containerd, and Docker Compose plugin on Ubuntu.
# Compatible with Ubuntu 20.04, 22.04, and 24.04.

set -e

echo ">>> [1/3] Removing old Docker versions (if any)..."
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

echo ">>> [2/3] Setting up Docker APT repository..."
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings

if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
fi

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo ">>> [3/3] Installing Docker Engine, CLI, and Compose plugin..."
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo ">>> Docker installed successfully!"
docker --version
docker compose version

echo ">>> To run Docker as non-root user, execute:"
echo "    sudo usermod -aG docker \$USER && newgrp docker"
echo ">>> Done."