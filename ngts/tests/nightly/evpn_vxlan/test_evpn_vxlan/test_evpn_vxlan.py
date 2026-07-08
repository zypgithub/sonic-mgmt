import logging
import pytest
import os

from ngts.config_templates.vlan_config_template import VlanConfigTemplate
from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.config_templates.vxlan_config_template import VxlanConfigTemplate
from ngts.config_templates.frr_config_template import FrrConfigTemplate
from ngts.constants.constants import VxlanConstants
from ngts.helpers.vxlan_helper import apply_fdb_config, send_and_validate_traffic, verify_counter_entry, \
    verify_mac_entry_learned, verify_mac_entry_not_learned, vni_to_hex_vni, verify_bgp_container_up, \
    config_evpn_route_map, remove_evpn_route_map
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from devts.infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker

"""

EVPN VXLAN Test Cases

Documentation: https://confluence.nvidia.com/pages/viewpage.action?spaceKey=SW&title=SONiC+NGTS+EVPN+VXLAN+Documentation

"""

logger = logging.getLogger()
allure.logger = logger

DUT_VLAN_100_IFACE = 'Vlan100'
VLAN_TO_MIN_MAX_VNI_MAP_LIST = [(1200, 1), (1000, 7385123), (575, 16777214)]
MIN_MAX_VLAN_TO_MIN_MAX_VNI_MAP_LIST = [(2, 1), (2, 123), (2, 16777214),
                                        (4094, 1), (4094, 1000), (4094, 16777214)]


@pytest.fixture(scope='module', autouse=True)
def basic_configuration(topology_obj, engines, cli_objects, interfaces):
    """
    Pytest fixture used to configure basic vxlan configuration
    :param topology_obj: topology object fixture
    :param cli_objects: cli_objects fixture
    :param engines: engines fixture
    :param interfaces:  interfaces fixture
    """
    vlan_config_dict = {
        'dut': [{'vlan_id': 40, 'vlan_members': [{interfaces.dut_ha_2: 'trunk'}, {interfaces.dut_hb_2: 'trunk'}]},
                {'vlan_id': 41, 'vlan_members': [{interfaces.dut_hb_2: 'trunk'}]},
                {'vlan_id': 100, 'vlan_members': [{interfaces.dut_ha_2: 'trunk'}]},
                {'vlan_id': 101, 'vlan_members': [{interfaces.dut_ha_2: 'trunk'}, {interfaces.dut_hb_2: 'trunk'}]}
                ],
        'ha': [{'vlan_id': 40, 'vlan_members': [{interfaces.ha_dut_2: None}]}
               ],
        'hb': [{'vlan_id': 40, 'vlan_members': [{interfaces.hb_dut_2: None}]},
               {'vlan_id': 41, 'vlan_members': [{interfaces.hb_dut_2: None}]},
               {'vlan_id': 101, 'vlan_members': [{interfaces.hb_dut_2: None}]}
               ]
    }

    ip_config_dict = {
        'dut': [{'iface': 'Vlan40', 'ips': [('40.0.0.1', '24'), ('4000::1', '64')]},
                {'iface': interfaces.dut_ha_1, 'ips': [('30.0.0.1', '24'), ('3000::1', '64')]},
                {'iface': '{}'.format(VxlanConstants.VTEP_INTERFACE), 'ips': [('10.1.0.32', '32')]},
                {'iface': 'Vlan100', 'ips': [('100.0.0.1', '24'), ('100::1', '64')]},
                {'iface': 'Vlan101', 'ips': [('101.0.0.1', '24'), ('101::1', '64')]}
                ],
        'ha': [{'iface': '{}.40'.format(interfaces.ha_dut_2), 'ips': [('40.0.0.2', '24'), ('4000::2', '64')]},
               {'iface': interfaces.ha_dut_1, 'ips': [('30.0.0.2', '24'), ('3000::2', '64')]}
               ],
        'hb': [{'iface': '{}.40'.format(interfaces.hb_dut_2), 'ips': [('40.0.0.3', '24'), ('4000::3', '64')]},
               {'iface': '{}.101'.format(interfaces.hb_dut_2), 'ips': [('101.0.0.3', '24'), ('101::3', '64')]}
               ]
    }

    frr_config_folder = os.path.dirname(os.path.abspath(__file__))
    vxlan_config_dict = {
        'dut': [{'evpn_nvo': 'my-nvo', 'vtep_name': 'vtep101032', 'vtep_src_ip': '10.1.0.32',
                 'tunnels': [{'vni': VxlanConstants.VNI_500100, 'vlan': VxlanConstants.VLAN_100},
                             {'vni': VxlanConstants.VNI_500101, 'vlan': VxlanConstants.VLAN_101}]
                 }
                ],
        'ha': [{'vtep_name': 'vtep_500100', 'vtep_src_ip': '30.0.0.2', 'vni': VxlanConstants.VNI_500100,
                'vtep_ips': [('100.0.0.2', '24'), ('100::2', '64')]},
               {'vtep_name': 'vtep_500101', 'vtep_src_ip': '30.0.0.2', 'vni': VxlanConstants.VNI_500101,
                'vtep_ips': [('101.0.0.2', '24'), ('101::2', '64')]}],
        'hb': [{'vtep_name': 'vtep_500100', 'vtep_src_ip': '40.0.0.3', 'vni': VxlanConstants.VNI_500100,
                'vtep_ips': [('100.0.0.3', '24'), ('100::3', '24')]}]
    }

    frr_config_dict = {
        'dut': {'configuration': {'config_name': 'dut_frr_config.conf', 'path_to_config_file': frr_config_folder},
                'cleanup': ['configure terminal', 'no router bgp', 'exit', 'exit']},
        'ha': {'configuration': {'config_name': 'ha_frr_config.conf', 'path_to_config_file': frr_config_folder},
               'cleanup': ['configure terminal', 'no router bgp', 'exit', 'exit']},
        'hb': {'configuration': {'config_name': 'hb_frr_config.conf', 'path_to_config_file': frr_config_folder},
               'cleanup': ['configure terminal', 'no router bgp', 'exit', 'exit']}
    }

    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    logger.info('Basic vlan and ip connectivity configuration completed')
    VxlanConfigTemplate.configuration(topology_obj, vxlan_config_dict)
    # in case there is useless bgp configuration exist
    FrrConfigTemplate.cleanup(topology_obj, frr_config_dict)
    FrrConfigTemplate.configuration(topology_obj, frr_config_dict)
    logger.info('Evpn vxlan configuration completed')
    logger.info("Enable vxlan counter")
    cli_objects.dut.vxlan.enable_vxlan_counter()
    with allure.step(
            f"Configure static mac address:{VxlanConstants.STATIC_MAC_OPERATION_SET} vlan:{VxlanConstants.VLAN_101} \
            port:{interfaces.dut_hb_2}"):
        apply_fdb_config(engines, vlan_id=VxlanConstants.VLAN_101, port=interfaces.dut_hb_2,
                         op=VxlanConstants.STATIC_MAC_OPERATION_SET, static_mac=VxlanConstants.STATIC_MAC_ADDR)

    yield

    with allure.step(
            f"Delete static mac address:{VxlanConstants.STATIC_MAC_OPERATION_SET} vlan:{VxlanConstants.VLAN_101} \
            port:{interfaces.dut_hb_2}"):
        apply_fdb_config(engines, vlan_id=VxlanConstants.VLAN_101, port=interfaces.dut_hb_2,
                         op=VxlanConstants.STATIC_MAC_OPERATION_DEL, static_mac=VxlanConstants.STATIC_MAC_ADDR)
    logger.info("Disable vxlan counter")
    cli_objects.dut.vxlan.disable_vxlan_counter()
    VxlanConfigTemplate.cleanup(topology_obj, vxlan_config_dict)
    FrrConfigTemplate.cleanup(topology_obj, frr_config_dict)
    logger.info('Evpn vxlan configuration cleanup completed')
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    VlanConfigTemplate.cleanup(topology_obj, vlan_config_dict)
    logger.info('Basic vlan and ip connectivity configuration cleanup completed')


