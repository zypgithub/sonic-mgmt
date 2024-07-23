import logging
import pytest
import os
import re
import json

from ngts.constants.constants import InterfacesTypeConstants, PlatformTypesConstants, SonicConst, CableComplianceConst
from ngts.tests.conftest import get_dut_loopbacks, get_dut_host_loopbacks
from ngts.helpers.interface_helpers import get_lb_mutual_speed, speed_string_to_int_in_mb
from ngts.cli_util.cli_parsers import parse_show_interfaces_transceiver_eeprom

logger = logging.getLogger()


@pytest.fixture(scope='module', autouse=True)
def auto_neg_configuration(topology_obj, setup_name, engines, cli_objects, platform_params):
    """
    Pytest fixture which will clean all fec configuration leftover from the dut

    """

    yield

    logger.info('Starting Auto Neg configuration cleanup')
    cli_objects.dut.general.apply_basic_config(topology_obj, setup_name, platform_params)

    logger.info('Auto Neg cleanup completed')


@pytest.fixture(scope='session')
def tested_lb_dict(topology_obj, split_mode_supported_speeds, ports_spec_compliance):
    """
    :param topology_obj: topology object fixture
    :param ports_spec_compliance: ports_spec_compliance fixture
    :return: a dictionary of loopback list for each split mode on the dut
    {1: [('Ethernet52', 'Ethernet56')],
    2: [('Ethernet12', 'Ethernet16')],
    4: [('Ethernet20', 'Ethernet24')]}
    """
    tested_lb_dict = {1: []
                      }
    update_split_2_if_possible(topology_obj, tested_lb_dict, ports_spec_compliance)
    update_split_4_if_possible(topology_obj, split_mode_supported_speeds, tested_lb_dict, ports_spec_compliance)
    update_split_8_if_possible(topology_obj, split_mode_supported_speeds, tested_lb_dict, ports_spec_compliance)
    split_mode = 1
    dut_lbs = list(filter(lambda lb: is_auto_neg_supported_lb(lb, ports_spec_compliance),
                          get_dut_loopbacks(topology_obj)))
    tested_lb_dict[split_mode].append(get_dut_lb_with_max_capability(dut_lbs, split_mode_supported_speeds))
    logger.info("Tests will run on the following ports :\n{}".format(tested_lb_dict))
    return tested_lb_dict


def get_dut_lb_with_max_capability(dut_lbs, split_mode_supported_speeds):
    return max(dut_lbs,
               key=lambda lb: speed_string_to_int_in_mb(max(get_lb_mutual_speed(lb, 1, split_mode_supported_speeds),
                                                            key=speed_string_to_int_in_mb)))


@pytest.fixture(scope='session')
def ports_lanes_dict(interfaces_status_dict, interfaces, cli_objects):
    ports_lanes_dict = {}
    for port, port_status in interfaces_status_dict.items():
        lanes = port_status['Lanes'].split(sep=",")
        ports_lanes_dict[port] = len(lanes)
    ports_lanes_dict[interfaces.ha_dut_1] = 4
    return ports_lanes_dict


def update_split_4_if_possible(topology_obj, split_mode_supported_speeds, tested_lb_dict, ports_spec_compliance):
    """
    :param topology_obj: topology object fixture
    :param split_mode_supported_speeds: a dictionary with available speed options for each split mode on all setup ports
    :param tested_lb_dict: a dictionary of loopback list for each split mode on the dut
    :param ports_spec_compliance: ports_spec_compliance fixture
    :return: Update loopback with split 4 configuration only in cases were there are mutual speeds available,
    for example, parsing of platform.json file for panther will not return speeds option for port with split 4,
    because this breakout mode is not supported on panther
    """
    if topology_obj.ports.get('dut-lb-splt4-p1-1') and topology_obj.ports.get('dut-lb-splt4-p2-1'):
        split_4_lb = (topology_obj.ports['dut-lb-splt4-p1-1'], topology_obj.ports['dut-lb-splt4-p2-1'])
        mutual_speeds = get_lb_mutual_speed(split_4_lb, 4, split_mode_supported_speeds)
        if mutual_speeds and is_auto_neg_supported_lb(split_4_lb, ports_spec_compliance):
            tested_lb_dict.update({4: [split_4_lb]})


