import pytest
import logging
import os
from ngts.constants.performance_constants import PerfConsts
from ngts.constants.constants import BugHandlerConst
from ngts.helpers.performance.packet_json_generator import PacketGenerator
from ngts.helpers.performance.traffic_helpers import create_json_traffic_file_with_stream_list, create_json_traffic_stream

logger = logging.getLogger()
TESTS_SCENARIO = "lossy_lossless"


def add_dscp_ecn_support(dscp_value):
    """
    This function changes the dscp value, in order to mark packet as ECN (Explicit Congestion Notification) supported.
    This way, packet isn't dropped due to RED (Random Early Detection).

    This function is used to add IP TOS (IPv4) or TC (IPv6) to support dscp and ECN.

    Args:
        dscp_value:     Current dscp value (34 for lossy traffic or 26 for lossless)

    Returns:
        ECN supported value (shift left and bit OR 10)
    """
    return (dscp_value << 2) | 0b10


def create_lossy_lossless_json_traffic_file(player_alias, traffic_parameters, json_path, num_lossy_packets, num_lossless_packets):
    traffic_parameters["num_packets"] = num_lossy_packets
    lossy_stream = create_json_traffic_stream(player_alias, traffic_parameters, f"{player_alias}_lossy_stream",
                                              add_dscp_ecn_support(traffic_parameters["lossy_dscp_value"]))

    traffic_parameters["num_packets"] = num_lossless_packets
    lossless_stream = create_json_traffic_stream(player_alias, traffic_parameters, f"{player_alias}_lossless_stream",
                                                 add_dscp_ecn_support(traffic_parameters["lossless_dscp_value"]))

    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path,
                                              stream_list=[lossy_stream, lossless_stream])


def get_lossy_lossless_basic_traffic(players, conf_args, num_lossy_packets, num_lossless_packets, template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    pkt_size = PerfConsts.PACKET_SIZE_LIST[0]
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 TESTS_SCENARIO, f"{player_alias}_{TESTS_SCENARIO.replace('/', '_')}_{pkt_size}.json")
        traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=TESTS_SCENARIO,
                                                                               conf_args=conf_args)
        traffic_parameters.update({"lossy_dscp_value": 34, "lossless_dscp_value": 26})

        create_lossy_lossless_json_traffic_file(player_alias=player_alias, traffic_parameters=traffic_parameters,
                                                json_path=json_path, num_lossy_packets=num_lossy_packets,
                                                num_lossless_packets=num_lossless_packets)
        traffic_jsons[player_alias] = json_path
    return traffic_jsons
