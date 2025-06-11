import allure
import logging
import pytest
import random
from retry.api import retry_call

from ngts.config_templates.vlan_config_template import VlanConfigTemplate
from ngts.cli_wrappers.sonic.sonic_interface_clis import SonicInterfaceCli
from ngts.config_templates.lag_lacp_config_template import LagLacpConfigTemplate
from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.cli_wrappers.linux.linux_interface_clis import LinuxInterfaceCli


logger = logging.getLogger()

TRAFFIC_TYPES = ['TCP', 'UDP']


@pytest.fixture()
def traffic_type():
    return random.choice(TRAFFIC_TYPES)


@pytest.fixture(scope='package', autouse=True)
def lag_lacp_base_configuration(topology_obj, interfaces, engines):
    """
    Pytest fixture which are doing configuration fot test case based on push gate config
    :param topology_obj: topology object fixture
    :param interfaces: interfaces fixture
    :param engines: engines fixture
    """
    dut_cli = topology_obj.players['dut']['cli']
    cli_obj = topology_obj.players['dut']['cli']

    ports_list = [interfaces.dut_ha_1, interfaces.dut_ha_2, interfaces.dut_hb_1, interfaces.dut_ha_2]
    with allure.step('Check that links are in UP state'.format(ports_list)):
        retry_call(cli_obj.interface.check_ports_status, fargs=[ports_list], tries=10, delay=10, logger=logger)

    # LAG/LACP config which will be used in test
    lag_lacp_config_dict = {
        'hb': [{'type': 'lacp', 'name': 'bond0', 'members': [interfaces.hb_dut_1, interfaces.hb_dut_2]}]
    }

    # VLAN config which will be used in test
    vlan_config_dict = {
        'dut': [{'vlan_id': 50, 'vlan_members': [{interfaces.dut_ha_1: 'trunk'}]}],
        'ha': [{'vlan_id': 50, 'vlan_members': [{interfaces.ha_dut_1: None}]}],
        'hb': [{'vlan_id': 50, 'vlan_members': [{'bond0': None}]}]
    }

    # IP config which will be used in test
    ip_config_dict = {
        'dut': [{'iface': 'Vlan50', 'ips': [('50.0.0.1', '24')]}],
        'ha': [{'iface': '{}.50'.format(interfaces.ha_dut_1), 'ips': [('50.0.0.2', '24')]}],
        'hb': [{'iface': 'bond0.50', 'ips': [('50.0.0.3', '24')]}]
    }

    logger.info('Starting Lag LACP Test Common configuration')
    LagLacpConfigTemplate.configuration(topology_obj, lag_lacp_config_dict)
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    logger.info('Lag LACP Test Common configuration completed')

    yield

    logger.info('Starting Lag LACP Test Common configuration cleanup')
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    VlanConfigTemplate.cleanup(topology_obj, vlan_config_dict)
    LagLacpConfigTemplate.cleanup(topology_obj, lag_lacp_config_dict)

    dut_cli.general.save_configuration()
    # to prevent advertising the same mac on an interfaces,
    # need to restart ports status after lldp enabling
    hosts_aliases = ['ha', 'hb']
    for host_alias in hosts_aliases:
        host_engine = topology_obj.players[host_alias]['engine']
        cli_object = topology_obj.players[host_alias]['cli']
        if not cli_object.lldp.is_lldp_enabled_on_host():
            cli_object.lldp.enable_lldp_on_host()
            for port in topology_obj.players_all_ports[host_alias]:
                cli_object.interface.disable_interface(port)
                cli_object.interface.enable_interface(port)

    logger.info('Lag LACP Test Common cleanup completed')


@pytest.fixture()
def lag_lacp_config_with_two_bonds(topology_obj, interfaces):
    """
    Pytest fixture which are doing configuration with twp bonds
    :param topology_obj: topology object fixture
    :param interfaces: interfaces fixture
    """
    lag_lacp_config_dict_one_bond = {
        'hb': [{'type': 'lacp', 'name': 'bond0', 'members': [interfaces.hb_dut_1, interfaces.hb_dut_2]}]
    }

    lag_lacp_config_dict_two_bonds = {
        'hb': [{'type': 'lacp', 'name': 'bond0', 'members': [interfaces.hb_dut_1]},
               {'type': 'lacp', 'name': 'bond1', 'members': [interfaces.hb_dut_2]}]
    }

    vlan_config_dict = {
        'hb': [{'vlan_id': 50, 'vlan_members': [{'bond0': None}]}]
    }

    ip_config_dict = {
        'hb': [{'iface': 'bond0.50', 'ips': [('50.0.0.3', '24')]}]
    }

    LagLacpConfigTemplate.cleanup(topology_obj, lag_lacp_config_dict_one_bond)
    LagLacpConfigTemplate.configuration(topology_obj, lag_lacp_config_dict_two_bonds)
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)

    yield

    LagLacpConfigTemplate.cleanup(topology_obj, lag_lacp_config_dict_two_bonds)
    LagLacpConfigTemplate.configuration(topology_obj, lag_lacp_config_dict_one_bond)
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)


def cleanup(cleanup_list):
    """
    execute all the functions in the cleanup list
    :return: None
    """
    cleanup_list.reverse()
    for func, args in cleanup_list:
        func(*args)


@pytest.fixture(autouse=True)
def cleanup_list():
    """
    Fixture to execute cleanup after a test is run
    :return: None
    """
    cleanup_list = []
    yield cleanup_list
    logger.info("------------------test teardown------------------")
    cleanup(cleanup_list)
