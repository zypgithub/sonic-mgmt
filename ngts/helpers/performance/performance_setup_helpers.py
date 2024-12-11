import logging
import logging.config
import allure
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.thread_log_filter import redirect_thread_stdout, config_root_logger
from ngts.helpers.custom_catch_exception_thread import CatchExceptionThread, parse_threads_exceptions_at_join

logger = logging.getLogger()


def apply_test_configuration(players, scenario, step="basic_test_configuration - set-up"):
    config_root_logger()
    logging.info("Applying test configuration on all players")
    threads_list = []
    for player_alias in PerfConsts.PERF_SETUP_PLAYERS_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"Start apply configuration on player {player_alias}"):
            thread = CatchExceptionThread(target=redirect_thread_stdout,
                                          args=(player_cli_obj.performance.apply_configuration_file, (scenario,)),
                                          name=player_alias)
            threads_list.append(thread)
    for th in threads_list:
        th.start()
    with allure.step("Check test configuration on players was applied correctly"):
        parse_threads_exceptions_at_join(threads_list, players, step)
    logging.info("Finished applying test configuration on all Players")


def save_base_configuration(players, step="basic_test_configuration - set-up"):
    config_root_logger()
    threads_list = []
    for player_alias in PerfConsts.PERF_SETUP_PLAYERS_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"Save configuration on player {player_alias}"):
            thread = CatchExceptionThread(target=redirect_thread_stdout,
                                          args=(player_cli_obj.performance.save_basic_configuration, (players,)),
                                          name=player_alias)
            threads_list.append(thread)
    for th in threads_list:
        th.start()

    with allure.step("Check configuration on Players had been Saved"):
        parse_threads_exceptions_at_join(threads_list, players, step)


def restore_basic_configuration(players, step="basic_test_configuration - tear-down"):
    config_root_logger()
    threads_list = []
    for player_alias in PerfConsts.PERF_SETUP_PLAYERS_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"Restoring Initial Configuration on Player {player_alias}"):
            thread = CatchExceptionThread(target=redirect_thread_stdout,
                                          args=(player_cli_obj.performance.restore_basic_configuration, ()),
                                          name=player_alias)
            threads_list.append(thread)

    for th in threads_list:
        th.start()

    with allure.step("Check configuration on Players had been Restored"):
        parse_threads_exceptions_at_join(threads_list, players, step)


def run_traffic(players, scenario, packet_size=4000, num_packets=8, is_ipv6=False, step="Running Traffic - Test body"):
    config_root_logger()
    packet_size = int(packet_size)
    threads_list = []
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"Running Traffic on Player {player_alias}"):
            thread = CatchExceptionThread(target=redirect_thread_stdout,
                                          args=(player_cli_obj.performance.run_traffic, (scenario, packet_size, num_packets, is_ipv6, )),
                                          name=player_alias)
            threads_list.append(thread)

    for th in threads_list:
        th.start()
    with allure.step("Check Traffic had been started"):
        parse_threads_exceptions_at_join(threads_list, players, step)


def stop_traffic(players, step="Stopping Traffic - Tear down"):
    config_root_logger()
    threads_list = []
    for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"Stopping Traffic on Player {player_alias}"):
            thread = CatchExceptionThread(target=redirect_thread_stdout,
                                          args=(player_cli_obj.performance.stop_traffic, ()),
                                          name=player_alias)
            threads_list.append(thread)
    for th in threads_list:
        th.start()

    with allure.step(f"Check traffic on players was stopped"):
        parse_threads_exceptions_at_join(threads_list, players, step)


def validate_traffic_results(players, scenario):
    config_root_logger()
    # only on dut
    dut_cli_object = players['dut']['cli']
    with allure.step(f"Validating Traffic on DUT"):
        dut_cli_object.performance.validate_traffic(scenario)


def traffic_validation(players, scenario, b_w_threshold, port_list=None, time_duration=60):
    '''
    Implementation pending
    '''
    pass


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
