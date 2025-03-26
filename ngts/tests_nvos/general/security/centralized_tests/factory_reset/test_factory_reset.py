import logging
from typing import Dict, Generator

from ngts.tests_nvos.general.security.gnmi_server.mtls.spiffe_id.test_gnmi_server_spiffe_id import gnmi_spiffe_factory_reset_no_params_check, gnmi_spiffe_factory_reset_keep_all_config_check, gnmi_spiffe_factory_reset_keep_basic_check, gnmi_spiffe_upgrade_check

import pytest

from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.test_api_mtls_spiffe_id import \
    api_spiffe_factory_reset_no_params_check, api_spiffe_factory_reset_keep_basic_check, \
    api_spiffe_factory_reset_keep_all_config_check
from ngts.tests_nvos.general.security.centralized_tests.factory_reset.constants import FactoryResetType, \
    FACTORY_RESET_TYPE_TO_ACTION_PARAM
from ngts.tests_nvos.general.security.centralized_tests.helpers.checker_skip_rules import SkipCheckerBySetup, \
    CheckerSkipRule, should_skip_checker
from ngts.tests_nvos.general.security.certificate.helpers import delete_certificates
from ngts.tests_nvos.general.security.certificate.test_cert_cacert_mgmt import certs_mgmt_factory_reset_no_params_check, \
    certs_mgmt_factory_reset_keep_only_files_check
from ngts.tests_nvos.general.security.nmx_cert.test_cluster_app_mngr_security import \
    cluster_app_mngr_security_factory_reset_no_params_check, \
    cluster_app_mngr_security_factory_reset_keep_all_config_check
from ngts.tests_nvos.general.security.rbac.rbac_factory_reset import rbac_factory_reset_keep_roles, \
    rbac_factory_reset_no_params_check
from ngts.tests_nvos.general.security.sed.helpers import sed_password_factory_reset_check
from ngts.tests_nvos.general.security.test_api_server_security.test_api_mtls import \
    api_mtls_factory_reset_no_params_check, api_mtls_factory_reset_keep_all_config_check
from ngts.tests_nvos.general.security.test_ssh_pka.test_ssh_pka_pka_only import ssh_pka_factory_reset_no_params_check, \
    ssh_pka_factory_reset_keep_basic_check
from ngts.tests_nvos.general.security.tpm_attestation.helpers import tpm_attestation_factory_reset_no_params_check
from ngts.tests_nvos.system.factory_reset.helpers import update_timezone
from ngts.tests_nvos.system.gnmi.test_gnmi_mtls import gnmi_mtls_factory_reset_no_params_check, \
    gnmi_mtls_factory_reset_keep_all_config_check
from ngts.tools.test_utils import allure_utils as allure

# generators to feature checkers

TPM_ATTESTATION = 'TPM attestation'
GNMI_CERT = 'GNMI cert + mTLS'
NMX_CERT = 'NMX cert'
API_MTLS = 'API mTLS'
CERTS_MGMT = 'Certificates management'
SED_PASSWORD = 'SED password'
SSH_PKA = 'SSH PKA'
RBAC = 'RBAC'
API_SPIFFE_ID = 'API SPIFFE ID'
GNMI_SPIFFE_ID = 'GNMI SPIFFE ID'

CHECKERS_SKIP_RULES: Dict[str, CheckerSkipRule] = {
    NMX_CERT: SkipCheckerBySetup(['juliet'], False),
    SED_PASSWORD: SkipCheckerBySetup(['gorilla']),
    TPM_ATTESTATION: SkipCheckerBySetup(['gorilla']),
}

NO_PARAMS_CHECKERS: Dict[str, Generator[None, None, None]] = {
    TPM_ATTESTATION: tpm_attestation_factory_reset_no_params_check(),
    GNMI_CERT: gnmi_mtls_factory_reset_no_params_check(),
    NMX_CERT: cluster_app_mngr_security_factory_reset_no_params_check(),
    API_MTLS: api_mtls_factory_reset_no_params_check(),
    CERTS_MGMT: certs_mgmt_factory_reset_no_params_check(),
    SSH_PKA: ssh_pka_factory_reset_no_params_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
    RBAC: rbac_factory_reset_no_params_check(),
    API_SPIFFE_ID: api_spiffe_factory_reset_no_params_check(),
    GNMI_SPIFFE_ID: gnmi_spiffe_factory_reset_no_params_check(),
}

