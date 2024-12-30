import allure
import json
from ngts.helpers.performance.packet_json_generator import PacketGenerator
from ngts.constants.performance_constants import PerfConsts


def create_json_traffic_stream(player_alias, tg_ports, packet_size, num_packets, is_ipv6, stream_name):
    ip_key = "IPv6" if is_ipv6 else "IP"
    packet = PacketGenerator(ports=tg_ports, packet_size=packet_size, num_packets=num_packets)
    packet.add_ether_header(src=PerfConsts.DUT_PKT_INFO["MAC"],
                            dst=PerfConsts.TG_ALIASES_PKT_INFO["MAC"][player_alias])
    packet.add_ip_header(src=PerfConsts.DUT_PKT_INFO[ip_key],
                         dst=PerfConsts.TG_ALIASES_PKT_INFO[ip_key][player_alias])
    packet.add_payload_header(player_alias)
    stream = packet.get_json()
    stream["name"] = stream_name
    return stream


def create_json_traffic_file(player_alias, tg_ports, packet_size, num_packets, is_ipv6, json_path):
    stream = create_json_traffic_stream(player_alias, tg_ports, packet_size,
                                        num_packets, is_ipv6, f"spcx_ra_{player_alias}_main_stream")
    traffic_json = {
        "port_groups": [
            {
                "name": f"spcx_ra_{player_alias}",
                "ports": tg_ports,
                "stream_list": [stream]
            }
        ]
    }
    with open(json_path, 'w') as json_file:
        json.dump(traffic_json, json_file, indent=3)


def validate_bw(traffic_json, bw_threshold, violations_list):
    with allure.step(f"Validate all bandwidth samples minimal value is above {bw_threshold} threshold"):
        bw_samples = traffic_json["Bandwidth_samples"]
        bw_samples.pop('sample_params')
        lower_bw_sample = []
        for sample_id, bw_sample in bw_samples.items():
            if bw_sample['bw_stats']['min_bw'] < bw_threshold:
                lower_bw_sample.append(sample_id)
        if lower_bw_sample:
            violations_list.append(f"Not all bandwidth samples were higher than threshold {bw_threshold}, "
                                   f"please check {lower_bw_sample}")


def validate_tc(traffic_json, tc_occ_threshold, violations_list):
    with allure.step(f"Validate all TC samples average occupancy is above {tc_occ_threshold} cells"):
        tc_samples = traffic_json["TC_samples"]
        tc_samples.pop('sample_params')
        higher_tc_samples = []
        for sample_id, tc_samples_dict in tc_samples.items():
            for tc_name, tc_samples_stats in tc_samples_dict.items():
                occ_avg = tc_samples_stats['occ_avg']
                if occ_avg > tc_occ_threshold:
                    higher_tc_samples.append(f"{sample_id} - {tc_name}")
        if higher_tc_samples:
            violations_list.append(f"Not all TC samples were lower than threshold {tc_occ_threshold}, "
                                   f"please check {higher_tc_samples}")
