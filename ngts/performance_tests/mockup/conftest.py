"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import allure
import logging
from ngts.helpers.performance.performance_setup_helpers import apply_test_configuration
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs
logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def basic_test_configuration(topology_obj, players, engines):
    apply_test_configuration(players, scenario="static_topology")
    yield
    with allure.step(f"Attaching Players Logs to Allure"):
        print_players_logs(print_to_stdout=True, players_info=players)
        remove_players_logs()
