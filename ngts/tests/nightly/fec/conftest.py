import re
import pytest
import logging
import random
from retry.api import retry_call
from ngts.tests.conftest import get_dut_loopbacks
from ngts.constants.constants import AutonegCommandConstants, SonicConst
from ngts.helpers.interface_helpers import get_lb_mutual_speed
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.tests.nightly.auto_negotition.conftest import is_auto_neg_supported_port, ports_spec_compliance

logger = logging.getLogger()


@pytest.fixture(scope='module', autouse=True)
def fec_configuration(topology_obj, interfaces, setup_name, engines, cli_objects, platform_params,
                      tested_lb_dict, tested_lb_dict_for_bug_2705016_flow):
    """
    Pytest fixture which will clean all fec configuration leftover from the dut

    """
    tested_ports = []
    tested_dut_host_ports = [interfaces.dut_ha_1, interfaces.dut_ha_2, interfaces.dut_hb_1]
    tested_ports += get_tested_ports(tested_lb_dict)
    tested_ports += get_tested_ports(tested_lb_dict_for_bug_2705016_flow)
    tested_ports += tested_dut_host_ports
    yield

    logger.info('Starting FEC configuration cleanup')
    cli_objects.dut.general.apply_basic_config(topology_obj, setup_name, platform_params)

    logger.info('FEC cleanup completed')


def get_tested_ports(tested_lb_dict):
    tested_ports = []
    for split_mode, fec_conf_dict in tested_lb_dict.items():
        for fec_mode, lb_list in fec_conf_dict.items():
            for lb in lb_list:
                tested_ports += list(lb)
    return tested_ports


@pytest.fixture(scope='session')
def pci_conf(engines, cli_objects):
    pci_conf = retry_call(cli_objects.dut.chassis.get_pci_conf, fargs=[], tries=6, delay=10)
    return pci_conf


@pytest.fixture(scope='session')
def fec_capability_for_dut_ports(topology_obj, engines, cli_objects, interfaces,
                                 tested_lb_dict, tested_lb_dict_for_bug_2705016_flow, sw_control_ports):
    logger.info("Getting ports fec capabilities")
    fec_capability_for_dut_ports_dict = {}
    ports = get_tested_lb_dict_tested_ports(tested_lb_dict)
    ports += get_tested_lb_dict_tested_ports(tested_lb_dict_for_bug_2705016_flow)
    ports += [interfaces.dut_ha_1, interfaces.dut_ha_2, interfaces.dut_hb_1, interfaces.dut_hb_2]
    if sw_control_ports and is_redmine_issue_active([3886748]):
        ports = [port for port in ports if port not in sw_control_ports]
    for port in ports:
        supported_fec_mode = cli_objects.dut.interface.get_interface_supported_fec_modes(port)
        if supported_fec_mode:
            fec_capability_for_dut_ports_dict[port] = supported_fec_mode
    logger.debug("ports fec capabilities: {}".format(fec_capability_for_dut_ports_dict))
    return fec_capability_for_dut_ports_dict


@pytest.fixture(autouse=True, scope='session')
def tested_lb_dict(topology_obj, split_mode_supported_speeds):
    """
    :param topology_obj: topology object fixture
    :param split_mode_supported_speeds: fixture, dictionary with available breakout options
    :return: a dictionary of loopback list for each split mode on the dut
    {1: [('Ethernet52', 'Ethernet56')],
    2: [('Ethernet12', 'Ethernet16')],
    4: [('Ethernet20', 'Ethernet24')]}
    """
    lb_ports = get_dut_loopbacks(topology_obj)
    if len(lb_ports) < 3:
        pytest.skip(f'Test expected at least 3 loopback ports, but found next ports only: {lb_ports}')
    lb_list_in_split_mode_1 = random.sample(lb_ports, k=3)
    split_2_lb = get_split_loopbacks_set(topology_obj, split_mode=2)
    split_4_lb = get_split_loopbacks_set(topology_obj, split_mode=4)

    tested_lb_dict = {
        1: {
            SonicConst.FEC_RS_MODE: [lb_list_in_split_mode_1[0]],
            SonicConst.FEC_FC_MODE: [lb_list_in_split_mode_1[1]],
            SonicConst.FEC_NONE_MODE: [lb_list_in_split_mode_1[2]]
        }
    }

    if split_2_lb:
        tested_lb_dict[2] = {random.choice(SonicConst.FEC_MODE_LIST): [split_2_lb]}
    if split_4_lb:
        mutual_speeds = get_lb_mutual_speed(split_4_lb, 4, split_mode_supported_speeds)
        if mutual_speeds:
            tested_lb_dict[4] = {random.choice(SonicConst.FEC_MODE_LIST): [split_4_lb]}
    return tested_lb_dict


