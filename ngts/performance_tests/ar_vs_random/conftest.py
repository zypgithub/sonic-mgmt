import pytest
import time
import logging
import os
from ngts.constants.performance_constants import PerfConsts, PowerConsts, MongoDbConsts
from ngts.constants.constants import BugHandlerConst
from ngts.helpers.performance.traffic_helpers import (create_json_traffic_file, create_json_traffic_stream,
                                                      create_json_traffic_file_with_stream_list, create_empty_json_traffic_file, dscp_to_tc)

logger = logging.getLogger()
TESTS_SCENARIO = "ar_vs_random"


def get_ar_vs_random_traffic(players, conf_args, bisection_traffic, template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    pkt_size = PerfConsts.PACKET_SIZE_LIST[0]
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 TESTS_SCENARIO, f"{player_alias}_{TESTS_SCENARIO.replace('/', '_')}_{pkt_size}.json")

        traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=TESTS_SCENARIO,
                                                                               conf_args=conf_args)
        tc = dscp_to_tc(PerfConsts.DVS_LOSSLESS_TC, 2)
        if player_alias == conf_args["host"]:
            if bisection_traffic:
                create_json_traffic_file(player_alias=player_alias,
                                         traffic_parameters=traffic_parameters, json_path=json_path, tc=tc)
            else:
                create_empty_json_traffic_file(json_path)
        else:
            get_spine_to_leaf_stream_list(players, player_alias, conf_args, traffic_parameters, json_path, tc=tc)
        traffic_jsons[player_alias] = json_path
    return traffic_jsons


def get_spine_to_leaf_stream_list(players, spine_tg, conf_args, traffic_parameters, json_path, tc=PerfConsts.CL_ROCE_LOSSLESS_DEFAULT_TC):
    dut_configuration = players['dut']['cli'].performance.get_device_configuration(conf_args=conf_args)
    left_tg_configuration = players['left_tg']['cli'].performance.get_device_configuration(conf_args=conf_args)
    leaf_dst_ips = list(dut_configuration["right_side_ports_to_ip_dict"].values())
    stream_list = []

    # Helper function to create stream with consistent formatting
    def create_stream(stream_name, packet_size, traffic_tc):
        traffic_parameters["packet_size"] = packet_size
        return create_json_traffic_stream(spine_tg, traffic_parameters, stream_name, tc=traffic_tc)

    unconnected_ports = left_tg_configuration[PerfConsts.PORT_GROUPS]["unconnected_ports"]
    connected_ports = left_tg_configuration[PerfConsts.PORT_GROUPS]["connected_ports"]
    tc_6 = dscp_to_tc(PerfConsts.DVS_CONTROL_TC, 2)

    for index, (unconnected_port, connected_port) in enumerate(zip(unconnected_ports, connected_ports)):
        traffic_parameters["ports"] = [unconnected_port]
        traffic_parameters["IP"]["dst"] = leaf_dst_ips[index]
        traffic_parameters["num_packets"] = 1
        port_pattern = f"_from_{hex(unconnected_port)}_to_{hex(connected_port)}"

        # RoCE ACK stream
        stream_name = f"RoCE_ack{port_pattern}"
        stream = create_stream(stream_name, PerfConsts.ROCE_ACK_SIZE, tc)
        stream_list.append(stream)

        # RTT probe stream
        stream_name = f"RTT_probe{port_pattern}"
        stream = create_stream(stream_name, PerfConsts.RTT_PROB_SIZE, tc)
        stream_list.append(stream)

        # RTT probe response stream
        stream_name = f"RTT_probe_response{port_pattern}"
        stream = create_stream(stream_name, PerfConsts.RTT_PROB_RESPONSE_SIZE, tc_6)
        stream_list.append(stream)

        # CNP stream
        stream_name = f"CNP{port_pattern}"
        stream = create_stream(stream_name, PerfConsts.CNP_SIZE, tc_6)
        stream_list.append(stream)

    # RoCE data stream
    traffic_parameters["ports"] = unconnected_ports
    traffic_parameters["num_packets"] = 2
    jump_step = 2 if not conf_args["one_to_one_leaf_scenario"] else 1
    for ip in leaf_dst_ips[::jump_step]:
        stream_name = f"spine_to_leaf_ip_{ip}"
        traffic_parameters["IP"]["dst"] = ip
        stream = create_stream(stream_name, PerfConsts.PACKET_SIZE_LIST[0], tc)
        stream_list.append(stream)

    create_json_traffic_file_with_stream_list(spine_tg, traffic_parameters, json_path, stream_list)
