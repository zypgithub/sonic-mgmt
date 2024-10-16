import logging
import os
import pytest

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from ngts.tests.nightly.adaptive_routing.constants import ArConsts
from ngts.helpers.adaptive_routing_helper import ArHelper
from ngts.helpers.vxlan_helper import validate_dest_files_exist_in_tarball, get_tech_support_tar_file
from infra.tools.validations.traffic_validations.iperf.iperf_runner import IperfChecker
from retry.api import retry_call

logger = logging.getLogger()
allure.logger = logger


class TestArBasic:

    @pytest.fixture(autouse=True)
    def setup_param(self, topology_obj, engines, cli_objects, interfaces, players, dut_ha_1_mac, ha_dut_1_mac,
                    ar_base_config_default_vrf, set_config_db_split_mode):
        self.topology_obj = topology_obj
        self.engines = engines
        self.interfaces = interfaces
        self.players = players
        self.cli_objects = cli_objects
        self.ingress_port = self.interfaces.dut_ha_1
        self.dut_mac = dut_ha_1_mac
        self.ha_dut_1_mac = ha_dut_1_mac
        self.hash_tx_port = ar_base_config_default_vrf
        self.ar_helper = ArHelper()
        self.expected_tx_port = self.ar_helper.get_received_port(self.interfaces, self.hash_tx_port)
        self.tx_ports = [interfaces.dut_hb_1, interfaces.dut_hb_2]

    def test_ar_buffer_grading_default_parameters(self):
        """
        This test case will send RoCEv2 packets to ports in ECMP group where ports has same link utilization and buffer
        grading parameters. Traffic must be split between all ports in ECMP group equally (some packet count deviation
        could be present in ports counters due to AR algorithms).
        """
        # Get interface counters before send RoCE v2 traffic
        iface_rx_count_before = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')
        # Send RoCE v2 traffic
        with allure.step(f'HA send {ArConsts.PACKET_NUM_MID} TC3 RoCEv2 with AR flag packets'):
            self.ar_helper.validate_roce_v2_pkts_traffic(players=self.players,
                                                         interfaces=self.interfaces,
                                                         ha_dut_1_mac=self.ha_dut_1_mac,
                                                         dut_ha_1_mac=self.dut_mac,
                                                         sender_count=ArConsts.PACKET_NUM_MID,
                                                         )

        # Get interface counters after send RoCE v2 traffic
        iface_rx_count_after = retry_call(self.ar_helper.validate_all_traffic_sent,
                                          fargs=[self.cli_objects, self.tx_ports, iface_rx_count_before,
                                                 ArConsts.PACKET_NUM_MID],
                                          tries=3,
                                          delay=5,
                                          logger=logger)

        # Verify that traffic was split between ports in ecmp group
        self.ar_helper.validate_traffic_distribution(self.tx_ports, iface_rx_count_after, iface_rx_count_before)

    def test_ar_buffer_grading_with_shaper(self, configure_port_shaper):
        """
        This test case will send RoCEv2 packets to ports in ECMP group where first port has limited buffer grading.
        All traffic has to go through the port with higher buffer grading set.
        """
        # Get interface counters before send RoCE v2 traffic
        iface_rx_count_before = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')

        # Send RoCE v2 traffic
        with allure.step(f'HA send {ArConsts.PACKET_NUM_MID} TC3 RoCEv2 with AR flag packets'):
            self.ar_helper.validate_roce_v2_pkts_traffic(players=self.players,
                                                         interfaces=self.interfaces,
                                                         ha_dut_1_mac=self.ha_dut_1_mac,
                                                         dut_ha_1_mac=self.dut_mac,
                                                         sender_count=ArConsts.PACKET_NUM_MID
                                                         )
        # Get interface counters after send RoCE v2 traffic
        logger.info("traffic validation")
        iface_rx_count_after = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')
        # Verify that traffic goes to port with higher port utilization % set to AR port
        sent_traffic = iface_rx_count_after[self.expected_tx_port] - iface_rx_count_before[self.expected_tx_port]
        min_expected_sent = ArConsts.PACKET_NUM_MID - ArConsts.LO_THRESHOLD_PROFILE0 * 1.3
        assert sent_traffic >= min_expected_sent, \
            (f"RoCEv2 with AR flags packets did not move to the port {self.expected_tx_port}."
             f"Actual sent: {sent_traffic} when expected at least {min_expected_sent}")

    def test_ar_custom_profile(self, config_ar_profile):
        """
        This test case will enable custom profile and send RoCEv2 packets to ports in ECMP group where ports has same
        link utilization and buffer grading parameters. Traffic must be split between all ports in ECMP group equally
        (some packet count deviation could be present in ports counters due to AR algorithms).
        """
        # Get show ar config output
        show_ar_dict = self.ar_helper.get_ar_configuration(self.cli_objects)
        assert show_ar_dict[ArConsts.AR_GLOBAL][ArConsts.AR_ACTIVE_PROFILE] == ArConsts.CUSTOM_PROFILE_NAME, \
            f"Active AR profile is {show_ar_dict[ArConsts.AR_GLOBAL][ArConsts.AR_ACTIVE_PROFILE]} but must be " \
            f"{ArConsts.CUSTOM_PROFILE_NAME}"

        # Get interface counters before send RoCE v2 traffic
        iface_rx_count_before = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')
        # Send RoCE v2 traffic
        with allure.step(f'HA send {ArConsts.PACKET_NUM_MID} TC3 RoCEv2 with AR flag packets'):
            self.ar_helper.validate_roce_v2_pkts_traffic(players=self.players,
                                                         interfaces=self.interfaces,
                                                         ha_dut_1_mac=self.ha_dut_1_mac,
                                                         dut_ha_1_mac=self.dut_mac,
                                                         sender_count=ArConsts.PACKET_NUM_MID,
                                                         )
        # Get interface counters after send RoCE v2 traffic
        iface_rx_count_after = retry_call(self.ar_helper.validate_all_traffic_sent,
                                          fargs=[self.cli_objects, self.tx_ports, iface_rx_count_before,
                                                 ArConsts.PACKET_NUM_MID],
                                          tries=3,
                                          delay=5,
                                          logger=logger)

        # Verify that traffic was split between ports in ecmp group
        self.ar_helper.validate_traffic_distribution(self.tx_ports, iface_rx_count_after, iface_rx_count_before)

    def test_ar_global_link_utilization(self, players, configure_global_util):
        """
        This test case will send Non-AR packets to ports in ECMP group where ports have 1% link utilization grading
        set configured. The link should be fully utilized. Afterwards, RoCEv2 packets will be sent,
         All traffic has to go through the less utilized ports.
        """
        utilized_port = self.expected_tx_port
        expected_ar_port = [port for port in self.tx_ports if port != utilized_port]

        # Get interface counters before send RoCE v2 traffic
        iface_rx_count_before = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')
        # Send traffic in the background to fully utilize the link
        logger.info('Sending iPerf traffic')
        IperfChecker(players, ArConsts.IPERF_VALIDATION).run_background_validation()
        # Send RoCE v2 traffic
        with allure.step(f'HA send {ArConsts.PACKET_NUM_MID} TC3 RoCEv2 with AR flag packets'):
            self.ar_helper.validate_roce_v2_pkts_traffic(players=self.players,
                                                         interfaces=self.interfaces,
                                                         ha_dut_1_mac=self.ha_dut_1_mac,
                                                         dut_ha_1_mac=self.dut_mac,
                                                         sender_count=ArConsts.PACKET_NUM_MID,
                                                         sendpfast=True,
                                                         mbps=100000,
                                                         loop=ArConsts.PACKET_NUM_LARGE,
                                                         timeout=5
                                                         )
        # Get interface counters after sending RoCE v2 traffic
        iface_rx_count_after = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')

        # Verify that 70% of the traffic goes to the other port from the same ECMP group
        sent_traffic = iface_rx_count_after[expected_ar_port[0]] - iface_rx_count_before[expected_ar_port[0]]
        min_expected_sent = ArConsts.PACKET_NUM_LARGE * 0.7
        percentage_sent = (sent_traffic / min_expected_sent) * 100
        assert sent_traffic >= min_expected_sent, \
            f"Traffic has not been shifted from port {utilized_port}  to port " \
            f"{expected_ar_port}. Expected to shift at least 70% but shifted only {percentage_sent:.2f}% "

    def test_ar_show_techsupport(self):
        """
        This test will check if dump/doai.gz present after show techsupport and is not empty
        """
        with allure.step('Generate show techsupport'):
            tar_file = get_tech_support_tar_file(self.engines)
        with allure.step('Check if doai tar file available'):
            validate_dest_files_exist_in_tarball(tar_file, ArConsts.AR_DUMP_FILE_NAME)
        with allure.step(f'Check if {ArConsts.AR_DUMP_FILE_NAME} not empty'):
            pass

    def test_ar_negative(self, config_vlan_intf, config_lag):
        """
        This test case will check negative scenarios for configuring AR feature
        """
        with allure.step('Validate AR handle enable ar function before doAI service enabled'):
            self.ar_helper.verify_enable_ar_before_doai_service_start(self.cli_objects)

        with allure.step('Validate AR prevent configuring with a non exist user defined profile'):
            self.ar_helper.verify_config_non_exist_profile(self.cli_objects)

        with allure.step('Validate AR prevent configuring on a non exist port'):
            self.ar_helper.verify_config_ar_at_non_exist_port(self.cli_objects)

        with allure.step('Validate AR prevent configuring on vlan interface'):
            self.ar_helper.verify_config_ar_on_vlan_intf(self.cli_objects)

        with allure.step('Validate AR prevent configuring on lag interface'):
            self.ar_helper.verify_config_ar_on_lag_intf_and_lag_member(self.cli_objects, self.topology_obj)

        with allure.step('Validate AR prevent configuring on mgmt interface'):
            self.ar_helper.verify_config_ar_on_mgmt_port(self.cli_objects)

        with allure.step('Validate AR prevent configuring invalid link utilization value'):
            self.ar_helper.verify_config_ar_invalid_global_link_utilization(self.cli_objects)

    def test_ar_with_reboot(self, get_reboot_type):
        """
        This test case will send RoCEv2 packets to ports in ECMP group where first port has limited buffer grading.
        All traffic has to go through the port with higher buffer grading set. Then random reboot will be performed and
        traffic will be sent one more time after reboot.
        """
        # Get interface counters before send RoCE v2 traffic
        iface_rx_count_before = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')
        # Send RoCE v2 traffic
        with allure.step(f'HA send {ArConsts.PACKET_NUM_MID} TC3 RoCEv2 with AR flag packets'):
            self.ar_helper.validate_roce_v2_pkts_traffic(players=self.players,
                                                         interfaces=self.interfaces,
                                                         ha_dut_1_mac=self.ha_dut_1_mac,
                                                         dut_ha_1_mac=self.dut_mac,
                                                         sender_count=ArConsts.PACKET_NUM_MID
                                                         )

        # Get interface counters after send RoCE v2 traffic
        iface_rx_count_after = retry_call(self.ar_helper.validate_all_traffic_sent,
                                          fargs=[self.cli_objects, self.tx_ports, iface_rx_count_before,
                                                 ArConsts.PACKET_NUM_MID],
                                          tries=3,
                                          delay=5,
                                          logger=logger)

        # Verify that traffic was split between ports in ecmp group
        self.ar_helper.validate_traffic_distribution(self.tx_ports, iface_rx_count_after, iface_rx_count_before)

        # Save configuration before reboot
        self.cli_objects.dut.general.save_configuration()
        with allure.step(f'Randomly choose {get_reboot_type} type'):
            self.cli_objects.dut.general.reboot_reload_flow(r_type=get_reboot_type, topology_obj=self.topology_obj)

        # Get interface counters before send RoCE v2 traffic after reboot
        iface_rx_count_before = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')

        # Send RoCE v2 traffic
        with allure.step(f'HA send {ArConsts.PACKET_NUM_MID} TC3 RoCEv2 with AR flag packets'):
            self.ar_helper.validate_roce_v2_pkts_traffic(players=self.players,
                                                         interfaces=self.interfaces,
                                                         ha_dut_1_mac=self.ha_dut_1_mac,
                                                         dut_ha_1_mac=self.dut_mac,
                                                         sender_count=ArConsts.PACKET_NUM_MID,
                                                         )
      # Get interface counters after send RoCE v2 traffic
        iface_rx_count_after = retry_call(self.ar_helper.validate_all_traffic_sent,
                                          fargs=[self.cli_objects, self.tx_ports, iface_rx_count_before,
                                                 ArConsts.PACKET_NUM_MID],
                                          tries=3,
                                          delay=5,
                                          logger=logger)

        # Verify that traffic was split between ports in ecmp group
        self.ar_helper.validate_traffic_distribution(self.tx_ports, iface_rx_count_after, iface_rx_count_before)

    def test_ar_with_remove_add_doai_app(self):
        """
        This test case will remove doAI application and installed to same version and traffic verification performed.
        Traffic verification performed.
        """

        try:
            with allure.step(f'Verify DNS configuration is set'):
                self.cli_objects.dut.ip.apply_dns_servers_into_resolv_conf()
            with allure.step(f'Remove and install doAI'):
                # Get current doAI version
                doai_version = self.cli_objects.dut.app_ext.get_installed_app_version(ArConsts.DOAI_CONTAINER_NAME)
                # Uninstall doAI
                self.ar_helper.uninstall_doai_flow(self.cli_objects, self.topology_obj)
                # Install doAI with the same version, enable AR with same ports.
                self.ar_helper.install_doai_flow(self.cli_objects, self.topology_obj, self.tx_ports, doai_version)

            # Get interface counters before send RoCE v2 traffic after enabling AR
            iface_rx_count_before = self.ar_helper.get_interfaces_counters(self.cli_objects, self.tx_ports, 'TX_OK')

            # Send RoCE v2 traffic
            with allure.step(f'HA send {ArConsts.PACKET_NUM_MID} TC3 RoCEv2 with AR flag packets'):
                self.ar_helper.validate_roce_v2_pkts_traffic(players=self.players,
                                                             interfaces=self.interfaces,
                                                             ha_dut_1_mac=self.ha_dut_1_mac,
                                                             dut_ha_1_mac=self.dut_mac,
                                                             sender_count=ArConsts.PACKET_NUM_MID,
                                                             )
            iface_rx_count_after = retry_call(self.ar_helper.validate_all_traffic_sent,
                                              fargs=[self.cli_objects, self.tx_ports, iface_rx_count_before,
                                                     ArConsts.PACKET_NUM_MID],
                                              tries=3,
                                              delay=5,
                                              logger=logger)

            # Verify that traffic was split between ports in ecmp group
            self.ar_helper.validate_traffic_distribution(self.tx_ports, iface_rx_count_after, iface_rx_count_before)

        finally:
            installed_version = self.cli_objects.dut.app_ext.get_installed_app_version(ArConsts.DOAI_CONTAINER_NAME)
            if installed_version != doai_version:
                self.cli_objects.dut.app_ext.upgrade_app(ArConsts.DOAI_CONTAINER_NAME, version=doai_version)


