import allure
import pytest
from ngts.constants.performance_constants import PerfConsts, MRCConsts, MongoDbConsts
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name, add_test_mongo_metadata
from ngts.helpers.performance.performance_setup_helpers import apply_test_configuration
from ngts.performance_tests.srv6.conftest import get_tg_traffic_params


def get_bisection_traffic(players, conf_args, traffic_type,
                          dut_interfaces_ipv6_configuration_dict, create_workload_stream,
                          template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_to_right_port_bisection_pairs = list(zip(ports["left_ports"], ports["right_ports"]))

    right_to_left_port_bisection_pairs = list(zip(ports["right_ports"], ports["left_ports"]))
    get_tg_traffic_params(players, PerfConsts.LEFT_TG_ALIAS, conf_args, traffic_type, template_suite, create_workload_stream,
                          dut_interfaces_ipv6_configuration_dict, traffic_jsons, left_to_right_port_bisection_pairs)
    get_tg_traffic_params(players, PerfConsts.RIGHT_TG_ALIAS, conf_args, traffic_type, template_suite, create_workload_stream,
                          dut_interfaces_ipv6_configuration_dict, traffic_jsons, right_to_left_port_bisection_pairs)

    return traffic_jsons


@pytest.fixture(scope='class', autouse=True)
def conf_args(chip_type, players):
    conf_args = {
        "is_ipv6": True,
        "packet_size": 4096,
        "scenario": "srv6",
        "hwsku": MRCConsts.HWSKU_BY_CHIP_TYPE[chip_type]["leaf"],
        "dut_mac": players['dut']['cli'].performance.get_mac()
    }
    return conf_args


@pytest.fixture(scope='class', autouse=False)
def port_group_df(request, players):
    request.getfixturevalue('basic_setup_configuration')
    port_group_df = []
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    for port in ports["left_ports"]:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "left_ports"})
    for port in ports["right_ports"]:
        port_group_df.append({"port": players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "right_ports"})
    return port_group_df


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args):
    with allure.step("Apply Test configuration on all Players"):
        apply_test_configuration(players, scenario=conf_args["scenario"], conf_args=conf_args)
    yield


@pytest.fixture(scope='function', autouse=True)
def update_test_mongo_metadata(request, players, is_ipv6, port_group_df):
    test_name = get_perf_test_name(request.node.name, is_ipv6)
    add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: "srv6",
                                        MongoDbConsts.PORT_GROUP_DF: port_group_df})
    yield
