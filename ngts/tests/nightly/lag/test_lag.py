import allure
import logging
import re
import ipaddress
import time
import random
from retry.api import retry_call
import pytest

from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.config_templates.lag_lacp_config_template import LagLacpConfigTemplate
from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.config_templates.vlan_config_template import VlanConfigTemplate
from ngts.config_templates.interfaces_config_template import InterfaceConfigTemplate
from ngts.cli_util.verify_cli_show_cmd import verify_show_cmd
from ngts.conftest import cleanup_last_config_in_stack
from ngts.helpers.reboot_reload_helper import get_supported_reboot_reload_types_list
from ngts.helpers.interface_helpers import speed_string_to_int_in_mb
from ngts.helpers.sonic_branch_helper import is_sanitizer_image
from ngts.helpers import json_file_helper
from ngts.constants.constants import SonicConst
from ngts.helpers.interface_helpers import get_service_port

logger = logging.getLogger()
PORTCHANNEL_NAME = 'PortChannel1111'
BASE_PKT = 'Ether(dst="{}")/IP(src="50.0.0.2",dst="50.0.0.3")/{}()/Raw()'
CHIP_LAGS_LIM = {
    'SPC': 64,
    'SPC2': 110,    # TODO SDK support 128, but currently 128 doesn't work
    'SPC3': 110,     # TODO SDK support 128, but currently 128 doesn't work
    'SPC4': 110,     # TODO SDK support 128, but currently 128 doesn't work
    'SPC5': 110     # TODO SDK support 128, but currently 128 doesn't work
}
CHIP_LAG_MEMBERS_LIM = {
    'SPC': 32,
    'SPC2': 64,
    'SPC3': 64,
    'SPC4': 64,
    'SPC5': 64
}


@pytest.mark.reboot_reload
@allure.title('LAG_LACP core functionality and reboot')
def test_core_functionality_with_reboot(topology_obj, cli_objects, traffic_type, interfaces, engines, cleanup_list,
                                        platform_params, is_simx):
    """
    This test case will check the base functionality of LAG/LACP feature.
    Config base configuration as in the picture below.
    Validate port channel and links state.
    Disable port 1 on the host. Validate port channel was affected.
    Disable port 2 and enable port 1 on the host. Validate port channel was affected.
    Enable port 2 on the host. Validate port channel was affected.
    Reboot switch and validate.
    :param topology_obj: topology object
    :param cli_objects: cli_objects object
    :param traffic_type: the type of the traffic
    :param interfaces: interfaces fixture
    :param engines: engines fixture
    :param cleanup_list: list with functions to cleanup
    :return: raise assertion error on unexpected behavior

                                                dut
                                       ------------------------------
                     ha                |    Vlan50 50.0.0.1/24      |                                  hb
              ------------------       |                            |dut_hb1 in lag               ------------------
              |                |       |dut_ha1 vlan50 trunk        |----------------------------|                |
              |     ha_dut1.50 |-------|                            |             hb_dut1 in bond|  bond0.50      |
              |     50.0.0.2/24|       |                            |             hb_dut2 in bond|  50.0.0.3/24   |
              |                |       |            PortChannel1111 |----------------------------|                |
              ------------------       |              vlan 50 trunk |dut_hb2 in lag              ------------------
                                       |                            |
                                       ------------------------------
    """
    dut_cli = topology_obj.players['dut']['cli']

    cleanup_list.append((cli_objects.hb.interface.enable_interface, (interfaces.dut_hb_1,)))
    cleanup_list.append((cli_objects.hb.interface.enable_interface, (interfaces.dut_hb_2,)))
    cleanup_list.append((cli_objects.hb.interface.enable_interface, ('bond0',)))

    # LAG/LACP config which will be used in this test
    lag_lacp_config_dict = {
        'dut': [{'type': 'lacp', 'name': PORTCHANNEL_NAME, 'members': [interfaces.dut_hb_1, interfaces.dut_hb_2]}]
    }
    add_lag_conf(topology_obj, lag_lacp_config_dict, cleanup_list)

    # VLAN config which will be used in this test
    vlan_config_dict = {'vlan_id': 50,
                        'vlan_member': PORTCHANNEL_NAME
                        }
    add_vlan_conf(engines.dut, dut_cli, vlan_config_dict, cleanup_list)

    try:
        with allure.step('Validate the PortChannel status'):
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S'), (interfaces.dut_hb_2, 'S')],
                                                  tries=3)

        with allure.step('Validate the base functionality of LAG - traffic'):
            # PING below need to prevent issue when packet not forwarded to host from switch
            validation_ping = {'sender': 'ha', 'args': {'count': 3, 'dst': '50.0.0.1'}}
            PingChecker(topology_obj.players, validation_ping).run_validation()
            traffic_validation(topology_obj, traffic_type)

        with allure.step('STEP1: Disable interface 1 on host, traffic should pass via interface 2'):
            cli_objects.hb.interface.disable_interface(interfaces.hb_dut_1)
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'D'), (interfaces.dut_hb_2, 'S')])
            traffic_validation(topology_obj, traffic_type)

        with allure.step('STEP2: Enable interface 1 and disable interface 2 on host,'
                         ' traffic should pass via interface 1'):
            cli_objects.hb.interface.enable_interface(interfaces.hb_dut_1)
            cli_objects.hb.interface.disable_interface(interfaces.hb_dut_2)
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S'), (interfaces.dut_hb_2, 'D')])
            traffic_validation(topology_obj, traffic_type)

        with allure.step('STEP3: Enable both interfaces on host'):
            cli_objects.hb.interface.enable_interface(interfaces.hb_dut_2)
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S'), (interfaces.dut_hb_2, 'S')])
            traffic_validation(topology_obj, traffic_type)

        with allure.step('STEP4: Reboot dut'):
            dut_cli.general.save_configuration()
            reboot_types = get_supported_reboot_reload_types_list(platform=platform_params.platform)
            reboot_type = random.choice(reboot_types)
            if is_simx:
                reboot_type = 'reboot'
            dut_cli.general.reboot_reload_flow(r_type=reboot_type, topology_obj=topology_obj)

        with allure.step('STEP5: Validate port channel status and send traffic'):
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S'), (interfaces.dut_hb_2, 'S')])
            traffic_validation(topology_obj, traffic_type)

        with allure.step('STEP6: Validate fallback parameter (default - false)'):
            cli_objects.hb.interface.disable_interface('bond0')
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Dw',
                                                  [(interfaces.dut_hb_1, 'D'), (interfaces.dut_hb_2, 'D')])
            cli_objects.hb.interface.enable_interface('bond0')

        with allure.step('STEP7: Validate configuration of LAG with fallback parameter "true"'):
            cleanup_last_config_in_stack(cleanup_list)  # pop vlan cleanup from stack
            cleanup_last_config_in_stack(cleanup_list)  # remove LAG
            lag_lacp_config_dict = {
                'dut': [{'type': 'lacp', 'name': PORTCHANNEL_NAME,
                         'members': [interfaces.dut_hb_1, interfaces.dut_hb_2], 'params': '--fallback enable'}]
            }
            add_lag_conf(topology_obj, lag_lacp_config_dict, cleanup_list)
            add_vlan_conf(engines.dut, dut_cli, vlan_config_dict, cleanup_list)
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S'), (interfaces.dut_hb_2, 'S')])
            traffic_validation(topology_obj, traffic_type)

        with allure.step('STEP8: Validate functionality of LAG with fallback parameter "true"'):
            config_bond_type_lag(topology_obj, interfaces, cleanup_list)
            logger.info('Wait 120 seconds for LACP timeout')
            time.sleep(120)
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S'), (interfaces.dut_hb_2, 'S')])
            traffic_validation(topology_obj, traffic_type)

    except BaseException as err:
        raise AssertionError(err)


