import allure
import json
import logging
import ipaddress
import random
import pandas as pd
from ngts.helpers.performance.packet_json_generator import PacketGenerator
from ngts.constants.performance_constants import PerfConsts, ValidationConsts
from ast import literal_eval


def generate_ip_address_list(address_start_v4="172.168.1.1", address_start_v6="172::1:1", step_v4=256, step_v6=0x10000,
                             number_of_address: int = 64, mode="v4"):
    """
    Returns :
        address_lst = {
            "v4": ["172.168.1.1", "172.168.1.2" ...],
            "v6": ["172::1", "172::2", ...]
        }
    """
    address_list = {
        "v4": [],
        "v6": []
    }
    if isinstance(step_v6, str):
        step_v6 = int(step_v6, 16)

    if mode in ["v4", "dual"]:
        start_address_v4 = ipaddress.IPv4Address(address_start_v4)
        for i in range(0, number_of_address):
            address_list["v4"].append(str(start_address_v4 + i * step_v4))

    if mode in ["v6", "dual"]:
        start_address_v6 = ipaddress.IPv6Address(address_start_v6)
        for i in range(0, number_of_address):
            address_list["v6"].append(str(start_address_v6 + i * step_v6))

    if mode == "dual":
        return address_list
    elif mode == "v4":
        return address_list["v4"]
    elif mode == "v6":
        return address_list["v6"]


def generate_ip_address_dict(address_start, step, mode, list_of_ports):
    '''
    Returns :
    {
        port1: "172.168.1.1",
        port2: "172.168.1.2",
        or
        port1: "172::1",
        port2: "172::2"
    }
    '''
    address_list = []
    if mode == "v4":
        address_list = generate_ip_address_list(address_start_v4=address_start, step_v4=step, number_of_address=len(list_of_ports), mode="v4")
    if mode == "v6":
        address_list = generate_ip_address_list(address_start_v6=address_start, step_v6=step, number_of_address=len(list_of_ports), mode="v6")

    return dict(zip(list_of_ports, address_list))


def address_calculator(address, operation="add", step=None, operand: str = None, mode="v6"):
    if mode == "v4":
        address = ipaddress.IPv4Address(address)
        step = int(step)
        if operation == "add":
            return str(ipaddress.IPv4Address(address) + (step * operand))
        elif operation == "sub":
            return str(ipaddress.IPv4Address(address) - (step * operand))
        elif operation == "mul":
            return str(ipaddress.IPv4Address(address) * (step * operand))
        elif operation == "div":
            return str(ipaddress.IPv4Address(address) / (step * operand))
    elif mode == "v6":
        address = ipaddress.IPv6Address(address)
        step = int(step, 16)
        if operation == "add":
            return str(ipaddress.IPv6Address(address) + (step * operand))
        elif operation == "sub":
            return str(ipaddress.IPv6Address(address) - (step * operand))
        elif operation == "mul":
            return str(ipaddress.IPv6Address(address) * (step * operand))
        elif operation == "div":
            return str(ipaddress.IPv6Address(address) / (step * operand))
    else:
        raise ValueError(f"Invalid mode: {mode}")


def create_empty_json_traffic_file(json_path):
    traffic_json = {
        "port_groups": [
            {
                "name": f"EMPTY_TRAFFIC_STREAM",
                "ports": [],
                "stream_list": [PacketGenerator(ports=[], packet_size=0, num_packets=0).get_json()]
            }
        ]
    }
    with open(json_path, 'w') as json_file:
        json.dump(traffic_json, json_file, indent=3)


