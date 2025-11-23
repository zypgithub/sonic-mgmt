import json
import allure
import logging
import pytest
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.helpers.performance.performance_setup_helpers import (run_traffic, get_topology_obj, validate_traffic_results)
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
from ngts.constants.performance_constants import PerfConsts
from ngts.constants.constants import InfraConst
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_spine_traffic
from ngts.performance_tests.optimizer_tests.spcx_ra.conftest import get_conf_args

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


@pytest.mark.parametrize("basic_setup_configuration", [InfraConst.IPV4, InfraConst.IPV6], indirect=True)
class TestOptimizeSPCXRA_x2Split_400G:

    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, chip_type, cleanup, basic_setup_configuration):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.ip = InfraConst.IPV6 if basic_setup_configuration else InfraConst.IPV4
        self.is_ipv6 = basic_setup_configuration
        self.chip_type = chip_type
        self.conf_args = get_conf_args(self.is_ipv6)
        if not cleanup:
            self.traffic_jsons = get_spcx_ra_spine_traffic(self.players, self.conf_args)

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_ibm')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and IBM enabled')
    def test_ar_perf_max_bandwidth_ibm(self, request, packet_size, init, cleanup):

        test_name = get_perf_test_name(request)

        if (not init) and (not cleanup):
            with allure.step("Restart switchd to let the new AR profile take effect"):
                self.cli_object.performance.restart_daemon("switchd")

            with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
                run_traffic(self.players, self.scenario, self.traffic_jsons)

            with allure.step("Wait for nexthop resolution after restart switchd"):
                self.cli_object.performance.wait_for_nexthop_resolution(self.conf_args, timeout=240)

            with allure.step(f"Verifying the traffic for packet size {packet_size}"):
                traffic_validation_jsons_list = validate_traffic_results(players=self.players, test_name=test_name,
                                                                         scenario=self.scenario,
                                                                         samples_params_dict=PerfConsts.SAMPLES_PARAMS)
            with allure.step("Save the validation results"):
                result_dict = {}
                result_dict['Bandwidth_samples'] = traffic_validation_jsons_list[0]['traffic_json']['Bandwidth_samples']
                result_dict['TC_samples'] = traffic_validation_jsons_list[0]['traffic_json']['TC_samples']
                with open(self.conf_args['result_file_location'], 'w') as f:
                    json.dump(result_dict, f)
