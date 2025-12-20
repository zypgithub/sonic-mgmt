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

SONIC_MGMT_REPO_URL = "https://svc_sonic_ver_bot:${GERRIT_API_KEY}@git-nbu-sw.nvidia.com/r/a/switchx/sonic/sonic-mgmt"


def _parse_args():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--topo", dest="topo", help="Path to the MARS topology configuration file")
    parser.add_argument("--branch", dest="branch", help="Branch to checkout", required=False)
    parser.add_argument("--tarball", dest="tarball", help="Path to the tarball file")
    parser.add_argument("--workspace-path", dest="workspace_path",
                        help="Specify the location to checkout sonic-mgmt repo")
    parser.add_argument("--host_name", dest="host_name", help="Host on which git actions should be executed, host name"
                                                              "the same as in MARS topology file")
    parser.add_argument("--tarball_path", dest="tarball_path", help="Tarballs directory",
                        default="/auto/sw_regression/system/SONIC/MARS/tarballs/")

    args = parser.parse_args()

    if not args.tarball and not args.branch:
        parser.error("Checkout requires --branch or --tarball flag to be set")
    return args


@retry(ThreadException, tries=3, delay=10)
def main():

    args = _parse_args()

    workspace_path = args.workspace_path
    host_name = args.host_name if args.host_name else constants.TEST_SERVER_DEVICE_ID
    topo = parse_topology(args.topo)
    host_device = topo.get_device_by_topology_id(host_name)
    host_device_username, host_device_password = topo.get_user_access(host_device.USERS[0])
    host_ssh_port = getattr(host_device, "PORT", 22)
    host = Connection(host_device.BASE_IP, port=host_ssh_port, user=host_device_username,
                      config=Config(overrides={"run": {"echo": True}}), inline_ssh_env=True,
                      connect_kwargs={"password": host_device_password})

    logger.info("Check if {} exists ".format(workspace_path))
    if host.run("test -d {}".format(workspace_path), warn=True).ok:
        logger.info("Folder {} exists. Delete it firstly.".format(workspace_path))
        host.run("rm -rf {}".format(workspace_path))

    logger.info("Prepare workspace {}".format(workspace_path))
    logger.info("Create workspace folder {}".format(workspace_path))
    host.run("mkdir -p {}".format(workspace_path))

    if args.tarball:
        tarball_path = os.path.join(args.tarball_path, args.tarball)
        logger.info("Extract tarball %s into workspace folder %s", tarball_path, workspace_path)
        host.run("tar -xvf {} -C {}".format(tarball_path, workspace_path))
        logger.info("Tarball extraction completed successfully.")
    else:
        logger.info("Clone sonic-mgmt repo (branch=%s) into workspace folder %s", args.branch, workspace_path)
        host.config.run.env = {"GERRIT_API_KEY": os.getenv("GERRIT_API_KEY")}
        host.run("git clone -b {} {} {}/sonic-mgmt".format(args.branch, SONIC_MGMT_REPO_URL, workspace_path))
        logger.info("Sonic-mgmt repo cloned successfully.")

    logger.info("Checkout completed successfully.")


if __name__ == "__main__":
    main()
