import pytest
import allure
import re
import random
from ngts.cli_wrappers.sonic.sonic_interface_clis import SonicInterfaceCli
from ngts.cli_wrappers.sonic.sonic_lldp_clis import SonicLldpCli
from ngts.config_templates.lag_lacp_config_template import LagLacpConfigTemplate
from ngts.config_templates.vlan_config_template import VlanConfigTemplate
from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.config_templates.interfaces_config_template import InterfaceConfigTemplate
from ngts.config_templates.route_config_template import RouteConfigTemplate
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from ngts.constants.constants import SonicConst
from retry.api import retry_call
import logging

logger = logging.getLogger()

DUT_HA_1_IP = "20.0.0.1"
DUT_HA_2_IP = "30.0.0.1"
DUT_HB_1_IP = "40.0.0.1"
DUT_HB_2_IP = "50.0.0.1"

HA_DUT_1_IP = "20.0.0.10"
HA_DUT_2_IP = "30.0.0.10"
HB_DUT_1_IP = "40.0.0.10"
HB_DUT_2_IP = "50.0.0.10"

# TODO: Need to check with the feature owner when the feature will be supported


@pytest.fixture(scope='package', autouse=False)
def orig_ifaces(cli_objects):
    """
    Fixture which used to get the original interfaces status before
    :param cli_objects: cli_objects fixture object
    :return: interfaces status in dictionary format
    """
    yield cli_objects.dut.interface.parse_interfaces_status()


@pytest.fixture(scope='package', autouse=False)
def dynamic_port_counter_configuration(cli_objects, interfaces, topology_obj):
    """
    Fixture which are doing configuration after add ports back in test case
    :param cli_objects: cli_objects fixture object
    :param interfaces: interfaces fixture object
    :param topology_obj: topology_obj fixture object
    """
    dut_original_interfaces_speeds = cli_objects.dut.interface.get_interfaces_speed([interfaces.dut_hb_2])
    interfaces_config_dict = {
        'dut': [{'iface': interfaces.dut_ha_2, 'speed': '10G',
                 'original_speed': dut_original_interfaces_speeds.get(interfaces.dut_ha_2, '10G')},
                {'iface': interfaces.dut_hb_2, 'speed': '10G',
                 'original_speed': dut_original_interfaces_speeds.get(interfaces.dut_hb_2, '10G')}
                ]
    }
    # LAG/LACP config which will be used in test
    lag_lacp_config_dict = {
        'dut': [{'type': 'lacp', 'name': 'PortChannel0001', 'members': [interfaces.dut_ha_2]},
                {'type': 'lacp', 'name': 'PortChannel0002', 'members': [interfaces.dut_hb_2]}],
        'hb': [{'type': 'lacp', 'name': 'bond0', 'members': [interfaces.hb_dut_2]}],
        'ha': [{'type': 'lacp', 'name': 'bond0', 'members': [interfaces.ha_dut_2]}]
    }

    # VLAN config which will be used in test
    vlan_config_dict = {
        'dut': [{'vlan_id': 20, 'vlan_members': [{interfaces.dut_ha_1: 'trunk'}]},
                {'vlan_id': 40, 'vlan_members': [{interfaces.dut_hb_1: 'trunk'}]}
                ],
        'ha': [{'vlan_id': 20, 'vlan_members': [{interfaces.ha_dut_1: None}]},
               ],
        'hb': [{'vlan_id': 40, 'vlan_members': [{interfaces.hb_dut_1: None}]},
               ]
    }

    # IP config which will be used in test
    ip_config_dict = {
        'dut': [{'iface': 'Vlan20', 'ips': [(DUT_HA_1_IP, '24')]},
                {'iface': 'Vlan40', 'ips': [(DUT_HB_1_IP, '24')]},
                {'iface': 'PortChannel0001', 'ips': [(DUT_HA_2_IP, '24')]},
                {'iface': 'PortChannel0002', 'ips': [(DUT_HB_2_IP, '24')]}
                ],
        'ha': [{'iface': "{}.20".format(interfaces.ha_dut_1), 'ips': [(HA_DUT_1_IP, '24')]},
               {'iface': 'bond0', 'ips': [(HA_DUT_2_IP, '24')]}],
        'hb': [{'iface': "{}.40".format(interfaces.hb_dut_1), 'ips': [(HB_DUT_1_IP, '24')]},
               {'iface': 'bond0', 'ips': [(HB_DUT_2_IP, '24')]}]
    }
    static_route_config_dict = {
        'ha': [{'dst': '40.0.0.0', 'dst_mask': 24, 'via': [DUT_HA_1_IP]},
               {'dst': '50.0.0.0', 'dst_mask': 24, 'via': [DUT_HA_2_IP]}],
        'hb': [{'dst': '20.0.0.0', 'dst_mask': 24, 'via': [DUT_HB_1_IP]},
               {'dst': '30.0.0.0', 'dst_mask': 24, 'via': [DUT_HB_2_IP]}]
    }

    InterfaceConfigTemplate.configuration(topology_obj, interfaces_config_dict)
    LagLacpConfigTemplate.configuration(topology_obj, lag_lacp_config_dict)
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    RouteConfigTemplate.configuration(topology_obj, static_route_config_dict)

    yield

    RouteConfigTemplate.cleanup(topology_obj, static_route_config_dict)
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    VlanConfigTemplate.cleanup(topology_obj, vlan_config_dict)
    LagLacpConfigTemplate.cleanup(topology_obj, lag_lacp_config_dict)
    InterfaceConfigTemplate.cleanup(topology_obj, interfaces_config_dict)


