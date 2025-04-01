import allure
import pytest
from ngts.constants.constants import SonicConst
from ngts.constants.performance_constants import PerfConsts, MRCConsts, MongoDbConsts
from ngts.helpers.performance.performance_setup_helpers import apply_test_configuration
from ngts.performance_tests.srv6.conftest import get_tg_bisection_traffic_params


def get_bisection_traffic(players, conf_args, traffic_type,
                          dut_interfaces_ipv6_configuration_dict, create_workload_stream,
                          left_ports, right_ports,
                          template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    left_to_right_port_bisection_pairs = list(zip(left_ports, right_ports))
    right_to_left_port_bisection_pairs = list(zip(right_ports, left_ports))
    tg_src_dst_port_bisection_pairs_dict = {PerfConsts.LEFT_TG_ALIAS: left_to_right_port_bisection_pairs,
                                            PerfConsts.RIGHT_TG_ALIAS: right_to_left_port_bisection_pairs}
    for tg_alias, port_bisection_pairs in tg_src_dst_port_bisection_pairs_dict.items():
        get_tg_bisection_traffic_params(players, tg_alias, conf_args, traffic_type, template_suite, create_workload_stream,
                                        dut_interfaces_ipv6_configuration_dict, traffic_jsons, port_bisection_pairs)

    return traffic_jsons


@pytest.fixture(scope='class', autouse=True)
def conf_args(chip_type, players):
    sku = MRCConsts.HWSKU_BY_CHIP_TYPE[chip_type]["leaf"]
    conf_args = {
        "is_ipv6": True,
        "packet_size": 4096,
        "scenario": "srv6",
        "speed": SonicConst.HWSKU_DOWNSTREAM_PORTS_SPEED[sku],
        "hwsku": sku,
        "dut_mac": players['dut']['cli'].performance.get_mac(),
        "dut": "leaf",
        "chip_type": chip_type,
        "downlinks_tg": PerfConsts.RIGHT_TG_ALIAS
    }
    return conf_args


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args):
    with allure.step("Apply Test configuration on all Players"):
        apply_test_configuration(players, scenario=conf_args["scenario"], conf_args=conf_args)
    yield


@pytest.fixture(scope='function', autouse=False)
def cleanup_trimming_threshold(players, conf_args):
    """
    to remove zero scheduler configuration
    """
    yield
    cli_obj = players['dut']['cli']
    cli_obj.general.reload_configuration(force=True)
    cli_obj.general.verify_dockers_are_up()
    cli_obj.trimming.configure_packets_aging()
