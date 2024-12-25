"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
import allure
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration,
                                                                restore_basic_configuration,
                                                                apply_test_configuration, set_ibm)

logger = logging.getLogger()
TESTS_SCENARIO = "spcx_ra/split_x2_400G_configuration"


@pytest.fixture(scope='session', autouse=True)
def basic_setup_configuration(players):
    try:
        with allure.step('Save Players initial Configuration'):
            save_base_configuration(players)
        with allure.step("Set Ingress Buffer Mode Configuration on Dut"):
            set_ibm(players, scenario=TESTS_SCENARIO, ibm_mode=False)
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(players, scenario=TESTS_SCENARIO)
        yield
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            restore_basic_configuration(players)


@pytest.fixture(scope='function', autouse=False)
def ibm_fixture(players):
    with allure.step("Set IBM to true"):
        set_ibm(players, scenario=TESTS_SCENARIO, ibm_mode=True, reload_conf=True)
    yield
    with allure.step("Set IBM to false"):
        set_ibm(players, scenario=TESTS_SCENARIO, ibm_mode=False, reload_conf=True)
