import os
import random
from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.performance_constants import MRCConsts, PerfConsts
from ngts.helpers.performance.traffic_helpers import (create_srv6_json_traffic_stream, dscp_to_tc)

PORT_DEFAULT_IPV6_PREFIX = "aaaa"
PORT_DEFAULT_IPV6_ROUTE_PREFIX = "bbbb"
PORT_DEFAULT_SRV6_PREFIX = "bbbb:1"
PORT_DEFAULT_SRC_PREFIX = "cccc"


def get_mloop_ports(mloops_dict, ports):
    mloop_ports = []
    for port in ports:
        mloop_ports.append(mloops_dict[port])
    return mloop_ports


def get_workload_method(workload):
    workload_to_method_dict = {
        "workload_1": create_workload1_stream,
        "workload_2": create_workload2_stream,
        "workload_3": create_workload3_stream,
        "opt_ts_workload": create_opt_ts_workload_stream,
    }
    return workload_to_method_dict[workload]


def get_dst_ip_by_traffic_type(traffic_type, dut_interfaces_ipv6_configuration_dict, dst_port):
    if traffic_type == "IPv6":
        return dut_interfaces_ipv6_configuration_dict[dst_port].replace(PORT_DEFAULT_IPV6_PREFIX,
                                                                        PORT_DEFAULT_IPV6_ROUTE_PREFIX)
    elif traffic_type == "SRv6":
        return dut_interfaces_ipv6_configuration_dict[dst_port].replace(PORT_DEFAULT_IPV6_PREFIX,
                                                                        PORT_DEFAULT_SRV6_PREFIX)
    else:
        raise TestIssue(f"Unknown traffic type {traffic_type} is not supported by workload1 traffic stream")


def create_workload1_stream(player_alias, cli_obj, src_ports, dst_port, traffic_parameters, traffic_type,
                            mloops_dict, dut_interfaces_ipv6_configuration_dict, stream_list,
                            mrc1_num_packets=10, send_ack=True, congestion=False, ecn_enabled=True):
    """
    1 RTT probe packet (+ProbeAck) and 1 RoCE Ack, for each 50 MRC1 data packet
    """
    set_workload_traffic_parameters(cli_obj, traffic_parameters, mloops_dict, src_ports, dst_port,
                                    dut_interfaces_ipv6_configuration_dict, traffic_type)
    get_mrc_data_stream(player_alias, traffic_parameters, src_ports, dst_port, mrc1_num_packets,
                        mrc_dscp=MRCConsts.MRC1_DSCP, rtt_dscp=MRCConsts.MRC1_RTT_DSCP, stream_list=stream_list,
                        send_ack=send_ack, congestion=congestion,
                        ecn_enabled=ecn_enabled, stream_num=1)


def create_opt_ts_workload_stream(player_alias, cli_obj, src_ports, dst_port, traffic_parameters, traffic_type,
                                  mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                  stream_list, congestion=False, ecn_enabled=True):
    """
    1 RTT probe packet (+ProbeAck) for each 1000 MRC1 data packet
    """
    create_workload1_stream(player_alias, cli_obj, src_ports, dst_port, traffic_parameters, traffic_type,
                            mloops_dict, dut_interfaces_ipv6_configuration_dict, stream_list,
                            mrc1_num_packets=10, send_ack=False, congestion=congestion, ecn_enabled=ecn_enabled)


def create_workload2_stream(player_alias, cli_obj, src_ports, dst_port, traffic_parameters, traffic_type,
                            mloops_dict, dut_interfaces_ipv6_configuration_dict, stream_list, mrc_num_packets=10,
                            congestion=False, ecn_enabled=True):
    """
    MRC1 Data: 97%. 1 RTT probe packet (+ProbeAck) and 1 RoCE Ack, for each 50 MRC1 data packets.
    If there is congestion, 1 CNP packet for each MRC1 data packet.  ?

    MRC Trimmed: 1% (1G /256bytes = num of packets trimmed that should be sent),
    SACK/NACK: 1%

    MRC re-transmitting: 1%.
    """
    set_workload_traffic_parameters(cli_obj, traffic_parameters, mloops_dict, src_ports, dst_port,
                                    dut_interfaces_ipv6_configuration_dict, traffic_type)
    get_mrc_data_stream(player_alias, traffic_parameters, src_ports, dst_port, mrc_num_packets,
                        mrc_dscp=MRCConsts.MRC1_DSCP, rtt_dscp=MRCConsts.MRC1_RTT_DSCP,
                        stream_list=stream_list, send_ack=True, congestion=congestion,
                        ecn_enabled=ecn_enabled, stream_num=1)
    mrc_trimmed_stream = get_mrc_stream(player_alias, traffic_parameters, 10, src_ports, dst_port,
                                        mrc_dscp=MRCConsts.MRC_TRIMMED_DSCP, mrc_stream_name="_TRIMMED",
                                        packet_size=os.environ.get("OPT_TS", 256),
                                        payload=True, ecn_enabled=False)
    sack_stream = get_sack_stream(player_alias, traffic_parameters, src_ports, dst_port)
    nack_stream = get_nack_stream(player_alias, traffic_parameters, src_ports, dst_port)
    mrc_retransmit_stream = get_mrc_stream(player_alias, traffic_parameters, 1, src_ports, dst_port,
                                           mrc_dscp=MRCConsts.MRC1_RETRANSMISSION_DSCP,
                                           mrc_stream_name="_RETRANSMIT",
                                           ecn_enabled=ecn_enabled)
    stream_list.extend([mrc_trimmed_stream, sack_stream, nack_stream, mrc_retransmit_stream])


