import logging
import tempfile
import tarfile
import json
import os
import re
import ipaddress

from retry import retry
from scapy.all import sniff
from scapy.layers.inet6 import IP
from scapy.layers.vxlan import VXLAN
from ngts.constants.constants import VxlanConstants
from ngts.config_templates.parallel_config_runner import parallel_config_runner
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from devts.infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker

logger = logging.getLogger()


def send_and_validate_traffic(player, sender, sender_intf, sender_pkt_format, sender_count, receiver, receiver_intf,
                              receiver_filter_format, receiver_count=-1):
    """
    This method is used to send then validate traffic
    :param player: player
    :param sender: sender, such as 'ha', 'hb'
    :param sender_intf: sender interface
    :param sender_pkt_format: sender packet format
    :param sender_count: how many packets needed to send
    :param receiver: receiver, such as 'ha', 'hb'
    :param receiver_intf: receiver interface
    :param receiver_filter_format: receiver filter format
    :param receiver_count: how many packets needed to be received, default value is -1,
    it means there should be no packet loss
    """
    if receiver_count == -1:
        receiver_count = sender_count
    traffic_validation = {'sender': sender,
                          'send_args': {'interface': sender_intf,
                                        'packets': sender_pkt_format,
                                        'count': sender_count},
                          'receivers':
                              [
                                  {'receiver': receiver,
                                   'receive_args': {
                                       'interface': receiver_intf,
                                       'filter': receiver_filter_format,
                                       'count': receiver_count
                                   }
                                   }
                          ]
                          }
    logger.info(f"Traffic parameters: {traffic_validation}")
    ScapyChecker(player, traffic_validation).run_validation()


def generate_fdb_json_content(vlan_id, port, op, mac_address):
    """
    This method is used to generate json content for fdb static mac configuration
    :param vlan_id: vlan id for static mac address
    :param port: ethernet port name
    :param op: operation type, for example, SET and DEL
    :param mac_address: static mac address
    :return: json content for fdb config
    """
    logger.info("Generating json content for static mac configuration")
    fdb_config_json = []
    entry_key_template = "FDB_TABLE:Vlan{vid}:{mac}"

    fdb_entry_json = {entry_key_template.format(vid=vlan_id, mac=mac_address): {"port": port, "type": "static"},
                      "OP": op
                      }
    fdb_config_json.append(fdb_entry_json)
    return fdb_config_json


def generate_static_mac_for_fdb(engines, vlan_id, port, op, dest, mac_address):
    """
    This method is used to generate a json file to config static mac
    :param engines: engines fixture
    :param vlan_id: vlan id for static mac address
    :param port: ethernet port name
    :param op: operation type, for example, SET and DEL
    :param dest: fdb json file path of dut
    :param mac_address: static mac address

    Generate FDB config file to apply it using 'swssconfig' tool.
    Generated config file template:
    [
        {
            "FDB_TABLE:Vlan[VID]:XX-XX-XX-XX-XX-XX": {
                "port": "Ethernet0",
                "type": "static"
            },
            "OP": "SET"
        }
    ]
    """
    fdb_config_json = generate_fdb_json_content(vlan_id, port, op, mac_address)

    with tempfile.NamedTemporaryFile(suffix=".json", prefix="fdb_config_", delete=False) as fp:
        logger.info(f"Generating FDB config file - {fp.name}")
        fdb_config_json = json.dumps(fdb_config_json)
        fp.write(fdb_config_json.encode('utf8'))
        fp.seek(0)
        logger.info(f"Content of FDB config file - {fp.read()}")

    # Copy FDB JSON config file to DUT
    logger.info(f"Start copying {fp.name} from ngts docker to {dest} at DUT")
    engines.dut.copy_file(source_file=fp.name, dest_file=dest, file_system='/', direction="put",
                          overwrite_file=True, verify_file=False)