@pytest.mark.reboot_reload
@allure.title('Test port cannot be added to LAG')
def test_port_cannot_be_added_to_lag(topology_obj, traffic_type, interfaces, engines, cleanup_list):
    """
    This test case will check the interop of the port channel.
    Check 'ip', 'speed', 'other_lag', 'vlan' dependencies.
    Config dependency on a port. Trying to add the port to port channel.
    Validate expected error message.
    :param topology_obj: topology object
    :param traffic_type: the type of the traffic
    :param interfaces: interfaces fixture
    :param engines: engines fixture
    :param cleanup_list: list with functions to cleanup
    :return: raise assertion error on unexpected behavior
    """
    try:
        dut_cli = topology_obj.players['dut']['cli']

        # LAG/LACP config which will be used in this test
        lag_lacp_config_dict = {
            'dut': [{'type': 'lacp', 'name': PORTCHANNEL_NAME, 'members': [interfaces.dut_hb_1]}]
        }
        add_lag_conf(topology_obj, lag_lacp_config_dict, cleanup_list)

        # Add VLAN config
        vlan_config_dict = {'vlan_id': 50,
                            'vlan_member': PORTCHANNEL_NAME
                            }
        add_vlan_conf(engines.dut, dut_cli, vlan_config_dict, cleanup_list)

        dependency_list = ['ip', 'speed', 'other_lag', 'vlan']

        for dependency in dependency_list:
            check_dependency(topology_obj, dependency, cleanup_list)

        with allure.step('Validate the PortChannel status'):
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S')],
                                                  tries=3)

        with allure.step('Validate the traffic via the LAG'):
            # PING below need to prevent issue when packet not forwarded to host from switch
            validation_ping = {'sender': 'ha', 'args': {'count': 3, 'dst': '50.0.0.1'}}
            PingChecker(topology_obj.players, validation_ping).run_validation()
            traffic_validation(topology_obj, traffic_type)

    except BaseException as err:
        raise AssertionError(err)


