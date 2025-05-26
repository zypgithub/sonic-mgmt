"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import os
from ngts.constants.constants import BugHandlerConst
from ngts.helpers.performance.traffic_helpers import create_empty_json_traffic_file
from ngts.performance_tests.conftest import get_all_players_ports
from ngts.performance_tests.lossy_lossless.conftest import create_lossy_lossless_json_traffic_file
import pytest
import logging
import allure
import json
import re
from ngts.helpers.general_helper import get_pytest_test_name
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration)
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata

logger = logging.getLogger()
TESTS_SCENARIO = "lossy_lossless"


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args):
    try:
        with allure.step('Save Players initial Configuration'):
            save_base_configuration(players)
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(players, scenario=TESTS_SCENARIO, conf_args=conf_args)
        yield
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            restore_basic_configuration(players)


def get_many_to_1_traffic(conf_args, num_lossy_packets, num_lossless_packets, template_suite="traffic_packets_json_files"):
    """
    Generate traffic configuration for many-to-1 lossy/lossless scenario.

    Args:
        conf_args: Dictionary containing configuration parameters
        num_lossy_packets: Number of lossy packets to generate
        num_lossless_packets: Number of lossless packets to generate
        template_suite: Directory containing traffic template files

    Returns:
        Dictionary mapping player aliases to their traffic configuration file paths
    """
    traffic_jsons = {}

    traffic_script_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                       TESTS_SCENARIO, "lossy_lossless_scenario_4_many_to_1.json")

    conf_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                             PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, TESTS_SCENARIO, "dvs",
                             f"{PerfConsts.LEFT_TG_ALIAS}_conf.json")

    with open(conf_path) as f:
        conf_json = json.load(f)

    traffic_parameters = {
        "ports": conf_args[PerfConsts.PORT_GROUPS][PerfConsts.LEFT_TG_ALIAS]["traffic_from_10_ports_group"],
        "MAC": {"src": conf_json["smac"], "dst": conf_json["left_mac"]},
        "IP": {"src": conf_json["source_ip"], "dst": conf_json["left_dst_ip"]},
        "UDP": {"src": PerfConsts.UDP_SOURCE_PORT, "dst": PerfConsts.ROCE_PORT},
        "AR": PerfConsts.ADAPTIVE_ROUTING_ENABLED,
        "packet_size": conf_args["packet_size"],
        "num_packets": conf_args["left_num_packets"],
        "is_ipv6": conf_args["is_ipv6"],
        "lossy_dscp_value": 34,
        "lossless_dscp_value": 26
    }

    create_lossy_lossless_json_traffic_file(player_alias=PerfConsts.LEFT_TG_ALIAS,
                                            traffic_parameters=traffic_parameters,
                                            json_path=traffic_script_path,
                                            num_lossy_packets=num_lossy_packets,
                                            num_lossless_packets=num_lossless_packets)

    traffic_jsons[PerfConsts.LEFT_TG_ALIAS] = traffic_script_path

    empty_traffic_script_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                             TESTS_SCENARIO, "empty_file.json")

    create_empty_json_traffic_file(empty_traffic_script_path)
    traffic_jsons[PerfConsts.RIGHT_TG_ALIAS] = empty_traffic_script_path

    return traffic_jsons


@pytest.fixture(scope='session', autouse=True)
def conf_args(players):
    """
    This function alters all of the jinja template files.
    """
    split_left = 2
    split_right = 2
    num_of_traffic_ports = 10

    all_ports_after_split = get_all_players_ports(players, split_right, split_left)

    conf_args = {"congestion_thresh_lo": PerfConsts.LOW_AR_THRESHOLD,
                 "auto_buffer_mode": "False",
                 "packet_size": PerfConsts.PACKET_SIZE_LIST[0],
                 "is_ipv6": False,
                 "split_right": 2,
                 "split_left": 2,
                 "two_sided_ar": True,
                 "scenario": TESTS_SCENARIO,
                 "left_num_packets": 0,  # Override in the test
                 "right_num_packets": 0,  # Override in the test
                 PerfConsts.PORT_GROUPS: {
                     PerfConsts.LEFT_TG_ALIAS: {
                         f"traffic_from_{num_of_traffic_ports}_ports_group": all_ports_after_split[PerfConsts.LEFT_TG_ALIAS]["unconnected_ports"][:num_of_traffic_ports],
                         "dont_care_ports": all_ports_after_split[PerfConsts.LEFT_TG_ALIAS]["unconnected_ports"][num_of_traffic_ports:]
                     },
                     PerfConsts.RIGHT_TG_ALIAS: {
                         "single_port_group": all_ports_after_split[PerfConsts.RIGHT_TG_ALIAS]["unconnected_ports"][:1],
                         "dont_care_ports": all_ports_after_split[PerfConsts.RIGHT_TG_ALIAS]["unconnected_ports"][1:]
                     },
                     PerfConsts.DUT_ALIAS: {
                         f"traffic_from_{num_of_traffic_ports}_ports_group": all_ports_after_split[PerfConsts.DUT_ALIAS]["left_split_ports"][:num_of_traffic_ports],
                         "single_port_group": all_ports_after_split[PerfConsts.DUT_ALIAS]["right_split_ports"][:1],
                         "dont_care_ports": (
                             all_ports_after_split[PerfConsts.DUT_ALIAS]["left_split_ports"][num_of_traffic_ports:] +
                             all_ports_after_split[PerfConsts.DUT_ALIAS]["right_split_ports"][1:]
                         )
                     }
                 }
                 }
    return conf_args