def create_json_traffic_stream(player_alias, traffic_parameters, stream_name, tc=PerfConsts.CL_ROCE_LOSSLESS_DEFAULT_TC,
                               ip_protocol=PerfConsts.IP_PROTOCOL_UDP):
    """
    Creates a JSON representation of a traffic stream.

    Args:
        player_alias (str): Alias for the player generating the traffic.
        traffic_parameters (dict): Dictionary containing traffic parameters such as ports, packet size,
                                   number of packets, MAC addresses, IP addresses, UDP ports, and AR.
        stream_name (str): Name of the traffic stream.
        tc (int, optional): Traffic class. Defaults to PerfConsts.CL_ROCE_LOSSLESS_DEFAULT_TC.

    Returns:
        dict: JSON representation of the traffic stream.
    """
    # Initialize a packet generator with specified ports, packet size, and number of packets
    packet = PacketGenerator(
        ports=traffic_parameters["ports"],
        packet_size=traffic_parameters["packet_size"],
        num_packets=traffic_parameters["num_packets"]
    )

    # Add Ethernet header with source and destination MAC addresses and traffic class
    packet.add_ether_header(
        src=traffic_parameters["MAC"]["src"],
        dst=traffic_parameters["MAC"]["dst"]
    )

    # Add IP header based on whether the traffic is IPv6 or IPv4
    if traffic_parameters['is_ipv6']:
        packet.add_ipv6_header(
            src=traffic_parameters["IP"]["src"],
            dst=traffic_parameters["IP"]["dst"],
            tc=tc
        )
    else:
        packet.add_ip_header(
            src=traffic_parameters["IP"]["src"],
            dst=traffic_parameters["IP"]["dst"],
            tos=tc
        )

    # Add UDP header with source and destination ports
    if ip_protocol == PerfConsts.IP_PROTOCOL_UDP:
        packet.add_udp_header(
            source_port=traffic_parameters["UDP"]["src"],
            dest_port=traffic_parameters["UDP"]["dst"]
        )
    else:
        packet.add_tcp_header(
            sport=traffic_parameters[PerfConsts.IP_PROTOCOL_TCP]["sport"],
            dport=traffic_parameters[PerfConsts.IP_PROTOCOL_TCP]["dport"]
        )

    # Add BTH header with acknowledgment request
    packet.add_bth_header(ar=traffic_parameters["AR"])

    # Add payload header with player alias
    packet.add_payload_header(player_alias)

    # Convert the packet to JSON and assign the stream name
    stream = packet.get_json()
    stream["name"] = stream_name

    return stream


def create_srv6_json_traffic_stream(player_alias, traffic_parameters, stream_name,
                                    tc, BTH={}, payload=True, ip_protocol=PerfConsts.IP_PROTOCOL_UDP):
    """
    Creates a JSON representation of a traffic stream.

    Args:
        player_alias (str): Alias for the player generating the traffic.
        traffic_parameters (dict): Dictionary containing traffic parameters such as ports, packet size,
                                   number of packets, MAC addresses, IP addresses, UDP ports, and AR.
        stream_name (str): Name of the traffic stream.
        tc (int, optional): Traffic class. Defaults to PerfConsts.CL_ROCE_LOSSLESS_DEFAULT_TC.

    Returns:
        dict: JSON representation of the traffic stream.
    """
    # Initialize a packet generator with specified ports, packet size, and number of packets
    packet = PacketGenerator(
        ports=traffic_parameters["ports"],
        packet_size=traffic_parameters["packet_size"],
        num_packets=traffic_parameters["num_packets"]
    )

    # Add Ethernet header with source and destination MAC addresses and traffic class
    packet.add_ether_header(
        src=traffic_parameters["MAC"]["src"],
        dst=traffic_parameters["MAC"]["dst"]
    )

    packet.add_ipv6_header(
        src=traffic_parameters["IPV6"]["src"],
        dst=traffic_parameters["IPV6"]["dst"],
        tc=tc
    )

    packet.add_ip_header(
        src=traffic_parameters["IP"]["src"],
        dst=traffic_parameters["IP"]["dst"],
        tos=tc
    )

    # Add UDP header with source and destination ports
    if ip_protocol == PerfConsts.IP_PROTOCOL_UDP:
        packet.add_udp_header(
            source_port=traffic_parameters[PerfConsts.IP_PROTOCOL_UDP]["src"],
            dest_port=traffic_parameters[PerfConsts.IP_PROTOCOL_UDP]["dst"]
        )
    elif ip_protocol == PerfConsts.IP_PROTOCOL_TCP:
        packet.add_tcp_header(
            sport=traffic_parameters[PerfConsts.IP_PROTOCOL_TCP]["sport"],
            dport=traffic_parameters[PerfConsts.IP_PROTOCOL_TCP]["dport"]
        )
    else:
        pass
    if BTH:
        packet.add_bth_header(opcode=BTH['opcode'], ar=1)
    # Add payload header with player alias
    if payload:
        packet.add_payload_header(player_alias)

    # Convert the packet to JSON and assign the stream name
    stream = packet.get_json()
    stream["name"] = stream_name

    return stream