@pytest.mark.reboot_reload
@allure.title('LAG min-links Test')
def test_lag_min_links(topology_obj, traffic_type, interfaces, engines, cleanup_list):
    """
    This test case will check the functionality of 'min-links' parameter.
    Checks that port channel in down state, until he have num of members < min-links parameter.
    :param topology_obj: topology object
    :param traffic_type: the type of the traffic
    :param interfaces: interfaces fixture
    :param engines: engines fixture
    :param cleanup_list: list with functions to cleanup
    :return: raise assertion error on unexpected behavior
    """
    try:
        dut_cli = topology_obj.players['dut']['cli']

        with allure.step('STEP1: Create PortChannel with min-links 1 and no members'):
            lag_config_dict = {
                'dut': [{'type': 'lacp', 'name': PORTCHANNEL_NAME, 'members': [], 'params': '--min-links 1'}]
            }
            add_lag_conf(topology_obj, lag_config_dict, cleanup_list)

        with allure.step('Validate the PortChannel status is Down'):
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Dw',
                                                  [],
                                                  tries=5)
        cleanup_last_config_in_stack(cleanup_list)

        with allure.step('STEP2: Create PortChannel with min-links 1 and 1 member'):
            lag_config_dict = {
                'dut': [{'type': 'lacp',
                         'name': PORTCHANNEL_NAME,
                         'members': [interfaces.dut_hb_1],
                         'params': '--min-links 1'}]
            }
            add_lag_conf(topology_obj, lag_config_dict, cleanup_list)

        with allure.step('Validate the PortChannel status is Up, port status is Selected'):
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S')],
                                                  tries=5)
        cleanup_last_config_in_stack(cleanup_list)

        with allure.step('STEP3: Create PortChannel with min-links 2 and 1 member'):
            lag_config_dict = {
                'dut': [{'type': 'lacp',
                         'name': PORTCHANNEL_NAME,
                         'members': [interfaces.dut_hb_1],
                         'params': '--min-links 2'}]
            }
            add_lag_conf(topology_obj, lag_config_dict, cleanup_list)

        with allure.step('Validate the PortChannel status is Down, port status is Selected'):
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Dw',
                                                  [(interfaces.dut_hb_1, 'S')],
                                                  tries=5)

        with allure.step('STEP4: Add second member to PortChannel with min-links 2'):
            lag_config_dict = {
                'dut': [{'type': 'lacp', 'name': PORTCHANNEL_NAME, 'members': [interfaces.dut_hb_2]}]
            }
            add_lag_conf(topology_obj, lag_config_dict, cleanup_list)

        with allure.step('Validate the PortChannel status is Up, both members status is Selected'):
            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  'Up',
                                                  [(interfaces.dut_hb_1, 'S'), (interfaces.dut_hb_2, 'S')],
                                                  tries=5)

        vlan_config_dict = {'vlan_id': 50,
                            'vlan_member': PORTCHANNEL_NAME
                            }
        add_vlan_conf(engines.dut, dut_cli, vlan_config_dict, cleanup_list)

        with allure.step('Validate the traffic via a LAG'):
            validation_ping = {'sender': 'ha', 'args': {'count': 3, 'dst': '50.0.0.1'}}
            PingChecker(topology_obj.players, validation_ping).run_validation()
            traffic_validation(topology_obj, traffic_type)
    except BaseException as err:
        raise AssertionError(err)


def exclude_service_ports(interfaces_info, service_ports):
    return {iface: info for iface, info in interfaces_info.items() if iface not in service_ports}


