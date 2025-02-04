import pytest
import allure
import os
from ngts.helpers.performance.performance_setup_helpers import configure_mloops, stop_traffic
from ngts.constants.constants import PytestConst
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs


@pytest.fixture(scope="session")
def is_ipv6(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: app_extension_dict
    """
    if request.config.getoption('--is_ipv6'):
        return True
    return False


@pytest.fixture(scope='function', autouse=True)
def basic_test_configuration(request, players):
    request.getfixturevalue('basic_setup_configuration')
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