def create_json_traffic_file(player_alias, traffic_parameters, json_path, ip_protocol=PerfConsts.IP_PROTOCOL_UDP, tc=PerfConsts.CL_ROCE_LOSSLESS_DEFAULT_TC):
    stream = create_json_traffic_stream(player_alias, traffic_parameters, f"spcx_ra_{player_alias}_main_stream", ip_protocol=ip_protocol, tc=tc)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list=[stream])


def create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list):
    traffic_json = {
        "port_groups": [
            {
                "name": f"{player_alias}_traffic_pattern",
                "stream_list": stream_list
            }
        ]
    }
    with open(json_path, 'w') as json_file:
        json.dump(traffic_json, json_file, indent=3)


def validate_no_drops_on_tg_ports(traffic_json, players, violations_list):
    for player_alias in PerfConsts.TG_ALIAS_LIST:
        with allure.step(f"Validate no drops on TG ports on - {player_alias}"):
            cli_obj = players[player_alias]['cli']
            violations = cli_obj.performance.validate_no_drops_on_tg_ports()
            violations_list.extend(violations)


def validate_bw(traffic_json, bw_threshold, validate_bw_rx, violations_list):
    with allure.step(f"Validate all bandwidth samples minimal value is above {bw_threshold} threshold"):
        bw_samples = traffic_json[ValidationConsts.BW_SAMPLES]
        bw_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
        lower_tx_bw_sample = []
        lower_rx_bw_sample = []
        for sample_id, bw_sample in bw_samples.items():
            bw_stats = bw_sample[ValidationConsts.BW_STATS]
            if bw_stats[ValidationConsts.TX_RATE_MIN] < bw_threshold:
                lower_tx_bw_sample.append(sample_id)
            if validate_bw_rx and bw_stats[ValidationConsts.RX_RATE_MIN] < bw_threshold:
                lower_rx_bw_sample.append(sample_id)
        if lower_tx_bw_sample:
            violations_list.append(f"Not all tx bandwidth samples were higher than threshold {bw_threshold}, "
                                   f"please check {lower_tx_bw_sample}")
        if lower_rx_bw_sample:
            violations_list.append(f"Not all rx bandwidth samples were higher than threshold {bw_threshold}, "
                                   f"please check {lower_rx_bw_sample}")


def get_ports_avg_bw(traffic_json):
    bw_samples = traffic_json[ValidationConsts.BW_SAMPLES]
    samples = list(traffic_json[ValidationConsts.BW_SAMPLES].keys())
    last_sample = bw_samples[samples[-1]]
    bw_samples_stats = last_sample[ValidationConsts.BW_STATS]
    avg_ports_tx = bw_samples_stats[ValidationConsts.TX_BW_AVG]
    avg_ports_rx = bw_samples_stats[ValidationConsts.RX_BW_AVG]
    return avg_ports_tx, avg_ports_rx


def get_tc_occ(traffic_json, tc_list, key=ValidationConsts.TC_OCC_AVG):
    tc_occ_dict = {}
    tc_samples = traffic_json[ValidationConsts.TC_SAMPLES]
    samples = list(tc_samples.keys())
    last_sample = tc_samples[samples[-1]]
    tc_df = last_sample[ValidationConsts.TC_DATAFRAME]
    for tc_dict in tc_df:
        tc_name = tc_dict[ValidationConsts.TC_NAME]
        if tc_name in tc_list:
            tc_occ = tc_dict[key]
            tc_occ_dict[tc_name] = tc_occ
    return tc_occ_dict


