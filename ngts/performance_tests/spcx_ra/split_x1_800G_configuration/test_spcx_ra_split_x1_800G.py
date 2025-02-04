import allure
import logging
import pytest
from ngts.helpers.performance.performance_setup_helpers import (restore_basic_configuration, apply_test_configuration,
                                                                run_traffic, run_validation, get_topology_obj,
                                                                get_performance_pytest_test_name,
                                                                skip_test_on_unsupported_os, set_allure_title)
from ngts.constants.constants import CliType, InfraConst
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_spine_traffic, get_spcx_ra_leaf_traffic
logger = logging.getLogger()


class TestSPCXRA_x1Split_800G:

    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.traffic_jsons = get_spcx_ra_spine_traffic(players, conf_args)
        self.ip = InfraConst.IPV6 if conf_args["is_ipv6"] else InfraConst.IPV4
        self.chip_type = chip_type

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and default AR profile.')
    def test_ar_perf_max_bandwidth(self, request, packet_size):
        pytest.xfail(f"test_ar_perf_max_bandwidth expected to on 800G with auto buffer mode")
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.ip)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                           chip_type=self.chip_type,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=None,
                           power_threshold=self.power_thresholds_by_chip_type)

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_ibm')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and IBM enabled')
    def test_ar_perf_max_bandwidth_ibm(self, request, packet_size, ibm_fixture):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.ip)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                           chip_type=self.chip_type,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=None,
                           power_threshold=self.power_thresholds_by_chip_type)

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_leaf')
    @allure.description('Calculate the port utilization on the DUT with AR enabled on one side')
    def test_ar_perf_max_bandwidth_leaf(self, request, packet_size, conf_args):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.ip)

        conf_args["two_sided_ar"] = False
        leaf_traffic_jsons = get_spcx_ra_leaf_traffic(self.players, conf_args)
        restore_basic_configuration(players=self.players, players_aliases=PerfConsts.PERF_SETUP_DUT_ALIASES)
        apply_test_configuration(players=self.players, players_aliases=PerfConsts.PERF_SETUP_DUT_ALIASES,
                                 scenario=self.scenario, conf_args=conf_args)
        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, leaf_traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                           chip_type=self.chip_type,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=None,
                           power_threshold=self.power_thresholds_by_chip_type)