def apply_fdb_config(engines, vlan_id, port, op, static_mac):
    """
    This method is used to create FDB config and applies it on DUT
    :param engines: engines fixture
    :param vlan_id: vlan id for static mac address
    :param port: ethernet port name
    :param op: operation type, for example, SET and DEL
    """
    dut_tmp_dir = "/tmp"
    fdb_json = "fdb.json"
    dut_fdb_config = os.path.join(dut_tmp_dir, fdb_json)

    engines.dut.run_cmd(f"mkdir -p {dut_tmp_dir}")

    logger.info("Generating static MAC fdb config file and store it to DUT")
    generate_static_mac_for_fdb(engines, vlan_id, port, op, dut_fdb_config, static_mac)

    logger.info("Copy static MAC fdb json config file to SWSS container")
    engines.dut.run_cmd(f"docker cp {dut_fdb_config} swss:/")

    # Add FDB entry
    logger.info(f"Apply static MAC entry - {port} - {static_mac}")
    engines.dut.run_cmd("docker exec -i swss swssconfig /fdb.json")


@retry(Exception, tries=5, delay=2)
def verify_mac_entry_learned(cli_objects, vlan_id, mac, port, fdb_type="dynamic"):
    """
    The method is to verify that mac address is saved to fdb table
    :param cli_objects: cli_objects fixture
    :param vlan_id:  vlan id
    :param mac: mac address
    :param port: port
    :param fdb_type: fdb type (dynamic/static)
    """
    mac_table = cli_objects.dut.mac.parse_mac_table()
    for k, v in mac_table.items():
        if v["Vlan"] == str(vlan_id) and v["MacAddress"].lower() == mac.lower() and v["Port"] == port and v[
                "Type"].lower() == fdb_type:
            return True
    assert False, f"Fdb item: {mac} {vlan_id} {port} {fdb_type} is not saved into fdb table"


@retry(Exception, tries=5, delay=2)
def verify_mac_entry_not_learned(cli_objects, vlan_id, mac, port, fdb_type="dynamic"):
    """
    The method is to verify that mac address doesn't exist in fdb table
    :param cli_objects: cli_objects fixture
    :param vlan_id:  vlan id
    :param mac: mac address
    :param port: port
    :param fdb_type: fdb type (dynamic/static)
    """
    mac_table = cli_objects.dut.mac.parse_mac_table()
    for k, v in mac_table.items():
        if v["Vlan"] == str(vlan_id) and v["MacAddress"].lower() == mac.lower() and v["Port"] == port and v[
                "Type"].lower() == fdb_type:
            assert False, f"Fdb item: {mac} {vlan_id} {port} {fdb_type} still exists in fdb table"
    return True


def check_vtep_based_vxlan_counter(vxlan_counters, tx_rx_type, packet_num):
    """
    This method is used to check vtep based vxlan counter, its output format is listed

    vtep101032
    ----------

    RX:
            18 packets
           N/A bytes
    TX:
           501 packets
           N/A bytes

    :param vxlan_counters: output of command 'show vxlan counters <vtep_ip>
    :param tx_rx_type: 'tx' or 'rx' mode
    :param packet_num: expected packet numbers
    """
    if tx_rx_type == 'tx':
        matched = re.search(r"TX\:\n\s+(\d+) packets", vxlan_counters)
    elif tx_rx_type == 'rx':
        matched = re.search(r"RX\:\n\s+(\d+) packets", vxlan_counters)
    if matched:
        matched_packet_num = matched.group(1)
        logger.info(f"{matched_packet_num} {tx_rx_type} packets parsed")
        assert int(matched_packet_num) >= packet_num, \
            f"{matched_packet_num} packets is less than expected {packet_num} packets"


def check_vxlan_counter(vtep_name, vxlan_counters, tx_rx_type, packet_num):
    """
    This method is used to check default vxlan counter, its output is listed

         IFACE    RX_PKTS    RX_BYTES    RX_PPS    TX_PKTS    TX_BYTES    TX_PPS
    ----------  ---------  ----------  --------  ---------  ----------  --------
    vtep101032          0         N/A    0.00/s          0         N/A    0.00/s

    :param vtep_name: vtep name
    :param vxlan_counters: parse dict of vxlan counters
    :param tx_rx_type: 'tx' or 'rx' mode
    :param packet_num: expected packet number
    """
    for _, counter_values in vxlan_counters.items():
        if tx_rx_type == 'tx':
            if counter_values["IFACE"] == vtep_name and int(counter_values["TX_PKTS"]) >= packet_num:
                return True
        elif tx_rx_type == 'rx':
            if counter_values["IFACE"] == vtep_name and int(counter_values["RX_PKTS"]) >= packet_num:
                return True
    assert False, f"There is no vxlan counter entry for tunnel {vtep_name}"


