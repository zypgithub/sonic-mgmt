import os
from collections import deque
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.performance.traffic_helpers import create_json_traffic_file_with_stream_list
from ngts.performance_tests.srv6.utils.srv6_workloads import create_round_robin_stream
from ngts.cli_wrappers.nvue.nvue_cli import NvueCli


def get_tg_bisection_traffic_params(players, player_alias, conf_args, traffic_type, template_suite, create_workload_stream,
                                    dut_interfaces_ipv6_configuration_dict, traffic_jsons, port_bisection_pairs):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_bisection.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    dut_mac_addresses = players['dut']['cli'].interface.get_all_interfaces_mac_addresses(verify_execution=False)
    for (src_port, dst_port) in port_bisection_pairs:
        player_cli_obj.performance.update_dst_mac_address(src_port, dut_mac_addresses, traffic_parameters)
        create_workload_stream(player_alias, player_cli_obj, [src_port], dst_port, traffic_parameters, traffic_type,
                               mloops_dict, dut_interfaces_ipv6_configuration_dict,
                               stream_list=stream_list, congestion=False)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_round_robin_traffic(players, conf_args, traffic_type,
                            upstream_downstream_group, bisection_traffic,
                            dut_interfaces_ipv6_configuration_dict,
                            template_suite="traffic_packets_json_files"):
    """
    First round (port i↔ port j: Means 1 packet ingress port i and egress port j, 1 packet ingress port j and egress port i):
    Port 0 ↔ 180
    Port 1 ↔ 181
    ...
    Port 178 ↔ 358.
    Port 179 ↔ 359.

    Second round:
    Port 0 ↔ 181.
    Port 1 ↔ 182.
    ...
    Port 178 ↔ 359.
    Port 179 ↔ 180.

    """
    traffic_jsons = {}
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports, right_ports = ports["left_ports"], ports["right_ports"]
    tg_src_dst_ports_dict = {PerfConsts.LEFT_TG_ALIAS: (left_ports, right_ports),
                             PerfConsts.RIGHT_TG_ALIAS: (right_ports, left_ports)}
    for tg_alias, (src_ports, dst_ports) in tg_src_dst_ports_dict.items():
        get_tg_round_robin_traffic_params(players, tg_alias, conf_args,
                                          traffic_type, template_suite,
                                          dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                          upstream_downstream_group, src_ports=src_ports, dst_ports=dst_ports,
                                          bisection_traffic=bisection_traffic)
    return traffic_jsons


def get_tg_round_robin_traffic_params(players, player_alias, conf_args, traffic_type, template_suite,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      upstream_downstream_group, src_ports, dst_ports,
                                      bisection_traffic, send_control_packets=False):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_round_robin.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    dut_mac_addresses = players['dut']['cli'].interface.get_all_interfaces_mac_addresses(verify_execution=False)
    for upstream_ports, downstream_ports in upstream_downstream_group:
        cycle_ports_pairs = get_cycle_ports_pairs(upstream_ports, downstream_ports)
        round_len = len(upstream_ports)
        for (port1, port2) in cycle_ports_pairs:
            ports_cycle_flow = get_ports_cycle_flow_by_tg(port1, port2, src_ports, dst_ports, bisection_traffic)
            for (src_port, dst_port) in ports_cycle_flow:
                player_cli_obj.performance.update_dst_mac_address(src_port, dut_mac_addresses, traffic_parameters)
                create_round_robin_stream(player_alias, player_cli_obj, [src_port], dst_port, traffic_parameters, traffic_type,
                                          mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                          stream_list=stream_list, send_data=True, send_ack=False, mrc_num_packets=1)
        if send_control_packets:
            last_round = cycle_ports_pairs[-round_len:]
            for (port1, port2) in last_round:
                ports_cycle_flow = get_ports_cycle_flow_by_tg(port1, port2, src_ports, dst_ports, bisection_traffic)
                for (src_port, dst_port) in ports_cycle_flow:
                    player_cli_obj.performance.update_dst_mac_address(src_port, dut_mac_addresses, traffic_parameters)
                    create_round_robin_stream(player_alias, player_cli_obj, [src_port], dst_port, traffic_parameters, traffic_type,
                                              mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                              stream_list=stream_list, send_data=False, send_ack=True)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_ports_cycle_flow_by_tg(port1, port2, tg_src_ports, other_tg_dst_ports, bisection_traffic):
    """
    In round-robin port i ↔ port j:
    Means 1 packet ingress port i and egress port j and 1 packet ingress port j and egress port i
    so, if both ports are of the tg, the tg needs to send both ways.
    otherwise, if both ports are of the other tg, the tg is not sending anything via these ports (they are not his ports).
    and in the other cases, the traffic directions depends on to which tg each port belongs.

    Args:
        port1: the first port in the pair, i.e. Ethernet0
        port2: the first port in the pair, i.e. Ethernet33
        tg_src_ports: the tg ports ("src_ports")
        other_tg_dst_ports:  the other tg ports ("dst ports")
        bisection_traffic: True if the ports should send to each other

    Returns:
    list of the relevant traffic pairs the tg need's to send.
    """
    if port1 in tg_src_ports and port2 in other_tg_dst_ports:
        return [(port1, port2)]
    elif port2 in tg_src_ports and port1 in other_tg_dst_ports and bisection_traffic:
        return [(port2, port1)]
    elif port1 in tg_src_ports and port2 in tg_src_ports and not bisection_traffic:
        return [(port1, port2)]
    else:
        return []


