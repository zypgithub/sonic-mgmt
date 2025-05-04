from struct import pack
import allure
import logging
import pytest
import random
from ngts.helpers.general_helper import get_pytest_test_name
from ngts.helpers.performance.traffic_helpers import validate_bw_per_ports
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, run_traffic, run_validation, get_topology_obj,
                                                                validate_traffic_results,
                                                                set_ports_admin_state,
                                                                skip_test_on_unsupported_os, get_obj_method)
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from ngts.constants.constants import CliType
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_leaf_traffic
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


class TestSpcX400GTo200G:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type, is_ipv6):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.conf_args = conf_args
        self.chip_type = chip_type
        self.is_ipv6 = is_ipv6

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('400G to 200G leaf test')
    @allure.description('400G<->200G test. Right side switch is leaf (200G).')
    def test_400_to_200_bw(self, request, packet_size):
        skip_test_on_unsupported_os(self.cli_object, CliType.NVUE)

        test_name = get_perf_test_name(request, self.is_ipv6)
        self.traffic_jsons = get_spcx_ra_leaf_traffic(self.players, self.conf_args)

        with allure.step(f"Run traffic on all the ports. Packet size is {packet_size} bytes"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)
        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            # TODO: Remove this once the issue 4426155 is fixed (change skip_first_counters_iteration to False (4426155))
            skip_first_counters_iteration = True if is_redmine_issue_active([4426155])[0] else False
            # TODO: Change to port groups (Shahaf Bodner next commit)
            bw_threshold = None
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=bw_threshold,
                                      tc_occ_threshold=PerfConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      skip_first_counters_iteration=skip_first_counters_iteration)
            run_validation(config)
