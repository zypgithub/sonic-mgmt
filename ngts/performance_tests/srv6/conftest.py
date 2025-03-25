import copy
import os
import random

from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts
from ngts.helpers.performance.traffic_helpers import (create_srv6_json_traffic_stream,
                                                      create_json_traffic_file_with_stream_list, dscp_to_tc)

PORT_DEFAULT_IPV6_PREFIX = "aaaa"
PORT_DEFAULT_IPV6_ROUTE_PREFIX = "bbbb"
PORT_DEFAULT_SRV6_PREFIX = "bbbb:1"
PORT_DEFAULT_SRC_PREFIX = "cccc"


def get_workload_method(workload):
    workload_to_method_dict = {
        "workload_1": create_workload1_stream,
        "workload_2": create_workload2_stream,
        "workload_3": create_workload3_stream,
    }
    return workload_to_method_dict[workload]


def get_tg_bisection_traffic_params(players, player_alias, conf_args, traffic_type, template_suite, create_workload_stream,
                                    dut_interfaces_ipv6_configuration_dict, traffic_jsons, port_bisection_pairs):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    for (src_port, dst_port) in port_bisection_pairs:
        create_workload_stream(player_alias, player_cli_obj, src_port, dst_port, traffic_parameters, traffic_type,
                               mloops_dict, dut_interfaces_ipv6_configuration_dict, stream_list=stream_list)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_tg_round_robin_traffic_params(players, player_alias, conf_args, traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons, cycle_ports_pairs, src_ports, dst_ports):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    for (port1, port2) in cycle_ports_pairs:
        ports_cycle_flow = get_ports_cycle_flow_by_tg(port1, port2, src_ports, dst_ports)
        for (src_port, dst_port) in ports_cycle_flow:
            create_workload_stream(player_alias, player_cli_obj, src_port, dst_port, traffic_parameters, traffic_type,
                                   mloops_dict, dut_interfaces_ipv6_configuration_dict, stream_list=stream_list)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_ports_cycle_flow_by_tg(port1, port2, tg_src_ports, other_tg_dst_ports):
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

    Returns:
    list of the relevant traffic pairs the tg need's to send.
    """
    if port1 in tg_src_ports and port2 in other_tg_dst_ports:
        return [(port1, port2)]
    elif port2 in tg_src_ports and port1 in other_tg_dst_ports:
        return [(port2, port1)]
    elif port1 in tg_src_ports and port2 in tg_src_ports:
        return [(port1, port2), (port2, port1)]
    elif port1 in other_tg_dst_ports and port2 in other_tg_dst_ports:
        return []


def get_round_robin_traffic(players, conf_args, traffic_type, upstream, downstream,
                            dut_interfaces_ipv6_configuration_dict, create_workload_stream,
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
    cycle_ports_pairs = get_cycle_ports_pairs(upstream, downstream)
    traffic_jsons = {}
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports, right_ports = ports["left_ports"], ports["right_ports"]
    get_tg_round_robin_traffic_params(players, PerfConsts.LEFT_TG_ALIAS, conf_args,
                                      traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      cycle_ports_pairs, src_ports=left_ports, dst_ports=right_ports)
    get_tg_round_robin_traffic_params(players, PerfConsts.RIGHT_TG_ALIAS, conf_args,
                                      traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      cycle_ports_pairs, src_ports=right_ports, dst_ports=left_ports)

    return traffic_jsons


def get_cycle_ports_pairs(upstream, downstream):
    round_len = len(upstream)
    cycle_pairing = []
    for round in range(round_len):
        for i in range(round_len):
            if upstream[i] != downstream[(i + round) % round_len]:
                cycle_pairing.append((upstream[i], downstream[(i + round) % round_len]))
    return cycle_pairing


def get_upstream_downstream_port_group_df(players):
    port_group_df = []
    dut_port = copy.deepcopy(players['dut']['cli'].performance.get_dut_ports())
    random.shuffle(dut_port)
    mid = len(dut_port) // 2
    upstream, downstream = dut_port[:mid], dut_port[mid:]
    for port in upstream:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "upstream"})
    for port in downstream:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "downstream"})
    return upstream, downstream, port_group_df


def get_spine_downstream_port_group_df(players):
    port_group_df = []
    downstream = copy.deepcopy(players['dut']['cli'].performance.get_dut_ports())
    for port in downstream:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "downstream"})
    return downstream, port_group_df


def get_dst_ip_by_traffic_type(traffic_type, dut_interfaces_ipv6_configuration_dict, dst_port):
    if traffic_type == "IPv6":
        return dut_interfaces_ipv6_configuration_dict[dst_port].replace(PORT_DEFAULT_IPV6_PREFIX,
                                                                        PORT_DEFAULT_IPV6_ROUTE_PREFIX)
    elif traffic_type == "SRv6":
        return dut_interfaces_ipv6_configuration_dict[dst_port].replace(PORT_DEFAULT_IPV6_PREFIX,
                                                                        PORT_DEFAULT_SRV6_PREFIX)
    else:
        raise TestIssue(f"Unknown traffic type {traffic_type} is not supported by workload1 traffic stream")


def create_workload1_stream(player_alias, cli_obj, src_port, dst_port, traffic_parameters, traffic_type,
                            mloops_dict, dut_interfaces_ipv6_configuration_dict, stream_list):
    """
    1 RTT probe packet (+ProbeAck) and 1 RoCE Ack, for each 50 MRC1 data packet
    """
    traffic_parameters["ports"] = [cli_obj.performance.get_hex_int_sdk_port(mloops_dict[src_port])]
    traffic_parameters["IP"] = {"src": "4.4.4.4", "dst": "10.0.1.0"}
    traffic_parameters["IPV6"]["src"] = dut_interfaces_ipv6_configuration_dict[src_port].replace(PORT_DEFAULT_IPV6_PREFIX,
                                                                                                 PORT_DEFAULT_SRC_PREFIX)
    traffic_parameters["IPV6"]["dst"] = get_dst_ip_by_traffic_type(traffic_type,
                                                                   dut_interfaces_ipv6_configuration_dict, dst_port)

    # MRC1
    traffic_parameters["num_packets"] = 50
    traffic_parameters["packet_size"] = 4096
    mrc1_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                  tc=dscp_to_tc(1), stream_name=f"{src_port}_to_{dst_port}_MRC1")
    # RTT
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = 255
    rtt_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                 tc=dscp_to_tc(2),
                                                 stream_name=f"{src_port}_to_{dst_port}_RTT",
                                                 BTH={'opcode': int(0x64)}, payload=False)
    # ProbeAck
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = 255
    probe_ack_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                       tc=dscp_to_tc(14),
                                                       stream_name=f"{src_port}_to_{dst_port}_ProbeAck",
                                                       BTH={'opcode': int(0x64)}, payload=False)
    # ROCE ACK
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = 255
    roce_ack_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                      tc=dscp_to_tc(15),
                                                      stream_name=f"{src_port}_to_{dst_port}_ROCE_ACK",
                                                      BTH={'opcode': int(0x11)}, payload=False)
    stream_list.extend([mrc1_stream, rtt_stream, probe_ack_stream, roce_ack_stream])


def create_workload2_stream():
    """
    MRC1 Data: 97%. 1 RTT probe packet (+ProbeAck) and 1 RoCE Ack, for each 50 MRC1 data packets.
    If there is congestion, 1 CNP packet for each MRC1 data packet.  ?

    MRC Trimmed: 1% (1G /256bytes = num of packets trimmed that should be sent),
    SACK/NACK: 1%

    MRC re-transmitting: 1%.
    """
    pass


def create_workload3_stream():
    """
    MRC1 Data: 50%. 1 RTT probe packet (+ProbeAck) and 1 RoCE Ack, for each 20-50 MRC1 data packets.
    If there is congestion, 1 CNP packet for each MRC1 data packet.

    MRC2 Data: 40%. 1 RTT probe packet (+ProbeAck) and 1 RoCE Ack, for each 20-50 MRC2 data packets.
    If there is congestion, 1 CNP packet for each MRC2 data packet.

    GFP Data: 6%,
    GFP control: 1%.

    MRC Trimmed: 1%,
    SACK/NACK: 1%

    MRC re-transmitting: 1%
    """
    pass
