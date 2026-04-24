import logging
import allure
import os
import struct

from retry.api import retry_call
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from retry import retry
from scapy.all import Ether, IP, IPv6, UDP, ICMP, wrpcap
from ngts.common.checkers import is_ver1_greater_or_equal_ver2

logger = logging.getLogger()

BTH_OPCODE_NAK_TYPE_AMP = {"0x0d/0x0d": "'RC', 'RDMA_READ_RESPONSE_FIRST'",
                           "0x0f/0x0f": "'RC', 'RDMA_READ_RESPONSE_LAST'",
                           "0x10/0x10": "'RC', 'RDMA_READ_RESPONSE_ONLY'",
                           "0x11/0x11": "'RC', 'ACKNOWLEDGE'",
                           "0x12/0x12": "'RC', 'ATOMIC_ACKNOWLEDGE'",
                           "0x4d/0x4d": "'RD', 'RDMA_READ_RESPONSE_FIRST'",
                           "0x4f/0x4f": "'RD', 'RDMA_READ_RESPONSE_LAST'",
                           "0x50/0x50": "'RD', 'RDMA_READ_RESPONSE_ONLY'",
                           "0x51/0x51": "'RD', 'ACKNOWLEDGE'",
                           "0x52/0x52": "'RD', 'ATOMIC_ACKNOWLEDGE'",
                           "0xad/0xad": "'XRC', 'RDMA_READ_RESPONSE_FIRST'",
                           "0xaf/0xaf": "'XRC', 'RDMA_READ_RESPONSE_LAST'",
                           "0xb0/0xb0": "'XRC', 'RDMA_READ_RESPONSE_ONLY'",
                           "0xb1/0xb1": "'XRC', 'ACKNOWLEDGE'",
                           "0xb2/0xb2": "'XRC', 'ATOMIC_ACKNOWLEDGE'"}


def copy_apply_rocev2_acl_config(dut_engine, file_name, file_path):
    dut_engine.copy_file(source_file=os.path.join(file_path, file_name),
                         dest_file=file_name,
                         file_system='/tmp/',
                         overwrite_file=True,
                         verify_file=False)
    dut_engine.run_cmd(f"sudo config load /tmp/{file_name} -y")


def remove_rocev2_acl_rule_and_talbe(topology_obj, alc_table_list, acl_table_type_list):
    cli_obj = topology_obj.players['dut']['cli']
    with allure.step("Delete rocev2 acl rule config"):
        cli_obj.acl.delete_config()
    with allure.step("Delete rocev2 acl table"):
        for acl_table in alc_table_list:
            cli_obj.acl.remove_table(acl_table)
    with allure.step("Delete rocev2 acl table type"):
        for acl_table_type in acl_table_type_list:
            cli_obj.acl.remove_table_type(acl_table_type)


def get_ip_header_and_src_ip(alc_rule):
    ip_header = "IP" if alc_rule["src_type"] == "SRC_IP" else "IPv6"
    src_ip = alc_rule['src_ip'].split("/")[0]
    return ip_header, src_ip


def gen_rocev2_packet(alc_rule, dst_mac, dst_ip):
    ip_header, src_ip = get_ip_header_and_src_ip(alc_rule)
    src_mac = 'b0:50:90:a0:30:00'
    scenario = alc_rule["scenario"]

    # aeth include 4 bytes, we just take care the first one
    aeth = struct.pack('=BBBB', 0x60, 0x00, 0x00, 0x00)
    # rdeth include 4 bytes, they can be filled with any data
    rdeth = struct.pack('=BBBB', 0x01, 0x01, 0x01, 0x01)
    bth = gen_bth(scenario, alc_rule)

    packet_prefix = f"Ether(dst='{dst_mac}', src='{src_mac}')/{ip_header}(dst='{dst_ip}', src='{src_ip}')/UDP(sport=56238, dport=4791)"

    if "bth_only" == scenario:
        pkt = f"{packet_prefix}/{bth}"
    elif scenario in ["bth_aeth_together", "aeth_only"]:
        pkt = f"{packet_prefix}/{bth}/{aeth}"
    elif "bth_aeth_together_random" == scenario:
        bth_code = BTH_OPCODE_NAK_TYPE_AMP[alc_rule['bth_opcode']]
        if "'RD'" in bth_code:
            pkt = f"{packet_prefix}/{bth}/{rdeth}/{aeth}"
        else:
            pkt = f"{packet_prefix}/{bth}/{aeth}"

    logger.info(f"alc rule is {alc_rule}\n, packet is :{pkt}")
    return eval(pkt)


