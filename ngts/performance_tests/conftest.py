import json
import pytest
import allure
import os
from datetime import datetime
from ngts.helpers.performance.performance_setup_helpers import configure_mloops, stop_traffic
from ngts.helpers.performance.Performance_log_print import print_players_logs, remove_players_logs
from ngts.constants.constants import PytestConst
from ngts.constants.performance_constants import MongoDbConsts, PowerConsts
from ngts.helpers.performance.performance_db_helpers import (create_performance_db_template,
                                                             create_test_validation_entry_to_db,
                                                             add_test_mongo_metadata, get_perf_test_name)
from infra.tools.exceptions.test_issue import TestIssue


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
            return params_json
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
def basic_test_configuration(request, players):
    request.getfixturevalue('basic_setup_configuration')
    try:
        with allure.step('Disable default sysdump generation'):
            os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "False"
        with allure.step('Configure Mloops on Traffic Generators'):
            configure_mloops(players)
        yield
        with allure.step('Stop Traffic on Traffic Generators'):
            stop_traffic(players)
    except Exception as e:
        raise e
    finally:
        with allure.step(f"Attaching Players Logs to Allure"):
            print_players_logs(print_to_stdout=True, players_info=players)
            remove_players_logs()


@pytest.fixture(scope='session', autouse=True)
def create_mongo_db_template_file(players, session_id, setup_name):
    create_performance_db_template(players, session_id, setup_name)


@pytest.fixture(scope='function', autouse=True)
def update_test_data_in_mongo_db(request, players, is_ipv6):
    try:
        test_name = get_perf_test_name(request.node.name, is_ipv6)
        time_now = datetime.now().strftime(MongoDbConsts.TIME_REGEX_FORMAT)
        add_test_mongo_metadata(test_name, {MongoDbConsts.TEST_NAME: test_name,
                                            MongoDbConsts.TIME_STAMP: time_now})
        yield
    except Exception as e:
        raise e
    finally:
        create_test_validation_entry_to_db(players, test_name)