@pytest.fixture(autouse=True, scope='session')
def tested_lb_dict_for_bug_2705016_flow(topology_obj, split_mode_supported_speeds):
    """
    :param topology_obj: topology object fixture
    :param split_mode_supported_speeds: fixture, dictionary with available breakout options
    :return: a dictionary of loopback list for each split mode on the dut
    {1: [('Ethernet52', 'Ethernet56')],
    2: [('Ethernet12', 'Ethernet16')],
    4: [('Ethernet20', 'Ethernet24')]}
    """
    modes_checked_in_bug_2705016_flow = [SonicConst.FEC_RS_MODE, SonicConst.FEC_NONE_MODE]
    lb_list_in_split_mode_1 = random.sample(get_dut_loopbacks(topology_obj), k=4)
    split_2_lb = get_split_loopbacks_set(topology_obj, split_mode=2)
    split_4_lb = get_split_loopbacks_set(topology_obj, split_mode=4)

    tested_lb_dict = {
        1: {
            SonicConst.FEC_RS_MODE: [lb_list_in_split_mode_1[0], lb_list_in_split_mode_1[1]],
            SonicConst.FEC_NONE_MODE: [lb_list_in_split_mode_1[2], lb_list_in_split_mode_1[3]]
        }
    }

    if split_2_lb:
        tested_lb_dict[2] = {random.choice(modes_checked_in_bug_2705016_flow): [split_2_lb]}
    if split_4_lb:
        mutual_speeds = get_lb_mutual_speed(split_4_lb, 4, split_mode_supported_speeds)
        if mutual_speeds:
            tested_lb_dict[4] = {random.choice(modes_checked_in_bug_2705016_flow): [split_4_lb]}

    return tested_lb_dict


def get_split_loopbacks_set(topology_obj, split_mode):
    """
    Get set with loopbacks which have split by split_mode
    :param topology_obj: topology_obj fixture
    :param split_mode: split mode, could be 2, 4, 8
    :return: example: ('Ethernet0', 'Ethernet1')
    """
    split_lb = ()
    if topology_obj.ports.get(f'dut-lb-splt{split_mode}-p1-1'):
        split_lb = (topology_obj.ports[f'dut-lb-splt{split_mode}-p1-1'],
                    topology_obj.ports[f'dut-lb-splt{split_mode}-p2-1'])
    return split_lb


@pytest.fixture(autouse=True, scope='session')
def tested_dut_to_host_conn(topology_obj, engines, interfaces, cli_objects):
    tested_conn_dict = {
        SonicConst.FEC_NONE_MODE: {"dut_port": interfaces.dut_ha_1,
                                   "host_port": interfaces.ha_dut_1,
                                   "cli": cli_objects.ha,
                                   "engine": engines.ha,
                                   'host': 'ha'
                                   },
        SonicConst.FEC_FC_MODE: {"dut_port": interfaces.dut_ha_2,
                                 "host_port": interfaces.ha_dut_2,
                                 "cli": cli_objects.ha,
                                 "engine": engines.ha,
                                 'host': 'ha'
                                 },
        SonicConst.FEC_RS_MODE: {"dut_port": interfaces.dut_hb_1,
                                 "host_port": interfaces.hb_dut_1,
                                 "cli": cli_objects.hb,
                                 "engine": engines.hb,
                                 'host': 'hb'
                                 }
    }
    return tested_conn_dict


@pytest.fixture(autouse=True, scope='session')
def dut_ports_default_mlxlink_configuration(is_simx, platform_params, chip_type, engines, cli_objects, interfaces,
                                            tested_lb_dict, fec_modes_speed_support,
                                            tested_lb_dict_for_bug_2705016_flow, pci_conf, dut_ports_number_dict,
                                            sw_control_ports):
    """
    on simx setups this information can not be taken from mlxlink cmd because this command is not supported on simx
    (There is no FW), so instead the dict will be default info generated by get_basic_fec_mode_dict function.
    :return: a dictionary with basic FEC mode and interface type on all ports
    i.e,
    { "Ethernet0" : { "FEC": "rs" ,"Type": "CR4" }, ...}
    """
    logger.info("Getting port basic fec configuration")
    if is_simx:
        dut_ports_basic_mlxlink_dict = get_basic_fec_mode_dict(cli_objects, fec_modes_speed_support)
    else:
        dut_ports_basic_mlxlink_dict = get_dut_ports_basic_mlxlink_dict(cli_objects, interfaces,
                                                                        tested_lb_dict,
                                                                        tested_lb_dict_for_bug_2705016_flow,
                                                                        pci_conf, dut_ports_number_dict,
                                                                        sw_control_ports)
    return dut_ports_basic_mlxlink_dict


