import allure
import logging
import pytest
import random
import re
from retry.api import retry_call
from ngts.helpers.dependencies_helpers import DependenciesBase
from ngts.tests.conftest import get_dut_loopbacks
from ngts.helpers.breakout_helpers import get_dut_breakout_modes
from ngts.helpers.interface_helpers import get_speed_in_G_format
from ngts.cli_util.verify_cli_show_cmd import verify_show_cmd
from infra.tools.redmine.redmine_api import is_redmine_issue_active

"""

 Dynamic Port Breakout Test Plan

 Documentation: https://wikinox.mellanox.com/display/SW/SONiC+NGTS+Port+Breakout+Documentation

"""

logger = logging.getLogger()

all_breakout_options = {"1x100G[40G]", "2x50G", "4x25G[10G]", "1x400G", "2x200G", "4x100G", "8x50G",
                        "1x200G[100G,50G,40G,25G,10G,1G]", "1x800G[400G,200G,100G,50G,40G,25G,10G]",
                        "2x100G[50G,40G,25G,10G,1G]", "4x50G[40G,25G,10G,1G]", "1x25G[10G]",
                        "1x100G[50G,40G,25G,10G]", "2x50G[40G,25G,10G]", "4x25G[10G]", "1x25G[10G,1G]",
                        "1x100G[50G,40G,25G,10G,1G]", "2x50G[40G,25G,10G,1G]", "4x25G[10G,1G]",
                        "1x400G[200G,100G,50G,40G,25G,10G,1G]", "2x400G[200G,100G,50G,40G,25G,10G]",
                        "2x200G[100G,50G,40G,25G,10G,1G]", "4x200G[100G,50G,40G,25G,10G]",
                        "4x100G[50G,40G,25G,10G,1G]", "8x100G[50G,25G,10G]"}


@pytest.fixture(autouse=True, scope='session')
def dut_engine(topology_obj):
    return topology_obj.players['dut']['engine']


@pytest.fixture(autouse=True, scope='session')
def cli_object(topology_obj):
    return topology_obj.players['dut']['cli']


def ports_breakout_modes(dut_engine, cli_object, sw_control_ports, is_sw_control_feature_enabled, cli_objects):
    if is_sw_control_feature_enabled and is_redmine_issue_active([3891669])[0]:
        pytest.skip(f"Skipping test when SW control feature enabled and RM 3891669 is active")
    aoc_cables = cli_objects.dut.im.sw_controlled_aoc_cables(sw_control_ports)
    return get_dut_breakout_modes(dut_engine, cli_object, aoc_cables)


def tested_modes_lb_conf(topology_obj, ports_breakout_modes, cli_objects, sw_control_ports):
    aoc_cables = cli_objects.dut.im.sw_controlled_aoc_cables(sw_control_ports)
    return get_random_lb_breakout_conf(topology_obj, ports_breakout_modes, aoc_cables)


@pytest.fixture(scope='session', autouse=True)
def dpb_configuration(topology_obj, setup_name, engines, cli_objects, platform_params, is_air):
    """
    Pytest fixture which will clean QoS configuration from the dut before DPB test
    and will configure Qos and dynamic buffer configuration after DPB tests finished

    """
    logger.info("Remove qos and dynamic buffer configuration before DPB tests")
    with allure.step("Remove qos and dynamic buffer configuration before DPB tests"):
        cli_objects.dut.qos.clear_qos()
        cli_objects.dut.general.save_configuration()
        cli_objects.dut.general.reload_flow(topology_obj=topology_obj, reload_force=True)

    yield

    logger.info('Starting DPB configuration cleanup')
    cli_objects.dut.general.apply_basic_config(topology_obj, setup_name, platform_params, is_air=is_air)

    logger.info('DPB cleanup completed')