@retry(Exception, tries=10, delay=2)
def verify_counter_entry(cli_objects, vtep_name, tx_rx_type, packet_num, vtep_mode=False):
    """
    This method is to verify the vxlan counter
    :param cli_objects: cli_object fixture
    :param vtep_name: vtep name
    :param packet_num: packet number that needs to be verified
    :param tx_rx_type: verify tx packet or rx packet
    """
    if vtep_mode:
        vxlan_counters = cli_objects.dut.vxlan.show_vxlan_counter(vtep_name)
        check_vtep_based_vxlan_counter(vxlan_counters, tx_rx_type, packet_num)
    else:
        vxlan_counters = cli_objects.dut.vxlan.show_vxlan_counter()
        check_vxlan_counter(vtep_name, vxlan_counters, tx_rx_type, packet_num)


@retry(Exception, tries=10, delay=2)
def verify_bgp_container_up(cli_objects):
    """
    This method is used to verify the bgp process status
    :param cli_objects: cli_objects fixture
    """
    name = 'bgp'
    status = cli_objects.dut.general.get_container_status(name)
    assert status, "{} container is not up, container status is None".format(name)
    assert "Up" in status, "expected status is Up, actual is {}".format(status)


def vni_to_hex_vni(vni):
    """
    This method is used to map integer vni value to hex vni value carried in vxlan packets
    :param vni: integer vni value
    :return: hex vni value carried in vxlan packets
    """
    hex_vni = hex(vni)
    hex_vni += '00'
    return hex_vni


@retry(Exception, tries=10, delay=2)
def verify_ecmp_counter_entry(cli_objects, interface_counter_check_list):
    """
    This method is to verify the vxlan counter
    :param cli_objects: cli_object fixture
    :param interface_counter_check_list: counter check items, for example,
    [['Ethernet64', 'rx', 400], [['Ethernet0', 'Ethernet128'], 'tx', 400]]
    """
    interface_counters_dict = cli_objects.dut.vxlan.show_interface_counter()
    check_item_num = len(interface_counter_check_list)
    count = 0
    for check_item in interface_counter_check_list:
        intf_names = check_item[0]
        tx_rx_type = check_item[1]
        packet_num = int(check_item[2])
        total_tx_packets = 0
        for _, counter_values in interface_counters_dict.items():
            if tx_rx_type == 'tx':
                for intf_name in intf_names:
                    if counter_values["IFACE"] == intf_name:
                        total_tx_packets += int(counter_values["TX_OK"])
            elif tx_rx_type == 'rx':
                if counter_values["IFACE"] == intf_names and int(counter_values["RX_OK"]) >= packet_num:
                    logger.info(f'Checking {counter_values["IFACE"]}, the {tx_rx_type} counter '
                                f'is {counter_values["RX_OK"]}, need to be at least {packet_num}')
                    count += 1
        if total_tx_packets >= packet_num:
            logger.info(f'Checking {intf_names}, the {tx_rx_type} counter is {total_tx_packets}, '
                        f'need to be at least {packet_num}')
            count += 1
    assert count == check_item_num, "Counter value not correct"


def get_tech_support_tar_file(engines):
    """
    This method is used to get tar.gz dump file and copy it from DUT to ngts docker
    :param engines: engines fixture
    :return: the tech support tarball file name
    """
    output_lines = engines.dut.run_cmd('show techsupport').split('\n')
    tar_file = output_lines[len(output_lines) - 1]
    tarball_file_name = str(tar_file.replace('/var/dump/', ''))

    engines.dut.copy_file(source_file=tar_file, dest_file=tarball_file_name, file_system='/tmp/', direction='get')
    engines.dut.run_cmd("sudo rm -rf {}".format(tar_file))

    return tarball_file_name


