from struct import pack
import allure
import logging
import pytest
import random

from ngts.helpers.performance.performance_setup_helpers import (run_traffic, traffic_validation, set_ibm,
                                                                set_port, reboot_dut, get_ports_from_dut,
                                                                validate_traffic_results, apply_test_configuration)
from ngts.constants.performance_constants import PerfConsts
logger = logging.getLogger()

PACKET_SIZE_TO_MAX_BW_DICT = PerfConsts.PACKET_SIZE_TO_MAX_BW_DICT
PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST
CONFIGURATION_TYPE_LIST = PerfConsts.CONFIGURATION_TYPE_LIST


class TestSPCXRA:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, players, engines):
        self.topology_obj = topology_obj
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"

    @allure.title('spcx_ra')
    def test_spcx_ra(self):
        """
        This test will SPCX_RA
        :return: raise assertion error if output is not there.
        """
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(self.players, scenario="spcx_ra")
        run_traffic(self.players, self.scenario)
        validate_traffic_results(self.players, self.scenario)

    @pytest.mark.parameterize("configuration", CONFIGURATION_TYPE_LIST)
    @pytest.mark.parameterize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth')
    @allure.description('Calculate the port utilization on the DUT with AR enabled, with various packet sizes (1500, 2000, 4000) and default AR profile.')
    def test_ar_perf_max_bandwidth(self, configuration, packet_size):
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(self.players, scenario=f"spcx_ra/{configuration}")

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            traffic_validation(self.players, self.scenario, b_w_threshold=PACKET_SIZE_TO_MAX_BW_DICT[packet_size])

    @pytest.mark.parameterize("packet_size", PACKET_SIZE_LIST)
    @allure.title('test_ar_perf_max_bandwidth_ibm')
    @allure.description('Calculate the port utilization on the DUT with AR enabled, with various packet sizes (1500, 2000, 4000) and IBM enabled')
    def test_ar_perf_max_bandwidth_ibm(self, packet_size):
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(self.players, scenario="spcx_ra/split_configuration")

        with allure.step("Set IBM to true"):
            set_ibm(self.players, ibm_mode=True)  # reload of switchd/docker/process should be done in the cli_wrapper.

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            traffic_validation(self.players, self.scenario, b_w_threshold=99)

    @allure.title('test_ar_perf_link_flap')
    @allure.description('With full line rate traffic, verify that traffic converges to the initial state after an interface flap.')
    def test_ar_perf_link_flap(self, packet_size=4000):
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(self.players, scenario="spcx_ra/split_configuration")

        with allure.step("Run 4000B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)

        port_list = get_ports_from_dut(self.cli_object)
        ports = random.sample(set(port_list), 2)
        with allure.step(f"Shutting down port number {ports[0]} {ports[1]}"):
            set_port(self.players, port_list=ports, shutdown=True)  # port number to port translation would be handled in cli_wrapper

        with allure.step("Verifying the B/W utilization is 0% on down ports"):
            traffic_validation(self.players, self.scenario, b_w_threshold=0, port_list=ports)

        with allure.step(f"Bringing up port number {ports[0]} {ports[1]}"):
            set_port(self.players, port_list=ports, shutdown=False)  # port number to port translation would be handled in cli_wrapper

        with allure.step(f"Verifying the B/W utilization is at least {PACKET_SIZE_TO_MAX_BW_DICT[str(packet_size)]}% on all the ports"):
            traffic_validation(self.players, self.scenario, b_w_threshold=PACKET_SIZE_TO_MAX_BW_DICT[str([packet_size])])

    @allure.title('test_ar_perf_reload_reboot')
    @allure.description('With full line rate traffic, verify that traffic converges to the initial state after cold reboot/reload.')
    def test_ar_perf_reload_reboot(self, packet_size=4000):
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(self.players, scenario="spcx_ra/split_configuration")

        with allure.step("Run 4000B packet Traffic on all the ports"):
            run_traffic(self.players, self.scenario, packet_size)  # add packet size as a parameter in this function

        with allure.step(f"Verifying the B/W utilization is at least {PACKET_SIZE_TO_MAX_BW_DICT[str(packet_size)]}% on all the ports after the reboot"):
            traffic_validation(self.players, self.scenario, b_w_threshold=PACKET_SIZE_TO_MAX_BW_DICT[str(packet_size)])

        with allure.step("Rebooting the dut."):
            reboot_dut(self.players, system_check=True)

        with allure.step(f"Verifying the B/W utilization is at least {PACKET_SIZE_TO_MAX_BW_DICT[str(packet_size)]}% on all the ports after the reboot"):
            traffic_validation(self.players, self.scenario, b_w_threshold=PACKET_SIZE_TO_MAX_BW_DICT[str(packet_size)])
