import os
import allure
import pytest
from ngts.constants.constants import PytestConst
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs
from ngts.helpers.performance.performance_setup_helpers import configure_mloops, stop_traffic


@pytest.fixture(scope='function', autouse=True)
def basic_test_configuration(players):
    try:
        with allure.step('Disable default sysdump generation'):
            os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "False"
        with allure.step('Configure Mloops on Traffic Generators'):
            configure_mloops(players)
        yield
        with allure.step('Stop Traffic on Traffic Generators'):
            stop_traffic(players)
    except Exception as e:
        raise e
    finally:
        with allure.step(f"Attaching Players Logs to Allure"):
            print_players_logs(print_to_stdout=True, players_info=players)
            remove_players_logs()
