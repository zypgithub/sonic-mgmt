"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
import os
import allure
import copy
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata
logger = logging.getLogger()
TESTS_SCENARIO = "spcx_ra"


@pytest.fixture(scope='class', autouse=True)
def conf_args(is_ipv6):
    conf_args = {"run_fw_latency_optimization": "True",
                 "auto_buffer_mode": "True",
                 "congestion_thresh_lo": 190,
                 "two_sided_ar": True,
                 "is_ipv6": is_ipv6,
                 "split_right": 2,
                 "split_left": 2,
                 "scenario": TESTS_SCENARIO,
                 "packet_size": PerfConsts.PACKET_SIZE_LIST[0],
                 "left_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
                 "right_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2}
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


@pytest.fixture(scope='function', autouse=False)
def ibm_fixture(players, conf_args):
    original_conf_args = copy.deepcopy(conf_args)
    conf_args["auto_buffer_mode"] = "False"
    with allure.step("Set IBM to true"):
        players['dut']['cli'].performance.set_ibm(TESTS_SCENARIO, conf_args)
    yield
    with allure.step("Set IBM to false"):
        players['dut']['cli'].performance.set_ibm(TESTS_SCENARIO, original_conf_args)


@pytest.fixture(scope='function', autouse=True)
def update_test_mongo_metadata(request, players, is_ipv6, port_group_df):
    test_name = get_perf_test_name(request.node.name, is_ipv6)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: "x2_400G_spine_w_fw_opt",
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
