"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
import allure
import copy
import os
import ipaddress
from dataclasses import dataclass
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts, MultiNosSharedData
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata
from ngts.constants.constants import BugHandlerConst
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.helpers.performance.traffic_helpers import generate_incremental_addresses

logger = logging.getLogger()


@dataclass(frozen=True)
class PacketSizeKey:
    """Data class for packet size mapping key - frozen to make it hash able"""
    test_id: str
    is_ipv4: bool
    is_ipv6: bool


# Test ID constants
TEST_ID_SHAPER_97_5_AR_ENABLED_SPLIT_4_64K_DIPS = "shaper_97.5_pkt_size_1900_ar_enabled_split_4_host_ports_64000_dips_to_host_64000_dips_to_spine"
TEST_ID_SHAPER_99_9_AR_ENABLED_SPLIT_4_128_DIPS = "shaper_99.9_pkt_size_4096_ar_enabled_split_4_host_ports_128_dips_to_host_60_dips_to_spine"
TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_4_64K_DIPS = "shaper_97.5_pkt_size_1900_ar_disabled_split_4_host_ports_64000_dips_to_host_64000_dips_to_spine"
TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_2_64K_DIPS = "shaper_97.5_pkt_size_2000_ar_disabled_split_2_host_ports_64000_dips_to_host_64000_dips_to_spine"

# Dictionary mapping PacketSizeKey to packet_size
PACKET_SIZE_MAPPING = {
    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_ENABLED_SPLIT_4_64K_DIPS, True, False): 2000,
    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_ENABLED_SPLIT_4_64K_DIPS, False, True): 2000,
    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_ENABLED_SPLIT_4_64K_DIPS, True, True): 2100,

    PacketSizeKey(TEST_ID_SHAPER_99_9_AR_ENABLED_SPLIT_4_128_DIPS, True, False): PerfConsts.PACKET_SIZE_4K,
    PacketSizeKey(TEST_ID_SHAPER_99_9_AR_ENABLED_SPLIT_4_128_DIPS, False, True): PerfConsts.PACKET_SIZE_4K,
    PacketSizeKey(TEST_ID_SHAPER_99_9_AR_ENABLED_SPLIT_4_128_DIPS, True, True): PerfConsts.PACKET_SIZE_4K,

    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_4_64K_DIPS, True, False): 2100,
    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_4_64K_DIPS, False, True): 2100,
    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_4_64K_DIPS, True, True): PerfConsts.PACKET_SIZE_4K,

    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_2_64K_DIPS, True, False): 2100,
    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_2_64K_DIPS, False, True): 2100,
    PacketSizeKey(TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_2_64K_DIPS, True, True): PerfConsts.PACKET_SIZE_4K,
}


def get_packet_size_for_test(test_id, is_ipv4, is_ipv6):
    """
    Get the packet size for a specific test configuration.

    Args:
        test_id (str): The test identifier
        is_ipv4 (bool): True if IPv4 is enabled
        is_ipv6 (bool): True if IPv6 is enabled

    Returns:
        int: The packet size for this configuration, or None if not found
    """
    key = PacketSizeKey(test_id, is_ipv4, is_ipv6)
    return PACKET_SIZE_MAPPING.get(key)


TESTS_SCENARIO = "alibaba_performance"


@dataclass
class TestParameters:
    """Data class to hold test parameters"""
    shaper_value: float
    ar_enabled: bool
    split_host_ports: int
    num_left_dips: int
    num_right_dips: int
    test_id: str


@dataclass
class TestIPCombinations:
    """Data class to hold ip combinations"""
    ipv4_enabled: str
    ipv6_enabled: str


@pytest.fixture(scope='class')
def test_params(request):
    """Fixture to provide test parameters with class scope"""
    return request.param


@pytest.fixture(scope='class')
def shaper_value(test_params):
    """Extract shaper_value from test_params"""
    return test_params.shaper_value


@pytest.fixture(scope='class')
def ar_enabled(test_params):
    """Extract ar_enabled from test_params"""
    return test_params.ar_enabled


@pytest.fixture(scope='class')
def split_host_ports(test_params):
    """Extract split_host_ports from test_params"""
    return test_params.split_host_ports


@pytest.fixture(scope='class')
def num_left_dips(test_params):
    """Extract num_left_packets from test_params"""
    return test_params.num_left_dips


@pytest.fixture(scope='class')
def num_right_dips(test_params):
    """Extract num_right_packets from test_params"""
    return test_params.num_right_dips


@pytest.fixture(scope='class')
def test_id(test_params):
    """Extract test_id from test_params"""
    return test_params.test_id


@pytest.fixture(scope='class')
def ip_combinations(request):
    """Fixture to provide test parameters with class scope"""
    return request.param


@pytest.fixture(scope='class')
def ipv4_enabled(ip_combinations):
    """Extract ipv4_enabled from ip_combinations"""
    return ip_combinations.ipv4_enabled


@pytest.fixture(scope='class')
def ipv6_enabled(ip_combinations):
    """Extract ipv6_enabled from ip_combinations"""
    return ip_combinations.ipv6_enabled