def get_ingress_ports_by_tg(ingress_ports, src_ports):
    return list(set(src_ports).intersection(ingress_ports))


def get_many_to_one_traffic(players, conf_args, traffic_type, dut_interfaces_ipv6_configuration_dict,
                            egress_ports, ingress_ports, create_workload_stream, congestion=False,
                            template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports, right_ports = ports["left_ports"], ports["right_ports"]
    tg_src_ports = {PerfConsts.LEFT_TG_ALIAS: left_ports,
                    PerfConsts.RIGHT_TG_ALIAS: right_ports}
    for tg_alias, src_ports in tg_src_ports.items():
        get_tg_many_to_one_traffic_params(players, tg_alias, conf_args,
                                          traffic_type, template_suite, create_workload_stream,
                                          dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                          egress_ports, ingress_ports, src_ports=src_ports,
                                          congestion=congestion)
    return traffic_jsons


def get_tg_many_to_one_traffic_params(players, player_alias, conf_args,
                                      traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      egress_ports, ingress_ports, src_ports, congestion):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_many_to_one.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []

    tg_ingress_ports = get_ingress_ports_by_tg(ingress_ports, src_ports)
    if tg_ingress_ports:
        for egress_port in egress_ports:
            create_workload_stream(player_alias, player_cli_obj, tg_ingress_ports, egress_port, traffic_parameters, traffic_type,
                                   mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                   stream_list=stream_list, congestion=congestion)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_ingress_ports_by_tg(ingress_ports, src_ports):
    return list(set(src_ports).intersection(ingress_ports))


def get_many_to_few_traffic(players, conf_args, traffic_type, dut_interfaces_ipv6_configuration_dict,
                            egress_ports, ingress_ports, create_workload_stream, congestion=False,
                            template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports, right_ports = ports["left_ports"], ports["right_ports"]
    tg_src_ports = {PerfConsts.LEFT_TG_ALIAS: left_ports,
                    PerfConsts.RIGHT_TG_ALIAS: right_ports}
    ingress_egress_ports_pairing = get_ingress_egress_ports_pairing(ingress_ports, egress_ports)
    for tg_alias, src_ports in tg_src_ports.items():
        get_tg_many_to_few_traffic_params(players, tg_alias, conf_args,
                                          traffic_type, template_suite, create_workload_stream,
                                          dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                          ingress_egress_ports_pairing, src_ports=src_ports,
                                          congestion=congestion)
    return traffic_jsons


def get_tg_many_to_few_traffic_params(players, player_alias, conf_args,
                                      traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      ingress_egress_ports_pairing, src_ports, congestion):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_many_to_few.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    for ingress_ports, egress_port in ingress_egress_ports_pairing:
        tg_ingress_ports = get_ingress_ports_by_tg(ingress_ports, src_ports)
        if tg_ingress_ports:
            create_workload_stream(player_alias, player_cli_obj, tg_ingress_ports, egress_port, traffic_parameters, traffic_type,
                                   mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                   stream_list=stream_list, congestion=congestion)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_ingress_egress_ports_pairing(ingress_ports, egress_ports):
    sublist_size = len(ingress_ports) // len(egress_ports)
    ingress_egress_ports_pairing = [ingress_ports[i:i + sublist_size] for i in range(0, len(ingress_ports), sublist_size)]
    return list(zip(ingress_egress_ports_pairing, egress_ports))


def get_cycle_ports_pairs(upstream, downstream):
    round_len = len(upstream)
    cycle_pairing = []
    for round in range(round_len):
        for i in range(round_len):
            if upstream[i] != downstream[(i + round) % round_len]:
                cycle_pairing.append((upstream[i], downstream[(i + round) % round_len]))
    return cycle_pairing


def get_cycle_ports_pairs_for_debug(upstream, downstream):
    downstream_deque = deque(downstream)
    cycle_pairing = []
    for upstream_port in upstream:
        cycle_pairing.extend((upstream_port, downstream_port) for downstream_port in downstream_deque)
        downstream_deque.rotate(-1)
    return cycle_pairing