def validate_bw_per_ports(traffic_json, bw_threshold, ports_list, violations_list):
    bw_samples = traffic_json[ValidationConsts.BW_SAMPLES]
    bw_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
    for sample_id, bw_sample in bw_samples.items():
        bw_df = pd.DataFrame(bw_sample[ValidationConsts.BW_DATAFRAME])
        for port in ports_list:
            port_tx = bw_df.loc[bw_df[ValidationConsts.PORT] == hex(literal_eval(port))].loc[:, ValidationConsts.TX_RATE].values[0]
            if bw_threshold == 0 and port_tx > bw_threshold:
                violations_list.append(f"Port {port} tx: {port_tx} > {bw_threshold}, "
                                       f"please check {sample_id}")
            if port_tx < bw_threshold:
                violations_list.append(f"Port {port} tx: {port_tx} < {bw_threshold}, "
                                       f"please check {sample_id}")


def validate_tc(traffic_json, tc_occ_threshold, violations_list):
    with allure.step(f"Validate all TC samples average occupancy is below {tc_occ_threshold} cells"):
        tc_samples = traffic_json[ValidationConsts.TC_SAMPLES]
        tc_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
        higher_tc_samples = []
        for sample_id, tc_sample in tc_samples.items():
            tc_df = tc_sample[ValidationConsts.TC_DATAFRAME]
            for tc_dict in tc_df:
                tc_name = tc_dict[ValidationConsts.TC_NAME]
                for tc_occ_key, tc_occ_th in tc_occ_threshold.items():
                    tc_occ = tc_dict[tc_occ_key]
                    if tc_occ > tc_occ_th:
                        higher_tc_samples.append(f"{sample_id} - {tc_name} {tc_occ_key} {tc_occ} > {tc_occ_th} threshold")
                        with allure.step(f"Attach TC sample {sample_id}: {tc_dict}"):
                            pass
        if higher_tc_samples:
            violations_list.append(f"Not all TC samples were lower than threshold {tc_occ_threshold}, "
                                   f"please check {higher_tc_samples}")


def validate_per_tc(traffic_json, tc_occ_threshold, tc_to_validate, violations_list):
    with allure.step(f"Validate {tc_to_validate} TC samples occupancy rate is below {tc_occ_threshold} cells"):
        tc_samples = traffic_json[ValidationConsts.TC_SAMPLES]
        tc_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
        higher_tc_samples = []
        for sample_id, tc_sample in tc_samples.items():
            tc_df = tc_sample[ValidationConsts.TC_DATAFRAME]
            for tc_dict in tc_df:
                tc_name = tc_dict[ValidationConsts.TC_NAME]
                if tc_name in tc_to_validate:
                    for tc_occ_key, tc_occ_th in tc_occ_threshold.items():
                        tc_occ = tc_dict[tc_occ_key]
                        if tc_occ > tc_occ_th:
                            higher_tc_samples.append(f"{sample_id} - {tc_name} {tc_occ_key} {tc_occ} > {tc_occ_th} threshold")
        if higher_tc_samples:
            violations_list.append(f"Not all TC samples were lower than threshold {tc_occ_threshold}, "
                                   f"please check {higher_tc_samples}")


def validate_counters(traffic_json, skip_first_counters_iteration, ignore_counter_list, violations_list):
    """
    Validates counter samples from traffic data, optionally skipping the first iteration.

    Args:
        traffic_json (dict): JSON containing traffic counter samples
        skip_first_counters_iteration (bool): Whether to skip validating the first counter sample
        ignore_counter_list (list): list of counters to ignore during validation
        violations_list (list): List to store any validation violations found
    """
    counters_samples = traffic_json[ValidationConsts.COUNTERS_SAMPLES]

    counters_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)

    # Remove the first counter sample if skip_first_counters_iteration is True
    if skip_first_counters_iteration:
        counters_samples.pop(next(iter(counters_samples)))

    # Process each counter sample
    for sample_id, counters_sample in counters_samples.items():
        validate_counters_sample(sample_id, counters_sample, ignore_counter_list, violations_list)


