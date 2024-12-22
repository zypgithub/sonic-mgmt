import logging
import pytest

from ngts.constants.constants import VxlanConstants
from ngts.helpers.vxlan_helper import send_and_validate_traffic, restart_bgp_session
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from ngts.tests.push_build_tests.conftest import is_evpn_support

"""

EVPN VXLAN Test Cases

Documentation: https://confluence.nvidia.com/pages/viewpage.action?spaceKey=SW&title=SONiC+NGTS+EVPN+VXLAN+Documentation

"""

logger = logging.getLogger()
allure.logger = logger

DUT_VLAN_100_IFACE = 'Vlan100'
HA_BOND_0_IFACE = 'bond0'
HB_VLAN_20_IFACE = 'bond0.20'
HB_VLAN_101_IFACE = 'bond0.101'
STATIC_MAC_PORT = 'PortChannel0002'
SOURCE_MAC_PORT_1_TO_HB = 'PortChannel0002'
SOURCE_MAC_PORT_1_TO_HA = 'PortChannel0002'


@pytest.fixture(scope='class')
def mac_addresses(engines, cli_objects):
    dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(DUT_VLAN_100_IFACE)
    ha_br_50020_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_50020_IFACE)
    ha_br_500100_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
    ha_br_500101_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500101_IFACE)
    hb_br_500100_mac = cli_objects.hb.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
    hb_bond0_20_mac = cli_objects.hb.mac.get_mac_address_for_interface(HB_VLAN_20_IFACE)
    hb_bond0_101_mac = cli_objects.hb.mac.get_mac_address_for_interface(HB_VLAN_101_IFACE)

    return dut_mac, ha_br_50020_mac, ha_br_500100_mac, ha_br_500101_mac, hb_br_500100_mac, hb_bond0_20_mac, \
        hb_bond0_101_mac


@pytest.fixture(scope='class')
def skip_if_upgrade(base_version, target_version):
    if base_version and target_version and '202012' in base_version:
        pytest.skip("If case of upgrade flow from 202012 - "
                    "202012 doesn't support VxLAN and this test will not be supported")