@pytest.mark.reboot_reload
@allure.title('LAG members scale Test')
def test_lag_members_scale(topology_obj, interfaces, engines, cleanup_list, platform_params):
    """
    This test case will check the configuration of 1 port channel with max number of members.
    :param topology_obj: topology object
    :param interfaces: interfaces fixture
    :param engines: engines fixture
    :param cleanup_list: list with functions to cleanup
    :return: raise assertion error on unexpected behavior
    """
    try:
        dut_cli = topology_obj.players['dut']['cli']
        del_port_from_vlan(engines.dut, dut_cli, interfaces.dut_ha_1, '50', cleanup_list)

        chip_type = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['chip_type']
        max_lag_members = CHIP_LAG_MEMBERS_LIM[chip_type]
        all_ifaces_info = dut_cli.interface.parse_interfaces_status()
        service_ports = get_service_port(platform_params.platform)
        all_ifaces_info = exclude_service_ports(all_ifaces_info, service_ports)
        # We need to create bond on ifaces with the same type, choose list with ifaces with the same type
        interfaces_types_dict = get_interfaces_by_type_dict(all_ifaces_info)
        test_ifaces_type = get_ifaces_type_which_has_bigger_ifaces_list(interfaces_types_dict)
        all_interfaces_with_same_type = interfaces_types_dict[test_ifaces_type]
        member_interfaces = random.sample(all_interfaces_with_same_type, min(max_lag_members,
                                                                             len(all_interfaces_with_same_type)))
        lb_member_interfaces = get_lag_lb_members(interfaces, member_interfaces)

        with allure.step('Set same speed to all interfaces'):
            dut_orig_ifaces_speeds = dut_cli.interface.get_interfaces_speed(all_interfaces_with_same_type)
            # Get minimal supported speed
            min_speed = min([speed_string_to_int_in_mb(speed) for speed in dut_orig_ifaces_speeds.values()])
            # Get speed for all members and if it's not similar - set all ports to minimal supported speed
            members_speed = {}
            [members_speed.update({iface: dut_orig_ifaces_speeds[iface]}) for iface in member_interfaces]
            if not all(x == list(members_speed.values())[0] for x in list(members_speed.values())):
                interfaces_config_list = []
                for interface in all_interfaces_with_same_type:
                    interfaces_config_list.append({'iface': interface,
                                                   'speed': min_speed,
                                                   'original_speed': dut_orig_ifaces_speeds.get(interface, min_speed)})
                interfaces_config_dict = {
                    'dut': interfaces_config_list
                }
                add_interface_conf(topology_obj, interfaces_config_dict, cleanup_list)

        with allure.step('Disable all member loopback interfaces'):
            dut_cli.interface.disable_interfaces(lb_member_interfaces)
            cleanup_list.append((dut_cli.interface.enable_interfaces, (lb_member_interfaces,)))

        with allure.step('Create PortChannel with all ports as members'):
            lag_config_dict = {
                'dut': [{'type': 'lacp', 'name': PORTCHANNEL_NAME, 'members': member_interfaces}]
            }
            add_lag_conf(topology_obj, lag_config_dict, cleanup_list)

        with allure.step('Check that all interfaces in Up state'):
            retry_call(dut_cli.interface.check_ports_status,
                       fargs=[list(set(member_interfaces).difference(lb_member_interfaces))],
                       tries=20, delay=15,
                       logger=logger)

        with allure.step('Validate members status in PortChannel'):
            expected_ports_status_list = []
            lag_status = 'Dw'
            for interface in member_interfaces:
                if interface in [interfaces.dut_hb_1, interfaces.dut_hb_2]:
                    expected_ports_status_list.append((interface, 'S'))
                    lag_status = 'Up'
                else:
                    expected_ports_status_list.append((interface, 'D'))

            verify_port_channel_status_with_retry(dut_cli,
                                                  engines.dut,
                                                  PORTCHANNEL_NAME,
                                                  lag_status,
                                                  expected_ports_status_list,
                                                  tries=10)
        with allure.step('Validate dockers status'):
            dut_cli.general.verify_dockers_are_up()

    except BaseException as err:
        raise AssertionError(err)


@pytest.mark.reboot_reload
@allure.title('LAGs scale Test')
def test_lags_scale(topology_obj, engines, cleanup_list):
    """
    This test case will check the configuration of maximum number of port channels with ipv4&ipv6 addresses.
    :param topology_obj: topology object
    :param engines: engines fixture
    :param cleanup_list: list with functions to cleanup
    :return: raise assertion error on unexpected behavior
    """
    # Skip the case on ASAN image
    if is_sanitizer_image(topology_obj):
        pytest.skip("Skip performance and scalability tests on ASAN image")

    try:
        # workaround for issue in teardown.
        # removing of LAGs take time. But in show and ASIC_DB it is presented as already removed.
        # the current indicate that LAG was removed is only logging:
        #           "NOTICE teamd#teammgrd: :- removeLag: Stop port channel PortChannel128"
        # TODO create logic for checking the logging.
        cleanup_list.append((time.sleep, (120,)))

        dut_cli = topology_obj.players['dut']['cli']

        chip_type = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['chip_type']
        number_of_lags = CHIP_LAGS_LIM[chip_type]

        lag_config_dict, lag_expected_info, ip_config_dict, ip_expected_info \
            = get_lags_scale_configuration(number_of_lags)

        with allure.step('Create max number of PortChannels'):
            add_lag_conf(topology_obj, lag_config_dict, cleanup_list)

        with allure.step('Validation port channels were created'):
            retry_call(
                verify_port_channels_status,
                fargs=[dut_cli, engines.dut, lag_expected_info],
                tries=10,
                delay=5,
                logger=logger,
            )

        with allure.step('Validation of bug 2435816 - add and verify IPs on all PortChannels'):
            add_ip_conf(topology_obj, ip_config_dict, cleanup_list)
            verify_port_channels_ip(dut_cli, engines.dut, ip_expected_info)

        with allure.step('Reloading the DUT config using cmd: "config reload -y"'):
            dut_cli.general.save_configuration()
            dut_cli.general.reboot_reload_flow(r_type=SonicConst.CONFIG_RELOAD_CMD, topology_obj=topology_obj)

        with allure.step('Validation for bug 2435254 - validate lags and ips'
                         ' are configured properly after config reload'):
            retry_call(
                verify_port_channels_status,
                fargs=[dut_cli, engines.dut, lag_expected_info],
                tries=10,
                delay=5,
                logger=logger,
            )
            retry_call(
                verify_port_channels_ip,
                fargs=[dut_cli, engines.dut, ip_expected_info],
                tries=3,
                delay=10,
                logger=logger,
            )
    except BaseException as err:
        raise AssertionError(err)