def get_random_lb_breakout_conf(topology_obj, ports_breakout_modes, ports_to_exclude=None):
    """
    :return: A dictionary with different loopback for each supported breakout modes.
    this will be used later in the test t configure different breakout modes on loopbacks and test them.
    i.e,
    {'2x100G[50G,40G,25G,10G,1G]': ('Ethernet48', 'Ethernet44'),
    '4x50G[40G,25G,10G,1G]': ('Ethernet116', 'Ethernet120')}
    """
    conf = {}
    breakout_modes_supported_lb, unbreakout_modes_supported_lb = \
        divide_breakout_modes_to_breakout_and_unbreakout_modes(topology_obj, ports_breakout_modes, ports_to_exclude)
    for breakout_mode, supported_lb_list in breakout_modes_supported_lb.items():
        # TODO: Currently SONiC doesn't support 8x breakout in DPB, remove this when 8x breakout is supported
        if '8x' in breakout_mode:
            continue
        unused_loopbacks = list(set(supported_lb_list).difference(set(conf.values())))
        if unused_loopbacks:
            lb = random.choice(unused_loopbacks)
            conf[breakout_mode] = lb
        else:
            continue
    if len(conf.keys()) < len(breakout_modes_supported_lb.keys()):
        logger.warning("Test configuration doesn't cover all breakout modes, missing breakout modes: {}"
                       .format(list(set(breakout_modes_supported_lb.keys()).difference(set(conf.keys())))))
    if not conf:
        pytest.skip("Can't test DPB Feature on this setup because there "
                    "are no available splittable ports on this topology")
    return conf


def divide_breakout_modes_to_breakout_and_unbreakout_modes(topology_obj, ports_breakout_modes, ports_to_exclude=None):
    """

    :return: a dictionary with a list of loopbacks that support each breakout modes
    and a dictionary with a list of loopbacks that support each unbreakout modes,
    i.e,
    breakout_modes_supported_lb =

    {'4x50G[40G,25G,10G,1G]': [('Ethernet8', 'Ethernet4'), ('Ethernet36', 'Ethernet40'),...],
    '2x100G[50G,40G,25G,10G,1G]': [('Ethernet8', 'Ethernet4'), ('Ethernet36', 'Ethernet40'),...] }
    -------------------------------------------------------------------------------
    unbreakout_modes_supported_lb =
    {'1x200G[100G,50G,40G,25G,10G,1G]': [('Ethernet8', 'Ethernet4'), ('Ethernet36', 'Ethernet40'),..]}
    """
    breakout_modes = parsed_dut_loopbacks_by_breakout_modes(topology_obj, ports_breakout_modes, ports_to_exclude)
    breakout_modes_supported_lb = {}
    unbreakout_modes_supported_lb = {}
    for breakout_mode, supported_lb_list in breakout_modes.items():
        if is_breakout_mode(breakout_mode):
            breakout_modes_supported_lb[breakout_mode] = supported_lb_list
        else:
            unbreakout_modes_supported_lb[breakout_mode] = supported_lb_list
    return breakout_modes_supported_lb, unbreakout_modes_supported_lb


def is_breakout_mode(breakout_mode):
    """
    :param breakout_mode: a breakout mode, such as:  "1x50G(2)+2x25G(2)", "2x100G[50G,40G,25G,10G,1G]" etc.
    :return: True if is breakout mode, False other wise
    For example:
    breakout_mode: "2x100G[50G,40G,25G,10G,1G]" -> return True
    breakout_mode: "1x50G(2)+2x25G(2)" -> return True
    breakout_mode: "1x100G[40G]" -> return False
    """
    breakout_pattern = "[248]x"
    return bool(re.search(breakout_pattern, breakout_mode))


def parsed_dut_loopbacks_by_breakout_modes(topology_obj, ports_breakout_modes, ports_to_exclude=None):
    """
    :return: A dictionary with a list of loopbacks that support each breakout modes.
    i.e,
    breakout_modes_supported_lb =
    {'4x50G[40G,25G,10G,1G]': [('Ethernet8', 'Ethernet4'), ('Ethernet36', 'Ethernet40'),...],
    '2x100G[50G,40G,25G,10G,1G]': [('Ethernet8', 'Ethernet4'), ('Ethernet36', 'Ethernet40'),...] },
    '1x200G[100G,50G,40G,25G,10G,1G]': [('Ethernet8', 'Ethernet4'), ('Ethernet36', 'Ethernet40'),..]}

    """
    breakout_modes_supported_lb = {}
    dut_loopback = get_dut_loopbacks(topology_obj)
    for lb in dut_loopback:
        if ports_to_exclude and set(lb).intersection(set(ports_to_exclude)):
            logger.info(f'Excluding loopback {lb} from test scenario')
            continue
        mutual_breakoutmodes = get_mutual_breakout_modes(ports_breakout_modes, lb)
        for breakout_mode in mutual_breakoutmodes:
            if breakout_modes_supported_lb.get(breakout_mode):
                breakout_modes_supported_lb[breakout_mode].append(lb)
            else:
                breakout_modes_supported_lb[breakout_mode] = [lb]
    return breakout_modes_supported_lb