@pytest.fixture(autouse=True, scope='session')
def mlxlink_supported_speeds(dut_ports_default_mlxlink_configuration):
    """
    The function parses the supported speed of each port from the output of mlxlink command
    :param dut_ports_default_mlxlink_configuration:  dut_ports_default_mlxlink_configuration fixture
    :return: A dictionary, mapping between each port to a sub-dictionary that contains the interface types supported
     by every speed the cable supports, i.e. {'Ethernet136': {'400G': {'CR8'}, '100G': {'CR2'}}}
    """
    interface_type_per_split = {1: "CR", 2: "CR2", 4: "CR4", 8: "CR8"}
    mlxlink_cable_fec_modes_speed_support = dict()
    mlxlink_split_mode_pattern = re.compile(r"_(\d+)X$")  # Matching mlxlink speeds with split mode like 400G_2X
    split_factor_group_ind = 1
    mlxlink_speed_ind = 0
    for port, port_mlxlink_data in dut_ports_default_mlxlink_configuration.items():
        mlxlink_cable_fec_modes_speed_support[port] = dict()
        speed_options = port_mlxlink_data[AutonegCommandConstants.CABLE_SPEED]
        for speed in speed_options:
            match = mlxlink_split_mode_pattern.search(speed)
            if match:
                split_factor = int(match.group(split_factor_group_ind))
                base_speed = speed.split('_')[mlxlink_speed_ind]
                interface_types_matched = {split_interface_type for split, split_interface_type in
                                           interface_type_per_split.items() if split_factor >= split}
            else:  # Speed patterns like 50G without a split should be added to all interface_types
                interface_types_matched = set(interface_type_per_split.values())
                base_speed = speed
            mlxlink_cable_fec_modes_speed_support[port].setdefault(base_speed, set()).update(
                interface_types_matched)
    return mlxlink_cable_fec_modes_speed_support


def get_tested_lb_dict_tested_ports(tested_lb_dict):
    tested_ports_list = []
    for split_mode, fec_mode_tested_lb_dict in tested_lb_dict.items():
        for fec_mode, lb_list in fec_mode_tested_lb_dict.items():
            for lb in lb_list:
                for port in lb:
                    tested_ports_list.append(port)
    return tested_ports_list


def get_dut_ports_basic_mlxlink_dict(cli_objects, interfaces, tested_lb_dict,
                                     tested_lb_dict_for_bug_2705016_flow, pci_conf, dut_ports_number_dict,
                                     sw_control_ports):
    dut_ports_basic_mlxlink_dict = {}
    ports = get_tested_lb_dict_tested_ports(tested_lb_dict)
    ports += get_tested_lb_dict_tested_ports(tested_lb_dict_for_bug_2705016_flow)
    ports += [interfaces.dut_ha_1, interfaces.dut_ha_2, interfaces.dut_hb_1, interfaces.dut_hb_2]

    if sw_control_ports and is_redmine_issue_active([3886748]):
        ports = [port for port in ports if port not in sw_control_ports]

    for port in ports:
        port_number = dut_ports_number_dict[port]
        mlxlink_conf = retry_call(cli_objects.dut.interface.parse_port_mlxlink_status,
                                  fargs=[pci_conf, port_number],
                                  tries=6, delay=10, logger=logger)
        port_fec_mode = mlxlink_conf[AutonegCommandConstants.FEC]
        port_width_mode = int(mlxlink_conf[AutonegCommandConstants.WIDTH])
        port_supported_speeds = mlxlink_conf[AutonegCommandConstants.CABLE_SPEED]
        dut_ports_basic_mlxlink_dict[port] = {
            AutonegCommandConstants.FEC: port_fec_mode,
            AutonegCommandConstants.TYPE: "CR{}".format(port_width_mode if port_width_mode > 1 else ""),
            AutonegCommandConstants.CABLE_SPEED: port_supported_speeds
        }
    logger.debug("port basic fec configuration: {}".format(dut_ports_basic_mlxlink_dict))
    return dut_ports_basic_mlxlink_dict


def get_ports_split_mode_dict(interfaces_status):
    """
    :param interfaces_status: {'Ethernet0': {'Lanes': '0,1,2,3,4,5,6,7', 'Speed': '100G', 'MTU': '9100',
        'FEC': 'N/A', 'Alias': 'etp1', 'Vlan': 'routed', 'Oper': 'up', 'Admin': 'up', 'Type': 'QSFP28 or later',
        'Asym PFC': 'N/A'}, 'Ethernet8': {'Lanes'.......
    :return: a dictionary of ports split mode
    { "Ethernet0": 1, "Ethernet4": 1, "Ethernet8": 1, "Ethernet12": 2, "Ethernet14": 2, "Ethernet16": 2,..}
    """
    ports_lanes_dict = {}
    for port, port_status in interfaces_status.items():
        lanes = port_status['Lanes'].split(sep=",")
        ports_lanes_dict[port] = len(lanes)
    max_lanes = max(ports_lanes_dict.values())
    ports_split_mode_dict = {}
    for port, port_lane_num in ports_lanes_dict.items():
        ports_split_mode_dict[port] = int(max_lanes / port_lane_num)
    return ports_split_mode_dict


