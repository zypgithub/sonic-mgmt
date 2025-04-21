"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata, get_perf_test_name
import pytest
import logging
import allure
import re
from ngts.helpers.general_helper import get_pytest_test_name
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration)
from ngts.constants.performance_constants import MongoDbConsts, PerfConsts, SPCXRAConsts

logger = logging.getLogger()
TESTS_SCENARIO = "lossy_lossless"


@pytest.fixture(scope='session', autouse=True)
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
def update_test_mongo_metadata(request, is_ipv6, port_group_df):
    test_name = get_perf_test_name(request.node.name, is_ipv6)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"{TESTS_SCENARIO}_basic_scenarios",
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield


@pytest.fixture(scope='session', autouse=True)
def conf_args():
    """
    This function alters all of the jinja template files.
    """
    conf_args = {"congestion_thresh_lo": 400,
                 "auto_buffer_mode": "False",
                 "packet_size": PerfConsts.PACKET_SIZE_LIST[0],
                 "is_ipv6": False,
                 "split_right": 2,
                 "split_left": 2,
                 "two_sided_ar": True,
                 "scenario": TESTS_SCENARIO,
                 "left_num_packets": 0,
                 "right_num_packets": 0,
                 }
    return conf_args


def set_allure_lossy_lossless_title(request, scenario):
    """
    Adds scenario name to allure title.
    """
    scenario_names_dict = {1: 'All lossless test',
                           2: 'All lossy test',
                           '3a': '50% lossless traffic, 50% lossy traffic',
                           '3b': '75% lossless traffic, 25% lossy traffic'}

    test_name = get_pytest_test_name(request)
    test_name_with_scenario = re.sub(r'\[.*?\]', test_name, f"- Scenario {scenario}: {scenario_names_dict[scenario]}")

    allure.dynamic.title(test_name_with_scenario)
    return test_name_with_scenario
