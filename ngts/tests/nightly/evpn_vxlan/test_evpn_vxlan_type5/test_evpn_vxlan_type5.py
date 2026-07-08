import logging
import pytest
import os
from retry import retry
from functools import partial

from ngts.config_templates.vlan_config_template import VlanConfigTemplate
from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.config_templates.vxlan_config_template import VxlanConfigTemplate
from ngts.config_templates.frr_vrf_config_template import FrrVrfConfigTemplate
from ngts.config_templates.vrf_config_template import VrfConfigTemplate
from ngts.config_templates.route_config_template import RouteConfigTemplate
from ngts.config_templates.mtu_config_template import MTUConfigTemplate
from ngts.config_templates.parallel_config_runner import parallel_config_runner
from ngts.constants.constants import VxlanConstants
from ngts.helpers.sniff_helper import send_traffic, start_sniffer, stop_sniffer
from ngts.helpers.vxlan_helper import send_and_validate_traffic, verify_ecmp_counter_entry, sonic_ports_flap, \
    restart_bgp_session, validate_ip_vrf_route, validate_ecmp_traffic, config_evpn_route_map, remove_evpn_route_map
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from scapy.layers.inet6 import IP
from scapy.layers.inet6 import IPv6
from devts.infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker

"""

EVPN VXLAN Test Cases

Documentation: https://confluence.nvidia.com/pages/viewpage.action?spaceKey=SW&title=SONiC+NGTS+EVPN+VXLAN+Documentation

"""

logger = logging.getLogger()
allure.logger = logger

