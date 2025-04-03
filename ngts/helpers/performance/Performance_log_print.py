import os
import allure
from pytest import File
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.thread_log_filter import config_root_logger
import logging

logger = logging.getLogger()


def print_players_logs(players_info, players_list=PerfConsts.PERF_SETUP_PLAYERS_ALIASES, print_to_stdout=False):
    config_root_logger()
    for player in players_list:
        player_hostname = players_info[player]['cli'].chassis.get_hostname()
        try:
            log_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", "log_files", f"{player}.log")
            with open(log_path, 'r') as f:
                allure.attach(f.read(), f'Logs for {player} - {player_hostname}', allure.attachment_type.TEXT)
            if print_to_stdout:
                print(f'################  Logs for {player} - {player_hostname}:  ################')
                with open(log_path, 'r') as f:
                    print(f.read())
                    print('-' * 40)  # Separator for each player's logs
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Log file for {player} not found")


def remove_players_logs(players_list=PerfConsts.PERF_SETUP_PLAYERS_ALIASES):
    for player in players_list:
        log_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", "log_files", f"{player}.log")
        if os.path.exists(log_path):
            os.remove(log_path)
