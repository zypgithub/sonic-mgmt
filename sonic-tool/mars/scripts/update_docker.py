#!/usr/bin/env python
"""
Prepare the SONiC testing topology.

This script is executed on the STM node. It establishes SSH connection to the hypervisor (Player) and
run commands on it. Purpose is to prepare the SONiC testing topology using the testbed-cli.sh tool.
"""

# Builtin libs
import argparse
import json
import os
import re
import sys
import time
import traceback
from ipaddress import IPv6Interface

# Third-party libs
from fabric import Config
from fabric import Connection
from invoke.exceptions import UnexpectedExit
from retry import retry
from retry.api import retry_call

# Home-brew libs
from lib import constants
from lib.utils import parse_topology, get_logger

logger = get_logger("UpdateDocker")

CONTAINER_IFACE = "eth0"
NETWORK_NAME = "containers_network"
GET_NETWORK_CMD = "docker network ls | grep '{}'".format(NETWORK_NAME)


def _parse_args():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--topo", dest="topo", help="Path to the MARS topology configuration file")
    parser.add_argument("--dut-name", nargs="?", dest="dut_name", help="The DUT name")
    parser.add_argument("--registry-url", nargs="?", dest="registry_url",
                        help="Docker registry URL. Default: use lib/constants.DOCKER_REGISTRY")
    parser.add_argument("--docker-name", nargs="?", default="sonic-mgmt", dest="docker_name",
                        help="Name of the sonic-mgmt docker. Default: 'sonic-mgmt'")
    parser.add_argument("--docker-tag", nargs="?", dest="docker_tag",
                        help="Docker image tag. Optional parameter.")
    parser.add_argument("--delete_container", nargs="?", dest="delete_container", default=False,
                        help="Force container removal and recreation, even if a docker container with the expected "
                             "image is already running.")
    parser.add_argument("--send_takeover_notification", help="If set to True, the script will send a takeover "
                                                             "notification to all the active terminals and wait for "
                                                             "a predefined period before starting the deployment",
                        dest="send_takeover_notification", default='no', choices=["yes", "no"])
    return parser.parse_args()


def inspect_container(conn, image_name, image_tag, container_name):
    """
    @summary: Inspect the specified docker image and container, gather some basic information.
    @param conn: Fabric connection to the host server.
    @param image_name: Docker image name.
    @param image_tag: Docker image tag.
    @param container_name: Docker container name to be inspected.
    @return: Returns inspection result in a dictionary.
    """
    res = {
        "container_exists": None,
        "container_running": None,
        "container_matches_image": None,
        "image_exists": None
    }

    res["container_exists"] = conn.run("docker ps -a -f name=%s$ --format '{{.Names}}'" % container_name).\
        stdout.strip() == container_name

    image_id = conn.run("docker images --no-trunc %s:%s --format '{{.ID}}'" % (image_name, image_tag)).stdout.strip()
    if len(image_id) > 0:
        res["image_exists"] = True

    if res["container_exists"]:
        container_info = json.loads(conn.run("docker inspect {}".format(container_name)).stdout.strip())
        try:
            res["container_running"] = container_info[0]["State"]["Running"]

            if res["image_exists"]:
                res["container_matches_image"] = image_id == container_info[0]["Image"]
        except (IndexError, KeyError) as e:
            logger.error("Failed to get container info, exception: %s" + repr(e))

    logger.info("Inspection result: %s" % json.dumps(res))
    return res


def start_container(conn, container_name, max_retries=3):
    """
    @summary: Try to start an existing container.
    @param conn: Fabric connection to the host server.
    @param container_name: Docker container name.
    @param max_retries: Max number of retries.
    @return: Returns True if starting container succeeded. Returns False if starting failed.
    """
    for i in range(max_retries):
        attempt = i + 1
        logger.info("Try to start container %s, max_retries=%d, attempt=%d" % (container_name, max_retries, attempt))
        try:
            conn.run("docker start %s" % container_name)
            logger.info("Started container %s, max_retries=%d, attempt=%d" % (container_name, max_retries, attempt))
            return True
        except UnexpectedExit as e:
            logger.error("Starting container exception: %s" % repr(e))
        logger.error("Starting container %s failed, max_retries=%d, attempt=%d" %
                     (container_name, max_retries, attempt))
        time.sleep(2)

    logger.error("Failed to start container %s after tried %d times." % (container_name, max_retries))
    return False


