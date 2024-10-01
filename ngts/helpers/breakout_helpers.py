import re

from retry.api import retry_call

import ngts.helpers.json_file_helper as json_file_helper
from ngts.cli_util.cli_constants import SonicConstant
from ngts.constants.constants import AutonegCommandConstants, ConfigDbJsonConst
from ngts.helpers.interface_helpers import get_alias_number, get_speed_in_G_format


def get_breakout_mode_supported_speed_list(breakout_mode):
    """
    this function will return the speed that will be configured on the port be the breakout mode.
    :param breakout_mode: i,e. '4x25G[10G,1G]'
    :return: return 25G
    """
    support_speed_list = []
    support_speed_list.append(re.search(r"\dx(\d+G|\d+)", breakout_mode).group(1))
    support_speed_list.extend(re.search(r"\dx(\d+G|\d+)\[([\d+G,]+|[\d,]+)\]", breakout_mode).group(2).split(','))
    return support_speed_list


def get_breakout_mode_by_speed_conf(breakout_modes_list, port_speed):
    """
    :param breakout_modes_list: i.e, ['4x25G[10G,1G]', '4x1G']
    :param port_speed: i.e, 25G
    :return: the breakout mode that configures the port_speed, in this case '4x25G[10G,1G]'
    """
    for breakout_mode in breakout_modes_list:
        brk_mode_configured_speed = get_breakout_mode_supported_speed_list(breakout_mode)
        if port_speed in brk_mode_configured_speed:
            return breakout_mode
    raise Exception("Didn't find breakout mode that configured speed: {} in breakout_modes_list: {}"
                    .format(port_speed, breakout_modes_list))


def get_all_split_ports_parents(config_db_json, topology_obj):
    """
    this function will return a list of the ports that have breakout
    configuration configured on them and the split number the port was split(breakout) to.
    for example, if port 'Ethernet196' is breakout to 2.
    now we have 2 ports 'Ethernet196' and 'Ethernet198', but 'Ethernet196' is the port the breakout was configured on.
    so it's the parent port of the split.
    :param config_db_json: a json object of the switch config_db.json file
    :return: a list of tuples of first split port and their split number
    for example, [('Ethernet196', 2), ('Ethernet200', 2), ('Ethernet204', 4), ('Ethernet208', 4)]
    """
    dut_first_split_port_info = []
    port_info_dict = config_db_json.get(ConfigDbJsonConst.PORT)
    if port_info_dict:
        for port, port_info in port_info_dict.items():
            port_alias = port_info[ConfigDbJsonConst.ALIAS]
            is_first_split_port = bool(re.match(r'etp\d+a', port_alias))
            if is_first_split_port and port in topology_obj.ports.values():
                split_num = get_split_number(config_db_json, port_alias)
                dut_first_split_port_info.append((port, split_num))
    return dut_first_split_port_info


def get_all_unsplit_ports(config_db_json, topology_obj):
    unsplit_ports = []
    port_info_dict = config_db_json.get(ConfigDbJsonConst.PORT, [])
    for port, port_info in port_info_dict.items():
        port_alias = port_info[ConfigDbJsonConst.ALIAS]
        is_unsplit_port = bool(re.match(r'etp\d+$', port_alias))
        if is_unsplit_port and port in topology_obj.ports.values():
            unsplit_ports.append(port)
    return unsplit_ports


def get_split_number(config_db_json, port_alias):
    """
    return the port split number, as the port was split to 2/4/8.
    :param config_db_json: a json object of the switch config_db.json file
    :param port_alias: the sonic port alias, e.g. 'etp1'
    :return: the number the port was split to, 2/4/8.
    """
    all_aliases = [port_info['alias'] for port_info in config_db_json[ConfigDbJsonConst.PORT].values()]
    port_alias_number = get_alias_number(port_alias)
    all_aliases_of_split_port = list(filter(lambda alias: re.search("etp{}[a-z]$".format(port_alias_number), alias),
                                            all_aliases))
    split_number = len(all_aliases_of_split_port)
    return split_number