PORT_NUM_LIST = [1]


@pytest.mark.parametrize("ports_num", PORT_NUM_LIST)
def test_dynamic_port_counters(request, cli_objects, topology_obj, engines, ports_num, interfaces, players, ha_dut_1_mac, orig_ifaces):
    """
    Test dynamically adding ports or deleting ports
    :param request: pytest request fixture object
    :param engines: engines fixture object
    :param topology_obj: topology_obj fixture object
    :param interfaces: interfaces fixture object
    :param players: players fixture object
    :param ha_dut_1_mac: ha_dut_1_mac fixture object
    :param orig_ifaces: orig_ifaces fixture object
    :param ports_num: how many ports will be dynamically deleted and add back.,
                      1 stand for all the available ports will be used, 1/2 stand for half of the available ports
                      will be used
    """
    dut_engine = engines.dut
    try:

        with allure.step("Get tested ports with their status"):
            sampling_interfaces = get_random_tested_ifaces(orig_ifaces, ports_num)
            expected_ifaces_after_delete = get_expected_ifaces(orig_ifaces, sampling_interfaces)
            add_ports_cmd, del_ports_cmd = get_add_del_cmds(orig_ifaces, sampling_interfaces)

        with allure.step("Get lldp table before delete ports"):
            ori_lldp_table = cli_objects.dut.lldp.parse_lldp_table_info()

        with allure.step("Delete ports"):
            dut_engine.run_cmd(del_ports_cmd)
        with allure.step("Verify the ports are deleted"):
            retry_call(verify_ifaces_status, fargs=[cli_objects.dut, expected_ifaces_after_delete],
                       tries=5, delay=10, logger=logger)
        with allure.step("Add all deleted port back"):
            dut_engine.run_cmd(add_ports_cmd)

        with allure.step("Verify ports are added, and the status are correct"):
            retry_call(verify_ifaces_status, fargs=[cli_objects.dut, orig_ifaces],
                       tries=10, delay=10, logger=logger)
        with allure.step("Verify the lldp table is as expected after the ports are added"):
            retry_call(verify_lldp_table, fargs=[cli_objects.dut, ori_lldp_table],
                       tries=3, delay=40, logger=logger)

        with allure.step("Verify traffic can be send receive correctly"):
            request.getfixturevalue("dynamic_port_counter_configuration")
            with allure.step("Send and verify traffic"):
                verify_traffic(interfaces, players, ha_dut_1_mac)
    except Exception as e:
        with allure.step("Reload config after failure"):
            cli_objects.dut.general.reboot_reload_flow(r_type=SonicConst.CONFIG_RELOAD_CMD, topology_obj=topology_obj)
        pytest.fail("test_dynamic_port_counters failed due to".format(e))


def verify_ifaces_status(cli_obj, expected_interfaces):
    """
    Verify that the interface status is as expected.
    :param cli_obj: the dut cli_obj
    :param expected_interfaces: the expected interfaces
    :return: None, raise exception on unexpected results
    """
    if len(expected_interfaces) > 0:
        interfaces = cli_obj.interface.parse_interfaces_status()
    else:
        interfaces = cli_obj.interface.parse_interfaces_status(headers_ofset=2, len_ofset=3,
                                                               data_ofset_from_start=4)
    for iface in expected_interfaces:
        assert interfaces[iface] == expected_interfaces[iface], \
            "the status of the interface {} not as expected {}".format(interfaces[iface], expected_interfaces[iface])


