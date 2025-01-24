import pytest
import logging
import os
from ngts.constants.performance_constants import PerfConsts
from ngts.constants.constants import BugHandlerConst
from ngts.helpers.performance.traffic_helpers import create_json_traffic_file

logger = logging.getLogger()
TESTS_SCENARIO = "spcx_ra"


@pytest.fixture(scope='session', autouse=True)
def power_thresholds_by_chip_type(chip_type):
    return PerfConsts.POWER_TH_PER_ASIC[chip_type]


def get_spcx_ra_spine_traffic(players, conf_args, template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    pkt_size = PerfConsts.PACKET_SIZE_LIST[0]
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 TESTS_SCENARIO, f"{player_alias}_{TESTS_SCENARIO.replace('/', '_')}_{pkt_size}.json")
        traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=TESTS_SCENARIO,
                                                                               conf_args=conf_args)
        create_json_traffic_file(player_alias=player_alias, traffic_parameters=traffic_parameters, json_path=json_path)
        traffic_jsons[player_alias] = json_path
    return traffic_jsons
