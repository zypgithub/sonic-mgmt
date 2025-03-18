import os
from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.constants import BugHandlerConst
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


def get_tg_traffic_params(players, player_alias, conf_args, traffic_type, template_suite, create_workload_stream,
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