@pytest.fixture(scope='class')
def mac_addresses(engines, cli_objects, interfaces):
    hb_vlan_101_iface = '{}.101'.format(interfaces.hb_dut_2)
    dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(DUT_VLAN_100_IFACE)
    ha_br_500100_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
    ha_br_500101_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500101_IFACE)
    hb_br_500100_mac = cli_objects.hb.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
    hb_vlan_101_mac = cli_objects.hb.mac.get_mac_address_for_interface(hb_vlan_101_iface)

    return dut_mac, ha_br_500100_mac, ha_br_500101_mac, hb_br_500100_mac, hb_vlan_101_mac


@pytest.fixture(scope='function')
def config_bgp_rr(topology_obj):
    frr_bgp_rr_config = {
        'configuration': [
            'configure terminal',
            'router bgp',
            'address-family l2vpn evpn',
            'neighbor 30.0.0.2 route-reflector-client',
            'neighbor 40.0.0.3 route-reflector-client',
            'exit',
            'exit'],
        'cleanup': [
            'configure terminal',
            'router bgp',
            'address-family l2vpn evpn',
            'no neighbor 30.0.0.2 route-reflector-client',
            'no neighbor 40.0.0.3 route-reflector-client',
            'exit',
            'exit']}
    with allure.step('Config BGP RR'):
        cli_object = topology_obj.players['dut']['cli']
        cli_object.frr.run_config_frr_cmd(frr_bgp_rr_config['configuration'])
        cli_object.frr.save_frr_configuration()

    yield

    with allure.step('Clear BGP RR configuration'):
        cli_object.frr.run_config_frr_cmd(frr_bgp_rr_config['cleanup'])
        cli_object.frr.save_frr_configuration()


