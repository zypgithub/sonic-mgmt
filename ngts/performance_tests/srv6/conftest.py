import copy
import os
import random
import pytest
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts
from ngts.helpers.performance.traffic_helpers import create_json_traffic_file_with_stream_list
from ngts.constants.constants import CliType
from ngts.helpers.performance.performance_setup_helpers import skip_test_on_unsupported_os


@pytest.fixture(scope='module', autouse=True)
def skip_test_conditionally(players):
    skip_test_on_unsupported_os(players['dut']['cli'], CliType.NVUE)
    skip_test_on_unsupported_os(players['dut']['cli'], CliType.DVS)
    yield


def get_many_to_few_traffic(players, conf_args, traffic_type, dut_interfaces_ipv6_configuration_dict,
                            egress_ports, ingress_ports, create_workload_stream, congestion=False,
                            template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports, right_ports = ports["left_ports"], ports["right_ports"]
    tg_src_ports = {PerfConsts.LEFT_TG_ALIAS: left_ports,
                    PerfConsts.RIGHT_TG_ALIAS: right_ports}
    for tg_alias, src_ports in tg_src_ports.items():
        get_tg_many_to_few_traffic_params(players, tg_alias, conf_args,
                                          traffic_type, template_suite, create_workload_stream,
                                          dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                          egress_ports, ingress_ports, src_ports=src_ports,
                                          congestion=congestion)
    return traffic_jsons


def get_tg_bisection_traffic_params(players, player_alias, conf_args, traffic_type, template_suite, create_workload_stream,
                                    dut_interfaces_ipv6_configuration_dict, traffic_jsons, port_bisection_pairs):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_bisection.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    for (src_port, dst_port) in port_bisection_pairs:
        create_workload_stream(player_alias, player_cli_obj, [src_port], dst_port, traffic_parameters, traffic_type,
                               mloops_dict, dut_interfaces_ipv6_configuration_dict,
                               stream_list=stream_list, ecn_enabled=is_ecn_marked(player_alias, conf_args))
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def is_ecn_marked(player_alias, conf_args):
    if conf_args.get("dut") == "leaf" and conf_args.get("downlinks_tg") == player_alias:
        return False
    else:
        return True


def get_tg_round_robin_traffic_params(players, player_alias, conf_args, traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      cycle_ports_pairs, src_ports, dst_ports, bisection_traffic):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_round_robin.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    ecn_enabled = is_ecn_marked(player_alias, conf_args)
    stream_list = []
    for (port1, port2) in cycle_ports_pairs:
        ports_cycle_flow = get_ports_cycle_flow_by_tg(port1, port2, src_ports, dst_ports, bisection_traffic)
        for (src_port, dst_port) in ports_cycle_flow:
            create_workload_stream(player_alias, player_cli_obj, [src_port], dst_port, traffic_parameters, traffic_type,
                                   mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                   stream_list=stream_list, ecn_enabled=ecn_enabled)
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


def get_tg_many_to_few_traffic_params(players, player_alias, conf_args,
                                      traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      egress_ports, ingress_ports, src_ports, congestion):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_many_to_few.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    tg_ingress_ports = get_ingress_ports_by_tg(ingress_ports, src_ports)
    if tg_ingress_ports:
        for egress_port in egress_ports:
            create_workload_stream(player_alias, player_cli_obj, tg_ingress_ports, egress_port, traffic_parameters, traffic_type,
                                   mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                   stream_list=stream_list, congestion=congestion, ecn_enabled=True)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_many_to_one_traffic(players, conf_args, traffic_type, dut_interfaces_ipv6_configuration_dict,
                            egress_ports, ingress_ports, create_workload_stream, congestion=False,
                            template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports, right_ports = ports["left_ports"], ports["right_ports"]
    tg_src_ports = {PerfConsts.LEFT_TG_ALIAS: left_ports,
                    PerfConsts.RIGHT_TG_ALIAS: right_ports}
    ingress_egress_ports_pairing = get_ingress_egress_ports_pairing(ingress_ports, egress_ports)
    for tg_alias, src_ports in tg_src_ports.items():
        get_tg_many_to_one_traffic_params(players, tg_alias, conf_args,
                                          traffic_type, template_suite, create_workload_stream,
                                          dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                          ingress_egress_ports_pairing, src_ports=src_ports,
                                          congestion=congestion)
    return traffic_jsons


def get_tg_many_to_one_traffic_params(players, player_alias, conf_args,
                                      traffic_type, template_suite, create_workload_stream,
                                      dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                      ingress_egress_ports_pairing, src_ports, congestion):
    player_cli_obj = players[player_alias]['cli']
    traffic_parameters = player_cli_obj.performance.get_traffic_parameters(scenario=conf_args["scenario"],
                                                                           conf_args=conf_args)
    json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                             conf_args["scenario"], f"{player_alias}_{conf_args['scenario']}_many_to_one.json")
    mloops_dict = dict(player_cli_obj.performance.mloops)
    stream_list = []
    for ingress_ports, egress_port in ingress_egress_ports_pairing:
        tg_ingress_ports = get_ingress_ports_by_tg(ingress_ports, src_ports)
        if tg_ingress_ports:
            create_workload_stream(player_alias, player_cli_obj, tg_ingress_ports, egress_port, traffic_parameters, traffic_type,
                                   mloops_dict, dut_interfaces_ipv6_configuration_dict,
                                   stream_list=stream_list, congestion=congestion, ecn_enabled=True)
    create_json_traffic_file_with_stream_list(player_alias, traffic_parameters, json_path, stream_list)
    traffic_jsons[player_alias] = json_path


def get_ingress_egress_ports_pairing(ingress_ports, egress_ports):
    sublist_size = len(ingress_ports) // len(egress_ports)
    ingress_egress_ports_pairing = [ingress_ports[i:i + sublist_size] for i in range(0, len(ingress_ports), sublist_size)]
    return list(zip(ingress_egress_ports_pairing, egress_ports))


def get_ingress_ports_by_tg(ingress_ports, src_ports):
    return list(set(src_ports).intersection(ingress_ports))


def get_round_robin_traffic(players, conf_args, traffic_type, upstream, downstream, bisection_traffic,
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
    tg_src_dst_ports_dict = {PerfConsts.LEFT_TG_ALIAS: (left_ports, right_ports),
                             PerfConsts.RIGHT_TG_ALIAS: (right_ports, left_ports)}
    for tg_alias, (src_ports, dst_ports) in tg_src_dst_ports_dict.items():
        get_tg_round_robin_traffic_params(players, tg_alias, conf_args,
                                          traffic_type, template_suite, create_workload_stream,
                                          dut_interfaces_ipv6_configuration_dict, traffic_jsons,
                                          cycle_ports_pairs, src_ports=src_ports, dst_ports=dst_ports,
                                          bisection_traffic=bisection_traffic)
    return traffic_jsons


def get_cycle_ports_pairs(upstream, downstream):
    round_len = len(upstream)
    cycle_pairing = []
    for round in range(round_len):
        for i in range(round_len):
            if upstream[i] != downstream[(i + round) % round_len]:
                cycle_pairing.append((upstream[i], downstream[(i + round) % round_len]))
    return cycle_pairing


@pytest.fixture(scope="class", autouse=False)
def upstream_downstream_port_group_df(request, players, chip_type):
    request.getfixturevalue('basic_setup_configuration')
    port_group_df = []
    num_of_ports = MRCConsts.UPSTREAM_DOWNSTREAM_NUM_OF_PORTS_BY_CHIP_TYPE[chip_type]
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports = copy.deepcopy(ports["left_ports"])
    right_ports = copy.deepcopy(ports["right_ports"])
    random.shuffle(left_ports)
    random.shuffle(right_ports)
    upstream, downstream = left_ports[:num_of_ports], right_ports[:num_of_ports]
    for port in upstream:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "upstream"})
    for port in downstream:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "downstream"})
    return upstream, downstream, port_group_df