def get_lag_lb_members(interfaces, member_interfaces):
    """
    :param interfaces: host-dut/dut-host ports dict
    :param member_interfaces: a list of lag member ports
    :return: a list of lag members which are connected as loopback
    """
    dut_host_ifaces = [interfaces.dut_ha_1, interfaces.dut_ha_2, interfaces.dut_hb_1, interfaces.dut_hb_2]
    lb_member_interfaces = list(set(member_interfaces).difference(dut_host_ifaces))
    return lb_member_interfaces


def get_lags_scale_configuration(number_of_lags):
    """
    Create configuration info for large number of lags with ip addresses and expected result
    :param number_of_lags: number of lags
    :return: lag_config_dict - lag configuration dictionary
             lag_expected_info - lag expected status information
             ip_config_dict - ip configuration dictionary
             ip_expected_info - ip expected status information
    """
    base_lag_name = 'PortChannel'
    base_lag_index = '1'
    lag_config_list = []
    lag_expected_info = []
    base_ipv4 = ipaddress.IPv4Address('100.0.0.1')
    base_ipv6 = ipaddress.IPv6Address('2000:2001::1')
    ip_config_list = []
    ip_expected_info = {'ipv4': [], 'ipv6': []}
    logger.info('Generate PortChannels configuration lists')
    for index in range(number_of_lags):
        lag_name = '{}{}'.format(base_lag_name, str(int(base_lag_index) + index))
        lag_config_list.append({'type': 'lacp', 'name': lag_name, 'members': []})
        lag_expected_info.append((r'{PORTCHANNEL}.*{PORTCHANNEL_STATUS}.*(N/A|.*)'
                                  .format(PORTCHANNEL=lag_name,
                                          PORTCHANNEL_STATUS='Dw'), True))
        lag_ipv4_address = base_ipv4 + index * 256    # increase the 10.0.X.1
        lag_ipv6_address = base_ipv6 + index * 65536  # increase the 2000:2001::X:1
        ip_config_list.append({'iface': lag_name, 'ips': [(lag_ipv4_address, '24'), (lag_ipv6_address, '112')]})
        ip_expected_info['ipv4'].append((r'{PORTCHANNEL}\s+{IP}/24'
                                         .format(PORTCHANNEL=lag_name, IP=lag_ipv4_address), True))
        ip_expected_info['ipv6'].append((r'{PORTCHANNEL}\s+{IP}/112'
                                         .format(PORTCHANNEL=lag_name, IP=lag_ipv6_address), True))

    lag_config_dict = {
        'dut': lag_config_list
    }
    ip_config_dict = {
        'dut': ip_config_list
    }
    logger.debug('lag_config_dict: {} \nlag_expected_info: {}'.format(lag_config_dict, lag_expected_info))
    return lag_config_dict, lag_expected_info, ip_config_dict, ip_expected_info


def check_dependency(topology_obj, dependency, cleanup_list):
    """
    Verify port channel dependencies
    :param topology_obj: topology object
    :param dependency: type of dependency
    :param cleanup_list: list with functions to cleanup
    :return: None, raise error in case of unexpected result
    """
    with allure.step('Validate the {} dependency'.format(dependency)):
        dut_engine = topology_obj.players['dut']['engine']
        dut_cli = topology_obj.players['dut']['cli']
        dut_hb_2 = topology_obj.ports['dut-hb-2']
        eval('config_{}_dependency(topology_obj, cleanup_list)'.format(dependency))
        err_msg = eval('get_{}_dependency_err_msg(dut_hb_2)'.format(dependency))
        verify_add_member_to_lag_failed_with_err(dut_engine, dut_cli, dut_hb_2, err_msg)
        cleanup_last_config_in_stack(cleanup_list)


