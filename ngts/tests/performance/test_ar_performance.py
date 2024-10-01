import logging
import pytest
import random

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.constants.constants import PerfConsts
from ngts.helpers.adaptive_routing_helper import ArHelper, ArPerfHelper
from retry.api import retry_call

logger = logging.getLogger()
allure.logger = logger


class TestArPerformance:

    @pytest.fixture(autouse=True)
    def setup_param(self, topology_obj, engines, cli_objects, players, config_node, config_dut):
        self.topology_obj = topology_obj
        self.engines = engines
        self.dut_engine = engines.dut
        self.players = players
        self.cli_objects = cli_objects
        self.ar_helper = ArHelper()
        self.ar_perf_helper = ArPerfHelper(self.topology_obj, self.engines)
        self.dut_mac = self.ar_perf_helper.get_switch_mac(self.topology_obj, 'dut')
        self.tg_ports = self.ar_perf_helper.all_engines_ports
        self.dut_tx_ports = self.ar_perf_helper.all_engines_ports['dut']
        self.tx_ports_left_tg = self.tg_ports[PerfConsts.LEFT_TG_ALIAS]["egress_ports"]
        self.tx_ports_right_tg = self.tg_ports[PerfConsts.RIGHT_TG_ALIAS]["egress_ports"]
        self.tg_tx_ports = {PerfConsts.LEFT_TG_ALIAS: self.tx_ports_left_tg,
                            PerfConsts.RIGHT_TG_ALIAS: self.tx_ports_right_tg}
        self.mloop_ports_left_tg = self.tg_ports[PerfConsts.LEFT_TG_ALIAS]["mloop_ports"]
        self.mloop_ports_right_tg = self.tg_ports[PerfConsts.RIGHT_TG_ALIAS]["mloop_ports"]
        self.random_dut_ports = random.sample(self.dut_tx_ports, 2)
        self.tg_ports_num = len(self.tx_ports_left_tg) if len(self.tx_ports_right_tg) == len(
            self.tx_ports_right_tg) else None
        if is_redmine_issue_active([3677516]):
            # TODO: WA due to a community bug in which AR configuration isn't applied if syncd starts before doai docker
            self.ar_helper.config_save_reload(cli_objects, topology_obj)

    def test_ar_perf_node_full_utilization(self):
        """
        On a static route based topology verify that the backpressure to the source
        from middle node is not observed below 95% of line rate.
         """
        try:
            with allure.step('Generate traffic from left and right nodes to fully utilize the links'):
                self.ar_perf_helper.generate_traffic_from_node(self.engines, self.dut_mac, self.tg_ports_num)
            for tg in self.tg_tx_ports:
                retry_call(self.ar_perf_helper.validate_tx_utilization,
                           fargs=[self.cli_objects, self.tg_tx_ports[tg], tg],
                           tries=5,
                           delay=5,
                           logger=logger)

        finally:
            self.ar_perf_helper.stop_traffic_generation(self.engines)

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    def test_ar_perf_max_bandwidth(self, packet_size):
        """
        Calculate the port utilization on the DUT with AR enabled,
        with various packet sizes and default AR profile.
        """
        try:
            with allure.step(f'Generate traffic with packet size {packet_size}'
                             f' from left and right nodes to fully utilize the links'):
                self.ar_perf_helper.generate_traffic_from_node(self.engines, self.dut_mac, self.tg_ports_num,
                                                               packet_size)
            self.ar_perf_helper.validate_tx_utilization(self.cli_objects, self.dut_tx_ports,
                                                        device="dut",
                                                        ibm=False,
                                                        packet_size=packet_size,
                                                        stress_mode=True)
        finally:
            self.ar_perf_helper.stop_traffic_generation(self.engines)

    @pytest.mark.parametrize("packet_size", PerfConsts.PACKET_SIZE_LIST)
    def test_ar_perf_max_bandwidth_ibm(self, packet_size, load_ibm_profile):
        """
        Calculate the port utilization on the DUT with AR enabled,
        with various packet sizes and ingress buffer mode enabled.
        """
        try:
            with allure.step(f'Generate traffic with packet size {packet_size}'
                             f' from left and right nodes to fully utilize the links'):
                self.ar_perf_helper.generate_traffic_from_node(self.engines, self.dut_mac, self.tg_ports_num,
                                                               packet_size)
            self.ar_perf_helper.validate_tx_utilization(self.cli_objects, self.dut_tx_ports,
                                                        device="dut",
                                                        ibm=True,
                                                        packet_size=packet_size,
                                                        stress_mode=True)

        finally:
            self.ar_perf_helper.stop_traffic_generation(self.engines)

    def test_ar_perf_link_flap(self):
        """
        With full line rate traffic, verify that traffic converges to the initial state after an interface flap.
        """
        try:
            with allure.step(f'Generate traffic from left and right nodes to fully utilize the links'):
                self.ar_perf_helper.generate_traffic_from_node(self.engines, self.dut_mac, self.tg_ports_num)
            retry_call(self.ar_perf_helper.validate_tx_utilization,
                       fargs=[self.cli_objects, self.dut_tx_ports, "dut"],
                       tries=5,
                       delay=5,
                       logger=logger)

            with allure.step(f'Perform link flap to {self.random_dut_ports}'):
                self.ar_perf_helper.link_flap_flow(self.cli_objects, self.random_dut_ports)
            self.ar_perf_helper.config_ip_neighbors_on_dut(self.engines, self.topology_obj)

            retry_call(self.ar_perf_helper.validate_tx_utilization,
                       fargs=[self.cli_objects, self.random_dut_ports, "dut"],
                       tries=5,
                       delay=5,
                       logger=logger)

        finally:
            self.ar_perf_helper.stop_traffic_generation(self.engines)

    def test_ar_perf_reload_reboot(self):
        """
        With full line rate traffic, verify that traffic converges to the initial state after cold reboot/reload.
        """
        try:
            with allure.step(f'Generate traffic from left and right nodes to fully utilize the links'):
                self.ar_perf_helper.generate_traffic_from_node(self.engines, self.dut_mac, self.tg_ports_num)
            retry_call(self.ar_perf_helper.validate_tx_utilization,
                       fargs=[self.cli_objects, self.dut_tx_ports, "dut"],
                       tries=5,
                       delay=5,
                       logger=logger)
            reboot_type = self.ar_perf_helper.choose_reboot_type(PerfConsts.PERF_SUPPORTED_REBOOT_TYPES)
            with allure.step(f'Randomly choose {reboot_type} type, and execute it'):
                self.cli_objects.dut.general.reboot_reload_flow(r_type=reboot_type, topology_obj=self.topology_obj)

            self.ar_perf_helper.config_ip_neighbors_on_dut(self.engines, self.topology_obj)

            retry_call(self.ar_perf_helper.validate_tx_utilization,
                       fargs=[self.cli_objects, self.dut_tx_ports, "dut"],
                       tries=5,
                       delay=5,
                       logger=logger)

        finally:
            self.ar_perf_helper.stop_traffic_generation(self.engines)
