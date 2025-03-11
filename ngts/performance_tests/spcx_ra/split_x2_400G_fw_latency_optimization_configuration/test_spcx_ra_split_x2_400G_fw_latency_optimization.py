import allure
import logging
import pytest

from ngts.helpers.performance.performance_setup_helpers import (run_traffic, run_validation,
                                                                set_allure_title,
                                                                skip_test_on_unsupported_os)
from ngts.constants.constants import CliType, InfraConst
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_spine_traffic

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


class TestSPCXRA_x2Split_400G:

    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type, is_ipv6):
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.traffic_jsons = get_spcx_ra_spine_traffic(players, conf_args)
        self.ip = InfraConst.IPV6 if is_ipv6 else InfraConst.IPV4
        self.is_ipv6 = is_ipv6
        self.chip_type = chip_type

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and default AR profile.')
    def test_ar_perf_max_bandwidth(self, request, packet_size):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.is_ipv6)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                                      tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_ibm')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and IBM enabled')
    def test_ar_perf_max_bandwidth_ibm(self, request, packet_size, ibm_fixture):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.is_ipv6)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[packet_size],
                                      samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                                      tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)