def validate_counters_sample(sample_id, counters_sample, ignore_counter_list, violations_list):
    """
    Validates a single counter sample for any non-zero counter values.

    Args:
        sample_id (str): Identifier for the counter sample
        counters_sample (dict): Sample data containing counter values
        ignore_counter_list (list): list of counters to ignore during validation
        violations_list (list): List to store any validation violations found
    """
    counters_df = pd.DataFrame(counters_sample[ValidationConsts.COUNTERS_DATAFRAME])

    ports_with_counters = counters_df.loc[counters_df.loc[:, counters_df.columns != ValidationConsts.PORT].any(axis=1), ValidationConsts.PORT].to_list()
    counters_with_values = counters_df.loc[:, counters_df.columns != ValidationConsts.PORT].columns[counters_df.loc[:, counters_df.columns != ValidationConsts.PORT].gt(0).any()].tolist()
    counters_with_values = [counter for counter in counters_with_values if counter not in ignore_counter_list]

    if counters_with_values:
        violations_list.append(f"Ports: {ports_with_counters} had one or more of the following counters:\n"
                               f"{counters_with_values} with values > 0,\n "
                               f"please check {sample_id}")


def is_ipv6(address):
    """Check if the address is an IPv6 address."""
    # Regex to match IPv6 address (simplified version, just checks for ':')
    return ":" in address


def dscp_to_tc(dscp, ecn=0):
    """
    Converts a DSCP value to a Traffic Class (TC) value for IPv6.

    Args:
        dscp (int): The DSCP value (0 to 63).
        ecn (int, optional): The ECN value (0 to 3). Default is 0 (no congestion).

    Returns:
        int: The Traffic Class value (8 bits).
    """
    if not (0 <= dscp <= 63):
        raise ValueError("DSCP value must be between 0 and 63.")

    if not (0 <= ecn <= 3):
        raise ValueError("ECN value must be between 0 and 3.")

    # DSCP value is stored in the first 6 bits (shifted into place)
    tc = (dscp << 2) | ecn

    return tc


def generate_mac_range(start_mac, count):
    mac_list = []

    # Convert the starting MAC address to an integer
    start_mac_int = int(start_mac.replace(":", ""), 16)

    # Generate the range of MAC addresses
    for i in range(count):
        # Increment the MAC address
        current_mac_int = start_mac_int + i

        # Format it back into a MAC address string
        current_mac = ':'.join(format(current_mac_int, '012x')[i:i + 2] for i in range(0, 12, 2))
        mac_list.append(current_mac)

    return mac_list


def pick_random_non_consecutive_ports(ports_list, port_number, non_consecutive_gap=16):
    if port_number > (len(ports_list) + 1) // 2:
        raise ValueError("Cannot select non-consecutive items, list too small for the selection.")

    indices = list(range(len(ports_list)))
    start_idx = random.choice(indices)

    selected_ports = []

    for i in range(port_number):
        selected_ports.append(ports_list[start_idx % len(ports_list)])
        start_idx += non_consecutive_gap
    return selected_ports


def pick_random_consecutive_ports(ports_list, port_number):
    indices = list(range(len(ports_list) - port_number))
    start_idx = random.choice(indices)
    selected_ports = ports_list[start_idx:start_idx + port_number]
    return selected_ports


