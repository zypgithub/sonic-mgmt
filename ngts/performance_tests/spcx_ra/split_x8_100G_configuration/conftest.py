import pytest
import logging
import allure
import copy
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration, skip_test_on_unsupported_chip_type)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata
from ngts.constants.constants import InfraConst
logger = logging.getLogger()
TESTS_SCENARIO = "spcx_ra"


@pytest.fixture(scope='module', autouse=True)
def skip_test_conditionally(chip_type):
    skip_test_on_unsupported_chip_type(chip_type, "SPC4")
    yield


def get_conf_args(is_ipv6):
    conf_args = {"run_fw_latency_optimization": "False",
                 "auto_buffer_mode": "False",
                 "congestion_thresh_lo": PerfConsts.LOW_AR_THRESHOLD,
                 "two_sided_ar": True,
                 "is_ipv6": is_ipv6,
                 "split_right": 8,
                 "split_left": 8,
                 "scenario": TESTS_SCENARIO,
                 "shaper_value": 0.975,
                 "packet_size": PerfConsts.PACKET_SIZE_LIST[0],
                 "left_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
                 "right_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
                 "speed": "100000000",
                 "params": None
                 }
    return conf_args


def apply_basic_setup_configuration(is_ipv6, players):
    conf_args = get_conf_args(is_ipv6)
    with allure.step('Save Players initial Configuration'):
        save_base_configuration(players)
    with allure.step("Apply Test configuration on all Players"):
        apply_test_configuration(players, scenario=TESTS_SCENARIO, conf_args=conf_args)


@pytest.fixture(scope='class')
def basic_setup_configuration(request, players):
    is_ipv6 = request.param == InfraConst.IPV6
    try:
        apply_basic_setup_configuration(is_ipv6, players)
        yield is_ipv6
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            restore_basic_configuration(players)


@pytest.fixture(scope='function', autouse=False)
def ibm_fixture(players, basic_setup_configuration):
    conf_args = get_conf_args(basic_setup_configuration)
    copied_conf_args = copy.deepcopy(conf_args)
    copied_conf_args["auto_buffer_mode"] = "True"
    with allure.step("Set auto buffer mode to True"):
        players['dut']['cli'].performance.set_ibm(TESTS_SCENARIO, copied_conf_args)
    yield
    with allure.step("Set auto buffer mode to False"):
        players['dut']['cli'].performance.set_ibm(TESTS_SCENARIO, conf_args)


@pytest.fixture(scope='function', autouse=True)
def update_test_mongo_metadata(request, port_group_df):
    test_name = get_perf_test_name(request)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: "x8_100G_spine",
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