def update_split_2_if_possible(topology_obj, tested_lb_dict, ports_spec_compliance):
    """
    :param topology_obj: topology object fixture
    :param tested_lb_dict: a dictionary of loopback list for each split mode on the dut
    :param ports_spec_compliance: ports_spec_compliance fixture
    :return: Update loopback with split 2 configuration only in cases were there is such a loopback in setup
    (some simx setups don't have split ports as part of the configuration)
    """
    if topology_obj.ports.get('dut-lb-splt2-p1-1') and topology_obj.ports.get('dut-lb-splt2-p2-1'):
        split_2_lb = (topology_obj.ports['dut-lb-splt2-p1-1'], topology_obj.ports['dut-lb-splt2-p2-1'])
        if is_auto_neg_supported_lb(split_2_lb, ports_spec_compliance):
            tested_lb_dict.update({2: [split_2_lb]})


def update_split_8_if_possible(topology_obj, split_mode_supported_speeds, tested_lb_dict, ports_spec_compliance):
    """
    :param topology_obj: topology object fixture
    :param split_mode_supported_speeds: a dictionary with available speed options for each split mode on all setup ports
    :param tested_lb_dict: a dictionary of loopback list for each split mode on the dut
    :param ports_spec_compliance: ports_spec_compliance fixture
    :return: Update loopback with split 8 configuration only in cases were there are mutual speeds available,
    for example, parsing of platform.json file for panther will not return speeds option for port with split 8,
    because this breakout mode is not supported on panther
    """
    if topology_obj.ports.get('dut-lb-splt8-p1-1') and topology_obj.ports.get('dut-lb-splt8-p2-1'):
        split_8_lb = (topology_obj.ports['dut-lb-splt8-p1-1'], topology_obj.ports['dut-lb-splt8-p2-1'])
        mutual_speeds = get_lb_mutual_speed(split_8_lb, 8, split_mode_supported_speeds)
        if mutual_speeds and is_auto_neg_supported_lb(split_8_lb, ports_spec_compliance):
            tested_lb_dict.update({8: [split_8_lb]})


@pytest.fixture(scope='session')
def tested_dut_host_lb_dict(topology_obj, interfaces, split_mode_supported_speeds, ports_spec_compliance):
    """
    :param topology_obj: topology object fixture
    :param ports_spec_compliance - ports_spec_compliance fixture
    :return: a dictionary of loopback of dut - host ports connectivity
    {1: [('Ethernet64', 'enp66s0f0')]}
    """
    tested_dut_host_lb_dict = dict()
    for dut_host_lb in get_dut_host_loopbacks(interfaces):
        if is_auto_neg_supported_port(dut_host_lb[0], ports_spec_compliance):
            tested_dut_host_lb_dict[1] = [dut_host_lb]
            break
    if not tested_dut_host_lb_dict:
        pytest.skip("Skipping test as there are no auto-neg supporting dut_host loopbacks")
    logger.info("Test will run on the following ports:\n{}".format(tested_dut_host_lb_dict))
    return tested_dut_host_lb_dict


@pytest.fixture(scope='session')
def interfaces_types_dict(engines, platform_params, chip_type):
    """

    """
    platform = platform_params.filtered_platform
    logger.info("platform is: {}".format(platform))
    if chip_type == "SPC":
        if platform.upper() == PlatformTypesConstants.FILTERED_PLATFORM_PANTHER:
            if is_aoc_cable(engines):
                supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC.get(
                    platform.upper()).get("PANTHER_AOC")
            else:
                supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC['default']
        else:
            supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC.get(
                platform.upper())
        if not supported_speed:
            supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC['default']

    elif chip_type == "SPC2":
        supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC2[platform.upper()]
    elif chip_type == "SPC3":
        supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC3[platform.upper()]
    elif chip_type == "SPC4":
        supported_speed = {}
    else:
        raise AssertionError("Chip type {} is unrecognized".format(chip_type))
    return supported_speed


