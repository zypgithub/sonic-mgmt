"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
import allure
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration, stop_traffic,
                                                                restore_basic_configuration, apply_test_configuration)
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs

logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def basic_test_configuration(players):
    try:
        with allure.step('Save Players initial Configuration'):
            save_base_configuration(players)
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(players, scenario="spcx_ra/split_x1_800G_configuration")
            yield
        with allure.step('Stop Traffic on Traffic Generators'):
            stop_traffic(players)
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            restore_basic_configuration(players)
        with allure.step(f"Attaching Players Logs to Allure"):
            print_players_logs(print_to_stdout=True, players_info=players)
            remove_players_logs()