def create_mgmt_network(conn):
    """
    @summary: create management network for containers - macvlan networt
    """
    logger.info('Create macvlan network %s', NETWORK_NAME)
    if not conn.run(GET_NETWORK_CMD, warn=True).stdout.strip():
        ip_route_info = conn.run('ip route | grep default').stdout.strip()
        ip_gw = ip_route_info.split()[2]
        ip_iface = ip_route_info.split()[4]

        ip_info = conn.run("ip addr | grep  -A1 ' '{} | grep 'inet'".format(ip_iface)).stdout.strip()
        our_addr = ip_info.split()[1].split('/')[0]
        net_info_data = conn.run('ip route | grep -m1 "scope link src {}"'.format(our_addr)).stdout.strip()
        net_info = net_info_data.split()[0]

        ipv6_info = conn.run("ip -6 addr | grep  -A1 ' '{} | grep 'inet6'".format(ip_iface)).stdout.strip()
        our_addr_v6 = ipv6_info.split()[1]
        ipv6 = IPv6Interface(our_addr_v6)
        ipv6_net_info = str(ipv6.network)
        ipv6_gw = str(ipv6.network.network_address) + "1"

        cmd = 'docker network create -d macvlan --ipv6 --gateway={} --subnet={} --gateway={} --subnet={} -o parent={} {}'.format(ip_gw, net_info, ipv6_gw, ipv6_net_info, ip_iface, NETWORK_NAME)
        conn.run(cmd)
        if not conn.run(GET_NETWORK_CMD, warn=True).stdout.strip():
            raise Exception("Docker mgmt network was not created!")

    else:
        logger.info('macvlan network \"%s\" - already exist', NETWORK_NAME)


def create_secrets_vars_script(conn, mars_docker_env_secrets, container_name):
    export_env_var_script_path = "/tmp/{CONTAINER_NAME}_export_env_var.sh".format(CONTAINER_NAME=container_name)
    if os.path.exists(export_env_var_script_path):
        conn.run("rm -f {SCRIPT_PATH}".format(SCRIPT_PATH=export_env_var_script_path), warn=True)
    regex = r"[\w|_]*=[\'|\w|\d|$|!|-|\.|\/|\-|:|~|\(|\)]*"
    env_vars = re.findall(regex, mars_docker_env_secrets)
    script_content = ["export {0}".format(env_var.replace("$", r"\$")) for env_var in env_vars]
    script_content = ["#!/bin/bash"] + script_content
    for line in script_content:
        conn.run("echo \"{LINE}\" >> {SCRIPT_PATH}".format(LINE=line, SCRIPT_PATH=export_env_var_script_path), warn=True)
    return export_env_var_script_path