@pytest.fixture(scope='session')
def interfaces_types_port_dict(engines, cli_objects, platform_params, chip_type, ports_aliases_dict, interfaces,
                               interfaces_types_dict):
    """
    get the supported interface type with the sdk api
    example of the return value of the get_supported_intf_type.py:
    {'1': {'CR': ['1G', '10G', '25G', '50G'], 'CR2': ['50G', '100G'], 'CR4': ['40G', '100G', '200G']},
     '2': {'CR': ['1G', '10G', '25G', '50G'], 'CR2': ['50G', '100G'], 'CR4': ['40G', '100G', '200G']},
     '3': {'CR': ['1G', '10G', '25G', '50G'], 'CR2': ['50G', '100G'], 'CR4': ['40G', '100G', '200G']},
     '4': {'CR': ['1G', '10G', '25G', '50G'], 'CR2': ['50G', '100G']},
     '5': {'CR': ['1G', '10G', '25G', '50G'], 'CR2': ['50G', '100G']},
     '6': {'CR': ['1G', '10G', '25G', '50G']},
     '7': {'CR': ['1G', '10G', '25G', '50G']},
     '8': {'CR': ['1G', '10G', '25G', '50G'], 'CR2': ['50G', '100G'], 'CR4': ['40G', '100G', '200G']},
     ...
     }
    """
    platform = platform_params.filtered_platform
    supported_speed = {}
    # For SPC1, the sdk dose not support to get port rate cap .
    if chip_type == "SPC":
        if platform.upper() == PlatformTypesConstants.FILTERED_PLATFORM_PANTHER:
            if is_aoc_cable(engines):
                port_supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC.get(
                    platform.upper()).get("PANTHER_AOC")
            else:
                port_supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC['default']
        else:
            port_supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC.get(
                platform.upper())
        if not port_supported_speed:
            port_supported_speed = InterfacesTypeConstants.INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC['default']
        for intf, alias in ports_aliases_dict.items():
            supported_speed[intf] = port_supported_speed
    else:
        base_dir = os.path.dirname(os.path.realpath(__file__))
        get_port_cap_file_name = "get_port_supported_intf_type.py"
        get_port_cap_file = os.path.join(base_dir, f"{get_port_cap_file_name}")
        engines.dut.copy_file(source_file=get_port_cap_file,
                              file_system='/tmp',
                              dest_file=get_port_cap_file_name,
                              overwrite_file=True, )
        cmd_copy_file_to_syncd = f"docker cp /tmp/{get_port_cap_file_name} syncd:/"
        engines.dut.run_cmd(cmd_copy_file_to_syncd)

        port_cap = engines.dut.run_cmd(f'docker exec syncd bash -c "python3 /{get_port_cap_file_name}"')
        port_cap = json.loads(port_cap.replace("\'", "\""))

        for intf, alias in ports_aliases_dict.items():
            regex_pattern = r"etp(\d+)\w*"
            label_port = re.match(regex_pattern, alias).group(1)
            supported_intf_type = port_cap[label_port]
            supported_speed[intf] = {}
            for intf_type, speeds in supported_intf_type.items():
                if not intf_type[2:]:
                    lane_num = 1
                else:
                    lane_num = int(intf_type[2:])
                supported_speed[intf][lane_num] = {intf_type: speeds}
    supported_speed[interfaces.ha_dut_1] = supported_speed[interfaces.dut_ha_1]
    return supported_speed


@pytest.fixture(autouse=True, scope='session')
def ports_aliases_dict(engines, cli_objects):
    """
    :param engines: setup engines fixture
    :param cli_objects: cli objects fixture
    :return: a dictionary of the port and it's sonic alias on the dut
    i.e, {'Ethernet0': 'etp1', ..
          'Ethernet60': 'etp16'}
    """
    return cli_objects.dut.interface.parse_ports_aliases_on_sonic()


def get_interface_cable_width(type_string, expected_speed=None):
    """
    :param type_string: a interface type string 'CR'
    :param expected_speed: if the expected speed is 400G the width of the cable will be 8,
                           although the cable type will be CR4 - this is a sonic limitation
    :return: int width  value, i.e, '1'
    more examples,
    'CR' -> 1
    'CR2' -> 2
    'CR4' -> 4
    """
    width = 1
    match = re.search(r"\w+(\d+)", type_string)
    if match:
        width = int(match.group(1))
    return width


def get_matched_types(lane_number, speed_list, types_dict):
    """
    :param lane_number: the port number of lanes i.e, 1,2,4 etc
    :param speed_list: set of speeds, {'40G', '25G', '50G', '10G'}
    :param types_dict: a dictionary of port supported types based on
    the port number of lanes
    i.e,
    {
        SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G']},
        SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G']},
        SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G']},
    }
    :return: a set of types that match speeds in the list, i.e, {'CR', 'CR4'}
    """
    matched_types = set()
    lane_option = list(filter(lambda lane_option: lane_option <= lane_number, [1, 2, 4, 8]))
    for speed in speed_list:
        for lane in lane_option:
            if lane in types_dict:
                for interface_type, supported_speeds in types_dict[lane].items():
                    if speed in supported_speeds:
                        matched_types.add(interface_type)
    return matched_types


