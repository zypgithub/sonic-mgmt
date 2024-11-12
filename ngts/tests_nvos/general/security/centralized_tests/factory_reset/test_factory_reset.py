import logging
from typing import Dict, Generator

import pytest

from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.security.centralized_tests.factory_reset.constants import FactoryResetType, \
    FACTORY_RESET_TYPE_TO_ACTION_PARAM
from ngts.tests_nvos.general.security.centralized_tests.helpers.checker_skip_rules import SkipCheckerBySetup, \
    CheckerSkipRule, should_skip_checker, SkipCheckerByCond
from ngts.tests_nvos.general.security.nmx_cert.test_nmx_cert import nmx_cert_factory_reset_no_params_check
from ngts.tests_nvos.general.security.sed.helpers import sed_password_factory_reset_check
from ngts.tests_nvos.general.security.test_api_server_security.test_api_mtls import \
    api_mtls_factory_reset_no_params_check, api_mtls_factory_reset_keep_all_config_check, \
    api_mtls_factory_reset_keep_only_files_check
from ngts.tests_nvos.general.security.tpm_attestation.helpers import tpm_attestation_factory_reset_no_params_check
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tests_nvos.system.factory_reset.helpers import update_timezone
from ngts.tests_nvos.system.gnmi.helpers import gnmi_cert_factory_reset_no_params_check
from ngts.tools.test_utils import allure_utils as allure

# generators to feature checkers

TPM_ATTESTATION = 'TPM attestation'
GNMI_CERT = 'GNMI cert'
NMX_CERT = 'NMX cert'
API_MTLS = 'API mTLS'
SED_PASSWORD = 'SED password'

CHECKERS_SKIP_RULES: Dict[str, CheckerSkipRule] = {
    API_MTLS: SkipCheckerByCond(is_bug_active(4103432)),    # TODO: remove once bug #4103432 closed
    NMX_CERT: SkipCheckerBySetup(['juliet'], False),
    SED_PASSWORD: SkipCheckerBySetup(['gorilla'])
}

NO_PARAMS_CHECKERS: Dict[str, Generator[None, None, None]] = {
    TPM_ATTESTATION: tpm_attestation_factory_reset_no_params_check(),
    GNMI_CERT: gnmi_cert_factory_reset_no_params_check(),
    NMX_CERT: nmx_cert_factory_reset_no_params_check(),
    API_MTLS: api_mtls_factory_reset_no_params_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
}

KEEP_BASIC_CHECKERS: Dict[str, Generator[None, None, None]] = {
    API_MTLS: api_mtls_factory_reset_no_params_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
}

KEEP_ALL_CONFIG_CHECKERS: Dict[str, Generator[None, None, None]] = {
    API_MTLS: api_mtls_factory_reset_keep_all_config_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
}

KEEP_ONLY_FILES_CHECKERS: Dict[str, Generator[None, None, None]] = {
    API_MTLS: api_mtls_factory_reset_keep_only_files_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
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
def test_reset_factory(factory_reset_type, engines, devices, topology_obj, platform_params, setup_name):
    """
    Validate reset factory flavors
    """
    checkers = FACTORY_RESET_TYPE_TO_CHECKER_FUNCTIONS[factory_reset_type]
    if not checkers:
        pytest.skip('test skipped: no checkers registered for this test')

    system = System()

    action_flag = FACTORY_RESET_TYPE_TO_ACTION_PARAM[factory_reset_type]
    logging.info(f'checkers names for factory reset {factory_reset_type}: {list(checkers.keys())}')
    logging.info(f'action flag for factory reset {factory_reset_type}: "{action_flag}"')

    try:
        with allure.step(f'factory reset test: {factory_reset_type}'):
            with allure.independent_step('pre factory reset steps'):
                for name, checker in checkers.items():
                    if not should_skip_checker(CHECKERS_SKIP_RULES, name, setup_name):
                        with allure.independent_step(name):
                            next(checker)

            with allure.step(f"Run reset factory - {factory_reset_type}"):
                do_factory_reset(devices, engines, system, action_flag, topology_obj)

            with allure.step('post factory reset steps'):
                for name, checker in checkers.items():
                    if not should_skip_checker(CHECKERS_SKIP_RULES, name, setup_name):
                        with allure.independent_step(name):
                            next(checker)

    finally:
        pass


def do_factory_reset(devices, engines, system, flag, topology_obj):
    with allure.step('do factory reset'):
        system_is_ready_tout = devices.dut.system_is_ready_wait_timeout + 2 * MINUTE
        system.factory_default.action_reset(operation=devices.dut.reset_factory, param=flag, topology_obj=topology_obj,
                                            system_is_ready_timeout=system_is_ready_tout, verify_duration=False).verify_result()
    with allure.step('update timezone'):
        update_timezone(system)