KEEP_BASIC_CHECKERS: Dict[str, Generator[None, None, None]] = {
    GNMI_CERT: gnmi_mtls_factory_reset_no_params_check(),
    NMX_CERT: cluster_app_mngr_security_factory_reset_no_params_check(),
    API_MTLS: api_mtls_factory_reset_no_params_check(),
    CERTS_MGMT: certs_mgmt_factory_reset_no_params_check(),
    SSH_PKA: ssh_pka_factory_reset_keep_basic_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
    RBAC: rbac_factory_reset_keep_roles(),
    API_SPIFFE_ID: api_spiffe_factory_reset_keep_basic_check(),
    GNMI_SPIFFE_ID: gnmi_spiffe_factory_reset_keep_basic_check(),
}

KEEP_ONLY_FILES_CHECKERS: Dict[str, Generator[None, None, None]] = {
    GNMI_CERT: gnmi_mtls_factory_reset_no_params_check(),
    NMX_CERT: cluster_app_mngr_security_factory_reset_no_params_check(),
    API_MTLS: api_mtls_factory_reset_no_params_check(),
    CERTS_MGMT: certs_mgmt_factory_reset_keep_only_files_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
    RBAC: rbac_factory_reset_no_params_check(),
    API_SPIFFE_ID: api_spiffe_factory_reset_no_params_check(),
    GNMI_SPIFFE_ID: gnmi_spiffe_factory_reset_no_params_check(),
}

KEEP_ALL_CONFIG_CHECKERS: Dict[str, Generator[None, None, None]] = {
    GNMI_CERT: gnmi_mtls_factory_reset_keep_all_config_check(),
    NMX_CERT: cluster_app_mngr_security_factory_reset_keep_all_config_check(),
    API_MTLS: api_mtls_factory_reset_keep_all_config_check(),
    CERTS_MGMT: certs_mgmt_factory_reset_keep_only_files_check(),
    SED_PASSWORD: sed_password_factory_reset_check(),
    RBAC: rbac_factory_reset_keep_roles(),
    API_SPIFFE_ID: api_spiffe_factory_reset_keep_all_config_check(),
    GNMI_SPIFFE_ID: gnmi_spiffe_factory_reset_keep_all_config_check(),
}

FACTORY_RESET_TYPE_TO_CHECKER_FUNCTIONS: Dict[str, Dict[str, Generator[None, None, None]]] = {
    FactoryResetType.NO_PARAMS: NO_PARAMS_CHECKERS,
    FactoryResetType.KEEP_BASIC: KEEP_BASIC_CHECKERS,
    FactoryResetType.KEEP_ONLY_FILES: KEEP_ONLY_FILES_CHECKERS,
    FactoryResetType.KEEP_ALL_CONFIG: KEEP_ALL_CONFIG_CHECKERS,
}


@pytest.mark.timeout(30 * MINUTE, func_only=True)
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
    checkers = {name: checker for name, checker in checkers.items() if
                not should_skip_checker(CHECKERS_SKIP_RULES, name, setup_name)}
    if not checkers:
        pytest.skip('test skipped: no checkers registered for this test')

    action_flag = FACTORY_RESET_TYPE_TO_ACTION_PARAM[factory_reset_type]
    logging.info(f'checkers names for factory reset {factory_reset_type}: {list(checkers.keys())}')
    logging.info(f'action flag for factory reset {factory_reset_type}: "{action_flag}"')

    should_do_factory_reset = False

    try:
        with allure.step('setup'):
            pass

        with allure.step(f'test: factory reset {factory_reset_type}'):
            with allure.independent_step('pre factory reset steps'):
                for name, checker in checkers.items():
                    if not should_skip_checker(CHECKERS_SKIP_RULES, name, setup_name):
                        with allure.independent_step(name):
                            next(checker)
                            should_do_factory_reset = True  # do factory reset only if any checker succeeded

            if should_do_factory_reset:
                with allure.step(f"Run reset factory - {factory_reset_type}"):
                    do_factory_reset(devices, action_flag, topology_obj)

                with allure.step('post factory reset steps'):
                    for name, checker in checkers.items():
                        if not should_skip_checker(CHECKERS_SKIP_RULES, name, setup_name):
                            with allure.independent_step(name):
                                next(checker)

    finally:
        with allure.step('cleanup'):
            with allure.independent_step('delete ca/certs'):
                delete_certificates()
                delete_certificates(True)


def do_factory_reset(devices, flag, topology_obj):
    system = System()
    with allure.step('do factory reset'):
        system.factory_default.action_reset(operation=devices.dut.reset_factory, param=flag, topology_obj=topology_obj,
                                            system_is_ready_timeout=devices.dut.timeout_system_is_ready,
                                            verify_duration=False).verify_result()
    with allure.step('update timezone'):
        update_timezone(system)