def convert_speeds_to_mb_format(speeds_list):
    """
    :param speeds_list: a list of speeds,  ['40G', '10G', '50G']
    :return: return a string of speeds configuration in string list format, i.e, '40000,10000,50000'
    """
    speeds_in_mb_format = list(map(lambda speed: str(speed_string_to_int_in_mb(speed)), speeds_list))
    return ",".join(speeds_in_mb_format)


@pytest.fixture(autouse=False)
def expected_auto_neg_loganalyzer_exceptions(request, cli_objects, loganalyzer):
    """
    expanding the ignore list of the loganalyzer for these tests because of reboot.
    :param request: pytest build-in
    :param loganalyzer: loganalyzer utility fixture
    :return: None
    """
    dut_hostname = cli_objects.dut.chassis.get_hostname()
    if loganalyzer:
        expected_regex_list = \
            loganalyzer[dut_hostname].parse_regexp_file(src=str(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                             "expected_negative_auto_neg_logs.txt")))
        loganalyzer[dut_hostname].expect_regex.extend(expected_regex_list)

    yield

    # If test skipped - remove expected regexps from loganalyzer.expect_regex list
    if request.node.rep_setup.skipped:
        if loganalyzer:
            expected_regex_list = \
                loganalyzer[dut_hostname].parse_regexp_file(
                    src=str(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "expected_negative_auto_neg_logs.txt")))

            for regexp in expected_regex_list:
                loganalyzer[dut_hostname].expect_regex.remove(regexp)


def get_all_advertised_speeds_sorted_string(speeds_list, physical_interface_type=None):
    """
    :param speeds_list: a list of speeds ['10000', '50000']
    :param physical_interface_type: physical interface type
    :return: return a string of sorted speeds configuration in M/G format, i.e, "10G,50G"
    """
    speeds_list = sorted(speeds_list, key=lambda speed_str: int(speed_str))
    if physical_interface_type == 'RJ45':
        speeds_in_str_format = list(map(lambda speed: "{}M".format(int(speed)), speeds_list))
    else:
        speeds_in_str_format = list(map(lambda speed: "{}G".format(int(int(speed) / 1000)), speeds_list))
    return ",".join(speeds_in_str_format)


def is_aoc_cable(engines):
    extended_spc = engines.dut.run_cmd(
        "show interfaces transceiver eeprom Ethernet0 | grep \"Extended Specification Compliance\"")
    if re.search("AOC", extended_spc):
        return True
    return False


@pytest.fixture(scope='session')
def ports_spec_compliance(topology_obj, engines, cable_compliance_info, is_simx):
    """
    The function parses the information of the command show interfaces transceiver eeprom to a dictionary that contains
    the compliance eeprom data for each port.
    :param topology_obj: topology_obj fixture
    :param engines: engines fixture
    :param cable_compliance_info: cable_compliance_info fixture
    :param is_simx: is_simx fixture
    :return: A dictionary mapping each port to a tuple of 2 values. The first value is the specification compliance
    type (extended or not) and the second value is the actual specification compliance value.
    It should be noted that eeprom_info_per_port contains the entire eeprom output of a port,
    so if it is needed for future usage, the function can be adjusted to return it as well.
    Example for entry in the dictionary - {"Ethernet8": ("Specification compliance", "passive_copper_media_interface")}
    """
    # If the platform is simx, we do not have port compliance and cannot parse it
    # Currently, auto-neg tests do not run on simx setups but when using this fixture in fec, we need to know if it's
    # simx
    if is_simx:
        return None
    eeprom_info_per_port = parse_show_interfaces_transceiver_eeprom(cable_compliance_info)
    ports_compliance = dict()
    for port_name, port_info in eeprom_info_per_port.items():
        # RJ45 cables shouldn't be skipped on all auto-neg cases despite not having eeprom data
        if port_info['Status'] == CableComplianceConst.UNDETECTED_RJ45_EEPROM_MSG:
            ports_compliance[port_name] = CableComplianceConst.DEFAULT_CABLE_COMPLIANCE_TUPLE
        else:
            ports_compliance[port_name] = parse_port_compliance(port_info)
    return ports_compliance