DUT_VLAN_10_IFACE = 'Vlan10'
DUMMY_0 = 'dummy0'
DUMMY_1 = 'dummy1'
DUMMY_IP = '5.5.5.1'
DUMMY_IPV6 = '5000::2'
IP_MASK = '24'
IPV6_MASK = '64'
VRF_1 = 'Vrf1'
VRF_2 = 'Vrf2'
BASE_VXLAN_CONF_DICT = {
    'dut': [{'evpn_nvo': 'my-nvo', 'vtep_name': 'vtep101032', 'vtep_src_ip': '10.1.0.32',
             'vrf_vni_map': [{'vrf': VRF_1, 'vni': 500100}],
             'tunnels': [{'vni': VxlanConstants.VNI_500100, 'vlan': VxlanConstants.VLAN_100}]
             }
            ],
    'ha': [{'vtep_name': 'vxlan_500100', 'vtep_src_ip': '30.0.0.2', 'vni': VxlanConstants.VNI_500100, 'vrf': VRF_1,
            'vtep_ips': [('100.0.0.2', '24')]}]
}
FRR_CONFIG_FOLDER = os.path.dirname(os.path.abspath(__file__))
FRR_ECMP_CONFIG_DICT = {
    'dut': {
        'configuration': {'config_name': 'dut_frr_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500100', 'end'],
            ['configure terminal', 'vrf Vrf2', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'no router bgp 65000 vrf Vrf2', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    },
    'ha': {
        'configuration': {'config_name': 'ha_frr_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500100', 'end'],
            ['configure terminal', 'vrf Vrf2', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'no router bgp 65000 vrf Vrf2', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    },
    'hb': {
        'configuration': {'config_name': 'hb_frr_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500100', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    }
}

FRR_CONFIG_CHANGE_BASE_DICT = {
    'dut': {
        'configuration': {'config_name': 'dut_frr_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500100', 'end'],
            ['configure terminal', 'vrf Vrf2', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'no router bgp 65000 vrf Vrf2', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    },
    'ha': {
        'configuration': {'config_name': 'ha_frr_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500100', 'end'],
            ['configure terminal', 'vrf Vrf2', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'no router bgp 65000 vrf Vrf2', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    }
}
FRR_MULTI_VRF_DICT = {
    'dut': {
        'configuration': {'config_name': 'dut_frr_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500100', 'end'],
            ['configure terminal', 'vrf Vrf2', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'no router bgp 65000 vrf Vrf2', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    },
    'ha': {
        'configuration': {'config_name': 'ha_frr_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500100', 'end'],
            ['configure terminal', 'vrf Vrf2', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'no router bgp 65000 vrf Vrf2', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    }
}
FRR_CONFIG_CHANGE_DICT = {
    'dut': {
        'configuration': {'config_name': 'dut_frr_change_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    },
    'ha': {
        'configuration': {'config_name': 'ha_frr_change_config.conf', 'path_to_config_file': FRR_CONFIG_FOLDER},
        'cleanup': [
            ['configure terminal', 'vrf Vrf1', 'no vni 500200', 'end'],
            ['configure terminal', 'no router bgp 65000 vrf Vrf1', 'end'],
            ['configure terminal', 'no router bgp', 'end']
        ]
    }
}


@pytest.fixture(scope='function')
def base_configuration(topology_obj, engines, cli_objects, interfaces, request):
    """
    Pytest fixture used to configure basic evpn vxlan type-5 configuration
    """
    vlan_config_dict = {
        'dut': [{'vlan_id': 100, 'vlan_members': []},
                {'vlan_id': 10, 'vlan_members': []}]
    }

    vrf_config_dict = {
        'dut': [{'vrf': VRF_1, 'vrf_interfaces': ['Vlan10', "Vlan100"]}],
        'ha': [{'vrf': VRF_1, 'table': '10'}]
    }

    ip_config_dict = {
        'dut': [{'iface': 'Vlan10', 'ips': [('10.0.0.1', '24'), ('1000::1', '64')]},
                {'iface': interfaces.dut_ha_1, 'ips': [('30.0.0.1', '24')]},
                {'iface': '{}'.format(VxlanConstants.VTEP_INTERFACE), 'ips': [('10.1.0.32', '32')]}
                ],
        'ha': [{'iface': interfaces.ha_dut_1, 'ips': [('30.0.0.2', '24')]},
               {'iface': '{}.10'.format(interfaces.ha_dut_2), 'ips': [('10.0.0.2', '24'), ('1000::2', '64')]},
               ]
    }

    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict, request)
    VrfConfigTemplate.configuration(topology_obj, vrf_config_dict, request)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict, request)
    logger.info('Basic vlan and ip connectivity configuration completed')
    VxlanConfigTemplate.configuration(topology_obj, BASE_VXLAN_CONF_DICT, request)
    logger.info('Evpn vxlan configuration completed')
    enable_vxlan_counter(cli_objects, request)


def config_dummy_interfaces(topology, request=None):
    """
    Config dummy interfaces at HA and HB
    """
    if request:
        with allure.step('Add remove dummy interface into finalizer'):
            cleanup = partial(remove_dummy_interfaces, topology)
            request.addfinalizer(cleanup)

    with allure.step('Configuring dummy interfaces'):
        conf = {}
        for player_alias in ['ha', 'hb']:
            cli_object = topology.players[player_alias]['stub_cli']
            cli_object.interface.add_dummy_interface(DUMMY_0, VRF_1)
            cli_object.interface.add_dummy_interface(DUMMY_1, VRF_1)
            cli_object.ip.add_ip_to_interface(DUMMY_0, DUMMY_IP, IP_MASK)
            cli_object.ip.add_ip_to_interface(DUMMY_1, DUMMY_IPV6, IPV6_MASK)
            conf[player_alias] = cli_object.interface.engine.commands_list
            conf[player_alias] += cli_object.ip.engine.commands_list
            cli_object.interface.engine.commands_list = []
            cli_object.ip.engine.commands_list = []

        parallel_config_runner(topology, conf)


def remove_dummy_interfaces(topology):
    """
    Delete dummy interfaces at HA and HB
    """
    conf = {}
    for player_alias in ['ha', 'hb']:
        cli_object = topology.players[player_alias]['stub_cli']
        cli_object.interface.del_interface(DUMMY_0)
        cli_object.interface.del_interface(DUMMY_1)
        conf[player_alias] = cli_object.interface.engine.commands_list
        conf[player_alias] += cli_object.ip.engine.commands_list
        cli_object.interface.engine.commands_list = []
        cli_object.ip.engine.commands_list = []

    parallel_config_runner(topology, conf)


def enable_vxlan_counter(cli_objects, request=None):
    if request:
        with allure.step('Add disable vxlan counter into finalizer'):
            cleanup = partial(disable_vxlan_counter, cli_objects)
            request.addfinalizer(cleanup)

    logger.info("Enable vxlan counter")
    cli_objects.dut.vxlan.enable_vxlan_counter()


def disable_vxlan_counter(cli_objects):
    logger.info("Disable vxlan counter")
    cli_objects.dut.vxlan.disable_vxlan_counter()


@pytest.fixture(scope='function')
def overlay_ecmp_configuration(topology_obj, engines, cli_objects, interfaces, base_configuration, request):
    """
    Fixture used to config overlay ecmp scenario, it will base on the base configuration
    """
    vlan_config_dict = {
        'dut': [{'vlan_id': 10, 'vlan_members': [{interfaces.dut_ha_2: 'trunk'}]}],
        'ha': [{'vlan_id': 10, 'vlan_members': [{interfaces.ha_dut_2: None}]}]
    }

    vrf_config_dict = {
        'hb': [{'vrf': VRF_1, 'table': '10'}]
    }

    ip_config_dict = {
        'dut': [{'iface': interfaces.dut_hb_1, 'ips': [('40.0.0.1', '24')]}
                ],
        'hb': [{'iface': interfaces.hb_dut_1, 'ips': [('40.0.0.3', '24')]}]
    }

    vxlan_config_dict = {
        'hb': [{'vtep_name': 'vxlan_500100', 'vtep_src_ip': '40.0.0.3', 'vni': VxlanConstants.VNI_500100, 'vrf': VRF_1,
                'vtep_ips': [('100.0.0.2', '24')]}]
    }

    mtu_restore_list = {
        'dut': [
            {'iface': interfaces.dut_ha_1, 'origin_mtu': VxlanConstants.MTU_9100},
            {'iface': interfaces.dut_ha_2, 'origin_mtu': VxlanConstants.MTU_9100},
            {'iface': interfaces.dut_hb_1, 'origin_mtu': VxlanConstants.MTU_9100}
        ],
        'ha': [
            {'iface': interfaces.ha_dut_1, 'origin_mtu': VxlanConstants.MTU_1500},
            {'iface': interfaces.ha_dut_2, 'origin_mtu': VxlanConstants.MTU_1500},
            {'iface': VxlanConstants.VNI_500100_IFACE, 'origin_mtu': VxlanConstants.MTU_1500},
            {'iface': DUMMY_0, 'origin_mtu': VxlanConstants.MTU_1500},
            {'iface': DUMMY_1, 'origin_mtu': VxlanConstants.MTU_1500}
        ],
        'hb': [
            {'iface': interfaces.hb_dut_1, 'origin_mtu': VxlanConstants.MTU_1500},
            {'iface': VxlanConstants.VNI_500100_IFACE, 'origin_mtu': VxlanConstants.MTU_1500},
            {'iface': DUMMY_0, 'origin_mtu': VxlanConstants.MTU_1500},
            {'iface': DUMMY_1, 'origin_mtu': VxlanConstants.MTU_1500}
        ]
    }

    logger.info('Configure overlay ecmp case related configuration')
    VrfConfigTemplate.configuration(topology_obj, vrf_config_dict, request)
    config_dummy_interfaces(topology_obj, request)
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict, request)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict, request)
    VxlanConfigTemplate.configuration(topology_obj, vxlan_config_dict, request)
    MTUConfigTemplate.configuration(topology_obj, mtu_restore_list, request)
    # in case there is useless bgp configuration exist
    FrrVrfConfigTemplate.cleanup(topology_obj, FRR_ECMP_CONFIG_DICT)
    FrrVrfConfigTemplate.configuration(topology_obj, FRR_ECMP_CONFIG_DICT, request)


@pytest.fixture(scope='function')
def multi_vrfs_configuration(topology_obj, engines, cli_objects, interfaces, base_configuration, request):
    """
    Fixture used to config multi vrfs scenario, it will base on the base configuration
    """
    vlan_config_dict = {
        'dut': [{'vlan_id': 200, 'vlan_members': []},
                {'vlan_id': 10, 'vlan_members': [{interfaces.dut_hb_1: 'trunk'}]},
                {'vlan_id': 20, 'vlan_members': [{interfaces.dut_hb_2: 'trunk'}]}],
        'hb': [{'vlan_id': 10, 'vlan_members': [{interfaces.hb_dut_1: None}]},
               {'vlan_id': 20, 'vlan_members': [{interfaces.hb_dut_2: None}]}]
    }

    vrf_config_dict = {
        'dut': [{'vrf': VRF_2, 'vrf_interfaces': ['Vlan20', "Vlan200"]}],
        'ha': [{'vrf': VRF_2, 'table': '20'}]
    }

    ip_config_dict = {
        'dut': [{'iface': 'Vlan20', 'ips': [('20.0.0.1', '24')]}],
        'hb': [{'iface': '{}.10'.format(interfaces.hb_dut_1), 'ips': [('10.0.0.3', '24')]},
               {'iface': '{}.20'.format(interfaces.hb_dut_2), 'ips': [('20.0.0.3', '24')]}]
    }

    vxlan_config_dict = {
        'dut': [{'vtep_name': 'vtep101032', 'vtep_src_ip': '10.1.0.32',
                 'vrf_vni_map': [{'vrf': VRF_2, 'vni': VxlanConstants.VNI_500200}],
                 'tunnels': [{'vni': VxlanConstants.VNI_500200, 'vlan': VxlanConstants.VLAN_200}]
                 }
                ],
        'ha': [{'vtep_name': 'vxlan_500200', 'vtep_src_ip': '30.0.0.2', 'vni': VxlanConstants.VNI_500200, 'vrf': VRF_2,
                'vtep_ips': [('200.0.0.2', '24')]}]
    }

    static_route_config_dict = {
        'hb': [{'dst': '100.0.0.0', 'dst_mask': 24, 'via': ['10.0.0.1']},
               {'dst': '200.0.0.0', 'dst_mask': 24, 'via': ['20.0.0.1']}]
    }

    logger.info('Configure multi vrfs case related configuration')
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict, request)
    VrfConfigTemplate.configuration(topology_obj, vrf_config_dict, request)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict, request)
    VxlanConfigTemplate.configuration(topology_obj, vxlan_config_dict, request)
    RouteConfigTemplate.configuration(topology_obj, static_route_config_dict, request)
    FrrVrfConfigTemplate.configuration(topology_obj, FRR_MULTI_VRF_DICT, request)


@pytest.fixture(scope='function')
def vrf_config_change_configuration(topology_obj, engines, cli_objects, interfaces, base_configuration, request):
    """
    Fixture used to config multi vrfs scenario, it will base on the base configuration
    """
    vlan_config_dict = {
        'dut': [{'vlan_id': 200, 'vlan_members': []},
                {'vlan_id': 10, 'vlan_members': [{interfaces.dut_hb_1: 'trunk'}]}],
        'hb': [{'vlan_id': 10, 'vlan_members': [{interfaces.hb_dut_1: None}]}]
    }

    ip_config_dict = {
        'hb': [{'iface': '{}.10'.format(interfaces.hb_dut_1), 'ips': [('10.0.0.3', '24')]}]
    }

    static_route_config_dict = {
        'hb': [{'dst': '100.0.0.0', 'dst_mask': 24, 'via': ['10.0.0.1']},
               {'dst': '200.0.0.0', 'dst_mask': 24, 'via': ['10.0.0.1']}]
    }

    logger.info('Configure vrf config change case related configuration')
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict, request)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict, request)
    RouteConfigTemplate.configuration(topology_obj, static_route_config_dict, request)
    # in case there is useless bgp configuration exist
    FrrVrfConfigTemplate.cleanup(topology_obj, FRR_CONFIG_CHANGE_BASE_DICT)
    FrrVrfConfigTemplate.configuration(topology_obj, FRR_CONFIG_CHANGE_BASE_DICT, request)


class TestEvpnVxlan:

    @pytest.fixture(autouse=True)
    def prepare_param(self, topology_obj, engines, players, interfaces):
        self.topology_obj = topology_obj
        self.engines = engines
        self.players = players
        self.interfaces = interfaces

        self.dut_loopback_ip = '10.1.0.32'
        self.dut_ha_1_ip = '30.0.0.1'
        self.dut_vlan_10_ip = '10.0.0.1'
        self.dut_vlan_20_ip = '20.0.0.1'

        self.ha_dut_1_ip = '30.0.0.2'
        self.ha_vlan_10_ip = '10.0.0.2'
        self.ha_vlan_ipv6 = '1000::2'
        self.ha_br_500100_ip = '100.0.0.2'
        self.ha_br_500200_ip = '200.0.0.2'
        self.ha_dummy_ip = '5.5.5.1'
        self.ha_dummy_ipv6 = '5000::2'
        self.ha_vlan_10_iface = f"{interfaces.ha_dut_2}.10"

        self.hb_dut_1_ip = '40.0.0.3'
        self.hb_vlan_10_ip = '10.0.0.3'
        self.hb_vlan_20_ip = '20.0.0.3'
        self.hb_dummy_ip = '5.5.5.1'
        self.hb_dummy_ipv6 = '5000::2'
        self.hb_vlan_10_iface = f"{interfaces.hb_dut_1}.10"
        self.hb_vlan_20_iface = f"{interfaces.hb_dut_2}.20"

        self.dut_vtep_ip = self.dut_loopback_ip
        self.ha_vtep_ip = self.ha_dut_1_ip
        self.hb_vtep_ip = self.hb_dut_1_ip

        self.ecmp_interface_counter_check_list = [
            [[interfaces.dut_ha_1, interfaces.dut_hb_1], 'tx', VxlanConstants.PACKET_NUM_400],
            [interfaces.dut_ha_2, 'rx', VxlanConstants.PACKET_NUM_400],
        ]

        self.receive_interface = {
            'ha': interfaces.ha_dut_1,
            'hb': interfaces.hb_dut_1
        }

        self.ecmp_traffic_list = {
            'ip': {'sip_list': VxlanConstants.BULK_ECMP_TRAFFIC_SRC_IP_LIST, 'dip': self.ha_dummy_ip, 'd_iface': 'ha',
                   'hex_dip': VxlanConstants.HEX_5_5_5_1},
            'ipv6': {'sip_list': VxlanConstants.BULK_ECMP_TRAFFIC_SRC_IPV6_LIST, 'dip': self.ha_dummy_ipv6,
                     'd_iface': 'hb', 'hex_dip': VxlanConstants.HEX_5000_2}
        }

        self.filter_format_list = {
            'ip': {'filter_format': VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER},
            'ipv6': {'filter_format': VxlanConstants.TCPDUMP_VXLAN_DST_IPV6_FILTER}
        }

        self.ecmp_traffic_format_list = {
            'ecmp_variable_length': {
                'ip': VxlanConstants.ECMP_VARIABLE_LENGTH_PACKET,
                'ipv6': VxlanConstants.ECMP_VARIABLE_LENGTH_PACKET_V6
            },
            'ecmp_simple': {
                'ip': VxlanConstants.ECMP_SIMPLE_PACKET,
                'ipv6': VxlanConstants.ECMP_SIMPLE_PACKET_V6
            }
        }

        self.mtu_config_list = {
            'ha': [
                {'iface': interfaces.ha_dut_1, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': interfaces.ha_dut_2, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': VxlanConstants.VNI_500100_IFACE, 'mtu': VxlanConstants.MTU_9100,
                 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': self.ha_vlan_10_iface, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': DUMMY_0, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': DUMMY_1, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500}
            ],
            'hb': [
                {'iface': interfaces.hb_dut_1, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': VxlanConstants.VNI_500100_IFACE, 'mtu': VxlanConstants.MTU_9100,
                 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': DUMMY_0, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500},
                {'iface': DUMMY_1, 'mtu': VxlanConstants.MTU_9100, 'origin_mtu': VxlanConstants.MTU_1500}
            ]
        }

        self.mtu_config_dut_ha_hb_1 = {
            'dut': [
                {'iface': interfaces.dut_ha_1, 'mtu': VxlanConstants.MTU_1000, 'origin_mtu': VxlanConstants.MTU_9100},
                {'iface': interfaces.dut_hb_1, 'mtu': VxlanConstants.MTU_1000, 'origin_mtu': VxlanConstants.MTU_9100}
            ]
        }

        self.target_vxlan_config_dict = {
            'dut': [{'evpn_nvo': 'my-nvo', 'vtep_name': 'vtep101032', 'vtep_src_ip': '10.1.0.32',
                     'vrf_vni_map': [{'vrf': VRF_1, 'vni': VxlanConstants.VNI_500200}],
                     'tunnels': [{'vni': VxlanConstants.VNI_500200, 'vlan': VxlanConstants.VLAN_200}]
                     }
                    ],
            'ha': [{'vtep_name': 'vxlan_500200', 'vtep_src_ip': '30.0.0.2', 'vni': VxlanConstants.VNI_500200,
                    'vrf': VRF_1, 'vtep_ips': [('200.0.0.2', '24')]}]
        }

    def collect_mac_overlay_ecmp(self, cli_objects, interfaces):
        logger.info('Collect MAC info of interfaces for overlay ecmp test')
        ha_vlan_10_iface = '{}.10'.format(interfaces.ha_dut_2)
        self.dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(DUT_VLAN_10_IFACE)
        self.ha_br_500100_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
        self.hb_br_500100_mac = cli_objects.hb.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
        self.ha_vlan_10_mac = cli_objects.ha.mac.get_mac_address_for_interface(ha_vlan_10_iface)

    def collect_mac_multi_vrfs(self, cli_objects, interfaces):
        logger.info('Collect MAC info of interfaces for multi vrfs mapping test')
        hb_vlan_10_iface = '{}.10'.format(interfaces.hb_dut_1)
        hb_vlan_20_iface = '{}.20'.format(interfaces.hb_dut_2)
        self.dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(DUT_VLAN_10_IFACE)
        self.ha_br_500100_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
        self.ha_br_500200_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500200_IFACE)
        self.hb_vlan_10_mac = cli_objects.hb.mac.get_mac_address_for_interface(hb_vlan_10_iface)
        self.hb_vlan_20_mac = cli_objects.hb.mac.get_mac_address_for_interface(hb_vlan_20_iface)

    def collect_mac_vrf_config_change(self, cli_objects, interfaces):
        logger.info('Collect MAC info of interfaces for vrf config change test')
        hb_vlan_10_iface = '{}.10'.format(interfaces.hb_dut_1)
        self.dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(DUT_VLAN_10_IFACE)
        self.ha_br_500100_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500100_IFACE)
        self.hb_vlan_10_mac = cli_objects.hb.mac.get_mac_address_for_interface(hb_vlan_10_iface)

    def validate_overlay_ecmp_traffic_and_counters(self, cli_objects, engines, sender_count, packet_format_dict,
                                                   receiver_count=-1, packet_len=100):
        """
        Validate overlay ip and ipv6 ecmp traffic and evpn vxlan counter function
        """
        pcap_path_list = [VxlanConstants.PCAP_PATH.format('ha'), VxlanConstants.PCAP_PATH.format('hb')]
        for ip_ver in self.ecmp_traffic_list.keys():
            proto = IP if ip_ver == 'ip' else IPv6
            ip_check_list = VxlanConstants.BULK_ECMP_TRAFFIC_SRC_IP_LIST if ip_ver == 'ip' else \
                VxlanConstants.BULK_ECMP_TRAFFIC_SRC_IPV6_LIST
            with allure.step(f"Send IP Overlay ECMP traffic from HA to HA and HB via VLAN {VxlanConstants.VLAN_10} to "
                             f"L3 VNI {VxlanConstants.VNI_500100}"):
                if receiver_count == -1:
                    logger.info("Clear interface and vxlan counter")
                    cli_objects.dut.vxlan.clear_vxlan_counter()
                    cli_objects.dut.interface.clear_counters()
                packet_format = packet_format_dict[ip_ver]
                pkt_overlay_ecmp_vlan10_vni500100 = packet_format.format(self.ha_vlan_10_mac, self.dut_mac,
                                                                         self.ecmp_traffic_list[ip_ver]['sip_list'],
                                                                         self.ecmp_traffic_list[ip_ver]['dip'],
                                                                         packet_len)
                logger.info("Validate IP Overlay ECMP traffic")
                start_sniffer(engines, self.receive_interface, pcap_path_format=VxlanConstants.PCAP_PATH)
                send_traffic(self.players, VxlanConstants.HOST_HA, self.ha_vlan_10_iface,
                             pkt_overlay_ecmp_vlan10_vni500100, sender_count)
                stop_sniffer(engines, self.receive_interface, pcap_path_format=VxlanConstants.PCAP_PATH)
                logger.info(f"Validate {ip_ver} traffic")
                validate_ecmp_traffic(pcap_path_list, ip_check_list, sender_count, receiver_count, proto)

            if receiver_count == -1:
                with allure.step('Validate vxlan counters'):
                    verify_ecmp_counter_entry(cli_objects, self.ecmp_interface_counter_check_list)

    def validate_multi_vrfs_traffic(self, interfaces, sender_count, receiver_count=-1):
        """
        Validate multi vrfs traffic
        1.Traffic from HB link hb-dut-1 to HA vxlan interface pass and vice-versa
        2.Traffic from HB link hb-dut-2 to HA vxlan interface pass and vice-versa
        """
        with allure.step(f"Send traffic from HB to HA via VLAN {VxlanConstants.VLAN_10} to "
                         f"L3 VNI {VxlanConstants.VNI_500100}"):
            pkt_multi_vrfs_hb_ha = VxlanConstants.SIMPLE_PACKET.format(self.hb_vlan_10_mac, self.dut_mac,
                                                                       self.hb_vlan_10_ip, self.ha_br_500100_ip)
            logger.info("Validate multi vrfs traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_10_iface,
                                      sender_pkt_format=pkt_multi_vrfs_hb_ha,
                                      sender_count=sender_count,
                                      receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER.
                                      format(VxlanConstants.HEX_500100, VxlanConstants.HEX_100_0_0_2),
                                      receiver_count=receiver_count)

        with allure.step(f"Send traffic from HA to HB via L3 VNI {VxlanConstants.VNI_500100} to "
                         f"VLAN {VxlanConstants.VLAN_10}"):
            pkt_multi_vrfs_ha_hb = VxlanConstants.SIMPLE_PACKET.format(self.ha_br_500100_mac, self.dut_mac,
                                                                       self.ha_br_500100_ip, self.hb_vlan_10_ip)
            logger.info("Validate multi vrfs traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HA,
                                      sender_intf=VxlanConstants.VNI_500100_IFACE,
                                      sender_pkt_format=pkt_multi_vrfs_ha_hb,
                                      sender_count=sender_count,
                                      receiver=VxlanConstants.HOST_HB,
                                      receiver_intf=self.hb_vlan_10_iface,
                                      receiver_filter_format=VxlanConstants.SIMPLE_PACKET_FILTER.
                                      format(self.hb_vlan_10_ip),
                                      receiver_count=receiver_count)

        with allure.step(f"Send traffic from HB to HA via VLAN {VxlanConstants.VLAN_20} to "
                         f"L3 VNI {VxlanConstants.VNI_500200}"):
            pkt_multi_vrfs_hb_ha = VxlanConstants.SIMPLE_PACKET.format(self.hb_vlan_20_mac, self.dut_mac,
                                                                       self.hb_vlan_20_ip, self.ha_br_500200_ip)
            logger.info("Validate multi vrfs traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_20_iface,
                                      sender_pkt_format=pkt_multi_vrfs_hb_ha,
                                      sender_count=sender_count,
                                      receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER.
                                      format(VxlanConstants.HEX_500200, VxlanConstants.HEX_200_0_0_2),
                                      receiver_count=receiver_count)

        with allure.step(f"Send traffic from HA to HB via L3 VNI {VxlanConstants.VNI_500200} to "
                         f"VLAN {VxlanConstants.VLAN_20}"):
            pkt_multi_vrfs_ha_hb = VxlanConstants.SIMPLE_PACKET.format(self.ha_br_500200_mac, self.dut_mac,
                                                                       self.ha_br_500200_ip, self.hb_vlan_20_ip)
            logger.info("Validate multi vrfs traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HA,
                                      sender_intf=VxlanConstants.VNI_500200_IFACE,
                                      sender_pkt_format=pkt_multi_vrfs_ha_hb,
                                      sender_count=sender_count,
                                      receiver=VxlanConstants.HOST_HB,
                                      receiver_intf=self.hb_vlan_20_iface,
                                      receiver_filter_format=VxlanConstants.SIMPLE_PACKET_FILTER.
                                      format(self.hb_vlan_20_ip),
                                      receiver_count=receiver_count)

    def validate_vrf_config_change_traffic(self, interfaces, sender_count, bridge_name, bridge_ip, bridge_mac, l3_vni):
        """
        Validate vrf config change traffic
        """
        with allure.step(f"Send traffic from HB to HA via VLAN {VxlanConstants.VLAN_10} to L3 VNI {l3_vni}"):
            pkt_multi_vrfs_hb_ha = VxlanConstants.SIMPLE_PACKET.format(self.hb_vlan_10_mac, self.dut_mac,
                                                                       self.hb_vlan_10_ip, bridge_ip)
            logger.info("Validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HB,
                                      sender_intf=self.hb_vlan_10_iface,
                                      sender_pkt_format=pkt_multi_vrfs_hb_ha,
                                      sender_count=sender_count,
                                      receiver=VxlanConstants.HOST_HA,
                                      receiver_intf=interfaces.ha_dut_1,
                                      receiver_filter_format=VxlanConstants.TCPDUMP_VXLAN_DST_IP_FILTER.
                                      format(VxlanConstants.VNI_HEX_MAP[l3_vni], VxlanConstants.IP_HEX_MAP[bridge_ip]))

        with allure.step(f"Send traffic from HA to HB via L3 VNI {l3_vni} to VLAN {VxlanConstants.VLAN_10}"):
            pkt_multi_vrfs_ha_hb = VxlanConstants.SIMPLE_PACKET.format(bridge_mac, self.dut_mac,
                                                                       bridge_ip, self.hb_vlan_10_ip)
            logger.info("Validate traffic")
            send_and_validate_traffic(player=self.players, sender=VxlanConstants.HOST_HA,
                                      sender_intf=bridge_name,
                                      sender_pkt_format=pkt_multi_vrfs_ha_hb,
                                      sender_count=sender_count,
                                      receiver=VxlanConstants.HOST_HB,
                                      receiver_intf=self.hb_vlan_10_iface,
                                      receiver_filter_format=VxlanConstants.SIMPLE_PACKET_FILTER.
                                      format(self.hb_vlan_10_ip))

    @retry(Exception, tries=5, delay=2)
    def validate_ecmp_evpn_type5_route(self, cli_objects):
        """
        This method is used to verify evpn type 5 route state in overlay ecmp scenario
        :param cli_objects: cli_objects fixture
        """
        with allure.step('Validate CLI type-5 routes on DUT'):
            dut_type_5_check_list = [
                (DUMMY_IP, IP_MASK, self.ha_vtep_ip, VxlanConstants.RD_100),
                (DUMMY_IPV6, IPV6_MASK, self.ha_vtep_ip, VxlanConstants.RD_100),
                (DUMMY_IP, IP_MASK, self.hb_vtep_ip, VxlanConstants.RD_100),
                (DUMMY_IPV6, IPV6_MASK, self.hb_vtep_ip, VxlanConstants.RD_100)
            ]
            dut_type_5_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_prefix()
            for ip_addr, mask, vtep_ip, rd in dut_type_5_check_list:
                cli_objects.dut.frr.validate_type_5_route(dut_type_5_info, ip_addr, mask, vtep_ip, rd)

        with allure.step('Validate CLI type-5 routes on HA'):
            ha_type_5_check_list = [
                (DUMMY_IP, IP_MASK, self.ha_vtep_ip, VxlanConstants.RD_100),
                (DUMMY_IPV6, IPV6_MASK, self.ha_vtep_ip, VxlanConstants.RD_100)
            ]
            ha_type_5_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_prefix()
            for ip_addr, mask, vtep_ip, rd in ha_type_5_check_list:
                cli_objects.ha.frr.validate_type_5_route(ha_type_5_info, ip_addr, mask, vtep_ip, rd)

        with allure.step('Validate CLI type-5 routes on HB'):
            hb_type_5_check_list = [
                (DUMMY_IP, IP_MASK, self.hb_vtep_ip, VxlanConstants.RD_100),
                (DUMMY_IPV6, IPV6_MASK, self.hb_vtep_ip, VxlanConstants.RD_100)
            ]
            hb_type_5_info = cli_objects.hb.frr.get_l2vpn_evpn_route_type_prefix()
            for ip_addr, mask, vtep_ip, rd in hb_type_5_check_list:
                cli_objects.hb.frr.validate_type_5_route(hb_type_5_info, ip_addr, mask, vtep_ip, rd)

    @retry(Exception, tries=5, delay=2)
    def validate_multi_vrfs_evpn_type5_route(self, cli_objects, learned=True):
        """
        This method is used to verify evpn type 5 route state in multi vrfs scenario
        :param cli_objects: cli_objects fixture
        """
        with allure.step('Validate CLI type-5 routes on DUT'):
            dut_type_5_check_list = [
                (self.ha_br_500100_ip, IP_MASK, self.ha_vtep_ip, VxlanConstants.RD_100),
                (self.ha_br_500200_ip, IP_MASK, self.ha_vtep_ip, VxlanConstants.RD_200)
            ]
            dut_type_5_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_prefix()
            for ip_addr, mask, vtep_ip, rd in dut_type_5_check_list:
                cli_objects.dut.frr.validate_type_5_route(dut_type_5_info, ip_addr, mask, vtep_ip, rd)

        with allure.step('Validate CLI type-5 routes on HA'):
            ha_type_5_check_list = [
                (self.dut_vlan_10_ip, IP_MASK, self.dut_vtep_ip, VxlanConstants.RD_100),
                (self.dut_vlan_20_ip, IP_MASK, self.dut_vtep_ip, VxlanConstants.RD_200)
            ]
            ha_type_5_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_prefix()
            for ip_addr, mask, vtep_ip, rd in ha_type_5_check_list:
                cli_objects.ha.frr.validate_type_5_route(ha_type_5_info, ip_addr, mask, vtep_ip, rd, learned)

    @retry(Exception, tries=5, delay=2)
    def validate_vrf_config_evpn_type5_route(self, cli_objects, bridge_ip, rd_num):
        """
        This method is used to verify evpn type 5 route state in vrf config change scenario
        :param cli_objects: cli_objects fixture
        """
        with allure.step('Validate CLI type-5 routes on DUT'):
            dut_type_5_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_prefix()
            cli_objects.dut.frr.validate_type_5_route(dut_type_5_info, bridge_ip, IP_MASK, self.ha_vtep_ip, rd_num)

        with allure.step('Validate CLI type-5 routes on HA'):
            ha_type_5_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_prefix()
            cli_objects.ha.frr.validate_type_5_route(ha_type_5_info, self.dut_vlan_10_ip, IP_MASK, self.dut_vtep_ip,
                                                     rd_num)

    def vxlan_config_change(self, topology_obj, request):
        """
        This method is used to change L3 VNI configuration in case: test_vni_to_vrf_config_change
        """
        logger.info('Clean FRR configuration')
        FrrVrfConfigTemplate.cleanup(topology_obj, FRR_CONFIG_CHANGE_BASE_DICT)
        logger.info('Change VXLAN configuration')
        VxlanConfigTemplate.cleanup(topology_obj, BASE_VXLAN_CONF_DICT)
        VxlanConfigTemplate.configuration(topology_obj, self.target_vxlan_config_dict, request)
        logger.info('Config new FRR configuration')
        FrrVrfConfigTemplate.configuration(topology_obj, FRR_CONFIG_CHANGE_DICT, request)

    def test_overlay_ecmp(self, topology_obj, cli_objects, engines, interfaces, overlay_ecmp_configuration):
        """
        This test will check EVPN Type 5 overlay ecmp functionality.

        Test has next steps:
        1. L3 evpn type 5 info correct at HA, DUT, HB
        2. Send routing packets from HA to DUT via vlan 10
        3. Check that IP and IPv6 traffic balanced 50/50 via 2 VTEPs(30.0.0.2, 40.0.0.3)
        4. Check vxlan tunnel counter works fine for L3 VNI
        5. Modify path MTU to 9100
        6. Check that both IP and IPv6 jumbo packets could be forwarded in vxlan tunnel
        7. Modify path MTU to a value smaller than 1500
        8. Check that both IP and IPv6 packets which length larger than the MTU could not be forwarded
           through vxlan tunnel
        """
        with allure.step('Check CLI VLAN to VNI mapping'):
            self.collect_mac_overlay_ecmp(cli_objects, interfaces)
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100)])

        with allure.step('Validate evpn type 5 routes'):
            self.validate_ecmp_evpn_type5_route(cli_objects)

        with allure.step('Validate IP and IPv6 Overlay ECMP traffic and counters'):
            self.validate_overlay_ecmp_traffic_and_counters(cli_objects, engines, VxlanConstants.PACKET_NUM_10,
                                                            self.ecmp_traffic_format_list['ecmp_simple'])

        with allure.step(f'Config MTU to {VxlanConstants.MTU_9100} for all the ports through path'):
            MTUConfigTemplate.configuration(topology_obj, self.mtu_config_list)
        with allure.step('Validate Jumbo IP and IPv6 Overlay ECMP traffic and counters'):
            self.validate_overlay_ecmp_traffic_and_counters(cli_objects, engines, VxlanConstants.PACKET_NUM_10,
                                                            self.ecmp_traffic_format_list['ecmp_variable_length'],
                                                            packet_len=VxlanConstants.JUMBO_PACKET_LEN)

        with allure.step(f'Config MTU of {interfaces.dut_ha_1}, {interfaces.dut_hb_1} to {VxlanConstants.MTU_1000}'):
            MTUConfigTemplate.configuration(topology_obj, self.mtu_config_dut_ha_hb_1)

        with allure.step(f'Validate IP and IPv6 Overlay ECMP traffic with length {VxlanConstants.MTU_1000} could not '
                         f'be forwarded through'):
            self.validate_overlay_ecmp_traffic_and_counters(cli_objects, engines, VxlanConstants.PACKET_NUM_10,
                                                            self.ecmp_traffic_format_list['ecmp_variable_length'],
                                                            packet_len=VxlanConstants.NORMAL_PACKET_LEN,
                                                            receiver_count=VxlanConstants.PACKET_NUM_0)

    def test_multi_vrfs_mapping(self, topology_obj, cli_objects, interfaces, multi_vrfs_configuration):
        """
        This test will check EVPN Type 5 multi-vrf functionality.

        Test has next steps:
        1.L3 evpn type 5 info correct at HA, DUT, HB
        2.Configure route map to block type 5 routes
        3.Do route map deny action validations
        4.Remove route map
        5.Do type 5 routes validations
        6.Send traffic from HB link hb-dut-1 to HA VXLAN interface and vice-versa. Check that traffic pass
        7.Send traffic from HB link hb-dut-2 to HA VXLAN interface and vice-versa. Check that traffic pass
        """
        try:
            with allure.step('Check CLI VLAN to VNI mapping'):
                self.collect_mac_multi_vrfs(cli_objects, interfaces)
                cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                    vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100),
                                       (VxlanConstants.VLAN_200, VxlanConstants.VNI_500200)])

            with allure.step('Configure route map to block type 5 routes'):
                config_evpn_route_map(cli_objects, VxlanConstants.EVPN_ROUTE_MAP, VxlanConstants.BGP_SESSION_ID,
                                      [
                                          (VxlanConstants.DENY, '1', '5'),
                                          (VxlanConstants.PERMIT, '2', '')
                                      ],
                                      [
                                          self.ha_vtep_ip,
                                          self.hb_vtep_ip
                                      ])

            with allure.step('Validate evpn type 5 routes are blocked'):
                self.validate_multi_vrfs_evpn_type5_route(cli_objects, learned=False)

            with allure.step('Remove route map'):
                remove_evpn_route_map(cli_objects, VxlanConstants.EVPN_ROUTE_MAP, VxlanConstants.BGP_SESSION_ID,
                                      [
                                          self.ha_vtep_ip,
                                          self.hb_vtep_ip
                                      ])

            with allure.step('Validate evpn type 5 routes'):
                self.validate_multi_vrfs_evpn_type5_route(cli_objects)

            with allure.step(f'Validate vrf route installed of {VRF_1}'):
                validate_ip_vrf_route(cli_objects.dut, VxlanConstants.BR_500100_IP, IP_MASK, VRF_1)
                validate_ip_vrf_route(cli_objects.dut, self.hb_vlan_10_ip, IP_MASK, VRF_1)

            with allure.step(f'Validate vrf route installed of {VRF_2}'):
                validate_ip_vrf_route(cli_objects.dut, VxlanConstants.BR_500200_IP, IP_MASK, VRF_2)
                validate_ip_vrf_route(cli_objects.dut, self.hb_vlan_20_ip, IP_MASK, VRF_2)

            with allure.step('Validate multi vrfs traffic'):
                self.validate_multi_vrfs_traffic(interfaces, VxlanConstants.PACKET_NUM_100)
        except Exception as err:
            with allure.step('Remove route map'):
                remove_evpn_route_map(cli_objects, VxlanConstants.EVPN_ROUTE_MAP, VxlanConstants.BGP_SESSION_ID,
                                      [
                                          self.ha_vtep_ip,
                                          self.hb_vtep_ip
                                      ])
            raise err

    def test_vni_to_vrf_config_change(self, topology_obj, cli_objects, interfaces, vrf_config_change_configuration,
                                      request):
        """
        This test will check EVPN Type 5 multi-vrf functionality.

        Test has next steps:
        1.Check CLI VLAN to VNI mapping
        2.Check evpn type 5 info correct at HA, DUT
        3.Validate vrf route installed of default config
        4.ping packets from HB to HA via L3 VNI
        5.Send traffic from HB link hb-dut-1 to HA VXLAN interfaces and vice-versa. Check that traffic pass
        6.Change vrf to vni mapping relation from Vrf1-500100 to Vrf1-500200
            a.Add Vlan200 at DUT
            b.Config vlan to vni mapping: 200:500200
            c.Config vrf to vni mapping at HA and DUT: Vrf1:500200
            d.Update FRR config at HA and DUT
            e.Validate evpn type 5 routes of new config
            f.Validate vrf route installed of new config
            g.Validate traffic of new config
        7.Interface shutdown/ no shutdown
        8.Validate evpn type 5 routes after port flap
        9.Validate vrf route installed after port flap
        10.Validate traffic of new config after port flap
        11.BGP session restart
        12.Validate BGP neighbor established after BGP restart
        13.Validate evpn type 5 routes after bgp restart
        14.Validate vrf route installed after bgp restart
        15.Validate traffic of new config after bgp restart
        """
        with allure.step('Check CLI VLAN to VNI mapping'):
            self.collect_mac_vrf_config_change(cli_objects, interfaces)
            cli_objects.dut.vxlan.check_vxlan_vlanvnimap(
                vlan_vni_map_list=[(VxlanConstants.VLAN_100, VxlanConstants.VNI_500100)])

        with allure.step('Validate evpn type 5 routes of default config'):
            self.validate_vrf_config_evpn_type5_route(cli_objects, self.ha_br_500100_ip, VxlanConstants.RD_100)

        with allure.step('Validate vrf route installed of default config'):
            validate_ip_vrf_route(cli_objects.dut, VxlanConstants.BR_500100_IP, IP_MASK, VRF_1)

        with allure.step(f'Send ping packets from HB to HA via L3 VNI {VxlanConstants.VNI_500100}'):
            ping_hb_ha_l3_vni = {'sender': VxlanConstants.HOST_HB,
                                 'args': {'interface': self.hb_vlan_10_iface, 'count': VxlanConstants.PACKET_NUM_3,
                                          'dst': self.ha_br_500100_ip}}
            PingChecker(self.players, ping_hb_ha_l3_vni).run_validation()

        with allure.step('Validate traffic of default config'):
            self.validate_vrf_config_change_traffic(interfaces, VxlanConstants.PACKET_NUM_100,
                                                    VxlanConstants.VNI_500100_IFACE, self.ha_br_500100_ip,
                                                    self.ha_br_500100_mac, VxlanConstants.VNI_500100)

        with allure.step('Change EVPN configuration'):
            self.vxlan_config_change(topology_obj, request)

        with allure.step('Validate evpn type 5 routes of new config'):
            self.validate_vrf_config_evpn_type5_route(cli_objects, self.ha_br_500200_ip, VxlanConstants.RD_200)

        with allure.step('Validate vrf route installed of new config'):
            validate_ip_vrf_route(cli_objects.dut, VxlanConstants.BR_500200_IP, IP_MASK, VRF_1)

        with allure.step('Validate traffic of new config'):
            self.ha_br_500200_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500200_IFACE)
            self.validate_vrf_config_change_traffic(interfaces, VxlanConstants.PACKET_NUM_100,
                                                    VxlanConstants.VNI_500200_IFACE, self.ha_br_500200_ip,
                                                    self.ha_br_500200_mac, VxlanConstants.VNI_500200)

        with allure.step(f'Do port flap at {interfaces.dut_ha_1} and {interfaces.dut_hb_1}'):
            sonic_ports_flap(cli_objects.dut, [interfaces.dut_ha_1, interfaces.dut_hb_1])

        with allure.step('Validate evpn type 5 routes after port flap'):
            self.validate_vrf_config_evpn_type5_route(cli_objects, self.ha_br_500200_ip, VxlanConstants.RD_200)

        with allure.step('Validate vrf route installed after port flap'):
            validate_ip_vrf_route(cli_objects.dut, VxlanConstants.BR_500200_IP, IP_MASK, VRF_1)

        with allure.step('Validate traffic of new config after port flap'):
            self.ha_br_500200_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500200_IFACE)
            self.validate_vrf_config_change_traffic(interfaces, VxlanConstants.PACKET_NUM_100,
                                                    VxlanConstants.VNI_500200_IFACE, self.ha_br_500200_ip,
                                                    self.ha_br_500200_mac, VxlanConstants.VNI_500200)

        with allure.step('Do BGP restart'):
            restart_bgp_session(cli_objects.dut)

        with allure.step(f'Validate BGP neighbor {self.ha_vtep_ip} established after BGP restart'):
            cli_objects.dut.frr.validate_bgp_neighbor_established(self.ha_vtep_ip)

        with allure.step('Validate evpn type 5 routes after bgp restart'):
            self.validate_vrf_config_evpn_type5_route(cli_objects, self.ha_br_500200_ip, VxlanConstants.RD_200)

        with allure.step('Validate vrf route installed after bgp restart'):
            validate_ip_vrf_route(cli_objects.dut, VxlanConstants.BR_500200_IP, IP_MASK, VRF_1)

        with allure.step('Validate traffic of new config after bgp restart'):
            self.ha_br_500200_mac = cli_objects.ha.mac.get_mac_address_for_interface(VxlanConstants.VNI_500200_IFACE)
            self.validate_vrf_config_change_traffic(interfaces, VxlanConstants.PACKET_NUM_100,
                                                    VxlanConstants.VNI_500200_IFACE, self.ha_br_500200_ip,
                                                    self.ha_br_500200_mac, VxlanConstants.VNI_500200)
