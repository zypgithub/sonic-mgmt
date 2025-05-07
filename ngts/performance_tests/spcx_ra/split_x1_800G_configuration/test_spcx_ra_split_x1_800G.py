import allure
import logging
import pytest
from ngts.constants.constants import CliType, InfraConst
from ngts.helpers.performance.performance_setup_helpers import (restore_basic_configuration, apply_test_configuration,
                                                                run_traffic, run_validation, get_topology_obj,
                                                                skip_test_on_unsupported_os, set_allure_title,
                                                                ValidationConfig)
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_spine_traffic, get_spcx_ra_leaf_traffic
from infra.tools.redmine.redmine_api import is_redmine_issue_active, get_issues_status
from ngts.cli_wrappers.nvue.nvue_cli import NvueCli

logger = logging.getLogger()


class TestSPCXRA_x1Split_800G:

    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type, is_ipv6, set_ibm):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.traffic_jsons = get_spcx_ra_spine_traffic(players, conf_args)
        self.chip_type = chip_type
        self.ip = InfraConst.IPV6 if is_ipv6 else InfraConst.IPV4
        self.is_ipv6 = is_ipv6
        self.conf_args = conf_args

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and default AR profile.')
    def test_ar_perf_max_bandwidth(self, request, packet_size, ibm_fixture):

        if isinstance(self.cli_object, NvueCli):
            pytest.mark.xfail(reason="test_ar_perf_max_bandwidth expected to fail on Nvue")

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.is_ipv6)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        # TODO: Remove this once the issue 4335726 is fixed
        with allure.step("Wait for nexthop resolution"):
            if is_redmine_issue_active([4335726])[0]:
                self.cli_object.performance.wait_for_nexthop_resolution(self.conf_args, timeout=PerfConsts.TIMEOUT_FOR_NEXTHOP_RESOLUTION)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                                      tc_occ_threshold=None,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_ibm')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and IBM enabled')
    def test_ar_perf_max_bandwidth_ibm(self, request, packet_size):

        if isinstance(self.cli_object, NvueCli):
            pytest.mark.xfail(reason="test_ar_perf_max_bandwidth_ibm expected to fail on Nvue")

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.is_ipv6)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        # TODO: Remove this once the issue 4335726 is fixed
        with allure.step("Wait for nexthop resolution"):
            if is_redmine_issue_active([4335726])[0]:
                self.cli_object.performance.wait_for_nexthop_resolution(self.conf_args, timeout=PerfConsts.TIMEOUT_FOR_NEXTHOP_RESOLUTION)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            # Not testing BW due to Bug SW #4348288- 800G AR is NOT supported. Keeping test for future reference.
            bw_threshold = None
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                                      bw_threshold=bw_threshold,
                                      tc_occ_threshold=None,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_leaf')
    @allure.description('Calculate the port utilization on the DUT with AR enabled on one side')
    def test_ar_perf_max_bandwidth_leaf(self, request, packet_size, conf_args):

        if isinstance(self.cli_object, NvueCli):
            pytest.mark.xfail(reason="test_ar_perf_max_bandwidth_leaf expected to fail on Nvue")

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.is_ipv6)
            add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: "x1_800G_leaf"})

        conf_args["two_sided_ar"] = False
        leaf_traffic_jsons = get_spcx_ra_leaf_traffic(self.players, conf_args)
        restore_basic_configuration(players=self.players, players_aliases=PerfConsts.PERF_SETUP_DUT_ALIASES)
        apply_test_configuration(players=self.players, players_aliases=PerfConsts.PERF_SETUP_DUT_ALIASES,
                                 scenario=self.scenario, conf_args=conf_args)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, leaf_traffic_jsons)

        ar_support_800g_redmine_id = 4348288
        ar_support_status = get_issues_status([ar_support_800g_redmine_id])[str(ar_support_800g_redmine_id)]
        with allure.step(f"Verifying the traffic for packet size {packet_size}. AR support status for 800G is {ar_support_status}"):
            # skip_first_counters_iteration is True due to 800G AR not supported (bug SW #4348288 won't fix)
            skip_first_counters_iteration = not is_redmine_issue_active([ar_support_800g_redmine_id])[0] or ar_support_status == "Won't fix"
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      tc_occ_threshold=None, skip_first_counters_iteration=skip_first_counters_iteration)

            run_validation(config)
