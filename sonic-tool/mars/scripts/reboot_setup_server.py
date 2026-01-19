#!/usr/bin/env python3
"""
Prepare the SONiC testing server.

This script is executed on the STM node. It establishes an SSH connection to the hypervisor and runs commands on it.
The purpose is to prepare the SONiC testing server which have lots of containers running for new regression.
"""

import time
import argparse
import socket
import os
import traceback
import sys

from fabric import Connection, Config
from paramiko.ssh_exception import NoValidConnectionsError, AuthenticationException, SSHException

from lib import constants
from lib.utils import parse_topology, get_logger

logger = get_logger("RebootSetupServer")

REBOOT_CMD = "sudo reboot"
RESTART_MOUNTS_CMD = "sudo systemctl restart ypbind rpcbind autofs"
REBOOT_TIMEOUT = 600   # 10 min
REBOOT_WAIT_TIME = 60
CHECK_INTERVAL = 20
DOCKER_THRESHOLD = 200


def _parse_args():
    """Parse CLI arguments"""
    parser = argparse.ArgumentParser(description="Reboot test server if too many containers are running.")
    parser.add_argument("--topo", required=True,
                        help="Path to the MARS topology configuration file")
    return parser.parse_args()


def create_connection(host, user, password):
    """Create Fabric connection"""
    cfg = Config(overrides={"run": {"echo": True}})
    return Connection(host, user=user, config=cfg, connect_kwargs={"password": password})


def get_test_server_from_topo(topo_path):
    """Parse topology and return test server info"""
    logger.info("Check if the setup have the topology_origin_server.xml file with original server info")
    base, ext = os.path.splitext(topo_path)
    origin_server_topo_path = base + "_origin_server" + ext
    if os.path.exists(origin_server_topo_path):
        topo_path = origin_server_topo_path

    logger.info("Parsing topology from {}".format(topo_path))
    topo = parse_topology(topo_path)
    test_server_device = topo.get_device_by_topology_id(constants.TEST_SERVER_DEVICE_ID)
    username, password = topo.get_user_access(test_server_device.USERS[0])
    hostname = test_server_device.BASE_IP
    return hostname, username, password


def get_container_count(conn):
    """Return number of running containers"""
    result = conn.run("docker ps -a | wc -l", hide=True)
    try:
        return int(result.stdout.strip())
    except ValueError:
        logger.error("Could not parse container count: {}".format(result.stdout))
        return -1


def get_ssh_conn_after_reboot(host, user, password, timeout=REBOOT_TIMEOUT):
    """Wait until SSH becomes available after reboot."""
    env_user = os.environ.get("BUILD_SERVER_USER")
    env_pass = os.environ.get("BUILD_SERVER_PASSWORD")
    tried_env_creds = False
    start = time.time()

    logger.info("Waiting for {} to become SSH-accessible...".format(host))

    while time.time() - start < timeout:
        try:
            conn = create_connection(host, user, password)
            conn.open()
            conn.close()
            logger.info("{} is back online (SSH OK, waited {}s)".format(host, int(time.time() - start)))
            return conn

        except AuthenticationException:
            if env_user and env_pass and not tried_env_creds:
                logger.warning("Authentication failed for {}, trying env creds ({})...".format(user, env_user))
                user, password = env_user, env_pass
                tried_env_creds = True
                continue
            logger.info("Authentication failed, retrying in {}s...".format(CHECK_INTERVAL))
            time.sleep(CHECK_INTERVAL)

        except (NoValidConnectionsError, SSHException, OSError, socket.error):
            logger.info("{} is not reachable. Wait for {} seconds and check again".format(host, CHECK_INTERVAL))
            time.sleep(CHECK_INTERVAL)

    raise Exception("Timeout waiting for {} is reachable by SSH.".format(host))


def reboot_server(conn, host):
    """Execute reboot command"""
    logger.info("Rebooting {} ...".format(host))
    try:
        conn.run(REBOOT_CMD, hide=False)
    except Exception as e:
        # Expected because SSH will drop
        logger.info("SSH disconnected during reboot (expected): {}".format(e))
    finally:
        conn.close()


def restart_mount_services(conn):
    """Reconnect and restart mount-related services"""
    logger.info("Restarting mount-related services")
    conn.run(RESTART_MOUNTS_CMD, hide=False)
    logger.info("Mount services restarted successfully.")
    conn.close()


def main():
    args = _parse_args()

    host, user, password = get_test_server_from_topo(args.topo)
    conn = create_connection(host, user, password)
    conn.run("hostname", hide=False)

    logger.info("Checking container count...")
    container_count = get_container_count(conn)
    logger.info("Found {} containers running on {}".format(container_count, host))

    if container_count <= DOCKER_THRESHOLD:
        logger.info("Container count <= {}, reboot not required.".format(DOCKER_THRESHOLD))
        conn.close()
        return

    reboot_server(conn, host)

    logger.info("Waiting for {} seconds to allow the server to reboot...".format(REBOOT_WAIT_TIME))
    time.sleep(REBOOT_WAIT_TIME)  # Wait for the server to reboot

    conn = get_ssh_conn_after_reboot(host, user, password)
    restart_mount_services(conn)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
