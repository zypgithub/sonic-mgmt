import allure
import logging
import pytest
import json
from ngts.helpers.general_helper import get_pytest_test_name
from ngts.helpers.performance.performance_setup_helpers import (run_traffic, get_topology_obj,
                                                                validate_traffic_results)
from ngts.performance_tests.lossy_lossless.lossy_lossless_basic_scenarios_1_2_3.conftest import set_allure_lossy_lossless_title
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from ngts.performance_tests.lossy_lossless.conftest import get_lossy_lossless_basic_traffic

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST
results_dict = {}


class TestOptimizeLossyLossless:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type, is_ipv6):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']

        self.conf_args = conf_args
        self.scenario = "lossy_lossless"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.chip_type = chip_type
        self.is_ipv6 = is_ipv6

    @pytest.mark.parametrize("scenario_name, num_lossy_packets,num_lossless_packets", [("lossy_lossless_scenario_1", 0, 8), ("lossy_lossless_scenario_2", 8, 0),
                                                                                       ("lossy_lossless_scenario_3a", 4, 4), ("lossy_lossless_scenario_3b", 2, 6)])
    @allure.title('Optimization run for 400G<->400G lossy lossless test')
    @allure.description('400G<->400G test. Send lossy traffic from both sides.')
    def test_basic_loosy_lossless_tests_1_2_3(self, request, scenario_name, num_lossy_packets, num_lossless_packets,
                                              init, cleanup, packet_size=4096):

        with allure.step(f"Set test correct allure title with {scenario_name} parameter"):
            test_name = set_allure_lossy_lossless_title(request, scenario_name, self.is_ipv6)

        if (not init) and (not cleanup):
            self.traffic_jsons = get_lossy_lossless_basic_traffic(self.players, self.conf_args, num_lossy_packets,
                                                                  num_lossless_packets)

            with allure.step(f"Run traffic on all the ports. "
                             f"lossy percentage is {(num_lossy_packets / (num_lossy_packets + num_lossless_packets)) * 100}%.\n"
                             f"lossless percentage is {(num_lossless_packets / (num_lossy_packets + num_lossless_packets)) * 100}%"):
                run_traffic(self.players, self.scenario, self.traffic_jsons)

            with allure.step(f"Verifying the traffic for packet size {packet_size}"):
                traffic_validation_jsons_list = validate_traffic_results(players=self.players, test_name=test_name,
                                                                         scenario=self.scenario,
                                                                         samples_params_dict=PerfConsts.SAMPLES_PARAMS)
            with allure.step("Save the validation results"):
                results_dict[test_name] = {}
                results_dict[test_name]['Bandwidth_samples'] = traffic_validation_jsons_list[0]['Bandwidth_samples']
                results_dict[test_name]['TC_samples'] = traffic_validation_jsons_list[0]['TC_samples']
                with open(self.conf_args['result_file_location'], 'w') as f:
                    json.dump(results_dict, f)