def create_workload3_stream(player_alias, cli_obj, src_ports, dst_port, traffic_parameters, traffic_type,
                            mloops_dict, dut_interfaces_ipv6_configuration_dict, stream_list, mrc1_num_packets=5,
                            mrc2_num_packets=5, congestion=False, ecn_enabled=True):
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
    set_workload_traffic_parameters(cli_obj, traffic_parameters, mloops_dict, src_ports, dst_port,
                                    dut_interfaces_ipv6_configuration_dict, traffic_type)
    get_mrc_data_stream(player_alias, traffic_parameters, src_ports, dst_port, mrc1_num_packets,
                        mrc_dscp=MRCConsts.MRC1_DSCP, rtt_dscp=MRCConsts.MRC1_RTT_DSCP, stream_list=stream_list,
                        send_ack=True, congestion=congestion, ecn_enabled=ecn_enabled, stream_num=1)
    get_mrc_data_stream(player_alias, traffic_parameters, src_ports, dst_port, mrc2_num_packets,
                        mrc_dscp=MRCConsts.MRC2_DSCP, rtt_dscp=MRCConsts.MRC2_RTT_DSCP, stream_list=stream_list,
                        send_ack=True, congestion=congestion, ecn_enabled=ecn_enabled, stream_num=2)
    mrc_trimmed_stream = get_mrc_stream(player_alias, traffic_parameters, 1, src_ports, dst_port,
                                        MRCConsts.MRC_TRIMMED_DSCP, mrc_stream_name="_TRIMMED",
                                        packet_size=os.environ.get("OPT_TS", 256), payload=False, ecn_enabled=False)
    sack_stream = get_sack_stream(player_alias, traffic_parameters, src_ports, dst_port)
    nack_stream = get_nack_stream(player_alias, traffic_parameters, src_ports, dst_port)
    mrc_retransmit_stream = get_mrc_stream(player_alias, traffic_parameters, 1, src_ports, dst_port,
                                           MRCConsts.MRC1_RETRANSMISSION_DSCP, mrc_stream_name="_RETRANSMIT", ecn_enabled=ecn_enabled)
    set_workload_traffic_parameters(cli_obj, traffic_parameters, mloops_dict, src_ports, dst_port,
                                    dut_interfaces_ipv6_configuration_dict, traffic_type=MRCConsts.TRAFFIC_TYPE_IPV6)
    gfp_data_stream = get_gfp_data_stream(player_alias, traffic_parameters, src_ports, dst_port)
    gfp_control_stream = get_gfp_control_stream(player_alias, traffic_parameters, src_ports, dst_port)
    stream_list.extend([mrc_trimmed_stream, sack_stream, nack_stream, mrc_retransmit_stream, gfp_data_stream, gfp_control_stream])


def get_mrc_data_stream(player_alias, traffic_parameters, src_ports, dst_port,
                        mrc_num_packets, mrc_dscp, rtt_dscp, stream_list,
                        send_ack=True, congestion=False, ecn_enabled=True, stream_num=1):
    mrc_stream = get_mrc_stream(player_alias, traffic_parameters, mrc_num_packets,
                                src_ports=src_ports, dst_port=dst_port,
                                mrc_dscp=mrc_dscp, mrc_stream_name=stream_num, ecn_enabled=ecn_enabled)
    rtt_stream = get_rtt_stream(player_alias, traffic_parameters, src_ports, dst_port,
                                rtt_dscp=rtt_dscp, rtt_stream_num=stream_num, ecn_enabled=ecn_enabled)
    stream_list.extend([mrc_stream, rtt_stream])
    if congestion:
        cnp_stream = get_cnp_stream(player_alias, traffic_parameters,
                                    src_ports, dst_port, num_packets=mrc_num_packets)
        stream_list.extend([cnp_stream])
    if send_ack:
        probe_ack_stream = get_probe_ack_stream(player_alias, traffic_parameters, src_ports, dst_port)
        roce_ack_stream = get_roce_ack_stream(player_alias, traffic_parameters, src_ports, dst_port)
        stream_list.extend([probe_ack_stream, roce_ack_stream])


def set_workload_traffic_parameters(cli_obj, traffic_parameters,
                                    mloops_dict, src_ports, dst_port, dut_interfaces_ipv6_configuration_dict, traffic_type):
    mloops_ports = get_mloop_ports(mloops_dict, src_ports)
    src_port = random.choice(src_ports)
    traffic_parameters["ports"] = cli_obj.performance.get_hex_int_sdk_ports(mloops_ports)
    traffic_parameters["IP"] = {"src": "4.4.4.4", "dst": "10.0.1.0"}
    traffic_parameters["IPV6"]["src"] = dut_interfaces_ipv6_configuration_dict[src_port].replace(PORT_DEFAULT_IPV6_PREFIX,
                                                                                                 PORT_DEFAULT_SRC_PREFIX)
    traffic_parameters["IPV6"]["dst"] = get_dst_ip_by_traffic_type(traffic_type,
                                                                   dut_interfaces_ipv6_configuration_dict, dst_port)


