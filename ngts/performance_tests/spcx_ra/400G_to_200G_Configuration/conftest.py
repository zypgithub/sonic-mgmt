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
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata
from ngts.constants.constants import CliType
from ngts.helpers.performance.performance_setup_helpers import skip_test_on_unsupported_os

logger = logging.getLogger()
TESTS_SCENARIO = "spcx_ra"


@pytest.fixture(scope='module', autouse=True)
def skip_test_conditionally(players):
    skip_test_on_unsupported_os(players['dut']['cli'], CliType.NVUE)
    yield


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args):
    try:
        with allure.step('Save Players initial Configuration'):
            # Relevant mostly for CL/Sonic- Save config for later cleanup
            save_base_configuration(players)
        with allure.step("Apply Test configuration on all Players"):
            # Apply the configuration from all of the jinja files and run the test.
            apply_test_configuration(players, scenario=TESTS_SCENARIO, conf_args=conf_args)
        yield
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            # In DVS- dvs_stop & start. CL/Sonic- Reload base config file
            restore_basic_configuration(players)


@pytest.fixture(scope='class', autouse=True)
def conf_args():
    """
    This function alters all of the jinja template files.
    """
    conf_args = {"run_fw_latency_optimization": "False",
                 "auto_buffer_mode": "False",
                 "congestion_thresh_lo": PerfConsts.LOW_AR_THRESHOLD,
                 "is_ipv6": False,
                 "split_right": 4,
                 "split_left": 2,
                 "host": "right_tg",
                 "spine": "left_tg",
                 "shaper_value": 0.975,
                 "packet_size": PerfConsts.PACKET_SIZE_LIST[0],
                 "left_num_packets": 1,
                 "right_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
                 "two_sided_ar": False,
                 "scenario": TESTS_SCENARIO
                 }
    return conf_args


@pytest.fixture(scope='function', autouse=True)
def update_test_mongo_metadata(request, players, is_ipv6, port_group_df):
    test_name = get_perf_test_name(request, is_ipv6)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: "400G_to_200G_leaf",
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
