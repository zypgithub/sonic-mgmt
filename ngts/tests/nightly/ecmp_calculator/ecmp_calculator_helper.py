import logging
import allure
import json
import os
import re
import copy

from jinja2 import Template
from retry.api import retry_call
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from ngts.tests.nightly.ecmp_calculator.constants import DATA_V4, DATA_V6, OUTER_NOLY_PACKET_BASIC_DATA, \
    OUTER_INNER_PACKET_BASIC_DATA, OUTER_NOLY_PACKET_V6_BASIC_DATA, OUTER_INNER_PACKET_V6_BASIC_DATA

ECMP_CALCULATOR_PATH = os.path.dirname(os.path.abspath(__file__))
ECMP_PACKET_JSON_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

logger = logging.getLogger()


class Traffic:

    def __init__(self):
        pass

    def get_ip_type(self, packet_info):
        outer_info = packet_info["outer"]
        if "ipv4" in outer_info:
            ip_type = "ipv4"
        elif "ipv6" in outer_info:
            ip_type = "ipv6"
        else:
            raise Exception("packet format doesn't include ipv4 and ipv6 field")
        return ip_type

    def get_udp_tcp_header(self, sub_packet_info, ip_type):

        proto_key = "proto" if ip_type == "ipv4" else "next_header"
        udp_tcp_header = "TCP" if sub_packet_info[ip_type][proto_key] == 6 else "UDP"

        return udp_tcp_header

    def gen_packet_with_inner_head(self, packet_info):
        outer_info = packet_info["outer"]
        inner_info = packet_info["inner"]

        ip_type = self.get_ip_type(packet_info)

        ip_header = "IP" if ip_type == "ipv4" else "IPv6"

        outer_udp_tcp_header = self.get_udp_tcp_header(outer_info, ip_type)
        inner_udp_tcp_header = self.get_udp_tcp_header(inner_info, ip_type)

        pkt = f"Ether(dst='{outer_info['layer2']['dmac']}', src='{outer_info['layer2']['smac']}') / {ip_header}(dst='{outer_info[ip_type]['dip']}', src='{outer_info[ip_type]['sip']}') / {outer_udp_tcp_header}(dport={outer_info['tcp_udp']['dport']}, sport={outer_info['tcp_udp']['sport']}) / VXLAN(vni={outer_info['vxlan_nvgre']['vni']}) / Ether(dst='{inner_info['layer2']['smac']}', src='{inner_info['layer2']['dmac']}') / {ip_header}(dst='{inner_info[ip_type]['dip']}', src='{inner_info[ip_type]['sip']}') / {inner_udp_tcp_header}(dport={inner_info['tcp_udp']['dport']}, sport={inner_info['tcp_udp']['dport']})"

        logger.info(f"outer_inner packet is :{pkt}")
        return pkt

    def gen_packet_without_inner_head(self, packet_info):
        outer_info = packet_info["outer"]
        ip_type = self.get_ip_type(packet_info)

        ip_header = "IP" if ip_type == "ipv4" else "IPv6"

        outer_udp_tcp_header = self.get_udp_tcp_header(outer_info, ip_type)

        pkt = f"Ether(dst='{outer_info['layer2']['dmac']}', src='{outer_info['layer2']['smac']}') / {ip_header}(dst='{outer_info[ip_type]['dip']}', src='{outer_info[ip_type]['sip']}') / {outer_udp_tcp_header}(dport={outer_info['tcp_udp']['dport']}, sport={outer_info['tcp_udp']['sport']})"

        logger.info(f"outer_only packet is :{pkt}")
        return pkt

    def traffic_validation(self, players, ingress_port, packet_info, packet_type, send_packet_count,
                           receive_packet_info):
        """
        This method will validate traffic
        :param players: players fixture
        :param ingress_port: ingress port
        :param packet_info: packet information which will be sent
        :param packet_type: packet type including outer_inner, outer_only, dot1q_outer_only
        :param send_packet_count: The number sending packet
        :param packet_type: packet type
        :param receive_packet_info: receive packet info, it is a list.Every entry include receiver, interface,
                                    receive packet counter, filter
        """
        with allure.step(f'Verify traffic is sent form the calculated port'):
            if packet_type == "outer_inner":
                pkt = self.gen_packet_with_inner_head(packet_info)
            elif packet_type == "outer_only":
                pkt = self.gen_packet_without_inner_head(packet_info)
            else:
                raise Exception(f"{packet_type} is not correct")
            validation = {'sender': 'ha',
                          'send_args': {'interface': ingress_port,
                                        'packets': pkt, 'count': send_packet_count},
                          'receivers':
                              [
                                  {'receiver': receive_packet_info[i]["receiver"],
                                   'receive_args': {'interface': receive_packet_info[i]['interface'],
                                                    'filter': receive_packet_info[i]['filter'],
                                                    'count': receive_packet_info[i]["counter"],
                                                    'timeout': 20}} for i in range(len(receive_packet_info))
                          ]
                          }

            logger.info('Sending traffic')
            scapy_checker = ScapyChecker(players, validation)
            retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=10, logger=logger)


