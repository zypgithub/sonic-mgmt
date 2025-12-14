#!/usr/bin/env bash
#
# load_and_up.sh
# Loads Docker images from bundle and starts all services via docker compose.
# If Docker is missing, it installs it automatically (Ubuntu only).

set -e

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ">>> Checking Docker installation..."

if ! command -v docker >/dev/null 2>&1; then
  echo ">>> Docker not found. Installing Docker Engine and Compose plugin..."

  # --- Docker installer (Ubuntu) ---
  sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
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

  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

  echo ">>> Docker successfully installed!"
else
  echo ">>> Docker is already installed."
fi

# --- Verify Compose availability ---
if ! docker compose version >/dev/null 2>&1; then
  echo ">>> Docker Compose plugin not found! Installing..."
  sudo apt-get install -y docker-compose-plugin
fi

echo ">>> Docker version: $(docker --version)"
echo ">>> Compose version: $(docker compose version)"

# --- Load local images (if any) ---
if ls "${BUNDLE_DIR}"/*.tar >/dev/null 2>&1; then
  echo ">>> Loading Docker images..."
  for tarfile in "${BUNDLE_DIR}"/*.tar; do
    echo "    -> Loading $tarfile"
    docker load -i "$tarfile"
  done
fi

# --- Bring up the services ---
echo ">>> Starting services with docker compose..."
docker compose -f "${BUNDLE_DIR}/docker-compose.yml" up -d

echo ">>> All services started successfully!"