def get_mutual_breakout_modes(ports_breakout_modes, ports_list):
    """
    :param ports_list: a list of ports, i.e. ['Ethernet8', 'Ethernet4', 'Ethernet36', 'Ethernet40']
    :return: a list of breakout modes supported by all the ports on the list
    """
    breakout_mode_sets = []
    for port in ports_list:
        breakout_mode_sets.append(set(ports_breakout_modes[port]['breakout_modes']))
    return set.intersection(*breakout_mode_sets)


def set_dpb_conf(dut_engine, cli_object, ports_breakout_modes, cleanup_list, conf, original_speed_conf, force=False):
    """
    configure DPB conf and return ports expected status after DPB had been applied.
    :param dut_engine: ssh engine
    :param cli_object: cli object
    :param ports_breakout_modes: a dictionary with information about ports breakout options
                                i.e.,
                                    {'Ethernet0':
                                        {'index': ['1'],
                                        'lanes': ['0'],
                                        'breakout_modes': ['1x25G[10G,1G]'],
                                        'breakout_port_by_modes': {'1x25G[10G,1G]': {'Ethernet0': '25G'}},
                                        'speeds_by_modes': {'1x25G[10G,1G]': ['10G', '1G', '25G']},
                                        'default_breakout_mode': '1x25G[10G,1G]'},
                                    'Ethernet4': ...}
    :param cleanup_list: a list of functions for test cleanup
    :param conf: a dictionary of DPB configuration that need to be applied
    i.e,
    {'4x25G[10G,1G]': ['Ethernet192']}
    breakout mode '4x25G[10G,1G]' should be applied to ports ['Ethernet192']
    :param original_speed_conf: original speed on ports that should be restored after DPB configuration has been removed
    :param force: True if DPB command should use -f flag, False otherwise
    :return: dictionary with ports status after DPB configuration had been applied
    {'Ethernet192': '25G',
    'Ethernet193': '25G',
    'Ethernet194': '25G',
    'Ethernet195': '25G', ...}
    """
    original_ports_list = []
    remove_conf = build_remove_dpb_conf(conf, ports_breakout_modes)
    for breakout_mode, ports_list in conf.items():
        original_ports_list += ports_list

    if cleanup_list is not None:
        set_dpb_cleanup(cleanup_list, dut_engine, cli_object, remove_conf, original_ports_list, original_speed_conf)
    breakout_ports_conf = cli_object.interface.configure_dpb_on_ports(conf, force=force)
    cli_object.interface.enable_interfaces(breakout_ports_conf.keys())
    return breakout_ports_conf


def set_dpb_cleanup(cleanup_list, dut_engine, cli_object, remove_conf, original_ports_list, original_speed_conf):
    for port_remove_dpb_conf in remove_conf:
        cleanup_list.append((cli_object.interface.configure_dpb_on_ports, (port_remove_dpb_conf,
                                                                           False, True)))
    cleanup_list.append((cli_object.interface.enable_interfaces, (original_ports_list,)))
    original_speed_conf_subset = {key: original_speed_conf[key] for key in original_ports_list}
    cleanup_list.append((cli_object.interface.set_interfaces_speed, (original_speed_conf_subset,)))


def is_splittable(ports_breakout_modes, port_name):
    """
    :param port_name: i.e 'Ethernet4'
    :return: True if port is supporting at least 1 breakout mode, else False
    """
    has_breakout_mode = False
    port_breakout_modes = ports_breakout_modes[port_name]['breakout_modes']
    for port_breakout_mode in port_breakout_modes:
        if is_breakout_mode(port_breakout_mode):
            has_breakout_mode = True
            break
    return has_breakout_mode


