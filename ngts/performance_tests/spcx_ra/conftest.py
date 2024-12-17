import pytest
import allure
from ngts.helpers.performance.performance_setup_helpers import stop_traffic
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs
from ngts.constants.performance_constants import PerfConsts


@pytest.fixture(scope='session', autouse=True)
def set_fan_env_aliases(players):
    for tg_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        tg_engine = players[tg_alias]['engine']
        tg_engine.run_cmd(f"export PLAYER_ALIAS={tg_alias}")


@pytest.fixture(scope='function', autouse=True)
def basic_test_teardown(players):
    try:
        yield
        with allure.step('Stop Traffic on Traffic Generators'):
            stop_traffic(players)
    except Exception as e:
        raise e
    finally:
        with allure.step(f"Attaching Players Logs to Allure"):
            print_players_logs(print_to_stdout=True, players_info=players)
            remove_players_logs()
