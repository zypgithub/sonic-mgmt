from struct import pack
import allure
import logging
import pytest
import random
from copy import deepcopy
from ngts.helpers.general_helper import get_pytest_test_name
from ngts.helpers.performance.traffic_helpers import validate_bw_per_ports
from ngts.helpers.performance.performance_setup_helpers import (run_traffic, traffic_validation,
                                                                validate_traffic_results,
                                                                set_ports_admin_state, reboot_dut,
                                                                skip_test_on_unsupported_os, get_obj_method)
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.constants import CliType
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

    @allure.title('test_ar_perf_link_flap')
    @pytest.mark.parametrize("packet_size", PACKET_SIZE_LIST)
    @pytest.mark.parametrize("flap_scenario", ["port_hiccup", "port_repeated_toggle", "toggle_multiple_ports"])
    @allure.description('With full line rate traffic, verify that traffic converges '
                        'to the initial state after an interface flap.')
    def test_ar_perf_link_flap(self, request, packet_size, flap_scenario):

        test_name = get_pytest_test_name(request)

        with allure.step("Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)

        flap_scenario_method = get_obj_method(self, flap_scenario)
        flap_scenario_method(test_name, packet_size)

        with allure.step(f"Verifying the BW utilization is at least {SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[packet_size]}% "
                         f"on all the ports"):
            traffic_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                               bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                               samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                               tc_occ_threshold=PerfConsts.OCC_AVG_TH)

    @allure.title('test_ar_perf_reload_reboot')
    @allure.description('With full line rate traffic, verify that traffic converges to'
                        ' the initial state after cold reboot/reload.')
    def test_ar_perf_reload_reboot(self, packet_size=4000):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.DVS)

        with allure.step("Run 4000B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            traffic_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                               bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                               samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                               tc_occ_threshold=PerfConsts.OCC_AVG_TH)

        with allure.step("Rebooting the dut."):
            reboot_dut(self.players, system_check=True)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            traffic_validation(players=self.players, test_name=test_name, scenario=self.scenario,
                               bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                               samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                               tc_occ_threshold=PerfConsts.OCC_AVG_TH)

    def port_hiccup(self, test_name, packet_size):
        port_list = self.cli_object.performance.get_dut_ports(self.scenario)
        port_to_shutdown = random.sample(set(port_list), 1)
        with allure.step(f"Shutting down port: {port_to_shutdown}"):
            set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="down")
        with allure.step(f"Bringing up port: {port_to_shutdown}"):
            set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="up")

    def port_repeated_toggle(self, test_name, packet_size):
        port_list = self.cli_object.performance.get_dut_ports(self.scenario)
        port_to_shutdown = random.sample(set(port_list), 1)
        with allure.step(f"toggle {port_to_shutdown} only - for x10 times"):
            for i in range(10):
                with allure.step(f"Shutting down port: {port_to_shutdown}"):
                    set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="down")
                with allure.step(f"Bringing up port: {port_to_shutdown}"):
                    set_ports_admin_state(self.players, port_list=port_to_shutdown, port_state="up")

    def toggle_multiple_ports(self, test_name, packet_size):
        num_of_ports_to_shutdown = random.randrange(2, 10)
        port_list = self.cli_object.performance.get_dut_ports(self.scenario)
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
