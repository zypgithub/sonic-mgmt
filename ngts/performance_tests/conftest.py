import json
import re
import pytest
import allure
import os
import logging
import time
from datetime import datetime
from ngts.helpers.performance.performance_setup_helpers import configure_mloops, stop_traffic
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs
from ngts.constants.constants import PytestConst
from ngts.constants.performance_constants import MongoDbConsts, PowerConsts, PerfConsts, ValidationConsts
from ngts.helpers.performance.performance_db_helpers import (create_performance_db_template,
                                                             create_test_validation_entry_to_db,
                                                             add_test_mongo_metadata, get_perf_test_name)
from ngts.helpers.thread_log_filter import config_root_logger
from infra.tools.exceptions.test_issue import TestIssue


@pytest.fixture(scope="session", autouse=True)
def config_root_logger_fixture():
    config_root_logger()


@pytest.fixture(scope="session")
def performance_parameters(request):
    """
    Method for getting the file location of the parameters from nv_optimizer
    """
    if request.config.getoption('--parameter_file_location'):
        try:
            # Convert params string to JSON object
            file_location = request.config.getoption('--parameter_file_location')
            with open(file_location, 'r') as file:
                params_json = json.load(file)
            return params_json["parameter_set"]
        except json.JSONDecodeError as e:
            raise TestIssue(f"Failed to parse params as JSON: {e}")
    return False


@pytest.fixture(scope="session")
def cleanup(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: app_extension_dict
    """
    if request.config.getoption(PytestConst.run_cleanup_only_arg):
        return True
    return False


@pytest.fixture(scope="session")
def init(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: app_extension_dict
    """
    if request.config.getoption(PytestConst.run_config_only_arg):
        return True
    return False


@pytest.fixture(scope='session', autouse=True)
def power_thresholds_by_chip_type(chip_type):
    return PowerConsts.POWER_TH_PER_ASIC[chip_type]


@pytest.fixture(scope="session")
def is_ipv6(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: app_extension_dict
    """
    if request.config.getoption('--is_ipv6'):
        return True
    return False


@pytest.fixture(scope='function', autouse=True)
def disable_sysdump_at_test_faliure(request):
    with allure.step('Disable default sysdump generation'):
        os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "False"


@pytest.fixture(scope='function', autouse=True)
def basic_test_configuration(request, players):
    request.getfixturevalue('basic_setup_configuration')
    try:
        with allure.step('Configure Mloops on Traffic Generators'):
            configure_mloops(players)
        yield
        with allure.step('Stop Traffic on Traffic Generators'):
            stop_traffic(players)
    except Exception as e:
        raise e
    finally:
        test_was_skipped = request.node.rep_call.skipped if hasattr(request.node, 'rep_call') else False
        if not test_was_skipped:
            with allure.step(f"Attaching Players Logs to Allure"):
                print_players_logs(print_to_stdout=True, players_info=players)
                remove_players_logs()


@pytest.fixture(scope='function', autouse=True)
def os_ports_name_mapping_df(request, players, is_ipv6):
    request.getfixturevalue('basic_setup_configuration')
    os_ports_name_mapping_df = players['dut']['cli'].performance.get_os_ports_name_mapping()
    test_name = get_perf_test_name(request, is_ipv6)
    add_test_mongo_metadata(test_name,
                            {ValidationConsts.OS_PORTS_NAME_MAPPING_DATAFRAME:
                                os_ports_name_mapping_df})
    return os_ports_name_mapping_df


@pytest.fixture(scope='session', autouse=True)
def create_mongo_db_template_file(players, session_id, setup_name):
    create_performance_db_template(players, session_id, setup_name)


@pytest.fixture(scope='function', autouse=True)
def update_test_data_in_mongo_db(request, players, is_ipv6):
    try:
        test_name = get_perf_test_name(request, is_ipv6)
        time_now = datetime.now().strftime(MongoDbConsts.TIME_REGEX_FORMAT)
        add_test_mongo_metadata(test_name, {MongoDbConsts.TEST_NAME: test_name,
                                            MongoDbConsts.TIME_STAMP: time_now})
        yield
    except Exception as e:
        raise e
    finally:
        if re.search('optimize', test_name, re.IGNORECASE):
            return
        else:
            create_test_validation_entry_to_db(players, test_name)


def get_all_players_ports(players, right_split_num=1, left_split_num=1):
    """
    Retrieves port configurations for all players in the performance test setup.

    This function collects port information from both the Device Under Test (DUT)
    and Traffic Generators (TG), applying the specified split configurations.

    Args:
        players (dict): Dictionary containing all players' information and their CLI interfaces
        right_split_num (int, optional): Number of splits for right-side ports. Defaults to 1
        left_split_num (int, optional): Number of splits for left-side ports. Defaults to 1

    Returns:
        dict: Dictionary with player names as keys and their port configurations as values.
              Format: {
                  'player_name': {
                      'left_ports': [...],
                      'right_ports': [...]
                  }
              }
    """
    all_ports_after_split = {}
    for player in PerfConsts.PERF_SETUP_PLAYERS_ALIASES:
        if player == PerfConsts.DUT_ALIAS:
            all_ports_after_split[player] = players[player]['cli'].performance.get_split_ports(
                right_split_num,
                left_split_num
            )
        else:
            split_num = left_split_num if player == PerfConsts.LEFT_TG_ALIAS else right_split_num
            all_ports_after_split[player] = players[player]['cli'].performance.get_player_unconnected_connected_after_split(
                split_num
            )
    return all_ports_after_split


@pytest.fixture(scope='function', autouse=False)
def port_group_df(request, players, conf_args=None):
    """
    Pytest fixture that creates a port group configuration dataframe.

    This fixture generates a list of dictionaries containing port configurations
    for the Device Under Test (DUT), organizing ports into relevant port groups.
    It can handle both standard DUT port groups and custom port group configurations.

    Args:
        request: Pytest request object
        players (dict): Dictionary containing all players' information
        conf_args (dict, optional): Configuration arguments containing custom port groups

    Returns:
        list: List of dictionaries with port configurations.
              Format: [
                  {
                      "port": <sdk_port>,
                      "port_group_name": "left_ports|right_ports|port_group_name"
                  },
                  ...
              ]
    """
    request.getfixturevalue('basic_setup_configuration')
    port_group_df = []

    port_groups = players[PerfConsts.DUT_ALIAS]['cli'].performance.port_groups

    for port_group_name, port_list in port_groups.items():
        sdk_port_list = players['dut']['cli'].performance.get_sdk_ports(port_list)
        for port in sdk_port_list:
            port_group_df.append({
                ValidationConsts.PORT: port,
                MongoDbConsts.PORT_GROUP_NAME: port_group_name
            })

    return port_group_df