def validate_dest_files_exist_in_tarball(tarball_file_name, dest_json_file):
    """
    This method is used to get destination file path in tarball
    :param tarball_file_name: tarball name
    :param dest_json_file: destination json file name, such as CONFIG_DB.json or APPL_DB.json
    :return: the path of destination json file
    """
    with tarfile.open(tarball_file_name, "r") as t:
        filenames = t.getnames()

    # get config_db.json or appl_db.json file path
    json_file_path = None
    for file_path in filenames:
        if dest_json_file in file_path:
            json_file_path = file_path
    assert json_file_path, f"{dest_json_file} not found in {tarball_file_name}"
    return json_file_path


def validate_vxlan_table_in_dest_json(engines, tarball_file_name, json_path, vxlan_table_list, remove_tarball=False):
    """
    This method is used to check whether all the vxlan tables exist in given json file
    :param tarball_file_name: tech support tarball
    :param json_path: json file path, typically the path of CONFIG_DB.json or APPL_DB.json
    :param vxlan_table_list: list contains vxlan table names, for example
    ['VXLAN_EVPN_NVO', 'VXLAN_TUNNEL_MAP', 'VXLAN_TUNNEL']
    """
    with tarfile.open(tarball_file_name, "r") as t:
        file_raw_content = t.extractfile(json_path)
        json_content = json.loads(str(file_raw_content.read(), 'utf8'))

    if remove_tarball:
        cmd = f"rm -rf {tarball_file_name}"
        logger.info(f"Delete {tarball_file_name} at NGTS docker\n{cmd}")
        os.system(cmd)
    # Find vxlan tables in json file
    exist_vxlan_tables = []
    for table in vxlan_table_list:
        exist_flag = False
        for key_name in json_content.keys():
            if table in key_name and key_name not in exist_vxlan_tables:
                logger.info(f"{table} exists in {json_path}")
                logger.info('--------------------------------------------')
                logger.info(f"{key_name}\n{json_content[key_name]}\n")
                exist_flag = True
                exist_vxlan_tables.append(key_name)
        assert exist_flag, f"{table} not found in {json_path}"


@retry(Exception, tries=5, delay=2)
def validate_basic_evpn_type_2_3_route(players, cli_objects, interfaces, vlan_id, dut_vlan_ip, dut_loopback_ip,
                                       ha_vtep_ip, hb_vlan_ip, rd):
    """
    This method is used to verify basic evpn type 2 and type 3 route states
    :param cli_objects: cli_objects fixture
    """
    hb_vlan_mac = cli_objects.hb.mac.get_mac_address_for_interface(f"{interfaces.hb_dut_1}.{vlan_id}")

    logger.info(f"Send ping from HB to DUT via VLAN {vlan_id}")
    ping_hb_dut_vlan = {'sender': 'hb',
                        'args': {'interface': f"{interfaces.hb_dut_1}.{vlan_id}", 'count': VxlanConstants.PACKET_NUM_3,
                                 'dst': dut_vlan_ip}}
    PingChecker(players, ping_hb_dut_vlan).run_validation()

    # VXLAN route validation
    logger.info('Validate CLI type-2 routes on DUT')
    dut_type_2_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_macip()
    cli_objects.dut.frr.validate_type_2_route(dut_type_2_info, hb_vlan_mac, dut_loopback_ip,
                                              rd, hb_vlan_ip)

    logger.info('Validate CLI type-3 routes on DUT')
    dut_type_3_info = cli_objects.dut.frr.get_l2vpn_evpn_route_type_multicast()
    cli_objects.dut.frr.validate_type_3_route(dut_type_3_info, ha_vtep_ip, ha_vtep_ip, rd)

    logger.info('Validate CLI type-2 routes on HA')
    ha_type_2_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_macip()
    cli_objects.ha.frr.validate_type_2_route(ha_type_2_info, hb_vlan_mac, dut_loopback_ip,
                                             rd, hb_vlan_ip)

    logger.info('Validate CLI type-3 routes on HA')
    ha_type_3_info = cli_objects.ha.frr.get_l2vpn_evpn_route_type_multicast()
    cli_objects.ha.frr.validate_type_3_route(ha_type_3_info, dut_loopback_ip, dut_loopback_ip, rd)