def config_ip_dependency(topology_obj, cleanup_list):
    """
    Add ip configurations to verify the ip dependency
    :param topology_obj: topology object
    :param cleanup_list: list with functions to cleanup
    """
    dut_hb_2 = topology_obj.ports['dut-hb-2']
    ip_config_dict = {
        'dut': [{'iface': dut_hb_2, 'ips': [('50.0.0.10', '24')]}]
    }
    add_ip_conf(topology_obj, ip_config_dict, cleanup_list)


def add_ip_conf(topology_obj, ip_config_dict, cleanup_list):
    """
    Add ip configurations
    :param topology_obj: topology object
    :param ip_config_dict: vlan configuration to add
    :param cleanup_list: list with functions to cleanup
    """
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    cleanup_list.append((IpConfigTemplate.cleanup, (topology_obj, ip_config_dict,)))


def get_ip_dependency_err_msg(interface):
    """
    Get expected error message of adding the port to port channel
    :param interface: interface name
    :return: expected error message
    """
    err_msg = '{} has ip address configured'.format(interface)
    return err_msg


def config_speed_dependency(topology_obj, cleanup_list):
    """
    Add speed configurations to verify the speed dependency
    :param topology_obj: topology object
    :param cleanup_list: list with functions to cleanup
    """
    dut_hb_2 = topology_obj.ports['dut-hb-2']
    cli_obj = topology_obj.players['dut']['cli']
    dut_engine = topology_obj.players['dut']['engine']
    dut_original_interfaces_speeds = cli_obj.interface.get_interfaces_speed([dut_hb_2])
    # Read supported port speeds from platform.json file
    platform_json_info = json_file_helper.get_platform_json(dut_engine, cli_obj, fail_if_does_not_exist=False)
    iface_supported_speeds = cli_obj.general.parse_platform_json(topology_obj, platform_json_info)[dut_hb_2]
    # Get unique values and find minimum configured speed
    unique_speeds = set(item for s in iface_supported_speeds.values() if s for item in s)
    min_supported_speed = min(unique_speeds, key=lambda x: int(x[:-1]))
    interfaces_config_dict = {
        'dut': [{'iface': dut_hb_2, 'speed': min_supported_speed,
                 'original_speed': dut_original_interfaces_speeds[dut_hb_2]}]
    }
    add_interface_conf(topology_obj, interfaces_config_dict, cleanup_list)


def add_interface_conf(topology_obj, interfaces_config_dict, cleanup_list):
    """
    Add interface configurations
    :param topology_obj: topology object
    :param interfaces_config_dict: vlan configuration to add
    :param cleanup_list: list with functions to cleanup
    """
    InterfaceConfigTemplate.configuration(topology_obj, interfaces_config_dict)
    cleanup_list.append((InterfaceConfigTemplate.cleanup, (topology_obj, interfaces_config_dict,)))


def get_speed_dependency_err_msg(interface):
    """
    Get expected error message of adding the port to port channel
    :param interface: interface name
    :return: expected error message
    """
    err_msg = 'Port speed of {} is different than the other members of the portchannel {}'. \
        format(interface, PORTCHANNEL_NAME)
    return err_msg


def config_other_lag_dependency(topology_obj, cleanup_list):
    """
    Add lag configurations to verify the lag dependency
    :param topology_obj: topology object
    :param cleanup_list: list with functions to cleanup
    """
    dut_hb_2 = topology_obj.ports['dut-hb-2']
    lag_config_dict_second_lag = {
        'dut': [{'type': 'lacp', 'name': 'PortChannel2222', 'members': [dut_hb_2]}]
    }
    add_lag_conf(topology_obj, lag_config_dict_second_lag, cleanup_list)


def add_lag_conf(topology_obj, lag_config_dict, cleanup_list):
    """
    Add lag configurations
    :param topology_obj: topology object
    :param lag_config_dict: vlan configuration to add
    :param cleanup_list: list with functions to cleanup
    """
    LagLacpConfigTemplate.configuration(topology_obj, lag_config_dict)
    cleanup_list.append((LagLacpConfigTemplate.cleanup, (topology_obj, lag_config_dict,)))


def remove_lag_conf(topology_obj, lag_config_dict, cleanup_list):
    """
    remove lag configurations
    :param topology_obj: topology object
    :param lag_config_dict: vlan configuration to remove
    :param cleanup_list: list with functions to cleanup
    """
    LagLacpConfigTemplate.cleanup(topology_obj, lag_config_dict)
    cleanup_list.append((LagLacpConfigTemplate.configuration, (topology_obj, lag_config_dict,)))


def get_other_lag_dependency_err_msg(interface):
    """
    Get expected error message of adding the port to port channel
    :param interface: interface name
    :return: expected error message
    """
    err_msg = '{} Interface is already member of {}'.format(interface, 'PortChannel2222')
    return err_msg


