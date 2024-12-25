import pytest
from ngts.constants.performance_constants import PerfConsts


@pytest.fixture(scope='session', autouse=True)
def set_fan_env_aliases(players):
    for tg_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        tg_engine = players[tg_alias]['engine']
        tg_engine.run_cmd(f"export PLAYER_ALIAS={tg_alias}")
