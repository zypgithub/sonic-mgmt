from ngts.helpers.performance.packet_json_generator import PacketGenerator
from ngts.constants.performance_constants import PerfConsts
from infra.tools.exceptions.test_issue import TestIssue


def create_json_traffic_file(player_alias, tg_ports, packet_size, num_packets, is_ipv6, json_path):
    ip_key = "IPv6" if is_ipv6 else "IP"
    packet = PacketGenerator(ports=tg_ports, packet_size=packet_size, num_packets=num_packets)
    packet.add_ether_header(src=PerfConsts.DUT_PKT_INFO["MAC"],
                            dst=PerfConsts.TG_ALIASES_PKT_INFO["MAC"][player_alias])
    packet.add_ip_header(src=PerfConsts.DUT_PKT_INFO[ip_key],
                         dst=PerfConsts.TG_ALIASES_PKT_INFO[ip_key][player_alias])
    packet.add_payload_header(player_alias)
    packet.to_json(json_path)


def validate_bw(traffic_json, bw_threshold):
    bw_samples = traffic_json["Bandwidth_samples"]
    lower_bw_sample = []
    for sample_id, bw_sample in bw_samples.items():
        if bw_sample['bw_stats']['min_bw'] < bw_threshold:
            lower_bw_sample.append(sample_id)
    if lower_bw_sample:
        raise TestIssue(f"Not all bandwidth samples were higher than threshold {bw_threshold}, "
                        f"please check {lower_bw_sample}")


def validate_tc(traffic_json, tc_occ_threshold):
    tc_samples = traffic_json["TC_samples"]
    lower_tc_samples = []
    for sample_id, tc_samples_dict in tc_samples.items():
        for tc_name, tc_samples_stats in tc_samples_dict.items():
            occ_avg = tc_samples_stats['occ_avg']
            if occ_avg < tc_occ_threshold:
                lower_tc_samples.append(f"{sample_id} - {tc_name}")
    if lower_tc_samples:
        raise TestIssue(f"Not all TC samples were higher than threshold {tc_occ_threshold}, "
                        f"please check {lower_tc_samples}")
