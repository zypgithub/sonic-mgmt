import pytest
import time
import logging
import os
from ngts.constants.performance_constants import PerfConsts, PowerConsts, MongoDbConsts
from ngts.constants.constants import BugHandlerConst
from ngts.helpers.performance.traffic_helpers import (create_json_traffic_file, create_json_traffic_stream,
                                                      create_json_traffic_file_with_stream_list)

logger = logging.getLogger()
TESTS_SCENARIO = "spcx_ra"


def get_spcx_ra_spine_traffic(players, conf_args, template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    pkt_size = PerfConsts.PACKET_SIZE_LIST[0]
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 TESTS_SCENARIO, f"{player_alias}_{TESTS_SCENARIO.replace('/', '_')}_{pkt_size}.json")
        traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=TESTS_SCENARIO,
                                                                               conf_args=conf_args)
        create_json_traffic_file(player_alias=player_alias, traffic_parameters=traffic_parameters, json_path=json_path)
        traffic_jsons[player_alias] = json_path
    return traffic_jsons


def get_spcx_ra_leaf_traffic(players, conf_args, template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    pkt_size = PerfConsts.PACKET_SIZE_LIST[0]
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 TESTS_SCENARIO, f"{player_alias}_{TESTS_SCENARIO.replace('/', '_')}_{pkt_size}.json")
        traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=TESTS_SCENARIO,
                                                                               conf_args=conf_args)
        if player_alias == conf_args["host"]:
            create_json_traffic_file(player_alias=player_alias,
                                     traffic_parameters=traffic_parameters, json_path=json_path)
        else:
            get_spine_to_leaf_stream_list(players, player_alias, conf_args, traffic_parameters, json_path)
        traffic_jsons[player_alias] = json_path
    return traffic_jsons


def get_spine_to_leaf_stream_list(players, spine_tg, conf_args, traffic_parameters, json_path):
    dut_configuration = players['dut']['cli'].performance.get_device_configuration(conf_args=conf_args)
    leaf_dst_ips = list(dut_configuration["right_side_ports_to_ip_dict"].values())
    stream_list = []
    for ip in leaf_dst_ips:
        stream_name = f"spine_to_leaf_ip_{ip}"
        traffic_parameters["IP"]["dst"] = ip
        stream = create_json_traffic_stream(spine_tg, traffic_parameters, stream_name)
        stream_list.append(stream)
    create_json_traffic_file_with_stream_list(spine_tg, traffic_parameters, json_path, stream_list)


@pytest.fixture(scope='class', autouse=False)
def port_group_df(request, players):
    request.getfixturevalue('basic_setup_configuration')
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()

    if ports['left_ports'] == [] or ports['right_ports'] == []:
        logging.info("No ports found for left and right ports retrying after a delay of 10 seconds")
        # TODO: remove this and implement split by middle technique to get the ports instead
        time.sleep(10)
        ports = players['dut']['cli'].performance.get_right_left_ports_dict()

    sdk_ports_left = players['dut']['cli'].performance.get_sdk_ports(ports["left_ports"])
    sdk_ports_right = players['dut']['cli'].performance.get_sdk_ports(ports["right_ports"])
    for port in sdk_ports_left:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "left_ports"})
    for port in sdk_ports_right:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "right_ports"})
    return port_group_df