def get_port_current_breakout_mode(config_db_json, port, split_num, parsed_platform_json_by_breakout_modes):
    port_speed = get_speed_in_G_format(config_db_json['PORT'][port]['speed'])
    if config_db_json.get('BREAKOUT_CFG'):
        if 'G' not in config_db_json['BREAKOUT_CFG'][port]['brkout_mode']:  # if RJ45 port
            port_speed = config_db_json['PORT'][port]['speed']
    supported_brk_modes = parsed_platform_json_by_breakout_modes[port][split_num]
    return get_breakout_mode_by_speed_conf(supported_brk_modes, port_speed)


def get_split_mode_supported_speeds(breakout_modes):
    """
    :param breakout_modes: a list of breakout modes, i.e. ['1x100G[50G,40G,25G,10G]',
    '2x50G[40G,25G,10G]', '4x25G[10G]']
    :return: a dictionary of supported speed for every split number option, i.e,
    {1: {'100G', '50G', '40G', '10G', '25G'},
    2: {'40G', '10G', '25G', '50G'},
    4: {'10G', '25G'}}
    """
    split_mode_supported_speeds = {1: set(), 2: set(), 4: set(), 8: set()}
    breakout_port_by_modes = get_speed_option_by_breakout_modes(breakout_modes)
    for breakout_mode, supported_speeds_list in breakout_port_by_modes.items():
        breakout_num, _ = breakout_mode.split("x")
        split_mode_supported_speeds[int(breakout_num)].update(supported_speeds_list)
    return split_mode_supported_speeds


def get_split_mode_supported_breakout_modes(breakout_modes):
    """
    :param breakout_modes: a list of breakout modes, i.e. ['1x100G[50G,40G,25G,10G]',
    '2x50G[40G,25G,10G]', '4x25G[10G]']
    :return: a dictionary of supported breakout mode for every split number option, i.e,
    {1:{'1x100G[50G,40G,25G,10G]'},
    2: {'2x50G[40G,25G,10G]'},
    4: {'4x25G[10G]'}
    """
    split_mode_supported_breakout_modes = {1: set(), 2: set(), 4: set(), 8: set()}
    for breakout_mode in breakout_modes:
        breakout_pattern = r"(\dx\d+G\[[\d*G,]*\]|\dx\d+G|\dx\d+\[[\d+,]*\])"
        if re.search(breakout_pattern, breakout_mode):
            breakout_num, _ = breakout_mode.split("x")
            split_mode_supported_breakout_modes[int(breakout_num)].add(breakout_mode)
    return split_mode_supported_breakout_modes


def get_dut_breakout_modes(dut_engine, cli_object, ports_to_exclude=None):
    """
    parsing platform breakout options and config_db.json breakout configuration.
    :return: a dictionary with available breakout options on all dut ports
    i.e,
       { 'Ethernet0' :{'index': ['1', '1', '1', '1'],
                       'lanes': ['0', '1', '2', '3'],
                       'alias_at_lanes': ['etp1a', ' etp1b', ' etp1c', ' etp1d'],
                       'breakout_modes': ['1x200G[100G,50G,40G,25G,10G,1G]',
                                          '2x100G[50G,40G,25G,10G,1G]',
                                          '4x50G[40G,25G,10G,1G]'],
                       'breakout_port_by_modes': {'1x200G[100G,50G,40G,25G,10G,1G]': {'Ethernet0': '200G'},
                                                  '2x100G[50G,40G,25G,10G,1G]': {'Ethernet0': '100G[',
                                                                                 'Ethernet2': '100G'},
                                                  '4x50G[40G,25G,10G,1G]': {'Ethernet0': '50G',
                                                                            'Ethernet1': '50G',
                                                                            'Ethernet2': '50G',
                                                                            'Ethernet3': '50G'}},
                       'default_breakout_mode': '1x200G[100G,50G,40G,25G,10G,1G]'}, .....}

    """
    platform_json = json_file_helper.get_platform_json(dut_engine, cli_object)
    config_db_json = json_file_helper.get_config_db(dut_engine)
    breakout_modes_by_ports = parse_platform_json(platform_json, config_db_json, cli_object, ports_to_exclude)
    # TODO: Currently SONiC doesn't support 8x breakout in DPB, remove this when 8x breakout is supported
    for _, breakout_data in breakout_modes_by_ports.items():
        breakout_modes = breakout_data['breakout_modes']
        for mode in breakout_modes:
            if '8x' in mode:
                breakout_modes.remove(mode)
                break
    return breakout_modes_by_ports