def config_vlan_dependency(topology_obj, cleanup_list):
    """
    Add vlan configurations to verify the vlan dependency
    :param topology_obj: topology object
    :param cleanup_list: list with functions to cleanup
    """
    dut_hb_2 = topology_obj.ports['dut-hb-2']
    engine = topology_obj.players['dut']['engine']
    dut_cli = topology_obj.players['dut']['cli']
    vlan_config_dict = {'vlan_id': 50,
                        'vlan_member': dut_hb_2
                        }
    add_vlan_conf(engine, dut_cli, vlan_config_dict, cleanup_list)


def get_vlan_dependency_err_msg(interface):
    """
    Get expected error message of adding the port to port channel
    :param interface: interface name
    :return: expected error message
    """
    err_msg = '{} Interface configured as VLAN_MEMBER under vlan : Vlan50'.format(interface)
    return err_msg


def add_vlan_conf(engine, cli_obj, vlan_config_dict, cleanup_list):
    """
    Add vlan configurations
    :param engine: engine of dut
    :param cli_obj: dut cli object
    :param vlan_config_dict: vlan configuration to add
    :param cleanup_list: list with functions to cleanup
    """
    cli_obj.vlan.add_port_to_vlan(vlan_config_dict['vlan_member'], vlan_config_dict['vlan_id'])
    cleanup_list.append((cli_obj.vlan.del_port_from_vlan,
                         (vlan_config_dict['vlan_member'], vlan_config_dict['vlan_id'])))


def del_port_from_vlan(dut_engine, cli_obj, port, vlan, cleanup_list):
    """
    Delete port from vlan
    :param dut_engine: dut engine
    :param cli_obj: dut cli object
    :param port: port name
    :param cleanup_list: list with functions to cleanup
    """
    cli_obj.vlan.del_port_from_vlan(port, vlan)
    cleanup_list.append((cli_obj.vlan.add_port_to_vlan, (port, vlan, 'trunk',)))


def verify_add_member_to_lag_failed_with_err(dut_engine, cli_object, member_port, err_msg):
    """
    Verify negative adding member to port channel
    :param dut_engine: dut engine
    :param cli_object: dut cli object
    :param member_port: name of member port to be added
    :param err_msg: expected error message
    :return: None, raise error in case of unexpected result
    """
    with allure.step('Verify lag dependency, adding member failed as expected with error message: {}'.format(err_msg)):
        output = cli_object.lag.add_port_to_port_channel(member_port, PORTCHANNEL_NAME)
        if not re.search(err_msg, output, re.IGNORECASE):
            output = cli_object.lag.delete_port_from_port_channel(member_port, PORTCHANNEL_NAME)
            raise AssertionError("Expected to failed on adding member to LAG "
                                 "with error msg '{}' but output {}".
                                 format(err_msg, output))


def get_pkt_to_send(traffic_type, cli_obj, dst_iface):
    """
    Create scapy packet for validation
    :param traffic_type: the type of the traffic
    :param cli_obj: device cli_obj
    :param dst_iface: destination interface name
    :return: scapy packet
    """
    dst_mac = cli_obj.mac.get_mac_address_for_interface(dst_iface)
    return BASE_PKT.format(dst_mac, traffic_type)


def verify_port_channel_status_with_retry(cli_object, dut_engine, lag_name, lag_status,
                                          expected_ports_status_list, tries=8, delay=15):
    """
    Verify the PortChannels from "show interfaces portchannel" output, accordingly to handed statuses with retry
    :param cli_object: dut cli object
    :param dut_engine: dut engine
    :param lag_name: port channel name
    :param lag_status: port channel status
    :param expected_ports_status_list: list of tuples - (member port name, status)
    :param tries: number of attempts
    :param delay: delay time between attempts
    """
    retry_call(cli_object.lag.verify_port_channel_status,
               fargs=[lag_name, lag_status, expected_ports_status_list],
               tries=tries,
               delay=delay,
               logger=logger)


def verify_port_channels_status(cli_object, dut_engine, expected_lag_info):
    """
    Verify the PortChannels from "show interfaces portchannel" output
    :param cli_object: dut cli object
    :param dut_engine: dut engine
    :param expected_lag_info: expected port channels information
    :return: None, raise error in case of unexpected result
    """
    port_channel_info = cli_object.lag.show_interfaces_port_channel()
    verify_show_cmd(port_channel_info, expected_lag_info)


def verify_port_channels_ip(cli_object, dut_engine, expected_ip_info):
    """
    Verify the PortChannels ips
    :param cli_object: dut cli object
    :param dut_engine: dut engine
    :param expected_ip_info: expected ip information
    :return: None, raise error in case of unexpected result
    """
    verify_port_channels_ipv4_addresses(cli_object, dut_engine, expected_ip_info['ipv4'])
    verify_port_channels_ipv6_addresses(cli_object, dut_engine, expected_ip_info['ipv6'])


