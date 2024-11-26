#!/usr/bin/env python
"""
After regression testing is done, this script should be executed to generate dump on DUT and backup the dump to netdisk.

This script is executed on the STM node. It establishes SSH connection to the DUT and run commands on it. Purpose is to
generate dump and back up the dump for later analysis.
"""

# Builtin libs
import argparse
import os
import subprocess
import socket

# Third-party libs
from fabric import Config
from fabric import Connection
from fabric.transfer import Transfer

# Home-brew libs
from lib import constants
from lib.utils import parse_topology, get_logger
from paramiko.ssh_exception import NoValidConnectionsError, SSHException

logger = get_logger("DumpBackup")


def _parse_args():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--topo", dest="topo", help="Path to the MARS topology configuration file")
    parser.add_argument("--since", nargs="?", dest="since", default="48 hours ago",
                        help="Collect logs and core files since given date. Default: '48 hours ago'")
    parser.add_argument("--dest", nargs="?", dest="dest",
                        help="Destination folder for backup dump. Default: use lib/constants.DUT_LOG_BACKUP_PATH")
    parser.add_argument("--session-id", dest="session_id", help="Current MARS session_id")
    return parser.parse_args()


def main():

    args = _parse_args()

    backup_location = args.dest if args.dest else constants.DUT_LOG_BACKUP_PATH
    session_id = args.session_id

    topo = parse_topology(args.topo)
    dut_device = topo.get_device_by_topology_id(constants.DUT_DEVICE_ID)
    dut_device_username, dut_device_password = topo.get_user_access(dut_device.USERS[0])
    switch_dut = Connection(dut_device.BASE_IP, user=dut_device_username,
                     config=Config(overrides={"run": {"echo": True}}),
                     connect_kwargs={"password": dut_device_password})
    duts = [switch_dut]
    if "bobcat" in args.topo:
        for dpu_port in range(5021, 5025):
            dpu_dut = Connection(dut_device.BASE_IP, user=dut_device_username, port=dpu_port,
                             config=Config(overrides={"run": {"echo": True}}), connect_timeout=15,
                             connect_kwargs={"password": dut_device_password})
            dpu_dut.ssh_port = dpu_port
            try:
                dpu_dut.open()
                duts.append(dpu_dut)
            except Exception as e:
                logger.warning(e)
                logger.warning("Failed to connect the dpu via port {}.".format(dpu_port))
                logger.warning("Unable to collect the dpu dump")

    switch_hostname = switch_dut.run("hostname").stdout.strip()
    backup_folder = os.path.join(backup_location, switch_hostname + "_setup")
    if not os.path.isdir(backup_folder):
        switch_dut.local("mkdir %s" % backup_folder)

    session_folder = os.path.join(backup_folder, session_id)
    if not os.path.isdir(session_folder):
        switch_dut.local("mkdir %s" % session_folder)

    for index, dut in enumerate(duts):
        target = "switch" if index == 0 else "dpu" + str(index - 1)
        logger.info("Generating dump on sonic dut {}".format(target))
        generate_dump_cmd = "sudo generate_dump -s '%s'" % args.since
        ssh_port_param = "-p {}".format(dut.ssh_port) if hasattr(dut, "ssh_port") else ""
        cmd_run = 'sshpass -p {} ssh {} {}@{} -o StrictHostKeyChecking=no "{}"'.format(
            dut_device_password, ssh_port_param, dut_device_username, dut_device.BASE_IP, generate_dump_cmd)

        process = subprocess.Popen(cmd_run, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, unused_err = process.communicate()

        dump_file = output.splitlines()[-1]
        logger.info("Generated dump {} on DUT {}".format(dump_file, target))
        logger.info("Backup the generated dump to %s" % session_folder)
        dut_scp = Transfer(dut)
        dut_scp.get(dump_file, local=os.path.join(session_folder, os.path.basename(dump_file)))

        logger.info("################### DONE ###################")


if __name__ == "__main__":
    main()