def convert_cable_speeds(cable_speeds, lanes_count):
    """
    Converts supported cable speeds from mlxlink command output format to breakout modes format
    :param cable_speeds: a list of strings representing speed options, i.e ['400G_8X', '100G_2X', '50G', '40G', '25G']
    :param lanes_count: number of lanes of port, i.e. 8
    :return: a list of strings representing supported breakout modes
    i.e. ['1x400G', '4x100G', '50G', '40G', '25G']
    """
    supported_speeds = []
    for cable_speed in cable_speeds:
        if '_' in cable_speed:
            speed, lanes_per_interface = cable_speed.split('_')
            # converts cable_speed from {speed}_{lanes-used}X to {interfaces_per_port}x{speed}
            virtual_ports_count = lanes_count // int(lanes_per_interface[:-1])
            supported_speeds.append(f'{virtual_ports_count}x{speed}')
        else:
            supported_speeds.append(cable_speed)
    return supported_speeds


def filter_breakout_modes(breakout_modes, cable_speeds):
    """
    Filter breakout modes list accordingly to cable supported speeds
    Breakout modes that have no cable supported speeds are ignored
    :param breakout_modes: an iterable of strings representing breakout mode, i.e. ['1x100G[50G,40G,25G,10G]',
    '2x50G[40G,25G,10G]', '4x25G[10G]']
    :param cable_speeds: a list of strings representing cable supported speeds, i.e ['1x400G', '4x100G', '50G', '40G']
    :return: list of filtered breakout modes, i.e. ['1x100G[50G,40G,25G,10G]', '2x50G[40G,25G,10G]']
    """
    filtered_breakout_modes = []
    for breakout_mode in breakout_modes:
        lanes_count = breakout_mode[:breakout_mode.index('x')]
        speed_list = breakout_mode[breakout_mode.index('x') + 1:].replace('[', ',').replace(']', '').split(',')
        if any(f'{lanes_count}x{speed}' in cable_speeds or speed in cable_speeds for speed in speed_list):
            filtered_breakout_modes.append(breakout_mode)
    return filtered_breakout_modes


def _mlxlink_get_cable_speeds(cli_object, pci_conf, port_number):
    """
    Parses mlxlink command output and in case Admin status is equal to 'Polling' raise an Exception
    Otherwise returns cable speeds supported

    :param cli_object: cli_object fixture
    :param str pci_conf: pci configuration, f.e. /dev/mst/mt53100_pciconf0
    :param str port_number: port number, f.e. '35'
    :return str: cable supported speeds
    """
    mlxlink_actual_conf = cli_object.interface.parse_port_mlxlink_status(pci_conf, port_number)
    if mlxlink_actual_conf[AutonegCommandConstants.ADMIN] == 'Polling':
        raise Exception("Port is still in polling state, failed to retrieve cable speeds")
    return mlxlink_actual_conf[AutonegCommandConstants.CABLE_SPEED]


def get_breakout_modes(cli_object, port_name, port_dict, parsed_port_dict):
    """
    Parses mlxlink command output for port and check cable supported speeds,
    then filters out port breakout modes retrieved from platform.json by comparing to supported speeds
    :param cli_object: cli_object
    :param port_name: a string representing the name of a port, i.e 'Ethernet136'
    :param port_dict: a dictionary with breakout info for a port,
    i.e.
        {'index': "20,20,20,20,20,20,20,20",
        'lanes': "152,153,154,155,156,157,158,159",
        'breakout_modes': {
            '1x400G[200G,100G,50G,40G,25G,10G,1G]': ['etp20'],
            '2x200G[100G,50G,40G,25G,10G,1G]': ['etp20a', 'etp20b'],
            '4x100G[50G,25G,10G,1G]': ['etp20a', 'etp20b', 'etp20c', 'etp20d'],
            '4x25G(4)[10G,1G]': ['etp20a', 'etp20b', 'etp20c', 'etp20d']
        },
        'default_brkout_mode': '1x400G[200G,100G,50G,40G,25G,10G,1G]',
        'Current Breakout Mode': '1x400G[200G,100G,50G,40G,25G,10G,1G]',
        'child ports': 'Ethernet152',
        'child port speeds': '400G'
    }
    :param parsed_port_dict: a dictionary representing parsed breakout info for a port,
    i.e.
        {'index': ['20', '20', '20', '20', '20', '20', '20', '20',],
        'lanes': ['152', '153', '154', '155', '156', '157', '158', '159']}
    :return: list of strings representing supported breakout modes
    """
    ports_aliases_dict = cli_object.interface.parse_ports_aliases_on_sonic()
    pci_conf = cli_object.chassis.get_pci_conf()
    # handle case, when port is listed in platform.json, but is missing on dut
    if port_name not in ports_aliases_dict:
        return []
    port_number = get_alias_number(ports_aliases_dict[port_name])
    cable_speeds = retry_call(_mlxlink_get_cable_speeds, fargs=[cli_object, pci_conf, port_number], tries=5,
                              delay=10, logger=None)
    converted_cable_speeds = convert_cable_speeds(cable_speeds, len(parsed_port_dict[SonicConstant.LANES]))
    return filter_breakout_modes(port_dict[SonicConstant.BREAKOUT_MODES].keys(), converted_cable_speeds)


