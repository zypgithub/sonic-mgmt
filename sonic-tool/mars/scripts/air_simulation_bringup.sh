#!/bin/bash

source /opt/rh/rh-python38/enable
PATH=/opt/rh/rh-python38/root/usr/bin:${PATH}

# Install pip if not present
python3 -m ensurepip --default-pip 2>/dev/null || true

# Clear PYTHONPATH to avoid conflicts with /opt/ver_sdk Python 2.7 packages
unset PYTHONPATH

pip3 install --upgrade pip
pip3 install --ignore-installed "devts@git+https://svc_sonic_ver_bot:${GERRIT_API_KEY}@git-nbu-sw.nvidia.com/r/a/devts@master"
# to solve the issue of openssl and urllib3 version compatibility
pip3 install "requests<2.32.0" "urllib3<2"

python3 -m scripts.air_simulation_bringup "$@"