@pytest.fixture(scope='class', autouse=True)
def conf_args(test_params, shaper_value, ar_enabled, split_host_ports, num_left_dips, num_right_dips, ipv4_enabled, ipv6_enabled):

    conf_args = {"run_fw_latency_optimization": "False",
                 "auto_buffer_mode": "False",
                 "congestion_thresh_lo": 190,
                 "two_sided_ar": False,
                 "ar_enabled": ar_enabled,
                 "split_right": split_host_ports,
                 "split_left": 2,
                 "host": "right_tg",
                 "spine": "left_tg",
                 "scenario": TESTS_SCENARIO,
                 "packet_size": get_packet_size_for_test(test_params.test_id, ipv4_enabled == "ipv4_enabled", ipv6_enabled == "ipv6_enabled"),
                 "left_num_packets": 36,
                 "left_num_dip_to_send": num_left_dips,
                 "right_num_packets": 72 // split_host_ports,
                 "right_num_dip_to_send": num_right_dips,
                 "num_routes_ipv4": 64000,
                 "num_routes_ipv6": 64000,
                 "disable_locality": True,
                 "set_lpm_root": True,
                 "hash_type": "crc",
                 "ecmp_size": 512,
                 "is_ipv4": ipv4_enabled == "ipv4_enabled",
                 "is_ipv6": ipv6_enabled == "ipv6_enabled",
                 "ipv4_source_ip": "4.4.4.4",
                 "ipv6_source_ip": "192:168:0:0:0:0:0:1",
                 "dip_left_to_right_start_ipv4": "10.0.1.0",
                 "dip_left_to_right_start_ipv6": "2001:db8::2",
                 "dip_right_to_left_start_ipv4": "192.168.1.0",
                 "dip_right_to_left_start_ipv6": "192:168:5:1:1:1:2:0",
                 "neigh_mac_left_to_right_start": "00:00:00:00:10:70",
                 "neigh_mac_right_to_left_start": "00:01:02:03:04:08",
                 "is_leaf_scenario": True,
                 "shaper_value": shaper_value,
                 "params": None
                 }
    # Reduce scale in case of 64K dips in IPv6- not enough space in KVD.
    if ipv4_enabled == "ipv4_disabled" and ipv6_enabled == "ipv6_enabled" and conf_args['left_num_dip_to_send'] == 64000:
        conf_args['left_num_dip_to_send'] = 55000
        conf_args['right_num_dip_to_send'] = 55000
        conf_args['num_routes_ipv6'] = 55000

    right_side_ipv4_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_right_to_left_start"],
                                                                 conf_args["dip_right_to_left_start_ipv4"],
                                                                 int(conf_args["num_routes_ipv4"]))

    left_side_ipv4_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_left_to_right_start"],
                                                                conf_args["dip_left_to_right_start_ipv4"],
                                                                int(conf_args["num_routes_ipv4"]))

    right_side_ipv6_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_right_to_left_start"],
                                                                 conf_args["dip_right_to_left_start_ipv6"],
                                                                 int(conf_args["num_routes_ipv6"]))

    left_side_ipv6_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_left_to_right_start"],
                                                                conf_args["dip_left_to_right_start_ipv6"],
                                                                int(conf_args["num_routes_ipv6"]))

    conf_args["ip_to_mac_dict"] = {"left": {"ipv4": left_side_ipv4_to_mac_list, "ipv6": left_side_ipv6_to_mac_list},
                                   "right": {"ipv4": right_side_ipv4_to_mac_list, "ipv6": right_side_ipv6_to_mac_list}}

    return conf_args


@pytest.fixture(scope='class', autouse=True)
def move_alibaba_acl_dump(players):
    """
    Move the Alibaba ACL dump to the DUT, using the shared JSON file.
    """

    acl_dump_path = '/tmp'
    acl_dump_name = 'acl_list.txt'
    players[PerfConsts.DUT_ALIAS]['cli'].performance.write_shared_json(key=MultiNosSharedData.ALIBABA_ACL_DUMP_PATH, data=acl_dump_path)
    players[PerfConsts.DUT_ALIAS]['cli'].performance.write_shared_json(key=MultiNosSharedData.ALIBABA_ACL_DUMP_NAME, data=acl_dump_name)
    acl_dump_original_file = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", TESTS_SCENARIO, "acl_list.txt")

    player_cli_obj = players[PerfConsts.PERF_SETUP_DUT_ALIASES[0]]['cli']
    player_cli_obj.performance.engine.copy_file(
        source_file=acl_dump_original_file,
        file_system=acl_dump_path,
        dest_file=acl_dump_name,
        overwrite_file=True,
        verify_file=False
    )


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args, move_alibaba_acl_dump):
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
            # TODO: Remove this once we have a better way to undo SDK tests
            if is_redmine_issue_active([4644033])[0]:
                player_cli_obj = players[PerfConsts.PERF_SETUP_DUT_ALIASES[0]]['cli']
                player_cli_obj.performance.execute_cmd('> /var/log/syslog')


@pytest.fixture(scope='function', autouse=True)
def update_test_mongo_metadata(request, port_group_df):
    test_name = get_perf_test_name(request)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: test_name,
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