def verify_lldp_table(cli_obj, expected_lldp_table):
    """
    Verify that the lldp table is as expected
    :param cli_obj: dut cli_obj
    :param expected_lldp_table: expected_lldp_table
    :return: None, raise exception on unexpected results
    """
    lldp_table = cli_obj.lldp.parse_lldp_table_info()
    for iface in expected_lldp_table:
        assert lldp_table[iface] == expected_lldp_table[iface], \
            "the lldp neighbor {} is not same as expected {}".format(lldp_table[iface], expected_lldp_table[iface])


def get_random_tested_ifaces(orig_ifaces, ports_num):
    """
    randomly select interfaces which will be used to do test(delete port, add port)
    :param orig_ifaces: orig_ifaces fixture result
    :param ports_num: the port number which will be used to do test.
    :return: list of interfaces used to do test
    """
    return random.sample(orig_ifaces.keys(), int(len(orig_ifaces) * ports_num))


def get_expected_ifaces(orig_ifaces, sampling_interfaces):
    """
    get expected interfaces after deleted
    :param orig_ifaces: orig_ifaces fixture result
    :param sampling_interfaces: the interfaces selected
    :return: list of interfaces status
    """
    ret = {}
    for iface in orig_ifaces:
        if iface not in sampling_interfaces:
            ret[iface] = orig_ifaces[iface]
    return ret


def get_add_del_cmds(orig_ifaces, sampling_interfaces):
    """
    get add and delete cmds
    :param orig_ifaces: orig_ifaces fixture result
    :param sampling_interfaces: the interfaces selected
    :return: get ports cmd and delete ports cmd.
    """
    add_cmd_pattern = 'redis-cli -n 4 hset "PORT|{}" admin_status {} alias {} index {}  lanes {} speed {}'
    del_cmd_pattern = 'redis-cli -n 4 del "PORT|{}"'
    add_cmd_list = []
    del_cmd_list = []
    for intf_name in sampling_interfaces:
        intf = orig_ifaces[intf_name]
        admin_status = intf['Admin']
        lanes = intf['Lanes']
        speed = intf['Speed'].strip('G') + '000'
        alias = intf['Alias']
        regex_pattern = r"etp(\d+)\w*"
        index = re.findall(regex_pattern, alias, re.IGNORECASE)[0]
        add_cmd = add_cmd_pattern.format(intf_name, admin_status, alias, index, lanes, speed)
        add_cmd_list.append(add_cmd)
        del_cmd = del_cmd_pattern.format(intf_name)
        del_cmd_list.append(del_cmd)
    add_ports_cmd = " && ".join(add_cmd_list)
    del_ports_cmd = " && ".join(del_cmd_list)
    return add_ports_cmd, del_ports_cmd


def verify_traffic(interfaces, players, ha_dut_1_mac):
    """
    Send traffic and verify the traffic can be received correctly.
    :param interfaces: interface fixture results
    :param players: players fixture results
    :param ha_dut_1_mac: ha_dut_1 interface mac address
    :return: None, raise an exception on failure
    """
    pkt_ha_hb_vlan = 'Ether(src="{}")/IP(src="{}", dst="{}")'.format(ha_dut_1_mac, HA_DUT_1_IP, HB_DUT_1_IP)
    pkt_filter = 'src {} and dst {}'.format(HA_DUT_1_IP, HB_DUT_1_IP)
    validation = {'sender': 'ha', 'send_args': {'interface': "{}.20".format(interfaces.ha_dut_1),
                                                'packets': pkt_ha_hb_vlan,
                                                'count': 3},
                  'receivers':
                      [
                          {'receiver': 'hb', 'receive_args': {'interface': interfaces.hb_dut_1,
                                                              'filter': pkt_filter}}
    ]
    }
    logger.info('Sending 3 packets from ha vlan 20  to hb vlan 40')
    ScapyChecker(players, validation).run_validation()

    pkt_hb_ha_lag = 'Ether()/IP(src="{}", dst="{}")'.format(HB_DUT_2_IP, HA_DUT_2_IP)
    pkt_filter = 'src {} and dst {}'.format(HB_DUT_2_IP, HA_DUT_2_IP)
    validation = {'sender': 'hb', 'send_args': {'interface': 'bond0',
                                                'packets': pkt_hb_ha_lag,
                                                'count': 3},
                  'receivers':
                      [
                          {'receiver': 'ha', 'receive_args': {'interface': interfaces.ha_dut_2,
                                                              'filter': pkt_filter}}
    ]
    }
    logger.info('Sending 3 packets from hb bound0  to ha bound0')
    ScapyChecker(players, validation).run_validation()
