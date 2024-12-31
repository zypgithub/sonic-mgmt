import allure
import logging
import pytest

from ngts.helpers.general_helper import get_pytest_test_name
from ngts.helpers.performance.performance_setup_helpers import run_traffic, traffic_validation
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


class TestSPCXRA_x2Split_400G:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, players, engines):
        self.topology_obj = topology_obj
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra/split_x2_400G_configuration"

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth')
    @allure.description('Calculate the port utilization on the DUT with AR enabled, '
                        'with various packet sizes (1500, 2000, 4000) and default AR profile.')
    def test_ar_perf_max_bandwidth(self, request, packet_size):

        test_name = get_pytest_test_name(request)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size=packet_size,
                        num_packets=SPCXRAConsts.PACKET_NUM_400G_x2)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            traffic_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                               bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                               samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                               tc_occ_threshold=PerfConsts.OCC_AVG_TH)

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_ibm')
    @allure.description('Calculate the port utilization on the DUT with AR enabled, '
                        'with various packet sizes (1500, 2000, 4000) and IBM enabled')
    def test_ar_perf_max_bandwidth_ibm(self, request, packet_size, ibm_fixture):

        test_name = get_pytest_test_name(request)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            traffic_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                               bw_threshold=SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[packet_size],
                               samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                               tc_occ_threshold=PerfConsts.OCC_AVG_TH)
