import allure
import pytest
import os
from collections import defaultdict
from ngts.constants.constants import SonicConst, BugHandlerConst
from ngts.constants.performance_constants import Cl_Consts, PerfConsts, MRCConsts
from ngts.helpers.performance.performance_setup_helpers import apply_test_configuration, restore_basic_configuration, save_base_configuration
from ngts.performance_tests.srv6.utils.srv6_traffic_patterns import get_tg_bisection_traffic_params


def get_bisection_traffic(players, conf_args, traffic_type,
                          dut_interfaces_ipv6_configuration_dict, create_workload_stream,
                          upstream_ports, downstream_ports,
                          template_suite="traffic_packets_json_files"):
    traffic_jsons = {}
    tg_src_dst_port_bisection_pairs_dict = sort_bisection_pairs_by_tg_alias(players, upstream_ports, downstream_ports)
    for tg_alias, bisection_pairs in tg_src_dst_port_bisection_pairs_dict.items():
        get_tg_bisection_traffic_params(players, tg_alias, conf_args, traffic_type, template_suite, create_workload_stream,
                                        dut_interfaces_ipv6_configuration_dict, traffic_jsons, bisection_pairs)

    return traffic_jsons


def sort_bisection_pairs_by_tg_alias(players, upstream_ports, downstream_ports):
    ports = players['dut']['cli'].performance.get_right_left_ports_dict()
    left_ports = ports["left_ports"]
    right_ports = ports["right_ports"]
    upstream_to_downstream_port_bisection_pairs = list(zip(upstream_ports, downstream_ports))
    downstream_to_upstream_port_bisection_pairs = list(zip(downstream_ports, upstream_ports))
    all_bisection_pairs = upstream_to_downstream_port_bisection_pairs + downstream_to_upstream_port_bisection_pairs
    tg_src_dst_port_bisection_pairs_dict = defaultdict(list)
    for pair in all_bisection_pairs:
        if pair[0] in left_ports:
            tg_src_dst_port_bisection_pairs_dict[PerfConsts.LEFT_TG_ALIAS].append(pair)
        elif pair[0] in right_ports:
            tg_src_dst_port_bisection_pairs_dict[PerfConsts.RIGHT_TG_ALIAS].append(pair)
    return tg_src_dst_port_bisection_pairs_dict


@pytest.fixture(scope='class', autouse=True)
def conf_args(chip_type, players):
    sku = MRCConsts.HWSKU_BY_CHIP_TYPE[chip_type]["leaf"]
    is_cumulus = players["dut"].get("is_cumulus", False)
    conf_args = {
        "is_ipv6": True,
        "packet_size": 4096,
        "scenario": "srv6",
        "split_left": Cl_Consts.SRV6_SPLIT_LEFT_BY_CHIP_TYPE[chip_type],
        "split_right": Cl_Consts.SRV6_SPLIT_RIGHT_BY_CHIP_TYPE[chip_type],
        "speed": Cl_Consts.SRV6_SPEED_BY_CHIP_TYPE[chip_type] if is_cumulus else SonicConst.HWSKU_DOWNSTREAM_PORTS_SPEED[sku],
        "hwsku": sku,
        "dut_mac": players['dut']['cli'].performance.mac,
        "dut": "leaf",
        "chip_type": chip_type,
        "downlinks_tg": PerfConsts.RIGHT_TG_ALIAS,
        "template_path": os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                      PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, "srv6", "sonic")

    }
    return conf_args


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args):
    try:
        with allure.step('Save Players initial Configuration'):
            save_base_configuration(players)
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(players, scenario=conf_args["scenario"], conf_args=conf_args)
        yield
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            restore_basic_configuration(players)


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
