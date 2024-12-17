"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
import allure
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.performance.performance_setup_helpers import (save_base_configuration, stop_traffic,
                                                                restore_basic_configuration, apply_test_configuration)
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs

logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def set_fan_env_aliases(players):
    for tg_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        tg_engine = players[tg_alias]['engine']
        tg_engine.run_cmd(f"export PLAYER_ALIAS={tg_alias}")


@pytest.fixture(scope='session', autouse=True)
def basic_setup_configuration(players):
    try:
        with allure.step('Save Players initial Configuration'):
            save_base_configuration(players)
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(players, scenario="spcx_ra/split_x1_800G_configuration")
            yield
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            restore_basic_configuration(players)
