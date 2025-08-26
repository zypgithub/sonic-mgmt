import json
import re
import pytest
import time
import logging
import os
import ipaddress
from netaddr import EUI
from ngts.constants.performance_constants import PerfConsts, PowerConsts, MongoDbConsts
from ngts.constants.constants import BugHandlerConst
from ngts.helpers.performance.packet_json_generator import PacketGenerator
from ngts.helpers.performance.traffic_helpers import (create_json_traffic_file, create_json_traffic_stream,
                                                      create_json_traffic_file_with_stream_list, create_empty_json_traffic_file, dscp_to_tc)

logger = logging.getLogger()
TESTS_SCENARIO = "alibaba_performance"


def get_alibaba_leaf_traffic(players, conf_args, template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 TESTS_SCENARIO, f"{player_alias}_{TESTS_SCENARIO.replace('/', '_')}_{conf_args['packet_size']}.json")
        traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=TESTS_SCENARIO,
                                                                               conf_args=conf_args)

        traffic_parameters["AR"] = PerfConsts.ADAPTIVE_ROUTING_ENABLED if conf_args["ar_enabled"] else PerfConsts.ADAPTIVE_ROUTING_DISABLED
        get_multiple_ip_stream_list(player_alias, traffic_parameters, json_path, conf_args)
        traffic_jsons[player_alias] = json_path
    return traffic_jsons


def get_multiple_ip_stream_list(spine_tg, traffic_parameters, json_path, conf_args):
    direction_from = "left" if spine_tg == "left_tg" else "right"
    stream_list = []

    ports_from = f'{direction_from} {"host" if conf_args["host"] == spine_tg else "spine"}'
    ports_to = f'{direction_from} {"spine" if conf_args["spine"] == spine_tg else "host"}'
    direction_to = "right" if direction_from == "left" else "left"

    for traffic_type, traffic_enabled in zip(["ipv4", "ipv6"], [conf_args["is_ipv4"], conf_args["is_ipv6"]]):
        if traffic_enabled:
            traffic_parameters["IP"]["dst"] = conf_args["ip_to_mac_dict"][direction_from][traffic_type][0][0]
            traffic_parameters["IP"]["src"] = conf_args[f"{traffic_type}_source_ip"]
            traffic_parameters["is_ipv6"] = traffic_type == "ipv6"
            stream_name = f"From {direction_from} {ports_from} to {direction_to} {ports_to}. Packet number {0} to {traffic_parameters['IP']['dst']}"
            logger.info(f"Stream name: {stream_name}")
            stream = create_json_traffic_stream(spine_tg, traffic_parameters, stream_name, tc=dscp_to_tc(PerfConsts.DVS_LOSSLESS_TC, 2))
            stream_list.append(stream)
    create_json_traffic_file_with_stream_list(spine_tg, traffic_parameters, json_path, stream_list)