def validate_no_dropped_packets_on_queue(cli_obj, interface_list, queue_list, violations_list):
    for interface in interface_list:
        with allure.step(f"Validate no dropped packets on queues {queue_list} for {interface}"):
            show_queue_counters_dict = cli_obj.interface.parse_show_queue_counters(interface)
            logging.info(f"show queue counters for {interface}:\n{show_queue_counters_dict}")
            for queue in queue_list:
                queue_counter_pkts, queue_drop_pkts = get_counters_for_queue(show_queue_counters_dict, queue)
                if queue_drop_pkts > 0:
                    violations_list.append(f"Dropped packets on {interface} queue {queue}")


def get_counters_for_queue(show_queue_counters_dict, queue):
    queue_counter_pkts = int(show_queue_counters_dict[f"UC{queue}"]["Counter/pkts"].replace(",", ""))
    queue_drop_pkts = int(show_queue_counters_dict[f"UC{queue}"]["Drop/pkts"].replace(",", ""))
    return queue_counter_pkts, queue_drop_pkts


def get_counters_for_queue_bytes(show_queue_counters_dict, queue, packet_size):
    queue_counter_bytes = int(show_queue_counters_dict[f"UC{queue}"]["Counter/bytes"].replace(",", ""))
    queue_drop_bytes = int(show_queue_counters_dict[f"UC{queue}"]["Drop/pkts"].replace(",", "")) * packet_size
    return queue_counter_bytes, queue_drop_bytes


def is_no_untrimmed_packets(drop_queue_counter_pkts, drop_queue_drop_pkts, trimming_queue_counter_pkts, trimming_queue_drop_pkts):
    if drop_queue_counter_pkts == 0 and \
            drop_queue_drop_pkts > 0 and \
            trimming_queue_counter_pkts > 0 and \
            trimming_queue_drop_pkts == 0:
        return True
    else:
        return False


def get_queue_packet_percentages(cli_obj, interface_list, queues_list):
    queue_packet_percentages = {}
    for interface in interface_list:
        total_queue_counter_pkts = 0
        show_queue_counters_dict = cli_obj.interface.parse_show_queue_counters(interface)
        logging.info(f"show queue counters for {interface}:\n{show_queue_counters_dict}")
        for queue in queues_list:
            queue_counter_pkts, queue_counter_drop_pkts = get_counters_for_queue(show_queue_counters_dict, queue)
            total_queue_counter_pkts += queue_counter_pkts
        for queue in queues_list:
            queue_counter_pkts, queue_counter_drop_pkts = get_counters_for_queue(show_queue_counters_dict, queue)
            queue_packet_percentage = round(queue_counter_pkts / total_queue_counter_pkts, 2)
            queue_packet_percentages[f"Queue{queue}"] = queue_packet_percentage
    return queue_packet_percentages


