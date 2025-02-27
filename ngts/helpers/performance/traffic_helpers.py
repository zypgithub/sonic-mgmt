import allure
import json
import ipaddress
import pandas as pd
from ngts.helpers.performance.packet_json_generator import PacketGenerator
from ngts.constants.performance_constants import PerfConsts


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


def create_json_traffic_stream(player_alias, traffic_parameters, stream_name, tc=PerfConsts.CL_ROCE_LOSSLESS_DEFAULT_TC):
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
    packet.add_udp_header(
        source_port=traffic_parameters["UDP"]["src"],
        dest_port=traffic_parameters["UDP"]["dst"]
    )

    # Add BTH header with acknowledgment request
    packet.add_bth_header(ar=traffic_parameters["AR"])

    # Add payload header with player alias
    packet.add_payload_header(player_alias)

    # Convert the packet to JSON and assign the stream name
    stream = packet.get_json()
    stream["name"] = stream_name

    return stream


def create_json_traffic_file(player_alias, traffic_parameters, json_path):
    stream = create_json_traffic_stream(player_alias, traffic_parameters, f"spcx_ra_{player_alias}_main_stream")
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list=[stream])


def create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list):
    traffic_json = {
        "port_groups": [
            {
                "name": f"spcx_ra_{player_alias}",
                "ports": traffic_parameters["ports"],
                "stream_list": stream_list
            }
        ]
    }
    with open(json_path, 'w') as json_file:
        json.dump(traffic_json, json_file, indent=3)


def validate_bw(traffic_json, bw_threshold, violations_list):
    with allure.step(f"Validate all bandwidth samples minimal value is above {bw_threshold} threshold"):
        bw_samples = traffic_json["Bandwidth_samples"]
        bw_samples.pop('sample_params', None)
        lower_bw_sample = []
        for sample_id, bw_sample in bw_samples.items():
            if bw_sample['bw_stats']['min_bw'] < bw_threshold:
                lower_bw_sample.append(sample_id)
        if lower_bw_sample:
            violations_list.append(f"Not all bandwidth samples were higher than threshold {bw_threshold}, "
                                   f"please check {lower_bw_sample}")


def validate_bw_per_ports(traffic_json, bw_threshold, ports_list, violations_list):
    bw_samples = traffic_json["Bandwidth_samples"]
    bw_samples.pop('sample_params', None)
    for sample_id, bw_sample in bw_samples.items():
        bw_df = pd.DataFrame(bw_sample['bandwidth_dataframe'])
        for port in ports_list:
            port_tx = bw_df.loc[bw_df['port'] == hex(int(port))].loc[:, 'tx_rate'].values[0]
            if bw_threshold == 0 and port_tx > bw_threshold:
                violations_list.append(f"Port {port} tx: {port_tx} > {bw_threshold}, "
                                       f"please check {sample_id}")
            if port_tx < bw_threshold:
                violations_list.append(f"Port {port} tx: {port_tx} < {bw_threshold}, "
                                       f"please check {sample_id}")


def validate_tc(traffic_json, tc_occ_threshold, violations_list):
    with allure.step(f"Validate all TC samples average occupancy is below {tc_occ_threshold} cells"):
        tc_samples = traffic_json["TC_samples"]
        tc_samples.pop('sample_params', None)
        higher_tc_samples = []
        for sample_id, tc_samples_dict in tc_samples.items():
            for tc_name, tc_samples_stats in tc_samples_dict.items():
                occ_avg = tc_samples_stats['occ_avg']
                if occ_avg > tc_occ_threshold:
                    higher_tc_samples.append(f"{sample_id} - {tc_name}")
        if higher_tc_samples:
            violations_list.append(f"Not all TC samples were lower than threshold {tc_occ_threshold}, "
                                   f"please check {higher_tc_samples}")


def validate_counters(traffic_json, violations_list):
    counters_samples = traffic_json["Counters_samples"]
    counters_samples.pop('sample_params', None)
    for sample_id, counters_sample in counters_samples.items():
        validate_counters_sample(sample_id, counters_sample, violations_list)


def validate_counters_sample(sample_id, counters_sample, violations_list):
    counters_df = counters_sample['counters_dataframe']
    for counters_dict in counters_df:
        for counter_name in PerfConsts.COUNTERS:
            counter_value = counters_dict[counter_name]
            if counter_value > 0:
                port = counters_dict["port"]
                violations_list.append(f"Port {port} {counter_name}: {counter_value} > 0, "
                                       f"please check {sample_id}")
