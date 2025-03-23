import allure
import logging
from ngts.performance_tests.lossy_lossless.lossy_lossless_10_to_1.conftest import get_many_to_1_traffic
import pytest

from ngts.helpers.general_helper import get_pytest_test_name
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, run_traffic, run_validation,
                                                                get_topology_obj)
from ngts.constants.performance_constants import PerfConsts

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


class TestLossyLosslessManyToOne:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']

        self.conf_args = conf_args
        self.scenario = "lossy_lossless"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.chip_type = chip_type

    @pytest.fixture
    def scenario_name(self):
        return 'lossy_lossless_scenario_4_many_to_1'

    @allure.title('Lossy lossless scenario 4. Many to 1')
    @allure.description('Lossy lossless scenario 4. Send many (10) to 1 one sided traffic')
    def test_basic_loosy_lossless_scenario_4_many_to_1(self, request, scenario_name, packet_size=4096):
        test_name = get_pytest_test_name(request)
        num_lossy_packets = 8
        num_lossless_packets = 0
        self.traffic_jsons = get_many_to_1_traffic(self.conf_args, num_lossy_packets, num_lossless_packets)

        with allure.step(f"Run traffic on all the ports:"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type, bw_threshold=None,
                                      tc_occ_threshold=None,
                                      run_validate_counters=False,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)
