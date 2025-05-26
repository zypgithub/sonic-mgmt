"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
from ngts.constants.constants import CliType
import pytest
import logging
import allure
import copy
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration, skip_test_on_unsupported_os)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata
logger = logging.getLogger()

TESTS_SCENARIO = "ar_vs_random"


@pytest.fixture(scope='module', autouse=True)
def skip_test_conditionally(players):
    skip_test_on_unsupported_os(players['dut']['cli'], CliType.NVUE)
    yield


@pytest.fixture(scope='function', autouse=True)
def conf_args(bisection_traffic, ecmp_type_ar, one_to_one_leaf_scenario):
    conf_args = {"run_fw_latency_optimization": "False",
                 "auto_buffer_mode": "False",
                 "congestion_thresh_lo": PerfConsts.LOW_AR_THRESHOLD,
                 "two_sided_ar": False,
                 "is_ipv6": False,
                 "split_right": 2,
                 "split_left": 2,
                 "host": "right_tg",
                 "spine": "left_tg",
                 "scenario": TESTS_SCENARIO,
                 "packet_size": PerfConsts.PACKET_SIZE_LIST[0],
                 "left_num_packets": 2,
                 "right_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
                 "speed": "400000000",
                 "ecmp_type_ar": ecmp_type_ar,
                 "bisection_traffic": bisection_traffic,
                 "one_to_one_leaf_scenario": one_to_one_leaf_scenario,
                 "params": None
                 }
    return conf_args


@pytest.fixture(scope='function', autouse=True)
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
def update_test_mongo_metadata(request, players, is_ipv6, port_group_df, bisection_traffic, ecmp_type_ar):
    test_name = get_perf_test_name(request, is_ipv6)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"ar_vs_random_leaf_{'with' if bisection_traffic else 'without'}"
                                        f"_bisection_traffic_{'AR' if ecmp_type_ar else 'Random'}",
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
