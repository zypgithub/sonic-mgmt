"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
import allure
import copy
import os
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from ngts.constants.nv_optimizer_constant import EnvVariables
from ngts.helpers.performance.performance_setup_helpers import get_perf_test_name, add_test_mongo_metadata
from ngts.constants.performance_constants import MongoDbConsts

logger = logging.getLogger()
TESTS_SCENARIO = "spcx_ra"


@pytest.fixture(scope='class', autouse=True)
def conf_args(is_ipv6, performance_parameters):
    conf_args = {
        "auto_buffer_mode": "False",
        "congestion_thresh_lo": 400,
        "two_sided_ar": True,
        "is_ipv6": is_ipv6,
        "split_right": 2,
        "split_left": 2,
        "scenario": TESTS_SCENARIO,
        "packet_size": PerfConsts.PACKET_SIZE_LIST[0],
        "left_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
        "right_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
        "speed": "400000000",
                 "params": performance_parameters,
                 "result_file_location": os.path.join(str(EnvVariables.ngts_dir), str(EnvVariables.result_parameter_file))
    }
    return conf_args


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args, init, cleanup):
    try:
        with allure.step('Save Players initial Configuration only during setup initialization'):
            if init:
                save_base_configuration(players)
        with allure.step("Apply Test configuration on all Players only during setup initialization"):
            if init:
                apply_test_configuration(players, scenario=TESTS_SCENARIO, conf_args=conf_args)
        yield
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration only when cleanup is called'):
            if cleanup:
                restore_basic_configuration(players)


@pytest.fixture(scope='function', autouse=False)
def ibm_fixture(players, conf_args):
    with allure.step("Set IBM in accordance with the test configuration"):
        players['dut']['cli'].performance.set_ibm(TESTS_SCENARIO, conf_args)


@pytest.fixture(scope='function', autouse=True)
def update_test_mongo_metadata(request, players, is_ipv6, port_group_df):

    test_name = get_perf_test_name(request, is_ipv6)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: "switch_perf_optimizer",
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
