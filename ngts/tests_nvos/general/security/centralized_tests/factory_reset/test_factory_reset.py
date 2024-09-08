from typing import Dict, Generator

import pytest

from ngts.tests_nvos.general.security.centralized_tests.factory_reset.constants import FactoryResetType, \
    FACTORY_RESET_TYPE_TO_ACTION_PARAM
from ngts.tests_nvos.general.security.test_api_server_security.test_api_mtls import \
    api_mtls_factory_reset_no_params_check, \
    api_mtls_factory_reset_keep_all_config_check, api_mtls_factory_reset_keep_only_files_check
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tests_nvos.system.factory_reset.helpers import get_current_time
from ngts.tests_nvos.system.test_system_factory_reset import execute_reset_factory
from ngts.tools.test_utils import allure_utils as allure

# generators to feature checkers

NO_PARAMS_CHECKERS: Dict[str, Generator[None, None, None]] = {
    'api mTLS': api_mtls_factory_reset_no_params_check(),
}

KEEP_BASIC_CHECKERS: Dict[str, Generator[None, None, None]] = {
    'api mTLS': api_mtls_factory_reset_no_params_check(),
}

KEEP_ALL_CONFIG_CHECKERS: Dict[str, Generator[None, None, None]] = {
    'api mTLS': api_mtls_factory_reset_keep_all_config_check(),
}

KEEP_ONLY_FILES_CHECKERS: Dict[str, Generator[None, None, None]] = {
    'api mTLS': api_mtls_factory_reset_keep_only_files_check(),
}

FACTORY_RESET_TYPE_TO_CHECKER_FUNCTIONS: Dict[str, Dict[str, Generator[None, None, None]]] = {
    FactoryResetType.NO_PARAMS: NO_PARAMS_CHECKERS,
    FactoryResetType.KEEP_BASIC: KEEP_BASIC_CHECKERS,
    FactoryResetType.KEEP_ALL_CONFIG: KEEP_ALL_CONFIG_CHECKERS,
    FactoryResetType.KEEP_ONLY_FILES: KEEP_ONLY_FILES_CHECKERS,
}


@pytest.mark.security
@pytest.mark.reset_factory
@pytest.mark.parametrize('factory_reset_type', FactoryResetType.ALL_TYPES)
def test_reset_factory(factory_reset_type, engines, devices, topology_obj, platform_params):
    """
    Validate reset factory flavors
    """
    system = System()

    checkers = FACTORY_RESET_TYPE_TO_CHECKER_FUNCTIONS[factory_reset_type]
    action_flag = FACTORY_RESET_TYPE_TO_ACTION_PARAM[factory_reset_type]
    logging.info(f'checkers names for factory reset {factory_reset_type}: {list(checkers.keys())}')
    logging.info(f'action flag for factory reset {factory_reset_type}: "{action_flag}"')

    try:
        with allure.step(f'factory reset test: {factory_reset_type}'):
            with allure.independent_step('pre factory reset steps'):
                for name, checker in checkers.items():
                    with allure.independent_step(name):
                        next(checker)

            with allure.step(f"Run reset factory - {factory_reset_type}"):
                do_factory_reset(devices, engines, system, action_flag)

            with allure.step('post factory reset steps'):
                for name, checker in checkers.items():
                    with allure.independent_step(name):
                        next(checker)

    finally:
        pass


def do_factory_reset(devices, engines, system, flag):
    with allure.step('get current time'):
        current_time = get_current_time(engines)
    with allure.step('do factory reset'):
        execute_reset_factory(engines, system, devices.dut.reset_factory, flag, current_time)
    with allure.step('update timezone'):
        update_timezone(system)
