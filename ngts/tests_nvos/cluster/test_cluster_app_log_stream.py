import logging
import os
import random
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

from retry import retry

logger = logging.getLogger()


@pytest.mark.nmx
@pytest.mark.parametrize('stream_protocol', ClusterConsts.NMXC_LOG_STREAM_PROTOCOLS)
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(7 * MINUTE, func_only=True)
def test_nmxc_log_stream_set(engines, setup_name, stream_protocol, test_api):
    player = engines.sonic_mgmt
    ipv4 = player.ip
    hostname = player.run_cmd("hostname")
    # ipv6 = player.run_cmd("hostname  -I | awk '{print $3}'")
    url_list = [hostname, ipv4]
    url = random.choice(url_list)
    full_url = f'{player.username}:{player.password}@{url}:{ClusterConsts.NMXC_LOG_STREAM_DEFAULT_PORT}'
    stream = f'{stream_protocol} {full_url}'
    full_url_show = f'{player.username}:********@{url}:{ClusterConsts.NMXC_LOG_STREAM_DEFAULT_PORT}'
    msg_uid = int(time.time())  # generates a unique ID using seconds elapsed since epoch
    log_msg = f"Unique Message ID {msg_uid}: Hello from NVOS"
    service = ClusterConsts.CONTROLLER_LOG_STREAM_SERVICE
    try:
        with allure.step("Start Cluster"):
            cluster = Cluster()
            ClusterTools.start_cluster(cluster, setup_name)

        with allure.step("Set NMX-C log stream configuration"):
            cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.action_update_cluster_log_stream(stream=stream)

        with allure.step("Validate NMX-Controller log stream configuration is {}".format(stream)):
            output = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.show(exempted_err_msgs="Error")
            assert validate_nmxc_log_stream_config(output, protocol=stream_protocol, remote_url=full_url_show), \
                "NMX-C log stream config is not set to {}".format(stream)

        with allure.step("Enable {} server on remote {}".format(stream_protocol, player.ip)):
            enable_log_server_on_remote(player, service)

        with allure.step("Stream logs to remote url"):
            log_cmd = f'logger -n {url} -P 514 "{log_msg}"'
            engines.dut.run_cmd(log_cmd)

        with allure.step("Validate logs are received at the remote"):
            retry_validate_log_msg_on_remote(player, log_msg)

        with allure.step("Unset NMX-C log stream configuration"):
            cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.action_restore_cluster_log_stream()

        with allure.step("Validate NMX-Controller log stream configuration is back to empty"):
            output = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.show(exempted_err_msgs="Error")
            assert validate_nmxc_log_stream_config(output, empty=True), "NMX-C log stream config is not empty"

    finally:
        with allure.step("Unset NMX-C log stream configuration"):
            cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.action_restore_cluster_log_stream()

        with allure.step("Stop Cluster"):
            logger.info("Set cluster state to disable")
            ClusterTools.stop_cluster(cluster)

        with allure.step("Remove temporary config file"):
            os.system(f"rm -rf {NvosConst.MARS_RESULTS_FOLDER}{ClusterConsts.CONTROLLER_LOG_STREAM_CONFIG_FILE}")


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_nmxc_log_stream_show(test_api):
    cluster = Cluster()
    try:
        with allure.step("Validate initial NMX-Controller log stream configuration is empty"):
            output = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.show(exempted_err_msgs="Error")
            assert validate_nmxc_log_stream_config(output, empty=True), "NMX-C log stream config is not empty"

    finally:
        clean_up_cluster_nmxc_log_stream(cluster)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(2 * MINUTE, func_only=True)
def test_nmxc_log_stream_set_unsupported_app(engines, setup_name, test_api):
    player = engines.sonic_mgmt
    stream_protocol = ClusterConsts.PROTOCOL_RSYSLOG
    url = player.ip
    app_name = ClusterConsts.NMX_TELEMETRY
    expected_str = f"{app_name} not supported yet"
    helper_nmxc_log_stream_set_incorrect(setup_name, player, stream_protocol, url, expected_str, app_name)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(2 * MINUTE, func_only=True)
def test_nmxc_log_stream_set_incorrect_app(engines, setup_name, test_api):
    player = engines.sonic_mgmt
    stream_protocol = ClusterConsts.PROTOCOL_RSYSLOG
    url = player.ip
    app_name = "dummy_app_name"
    expected_str = f"{app_name} not supported yet"
    helper_nmxc_log_stream_set_incorrect(setup_name, player, stream_protocol, url, expected_str, app_name)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(2 * MINUTE, func_only=True)
def test_nmxc_log_stream_set_incorrect_protocol(engines, setup_name, test_api):
    player = engines.sonic_mgmt
    stream_protocol = "dummy_protocol"
    url = player.ip
    # Change to below line after fixed by design along with support for elk, splunk protocols
    # expected_str = f"'{stream_protocol}' is not one of {ClusterConsts.NMXC_LOG_STREAM_PROTOCOLS}"
    expected_str = "Invalid Command"
    helper_nmxc_log_stream_set_incorrect(setup_name, player, stream_protocol, url, expected_str)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(2 * MINUTE, func_only=True)
def test_nmxc_log_stream_set_incorrect_url(engines, setup_name, test_api):
    player = engines.sonic_mgmt
    stream_protocol = ClusterConsts.PROTOCOL_RSYSLOG
    url = "dummy:123"
    expected_str = f"is not a 'log-remote-url'"
    helper_nmxc_log_stream_set_incorrect(setup_name, player, stream_protocol, url, expected_str)