class TestEvpnVxlan:

    @pytest.fixture(autouse=True)
    def prepare_param(self, topology_obj, engines, players, interfaces, mac_addresses, cli_objects, upgrade_params,
                      sonic_branch):
        if upgrade_params.is_upgrade_required:
            base_image, target_image = cli_objects.dut.general.get_base_and_target_images()
            if not is_evpn_support(base_image):
                pytest.skip(f'EVPN VxLAN feature is not supported during upgrade from {base_image} image')
        if not is_evpn_support(sonic_branch):
            pytest.skip(f"{sonic_branch} doesn't support EVPN VxLAN feature")

        self.topology_obj = topology_obj
        self.engines = engines
        self.players = players
        self.interfaces = interfaces

        self.dut_loopback_ip = '10.1.0.32'
        self.dut_vlan_20_ip = '20.0.0.1'
        self.dut_vlan_100_ip = '100.0.0.1'
        self.dut_vlan_101_ip = '101.0.0.1'
        self.dut_ha_1_ip = '30.0.0.1'

        self.ha_bond_0_ip = '30.0.0.2'
        self.ha_vni_50020_iface_ip = '20.0.0.2'
        self.ha_vni_500100_iface_ip = '100.0.0.2'
        self.ha_vni_500101_iface_ip = '101.0.0.2'
        self.ha_vni_500200_iface_ip = '200.0.0.2'

        self.hb_vlan_40_ip = '40.0.0.3'
        self.hb_vlan_20_iface_ip = '20.0.0.3'
        self.hb_vni_500100_iface_ip = '100.0.0.3'
        self.hb_vlan_101_iface_ip = '101.0.0.3'

        self.dut_vtep_ip = self.ha_bond_0_ip
        self.ha_vtep_ip = self.ha_bond_0_ip
        self.hb_vtep_ip = self.hb_vlan_40_ip

        self.dut_mac, self.ha_br_50020_mac, self.ha_br_500100_mac, self.ha_br_500101_mac, \
            self.hb_br_500100_mac, self.hb_bond0_20_mac, self.hb_bond0_101_mac = mac_addresses

    def validate_basic_evpn_type_2_3_route(self, cli_objects):
        """
        This method is used to verify basic evpn type 2 and type 3 route states
        :param cli_objects: cli_objects fixture
        """
        # VXLAN route validation
        with allure.step('Validate CLI type-2 routes on DUT'):
            dut_type_2_check_list = [
                (self.ha_br_50020_mac, self.ha_bond_0_ip, VxlanConstants.RD_20, self.ha_vni_50020_iface_ip),
                (self.hb_bond0_101_mac, self.dut_loopback_ip, VxlanConstants.RD_101, self.hb_vlan_101_iface_ip)
            ]
            dut_type_2_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_macip()
            for mac_addr, vtep_ip, rd, ip_addr in dut_type_2_check_list:
                cli_objects.dut.frr.validate_type_2_route(dut_type_2_info, mac_addr, vtep_ip, rd, ip_addr)

        with allure.step('Validate CLI type-3 routes on DUT'):
            dut_type_3_check_list = [
                (self.ha_bond_0_ip, self.ha_bond_0_ip, VxlanConstants.RD_20),
                (self.ha_bond_0_ip, self.ha_bond_0_ip, VxlanConstants.RD_100),
                (self.ha_bond_0_ip, self.ha_bond_0_ip, VxlanConstants.RD_101),
                (self.hb_vlan_40_ip, self.hb_vlan_40_ip, VxlanConstants.RD_100)
            ]
            dut_type_3_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_multicast()
            for vtep_ip, vtep_ip, rd in dut_type_3_check_list:
                cli_objects.dut.frr.validate_type_3_route(dut_type_3_info, vtep_ip, vtep_ip, rd)

        with allure.step('Validate CLI type-2 routes on HA'):
            ha_type_2_check_list = [
                (self.hb_bond0_20_mac, self.dut_loopback_ip, VxlanConstants.RD_20, self.hb_vlan_20_iface_ip),
                (self.hb_bond0_101_mac, self.dut_loopback_ip, VxlanConstants.RD_101, self.hb_vlan_101_iface_ip)
            ]
            ha_type_2_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_macip()
            for mac_addr, vtep_ip, rd, ip_addr in ha_type_2_check_list:
                cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, mac_addr, vtep_ip, rd, ip_addr)

        with allure.step('Validate CLI type-3 routes on HA'):
            ha_type_3_check_list = [
                (self.dut_loopback_ip, self.dut_loopback_ip, VxlanConstants.RD_20),
                (self.dut_loopback_ip, self.dut_loopback_ip, VxlanConstants.RD_100),
                (self.dut_loopback_ip, self.dut_loopback_ip, VxlanConstants.RD_101)
            ]
            ha_type_3_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_multicast()
            for vtep_ip, vtep_ip, rd in ha_type_3_check_list:
                cli_objects.ha.frr.validate_type_3_route(ha_type_3_info, vtep_ip, vtep_ip, rd)

        with allure.step('Validate CLI type-3 routes on HB'):
            hb_type_3_check_list = [
                (self.dut_loopback_ip, self.dut_loopback_ip, VxlanConstants.RD_100),
                (self.dut_loopback_ip, self.dut_loopback_ip, VxlanConstants.RD_101)
            ]
            hb_type_3_info = cli_objects.hb.frr.get_l2vpn_evpn_route_type_multicast()
            for vtep_ip, vtep_ip, rd in hb_type_3_check_list:
                cli_objects.hb.frr.validate_type_3_route(hb_type_3_info, vtep_ip, vtep_ip, rd)

    def validate_basic_evpn_type_5_route(self, cli_objects):
        """
        This method is used to verify basic evpn type 5 route states
        :param cli_objects: cli_objects fixture
        """
        with allure.step('Validate CLI type-5 routes on DUT'):
            dut_type_5_check_list = [
                (self.ha_vni_50020_iface_ip, VxlanConstants.PREFIX_LENGTH, self.ha_vtep_ip, VxlanConstants.RD_200),
                (self.ha_vni_500200_iface_ip, VxlanConstants.PREFIX_LENGTH, self.ha_vtep_ip, VxlanConstants.RD_200)
            ]
            dut_type_5_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_prefix()
            for ip_addr, mask, vtep_ip, rd in dut_type_5_check_list:
                cli_objects.dut.frr.validate_type_5_route(dut_type_5_info, ip_addr, mask, vtep_ip, rd)

        with allure.step('Validate CLI type-5 routes on HA'):
            dut_type_5_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_prefix()
            cli_objects.ha.frr.validate_type_5_route(dut_type_5_info, self.dut_vlan_20_ip,
                                                     VxlanConstants.PREFIX_LENGTH, self.dut_vtep_ip,
                                                     VxlanConstants.RD_200)

    def validate_l3_connectivity(self):
        """
        This method is used to validate layer 3 connectivity between DUT and HB
        It also helps to trigger arp learning at DUT
        """
        with allure.step(f'Send ping from HB to DUT via VLAN {VxlanConstants.VLAN_101}'):
            ping_hb_dut_vlan_101 = {'sender': 'hb',
                                    'args': {'interface': HB_VLAN_101_IFACE, 'count': VxlanConstants.PACKET_NUM_3,
                                             'dst': self.dut_vlan_101_ip}}
            PingChecker(self.players, ping_hb_dut_vlan_101).run_validation()

        with allure.step(f'Send ping from HB to DUT via VLAN {VxlanConstants.VLAN_20}'):
            ping_hb_dut_vlan_20 = {'sender': 'hb',
                                   'args': {'interface': HB_VLAN_20_IFACE, 'count': VxlanConstants.PACKET_NUM_3,
                                            'dst': self.dut_vlan_20_ip}}
            PingChecker(self.players, ping_hb_dut_vlan_20).run_validation()

    def validate_vxlan_traffic(self, interfaces):
        """
        This method is used to validate vxlan traffic
        :param interfaces: interfaces fixture
        """
        # Routing
        with allure.step('Send traffic from HB to HA via VLAN 101 to VNI 500100(routing)'):
            pkt_hb_ha_vlan101_vni500100_r = VxlanConstants.SIMPLE_PACKET.format(self.hb_bond0_101_mac, self.dut_mac,
                                                                                self.hb_vlan_101_iface_ip,
                                                                                self.ha_vni_500100_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=HB_VLAN_101_IFACE, sender_pkt_format=pkt_hb_ha_vlan101_vni500100_r,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                          VxlanConstants.HEX_500100,
                                          VxlanConstants.HEX_101_0_0_3))
        # Negative validations
        with allure.step('Send traffic from HB to HA via VNI 500100 to VNI 500100(negative)'):
            pkt_hb_ha_vni500100_vni500100 = VxlanConstants.SIMPLE_PACKET.format(self.hb_br_500100_mac,
                                                                                self.ha_br_500100_mac,
                                                                                self.hb_vni_500100_iface_ip,
                                                                                self.ha_vni_500100_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=VxlanConstants.VNI_500100_IFACE,
                                      sender_pkt_format=pkt_hb_ha_vni500100_vni500100,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                          VxlanConstants.HEX_500100,
                                          VxlanConstants.HEX_100_0_0_3), receiver_count=VxlanConstants.PACKET_NUM_0)

        with allure.step('Send traffic from HB to HA via VLAN 101 to VNI 500100(negative)'):
            pkt_hb_ha_vlan101_vni500100 = VxlanConstants.SIMPLE_PACKET.format(self.hb_bond0_101_mac,
                                                                              self.ha_br_500100_mac,
                                                                              self.hb_vlan_101_iface_ip,
                                                                              self.ha_vni_500100_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=HB_VLAN_101_IFACE, sender_pkt_format=pkt_hb_ha_vlan101_vni500100,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                          VxlanConstants.HEX_500100,
                                          VxlanConstants.HEX_101_0_0_3), receiver_count=VxlanConstants.PACKET_NUM_0)

        with allure.step('Send traffic from HB to HA via VNI 500100 to VNI 500101(negative)'):
            pkt_hb_ha_vni500100_vni500101 = VxlanConstants.SIMPLE_PACKET.format(self.hb_br_500100_mac,
                                                                                self.ha_br_500101_mac,
                                                                                self.hb_vni_500100_iface_ip,
                                                                                self.ha_vni_500101_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=VxlanConstants.VNI_500100_IFACE,
                                      sender_pkt_format=pkt_hb_ha_vni500100_vni500101,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                          VxlanConstants.HEX_500101,
                                          VxlanConstants.HEX_100_0_0_3), receiver_count=VxlanConstants.PACKET_NUM_0)

    def validate_symmetrical_irb_traffic(self, interfaces):
        """
        This method is used to validate evpn symmetrical irb traffic
        :param interfaces: interfaces fixture
        """
        with allure.step(f"Send traffic from HB to HA via L3 VNI:{VxlanConstants.VNI_500200}"):
            pkt_hb_ha_l3_vni500200 = VxlanConstants.SIMPLE_PACKET.format(self.hb_bond0_20_mac, self.dut_mac,
                                                                         self.hb_vlan_20_iface_ip,
                                                                         self.ha_vni_500200_iface_ip)
            logger.info(f"Send and validate traffic:{pkt_hb_ha_l3_vni500200}")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=HB_VLAN_20_IFACE, sender_pkt_format=pkt_hb_ha_l3_vni500200,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                          VxlanConstants.HEX_500200,
                                          VxlanConstants.HEX_20_0_0_3))

    def test_evpn_vxlan_basic(self, cli_objects, interfaces, skip_if_upgrade):
        """
        This test will check basic EVPN VXLAN functionality.

        Test has next steps:
        1. Check VLAN to VNI mapping
        2. Do traffic validations
            - Send ping from HB to DUT via VLAN 101
            - Send traffic from HB to HA via VNI 500100 to VNI 500100(negative)
            - Send traffic from HB to HA via VLAN 101 to VNI 500100(negative)
            - Send traffic from HB to HA via VLAN 101 to VNI 500100(routing)
            - Send traffic from HB to HA via VNI 500100 to VNI 500101(negative)
        3. Do CLI validations via FRR for: type-2, type-3 routes on DUT, HA, HB

                                                dut
                                           -------------------------------
                 ha                        | Loopback0 10.1.0.32/32      |                                  hb
          --------------------------- BGP  |                             |               ----------------------------
          | bond0 30.0.0.2/24       |------| PortChannel0001 30.0.0.1/24 |               | vni500100 100.0.0.3/24   |
          |                         |      | Vlan100 100.0.0.1/24        |               |                          |
          | vni500100 100.0.0.2/24  |      | Vlan101 101.0.0.1/24        |    BGP        |                          |
          | vni500101 101.0.0.2/24  |      |              PortChannel0002|---------------| bond0.40                 |
          ---------------------------      | VNI500100=Vlan100  Vlan40   |               | bond0.101 101.0.0.3/24   |
                                           | VNI500101=Vlan101  Vlan101  |               ----------------------------
                                           -------------------------------
                vtep 30.0.0.2                    vtep 10.1.0.32                                 vtep 40.0.0.3
              (vxlan encap/decap)              (vxlan encap/decap)                            (vxlan encap/decap)

        """
        with allure.step('Check CLI VLAN to VNI mapping'):
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                   (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101),
                                   (VxlanConstants.VLAN_20, VxlanConstants.VNI_50020),
                                   (VxlanConstants.VLAN_200, VxlanConstants.VNI_500200)
                                   ])
        with allure.step('Validate L3 connectivity'):
            self.validate_l3_connectivity()

        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)

        with allure.step('Validate evpn type 5 routes'):
            self.validate_basic_evpn_type_5_route(cli_objects)

        with allure.step('Validate VXLAN traffic'):
            self.validate_vxlan_traffic(interfaces)

        with allure.step('Validate EVPN symmetrical irb traffic'):
            self.validate_symmetrical_irb_traffic(interfaces)

    def test_prevent_remove_recovered_fdb_table(self, cli_objects, skip_if_upgrade):
        """
        This test is designed dedicate for https://redmine.mellanox.com/issues/3460839
        Steps to validate:
            Configure L2 EVPN and learn remote FDB entries.
            Perform warm reboot.
            After system has reconciled, withdraw few of the remote FDB entries.
        """
        with allure.step('Withdraw and announce remote EVPN routes'):
            restart_bgp_session(cli_objects.ha)

        with allure.step('Validate bgp neighbor established'):
            cli_objects.ha.frr.validate_bgp_neighbor_established(self.dut_ha_1_ip)

        with allure.step('Check CLI VLAN to VNI mapping'):
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                   (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101),
                                   (VxlanConstants.VLAN_20, VxlanConstants.VNI_50020),
                                   (VxlanConstants.VLAN_200, VxlanConstants.VNI_500200)
                                   ])
