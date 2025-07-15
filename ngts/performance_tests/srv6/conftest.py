import copy
import os
import random
import pytest
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts
from ngts.constants.constants import CliType
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli
from ngts.helpers.performance.performance_setup_helpers import skip_test_on_unsupported_os


@pytest.fixture(scope='module', autouse=True)
def skip_test_conditionally(players):
    skip_test_on_unsupported_os(players['dut']['cli'], CliType.NVUE)
    skip_test_on_unsupported_os(players['dut']['cli'], CliType.DVS)
    yield


def get_upstream_downstream_port_group_df(players, upstream_ports_num, downstream_ports_num):
    """
    This function creates a port group dataframe for the upstream and downstream groups.
    The ports are selected consecutively from the left and right ports.

    Parameters:
        players: dictionary containing the players
        upstream_ports_num: number of ports in the upstream group
        downstream_ports_num: number of ports in the downstream group
    Returns:
        upstream: list of ports in the upstream group
        downstream: list of ports in the downstream group
        port_group_df: list of dictionaries containing the port and the port group name
    """
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports = copy.deepcopy(ports["left_ports"])
    right_ports = copy.deepcopy(ports["right_ports"])
    upstream_start_index = random.randint(0, len(left_ports) - upstream_ports_num)
    upstream_end_index = upstream_start_index + upstream_ports_num
    downstream_start_index = random.randint(0, len(right_ports) - downstream_ports_num)
    downstream_end_index = downstream_start_index + downstream_ports_num
    upstream = left_ports[upstream_start_index:upstream_end_index]
    downstream = right_ports[downstream_start_index:downstream_end_index]
    sdk_port_list_upstream = players['dut']['cli'].performance.get_sdk_ports(upstream)
    sdk_port_list_downstream = players['dut']['cli'].performance.get_sdk_ports(downstream)
    for port in sdk_port_list_upstream:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "upstream"})
    for port in sdk_port_list_downstream:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "downstream"})
    return upstream, downstream, port_group_df


def get_upstream_downstream_groups_port_group_df(players, upstream_ports_num, downstream_ports_num, num_of_groups):
    """
    This function creates a port group dataframe for the upstream and downstream groups.
    The ports are selected consecutively from the left and right ports.

    Parameters:
        players: dictionary containing the players
        upstream_ports_num: number of ports in the upstream group
        downstream_ports_num: number of ports in the downstream group
    Returns:
        upstream: list of ports in the upstream group
        downstream: list of ports in the downstream group
        port_group_df: list of dictionaries containing the port and the port group name
    """
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports = copy.deepcopy(ports["left_ports"])
    right_ports = copy.deepcopy(ports["right_ports"])
    upstream_group_size = upstream_ports_num * num_of_groups
    downstream_group_size = downstream_ports_num * num_of_groups
    upstream_start_index = random.randint(0, len(left_ports) - upstream_group_size)
    upstream_end_index = upstream_start_index + upstream_group_size
    downstream_start_index = random.randint(0, len(right_ports) - downstream_group_size)
    downstream_end_index = downstream_start_index + downstream_group_size
    upstream = left_ports[upstream_start_index:upstream_end_index]
    downstream = right_ports[downstream_start_index:downstream_end_index]
    upstream_groups = split_into_subsets(upstream, upstream_ports_num)
    downstream_groups = split_into_subsets(downstream, downstream_ports_num)
    for i in range(num_of_groups):
        sdk_port_list_upstream = players['dut']['cli'].performance.get_sdk_ports(upstream_groups[i])
        sdk_port_list_downstream = players['dut']['cli'].performance.get_sdk_ports(downstream_groups[i])
        for port in sdk_port_list_upstream:
            port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: f"upstream_group_{i + 1}"})
        for port in sdk_port_list_downstream:
            port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: f"downstream_group_{i + 1}"})
    return upstream_groups, downstream_groups, port_group_df


def split_into_subsets(lst, subset_size):
    return [lst[i:i + subset_size] for i in range(0, len(lst), subset_size)]


def get_leaf_many_to_few_port_group_df(players, M, num_of_ingress_ports):
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports = copy.deepcopy(ports["left_ports"])
    right_ports = copy.deepcopy(ports["right_ports"])
    egress_ports_num = num_of_ingress_ports // M
    num_of_egress_ports_for_each_tg = egress_ports_num // 2
    num_of_ingress_ports_for_each_tg = num_of_ingress_ports // 2
    total_num_of_ports_for_each_tg = num_of_egress_ports_for_each_tg + num_of_ingress_ports_for_each_tg
    plus_egress_ports_num = 0 if egress_ports_num % 2 == 0 else 1
    left_start_index = random.randint(0, len(left_ports) - total_num_of_ports_for_each_tg - plus_egress_ports_num)
    right_start_index = random.randint(0, len(right_ports) - total_num_of_ports_for_each_tg)
    left_egress_ports_start_index = left_start_index
    right_egress_ports_start_index = right_start_index
    left_egress_ports_end_index = left_egress_ports_start_index + num_of_egress_ports_for_each_tg + plus_egress_ports_num
    right_egress_ports_end_index = right_egress_ports_start_index + num_of_egress_ports_for_each_tg
    left_ingress_ports_start_index = left_egress_ports_end_index
    right_ingress_ports_start_index = right_egress_ports_end_index
    left_ingress_ports_end_index = left_ingress_ports_start_index + num_of_ingress_ports_for_each_tg
    right_ingress_ports_end_index = right_ingress_ports_start_index + num_of_ingress_ports_for_each_tg
    left_egress_ports, right_egress_ports = left_ports[left_egress_ports_start_index:left_egress_ports_end_index], \
        right_ports[right_egress_ports_start_index:right_egress_ports_end_index]
    left_ingress_ports, right_ingress_ports = left_ports[left_ingress_ports_start_index:left_ingress_ports_end_index], \
        right_ports[right_ingress_ports_start_index:right_ingress_ports_end_index]
    egress_ports = left_egress_ports + right_egress_ports
    ingress_ports = left_ingress_ports + right_ingress_ports
    sdk_port_list_egress = players['dut']['cli'].performance.get_sdk_ports(egress_ports)
    sdk_port_list_ingress = players['dut']['cli'].performance.get_sdk_ports(ingress_ports)
    for port in sdk_port_list_egress:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "egress_ports"})
    for port in sdk_port_list_ingress:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "ingress_ports"})
    return egress_ports, ingress_ports, port_group_df