def validate_trimmed_untrimmed_dropped_percentages(cli_obj, interface_list, trimming_queue, drop_queues, violations_list, return_dict=False):
    """
    validate that packets sent to queue drop_queue which are dropped are trimmed on queue trimming_queue for all interfaces
    :param interface_list: list of interfaces, i.e ['Ethernet111', 'Ethernet112']
    :param trimming_queue: trimming queue, i.e 'UC4'
    :param drop_queues: drop queue, i.e 'UC1'
    """
    queue_packet_percentages = []
    with allure.step(f"Validate all packets sent to queue {drop_queues} are dropped and trimmed on queue {trimming_queue} for all egress interfaces"):
        for interface in interface_list:
            with allure.step(f"Validate all packets sent to queue {drop_queues} are dropped and trimmed on queue {trimming_queue} for {interface}"):
                total_drop_queue_counter_pkts = 0
                total_packets_egress_port = 0
                total_packets_egress_port_dropped = 0
                total_drop_queue_counter_pkts_bytes = 0
                total_packets_egress_port_bytes = 0
                total_packets_egress_port_dropped_bytes = 0
                show_queue_counters_dict = cli_obj.interface.parse_show_queue_counters(interface)
                logging.info(f"show queue counters for {interface}:\n{show_queue_counters_dict}")
                for drop_queue in drop_queues:
                    total_drop_queue_counter_pkts, total_packets_egress_port_dropped, total_drop_queue_counter_pkts_bytes, total_packets_egress_port_dropped_bytes = update_queue_counters(show_queue_counters_dict, drop_queue,
                                                                                                                                                                                           total_drop_queue_counter_pkts, total_packets_egress_port_dropped,
                                                                                                                                                                                           total_drop_queue_counter_pkts_bytes, total_packets_egress_port_dropped_bytes)
                total_packets_egress_port = total_drop_queue_counter_pkts + total_packets_egress_port_dropped
                trimming_queue_counter_pkts, trimming_queue_drop_pkts = get_counters_for_queue(show_queue_counters_dict, trimming_queue)
                trimming_queue_counter_pkts_bytes, trimming_queue_drop_pkts_bytes = get_counters_for_queue_bytes(show_queue_counters_dict, trimming_queue, PerfConsts.PACKET_SIZE_4K)
                total_packets_egress_port_bytes = total_drop_queue_counter_pkts_bytes + trimming_queue_counter_pkts_bytes
                dropped_without_trimming = total_packets_egress_port_dropped - trimming_queue_counter_pkts
                if dropped_without_trimming > 0:
                    dropped_without_trimming_percentage = round(dropped_without_trimming / total_packets_egress_port, 2)
                else:
                    dropped_without_trimming_percentage = 0
                untrimmed_percentage = round(total_drop_queue_counter_pkts / total_packets_egress_port, 2)
                untrimmed_bytes_percentage = round(total_drop_queue_counter_pkts_bytes / total_packets_egress_port_bytes, 2)
                trimming_percentage = round(trimming_queue_counter_pkts / total_packets_egress_port, 2)
                trimming_bytes_percentage = round(trimming_queue_counter_pkts_bytes / total_packets_egress_port_bytes, 2)
                queue_packet_percentages_dict = {ValidationConsts.PORT: interface,
                                                 ValidationConsts.UNTRIMMED_PRECENTAGE: untrimmed_percentage,
                                                 ValidationConsts.TRIMMING_PRECENTAGE: trimming_percentage,
                                                 ValidationConsts.DROPPED_WITHOUT_TRIMMING_PRECENTAGE: dropped_without_trimming_percentage,
                                                 ValidationConsts.UNTRIMMED_BYTES_PRECENTAGE: untrimmed_bytes_percentage,
                                                 ValidationConsts.TRIMMING_BYTES_PRECENTAGE: trimming_bytes_percentage}
                queue_packet_percentages.append(queue_packet_percentages_dict)
                if trimming_queue_drop_pkts > 0:
                    violations_list.append(f"Dropped packets detected on Trimming queue {trimming_queue} for {interface}")
                if dropped_without_trimming_percentage > 0:
                    violations_list.append(f"Dropped packets without trimming detected on {interface}")
                if return_dict:
                    return queue_packet_percentages_dict
    queue_packet_percentages_df = pd.DataFrame(queue_packet_percentages)
    with allure.step(f"Attach queue_packet_percentages_df"):
        allure.attach(queue_packet_percentages_df.to_html(), "Queue packet percentages dataframe", attachment_type=allure.attachment_type.HTML)


def update_queue_counters(show_queue_counters_dict, queue,
                          queue_pkts_counter, queue_drop_pkts_counter,
                          queue_pkts_bytes_counter, queue_dropped_bytes_counter):
    queue_pkts, queue_drop = get_counters_for_queue(show_queue_counters_dict, queue)
    queue_bytes, queue_drop_bytes = get_counters_for_queue_bytes(show_queue_counters_dict, queue, PerfConsts.PACKET_SIZE_4K)
    queue_pkts_counter += queue_pkts
    queue_drop_pkts_counter += queue_drop
    queue_pkts_bytes_counter += queue_bytes
    queue_dropped_bytes_counter += queue_drop_bytes
    return queue_pkts_counter, queue_drop_pkts_counter, queue_pkts_bytes_counter, queue_dropped_bytes_counter
