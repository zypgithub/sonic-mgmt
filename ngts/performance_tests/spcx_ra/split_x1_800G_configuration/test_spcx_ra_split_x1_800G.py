
import allure
import logging
import pytest

from ngts.helpers.performance.performance_setup_helpers import (run_traffic, traffic_validation)
from ngts.constants.performance_constants import PerfConsts
logger = logging.getLogger()

PACKET_SIZE_TO_MAX_BW_DICT = PerfConsts.DUT_TX_UTIL_TH_DICT
PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


class TestSPCXRA_x1Split_800G:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, players, engines):
        self.topology_obj = topology_obj
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra/split_x1_800G_configuration"

    @pytest.mark.parameterize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth')
    @allure.description('Calculate the port utilization on the DUT with AR enabled, with various packet sizes (1500, 2000, 4000) and default AR profile.')
    def test_ar_perf_max_bandwidth(self, packet_size):

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            traffic_validation(self.players, self.scenario, b_w_threshold=PACKET_SIZE_TO_MAX_BW_DICT[packet_size])
