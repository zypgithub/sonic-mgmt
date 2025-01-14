import pytest
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts


@pytest.fixture(scope='session', autouse=True)
def set_fan_env_aliases(players):
    for tg_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        tg_engine = players[tg_alias]['engine']
        tg_engine.run_cmd(f"export PLAYER_ALIAS={tg_alias}")


@pytest.fixture(scope='session', autouse=True)
def power_thresholds_by_chip_type(chip_type):
    return PerfConsts.POWER_TH_PER_ASIC[chip_type]