def get_spine_many_to_few_port_group_df(players, M):
    port_group_df = []
    ports = players['dut']['cli'].performance.get_dut_ports()
    dut_ports = copy.deepcopy(ports)
    random.shuffle(dut_ports)
    egress_ports_num = len(dut_ports) // M
    egress_ports = dut_ports[:egress_ports_num]
    ingress_ports = ports
    sdk_port_list_egress = players['dut']['cli'].performance.get_sdk_ports(egress_ports)
    sdk_port_list_ingress = players['dut']['cli'].performance.get_sdk_ports(ingress_ports)
    for port in sdk_port_list_egress:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "egress_ports"})
    for port in sdk_port_list_ingress:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "ingress_ports"})
    return egress_ports, ingress_ports, port_group_df


@pytest.fixture(scope="class", autouse=False)
def victim_flow_port_group_df(request, players):
    request.getfixturevalue('basic_setup_configuration')
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    victim_ports_num = MRCConsts.VICTIM_PORTS_NUM
    left_ports = copy.deepcopy(ports["left_ports"])
    right_ports = copy.deepcopy(ports["right_ports"])
    bisection_left, many_to_one_ingress_ports = left_ports[:victim_ports_num], left_ports[victim_ports_num:2 * victim_ports_num - 1]
    bisection_right, many_to_one_egress_ports = right_ports[:victim_ports_num], right_ports[victim_ports_num:victim_ports_num + 1]
    egress_port = many_to_one_egress_ports[0]
    many_to_one_ingress_ports.append(egress_port)
    sdk_port_list_bisection_left = players['dut']['cli'].performance.get_sdk_ports(bisection_left)
    sdk_port_list_bisection_right = players['dut']['cli'].performance.get_sdk_ports(bisection_right)
    sdk_port_list_many_to_one_ingress_ports = players['dut']['cli'].performance.get_sdk_ports(many_to_one_ingress_ports)
    sdk_port_list_many_to_one_egress_ports = players['dut']['cli'].performance.get_sdk_ports(many_to_one_egress_ports)
    for port in sdk_port_list_bisection_left:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "bisection_left"})
    for port in sdk_port_list_bisection_right:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "bisection_right"})
    for port in sdk_port_list_many_to_one_ingress_ports:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "many_to_one_ingress_ports"})
    for port in sdk_port_list_many_to_one_egress_ports:
        port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: "many_to_one_egress_port"})
    return bisection_left, bisection_right, many_to_one_ingress_ports, many_to_one_egress_ports, port_group_df


def get_spine_downstream_groups_port_group_df(players, downstream_ports_num, num_of_groups):
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports = copy.deepcopy(ports["left_ports"])
    right_ports = copy.deepcopy(ports["right_ports"])
    downstream_group_size = downstream_ports_num * num_of_groups
    downstream_start_index = random.randint(0, len(right_ports) - downstream_group_size)
    downstream_end_index = downstream_start_index + downstream_group_size
    downstream_1 = left_ports[downstream_start_index:downstream_end_index]
    downstream_2 = right_ports[downstream_start_index:downstream_end_index]
    downstream_groups_1 = split_into_subsets(downstream_1, downstream_ports_num)
    downstream_groups_2 = split_into_subsets(downstream_2, downstream_ports_num)
    for i in range(num_of_groups):
        sdk_port_list_downstream_groups_1 = players['dut']['cli'].performance.get_sdk_ports(downstream_groups_1[i])
        sdk_port_list_downstream_groups_2 = players['dut']['cli'].performance.get_sdk_ports(downstream_groups_2[i])
        for port in sdk_port_list_downstream_groups_1:
            port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: f"downstream_group_1_{i + 1}"})
        for port in sdk_port_list_downstream_groups_2:
            port_group_df.append({"port": port, MongoDbConsts.PORT_GROUP_NAME: f"downstream_group_2_{i + 1}"})
    return downstream_groups_1, downstream_groups_2, port_group_df


def config_optimal_trimming_size(chip_type, cli_objects):
    if chip_type == "SPC5":
        opt_ts = os.environ.get("OPT_TS", default=MRCConsts.OPT_TS_DEFAULT)
        cli_objects.dut.trimming.enable_trimming_on_lossy_queue()
        cli_objects.dut.trimming.configure_trimming_size(opt_ts)


@pytest.fixture(scope="function", autouse=False)
def cleanup_ports_shaper(cli_objects):
    yield
    for tg_alias in PerfConsts.TG_ALIAS_LIST:
        cli_objects[tg_alias].performance.configure_ports_shaper(shaper_value=MRCConsts.SHAPER_VALUE_AFTER_TEST)


def get_trimming_tests_skip_condition(cli_obj, actual_chip_type, unsupported_chip_type):
    condition = actual_chip_type == unsupported_chip_type and isinstance(cli_obj, SonicCli)
    skip_message = f"This test is not supported on {unsupported_chip_type} on SONiC OS"
    return condition, skip_message