def verify_ifaces_speed_and_status(cli_object, dut_engine, breakout_ports_conf):
    """
    verify the ports state is up and speed configuration is as expected
    :param breakout_ports_conf: a dictionary with the port configuration after breakout
    {'Ethernet216': '25G',
    'Ethernet217': '25G',...}
    :return: raise assertion error in case validation of port status or speed fail
    """
    interfaces_list = list(breakout_ports_conf.keys())
    with allure.step('Verify interfaces are in up state'):
        logger.info('Verify interfaces are in up state')
        retry_call(cli_object.interface.check_ports_status,
                   fargs=[interfaces_list],
                   tries=6, delay=10, logger=logger)
    verify_ifaces_speed(dut_engine, cli_object, breakout_ports_conf)
    full_interfaces_list = cli_object.interface.parse_interfaces_status().keys()
    verify_ifaces_transceiver_presence(cli_object, full_interfaces_list)


def verify_ifaces_speed(dut_engine, cli_object, breakout_ports_conf):
    """
    :param breakout_ports_conf: a dictionary with the port configuration after breakout
    {'Ethernet216': '25G',
    'Ethernet217': '25G',...}
    :return: raise assertion error in case configured speed is not as expected
    """
    interfaces_list = list(breakout_ports_conf.keys())
    with allure.step('Verify interfaces speed configuration'):
        logger.info('Verify interfaces speed configuration')
        actual_speed_conf = cli_object.interface.get_interfaces_speed(interfaces_list)
        compare_actual_and_expected_speeds(breakout_ports_conf, actual_speed_conf)


def verify_ifaces_transceiver_presence(cli_object, interfaces_list):
    """
    :param dut_engine: ssh engine of dut
    :param cli_object: cli object of dut
    :param breakout_ports_conf: a dictionary with the port configuration after breakout
    {'Ethernet216': '25G',
    'Ethernet217': '25G',...}
    :return: Exception raised in case of not all breakout ports has transceiver present
    """
    with allure.step('Verify interfaces transceiver presence'):
        transceiver_presence = cli_object.interface.parse_interfaces_transceiver_presence()
        for iface in interfaces_list:
            with allure.step(f'Verify interface {iface} transceiver presence'):
                assert transceiver_presence[iface]['Presence'] == 'Present'


def compare_actual_and_expected_speeds(expected_speeds_dict, actual_speeds_dict):
    """
    :param expected_speeds_dict: a dictionary of ports expected speeds,
    i.e, {'Ethernet216': '25G',
    'Ethernet217': '25G',...}
    :param actual_speeds_dict: a dictionary of ports actual speeds
    :return: raise assertion error in case expected and actual speed don't match
    """
    with allure.step('Compare expected and actual speeds'):
        logger.debug("expected_speeds_dict: {}".format(expected_speeds_dict))
        logger.debug("actual_speeds_dict: {}".format(actual_speeds_dict))
        for interface, expected_speed in expected_speeds_dict.items():
            actual_speed = actual_speeds_dict[interface]
            expected_speed = get_speed_in_G_format(expected_speed)
            assert actual_speed == expected_speed, \
                f"Interface {interface} actual speed: {actual_speed}) " \
                f"after breakout doesn't match expected speed: {expected_speed}"


def verify_no_breakout(cli_object, ports_breakout_conf, tested_conf):
    """
    :param cli_object: dut cli object
    :param ports_breakout_conf: a dictionary with the port configuration after breakout
    {'Ethernet216': '25G',
    'Ethernet217': '25G',...}
    :param tested_conf: a dictionary of the tested configuration,
    i.e breakout mode and ports list which breakout mode will be applied on
    {'2x50G[40G,25G,10G,1G]': ('Ethernet212', 'Ethernet216'), '4x25G[10G,1G]': ('Ethernet228', 'Ethernet232')}
    :return: raise assertion error in case the breakout mode is still applied on the ports
    """
    all_breakout_ports = list(ports_breakout_conf.keys())
    ports_list = []
    for breakout_mode, ports in tested_conf.items():
        for port in ports:
            ports_list.append(port)
            all_breakout_ports.remove(port)

    with allure.step('Verify ports {} are up'.format(ports_list)):
        retry_call(cli_object.interface.check_ports_status,
                   fargs=[ports_list],
                   tries=6, delay=10, logger=logger)

    with allure.step('Verify there is no breakout ports: {}'.format(all_breakout_ports)):
        cmd_output = cli_object.interface.show_interfaces_status()
        verify_show_cmd(cmd_output, [(r"{}\s+".format(port), False) for port in all_breakout_ports])


