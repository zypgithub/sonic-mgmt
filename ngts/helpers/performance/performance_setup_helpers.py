import logging
import logging.config
import allure
import json
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.thread_log_filter import redirect_thread_stdout, config_root_logger
from ngts.helpers.custom_catch_exception_thread import CatchExceptionThread, parse_threads_exceptions_at_join
from infra.tools.exceptions.test_issue import TestIssue
from ngts.helpers.performance.traffic_helpers import validate_bw, validate_tc

logger = logging.getLogger()


def apply_test_configuration(players, scenario, step="basic_test_configuration - set-up"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                                           action="apply test configuration",
                                           performance_clis_function_name="apply_configuration_file",
                                           performance_clis_function_args=(scenario,), step=step)
    configure_mloops(players)


def configure_mloops(players, step="basic_test_configuration - set-up"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="configure mloops",
                                           performance_clis_function_name="configure_mloops",
                                           performance_clis_function_args=(), step=step)


def save_base_configuration(players, step="basic_test_configuration - set-up"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                                           action="save base configuration",
                                           performance_clis_function_name="save_basic_configuration",
                                           performance_clis_function_args=(players,), step=step)


def restore_basic_configuration(players, step="basic_test_configuration - tear-down"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                                           action="restore base configuration",
                                           performance_clis_function_name="restore_basic_configuration",
                                           performance_clis_function_args=(), step=step)


def run_traffic(players, scenario, packet_size=4000, num_packets=8, is_ipv6=False, step="Running Traffic - Test body"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="run traffic",
                                           performance_clis_function_name="run_traffic",
                                           performance_clis_function_args=(scenario, packet_size, num_packets, is_ipv6),
                                           step=step)


def stop_traffic(players, step="Stopping Traffic - Tear down"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="stop traffic",
                                           performance_clis_function_name="stop_traffic",
                                           performance_clis_function_args=(),
                                           step=step)


def validate_traffic_results(players, test_name, scenario, samples_params_dict):
    config_root_logger()
    # only on dut
    dut_cli_object = players['dut']['cli']
    dut_hostname = dut_cli_object.chassis.get_hostname()
    with allure.step(f"Validating Traffic on DUT"):
        full_path = dut_cli_object.performance.validate_traffic(test_name, scenario, samples_params_dict)
    with open(full_path) as f:
        allure.attach(f.read(), f'Traffic Validation JSON results on dut - {dut_hostname}', allure.attachment_type.JSON)
        traffic_json = json.load(f)
    return traffic_json


def traffic_validation(players, test_name, scenario, bw_threshold,
                       samples_params_dict=PerfConsts.SAMPLES_PARAMS,
                       tc_occ_threshold=PerfConsts.OCC_AVG_TH, port_list=None):
    traffic_json = validate_traffic_results(players, test_name, scenario, samples_params_dict)
    validate_bw(traffic_json, bw_threshold)
    validate_tc(traffic_json, tc_occ_threshold)


def set_ibm(players, ibm_mode=True):
    '''
    Implementation pending
    '''
    pass


def set_port(players, port_list, shutdown=True):
    '''
    Implementation pending
    '''
    pass


def reboot_dut(players, system_check=False):
    '''
    Implementation pending
    '''
    pass


def get_ports_from_dut(cli_object):
    '''
    Implementation pending
    '''
    pass


def call_performance_function_with_threads(players, players_aliases, action,
                                           performance_clis_function_name,
                                           performance_clis_function_args, step):
    config_root_logger()
    players_aliases_str = ",".join(players_aliases)
    logging.info(f"Start {action} on {players_aliases_str}")
    threads_list = []
    for player_alias in players_aliases:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"Start {action} on player {player_alias}"):
            performance_method = get_obj_method(player_cli_obj.performance, performance_clis_function_name)
            thread = CatchExceptionThread(target=redirect_thread_stdout,
                                          args=(performance_method,
                                                performance_clis_function_args),
                                          name=player_alias)
            threads_list.append(thread)
    for th in threads_list:
        th.start()
    with allure.step(f"Check {action} on {players_aliases_str} was applied correctly"):
        parse_threads_exceptions_at_join(threads_list, players, step)
    logging.info(f"Finished {action} on {players_aliases_str}")


def get_obj_method(cli_obj, method_name):
    if hasattr(cli_obj, method_name):
        method = getattr(cli_obj, method_name)
        if callable(method):
            return method
    raise TestIssue(f"Failed to find a callable function with name \"{method_name}\" "
                    f"in {cli_obj.__class__.__name__}")
