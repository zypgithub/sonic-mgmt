import logging
import random
import json
import sys
from io import StringIO
import ptf.packet as scapy
from tests.common.reboot import reboot
from tests.common.config_reload import config_reload
from tests.common.helpers.dut_utils import get_available_tech_support_files, get_new_techsupport_files_list, \
    extract_techsupport_tarball_file

logger = logging.getLogger(__name__)


class SRv6():
    uN = 'uN'
    prefix_len = '48'
    pipe_mode = 'pipe'
    uniform_mode = 'uniform'


class SRv6Packets():
    '''
    Define the ipv6 packets used in srv6 test
    Each item was defined with actions and packet type as well as segment left and segment list, destination ip
    '''
    srv6_packets = [
        {
            'action': SRv6.uN,
            'packet_type': 'reduced_srh',
            'srh_seg_left': None,
            'srh_seg_list': None,
            'inner_dscp': None,
            'outer_dscp': None,
            'dst_ipv6': '2001:1000:0100:0200::',
            'exp_dst_ipv6': '2001:1000:0200::',
            'exp_inner_dscp_pipe': None,
            'exp_outer_dscp_uniform': None,
            'exp_srh_seg_left': None,
            'inner_pkt_ver': '4',
            'exp_process_result': 'forward',
        },
        {
            'action': SRv6.uN,
            'packet_type': 'reduced_srh',
            'srh_seg_left': None,
            'srh_seg_list': None,
            'inner_dscp': None,
            'outer_dscp': None,
            'dst_ipv6': '2001:1001:0200:0300::',
            'exp_dst_ipv6': '2001:1001:0300::',
            'exp_inner_dscp_pipe': None,
            'exp_outer_dscp_uniform': None,
            'exp_srh_seg_left': None,
            'inner_pkt_ver': '6',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'one_u_sid',
            'srh_seg_left': 1,
            'inner_dscp': None,
            'outer_dscp': None,
            'srh_seg_list': ['2001:2000:0300:0400:0500:0600::'],
            'dst_ipv6': '2001:2000:0300::',
            'exp_dst_ipv6': '2001:2000:0300:0400:0500:0600::',
            'exp_inner_dscp_pipe': None,
            'exp_outer_dscp_uniform': None,
            'exp_srh_seg_left': 0,
            'inner_pkt_ver': '4',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'one_u_sid',
            'srh_seg_left': 1,
            'inner_dscp': None,
            'outer_dscp': None,
            'srh_seg_list': ['2001:2001:0400:0500:0600::'],
            'dst_ipv6': '2001:2001:0400:0500::',
            'exp_dst_ipv6': '2001:2001:0500::',
            'exp_inner_dscp_pipe': None,
            'exp_outer_dscp_uniform': None,
            'exp_srh_seg_left': 1,
            'inner_pkt_ver': '6',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'two_u_sid',
            'srh_seg_left': 1,
            'inner_dscp': None,
            'outer_dscp': None,
            'srh_seg_list': [
                '2001:3000:0500:0600::',
                '2001:3000:0600:0700:0800:0900:0a00::'
            ],
            'dst_ipv6': '2001:3000:0500::',
            'exp_dst_ipv6': '2001:3000:0500:0600::',
            'exp_inner_dscp_pipe': None,
            'exp_outer_dscp_uniform': None,
            'exp_srh_seg_left': 0,
            'inner_pkt_ver': '4',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'two_u_sid',
            'srh_seg_left': 2,
            'inner_dscp': None,
            'outer_dscp': None,
            'srh_seg_list': [
                '2001:3001:0500::',
                '2001:3000:0600:0700:0800:0900:0a00::'
            ],
            'dst_ipv6': '2001:3001:0600::',
            'exp_dst_ipv6': '2001:3000:0600:0700:0800:0900:0a00::',
            'exp_inner_dscp_pipe': None,
            'exp_outer_dscp_uniform': None,
            'exp_srh_seg_left': 1,
            'inner_pkt_ver': '6',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'reduced_srh',
            'srh_seg_left': None,
            'srh_seg_list': None,
            'inner_dscp': 20,
            'outer_dscp': 40,
            'dst_ipv6': '2001:4000:0700::',
            'exp_dst_ipv6': None,
            'exp_srh_seg_left': None,
            'exp_inner_dscp_pipe': 20,
            'exp_outer_dscp_uniform': 40,
            'inner_pkt_ver': '4',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'one_u_sid',
            'srh_seg_left': 0,
            'inner_dscp': 32,
            'outer_dscp': 31,
            'srh_seg_list': [
                '2001:3001:0500::',
                '2001:3000:0600:0700:0800:0900:0a00::'
            ],
            'dst_ipv6': '2001:4001:0800::',
            'exp_inner_dscp_pipe': 32,
            'exp_outer_dscp_uniform': 31,
            'exp_dst_ipv6': None,
            'exp_srh_seg_left': None,
            'inner_pkt_ver': '4',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'two_u_sid',
            'srh_seg_left': 0,
            'inner_dscp': 2,
            'outer_dscp': 62,
            'srh_seg_list': [
                '2001:3001:0500::',
                '2001:3000:0600:0700:0800:0900:0a00::'
            ],
            'dst_ipv6': '2001:5000:0900::',
            'exp_inner_dscp_pipe': 2,
            'exp_outer_dscp_uniform': 62,
            'exp_dst_ipv6': None,
            'exp_srh_seg_left': None,
            'inner_pkt_ver': '6',
            'exp_process_result': 'forward'
        },
        {
            'action': SRv6.uN,
            'packet_type': 'reduced_srh',
            'srh_seg_left': None,
            'srh_seg_list': None,
            'inner_dscp': 63,
            'outer_dscp': 1,
            'dst_ipv6': '2001:5001:0a00::',
            'exp_inner_dscp_pipe': 63,
            'exp_outer_dscp_uniform': 1,
            'exp_dst_ipv6': None,
            'exp_srh_seg_left': None,
            'inner_pkt_ver': '6',
            'exp_process_result': 'forward'
        }
    ]
    srv6_next_header = {
        scapy.IP: 4,
        scapy.IPv6: 41
    }