def create_and_start_container(conn, image_name, image_tag, container_name, mac_address):
    """
    @summary: Create and start specified container from specified image
    @param conn: Fabric connection to the host server
    @param image_name: Docker image name
    @param image_tag: Docker image tag
    @param container_name: Docker container name to be started
    @param mac_address: MAC address of the container's management interface
    """
    container_iface_mac = mac_address
    create_mgmt_network(conn)

    container_mountpoints_dict = constants.SONIC_MGMT_MOUNTPOINTS.items()
    if conn.host in constants.MTBC_SERVER_LIST:
        container_mountpoints_dict += constants.SONIC_MGMT_MOUNTPOINTS_MTBC.items()
    if conn.host in constants.MTL_NVOS_SERVER_LIST:
        container_mountpoints_dict += constants.MTL_NVOS_MOUNTPOINTS.items()
    container_mountpoints_list = []
    for key, value in container_mountpoints_dict:
        if key == "/workspace":
            container_mountpoints_list.append("-v {}:{}:rw".format(key, value))
        else:
            container_mountpoints_list.append("-v {}:{}:rslave".format(key, value))

    container_mountpoints = " ".join(container_mountpoints_list)

    mars_docker_env_secrets = os.getenv("MARS_DOCKER_ENV_SECRETS")
    secrets_vars_script_path = create_secrets_vars_script(conn, mars_docker_env_secrets, container_name)
    cmd_tmplt = "docker run --init -d -t --cap-add=NET_ADMIN {CONTAINER_MOUNTPOINTS} " \
                "--privileged --network=containers_network --mac-address={MAC_ADDRESS} " \
                "--env ANSIBLE_CONFIG=/root/mars/workspace/sonic-mgmt/ansible/ansible.cfg {MARS_DOCKER_ENV_SECRETS} " \
                "--name {CONTAINER_NAME} {IMAGE_NAME}:{IMAGE_TAG} /bin/bash"
    cmd = cmd_tmplt.format(
        CONTAINER_MOUNTPOINTS=container_mountpoints,
        MAC_ADDRESS=container_iface_mac,
        CONTAINER_NAME=container_name,
        IMAGE_NAME=image_name,
        IMAGE_TAG=image_tag,
        MARS_DOCKER_ENV_SECRETS=mars_docker_env_secrets
    )

    logger.info("Try to remove existing docker container anyway")
    conn.run("docker rm -f {CONTAINER_NAME}".format(CONTAINER_NAME=container_name), warn=True)

    global failed_in_creating_container
    failed_in_creating_container = False

    @retry(exceptions=AssertionError, tries=10, delay=60)
    def _create_container():
        conn.run(cmd, warn=True)
        logger.info("Created container, wait a few seconds for it to start")
        time.sleep(5)
        logger.info("Check whether the container is started successfully.")
        container_state = json.loads(conn.run("docker inspect --format '{{json .State}}' %s" % container_name)
                                     .stdout.strip())

        if not container_state["Running"]:
            logger.error("The created container is not started, try to restart it")
            if not start_container(conn, container_name, max_retries=1):
                logger.error("Restart container failed. "
                             "Remove the container and delay 60s before recreating.")
                global failed_in_creating_container
                failed_in_creating_container = True
                conn.run("docker rm -f {CONTAINER_NAME}".format(CONTAINER_NAME=container_name), warn=True)
                assert False, "Failed to create the container."

    _create_container()

    validate_docker_is_up(conn, container_name)
    logger.info("Configure container after starting it")
    copy_script_cmd = "docker cp {SCRIPT_PATH} " \
                      "{CONTAINER_NAME}:/etc/profile.d/".format(SCRIPT_PATH=secrets_vars_script_path,
                                                                CONTAINER_NAME=container_name)
    conn.run(copy_script_cmd, warn=True)
    conn.run("rm -f {SCRIPT_PATH}".format(SCRIPT_PATH=secrets_vars_script_path), warn=True)
    if not configure_docker_route(conn, container_name):
        logger.error("Configure docker container failed.")
        sys.exit(1)


@retry(Exception, tries=3, delay=10)
def validate_docker_is_up(conn, container_name):
    """
    This function will run a dummy echo command on docker containers,
    In order to validate the container is really up.
    This function purpose is to avoid failures,
    when configuring the docker (during configure_docker_route) and the docker is not up yet.
    :param conn: Fabric connection to the host server
    :param container_name: Docker container name that was started
    :return: raise Exception if docker is not up after all retries failed
    """
    logger.info("Validating docker {CONTAINER_NAME} is up by running dummy echo cmd"
                .format(CONTAINER_NAME=container_name))
    conn.run("docker exec {CONTAINER_NAME} bash -c \"echo \"UP\"\"".format(CONTAINER_NAME=container_name))