def load_packet_json(file_name):
    with open(os.path.join(ECMP_PACKET_JSON_TEMPLATE_PATH, file_name)) as f:
        return json.load(f)


def save_packet_json(packet_info, file_name):
    with open(os.path.join(ECMP_PACKET_JSON_TEMPLATE_PATH, file_name), 'w') as f:
        json.dump(f)


def copy_packet_json_to_syncd(dut_engine, file_name, source_file_path=ECMP_PACKET_JSON_TEMPLATE_PATH):
    dut_engine.copy_file(source_file=os.path.join(source_file_path, file_name),
                         dest_file=file_name,
                         file_system='/tmp/',
                         overwrite_file=True,
                         verify_file=False)
    dut_engine.run_cmd(f"docker cp /tmp/{file_name} syncd:/{file_name}")


def calculate_ecmp_egress_port(engine_dut, ingress_port, packet_json_file, vrf=""):
    reg_egress_ports = r"^Egress (port|ports): (?P<ports>.*)"
    vrf_cmd = ''
    if vrf:
        vrf_cmd = f" --vrf {vrf}"
    cmd = f"docker exec syncd bash -c '/usr/bin/ecmp_calc.py -i {ingress_port} -p ./{packet_json_file} {vrf_cmd}'"
    calc_result = engine_dut.run_cmd(cmd)
    res = re.match(reg_egress_ports, calc_result)
    if not res:
        raise Exception(f"Failed to calculate ecmp egress port:{calc_result}")
    ports = res.groupdict()['ports'].strip().split(" ")
    logger.info(f"Calculated egress ports are {ports}")
    return ports


def get_host_name_and_receive_port_as_egress_port(interfaces, egress_port, is_sub_interface=False):
    if is_sub_interface:
        int_host_map = {interfaces.dut_ha_2: {"host": "ha", "receive_port": f"{interfaces.ha_dut_2}.200"},
                        interfaces.dut_hb_1: {"host": "hb", "receive_port": f"{interfaces.hb_dut_1}.300"},
                        interfaces.dut_hb_2: {"host": "hb", "receive_port": f"{interfaces.hb_dut_2}.400"}}
    else:
        int_host_map = {interfaces.dut_ha_2: {"host": "ha", "receive_port": interfaces.ha_dut_2},
                        interfaces.dut_hb_1: {"host": "hb", "receive_port": interfaces.hb_dut_1},
                        interfaces.dut_hb_2: {"host": "hb", "receive_port": interfaces.hb_dut_2}}
    return int_host_map[egress_port]["host"], int_host_map[egress_port]["receive_port"]


def gen_packet_json_file(packet_type, packet_info, packet_json_file_name):
    """
    This method is to generate dhcp config according to the j2 template
    :param packet_type:
    :param packet_info:
    :param packet_json_file_name:
    """
    if packet_info['ip_type'] == 'ipv4':
        file_name = "packet_outer_only.j2" if packet_type == "outer_only" else "packet_outer_inner.j2"
    else:
        file_name = "packet_outer_only_ipv6.j2" if packet_type == "outer_only" else "packet_outer_inner_ipv6.j2"

    logger.info(f"Generate packet json file with template file {file_name} and packet:{packet_info}")
    with open(os.path.join(ECMP_PACKET_JSON_TEMPLATE_PATH, file_name)) as template_file:
        t = Template(template_file.read())

    content = t.render(packet=packet_info)
    logger.info(f"packet json content is {content}")

    logger.info(f"Save packet json to {packet_json_file_name}")
    with open(os.path.join(ECMP_PACKET_JSON_TEMPLATE_PATH, packet_json_file_name), "w", encoding='utf-8') as f:
        f.write(content)


def gen_test_data(field, packet_type, dut_mac):
    test_data_list = []

    if field in DATA_V4:
        for field_value in DATA_V4[field]:
            if packet_type == "outer_only":
                packet = copy.deepcopy(OUTER_NOLY_PACKET_BASIC_DATA)
            elif packet_type == "outer_inner":
                packet = copy.deepcopy(OUTER_INNER_PACKET_BASIC_DATA)
            else:
                raise Exception(f"Packet_type:{packet_type} is not correct ")
            packet[field] = field_value
            packet["outer_dmac"] = dut_mac
            test_data = {"packet": packet, "packet_type": packet_type}
            test_data_list.append(test_data)
    if field in DATA_V6:
        for field_value in DATA_V6[field]:
            if packet_type == "outer_only":
                packet = copy.deepcopy(OUTER_NOLY_PACKET_V6_BASIC_DATA)
            elif packet_type == "outer_inner":
                packet = copy.deepcopy(OUTER_INNER_PACKET_V6_BASIC_DATA)
            else:
                raise Exception(f"Packet_type:{packet_type} is not correct ")
            packet[field] = field_value
            packet["outer_dmac"] = dut_mac
            test_data = {"packet": packet, "packet_type": packet_type}
            test_data_list.append(test_data)
    logger.info(f"Generated test data list are:{test_data_list}")
    return test_data_list