def send_ping_and_verify_results(topology_obj, dut_engine, cleanup_list, lb_list, ports_ip_conf=None):
    """
    Function is disabled due to open issue -
    https://github.com/Azure/sonic-buildimage/issues/5947
    TODO: once issue https://github.com/Azure/sonic-buildimage/issues/5947 has been resolved - function can be restored
    :param lb_list: a dictionary of the tested configuration,
    i.e breakout mode and ports list which breakout mode will be applied on
    [('Ethernet212', 'Ethernet216'), ('Ethernet228', 'Ethernet232')]
    :return: raise assertion error in case ping failed
    """
    # ports_ip_conf = set_ip_conf_for_ping(topology_obj, cleanup_list, lb_list) if not ports_ip_conf else ports_ip_conf
    # ping_validation(dut_engine, lb_list, ports_ip_conf)


def set_ip_conf_for_ping(topology_obj, cleanup_list, lb_list):
    ports_list = get_ports_list_from_loopback_tuple_list(lb_list)
    ports_ip_conf = {port: {} for port in ports_list}
    DependenciesBase.set_ip_dependency(topology_obj, ports_list, ports_ip_conf, cleanup_list)
    return ports_ip_conf


def ping_validation(dut_engine, lb_list, ports_ip_conf):
    """
    :param dut_engine: an ssh engine
    :param lb_list: a list of tuples of ports connected as loopback
    :param ports_ip_conf: ports ip configuration
    :return: ping result
    """
    for lb in lb_list:
        with allure.step('Send ping validation between ports: {}'.format(lb)):
            src_port = lb[0]
            dst_port = lb[1]
            src_ip = ports_ip_conf[lb[0]]['ip']
            dst_ip = ports_ip_conf[lb[1]]['ip']
            ping_cmd = "ping -I {} {} -c 3".format(src_port, dst_ip)
            logger.info('Sending 3 tagged packets from interface {} with ip {} to interface {} with ip {}'
                        .format(src_port, src_ip, dst_port, dst_ip))
            output = dut_engine.run_cmd(ping_cmd)
            packets_recevied = int(
                re.search(r"\d+\s+packets\s+transmitted,\s+(\d+)\s+received,\s+\d+%\s+packet\s+loss,\s+time\s+\d+ms",
                          output).group(1))
            assert packets_recevied == 3, \
                "Ping validation failed because actual packets received {} != expected packet: 3".format(
                    packets_recevied)


def get_ports_list_from_loopback_tuple_list(lb_list):
    """
    :param lb_list: a list of tuples of ports connected by loopback, i.e. [('Ethernet8', 'Ethernet4'),
    ('Ethernet36', 'Ethernet40'),..]
    :return: a list of the ports ['Ethernet8', 'Ethernet4', 'Ethernet36', 'Ethernet40',..]
    """
    ports_list = []
    for lb_port_1, lb_port_2 in lb_list:
        ports_list.append(lb_port_1)
        ports_list.append(lb_port_2)
    return ports_list


def build_remove_dpb_conf(tested_modes_lb_conf, ports_breakout_modes):
    """
    :return: a dictionary with the breakout mode to remove all the breakout configuration
    i.e,
    {'1x100G[50G,40G,25G,10G]': ('Ethernet212', 'Ethernet216'),
    '1x100G[50G,40G,25G,10G]': ('Ethernet228', 'Ethernet232')}
    """
    remove_breakout_ports_conf = []
    for breakout_mode, lb in tested_modes_lb_conf.items():
        for port in lb:
            default_breakout_mode = ports_breakout_modes[port]['default_breakout_mode']
            remove_breakout_ports_conf.append({default_breakout_mode: [port]})
    return remove_breakout_ports_conf


def cleanup(cleanup_list):
    """
    execute all the functions in the cleanup list
    :return: None
    """
    while cleanup_list:
        cleanup_item = cleanup_list.pop(0)
        func, args = cleanup_item
        func(*args)
