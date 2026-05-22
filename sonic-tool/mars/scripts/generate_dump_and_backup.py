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
import ipaddress

# Third-party libs
from fabric import Config
from fabric import Connection
from fabric.transfer import Transfer

# Home-brew libs
from lib import constants
from lib.utils import parse_topology, get_logger

logger = get_logger("DumpBackup")


def _is_ipv6_address(ip_str):
    """Check if the given string is an IPv6 address."""
    try:
        # ipaddress on Python 2 requires unicode input
        if hasattr(ip_str, 'decode'):
            ip_str = ip_str.decode('utf-8')
        addr = ipaddress.ip_address(ip_str)
        return isinstance(addr, ipaddress.IPv6Address)
    except ValueError:
        return False


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


def _build_ipv6_gateway(topo):
    """Build a fabric Connection gateway via the SONIC_MGMT device for IPv6 DUT access.

    When the DUT only has an IPv6 management address and the execution environment (e.g. MARS
    docker) lacks IPv6 connectivity, the sonic-mgmt docker (which *does* have IPv6) can act
    as an SSH jump host.

    Returns a Connection object to the SONIC_MGMT device, or None if the device is not found.
    """
    try:
        mgmt_device = topo.get_device_by_topology_id(constants.SONIC_MGMT_DEVICE_ID)
        mgmt_username, mgmt_password = topo.get_user_access(mgmt_device.USERS[0])
        logger.info("Using SONIC_MGMT device {} as SSH gateway for IPv6 DUT access".format(mgmt_device.BASE_IP))
        return Connection(mgmt_device.BASE_IP, user=mgmt_username,
                          connect_kwargs={"password": mgmt_password})
    except Exception as e:
        logger.warning("Failed to build IPv6 gateway via SONIC_MGMT device: {}".format(e))
        return None


def _build_ssh_proxy_command(mgmt_ip, mgmt_username, mgmt_password):
    """Build an SSH ProxyCommand string to tunnel through the SONIC_MGMT device."""
    return ('sshpass -p {pwd} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
            '-W [%h]:%p {user}@{ip}').format(pwd=mgmt_password, user=mgmt_username, ip=mgmt_ip)


def main():

    args = _parse_args()

    backup_location = args.dest if args.dest else constants.DUT_LOG_BACKUP_PATH
    session_id = args.session_id

    topo = parse_topology(args.topo)
    dut_device = topo.get_device_by_topology_id(constants.DUT_DEVICE_ID)
    dut_device_username, dut_device_password = topo.get_user_access(dut_device.USERS[0])

    # When the DUT has an IPv6 address, use the sonic-mgmt docker as an SSH gateway
    # because the MARS docker typically does not have IPv6 connectivity.
    ipv6_dut = _is_ipv6_address(dut_device.BASE_IP)
    gateway = None
    proxy_command = ""
    if ipv6_dut:
        gateway = _build_ipv6_gateway(topo)
        if gateway is None:
            logger.error("DUT has IPv6 address but no SONIC_MGMT gateway is available. "
                         "Connection will likely fail.")
        else:
            # Also prepare ProxyCommand for subprocess-based SSH calls
            mgmt_device = topo.get_device_by_topology_id(constants.SONIC_MGMT_DEVICE_ID)
            mgmt_username, mgmt_password = topo.get_user_access(mgmt_device.USERS[0])
            proxy_command = _build_ssh_proxy_command(mgmt_device.BASE_IP, mgmt_username, mgmt_password)

    switch_dut = Connection(dut_device.BASE_IP, user=dut_device_username,
                     config=Config(overrides={"run": {"echo": True}}),
                     connect_kwargs={"password": dut_device_password},
                     gateway=gateway)
    duts = [switch_dut]
    if "bobcat" in args.topo:
        for dpu_port in range(5021, 5025):
            dpu_dut = Connection(dut_device.BASE_IP, user=dut_device_username, port=dpu_port,
                             config=Config(overrides={"run": {"echo": True}}), connect_timeout=15,
                             connect_kwargs={"password": dut_device_password},
                             gateway=gateway)
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

        # Build SSH command, using ProxyCommand for IPv6 DUTs
        proxy_option = '-o "ProxyCommand={}"'.format(proxy_command) if proxy_command else ""
        ipv6_flag = "-6" if ipv6_dut and not proxy_command else ""
        cmd_run = 'sshpass -p {} ssh {} {} {} {}@{} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "{}"'.format(
            dut_device_password, ipv6_flag, ssh_port_param, proxy_option,
            dut_device_username, dut_device.BASE_IP, generate_dump_cmd)
        logger.info("Running command: {}".format(cmd_run))
        process = subprocess.Popen(cmd_run, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, stderr = process.communicate()
        if stderr:
            logger.error("stderr: {}".format(stderr))
        dump_file = output.splitlines()[-1]
        logger.info("Generated dump {} on DUT {}".format(dump_file, target))
        logger.info("Backup the generated dump to %s" % session_folder)
        dut_scp = Transfer(dut)
        dut_scp.get(dump_file, local=os.path.join(session_folder, os.path.basename(dump_file)))

        logger.info("################### DONE ###################")


if __name__ == "__main__":
    main()