class MyLocators():
    my_locator_list = [
        ['locator_1', '2001:1000:100::'],
        ['locator_2', '2001:1001:200::'],
        ['locator_3', '2001:2000:300::'],
        ['locator_4', '2001:2001:400::'],
        ['locator_5', '2001:3000:500::'],
        ['locator_6', '2001:3001:600::'],
        ['locator_7', '2001:4000:700::'],
        ['locator_8', '2001:4001:800::'],
        ['locator_9', '2001:5000:900::'],
        ['locator_10', '2001:5001:a00::']
    ]


class MySIDs(MyLocators):
    TUNNEL_MODE = [SRv6.pipe_mode]
    MY_SID_LIST = [
        [MyLocators.my_locator_list[0][0], MyLocators.my_locator_list[0][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[1][0], MyLocators.my_locator_list[1][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[2][0], MyLocators.my_locator_list[2][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[3][0], MyLocators.my_locator_list[3][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[4][0], MyLocators.my_locator_list[4][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[5][0], MyLocators.my_locator_list[5][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[6][0], MyLocators.my_locator_list[6][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[7][0], MyLocators.my_locator_list[7][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[8][0], MyLocators.my_locator_list[8][1], SRv6.uN, 'default'],
        [MyLocators.my_locator_list[9][0], MyLocators.my_locator_list[9][1], SRv6.uN, 'default']
    ]


def get_default_tunnel_mode(duthost):
    default_tunnel_mode = duthost.shell(
        'redis-cli -n 0 -c HGET "TUNNEL_DECAP_TABLE:IPINIP_V6_TUNNEL" "dscp_mode"')["stdout"]
    return default_tunnel_mode


def create_srv6_locator(duthost,
                        locator_name,
                        prefix,
                        block_len=32,
                        node_len=16,
                        func_len=0,
                        arg_len=0):
    logger.info(f'Configure locator: SRV6_MY_LOCATORS|{locator_name}')
    duthost.shell(
        f'redis-cli -n 4 -c HSET "SRV6_MY_LOCATORS|{locator_name}" '
        f'"prefix" "{prefix}" '
        f'"block_len" "{block_len}" '
        f'"node_len" "{node_len}" '
        f'"func_len" "{func_len}" '
        f'"arg_len" "{arg_len}"')


def validate_srv6_in_appl_db(duthost,
                             block_len=32,
                             node_len=16,
                             func_len=0,
                             arg_len=0):
    for entry in MySIDs.MY_SID_LIST:
        prefix = entry[1]
        action = entry[2]
        try:
            appl_action = duthost.shell(f'sonic-db-cli APPL_DB HGET "SRV6_MY_SID_TABLE:'
                                        f'{block_len}:{node_len}:{func_len}:{arg_len}:{prefix}" action')["stdout"]
            if action.lower() != appl_action:
                logger.error(f"Real action is {appl_action}, but expected action is {action}")
                return False
        except Exception as err:
            logger.error(f"Failed to check SRV6_MY_SID_TABLE - prefix:{prefix} in Application DB")
            raise err
    return True


def del_srv6_locator(duthost, locator_name):
    logger.info(f'Delete locator: SRV6_MY_LOCATORS|{locator_name}')
    duthost.shell(f'redis-cli -n 4 -c DEL "SRV6_MY_LOCATORS|{locator_name}"')


def create_srv6_sid(duthost,
                    locator_name,
                    ip_addr,
                    action=SRv6.uN,
                    decap_vrf='default',
                    decap_dscp_mode=SRv6.uniform_mode):
    logger.info(f'Configure sid: SRV6_MY_SIDS|{locator_name}|{ip_addr}/{SRv6.prefix_len}')
    duthost.shell(
        f'redis-cli -n 4 -c HSET "SRV6_MY_SIDS|{locator_name}|{ip_addr}/{SRv6.prefix_len}" '
        f'"action" "{action}" '
        f'"decap_vrf" "{decap_vrf}" '
        f'"decap_dscp_mode" "{decap_dscp_mode}"')


def del_srv6_sid(duthost, locator_name, ip_addr):
    logger.info(f'Delete sid: SRV6_MY_SIDS|{locator_name}|{ip_addr}/{SRv6.prefix_len}')
    duthost.shell(f'redis-cli -n 4 -c DEL "SRV6_MY_SIDS|{locator_name}|{ip_addr}/{SRv6.prefix_len}"')


def random_reboot(duthost, localhost):
    """
    Randomly choose one action from reload/cold reboot and do the action and wait system recovery
    """
    reboot_type_list = ["reload", "cold"]
    reboot_type = random.choice(reboot_type_list)
    logger.info(f'Randomly choose {reboot_type} from {reboot_type_list}')

    if reboot_type == "reload":
        config_reload(duthost, safe_reload=True, check_intf_up_ports=True)
    else:
        logger.info(f'Do {reboot_type}')
        reboot(duthost, localhost, reboot_type=reboot_type, wait_warmboot_finalizer=True, safe_reboot=True,
               check_intf_up_ports=True, wait_for_bgp=True)


def get_ip_route_nexthops(duthost, destination):
    """
    Get nexthop interfaces for a specific destination
    Args:
        duthost (AnsibleHost): Device Under Test (DUT)
        destination: get the nexthops of this route
    Returns:
        The nexthop interfaces
    """
    output = duthost.shell(f'show ip route {destination} json')['stdout']
    ip_route_json = json.loads(output)
    nexthop_list = []
    for route in ip_route_json[destination]:
        nexthop_list.extend(route["nexthops"])
    nexthops = []
    for nexthop in nexthop_list:
        nexthops.append(nexthop["interfaceName"])
    return nexthops


def dump_packet_detail(pkt):
    _stdout, sys.stdout = sys.stdout, StringIO()
    try:
        pkt.show()
        return sys.stdout.getvalue()
    finally:
        sys.stdout = _stdout


def validate_sai_sdk_dump_files(duthost, techsupport_folder, feature_list=[]):
    """
    Validated that expected SAI dump file available inside in techsupport dump file
    """
    logger.info('Validate SAI dump file is included in the tech-support dump')
    saidump_files_inside_techsupport = \
        duthost.shell(f'ls {techsupport_folder}/sai_sdk_dump')['stdout_lines']
    assert saidump_files_inside_techsupport, 'Expected SAI SDK dump file(folder) not available in techsupport dump'
    for feature in feature_list:
        for sai_sdk_dump in saidump_files_inside_techsupport:
            res = duthost.shell(f'zgrep {feature} {techsupport_folder}/sai_sdk_dump/{sai_sdk_dump}',
                                module_ignore_errors=True)['stdout_lines']
            if res and feature in ''.join(res):
                logger.info(f'Feature {feature} parameter exist in {techsupport_folder}/sai_sdk_dump/{sai_sdk_dump}'
                            f'\n{res}')
                break
        else:
            raise Exception(f'Feature "{feature}" parameter does not exist in sai sdk dump files')


def validate_techsupport_generation(duthost, feature_list=[]):
    """
    Validate sai sdk dump file exist
    """
    available_tech_support_files = get_available_tech_support_files(duthost)
    logger.info('Execute show techsupport command')
    duthost.shell('show techsupport')
    new_techsupport_files_list = get_new_techsupport_files_list(duthost, available_tech_support_files)
    tech_support_file_path = new_techsupport_files_list[0]
    logger.info(f'New tech support file: {new_techsupport_files_list}')
    tech_support_name = tech_support_file_path.split('.')[0].lstrip('/var/dump/')

    try:
        logger.info(f'Doing validation for techsupport : {tech_support_name}')
        techsupport_folder_path = extract_techsupport_tarball_file(duthost, tech_support_file_path)
        logger.info('Checking that expected SAI SDK dump file available in techsupport file')
        validate_sai_sdk_dump_files(duthost, techsupport_folder_path, feature_list)
    finally:
        logger.info(f'Delete {tech_support_file_path}')
        duthost.shell(f'sudo rm -rf {tech_support_file_path}')