@pytest.fixture(scope="class", autouse=False)
def victim_flow_port_group_df(request, players):
    request.getfixturevalue('basic_setup_configuration')
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    victim_ports_num = MRCConsts.VICTIM_PORTS_NUM
    left_ports = copy.deepcopy(ports["left_ports"])
    right_ports = copy.deepcopy(ports["right_ports"])
    random.shuffle(left_ports)
    random.shuffle(right_ports)
    bisection_left, many_to_one_ingress_ports = left_ports[:victim_ports_num], left_ports[victim_ports_num:2 * victim_ports_num - 1]
    bisection_right, many_to_one_egress_ports = right_ports[:victim_ports_num], right_ports[victim_ports_num:victim_ports_num + 1]
    egress_port = many_to_one_egress_ports[0]
    many_to_one_ingress_ports.append(egress_port)
    for port in bisection_left:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "bisection_left"})
    for port in bisection_right:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "bisection_right"})
    for port in many_to_one_ingress_ports:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "many_to_one_ingress_ports"})
    for port in many_to_one_egress_ports:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "many_to_one_egress_port"})
    return bisection_left, bisection_right, many_to_one_ingress_ports, many_to_one_egress_ports, port_group_df


@pytest.fixture(scope="class")
def spine_downstream_port_group_df(players):
    port_group_df = []
    downstream = copy.deepcopy(players['dut']['cli'].performance.get_dut_ports())
    for port in downstream:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "downstream"})
    return downstream, port_group_df


@pytest.fixture(scope="class", autouse=False)
def config_optimal_trimming_size(cli_objects):
    opt_ts = os.environ.get("OPT_TS", default=MRCConsts.OPT_TS_DEFAULT)
    cli_objects.dut.trimming.enable_trimming_on_lossy_queue()
    cli_objects.dut.trimming.configure_trimming_size(opt_ts)
    yield