def parse_port_compliance(port_info):
    """
    The function parses the port compliance information from the output of "show interfaces transceiver eeprom" command
    :param port_info:  The port information, as it appears in the output of "show interfaces transceiver eeprom"
    :return: A tuple of 2 values. The first value is the specification compliance
    type (extended or not) and the second value is the actual specification compliance value.
    Example for return value - ("Specification compliance", "passive_copper_media_interface")
    """
    port_compliance = get_port_compliance(port_info)
    if isinstance(port_compliance, str):
        port_compliance_type = CableComplianceConst.SPEC_COMPLIANCE_PREFIX
    else:  # This means the compliance is a dict
        port_compliance_type, port_compliance = parse_port_compliance_dict(port_compliance)
    return port_compliance_type, port_compliance


def get_port_compliance(port_info):
    """
    The function returns the port compliance.
    :param port_info: The port information, as it appears in the output of "show interfaces transceiver eeprom"
    :return: The port compliance, which can either be a single value or a dictionary.
    """
    if CableComplianceConst.SPEC_COMPLIANCE_PREFIX in port_info.keys():
        port_compliance = port_info[CableComplianceConst.SPEC_COMPLIANCE_PREFIX]
    else:
        # In the case the port compliance is a dictionary, the function parse_show_interfaces_transceiver_eeprom parses
        # it with the ':'
        port_compliance = port_info[f'{CableComplianceConst.SPEC_COMPLIANCE_PREFIX}:']
    return port_compliance


def parse_port_compliance_dict(port_compliance_dict):
    """
    The function parses the port compliance in the case it is a dictionary.
    :param port_compliance_dict: The port compliance dictionary, as it appears in "show interfaces transceiver eeprom"
    :return: A tuple of 2 values, containing the port compliance type and port compliance value. Supported types can be
    seen in the keys of CableComplianceConst.SUPPORTED_SPECIFICATION_COMPLIANCE
    """
    port_compliance_type = None
    port_compliance = None
    if CableComplianceConst.EXTENDED_SPEC_COMPLIANCE_PREFIX in port_compliance_dict.keys():
        port_compliance_type = CableComplianceConst.EXTENDED_SPEC_COMPLIANCE_PREFIX
        port_compliance = port_compliance_dict[port_compliance_type]
    elif CableComplianceConst.SFP_COMPLIANCE in port_compliance_dict.keys():
        port_compliance_type = CableComplianceConst.SFP_COMPLIANCE
        port_compliance = port_compliance_dict[port_compliance_type]
    return port_compliance_type, port_compliance


def is_auto_neg_supported_port(port, compliance_info_per_port, used_in_auto_neg_tests=True):
    """
    The function returns True if the port supports auto-neg and false otherwise.
    :param port: port to check
    :param compliance_info_per_port: output of compliance_info_per_port fixture
    :param used_in_auto_neg_tests: a boolean stating if the function is called from the auto-neg test (and thus port is skipped)
    :return: True if the port supports auto-neg and False otherwise
    """
    port_supports_auto_neg = False
    port_spec_type, port_spec_value = compliance_info_per_port[port]

    matched_supported_regex = any(re.search(regex_pattern, port_spec_value) for regex_pattern in
                                  CableComplianceConst.SUPPORTED_SPECIFICATION_COMPLIANCE[port_spec_type])
    if matched_supported_regex:
        logger.debug(f"Supported port is - {port}. {port_spec_type} : {port_spec_value}\n")
        port_supports_auto_neg = True
    if not port_supports_auto_neg:
        matched_unsupported_regex = any(re.search(regex_pattern, port_spec_value) for regex_pattern in
                                        CableComplianceConst.UNSUPPORTED_SPECIFICATION_COMPLIANCE[port_spec_type])
        if matched_unsupported_regex:
            if used_in_auto_neg_tests:
                logger.warning(f"Tests will not run on port {port} because of unsupported cable type - "
                               f"{port_spec_type} : {port_spec_value}\n")
        else:
            raise AssertionError(f"Test failed because port {port} has unknown {port_spec_type} : {port_spec_value}\n"
                                 f"Check if the cable should support auto-negotiation and update test accordingly\n")
    return port_supports_auto_neg


def is_auto_neg_supported_lb(lb, compliance_info_per_port):
    """
    The function returns True if the both ports of the lb support auto-neg and false otherwise.
    :param lb: lb to check
    :param compliance_info_per_port: output of compliance_info_per_port fixture
    :return: True if the lb supports auto-neg and False otherwise
    """
    return all(is_auto_neg_supported_port(port, compliance_info_per_port) for port in lb)
