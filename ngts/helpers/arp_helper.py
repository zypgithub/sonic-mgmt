import logging
import allure

from retry.api import retry_call
from ngts.cli_wrappers.sonic.sonic_arp_clis import SonicArpCli
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker

logger = logging.getLogger()

TCPDUMP_ARP_FILTER = 'arp && (ether dst host {}) '
INTERFACE_TYPE_LIST = ["ethernet", "vlan", "portchannel"]


def clear_dynamic_arp_table_and_check_the_specified_arp_entry_deleted(cli_obj, ip):
    """
    This method is to clear the dynamic arp table and check some arp entry is removed or not
    :param cli_obj: cli_obj object
    :param ip: ip address for the specified arp entry
    """
    cli_obj.arp.clear_arp()
    retry_call(verify_arp_entry_not_in_ip_neigh_table, fargs=[cli_obj, ip], tries=3, delay=10, logger=logger)


def verify_arp_entry_in_arp_table(cli_obj, ip, mac, iface, vlan):
    """
    This method is to verify if arp entry is added into the arp table
    :param cli_obj: cli_obj object
    :param ip: ip address
    :param mac: mac address
    :param iface: interface such as ethernet, PortChannel Id
    :param vlan: vlan Id
    """
    arp_table = cli_obj.arp.show_arp_table()
    if arp_table:
        if ip in arp_table:
            assert arp_table[ip][
                "MacAddress"].lower() == mac.lower(), "Actual ARP mac: {} not match expected ARP mac: {} " \
                "for ip: {}".format(arp_table[ip]["MacAddress"], mac, ip)
            assert arp_table[ip][
                "Iface"] == iface, "Actual ARP Iface: {} not match expected ARP Iface: {} for ip: {}".format(
                arp_table[ip]["Iface"], iface, ip)
            assert arp_table[ip][
                "Vlan"] == vlan, "Actual ARP vlan: {} not match expected ARP vlan:{} for ip: {}".format(
                arp_table[ip]["Vlan"], vlan, ip)
            return True

    raise Exception('Arp table is empty')


def verify_arp_entry_not_in_ip_neigh_table(cli_obj, ip):
    """
    This method is to verify if arp entry is not in the ip neigh table
    :param cli_obj: cli_obj object
    :param ip: ip address
    """
    ip_neigh_table = cli_obj.ip.show_ip_neigh()
    for arp_entry in ip_neigh_table.split("\n"):
        arp_ip, *_ = arp_entry.split()
        if arp_ip == ip:
            raise Exception('Arp entry {} exists in the ip neigh table'.format(arp_ip))


def arp_request_traffic_validation(players, interface_data, dst_mac, receive_packet_count, is_garp=False):
    """
    This method will validate the arp request traffic
    :param players: players
    :param interface_data: the interface will be used to receiver the packets
    :param dst_mac: src mac address
    :param receive_packet_count: receive packet count
    :param is_garp: Bool, true means sending garp, otherwise send not garp
    """
    with allure.step('Host A sends ARP request to DUT and check that receives the arp response'):
        if is_garp:
            dst_ip = interface_data["host_ip"]
        else:
            dst_ip = interface_data["dut_ip"]
        pkt_arp_req = 'Ether(src="{}", dst="{}") / ARP(' \
                      'op=1, hwsrc="{}", hwdst="00:00:00:00:00:00", psrc="{}", pdst="{}")'.format(
                          interface_data["host_mac"], dst_mac, interface_data["host_mac"], interface_data["host_ip"], dst_ip)

        validation = {'sender': interface_data["host_alias"],
                      'send_args': {'interface': interface_data["host_interface"],
                                    'packets': pkt_arp_req, 'count': 1},
                      'receivers':
                          [
                              {'receiver': interface_data["host_alias"],
                               'receive_args': {'interface': interface_data["host_interface"],
                                                'filter': TCPDUMP_ARP_FILTER.format(interface_data["host_mac"]),
                                                'count': receive_packet_count,
                                                'timeout': 20}},
        ]
        }
        logger.info('Sending traffic')
        scapy_checker = ScapyChecker(players, validation)
        retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=10, logger=logger)


def send_arp_request_and_check_update_corresponding_entry_into_arp_table(cli_obj, players, interface_data,
                                                                         request_type="broadcast"):
    """
    Send arp request and check update the corresponding arp entry into arp table
    :param cli_obj: cli_obj
    :param players: players fixture
    :param interface_data: interface
    :param request_type: arp request type(broadcast or unicast)
    """
    if request_type == "broadcast":
        dst_mac = "FF:FF:FF:FF:FF:FF"
    else:
        dst_mac = interface_data["dut_mac"]

    with allure.step('Host sends {} ARP request to DUT and check that receives the arp response'.format(request_type)):
        arp_request_traffic_validation(players=players, interface_data=interface_data,
                                       dst_mac=dst_mac, receive_packet_count=1)

    with allure.step("Verify DUT add the Host's IP and MAC into the ARP table"):
        retry_call(verify_arp_entry_in_arp_table,
                   fargs=[cli_obj, interface_data["host_ip"],
                          interface_data["host_mac"], interface_data["dut_interface"],
                          interface_data["dut_vlan_id"]],
                   tries=3, delay=10, logger=logger)
