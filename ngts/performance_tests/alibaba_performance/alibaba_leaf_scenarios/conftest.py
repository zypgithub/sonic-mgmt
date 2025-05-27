"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
import allure
import copy
import ipaddress
from dataclasses import dataclass
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts
from ngts.performance_tests.conftest import get_all_players_ports
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata
from ngts.helpers.performance.traffic_helpers import generate_incremental_addresses

logger = logging.getLogger()

TESTS_SCENARIO = "alibaba_performance"


@dataclass
class TestParameters:
    """Data class to hold test parameters"""
    shaper_value: float
    packet_size: int
    ar_enabled: bool
    split_host_ports: int
    test_id: str


@pytest.fixture(scope='class')
def test_params(request):
    """Fixture to provide test parameters with class scope"""
    return request.param


@pytest.fixture(scope='class')
def shaper_value(test_params):
    """Extract shaper_value from test_params"""
    return test_params.shaper_value


@pytest.fixture(scope='class')
def packet_size(test_params):
    """Extract packet_size from test_params"""
    return test_params.packet_size


@pytest.fixture(scope='class')
def ar_enabled(test_params):
    """Extract ar_enabled from test_params"""
    return test_params.ar_enabled


@pytest.fixture(scope='class')
def split_host_ports(test_params):
    """Extract split_host_ports from test_params"""
    return test_params.split_host_ports


@pytest.fixture(scope='class')
def test_id(test_params):
    """Extract test_id from test_params"""
    return test_params.test_id


@pytest.fixture(scope='class', autouse=True)
def conf_args(players, shaper_value, packet_size, ar_enabled, split_host_ports):

    all_ports_after_split = get_all_players_ports(players, split_host_ports, 2)
    num_host_ports = len(all_ports_after_split[PerfConsts.DUT_ALIAS]["right_split_ports"])

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
                 "packet_size": packet_size,
                 "left_num_packets": 1,
                 "left_num_dip_to_send": num_host_ports,
                 "right_num_packets": 2,
                 "right_num_dip_to_send": 60 if ar_enabled else 64,
                 "num_routes_ipv4": 64000,
                 "num_routes_ipv6": 64000,
                 "disable_locality": True,
                 "set_lpm_root": True,
                 "hash_type": "crc",
                 "ecmp_size": 512,
                 "is_ipv6": False,  # Changed in test
                 "is_ipv4": True,  # Changed in test
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
    right_side_ipv4_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_left_to_right_start"],
                                                                 conf_args["dip_left_to_right_start_ipv4"],
                                                                 int(conf_args["num_routes_ipv4"] / 2))

    left_side_ipv4_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_right_to_left_start"],
                                                                conf_args["dip_right_to_left_start_ipv4"],
                                                                int(conf_args["num_routes_ipv4"] / 2))

    right_side_ipv6_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_left_to_right_start"],
                                                                 conf_args["dip_left_to_right_start_ipv6"],
                                                                 int(conf_args["num_routes_ipv6"] / 2))

    left_side_ipv6_to_mac_list = generate_incremental_addresses(conf_args["neigh_mac_right_to_left_start"],
                                                                conf_args["dip_right_to_left_start_ipv6"],
                                                                int(conf_args["num_routes_ipv6"] / 2))

    conf_args["ip_to_mac_dict"] = {"left": {"ipv4": left_side_ipv4_to_mac_list, "ipv6": left_side_ipv6_to_mac_list},
                                   "right": {"ipv4": right_side_ipv4_to_mac_list, "ipv6": right_side_ipv6_to_mac_list}}

    return conf_args


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


@pytest.fixture(scope='function', autouse=True)
def update_test_mongo_metadata(request, port_group_df):
    test_name = get_perf_test_name(request)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: test_name,
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
