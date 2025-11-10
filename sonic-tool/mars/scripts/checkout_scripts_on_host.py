#!/usr/bin/env python
"""
Checkout the sonic-mgmt git repository in the host

This script is executed on the STM node. It establishes SSH connection to the host (Player) and
run commands on it. Purpose is to checkout the sonic-mgmt repository in the host(hypervisor or sonic_mgmt or etc.).
"""

# Builtin libs
import argparse
import os
import re

# Third-party libs
from fabric import Config
from fabric import Connection
from invoke.exceptions import ThreadException
from retry import retry

# Home-brew libs
from lib import constants
from lib.utils import parse_topology, get_logger

logger = get_logger("CheckoutOnSonicMgmt")


def _parse_args():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--topo", dest="topo", help="Path to the MARS topology configuration file")
    parser.add_argument("--tarball", dest="tarball", help="Path to the tarball file")
    parser.add_argument("--workspace-path", dest="workspace_path",
                        help="Specify the location to checkout sonic-mgmt repo")
    parser.add_argument("--host_name", dest="host_name", help="Host on which git actions should be executed, host name"
                                                              "the same as in MARS topology file")
    parser.add_argument("--tarball_path", dest="tarball_path", help="Tarballs directory",
                        default="/auto/sw_regression/system/SONIC/MARS/tarballs/")
    return parser.parse_args()


@retry(ThreadException, tries=3, delay=10)
def main():

    args = _parse_args()

    tarball_shared_path = args.tarball_path
    tarball_path = os.path.join(tarball_shared_path, args.tarball)
    workspace_path = args.workspace_path
    host_name = args.host_name if args.host_name else constants.TEST_SERVER_DEVICE_ID
    topo = parse_topology(args.topo)
    host_device = topo.get_device_by_topology_id(host_name)
    host_device_username, host_device_password = topo.get_user_access(host_device.USERS[0])
    host_ssh_port = getattr(host_device, "PORT", 22)
    host = Connection(host_device.BASE_IP, port=host_ssh_port, user=host_device_username,
                      config=Config(overrides={"run": {"echo": True}}),
                      connect_kwargs={"password": host_device_password})

    logger.info("Check if {} exists ".format(workspace_path))
    if host.run("test -d {}".format(workspace_path), warn=True).ok:
        logger.info("Folder {} exists. Delete it firstly.".format(workspace_path))
        host.run("rm -rf {}".format(workspace_path))

    logger.info("Prepare workspace {}".format(workspace_path))
    logger.info("Create workspace folder {}".format(workspace_path))
    host.run("mkdir -p {}".format(workspace_path))

    logger.info("Extract tarball {} into workspace folder {}".format(tarball_path, workspace_path))
    host.run("tar -xvf {} -C {}".format(tarball_path, workspace_path))

    logger.info("Tarball extraction completed successfully.")


if __name__ == "__main__":
    main()
