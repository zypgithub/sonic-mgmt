from struct import pack
import allure
import logging
import pytest
import random
from ngts.helpers.general_helper import get_pytest_test_name
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.helpers.performance.traffic_helpers import validate_bw_per_ports
from ngts.helpers.performance.performance_setup_helpers import (run_traffic, run_validation, get_topology_obj,
                                                                validate_traffic_results,
                                                                set_ports_admin_state,
                                                                skip_test_on_unsupported_os, get_obj_method)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.constants import CliType
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_leaf_traffic

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


class TestSpcX400GTo200G:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.conf_args = conf_args
        self.chip_type = chip_type

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('400G to 200G leaf test')
    @allure.description('400G<->200G test. Right side switch is leaf (200G).')
    def test_400_to_200_bw(self, request, packet_size):
        skip_test_on_unsupported_os(self.cli_object, CliType.NVUE)

        test_name = get_pytest_test_name(request)
        self.traffic_jsons = get_spcx_ra_leaf_traffic(self.players, self.conf_args)

        with allure.step(f"Run traffic on all the ports. Packet size is {packet_size} bytes"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)
        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(chip_type=self.chip_type, players=self.players, test_name=test_name, scenario=self.scenario,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                           power_threshold=self.power_thresholds_by_chip_type)