def verify_port_channels_ipv4_addresses(cli_object, dut_engine, expected_ip_info):
    """
    Verify the PortChannels ips from "show ip interfaces" output
    :param cli_object: dut cli object
    :param dut_engine: dut engine
    :param expected_ip_info: expected ip information
    :return: None, raise error in case of unexpected result
    """
    ip_info = cli_object.ip.show_ip_interfaces()
    verify_show_cmd(ip_info, expected_ip_info)


def verify_port_channels_ipv6_addresses(cli_object, dut_engine, expected_ip_info):
    """
    Verify the PortChannels ips from "show ipv6 interfaces" output
    :param cli_object: dut cli object
    :param dut_engine: dut engine
    :param expected_ip_info: expected ip information
    :return: None, raise error in case of unexpected result
    """
    ip_info = cli_object.ip.show_ipv6_interfaces()
    verify_show_cmd(ip_info, expected_ip_info)


def traffic_validation(topology_obj, traffic_type):
    """
    Validate the handed traffic type on the setup
    :param topology_obj: topology object
    :param traffic_type: the type of the traffic (TCP/UDP)
    :return: None, raise error in case of unexpected result
    """
    tcpdump_filter = 'dst 50.0.0.3 and {}'.format(traffic_type.lower())
    hadut1 = topology_obj.ports['ha-dut-1']
    hb_cli_obj = topology_obj.players['hb']['cli']
    pkt = get_pkt_to_send(traffic_type, hb_cli_obj, 'bond0')
    validation = {'sender': 'ha', 'send_args': {'interface': hadut1 + '.50',
                                                'packets': pkt, 'count': 100},
                  'receivers':
                      [
                          {'receiver': 'hb',
                           'receive_args': {'interface': 'bond0.50',
                                            'filter': tcpdump_filter, 'count': 100}}
    ]
    }
    ScapyChecker(topology_obj.players, validation).run_validation()


def config_bond_type_lag(topology_obj, interfaces, cleanup_list):
    """
    Config bond to type lag, add to cleanup restore functions
    :param topology_obj: topology object
    :param interfaces: interfaces obj
    :param cleanup_list: list with functions to cleanup
    :return: None, raise error in case of unexpected result
    """
    lag_lacp_config_dict = {
        'hb': [{'type': 'lacp', 'name': 'bond0', 'members': [interfaces.hb_dut_1, interfaces.hb_dut_2]}]
    }

    vlan_config_dict = {
        'hb': [{'vlan_id': 50, 'vlan_members': [{'bond0': None}]}]
    }

    ip_config_dict = {
        'hb': [{'iface': 'bond0.50', 'ips': [('50.0.0.3', '24')]}]
    }

    lag_lacp_config_dict_type_lag = {
        'hb': [{'type': 'lag', 'name': 'bond0', 'members': [interfaces.hb_dut_1, interfaces.hb_dut_2]}]
    }

    # add to cleanup stack original IP and Vlan config
    cleanup_list.append((IpConfigTemplate.configuration, (topology_obj, ip_config_dict,)))
    cleanup_list.append((VlanConfigTemplate.configuration, (topology_obj, vlan_config_dict,)))

    # remove origin lag config and add to stack the adding
    remove_lag_conf(topology_obj, lag_lacp_config_dict, cleanup_list)

    # add temp config and add to stack the cleanup
    add_lag_conf(topology_obj, lag_lacp_config_dict_type_lag, cleanup_list)

    # add original IP and Vlan configs
    VlanConfigTemplate.configuration(topology_obj, vlan_config_dict)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)


def get_interfaces_by_type_dict(interfaces_info):
    """
    Get dictionary with lists of RJ45 interfaces and rest QSFP interfaces
    :param interfaces_info: parsed output from "show interfaces status" command
    :return: dictionary
    """
    rg45_type = 'RJ45'
    qsfp_type = 'QSFP'
    interfaces_types_dict = {rg45_type: [], qsfp_type: []}

    for interface in interfaces_info:
        if interfaces_info[interface]['Type'] == rg45_type:
            interfaces_types_dict[rg45_type].append(interface)
        else:
            interfaces_types_dict[qsfp_type].append(interface)

    return interfaces_types_dict


def get_ifaces_type_which_has_bigger_ifaces_list(interfaces_types_dict):
    """
    Get type of interface which has bigger number of interfaces
    :param interfaces_types_dict: dict, example: {'RJ45': ['Ethernet0', 'Ethernet1'], 'QSFP': ['Ethernet2']}
    :return: str, interface type which have bigger list of interfaces
    """
    num_of_ifaces = 0
    ifaces_type = None

    for iface_type in interfaces_types_dict:
        if len(interfaces_types_dict[iface_type]) > num_of_ifaces:
            num_of_ifaces = len(interfaces_types_dict[iface_type])
            ifaces_type = iface_type

    return ifaces_type
