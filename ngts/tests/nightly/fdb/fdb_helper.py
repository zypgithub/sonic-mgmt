import logging
import allure
import copy
from retry import retry

from ngts.helpers.network import generate_mac
from retry.api import retry_call
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from ngts.cli_wrappers.sonic.sonic_mac_clis import SonicMacCli


logger = logging.getLogger()

DUMMY_MAC_PREFIX = "02:11:22:33"
DUMMY_MAC_COUNT = 5
TCPDUMP_FILTER = '{} && (ether src host {})'
DUMMY_MACS = generate_mac(DUMMY_MAC_COUNT)
FDB_AGING_TIME = "30"


def traffic_validation(players, interfaces, interface_data, src_mac, pkt_type, receive_packet_counts):
    """
    This method will validate traffic
    :param players: players fixture
    :param interfaces: interfaces fixture
    :param interface_data: the interface will be used to send and  receive the packets
    :param src_mac: src mac address
    :param pkt_type: packet type fixture
    :param receive_packet_counts: receive packet count list
    """
    with allure.step(f'Host A sends {pkt_type} packet  with src_mac {src_mac} to DUT and check if receiver receives it or not'):
        if pkt_type == "arp_req":
            pkt = f'Ether(src="{src_mac}", dst="FF:FF:FF:FF:FF:FF") / ARP(op=1, hwsrc="{src_mac}", hwdst="00:00:00:00:00:00", psrc="{interface_data["src_ip"]}", pdst="{interface_data["dst_ip"]}")'
            protocol = "arp"
        elif pkt_type == "arp_resp":
            pkt = f'Ether(src="{src_mac}", dst="{interface_data["dst_mac"]}") / ARP(op=2, hwsrc="{src_mac}", hwdst="{interface_data["dst_mac"]}", psrc="{interface_data["src_ip"]}", pdst="{interface_data["dst_ip"]}")'
            protocol = "arp"
        elif pkt_type == "lldp":
            pkt = f'Ether(dst="01:80:c2:00:00:0e", src="{src_mac}", type=0x88cc) / Padding("00000000")'
        elif pkt_type == "icmp":
            pkt = f'Ether(src="{src_mac}", dst="{interface_data["dst_mac"]}")/IP(dst="{interface_data["dst_ip"]}")/ICMP()'
            protocol = "icmp"
        else:
            assert True, f"pkt_type:{pkt_type} is not correct"

        first_receiver_count_index = 0
        if pkt_type == "lldp":  # lldp packet will not be received on hb,so don't validate
            validation = {'sender': interface_data["sender_alias"],
                          'send_args': {'interface': interface_data["sender_interface"],
                                        'packets': pkt, 'count': 1}
                          }
        else:
            validation = {'sender': interface_data["sender_alias"],
                          'send_args': {'interface': interface_data["sender_interface"],
                                        'packets': pkt, 'count': 1},
                          'receivers':
                              [
                                  {'receiver': interface_data["receiver_alias"],
                                   'receive_args': {'interface': interface_data["receiver_interface"],
                                                    'filter': TCPDUMP_FILTER.format(protocol, src_mac),
                                                    'count': receive_packet_counts[first_receiver_count_index],
                                                    'timeout': 20}}
            ]
            }
        if len(receive_packet_counts) == 2:
            second_receiver_count_index = 1
            receiver2 = copy.deepcopy(validation["receivers"][0])
            receiver2["receive_args"]["interface"] = interfaces.hb_dut_2
            receiver2["receive_args"]["count"] = receive_packet_counts[second_receiver_count_index]
            validation["receivers"].append(receiver2)
        logger.info('Sending traffic')
        scapy_checker = ScapyChecker(players, validation)
        retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=10, logger=logger)


def gen_test_interface_data(cli_objects, interfaces, vlan_id):
    """
    The method is to prepare the interface test data
    :param cli_objects: cli_objects object fixture
    :param interfaces: interfaces object fixture
    :param vlan_id:  vlan id
    """
    if vlan_id == "40":
        dst_mac = cli_objects.hb.mac.get_mac_address_for_interface(interfaces.hb_dut_1)
        sender_interface = interfaces.ha_dut_1
        receiver_interface = interfaces.hb_dut_1
        src_ip = "40.0.0.2"
        dst_ip = "40.0.0.3"

    else:
        dst_mac = cli_objects.hb.mac.get_mac_address_for_interface(interfaces.hb_dut_2)
        sender_interface = interfaces.ha_dut_2
        receiver_interface = interfaces.hb_dut_2
        src_ip = "50.0.0.2"
        dst_ip = "50.0.0.3"

    interface_data = {"src_ip": src_ip,
                      "dst_ip": dst_ip,
                      "sender_interface": sender_interface,
                      "receiver_interface": receiver_interface,
                      "vlan_id": vlan_id,
                      "dst_mac": dst_mac,
                      "sender_alias": "ha",
                      "receiver_alias": "hb"}

    return interface_data


@retry(Exception, tries=3, delay=5)
def verify_mac_saved_to_fdb_table(cli_obj, vlan_id, mac, port, fdb_type="dynamic"):
    """
    The method is to verify that mac address is saved to fdb table
    :param cli_obj: dut cli object
    :param vlan_id:  vlan id
    :param mac: mac address
    :param port: port
    :param fdb_type: fdb type (dynamic/static)
    """
    mac_table = cli_obj.mac.parse_mac_table()
    for k, v in mac_table.items():
        if v["Vlan"] == vlan_id and v["MacAddress"].lower() == mac.lower() and v["Port"] == port and v["Type"].lower() == fdb_type:
            return True
    assert False, f"Fdb item: {mac} {vlan_id} {port} {fdb_type} is not saved into fdb table"


@retry(Exception, tries=3, delay=5)
def verify_mac_not_in_fdb_table(cli_obj, vlan_id, mac, port, fdb_type="dynamic"):
    """
    The method is to verify that mac address doesn't exist in fdb table
    :param cli_obj: dut cli object
    :param vlan_id:  vlan id
    :param mac: mac address
    :param port: port
    :param fdb_type: fdb type (dynamic/static)
    """
    mac_table = cli_obj.mac.parse_mac_table()
    for k, v in mac_table.items():
        if v["Vlan"] == vlan_id and v["MacAddress"].lower() == mac.lower() and v["Port"] == port and v["Type"].lower() == fdb_type:
            assert False, f"Fdb item: {mac} {vlan_id} {port} {fdb_type} still exists in fdb table"
    return True