class TestEvpnVxlan:

    @pytest.fixture(autouse=True)
    def prepare_param(self, topology_obj, engines, players, interfaces, mac_addresses):
        self.topology_obj = topology_obj
        self.engines = engines
        self.players = players
        self.interfaces = interfaces

        self.dut_loopback_ip = '10.1.0.32'
        self.dut_vlan_100_ip = '100.0.0.1'
        self.dut_vlan_101_ip = '101.0.0.1'
        self.dut_ha_1_ip = '30.0.0.1'
        self.dut_vlan_40_ip = '40.0.0.1'

        self.ha_dut_1_ip = '30.0.0.2'
        self.ha_vni_500100_iface_ip = '100.0.0.2'
        self.ha_vni_500101_iface_ip = '101.0.0.2'

        self.hb_vlan_40_ip = '40.0.0.3'
        self.hb_vni_500100_iface_ip = '100.0.0.3'
        self.hb_vlan_101_iface_ip = '101.0.0.3'

        self.hb_vlan_101_iface = f"{interfaces.hb_dut_2}.101"
        self.hb_vlan_40_iface = f"{interfaces.hb_dut_2}.40"

        self.dut_bgp_neighbor_30_0_0_2 = self.ha_dut_1_ip
        self.ha_bgp_neighbor_30_0_0_1 = self.dut_ha_1_ip

        self.dut_vtep_ip = self.dut_loopback_ip
        self.ha_vtep_ip = self.ha_dut_1_ip
        self.hb_vtep_ip = self.hb_vlan_40_ip

        self.dut_mac, self.ha_br_500100_mac, self.ha_br_500101_mac, self.hb_br_500100_mac, self.hb_vlan_101_mac = \
            mac_addresses

    def config_vlan_vni_map(self, topology_obj, interfaces, vlan_id, vni):
        """
        This method is used to config vlan and vni map related configurations
        :param topology_obj: topology_obj fixture
        :param interfaces: interfaces fixture
        :param vlan_id: vlan id
        :param vni: vni
        """
        vlan_config_dict = {
            'dut': [{'vlan_id': '{}'.format(vlan_id), 'vlan_members': [{interfaces.dut_ha_2: 'trunk'}]}
                    ]
        }

        ip_config_dict = {
            'dut': [{'iface': 'Vlan{}'.format(vlan_id), 'ips': [
                (VxlanConstants.DUT_VNI_INTF_ADDRESS_TEMPLATE.format(vlan_id % VxlanConstants.IP_GENERATE_SEED), '24')]}
            ]
        }

        vxlan_config_dict = {
            'dut': [{'vtep_name': 'vtep101032', 'vtep_src_ip': '10.1.0.32',
                     'tunnels': [{'vni': '{}'.format(vni), 'vlan': '{}'.format(vlan_id)}]}
                    ],
            'ha': [{'vtep_name': 'vtep_{}'.format(vni), 'vtep_src_ip': '30.0.0.2', 'vni': '{}'.format(vni),
                    'vtep_ips': [(VxlanConstants.VM_VNI_INTF_ADDRESS_TEMPLATE.format(
                        vlan_id % VxlanConstants.IP_GENERATE_SEED), '24')]}],
        }

        logger.info('Evpn vxlan configuration completed')
        VlanConfigTemplate.configuration(topology_obj, vlan_config_dict)
        IpConfigTemplate.configuration(topology_obj, ip_config_dict)
        VxlanConfigTemplate.configuration(topology_obj, vxlan_config_dict)

    def clean_vlan_vni_map(self, topology_obj, interfaces, vlan_id, vni):
        """
        This method is used to clean vlan and vni map related configurations
        :param topology_obj: topology_obj fixture
        :param interfaces: interfaces fixture
        :param vlan_id: vlan id
        :param vni: vni
        """
        vlan_config_dict = {
            'dut': [{'vlan_id': '{}'.format(vlan_id), 'vlan_members': [{interfaces.dut_ha_2: 'trunk'}]}
                    ]
        }

        ip_config_dict = {
            'dut': [{'iface': 'Vlan{}'.format(vlan_id), 'ips': [
                (VxlanConstants.DUT_VNI_INTF_ADDRESS_TEMPLATE.format(vlan_id % VxlanConstants.IP_GENERATE_SEED), '24')]}
            ]
        }

        vxlan_config_dict = {
            'dut': [{'vtep_name': 'vtep101032', 'vtep_src_ip': '10.1.0.32',
                     'tunnels': [{'vni': '{}'.format(vni), 'vlan': '{}'.format(vlan_id)}]}
                    ],
            'ha': [{'vtep_name': 'vtep_{}'.format(vni), 'vtep_src_ip': '30.0.0.2', 'vni': '{}'.format(vni),
                    'vtep_ips': [(VxlanConstants.VM_VNI_INTF_ADDRESS_TEMPLATE.format(
                        vlan_id % VxlanConstants.IP_GENERATE_SEED), '24')]}],
        }

        logger.info('Cleanup evpn vxlan configuration')
        VxlanConfigTemplate.cleanup(topology_obj, vxlan_config_dict)
        IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
        VlanConfigTemplate.cleanup(topology_obj, vlan_config_dict)

    def get_ha_br_mac(self, cli_objects, vni):
        """
        This method is used to get the mac address of bridge interface at HA
        :param cli_objects: cli_objects fixture
        :return: mac address of bridge interface at HA
        """
        ha_vni_iface = f"br_{vni}"
        ha_br_mac = cli_objects.ha.mac.get_mac_address_for_interface(ha_vni_iface)
        return ha_br_mac

    def validate_basic_evpn_type_2_route(self, cli_objects):
        """
        This method is used to verify basic evpn type 2 route states
        :param cli_objects: cli_objects fixture
        """
        with allure.step('Send ping from HB to DUT via VLAN 101'):
            ping_hb_dut_vlan_101 = {'sender': 'hb',
                                    'args': {'interface': self.hb_vlan_101_iface, 'count': VxlanConstants.PACKET_NUM_3,
                                             'dst': self.dut_vlan_101_ip}}
            PingChecker(self.players, ping_hb_dut_vlan_101).run_validation()

        # VXLAN route validation
        with allure.step('Validate CLI type-2 routes on DUT'):
            dut_type_2_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_macip()
            cli_objects.dut.frr.validate_type_2_route(dut_type_2_info, self.hb_vlan_101_mac, self.dut_loopback_ip,
                                                      VxlanConstants.RD_101, self.hb_vlan_101_iface_ip)

        with allure.step('Validate CLI type-2 routes on HA'):
            ha_type_2_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_macip()
            cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, self.hb_vlan_101_mac, self.dut_loopback_ip,
                                                     VxlanConstants.RD_101, self.hb_vlan_101_iface_ip)

    def validate_basic_evpn_type_2_3_route(self, cli_objects, learned=True):
        """
        This method is used to verify basic evpn type 2 and type 3 route states
        :param cli_objects: cli_objects fixture
        """
        with allure.step('Send ping from HB to DUT via VLAN 101'):
            ping_hb_dut_vlan_101 = {'sender': 'hb',
                                    'args': {'interface': self.hb_vlan_101_iface, 'count': VxlanConstants.PACKET_NUM_3,
                                             'dst': self.dut_vlan_101_ip}}
            PingChecker(self.players, ping_hb_dut_vlan_101).run_validation()

        # VXLAN route validation
        with allure.step('Validate CLI type-2 routes on DUT'):
            dut_type_2_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_macip()
            cli_objects.dut.frr.validate_type_2_route(dut_type_2_info, self.hb_vlan_101_mac, self.dut_loopback_ip,
                                                      VxlanConstants.RD_101, self.hb_vlan_101_iface_ip)

        with allure.step('Validate CLI type-3 routes on DUT'):
            dut_type_3_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_multicast()
            cli_objects.dut.frr.validate_type_3_route(dut_type_3_info, self.ha_dut_1_ip, self.ha_dut_1_ip,
                                                      VxlanConstants.RD_100)
            cli_objects.dut.frr.validate_type_3_route(dut_type_3_info, self.ha_dut_1_ip, self.ha_dut_1_ip,
                                                      VxlanConstants.RD_101)

            cli_objects.dut.frr.validate_type_3_route(dut_type_3_info, self.hb_vlan_40_ip, self.hb_vlan_40_ip,
                                                      VxlanConstants.RD_100)

        with allure.step('Validate CLI type-2 routes on HA'):
            ha_type_2_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_macip()
            cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, self.hb_vlan_101_mac, self.dut_loopback_ip,
                                                     VxlanConstants.RD_101, self.hb_vlan_101_iface_ip, learned)

        with allure.step('Validate CLI type-3 routes on HA'):
            ha_type_3_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_multicast()
            cli_objects.ha.frr.validate_type_3_route(ha_type_3_info, self.dut_loopback_ip, self.dut_loopback_ip,
                                                     VxlanConstants.RD_100, learned)
            cli_objects.ha.frr.validate_type_3_route(ha_type_3_info, self.dut_loopback_ip, self.dut_loopback_ip,
                                                     VxlanConstants.RD_101, learned)

        with allure.step('Validate CLI type-3 routes on HB'):
            hb_type_3_info = cli_objects.hb.frr.get_l2vpn_evpn_route_type_multicast()
            cli_objects.hb.frr.validate_type_3_route(hb_type_3_info, self.dut_loopback_ip, self.dut_loopback_ip,
                                                     VxlanConstants.RD_100, learned)
            cli_objects.hb.frr.validate_type_3_route(hb_type_3_info, self.dut_loopback_ip, self.dut_loopback_ip,
                                                     VxlanConstants.RD_101, learned)

    def validate_traffic_and_counters(self, cli_objects, interfaces, vtep_mode=False):
        with allure.step("Send traffic from HB to HA via VLAN 101 to VNI 500101"):
            logger.info("Clear vxlan counter")
            cli_objects.dut.vxlan.clear_vxlan_counter()
            pkt_hb_ha_vlan101_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.hb_vlan_101_mac,
                                                                                self.ha_br_500101_mac,
                                                                                self.hb_vlan_101_iface_ip,
                                                                                self.ha_vni_500101_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_101_iface,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_500, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                          VxlanConstants.HEX_500101,
                                          VxlanConstants.HEX_101_0_0_3))
            logger.info("Validate vxlan tx counters")
            verify_counter_entry(cli_objects, VxlanConstants.VTEP_NAME_DUT, 'tx', 500, vtep_mode)

        with allure.step("Send traffic from HA to HB via to VNI 500101"):
            logger.info("Clear vxlan counter")
            cli_objects.dut.vxlan.clear_vxlan_counter()
            pkt_hb_ha_vlan101_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.ha_br_500101_mac,
                                                                                self.hb_vlan_101_mac,
                                                                                self.ha_vni_500101_iface_ip,
                                                                                self.hb_vlan_101_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HA,
                                      sender_intf=VxlanConstants.VNI_500101_IFACE,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_500, receiver=VxlanConstants.HOST_HB,
                                      receiver_intf=self.hb_vlan_101_iface,
                                      receiver_filter_format=VxlanConstants.SIMPLE_PACKET_FILTER.format(
                                          self.hb_vlan_101_iface_ip))
            logger.info("Validate vxlan rx counters")
            verify_counter_entry(cli_objects, VxlanConstants.VTEP_NAME_DUT, 'rx', 500, vtep_mode)

    def config_bgp_unnumbered_mode_between_ha_dut(self, cli_objects, interfaces):
        """
        This method is used to configure BGP unnumbered mode between ha and dut
        :param cli_objects: cli_objects fixture
        :param interfaces: interfaces fixture
        :return:
        """
        logger.info(
            f"Configure BGP unnumbered at DUT - {interfaces.dut_ha_1} - bgp session {VxlanConstants.BGP_SESSION_ID}")
        cli_objects.dut.frr.config_bgp_unnumbered_mode(VxlanConstants.BGP_SESSION_ID, self.dut_bgp_neighbor_30_0_0_2,
                                                       interfaces.dut_ha_1)
        logger.info(
            f"Configure BGP unnumbered at HA - {interfaces.ha_dut_1} - bgp session {VxlanConstants.BGP_SESSION_ID}")
        cli_objects.ha.frr.config_bgp_unnumbered_mode(VxlanConstants.BGP_SESSION_ID, self.ha_bgp_neighbor_30_0_0_1,
                                                      interfaces.ha_dut_1)

    def clean_bgp_unnumbered_mode_between_ha_dut(self, cli_objects, interfaces):
        """
        This method is used to clean BGP unnumbered mode between ha and dut and recovery default BGP configuration
        :param cli_objects: cli_objects fixture
        :param interfaces: interfaces fixture
        :return:
        """
        logger.info(
            f"Clean BGP unnumbered at DUT - {interfaces.dut_ha_1} - bgp session {VxlanConstants.BGP_SESSION_ID} \
            then recover default BGP configuration")
        cli_objects.dut.frr.clean_bgp_unnumbered_mode(VxlanConstants.BGP_SESSION_ID, self.dut_bgp_neighbor_30_0_0_2,
                                                      interfaces.dut_ha_1)
        logger.info(
            f"Clean BGP unnumbered at HA - {interfaces.ha_dut_1} - bgp session {VxlanConstants.BGP_SESSION_ID} \
            then recover default BGP configuration")
        cli_objects.ha.frr.clean_bgp_unnumbered_mode(VxlanConstants.BGP_SESSION_ID, self.ha_bgp_neighbor_30_0_0_1,
                                                     interfaces.ha_dut_1)

    def validate_vxlan_tunnel(self, cli_objects):
        """
        This method is used to validate vxlan tunnel info
        :param cli_objects: cli_objects fixture
        """
        expected_tunnel_infos = []
        for vlan, vni in [(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                          (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101)]:
            expected_tunnel_info = {'vxlan tunnel name': VxlanConstants.VTEP_NAME_DUT,
                                    'source ip': self.dut_loopback_ip,
                                    'destination ip': '',
                                    'tunnel map name': 'map_{}_Vlan{}'.format(vni, vlan),
                                    'tunnel map mapping(vni -> vlan)': '{} -> Vlan{}'.format(vni, vlan)}
            expected_tunnel_infos.append(expected_tunnel_info)
        cli_objects.dut.vxlan.check_vxlan_tunnels(expected_tunnels_info_list=[expected_tunnel_info])

    def hb_trigger_local_mac_learning(self, interfaces):
        """
        Trigger dut local mac learning at HB by unknown traffic
        HB is connected with DUT directly by vlan, this is called 'local' in vxlan scenario
        """
        unknown_trigger_pkt = VxlanConstants.SIMPLE_PACKET.format(VxlanConstants.SOURCE_MAC_ADDR_1,
                                                                  VxlanConstants.UNKNOWN_UNICAST_MAC,
                                                                  VxlanConstants.UNKNOWN_SRC_IP,
                                                                  VxlanConstants.UNKNOWN_DST_IP)
        logger.info("Trigger DUT local mac learning by send unknown traffic at HB")
        send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                  sender_intf=self.hb_vlan_101_iface, sender_pkt_format=unknown_trigger_pkt,
                                  sender_count=VxlanConstants.PACKET_NUM_500, receiver=VxlanConstants.HOST_HA,
                                  receiver_intf=interfaces.ha_dut_1,
                                  receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                      VxlanConstants.HEX_500101,
                                      VxlanConstants.HEX_UNKNOWN_SRC_IP))

    def trigger_remote_mac_learning(self, engines, intf, vlan):
        """
        Trigger dut remote mac learning at HA by traffic
        :param engines: engines interfaces
        :param intf: interface name
        :param vlan: vlan id
        """
        unknown_trigger_pkt = VxlanConstants.SIMPLE_DOT1Q_PACKET.format(VxlanConstants.SOURCE_MAC_ADDR_1,
                                                                        VxlanConstants.BROADCAST_MAC, vlan,
                                                                        VxlanConstants.UNKNOWN_SRC_IP,
                                                                        VxlanConstants.UNKNOWN_DST_IP)
        logger.info("Trigger remote mac learning by send unknown traffic from DUT to HA")
        cmd = '''
cat << EOF > send_traffic.py
from scapy.all import *
from scapy.contrib.roce import *

sendp({}, iface="{}", count={})
EOF
'''.format(unknown_trigger_pkt, intf, VxlanConstants.PACKET_NUM_100)
        logger.info(f"Traffic: {unknown_trigger_pkt}")
        engines.dut.run_cmd(cmd)
        engines.dut.run_cmd("sudo python3 send_traffic.py")

    def validate_mac_move_local_to_remote(self, cli_objects, engines, interfaces):
        """
        This method is used to verify mac move from local(vlan) to remote(vxlan)
        :param cli_objects: cli_objects fixture
        :param interfaces: interfaces fixture
        """
        try:
            with allure.step('Bind {}.40 with bridge {}'.format(interfaces.ha_dut_2, VxlanConstants.VNI_500101_IFACE)):
                cli_objects.ha.vxlan.bind_if_with_bridge(VxlanConstants.VNI_500101_IFACE,
                                                         '{}.40'.format(interfaces.ha_dut_2))

            with allure.step('Validate local MAC learning'):
                logger.info('Trigger switch local mac learning')
                self.hb_trigger_local_mac_learning(interfaces)
                logger.info('Check local mac learning')
                verify_mac_entry_learned(cli_objects, vlan_id=VxlanConstants.VLAN_101,
                                         mac=VxlanConstants.SOURCE_MAC_ADDR_1,
                                         port=interfaces.dut_hb_2)

            with allure.step('Validate remote MAC learning by VXLAN'):
                logger.info('Trigger switch remote mac learning at HA')
                self.trigger_remote_mac_learning(engines, interfaces.dut_ha_2, 40)
                logger.info(
                    f"Validate MAC {VxlanConstants.SOURCE_MAC_ADDR_1} is learned from remote HA by EVPN VXLAN - \
                    vlan {VxlanConstants.RD_101} - vtep {self.ha_vtep_ip} - vni {VxlanConstants.VNI_500101}")
                cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                    (VxlanConstants.RD_101, VxlanConstants.SOURCE_MAC_ADDR_1, self.ha_vtep_ip,
                     VxlanConstants.VNI_500101),
                ])

            with allure.step(f"Validate MAC {VxlanConstants.SOURCE_MAC_ADDR_1} is removed from local MAC table"):
                verify_mac_entry_not_learned(cli_objects, vlan_id=VxlanConstants.VLAN_101,
                                             mac=VxlanConstants.SOURCE_MAC_ADDR_1,
                                             port=interfaces.dut_hb_2)

        except Exception as err:
            raise AssertionError(err)
        finally:
            with allure.step(
                    'Unbind {}.40 with bridge {}'.format(interfaces.ha_dut_2, VxlanConstants.VNI_500101_IFACE)):
                cli_objects.ha.vxlan.unbind_if_with_bridge(VxlanConstants.VNI_500101_IFACE,
                                                           '{}.40'.format(interfaces.ha_dut_2))

    def validate_mac_move_remote_to_local(self, cli_objects, engines, interfaces):
        """
        This method is used to verify mac move from remote(vxlan) to local(vlan)
        :param cli_objects: cli_objects fixture
        :param engines: engines fixture
        :param interfaces: interfaces fixture
        """
        try:
            with allure.step('Bind {}.40 with bridge {}'.format(interfaces.ha_dut_2, VxlanConstants.VNI_500101_IFACE)):
                cli_objects.ha.vxlan.bind_if_with_bridge(VxlanConstants.VNI_500101_IFACE,
                                                         '{}.40'.format(interfaces.ha_dut_2))

            with allure.step('Validate remote MAC learning by VXLAN'):
                logger.info('Trigger switch remote mac learning at HA')
                self.trigger_remote_mac_learning(engines, interfaces.dut_ha_2, 40)
                logger.info(
                    f"Validate MAC {VxlanConstants.SOURCE_MAC_ADDR_1} is learned from remote HA by EVPN VXLAN - \
                    vlan {VxlanConstants.RD_101} - vtep {self.ha_vtep_ip} - vni {VxlanConstants.VNI_500101}")
                cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                    (VxlanConstants.RD_101, VxlanConstants.SOURCE_MAC_ADDR_1, self.ha_vtep_ip,
                     VxlanConstants.VNI_500101),
                ])

            with allure.step('Validate local MAC learning'):
                logger.info('Trigger switch local mac learning')
                self.hb_trigger_local_mac_learning(interfaces)
                logger.info('Check local mac learning')
                verify_mac_entry_learned(cli_objects, vlan_id=VxlanConstants.VLAN_101,
                                         mac=VxlanConstants.SOURCE_MAC_ADDR_1,
                                         port=interfaces.dut_hb_2)

            with allure.step(f"Validate MAC {VxlanConstants.SOURCE_MAC_ADDR_1} is removed from VXLAN remote mac table"):
                cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                    (VxlanConstants.RD_101, VxlanConstants.SOURCE_MAC_ADDR_1, self.ha_vtep_ip,
                     VxlanConstants.VNI_500101),
                ], learned=False)

        except Exception as err:
            raise AssertionError(err)
        finally:
            with allure.step(
                    'Unbind {}.40 with bridge {}'.format(interfaces.ha_dut_2, VxlanConstants.VNI_500101_IFACE)):
                cli_objects.ha.vxlan.unbind_if_with_bridge(VxlanConstants.VNI_500101_IFACE,
                                                           '{}.40'.format(interfaces.ha_dut_2))

    def validate_mac_move_remote_to_remote(self, cli_objects, engines, interfaces):
        """
        This method is used to verify mac move from remote(vxlan) to remote(vxlan)
        :param cli_objects: cli_objects fixture
        :param engines: engines fixture
        :param engines: interfaces fixture
        """
        try:
            with allure.step('Bind {}.40 with bridge {}'.format(interfaces.ha_dut_2, VxlanConstants.VNI_500100_IFACE)):
                cli_objects.ha.vxlan.bind_if_with_bridge(VxlanConstants.VNI_500100_IFACE,
                                                         '{}.40'.format(interfaces.ha_dut_2))

            with allure.step('Bind {}.41 with bridge {}'.format(interfaces.hb_dut_2, VxlanConstants.VNI_500100_IFACE)):
                cli_objects.hb.vxlan.bind_if_with_bridge(VxlanConstants.VNI_500100_IFACE,
                                                         '{}.41'.format(interfaces.hb_dut_2))

            with allure.step('Validate remote MAC learning by VXLAN at HA'):
                logger.info('Trigger switch remote mac learning at HA')
                self.trigger_remote_mac_learning(engines, interfaces.dut_ha_2, 40)
                logger.info(
                    f"Validate MAC {VxlanConstants.SOURCE_MAC_ADDR_1} is learned from remote HA by EVPN VXLAN - \
                    vlan {VxlanConstants.RD_100} - vtep {self.ha_vtep_ip} - vni {VxlanConstants.VNI_500100}")
                cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                    (VxlanConstants.RD_100, VxlanConstants.SOURCE_MAC_ADDR_1, self.ha_vtep_ip,
                     VxlanConstants.VNI_500100),
                ])

            with allure.step('Validate remote MAC learning by VXLAN at HB'):
                logger.info('Trigger switch remote mac learning at HB')
                self.trigger_remote_mac_learning(engines, interfaces.dut_hb_2, 41)
                logger.info(
                    f"Validate MAC {VxlanConstants.SOURCE_MAC_ADDR_1} is learned from remote HB by EVPN VXLAN - \
                    vlan {VxlanConstants.RD_100} - vtep {self.hb_vtep_ip} - vni {VxlanConstants.VNI_500100}")
                cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                    (VxlanConstants.RD_100, VxlanConstants.SOURCE_MAC_ADDR_1, self.hb_vtep_ip,
                     VxlanConstants.VNI_500100),
                ])

            with allure.step(
                    f"Validate MAC {VxlanConstants.SOURCE_MAC_ADDR_1} from HA is removed from VXLAN remote mac table"):
                cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                    (VxlanConstants.RD_100, VxlanConstants.SOURCE_MAC_ADDR_1, self.ha_vtep_ip,
                     VxlanConstants.VNI_500100),
                ], learned=False)

        except Exception as err:
            raise AssertionError(err)
        finally:
            with allure.step(
                    'Unbind {}.40 with bridge {}'.format(interfaces.ha_dut_2, VxlanConstants.VNI_500100_IFACE)):
                cli_objects.ha.vxlan.unbind_if_with_bridge(VxlanConstants.VNI_500100_IFACE,
                                                           '{}.40'.format(interfaces.ha_dut_2))
            with allure.step(
                    'Unbind {}.41 with bridge {}'.format(interfaces.ha_dut_2, VxlanConstants.VNI_500100_IFACE)):
                cli_objects.hb.vxlan.unbind_if_with_bridge(VxlanConstants.VNI_500100_IFACE,
                                                           '{}.41'.format(interfaces.hb_dut_2))

    def test_local_mac_handling(self, engines, cli_objects):
        """
        This test will check EVPN VXLAN MAC advertise functionality.

        Test has next steps:
        1. Check VLAN to VNI mapping
        2. Configure route map to block type 2 and 3 routes
        3. Do route map deny action validations
        4. Remove route map
        5. Do type 2 and type 3 routes validations
        6. Check on HA that in tunnel with VNI 500101 via BGP received static MAC from DUT(which configured for Vlan101)
        7. Check on HA that in tunnel with VNI 500101 via BGP received MAC address for HB Vlan101 interface
        """
        try:
            with allure.step('Check CLI VLAN to VNI mapping'):
                cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                    vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                       (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101)])

            with allure.step('Configure route map to block type 2 and 3 routes'):
                config_evpn_route_map(cli_objects, VxlanConstants.EVPN_ROUTE_MAP, VxlanConstants.BGP_SESSION_ID,
                                      [
                                          (VxlanConstants.DENY, '1', '2'),
                                          (VxlanConstants.DENY, '2', '3'),
                                          (VxlanConstants.PERMIT, '3', '')
                                      ],
                                      [
                                          self.ha_vtep_ip,
                                          self.hb_vtep_ip
                                      ])
            with allure.step('Validate evpn type 2 and type 3 routes are blocked'):
                self.validate_basic_evpn_type_2_3_route(cli_objects, learned=False)

            with allure.step('Remove route map'):
                remove_evpn_route_map(cli_objects, VxlanConstants.EVPN_ROUTE_MAP, VxlanConstants.BGP_SESSION_ID,
                                      [
                                          self.ha_vtep_ip,
                                          self.hb_vtep_ip
                                      ])

            with allure.step('Validate evpn type 2 and type 3 routes are learned'):
                self.validate_basic_evpn_type_2_3_route(cli_objects)

            # MAC route validation
            with allure.step(f"Validate route received at HA of Static MAC {VxlanConstants.STATIC_MAC_ADDR}"):
                ha_type_2_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_macip()
                cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, VxlanConstants.STATIC_MAC_ADDR.replace('-', ':'),
                                                         self.dut_loopback_ip, VxlanConstants.RD_101)

            with allure.step(f"Validate route received at HA of MAC {self.hb_vlan_101_mac}"):
                ha_type_2_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_macip()
                cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, self.hb_vlan_101_mac, self.dut_loopback_ip,
                                                         VxlanConstants.RD_101, self.hb_vlan_101_iface_ip)
        except Exception as err:
            with allure.step('Remove route map'):
                remove_evpn_route_map(cli_objects, VxlanConstants.EVPN_ROUTE_MAP, VxlanConstants.BGP_SESSION_ID,
                                      [
                                          self.ha_vtep_ip,
                                          self.hb_vtep_ip
                                      ])
            raise err

    def test_remote_mac_handling(self, engines, cli_objects):
        """
        This test will check EVPN VXLAN MAC advertise functionality.

        Test has next steps:
        1. Check VLAN to VNI mapping
        2. Do type 2 and type 3 routes validations
        3. Check on DUT that MAC address for interface br500100 on HA obtained via
            BGP and available in vxlan remote MAC table
        4. Check on DUT that MAC address for interface br500101 on HA obtained via
            BGP and available in vxlan remote MAC table
        5. Check on DUT that MAC address for interface br500100 on HB obtained via
            BGP and available in vxlan remote MAC table
        """

        with allure.step('Check CLI VLAN to VNI mapping'):
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                   (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101)])

        # VXLAN route validation
        self.validate_basic_evpn_type_2_3_route(cli_objects)

        # MAC route validation
        with allure.step(f"Validate MAC route of HA {VxlanConstants.VNI_500100_IFACE} received at DUT"):
            dut_type_2_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_macip()
            cli_objects.dut.frr.validate_type_2_route(dut_type_2_info, self.ha_br_500100_mac, self.ha_vtep_ip,
                                                      VxlanConstants.RD_100, self.ha_vni_500100_iface_ip)

        with allure.step(f"Validate MAC route of HA {VxlanConstants.VNI_500101_IFACE} received at DUT"):
            dut_type_2_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_macip()
            cli_objects.dut.frr.validate_type_2_route(dut_type_2_info, self.ha_br_500101_mac, self.ha_vtep_ip,
                                                      VxlanConstants.RD_101, self.ha_vni_500101_iface_ip)

        with allure.step(f"Validate MAC route of HB {VxlanConstants.VNI_500100_IFACE} received at DUT"):
            dut_type_2_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_macip()
            cli_objects.dut.frr.validate_type_2_route(dut_type_2_info, self.hb_br_500100_mac, self.hb_vtep_ip,
                                                      VxlanConstants.RD_100, self.hb_vni_500100_iface_ip)

        # Remote MAC learning validation
        with allure.step("Validate MACs are learned from remote HA and HB"):
            cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                (VxlanConstants.RD_100, self.ha_br_500100_mac, self.ha_vtep_ip, VxlanConstants.VNI_500100),
                (VxlanConstants.RD_101, self.ha_br_500101_mac, self.ha_vtep_ip, VxlanConstants.VNI_500101),
                (VxlanConstants.RD_100, self.hb_br_500100_mac, self.hb_vtep_ip, VxlanConstants.VNI_500100)
            ])

    def test_mac_move_handling(self, engines, cli_objects, interfaces, config_bgp_rr):
        """
        This test will check EVPN VXLAN MAC advertise functionality.

        Test has next steps:
        1. Check VLAN to VNI mapping
        2. Do type 2 and type 3 routes validations
        3. Local to remote mac move validation
        4. Remote to local mac move validation
        5. Remote to remote mac move validation

        :return: raise assertion error in case when test failed
        """

        with allure.step('Check CLI VLAN to VNI mapping'):
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                   (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101)])

        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)

        with allure.step('Validate MAC move from local to remote'):
            self.validate_mac_move_local_to_remote(cli_objects, engines, interfaces)

        with allure.step('Validate MAC move from remote to local'):
            self.validate_mac_move_remote_to_local(cli_objects, engines, interfaces)

        with allure.step('Validate MAC move from remote to remote'):
            self.validate_mac_move_remote_to_remote(cli_objects, engines, interfaces)

    def test_mac_ip_route_handling(self, engines, cli_objects):
        """
        This test will check EVPN VXLAN MAC advertise functionality.

        Test has next steps:
        1. Check VLAN to VNI mapping
        2. Check on HA that in tunnel with VNI 500100 via BGP received type-2 route
            with MAC/IP from interface Vlan100 on HB(100.0.0.1)
        3. Check on HA that in tunnel with VNI 500101 via BGP received type-2 route
            with MAC/IP from interface Vlan101 on HB(101.0.0.3)
        4. Check on HA that in tunnel with VNI 500101 via BGP received type-2 route
            with MAC/IP from interface Vlan101 on DUT(101.0.0.1)

        :return: raise assertion error in case when test failed
        """

        with allure.step('Check CLI VLAN to VNI mapping'):
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                   (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101)])

        # VXLAN route validation
        with allure.step('Validate CLI type-2 routes on HA'):
            with allure.step('Send ping from HB to DUT via VLAN 101'):
                ping_hb_dut_vlan_101 = {'sender': 'hb', 'args': {'interface': self.hb_vlan_101_iface,
                                                                 'count': VxlanConstants.PACKET_NUM_3,
                                                                 'dst': self.dut_vlan_101_ip}}
                PingChecker(self.players, ping_hb_dut_vlan_101).run_validation()
            ha_type_2_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_macip()
            logger.info(
                f"Validate HA received type-2 route with MAC/IP from interface Vlan100 on DUT - {self.dut_mac} - \
                {self.dut_vlan_100_ip}")
            cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, self.dut_mac, self.dut_loopback_ip,
                                                     VxlanConstants.RD_100, self.dut_vlan_100_ip)

            logger.info(
                f"Validate HA received type-2 route with MAC/IP from interface Vlan101 on HB - {self.hb_vlan_101_mac} \
                 - {self.hb_vlan_101_iface_ip}")
            cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, self.hb_vlan_101_mac, self.dut_loopback_ip,
                                                     VxlanConstants.RD_101, self.hb_vlan_101_iface_ip)

            logger.info(
                f"Validate HA received type-2 route with MAC/IP from interface Vlan101 on DUT - {self.dut_mac} - \
                {self.dut_vlan_101_ip}")
            cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, self.dut_mac, self.dut_loopback_ip,
                                                     VxlanConstants.RD_101, self.dut_vlan_101_ip)

    def test_tunnels_statistics(self, engines, cli_objects, interfaces):
        """
        This test will check EVPN VXLAN Counter functionality.

        Test has next steps:
        1. Check VLAN to VNI mapping
        2. Check type 2 and type 3 route
        3. Send 500 packets from HB Vlan 101 to 101.0.0.2
        4. Check counters for VXLAN tunnel(TX)
        5. Send 500 packets from HA 101.0.0.2 to HB 101.0.0.3
        6. Check counters for VXLAN tunnel(RX)
        """

        with allure.step('Check CLI VLAN to VNI mapping'):
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                   (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101)])

        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)

        with allure.step("Send traffic from HB to HA via VLAN 101 to VNI 500101"):
            logger.info("Clear vxlan counter")
            cli_objects.dut.vxlan.clear_vxlan_counter()
            pkt_hb_ha_vlan101_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.hb_vlan_101_mac,
                                                                                self.ha_br_500101_mac,
                                                                                self.hb_vlan_101_iface_ip,
                                                                                self.ha_vni_500101_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_101_iface,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_500, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                          VxlanConstants.HEX_500101,
                                          VxlanConstants.HEX_101_0_0_3))
            logger.info("Validate vxlan tx counters")
            verify_counter_entry(cli_objects, VxlanConstants.VTEP_NAME_DUT, 'tx', 500)

        with allure.step("Send traffic from HA to HB via to VNI 500101"):
            logger.info("Clear vxlan counter")
            cli_objects.dut.vxlan.clear_vxlan_counter()
            pkt_hb_ha_vlan101_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.ha_br_500101_mac,
                                                                                self.hb_vlan_101_mac,
                                                                                self.ha_vni_500101_iface_ip,
                                                                                self.hb_vlan_101_iface_ip)
            logger.info("Send and validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HA,
                                      sender_intf=VxlanConstants.VNI_500101_IFACE,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_500, receiver=VxlanConstants.HOST_HB,
                                      receiver_intf=self.hb_vlan_101_iface,
                                      receiver_filter_format=VxlanConstants.SIMPLE_PACKET_FILTER.format(
                                          self.hb_vlan_101_iface_ip))
            logger.info("Validate vxlan rx counters")
            verify_counter_entry(cli_objects, VxlanConstants.VTEP_NAME_DUT, 'rx', 500)

    def test_traffic_forwarding_between_tunnels(self, cli_objects):
        """
        This test will check basic EVPN VXLAN functionality.

        Test has next steps:
        1. Check VLAN to VNI mapping
        2. Do traffic validations
            - Send ping from HA 100.0.0.2 to HB 100.0.0.3(negative)
            - Send ping from HB 40.0.0.3 to DUT 40.0.0.1, it's only forwarded in vlan
        """
        with allure.step('Check CLI VLAN to VNI mapping'):
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                   (VxlanConstants.VLAN_101, VxlanConstants.VNI_500101)])

        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)

        with allure.step(
                f"Send ping from HA {self.ha_vni_500100_iface_ip} to HB {self.hb_vni_500100_iface_ip} via VNI \
                {VxlanConstants.VNI_500100} (negative)"):
            ping_ha_hb_vni_500100 = {'sender': 'ha', 'args': {'interface': VxlanConstants.VNI_500100_IFACE,
                                                              'count': VxlanConstants.PACKET_NUM_3,
                                                              'expected_count': VxlanConstants.PACKET_NUM_0,
                                                              'dst': self.hb_vni_500100_iface_ip}}
            PingChecker(self.players, ping_ha_hb_vni_500100).run_validation()

        with allure.step(f"Send ping from Hb {self.hb_vlan_40_ip} to DUT {self.dut_vlan_40_ip} via vlan 40"):
            logger.info("Clear vxlan counter")
            cli_objects.dut.vxlan.clear_vxlan_counter()
            ping_hb_dut_vlan_40 = {'sender': 'hb',
                                   'args': {'interface': self.hb_vlan_40_iface, 'count': VxlanConstants.PACKET_NUM_3,
                                            'dst': self.dut_vlan_40_ip}}
            PingChecker(self.players, ping_hb_dut_vlan_40).run_validation()
            logger.info('There should be no packet forwards in vxlan')
            verify_counter_entry(cli_objects, VxlanConstants.VTEP_NAME_DUT, 'rx', 0)

    def test_L2_BUM(self, cli_objects, interfaces):
        """
        This test will check basic EVPN VXLAN functionality.

        Test has next steps:
        1. Send from HB broadcast traffic. Check that traffic forwarded to VXLAN tunnels
        2. Send from HA broadcast traffic from tunnel.
           Check that traffic forwarded from tunnel, but not forwarded to other tunnels
        3. Repeat steps 1-2 for Unknown Unicast
        """
        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)

        with allure.step('Send Broadcast traffic from HB to HA via VLAN 101 to VNI 500101'):
            pkt_hb_ha_vlan101_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.hb_vlan_101_mac,
                                                                                VxlanConstants.BROADCAST_MAC,
                                                                                self.hb_vlan_101_iface_ip,
                                                                                VxlanConstants.BROADCAST_IP)
            logger.info('Check that Broadcast traffic forwarded to VXLAN tunnels')
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_101_iface,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER.format(
                                          VxlanConstants.HEX_500101,
                                          VxlanConstants.HEX_255_255_255_255))
            logger.info('Check that Broadcast traffic forwarded from VXLAN tunnels and not forwarded to other tunnels')
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_101_iface,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER.format(
                                          VxlanConstants.HEX_500100,
                                          VxlanConstants.HEX_255_255_255_255),
                                      receiver_count=VxlanConstants.PACKET_NUM_0)

        with allure.step('Send Broadcast traffic from HA to DUT via VNI 500101'):
            pkt_ha_hb_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.ha_br_500101_mac,
                                                                        VxlanConstants.BROADCAST_MAC,
                                                                        self.ha_vni_500101_iface_ip,
                                                                        VxlanConstants.BROADCAST_IP)
            logger.info('Check that Broadcast traffic forwarded to VXLAN tunnels')
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HA,
                                      sender_intf=VxlanConstants.VNI_500101_IFACE,
                                      sender_pkt_format=pkt_ha_hb_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HB,
                                      receiver_intf=self.hb_vlan_101_iface,
                                      receiver_filter_format=VxlanConstants.SIMPLE_PACKET_FILTER.format(
                                          VxlanConstants.BROADCAST_IP))

        with allure.step('Send Unknown Unicast traffic from HB to HA via VLAN 101 to VNI 500101'):
            pkt_hb_ha_vlan101_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.hb_vlan_101_mac,
                                                                                VxlanConstants.UNKNOWN_UNICAST_MAC,
                                                                                self.hb_vlan_101_iface_ip,
                                                                                self.ha_vni_500101_iface_ip)
            logger.info('Check that Unknown Unicast traffic forwarded to VXLAN tunnels')
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_101_iface,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER.format(
                                          VxlanConstants.HEX_500101,
                                          VxlanConstants.HEX_101_0_0_2))
            logger.info(
                'Check that Unknown Unicast traffic forwarded from VXLAN tunnels and not forwarded to other tunnels')
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_101_iface,
                                      sender_pkt_format=pkt_hb_ha_vlan101_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER.format(
                                          VxlanConstants.HEX_500100,
                                          VxlanConstants.HEX_101_0_0_2),
                                      receiver_count=VxlanConstants.PACKET_NUM_0)

        with allure.step('Send Unknown Unicast traffic from HA to DUT via VNI 500101'):
            pkt_ha_hb_vni500101_r = VxlanConstants.SIMPLE_PACKET.format(self.ha_br_500101_mac,
                                                                        VxlanConstants.UNKNOWN_UNICAST_MAC,
                                                                        self.ha_vni_500101_iface_ip,
                                                                        self.hb_vlan_101_iface_ip)
            logger.info('Check that traffic forwarded to VXLAN tunnels')
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HA,
                                      sender_intf=VxlanConstants.VNI_500101_IFACE,
                                      sender_pkt_format=pkt_ha_hb_vni500101_r,
                                      sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HB,
                                      receiver_intf=self.hb_vlan_101_iface,
                                      receiver_filter_format=VxlanConstants.SIMPLE_PACKET_FILTER.format(
                                          VxlanConstants.DST_IP_101_0_0_3))

    def test_bgp_unnumbered(self, cli_objects, topology_obj, interfaces):
        """
        This test will check EVPN VXLAN functionality over BGP unnumbered mode.

        Test has next steps:
        1. Send traffic from HB 101.0.0.3 to HA br_500101 interface IP 101.0.0.2
        2. Check on HA that type-2 route(MAC/IP from HB) available via BGP in VXLAN tunnel
        3. Check on DUT that MAC for interface br_500101 available in vxlan remote mac table
        """
        try:
            with allure.step('Configure BGP unnumbered mode between HA and DUT'):
                self.config_bgp_unnumbered_mode_between_ha_dut(cli_objects, interfaces)
            with allure.step(f"Validate BGP neighbor {interfaces.dut_ha_1} established"):
                cli_objects.dut.frr.validate_bgp_neighbor_established(interfaces.dut_ha_1)
            with allure.step('Validate evpn type 2 routes'):
                self.validate_basic_evpn_type_2_route(cli_objects)
            with allure.step('Validate vxlan traffic and counters'):
                self.validate_traffic_and_counters(cli_objects, interfaces)
            with allure.step(
                    f"Validate MAC {self.ha_br_500101_mac} is learned from EVPN VXLAN - vlan {VxlanConstants.RD_101} \
                    - vtep {self.ha_vtep_ip} - vni {VxlanConstants.VNI_500101}"):
                cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                    (VxlanConstants.RD_101, self.ha_br_500101_mac, self.ha_vtep_ip, VxlanConstants.VNI_500101),
                ])
        except Exception as err:
            raise AssertionError(err)
        finally:
            with allure.step('Clean BGP unnumbered mode between HA and DUT and recovery default BGP configuration'):
                self.clean_bgp_unnumbered_mode_between_ha_dut(cli_objects, interfaces)

    def test_min_max_vni_id(self, cli_objects, topology_obj, interfaces):
        """
        This test will check basic EVPN VXLAN functionality.

        Test has next steps:
        1. Configure BGP/EVPN VXLAN with mapping VLAN 1200 to VNI 1 - check traffic pass via tunnel
        2. Configure BGP/EVPN VXLAN with mapping VLAN 1000 to VNI 7 385 123 - check traffic pass via tunnel
        3. Configure BGP/EVPN VXLAN with mapping VLAN 575 to VNI 16 777 214 - check traffic pass via tunnel
        """
        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)

        for vid, vni in VLAN_TO_MIN_MAX_VNI_MAP_LIST:
            try:
                with allure.step(f"Configure BGP/EVPN VXLAN with mapping vlan {vid} to vni {vni}"):
                    self.config_vlan_vni_map(topology_obj, interfaces, vid, vni)
                with allure.step(f"Validate BGP neighbor {self.hb_vlan_40_ip} established"):
                    cli_objects.dut.frr.validate_bgp_neighbor_established(self.hb_vlan_40_ip)
                with allure.step(f"Validate BGP neighbor {self.ha_dut_1_ip} established"):
                    cli_objects.dut.frr.validate_bgp_neighbor_established(self.ha_dut_1_ip)
                    ha_br_mac = self.get_ha_br_mac(cli_objects, vni)
                with allure.step(
                        f"Validate MAC {ha_br_mac} is learned from EVPN VXLAN - vlan {vid} - vtep {self.ha_vtep_ip} \
                        - vni {vni}"):
                    cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                        (vid, ha_br_mac, self.ha_vtep_ip, vni)
                    ])
                with allure.step(f"Send traffic from HB to HA via VLAN {vid} to VNI {vni}"):
                    pkt_hb_ha_vid_vni = VxlanConstants.SIMPLE_PACKET.\
                        format(self.hb_vlan_101_mac, self.dut_mac,
                               self.hb_vlan_101_iface_ip,
                               VxlanConstants.VM_VNI_INTF_ADDRESS_TEMPLATE.
                               format(vid % VxlanConstants.IP_GENERATE_SEED))
                    logger.info(f"Check that traffic forwarded to VXLAN tunnel - VLAN {vid} to VNI {vni}")
                    send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                              sender_intf=self.hb_vlan_101_iface, sender_pkt_format=pkt_hb_ha_vid_vni,
                                              sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                              receiver_intf=interfaces.ha_dut_1,
                                              receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                                  vni_to_hex_vni(vni),
                                                  VxlanConstants.HEX_101_0_0_3))
            except Exception as err:
                raise AssertionError(err)
            finally:
                logger.info(f"Clean configuration - BGP/EVPN VXLAN with mapping vlan {vid} to vni {vni}")
                self.clean_vlan_vni_map(topology_obj, interfaces, vid, vni)

    def test_min_max_vlan_id_mapping_to_vni(self, cli_objects, topology_obj, interfaces):
        """
        This test will check basic EVPN VXLAN functionality.

        Test has next steps:
        1. Configure BGP/EVPN VXLAN with mapping VLAN 1 to VNI 1 - check traffic pass via tunnel
        2. Configure BGP/EVPN VXLAN with mapping VLAN 1 to VNI 123 - check traffic pass via tunnel
        3. Configure BGP/EVPN VXLAN with mapping VLAN 1 to VNI 16 777 214 - check traffic pass via tunnel
        4. Configure BGP/EVPN VXLAN with mapping VLAN 4094 to VNI 1 - check traffic pass via tunnel
        5. Configure BGP/EVPN VXLAN with mapping VLAN 4094 to VNI 1000 - check traffic pass via tunnel
        6. Configure BGP/EVPN VXLAN with mapping VLAN 4094 to VNI 16 777 214 - check traffic pass via tunnel
        """
        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)

        for vid, vni in MIN_MAX_VLAN_TO_MIN_MAX_VNI_MAP_LIST:
            try:
                with allure.step(f"Configure BGP/EVPN VXLAN with mapping vlan {vid} to vni {vni}"):
                    self.config_vlan_vni_map(topology_obj, interfaces, vid, vni)

                with allure.step(f"Validate BGP neighbor {self.hb_vlan_40_ip} established"):
                    cli_objects.dut.frr.validate_bgp_neighbor_established(self.hb_vlan_40_ip)
                with allure.step(f"Validate BGP neighbor {self.ha_dut_1_ip} established"):
                    cli_objects.dut.frr.validate_bgp_neighbor_established(self.ha_dut_1_ip)
                    ha_br_mac = self.get_ha_br_mac(cli_objects, vni)
                with allure.step(
                        f"Validate MAC {ha_br_mac} is learned from EVPN VXLAN - vlan {vid} - vtep {self.ha_vtep_ip} \
                        - vni {vni}"):
                    cli_objects.dut.vxlan.check_vxlan_remotemac(vlan_mac_vtep_vni_check_list=[
                        (vid, ha_br_mac, self.ha_vtep_ip, vni)
                    ])
                with allure.step(f"Send traffic from HB to HA via VLAN {vid} to VNI {vni}"):
                    pkt_hb_ha_vid_vni = VxlanConstants.SIMPLE_PACKET.\
                        format(self.hb_vlan_101_mac, self.dut_mac,
                               self.hb_vlan_101_iface_ip,
                               VxlanConstants.VM_VNI_INTF_ADDRESS_TEMPLATE.
                               format(vid % VxlanConstants.IP_GENERATE_SEED))
                    logger.info(f"Check that traffic forwarded to VXLAN tunnels - VLAN {vid} to VNI {vni}")
                    send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                              sender_intf=self.hb_vlan_101_iface, sender_pkt_format=pkt_hb_ha_vid_vni,
                                              sender_count=VxlanConstants.PACKET_NUM_3, receiver=VxlanConstants.HOST_HA,
                                              receiver_intf=interfaces.ha_dut_1,
                                              receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_SRC_IP_FILTER.format(
                                                  vni_to_hex_vni(vni),
                                                  VxlanConstants.HEX_101_0_0_3))
            except Exception as err:
                raise AssertionError(err)
            finally:
                logger.info(f"Clean configuration - BGP/EVPN VXLAN with mapping vlan {vid} to vni {vni}")
                self.clean_vlan_vni_map(topology_obj, interfaces, vid, vni)

    def test_restart_bgp_on_dut(self, cli_objects, topology_obj, interfaces):
        """
        This test will check EVPN VXLAN functionality over BGP restart.

        Test has next steps:
        1. Check that traffic pass from VLAN 101 to tunnel and back, check MAC table on DUT
        2. Restart BGP in DUT
        3. Check that VXLAN tunnel established successfully after restart BGP
        4. Check that traffic pass from VLAN 101 to tunnel and back, check MAC table on DUT
        """
        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)
        with allure.step('Validate vxlan traffic and counters before BGP restart'):
            self.validate_traffic_and_counters(cli_objects, interfaces)

        with allure.step('Restart BGP at DUT'):
            cli_objects.dut.frr.bgp_neighbor(self.ha_vtep_ip, 'disable')
            cli_objects.dut.frr.bgp_neighbor(self.hb_vtep_ip, 'disable')
            cli_objects.dut.frr.bgp_neighbor(self.ha_vtep_ip, 'enable')
            cli_objects.dut.frr.bgp_neighbor(self.hb_vtep_ip, 'enable')
        with allure.step('Validate BGP is UP after restart'):
            verify_bgp_container_up(cli_objects)
        with allure.step(f"Validate BGP neighbor {self.hb_vlan_40_ip} established after BGP restart"):
            cli_objects.dut.frr.validate_bgp_neighbor_established(self.hb_vlan_40_ip)
        with allure.step(f"Validate BGP neighbor {self.ha_dut_1_ip} established after BGP restart"):
            cli_objects.dut.frr.validate_bgp_neighbor_established(self.ha_dut_1_ip)

        with allure.step('Validate evpn type 2 and type 3 routes after BGP restart'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)
        with allure.step('Validate vxlan traffic and counters after BGP restart'):
            self.validate_traffic_and_counters(cli_objects, interfaces)

    def test_restart_bgp_on_peer(self, cli_objects, topology_obj, interfaces):
        """
        This test will check EVPN VXLAN functionality over BGP restart.

        Test has next steps:
        1. Check that traffic pass from VLAN 101 to tunnel and back, check MAC table on DUT
        2. Restart BGP in HA
        3. Check that VXLAN tunnel established successfully after restart BGP
        4. Check that traffic pass from VLAN 101 to tunnel and back, check MAC table on DUT
        """
        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)
        with allure.step('Validate vxlan traffic and counters before BGP restart'):
            self.validate_traffic_and_counters(cli_objects, interfaces)

        with allure.step('Restart BGP at HA'):
            cli_objects.ha.frr.bgp_neighbor(self.dut_ha_1_ip, 'disable')
            cli_objects.ha.frr.bgp_neighbor(self.dut_ha_1_ip, 'enable')

        with allure.step(f"Validate BGP neighbor {self.ha_dut_1_ip} established after HA BGP restart"):
            cli_objects.dut.frr.validate_bgp_neighbor_established(self.ha_dut_1_ip)
        with allure.step('Validate evpn type 2 and type 3 routes after HA BGP restart'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)
        with allure.step('Validate vxlan traffic and counters after HA BGP restart'):
            self.validate_traffic_and_counters(cli_objects, interfaces)

    def test_cli_cmds_check(self, cli_objects, engines, topology_obj, interfaces):
        """
        This test will check configuration of all evpn vxlan commands

        Test will check below commands:
            config vxlan add <vxlan_name> <src_ipv4>
            config vxlan del <vxlan_name>
            config vxlan evpn_nvo add <nvo_name> <vxlan_name>
            config vxlan evpn_nvo del <nvo_name>
            config vxlan map add <vxlan_name> <vlan_id> <vni>
            config vxlan map_range add <vxlan_name> <vlan_start> <vlan_end> <vni_start>
            config vxlan map del <vxlan_name> <vlan_id> <vni>
            config vxlan map_range del <vxlan_name> <vlan_start> <vlan_end> <vni_start>
            config vrf add_vrf_vni_map <vrf-name> <vni>       # need to work with Type-5 route in the future
            config vrf del_vrf_vni_map <vrf-name>             # need to work with Type-5 route in the future
            config neigh-suppress vlan <vlan-id> <"on"/"off"> # Both community and nvidia did not implemented
                                                                this function
            show vxlan interface
            show vxlan vlanvnimap
            show vxlan vrfvnimap       # need to work with Type-5 route in the future
            show vxlan tunnel
            show vxlan remotevtep      # nvidia implementation do not support to show this table
            show vxlan remotemac <remote_vtep_ip/all>
            show vxlan remotevni <remote_vtep_ip/all>
            show vxlan counters
            show vxlan counters <tunnel name>
        """
        with allure.step('Validate VXLAN remote vni - using all option'):
            cli_objects.dut.vxlan.check_vxlan_remotevni(vlan_vtep_vni_check_list=[
                (VxlanConstants.VLAN_100, self.ha_vtep_ip, VxlanConstants.VNI_500100),
                (VxlanConstants.VLAN_101, self.ha_vtep_ip, VxlanConstants.VNI_500101),
                (VxlanConstants.VLAN_100, self.hb_vtep_ip, VxlanConstants.VNI_500100),
            ], all=True)
        with allure.step('Reconfigure VXLAN by VXLAN range map command'):
            cli_objects.dut.vxlan.del_vtep_mapping_range_to_vlan_vni(VxlanConstants.VTEP_NAME_DUT,
                                                                     VxlanConstants.VLAN_100, VxlanConstants.VLAN_101,
                                                                     VxlanConstants.VNI_500100)
            cli_objects.dut.vxlan.add_vtep_mapping_range_to_vlan_vni(VxlanConstants.VTEP_NAME_DUT,
                                                                     VxlanConstants.VLAN_100, VxlanConstants.VLAN_101,
                                                                     VxlanConstants.VNI_500100)
        with allure.step('Validate VXLAN interface information'):
            cli_objects.dut.vxlan.check_vxlan_interface_info(VxlanConstants.EVPN_NVO, VxlanConstants.VTEP_NAME_DUT,
                                                             self.dut_loopback_ip, VxlanConstants.VTEP_INTERFACE)
        with allure.step('Validate VXLAN tunnel'):
            self.validate_vxlan_tunnel(cli_objects)
        with allure.step('Validate VXLAN remote vni - using vtep ip option'):
            cli_objects.dut.vxlan.check_vxlan_remotevni(vlan_vtep_vni_check_list=[
                (VxlanConstants.VLAN_100, self.ha_vtep_ip, VxlanConstants.VNI_500100),
                (VxlanConstants.VLAN_101, self.ha_vtep_ip, VxlanConstants.VNI_500101),
                (VxlanConstants.VLAN_100, self.hb_vtep_ip, VxlanConstants.VNI_500100),
            ])
        with allure.step('Validate evpn type 2 and type 3 routes'):
            self.validate_basic_evpn_type_2_3_route(cli_objects)
        with allure.step('Validate VXLAN traffic and counters'):
            self.validate_traffic_and_counters(cli_objects, interfaces, vtep_mode=True)
