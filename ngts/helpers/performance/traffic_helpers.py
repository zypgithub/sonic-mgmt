import allure
import json
import ipaddress
import pandas as pd
from ngts.helpers.performance.packet_json_generator import PacketGenerator
from ngts.constants.performance_constants import PerfConsts


def ip_to_int(ipstr):
    return int(ipaddress.ip_address(ipstr))


def int_to_ip(n):
    return str(ipaddress.ip_address(n))


def generate_ip_list(start_ip_address, list_of_ports):
    ip_list = [int_to_ip(ip_to_int(start_ip_address) + i) for i in range(len(list_of_ports))]
    return dict(list(zip(list_of_ports, ip_list)))


def create_json_traffic_stream(player_alias, traffic_parameters, stream_name):
    packet = PacketGenerator(ports=traffic_parameters["ports"],
                             packet_size=traffic_parameters["packet_size"],
                             num_packets=traffic_parameters["num_packets"])
    packet.add_ether_header(src=traffic_parameters["MAC"]["src"],
                            dst=traffic_parameters["MAC"]["dst"])
    packet.add_ip_header(src=traffic_parameters["IP"]["src"],
                         dst=traffic_parameters["IP"]["dst"])
    packet.add_udp_header(source_port=traffic_parameters["UDP"]["src"],
                          dest_port=traffic_parameters["UDP"]["dst"])
    packet.add_bth_header(ar=traffic_parameters["AR"])
    packet.add_payload_header(player_alias)
    stream = packet.get_json()
    stream["name"] = stream_name
    return stream


def create_json_traffic_file(player_alias, traffic_parameters, json_path):
    stream = create_json_traffic_stream(player_alias, traffic_parameters, f"spcx_ra_{player_alias}_main_stream")
    traffic_json = {
        "port_groups": [
            {
                "name": f"spcx_ra_{player_alias}",
                "ports": traffic_parameters["ports"],
                "stream_list": [stream]
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
            port_tx = bw_df.loc[bw_df['port'] == hex(port)].loc[:, 'tx_rate'].values[0]
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