def parse_platform_json(platform_json_obj, config_db_json, cli_object, ports_to_exclude=None):
    """
    parsing platform breakout options and config_db.json breakout configuration.
    :param platform_json_obj: a json object of platform.json file
    :param config_db_json: a json object of config_db.json file
    :param cli_object: cli_object
    :param ports_to_exclude: list of ports to be excluded from dpb test case
    :return: a dictionary with available breakout options on all dut ports
    i.e,
       { 'Ethernet0' :{'index': ['1', '1', '1', '1'],
                       'lanes': ['0', '1', '2', '3'],
                       'alias_at_lanes': ['etp1a', ' etp1b', ' etp1c', ' etp1d'],
                       'breakout_modes': ['1x200G[100G,50G,40G,25G,10G,1G]',
                                          '2x100G[50G,40G,25G,10G,1G]',
                                          '4x50G[40G,25G,10G,1G]'],
                       'breakout_port_by_modes': {'1x200G[100G,50G,40G,25G,10G,1G]': {'Ethernet0': '200G'},
                                                  '2x100G[50G,40G,25G,10G,1G]': {'Ethernet0': '100G',
                                                                                 'Ethernet2': '100G'},
                                                  '4x50G[40G,25G,10G,1G]': {'Ethernet0': '50G',
                                                                            'Ethernet1': '50G',
                                                                            'Ethernet2': '50G',
                                                                            'Ethernet3': '50G'}},
                       'default_breakout_mode': '1x200G[100G,50G,40G,25G,10G,1G]'}, .....}
    """
    ports_breakout_info = {}
    for port_name, port_dict in platform_json_obj["interfaces"].items():
        if ports_to_exclude and port_name in ports_to_exclude:
            continue
        parsed_port_dict = dict()
        parsed_port_dict[SonicConstant.INDEX] = port_dict[SonicConstant.INDEX].split(",")
        parsed_port_dict[SonicConstant.LANES] = port_dict[SonicConstant.LANES].split(",")
        breakout_modes = get_breakout_modes(cli_object, port_name, port_dict, parsed_port_dict)
        parsed_port_dict[SonicConstant.BREAKOUT_MODES] = breakout_modes
        parsed_port_dict['breakout_port_by_modes'] = get_breakout_port_by_modes(breakout_modes,
                                                                                parsed_port_dict
                                                                                [SonicConstant.LANES])
        parsed_port_dict['speeds_by_modes'] = get_speed_option_by_breakout_modes(breakout_modes)
        port_breakout_cfg = config_db_json[SonicConstant.BREAKOUT_CFG].get(port_name)
        if port_breakout_cfg:
            parsed_port_dict['default_breakout_mode'] = port_breakout_cfg[SonicConstant.BRKOUT_MODE]
        ports_breakout_info[port_name] = parsed_port_dict
    return ports_breakout_info


@staticmethod
def get_default_breakout_mode(engine_dut, cli_object, port_list):
    """
    get the default port breakout mode for port list
    :param engine_dut: ssh engine object
    :param cli_object: dut cli object
    :param port_list:port list
    :return: dictionary of the breakout mode
    """
    ports_breakout_modes = get_dut_breakout_modes(engine_dut, cli_object)
    default_ports_breakout_conf = {}
    for port in port_list:
        default_breakout_mode = ports_breakout_modes[port]['default_breakout_mode']
        if default_breakout_mode in default_ports_breakout_conf.keys():
            default_ports_breakout_conf[default_breakout_mode].append(port)
        else:
            default_ports_breakout_conf[default_breakout_mode] = [port]
    return default_ports_breakout_conf