def configure_docker_route(conn, container_name):
    """
    @summary: Configure docker container.
    For the sonic-mgmt container to get IP address from LAB DHCP server
    @param conn: Fabric connection to the host server
    @param container_name: Docker container name to be started
    @return: Returns True if configurations are successful. In case of exception, return False.
    """

    try:
        logger.info("Try to configure route and execute dhclient on container")

        # Remove existing default IP assigned by dockerd to macvlan eth0 interface
        available_ips_info = conn.run('docker exec {CONTAINER_NAME} bash -c "sudo ip -j address"'
                                      .format(CONTAINER_NAME=container_name)).stdout.strip()
        ip_address_dict = json.loads(available_ips_info)
        for interface_data in ip_address_dict:
            if CONTAINER_IFACE in interface_data['ifname']:
                available_ip = interface_data['addr_info']
                for ip_data in available_ip:
                    if ip_data['family'] == "inet":
                        cmd = 'ip addr del {}/{} dev {}'.format(ip_data['local'], ip_data['prefixlen'], CONTAINER_IFACE)
                        conn.run('docker exec {CONTAINER_NAME} bash -c "sudo {CMD}"'
                                 .format(CONTAINER_NAME=container_name, CMD=cmd))

        # Connect default bridge network in container which will be used for access hypervisor IP
        conn.run('docker network connect bridge {CONTAINER_NAME}'.format(CONTAINER_NAME=container_name))
        # Remove default route via "bridge" network(added by default after connect network)
        conn.run('docker exec {CONTAINER_NAME} bash -c "sudo ip route del default"'
                 .format(CONTAINER_NAME=container_name), warn=True)
        # Get hypervisor IP in "bridge" network
        parser_line = '{{ .NetworkSettings.Networks.bridge.Gateway }}'
        hyper_local_ip = conn.run("docker inspect -f '{}' {}".format(parser_line, container_name)).stdout.strip()
        # Add route to hypervisor via "bridge" network
        conn.run('docker exec {CONTAINER_NAME} bash -c "sudo ip route add {HYPER_IP} via {HYPER_DOCKER_IP}"'
                 .format(CONTAINER_NAME=container_name, HYPER_IP=conn.host, HYPER_DOCKER_IP=hyper_local_ip))
        # Run dhclient on macvlan network and get public IP/default route from DHCP server based on MAC address
        conn.run('docker exec {CONTAINER_NAME} bash -c "sudo dhclient {CONTAINER_IFACE} -v"'
                 .format(CONTAINER_NAME=container_name, CONTAINER_IFACE=CONTAINER_IFACE))

        conn.run('docker exec {CONTAINER_NAME} bash -c "sudo /etc/init.d/ssh restart"'
                 .format(CONTAINER_NAME=container_name))

        logger.info("Successfully configured route and executed dhclient on container")
        return True
    except UnexpectedExit as e:
        logger.error("Exception: %s" % repr(e))
        logger.error("Configure route & dhclient on container failed.")
        return False


def cleanup_dangling_docker_images(test_server):
    """
    @summary:
     When running docker system prune -a, it will remove both unused and dangling images.
     Therefore any images being used in a container,
     whether they have been exited or currently running, will NOT be affected.
    """
    test_server.run("docker system prune --all -f", warn=True)