class TestArMaxPort:

    @pytest.fixture(autouse=True)
    def setup_param(self, topology_obj, engines, cli_objects, interfaces, players, ar_max_ports_config):
        self.topology_obj = topology_obj
        self.engines = engines
        self.interfaces = interfaces
        self.players = players
        self.cli_objects = cli_objects
        self.ar_helper = ArHelper()
        self.dut_ports = ar_max_ports_config

    def test_ar_max_port(self, get_reboot_type):
        """
        This test will check if AR can be configured at DUT all ports and be persistent after reboot
        """
        with allure.step('Verify port configuration correctness'):
            show_ports_config = self.ar_helper.get_ar_configuration(self.cli_objects)[ArConsts.
                                                                                      AR_PORTS_GLOBAL]
            for port in self.dut_ports:
                assert port in show_ports_config, f"Port {port} has not been added to AR config"

        with allure.step('Save changes'):
            self.ar_helper.config_save_reload(self.cli_objects, self.topology_obj, reload_force=True)

        show_ar_dict_before_reboot = self.ar_helper.get_ar_configuration(self.cli_objects)

        with allure.step(f'Randomly choose {get_reboot_type} type'):
            self.cli_objects.dut.general.reboot_reload_flow(r_type=get_reboot_type, topology_obj=self.topology_obj, reload_force=True)

        with allure.step(f'Verify profile {ArConsts.GOLDEN_PROFILE0} correctness after {get_reboot_type}'):
            # Get show ar config output
            show_ar_dict_after_reboot = self.ar_helper.get_ar_configuration(self.cli_objects)

            # Compare output with golden profile values
        assert show_ar_dict_before_reboot == show_ar_dict_after_reboot, \
            f"Golden profile configuration did not match after {get_reboot_type}"
