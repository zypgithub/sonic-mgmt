#!/usr/bin/env python
"""
Update configuration files inside sonic-mgmt repo with entries for new setups obtained from Noga.

This script is executed on the STM node. It establishes SSH connection to the test server and
run command on it. It uses the following script - 'sonic-tool/sonic_ngts/scripts/update_sonic_mgmt.py'
"""

import argparse
import os

from fabric import Config
from fabric import Connection

from lib import constants
from lib.utils import parse_topology, get_logger

logger = get_logger("TuneConfigs")


def _parse_args():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--topo", dest="topo", help="Path to the MARS topology configuration file")
    parser.add_argument("--dut-name", required=True, dest="dut_name", help="The DUT name")
    parser.add_argument("--workspace-path", dest="workspace_path",
                        help="Specify the location of sonic-mgmt repo on sonic-mgmt docker container.")
    return parser.parse_args()


if __name__ == "__main__":
    logger.info("Update sonic-mgmt inventory files with new setup info to be able to run image deploy")

    args = _parse_args()

    workspace_path = args.workspace_path
    sonic_mgmt_repo_name = "sonic-mgmt"
    sonic_tool_repo_name = "sonic-tool"
    sonic_mgmt_repo_path = os.path.join(workspace_path, sonic_mgmt_repo_name)
    sonic_tool_repo_path = os.path.join(workspace_path, sonic_tool_repo_name)

    topo_file = args.topo
    topo_obj = parse_topology(topo_file)

    setup_name = topo_file.split('/')[-2]

    sonic_mgmt_container_info = topo_obj.get_device_by_topology_id(constants.SONIC_MGMT_DEVICE_ID)
    sonic_mgmt_device_username, sonic_mgmt_device_password = topo_obj.get_user_access(sonic_mgmt_container_info.USERS[0])
    print('sonic_mgmt_repo_path : {}'.format(sonic_mgmt_repo_path))

    # Collecting dictionary containing current env variables to apply them for following connection
    env_dict = {key: f'"{value}"' for key, value in dict(os.environ).items()}
    sonic_mgmt_container = Connection(sonic_mgmt_container_info.BASE_IP,
                                      user=sonic_mgmt_device_username,
                                      config=Config(overrides={"run": {"echo": True, "env": env_dict}}),
                                      connect_kwargs={"password": sonic_mgmt_device_password},
                                      inline_ssh_env=True)
    update_sonic_mgmt_script_path = f'{sonic_mgmt_repo_path}/sonic-tool/sonic_ngts/scripts/update_sonic_mgmt.py'
    cmd = f'PYTHONPATH=/devts/ {constants.NGTS_PATH_PYTHON} {update_sonic_mgmt_script_path} --dut="{args.dut_name}" ' \
          f'--mgmt_repo="{sonic_mgmt_repo_path}" --setup_name="{setup_name}"'

    sonic_mgmt_container.run(cmd)