@pytest.fixture(autouse=True, scope='session')
def host_speed_type_support(topology_obj, engines, cli_objects, interfaces, hosts_ports):
    """
    Method which getting supported speed-type dictionary per host interface
    :return: a dictionary
    for example:
    {'enp4s0f0': {'40G': ['CR4', 'LR4', 'SR4'], '10G': ['CR'], '25G': ['CR', 'SR'], '1G': ['KX'],
     '50G': ['CR2'], '100G': ['SR4', 'CR4', 'LR4_ER4']}}
    """
    host_speed_type_support = {}
    for host_engine, host_info in hosts_ports.items():
        host_cli, host_ports = host_info
        for port in host_ports:
            port_ethtool_status = host_cli.interface.parse_show_interface_ethtool_status(port)
            port_supported_types = port_ethtool_status["supported types"]
            host_speed_type_support.update({port: {}})
            for speed_type in port_supported_types:
                split_speed_type = speed_type.split('BASE-')
                sup_speed = split_speed_type[0]
                sup_type = split_speed_type[1]
                if 'KR' in sup_type:
                    sup_type = sup_type.replace('KR', 'CR')  # same support
                if sup_speed in host_speed_type_support[port]:
                    host_speed_type_support[port][sup_speed].append(sup_type)
                else:
                    host_speed_type_support[port].update({sup_speed: [sup_type]})
                host_speed_type_support[port][sup_speed] = list(set(host_speed_type_support[port][sup_speed]))
    return host_speed_type_support


def get_basic_fec_mode_dict(cli_objects, fec_modes_speed_support):
    """
    on simx setups this information can not be taken from mlxlink cmd because this command is not supported on simx
    (There is no FW), so instead the dict will be default info generated by get_basic_fec_mode_dict function.

    "rs" is the default FEC mode because it is supported on all maximum capability
    speed which configured on setup with basic configuration.
    (on SN3700 port with 4 lane max capability speed is 200G)
    :return: a dictionary with basic FEC mode, interface type and cable_supported_speeds on all ports on simx setup
    i.e,
    { "Ethernet0" : { "FEC": "rs" ,"Type": "CR4" }, ...}
    """
    basic_fec_mode_dict = {}
    interfaces_status = cli_objects.dut.interface.parse_interfaces_status()
    fec_modes_speed_support = fec_modes_speed_support
    ports_split_mode_dict = get_ports_split_mode_dict(interfaces_status)
    default_fec_mode = SonicConst.FEC_RS_MODE
    default_fec_mode_speed_support = fec_modes_speed_support[default_fec_mode]
    interface_type_index = 0
    for port, port_split_mode in ports_split_mode_dict.items():
        port_speed = interfaces_status[port]['Speed']
        basic_fec_mode_dict[port] = {
            AutonegCommandConstants.FEC: default_fec_mode,
            AutonegCommandConstants.TYPE:
                default_fec_mode_speed_support[port_split_mode][port_speed][interface_type_index],
            AutonegCommandConstants.CABLE_SPEED: default_fec_mode_speed_support[port_split_mode]
        }
    return basic_fec_mode_dict


def get_lb_mutual_fec_modes(lb, fec_capability_for_dut_ports):
    port_supported_fec_modes = []
    for port in lb:
        port_supported_fec_modes.append(set(fec_capability_for_dut_ports[port]))
    return list(set.intersection(*port_supported_fec_modes))


@pytest.fixture(scope='session')
def ports_support_autoneg(topology_obj, ports_spec_compliance, is_simx):
    """
    The function returns a set containing ports that support autoneg
    :param: topology_obj: topology_obj fixture
    :param: ports_spec_compliance: ports_spec_compliance fixture
    :param: is_simx: is_simx fixture
    :returns: A set containing ports that support autoneg, i.e. {"Ethernet0", "Ethernet8", ...}.
    """
    ports_supporting_autoneg = set()
    if is_simx:
        return ports_supporting_autoneg
    ports_data = topology_obj.players_all_ports['dut']
    for port in ports_data:
        if is_auto_neg_supported_port(port, ports_spec_compliance, used_in_auto_neg_tests=False):
            ports_supporting_autoneg.add(port)
    return ports_supporting_autoneg