def gen_bth(scenario, alc_rule):
    """
    This method will generate bth packet. bth including 12 bytes, we just take care the first byte,
    for the other 11 bytes they can filled with any data
    :param scenario: test scenario
    :param alc_rule: alc_rule
    """
    if "bth_only" == scenario:
        bth = struct.pack('=BBBBBBBBBBBB', 0x80, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00)
    elif scenario in ["bth_aeth_together", "aeth_only"]:
        bth = struct.pack('=BBBBBBBBBBBB', 0x11, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00)
    elif "bth_aeth_together_random" == scenario:
        bth_code = int(alc_rule['bth_opcode'].split('/')[0], 16)
        bth = struct.pack('=BBBBBBBBBBBB', bth_code, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00)
    logger.info(f"scenario:{scenario}, alc_rule:{alc_rule}, bth:{bth}")
    return bth


def gen_non_rocev2_packet(alc_rule, dst_mac, dst_ip):
    ip_header, src_ip = get_ip_header_and_src_ip(alc_rule)
    src_mac = 'c0:50:90:a0:30:00'

    pkt = f"Ether(src='{src_mac}', dst='{dst_mac}')/{ip_header}(dst='{dst_ip}',src='{src_ip}')/ICMP()"
    logger.info(f"alc rule is {alc_rule}\n, packet is :{pkt}")
    return eval(pkt)


def traffic_validation(players, send_pcap_info_dict, send_packet_count):
    """
    This method will validate traffic
    :param players: players fixture
    :param send_packet_count: The number sending packet
    :param send_pcap_info_dict: pcap file name set
    """
    for pcap_file_name, sender_and_send_port in send_pcap_info_dict.items():
        with allure.step(f'Send {send_packet_count} {pcap_file_name} from {sender_and_send_port["sender"]} on {sender_and_send_port["send_port"]}'):
            validation = {'sender': sender_and_send_port["sender"],
                          'send_args': {'interface': sender_and_send_port["send_port"],
                                        'pcap': pcap_file_name,
                                        'count': send_packet_count}
                          }

            logger.info('Sending rocev2 traffic')
            scapy_checker = ScapyChecker(players, validation)
            retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=10, logger=logger)
            if os.path.exists(pcap_file_name):
                logger.info(f"Remove existing file {pcap_file_name}")
                os.remove(pcap_file_name)


def gen_pcap_file(sender, send_port, acl_rule, dst_mac, dst_ip, traffic_type, port_type, send_pcap_info_dict):
    """
    This method is to generate pcap file with the packet
    """
    pcap_file_name = f'/tmp/{sender}_{send_port}_{port_type}_{traffic_type}.pcap'
    with allure.step(f'write packet into {pcap_file_name} '):
        if traffic_type == "match":
            pkt = gen_rocev2_packet(acl_rule, dst_mac, dst_ip)
        else:
            pkt = gen_non_rocev2_packet(acl_rule, dst_mac, dst_ip)
        wrpcap(pcap_file_name, pkt, append=True, sync=True)
    if pcap_file_name not in send_pcap_info_dict:
        send_pcap_info_dict[pcap_file_name] = {}
        send_pcap_info_dict[pcap_file_name]["sender"] = sender
        send_pcap_info_dict[pcap_file_name]["send_port"] = send_port


@retry(Exception, tries=12, delay=5)
def verify_acl_rule_counter(topology_obj, send_packet_count, rocev2_acl_rule_list):
    show_acl_rule_dict = topology_obj.players['dut']['cli'].acl.show_and_parse_acl_rules_counters('')
    for acl_rule in rocev2_acl_rule_list:
        assert acl_rule["table_name"] in show_acl_rule_dict, f'{acl_rule["table_name"]}, {show_acl_rule_dict}'
        for show_acl_rule in show_acl_rule_dict[acl_rule["table_name"]]:
            if acl_rule["name"] == show_acl_rule['RULE NAME']:
                assert acl_rule["priority"] == show_acl_rule['PRIO'], \
                    f'expected:{acl_rule["priority"]}, actual: {show_acl_rule["PRIO"]}'
                assert send_packet_count == int(show_acl_rule['PACKETS COUNT']), \
                    f'expected:{send_packet_count}, actual: {show_acl_rule["PACKETS COUNT"]}'


def is_support_rocev2_acl_counter_feature(cli_objects, is_simx, sonic_branch):
    logger.info(f"sonic branch: {sonic_branch}, is_simx:{is_simx}")
    if sonic_branch in ["202211", "202205"]:
        return False

    sai_version = cli_objects.dut.general.get_sai_version()
    base_sai_version = "2211.23.1.60"
    logger.info(f'sai_version: {sai_version}, base sai_version:{base_sai_version}')
    if not sai_version or not is_ver1_greater_or_equal_ver2(sai_version, base_sai_version):
        logger.info(f'sai_version not support recev2 acl counter feature')
        return False

    if is_simx:
        simx_version, simx_chipe_type = cli_objects.dut.general.get_simx_version_and_chip_type()
        simx_version = simx_version.replace("-", ".")
        if simx_chipe_type and simx_version:
            base_simx_version = "5.1.1057" if simx_chipe_type == "Spectrum-1" else '23.4.0005'
            return is_ver1_greater_or_equal_ver2(simx_version, base_simx_version)
        else:
            return False
    return True
