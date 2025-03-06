import logging
import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.nmx
@pytest.mark.parametrize('stream_protocol', ClusterConsts.NMXC_LOG_STREAM_PROTOCOLS)
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(2 * MINUTE, func_only=True)
def test_nmxc_log_stream_set(engines, setup_name, stream_protocol, test_api):
    player = engines.sonic_mgmt
    url_list = [player.ip]
    url = random.choice(url_list)
    full_url = f'{player.username}:{player.password}@{url}:{ClusterConsts.NMXC_LOG_STREAM_DEFAULT_PORT}'
    stream = f'{stream_protocol} {full_url}'
    full_url_show = f'{player.username}:********@{url}:{ClusterConsts.NMXC_LOG_STREAM_DEFAULT_PORT}'
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

        with allure.step("Validate logs are streamed to remote"):
            # TO DO: Add test
            logger.info("Buffer for testing at the remote end")

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