def main():

    args = _parse_args()

    registry_url = constants.DOCKER_REGISTRY
    logger.info("Default registry_url=%s" % registry_url)
    if args.registry_url:
        registry_url = args.registry_url
        logger.info("Override default registry_url value, now registry_url=%s" % registry_url)

    docker_image_name = 'docker-ngts'
    if args.docker_tag:
        docker_tag = args.docker_tag
    else:
        docker_tag = get_docker_default_tag(docker_image_name)

    if args.dut_name:
        container_name = '{}_{}'.format(args.dut_name, docker_image_name)
    else:
        container_name = args.docker_name

    topo = parse_topology(args.topo)
    test_server_device = topo.get_device_by_topology_id(constants.TEST_SERVER_DEVICE_ID)
    test_server_device_username, test_server_device_password = topo.get_user_access(test_server_device.USERS[0])
    docker_host = topo.get_device_by_topology_id(constants.SONIC_MGMT_DEVICE_ID)
    mac = docker_host.MAC_ADDRESS

    test_server = Connection(test_server_device.BASE_IP, user=test_server_device_username,
                             config=Config(overrides={"run": {"echo": True}}),
                             connect_kwargs={"password": test_server_device_password})

    if args.send_takeover_notification == 'yes':
        send_takeover_notification(topo)

    logger.info("Pull docker image to ensure that it is up to date")
    retry_call(test_server.run, fargs=["docker pull {}/{}:{}".format(registry_url, docker_image_name, docker_tag)],
               tries=3, delay=10, logger=logger)

    logger.info("Check current docker container and image status")
    inspect_res = inspect_container(test_server, "{}/{}".format(registry_url, docker_image_name), docker_tag,
                                    container_name)

    if not inspect_res["image_exists"]:
        logger.error("No docker image. Please check using commands:")
        logger.error("    curl -X GET http://{}/v2/_catalog".format(registry_url))
        logger.error("    curl -X GET http://{}/v2/{}/tags/list".format(registry_url, docker_image_name))
        sys.exit(1)

    delete_container_required = args.delete_container
    if not delete_container_required:
        if inspect_res["container_matches_image"]:
            if inspect_res["container_running"]:
                logger.info("The {} docker container with expected image is running.".format(container_name))
                logger.info("################### DONE ###################")
                sys.exit(0)
            else:
                logger.info("The {} docker container using expected image is stopped. Try to start it")
                if start_container(test_server, container_name, max_retries=3):
                    if configure_docker_route(test_server, container_name):
                        logger.info("################### DONE ###################")
                        sys.exit(0)
                    else:
                        logger.error("Failed to configure routes and dhclient on container. "
                                     "Try to delete and re-create")
                        delete_container_required = True
                else:
                    logger.error("Starting container %s failed. Will delete it and re-create" % container_name)
                    delete_container_required = True

    logger.info("Need to create and start sonic-mgmt container")
    create_and_start_container(test_server, "{}/{}".format(registry_url, docker_image_name),
                               docker_tag, container_name, mac)

    logger.info("Try to delete dangling docker images to save space")
    cleanup_dangling_docker_images(test_server)

    logger.info("################### DONE ###################")


def get_docker_default_tag(docker_name):
    latest = "latest"
    default_list = {'docker-ngts': '1.2.325'}
    return default_list.get(docker_name, latest)


def send_takeover_notification(topo):
    wait_between_notf_to_regression_start = 3
    players_to_be_notified = [constants.SONIC_MGMT_DEVICE_ID, constants.DUT_DEVICE_ID]
    players_were_notified = False
    for player in players_to_be_notified:
        player_info = topo.get_device_by_topology_id(player)
        player_info_username, player_info_password = topo.get_user_access(player_info.USERS[0])
        try:
            notify_player_users(player_info, wait_between_notf_to_regression_start,
                                player_info_username, player_info_password)
            players_were_notified = True
        except Exception:
            logger.warning("Unable to connect to {}:{}, in order to notify logged users about regression "
                           "start".format(player, player_info.BASE_IP))
    if players_were_notified:
        logger.info("Sleeping for {} minutes".format(wait_between_notf_to_regression_start))
        time.sleep(wait_between_notf_to_regression_start * 60)


def notify_player_users(player_info, wait_between_notf_to_regression_start, player_info_username, player_info_password):
    takeover_message = "Mars regression is taking over in {} minutes. Please save your work and logout".\
        format(wait_between_notf_to_regression_start)
    player_engine = Connection(player_info.BASE_IP, user=player_info_username,
                               config=Config(overrides={"run": {"echo": True}}),
                               connect_kwargs={"password": player_info_password},
                               connect_timeout=5)
    logger.info("Sending takeover notification to:{}".format(player_info.BASE_IP))
    player_engine.run('wall {}'.format(takeover_message))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
