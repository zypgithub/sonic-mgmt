import logging
import os

import allure

from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts

logger = logging.getLogger()


def print_players_logs(players_info, players_list=PerfConsts.PERF_SETUP_PLAYERS_ALIASES, print_to_stdout=False):
    """Attach per-player CLI log files to Allure; missing files are skipped (no teardown failure)."""
    for player in players_list:
        player_hostname = players_info[player]['cli'].chassis.get_hostname()
        log_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", "log_files", f"{player}.log")
        if not os.path.isfile(log_path):
            msg = f"No log file at {log_path} for {player} ({player_hostname})"
            logger.warning(msg)
            allure.attach(msg, f'Logs for {player} - {player_hostname} (missing)', allure.attachment_type.TEXT)
            if print_to_stdout:
                print(f'################  {msg}  ################')
                print('-' * 40)
            continue
        with open(log_path, 'r') as f:
            body = f.read()
        allure.attach(body, f'Logs for {player} - {player_hostname}', allure.attachment_type.TEXT)
        if print_to_stdout:
            print(f'################  Logs for {player} - {player_hostname}:  ################')
            print(body)
            print('-' * 40)  # Separator for each player's logs


def remove_players_logs(players_list=PerfConsts.PERF_SETUP_PLAYERS_ALIASES):
    for player in players_list:
        log_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", "log_files", f"{player}.log")
        if os.path.exists(log_path):
            os.remove(log_path)