def get_mrc_stream(player_alias, traffic_parameters, mrc_num_packets,
                   src_ports, dst_port, mrc_dscp, mrc_stream_name,
                   packet_size=4096, payload=True, ecn_enabled=True):
    traffic_parameters["num_packets"] = mrc_num_packets
    traffic_parameters["packet_size"] = packet_size
    ecn_value = 1 if ecn_enabled else 0
    mrc_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                 tc=dscp_to_tc(mrc_dscp, ecn=ecn_value),
                                                 stream_name=f"{', '.join(src_ports)}_to_{dst_port}_MRC{mrc_stream_name}",
                                                 BTH={'opcode': int(0x00)}, payload=payload)
    return mrc_stream


def get_rtt_stream(player_alias, traffic_parameters, src_ports,
                   dst_port, rtt_dscp, rtt_stream_num, ecn_enabled=True):
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = PerfConsts.RTT_PROB_SIZE
    ecn_value = 1 if ecn_enabled else 0
    rtt_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                 tc=dscp_to_tc(rtt_dscp, ecn=ecn_value),
                                                 stream_name=f"{', '.join(src_ports)}_to_{dst_port}_RTT_{rtt_stream_num}",
                                                 BTH={'opcode': int(0x64)}, payload=False)
    return rtt_stream


def get_probe_ack_stream(player_alias, traffic_parameters, src_ports, dst_port):
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = PerfConsts.RTT_PROB_RESPONSE_SIZE
    probe_ack_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                       tc=dscp_to_tc(MRCConsts.PROBE_ACK_DSCP),
                                                       stream_name=f"{', '.join(src_ports)}_to_{dst_port}_ProbeAck",
                                                       BTH={'opcode': int(0x64)}, payload=False)
    return probe_ack_stream


def get_roce_ack_stream(player_alias, traffic_parameters, src_ports, dst_port):
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = PerfConsts.ROCE_ACK_SIZE
    roce_ack_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                      tc=dscp_to_tc(MRCConsts.ROCE_ACK_DSCP),
                                                      stream_name=f"{', '.join(src_ports)}_to_{dst_port}_ROCE_ACK",
                                                      BTH={'opcode': int(0x11)}, payload=False)
    return roce_ack_stream


def get_nack_stream(player_alias, traffic_parameters, src_ports, dst_port):
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = PerfConsts.NACK_SIZE
    nack_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                  tc=dscp_to_tc(MRCConsts.NACK_DSCP),
                                                  stream_name=f"{', '.join(src_ports)}_to_{dst_port}_NACK",
                                                  BTH={'opcode': int(0x1E)}, payload=False)
    return nack_stream


def get_sack_stream(player_alias, traffic_parameters, src_ports, dst_port):
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = PerfConsts.SACK_SIZE
    sack_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                  tc=dscp_to_tc(MRCConsts.SACK_DSCP),
                                                  stream_name=f"{', '.join(src_ports)}_to_{dst_port}_SACK",
                                                  BTH={'opcode': int(0x1D)}, payload=False)
    return sack_stream


def get_cnp_stream(player_alias, traffic_parameters, src_ports, dst_port, num_packets=1):
    traffic_parameters["num_packets"] = num_packets
    traffic_parameters["packet_size"] = PerfConsts.CNP_SIZE
    cnp_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                 tc=dscp_to_tc(MRCConsts.CNP_DSCP),
                                                 stream_name=f"{', '.join(src_ports)}_to_{dst_port}_CNP",
                                                 BTH={'opcode': int(0x81)}, payload=False)
    return cnp_stream


def get_gfp_data_stream(player_alias, traffic_parameters, src_ports, dst_port):
    traffic_parameters["num_packets"] = 6
    traffic_parameters["packet_size"] = 4096
    gfp_data_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                      tc=dscp_to_tc(MRCConsts.GFP_DATA_DSCP),
                                                      stream_name=f"{', '.join(src_ports)}_to_{dst_port}_GFP_DATA",
                                                      BTH={'opcode': int(0x00)}, payload=False)
    return gfp_data_stream


def get_gfp_control_stream(player_alias, traffic_parameters, src_ports, dst_port):
    traffic_parameters["num_packets"] = 1
    traffic_parameters["packet_size"] = PerfConsts.GFP_CONTROL_SIZE
    gfp_control_stream = create_srv6_json_traffic_stream(player_alias, traffic_parameters,
                                                         tc=dscp_to_tc(MRCConsts.GFP_CONTROL_DSCP),
                                                         stream_name=f"{', '.join(src_ports)}_to_{dst_port}_GFP_CONTROL",
                                                         BTH={'opcode': int(0x81)}, payload=False)
    return gfp_control_stream