def helper_nmxc_log_stream_set_incorrect(setup_name, player, stream_protocol, url, expected_str="",
                                         app_name=ClusterConsts.NMX_CONTROLLER):

    stream = f'{stream_protocol} {player.username}:{player.password}@{url}:{ClusterConsts.NMXC_LOG_STREAM_DEFAULT_PORT}'
    try:
        with allure.step("Start Cluster"):
            cluster = Cluster()
            ClusterTools.start_cluster(cluster, setup_name)

        try:
            with allure.step("Set NMX-C log stream configuration"):
                cluster.apps.app_name[app_name].logstream.action_update_cluster_log_stream(
                    expected_str=expected_str, stream=stream)
        except TypeError as e:
            logger.info("Expected error found:{}".format(type(e).__name__))

        with allure.step("Validate NMX-Controller log stream configuration remains empty"):
            output = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.show(exempted_err_msgs="Error")
            assert validate_nmxc_log_stream_config(output, empty=True), "NMX-C log stream config is not empty"

    finally:
        with allure.step("Unset NMX-C log stream configuration"):
            cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.action_restore_cluster_log_stream()

        with allure.step("Stop Cluster"):
            logger.info("Set cluster state to disable")
            ClusterTools.stop_cluster(cluster)


def clean_up_cluster_nmxc_log_stream(cluster):
    output = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.show(exempted_err_msgs="Error")
    if output != "Error: The requested item does not exist.":
        cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.action_restore_cluster_log_stream()


def validate_nmxc_log_stream_config(output, protocol="", remote_url="", empty=False):
    if output == "Error: The requested item does not exist.":
        # NMX-C config keys itself are not available
        return empty

    output = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()

    if output["protocol"] != protocol:
        "Protocol is {} instead of {}".format(output["protocol"], protocol)
        return False
    if output["remote-url"] != remote_url:
        "Remote-url is {} instead of {}".format(output["remote-url"], remote_url)
        return False

    return True


def enable_log_server_on_remote(player, service):
    check_processes_cmd = f'sudo service {service} status'
    with allure.step("Verify and update protocol config file"):
        ret_value = verify_update_protocol_conf_file(player)
        if ret_value == "change":
            with allure.step("Restarting {} server on {}".format(service, player.ip)):
                player.run_cmd(f"sudo service {service} restart")
        else:
            output = player.run_cmd(check_processes_cmd)
            if f'{service}d is running' not in output:
                with allure.step("Starting {} server on {}".format(service, player.ip)):
                    player.run_cmd(f"sudo service {service} start")

    with allure.step("Checking log server is running on remote"):
        retry_check_log_server_on_remote(player, service, check_processes_cmd)


def verify_update_protocol_conf_file(player):
    file_name = ClusterConsts.CONTROLLER_LOG_STREAM_CONFIG_FILE
    conf_file = f"{NvosConst.MARS_RESULTS_FOLDER}{file_name}"
    config_line_1 = 'module(load="imudp")\n'
    config_line_2 = 'input(type="imudp" port="514")\n'
    config_lines = [config_line_1, config_line_2]
    cmd_copy_from_remote = f"sshpass -p {player.password} scp -o StrictHostKeyChecking=no {player.username}@" \
        f"{player.ip}:/etc/{file_name} {NvosConst.MARS_RESULTS_FOLDER}"
    cmd_copy_to_remote = f"sshpass -p {player.password} scp -o StrictHostKeyChecking=no" \
        f"{NvosConst.MARS_RESULTS_FOLDER}{file_name} {player.username}@{player.ip}:/etc/{file_name}"

    # Extract protocol config file from server
    os.system(cmd_copy_from_remote)

    # Update the protocol config file
    with open(conf_file, 'r') as file:
        lines = file.readlines()

    if config_line_1 in lines and config_line_2 in lines:
        # config lines already present
        logger.info("Protocol config already present")
        return "no change"

    if "#" + config_line_1 in lines and "#" + config_line_2 in lines:
        # commented config lines present
        logger.info("Uncomment commented config lines in protocol config file")
        with open(conf_file, 'w') as file:
            for line in lines:
                if line[1:] in config_lines:
                    file.write(line[1:])
                else:
                    file.write(line)

    else:
        # config lines not present
        logger.info("Adding config lines in protocol config file")
        with open(conf_file, 'a') as file:
            file.write("\n# provides UDP syslog reception\n")
            for config_line in config_lines:
                file.write(config_line)

    # Copy back the updated protocol config file and remove local copy
    os.system(cmd_copy_to_remote)
    return "change"


@retry(Exception, tries=24, delay=10)
def retry_check_log_server_on_remote(player, service, check_processes_cmd):
    output = player.run_cmd(check_processes_cmd)
    assert f'{service}d is running' in output, \
        "Not able to start log server on {}".format(player.ip)


@retry(Exception, tries=6, delay=10)
def retry_validate_log_msg_on_remote(player, log_msg):
    logger.info("Checking log message is present on remote")
    log_msg_read_cmd = f'cat /var/log/syslog | grep "{log_msg}"'
    output = player.run_cmd(log_msg_read_cmd)
    assert output, "Log msg {} not found on {}".format(log_msg, player.ip)