@staticmethod
def get_breakout_mode(engine_dut, cli_object, port_list):
    """
    get the breakout mode for port list
    :param engine_dut: ssh engine object
    :param cli_object: dut cli object
    :param port_list:port list
    :return: dictionary of the breakout mode
    """
    breakout_mode = {}
    port_breakout_modes = get_dut_breakout_modes(engine_dut, cli_object)
    for port in port_list:
        supported_breakout_modes = port_breakout_modes[port]['breakout_modes']
        breakout_mode[port] = supported_breakout_modes[-1]
    return breakout_mode


def get_speed_option_by_breakout_modes(breakout_modes):
    """
    :param breakout_modes: a list of breakout modes supported by a port, i.e,
    ['1x200G[100G,50G,40G,25G,10G,1G]', '2x100G[50G,40G,25G,10G,1G]', '4x50G[40G,25G,10G,1G]',  '4x25G(4)[10G,1G]']
    :return: a dictionary with speed configuration available for each breakout modes,
    i.e,
    {'1x200G[100G,50G,40G,25G,10G,1G]': [100G,50G,40G,25G,10G,1G],
    '2x100G[50G,40G,25G,10G,1G]': [50G,40G,25G,10G,1G],
    '4x50G[40G,25G,10G,1G]': [40G,25G,10G,1G],
    '4x25G(4)[10G,1G]': [25G, 10G, 1G]}
    """
    breakout_port_by_modes = {}
    for breakout_mode in breakout_modes:
        breakout_pattern = r"\dx\d+G(?:\(\d\))?[[\d*G,]*\]|\dx\d+\[[\d*G,]*\]"
        if re.search(breakout_pattern, breakout_mode):
            breakout_num, speed_conf = breakout_mode.split("x")
            speed, _ = speed_conf.split('[')
            speed = re.sub(r"\(\d\)", "", speed)
            speeds_list_pattern = r"\[(.*)\]"
            speeds_list_str = re.search(speeds_list_pattern, speed_conf).group(1)
            speeds_list = speeds_list_str.split(sep=',')
            speeds_list.append(speed)
            breakout_port_by_modes[breakout_mode] = speeds_list
    return breakout_port_by_modes


def get_breakout_port_by_modes(breakout_modes, lanes):
    """
    :param breakout_modes: a list of breakout modes supported by a port, i.e,
    ['1x200G[100G,50G,40G,25G,10G,1G]', '2x100G[50G,40G,25G,10G,1G]', '4x50G[40G,25G,10G,1G]']
    :param lanes: a list with port lanes, i.e, for port Ethernet0 the list will be [0, 1, 2, 3]
    :return: a dictionary with ports and speed configuration result for each breakout modes,
    i.e,
    {'1x200G[100G,50G,40G,25G,10G,1G]': {'Ethernet0': '200G'},
    '2x100G[50G,40G,25G,10G,1G]': {'Ethernet0': '100G',
                                   'Ethernet2': '100G'},
    '4x50G[40G,25G,10G,1G]': {'Ethernet0': '50G', 'Ethernet1': '50G',
                              'Ethernet2': '50G', 'Ethernet3': '50G'}}
    """
    breakout_port_by_modes = {}
    for breakout_mode in breakout_modes:
        breakout_pattern = r"\dx\d+G\[[\d*G,]*\]|\dx\d+G"
        if re.search(breakout_pattern, breakout_mode):
            breakout_num, speed_conf = breakout_mode.split("x")
            speed_value = r"(\d+G)\[[\d*G,]*\]|(\d+G)"
            speed = re.match(speed_value, speed_conf).group(1)
            num_lanes_after_breakout = len(lanes) // int(breakout_num)
            lanes_after_breakout = [lanes[idx:idx + num_lanes_after_breakout]
                                    for idx in range(0, len(lanes), num_lanes_after_breakout)]
            breakout_port = {'Ethernet{}'.format(lanes[0]): speed for lanes in lanes_after_breakout}
            breakout_port_by_modes[breakout_mode] = breakout_port
    return breakout_port_by_modes
