#!/bin/bash

pip3 install --ignore-installed "devts@git+https://svc_sonic_ver_bot:${GERRIT_API_KEY}@git-nbu-sw.nvidia.com/r/a/devts@master"
python3 -m scripts.air_simulation_bringup "$@"