def sonic_ports_flap(cli_obj, port_list, flap_count=2):
    for i in range(flap_count):
        cli_obj.interface.disable_interfaces(port_list)
        cli_obj.interface.check_link_state(port_list, expected_status='down')
        cli_obj.interface.enable_interfaces(port_list)
        cli_obj.interface.check_link_state(port_list)


def restart_bgp_session(cli_object):
    """
    Restart bgp session
    """
    logging.info("Restart BGP session")
    restart_bgp_cmd = 'clear bgp *'
    cli_object.frr.run_config_frr_cmd(restart_bgp_cmd)


def get_network(ip, mask_len):
    """
    Get the network from ip
    """
    ip_version = ipaddress.ip_address(ip).version
    if ip_version == 4:
        network = ipaddress.IPv4Network(f"{ip}/{mask_len}", strict=False).network_address.compressed
    else:
        network = ipaddress.IPv6Network(f"{ip}/{mask_len}", strict=False).network_address.compressed
    return network


@retry(Exception, tries=10, delay=2)
def validate_ip_vrf_route(cli_obj, route_ip, mask_len, vrf):
    """
    This method is used to validate ip/ipv6 vrf route
    """
    ip_vrf_route_info = cli_obj.route.show_ip_route(vrf=vrf)
    ip_network = get_network(route_ip, mask_len)
    err_msg = 'Expected vrf route: {}/{} \n not found in: \n{}'.format(ip_network, mask_len, ip_vrf_route_info)
    assert '{}/{}'.format(ip_network, mask_len) in ip_vrf_route_info, err_msg


def clean_frr_vrf_config(topology, config_list):
    """
    This method is used to change frr/bgp configuration
    """
    logger.info(f'Clean FRR - {config_list}')
    for config_item in config_list:
        conf = {}
        for player_alias, config_list in config_item.items():
            cli_object = topology.players[player_alias]['stub_cli']
            for config in config_list:
                cli_object.frr.run_config_frr_cmd(config)
            cli_object.frr.save_frr_configuration()
            conf[player_alias] = cli_object.frr.engine.commands_list
            cli_object.frr.engine.commands_list = []

        parallel_config_runner(topology, conf)


def validate_ecmp_traffic(pcap_path_list, ip_check_list, sender_count, receiver_count=-1, proto=IP):
    """
    Validate traffic captured at ECMP interfaces, there should be load balanced over the next_hop interfaces
    """
    total_count = 0
    for pcap in pcap_path_list:
        count = 0
        vxlan_pkts = sniff(offline=pcap, lfilter=lambda p: VXLAN in p)
        layer_index = 2 if proto == IP else 1
        for pkt in vxlan_pkts:
            if pkt.getlayer(proto, nb=layer_index).src in ip_check_list:
                count += 1
        logger.info(f"Matched {count} VXLAN packets in {pcap}")
        if receiver_count == -1:
            assert count > 0, f"There must be at least 1 VXLAN packet received in {pcap}"
        total_count += count
    logger.info(f"Total received packet number:{total_count}")
    if receiver_count == -1:
        assert total_count == len(ip_check_list) * int(sender_count)
    else:
        assert total_count == receiver_count


def config_evpn_route_map(cli_objects, route_map, bgp_session_id, route_map_params, bgp_neighbor_list):
    logger.info(f"Config route map for evpn routes")
    for action, sesquence, route_type in route_map_params:
        cli_objects.dut.frr.config_evpn_route_map(route_map, action, sesquence, route_type)

    logger.info("Bind route map to bgp")
    for bgp_neighbor in bgp_neighbor_list:
        cli_objects.dut.frr.bind_evpn_route_map(route_map, bgp_neighbor, bgp_session_id)


def remove_evpn_route_map(cli_objects, route_map, bgp_session_id, bgp_neighbor_list):
    logger.info("Unbind route map to bgp")
    for bgp_neighbor in bgp_neighbor_list:
        cli_objects.dut.frr.bind_evpn_route_map(name=route_map, bgp_neighbor=bgp_neighbor,
                                                bgp_session_id=bgp_session_id, bind=False)

    logger.info("Remove route map")
    cli_objects.dut.frr.clean_evpn_route_map(route_map)
