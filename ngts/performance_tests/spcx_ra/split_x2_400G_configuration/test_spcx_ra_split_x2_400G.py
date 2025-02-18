from struct import pack
import allure
import logging
import pytest
import random
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.helpers.performance.traffic_helpers import validate_bw_per_ports, validate_counters_sample
from ngts.helpers.performance.performance_setup_helpers import (run_traffic, run_validation, get_topology_obj,
                                                                validate_traffic_results,
                                                                set_ports_admin_state,
                                                                skip_test_on_unsupported_os, get_obj_method,
                                                                set_allure_title)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.constants import CliType, InfraConst
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_spine_traffic

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


class TestSPCXRA_x2Split_400G:

    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.traffic_jsons = get_spcx_ra_spine_traffic(players, conf_args)
        self.ip = InfraConst.IPV6 if conf_args["is_ipv6"] else InfraConst.IPV4

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and default AR profile.')
    def test_ar_perf_max_bandwidth(self, request, packet_size):

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.ip)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                           power_threshold=self.power_thresholds_by_chip_type)

    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_ibm')
    @allure.description('Calculate the port utilization on the DUT with AR enabled and IBM enabled')
    def test_ar_perf_max_bandwidth_ibm(self, request, packet_size, ibm_fixture):

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.ip)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                           power_threshold=self.power_thresholds_by_chip_type)

    @allure.title('test_ar_perf_link_flap')
    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @pytest.mark.parametrize("flap_scenario", ["port_hiccup", "port_repeated_toggle", "toggle_multiple_ports"])
    @allure.description('With full line rate traffic, verify that traffic converges '
                        'to the initial state after an interface flap.')
    def test_ar_perf_link_flap(self, request, packet_size, flap_scenario):
        # TODO: remove when bug 4267499 is resolved
        if is_redmine_issue_active([4267499])[0] and flap_scenario == "toggle_multiple_ports":
            pytest.xfail(f"test_ar_perf_link_flap[toggle_multiple_ports] expected to fail while RM 4267499 is active")

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.ip)

        with allure.step("Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        flap_scenario_method = get_obj_method(self, flap_scenario)
        flap_scenario_method(test_name, packet_size)

        with allure.step(f"Verifying the BW utilization is at least {SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[packet_size]}% "
                         f"on all the ports"):
            traffic_validation_jsons_list = run_validation(players=self.players, test_name=test_name,
                                                           scenario=self.scenario,
                                                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                                                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                                                           tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                                                           power_threshold=self.power_thresholds_by_chip_type,
                                                           run_validate_counters=False)
            self.validate_counters_post_congestion(traffic_validation_jsons_list)

    @allure.title('test_ar_perf_reload_reboot')
    @allure.description('With full line rate traffic, verify that traffic converges to'
                        ' the initial state after cold reboot/reload.')
    def test_ar_perf_reload_reboot(self, request, packet_size=4096):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.DVS)

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.ip)

        with allure.step("Run 4000B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                           power_threshold=self.power_thresholds_by_chip_type)

        with allure.step("Rebooting the dut."):
            self.cli_object.general.reboot(self.dut_engine, save_config=True, wait_after_ping=240)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            run_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                           bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                           samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                           tc_occ_threshold=PerfConsts.OCC_AVG_TH,
                           power_threshold=self.power_thresholds_by_chip_type)

    def port_hiccup(self, test_name, packet_size):
        port_list = self.cli_object.performance.get_dut_ports()
        port_to_shutdown = random.sample(set(port_list), 1)
        with allure.step(f"Shutting down port: {port_to_shutdown}"):
            set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="down")
        with allure.step(f"Bringing up port: {port_to_shutdown}"):
            set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="up")

    def port_repeated_toggle(self, test_name, packet_size):
        port_list = self.cli_object.performance.get_dut_ports()
        port_to_shutdown = random.sample(set(port_list), 1)
        with allure.step(f"toggle {port_to_shutdown} only - for x10 times"):
            for i in range(10):
                with allure.step(f"Shutting down port: {port_to_shutdown}"):
                    set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="down")
                with allure.step(f"Bringing up port: {port_to_shutdown}"):
                    set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="up")

    def toggle_multiple_ports(self, test_name, packet_size):
        num_of_ports_to_shutdown = random.randrange(2, 10)
        port_list = self.cli_object.performance.get_dut_ports()
        ports_to_shutdown = random.sample(set(port_list), num_of_ports_to_shutdown)
        up_ports = list(set(port_list) - set(ports_to_shutdown))
        with allure.step(f"Shutting down ports: {ports_to_shutdown}"):
            set_ports_admin_state(self.players, port_list=ports_to_shutdown, port_state="down")

        with allure.step("Run traffic validation on Json results"):
            self.validate_link_flap_traffic(test_name, ports_to_shutdown, up_ports, packet_size)

        with allure.step(f"Bringing up ports: {ports_to_shutdown}"):
            set_ports_admin_state(self.players, port_list=ports_to_shutdown, port_state="up")

    def validate_link_flap_traffic(self, test_name, ports_to_shutdown, up_ports, packet_size):
        with allure.step("Run traffic validation on Json results"):
            traffic_validation_jsons_list = validate_traffic_results(self.players, test_name,
                                                                     self.scenario, PerfConsts.SAMPLES_PARAMS)

            violations_list = []
            for traffic_json in traffic_validation_jsons_list:
                with allure.step("Verifying the B/W utilization is 0% on down ports"):
                    validate_bw_per_ports(traffic_json, bw_threshold=0,
                                          ports_list=ports_to_shutdown, violations_list=violations_list)
                bw_threshold = SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size]
                with allure.step(f"Verifying the B/W utilization is {bw_threshold} on up ports"):
                    validate_bw_per_ports(traffic_json, bw_threshold=bw_threshold,
                                          ports_list=up_ports, violations_list=violations_list)

            if violations_list:
                raise TestIssue("\n".join(violations_list))

    def validate_counters_post_congestion(self, validation_jsons_list):
        violations_list = []
        for validation_json in validation_jsons_list:
            counters_samples = validation_json["Counters_samples"]
            counters_samples.pop('sample_params', None)
            for sample_idx, (sample_id, counters_sample) in enumerate(counters_samples.items()):
                if sample_idx != 0:
                    validate_counters_sample(sample_id, counters_sample, violations_list)
        if violations_list:
            raise TestIssue("\n".join(violations_list))
