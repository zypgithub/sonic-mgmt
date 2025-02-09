import random
import string

import pytest

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, TestFlowType, RebootTestFlowType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.general.security.test_api_server_security.constants import ApiConsts, TEST_CERTS, CERTIFICATE
from ngts.tests_nvos.general.security.test_api_server_security.constants import CA_CERTIFICATE
from ngts.tests_nvos.general.security.test_api_server_security.helpers import verify_api_connection, verify_mtls_config, \
    verify_api_ca_configuration, cleanup_mtls_test, setup_mtls_test, setup_mtls_checker


@pytest.mark.mtls
@pytest.mark.security
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_api_mtls_cli(test_api):
    """
    Verify that all CLI work and check values change properly in show

    1. Run show commands
    2. Verify outputs contain the required fields
    3. Set ca-certificate
    4. Verify in show commands
    5. Unset
    6. Verify in show commands
    """
    TestToolkit.tested_api = test_api
    system = System()
    imported_cas = [cert.cacert_name for cert in TEST_CERTS]
    ca = random.choice(imported_cas)

    with allure.step('run show commands and verify required fields'):
        with allure.independent_step('api show'):
            api_conf = OutputParsingTool.parse_json_str_to_dictionary(system.api.show()).get_returned_value()
            assert all(field in api_conf for field in
                       ApiConsts.fields), f'some of expected fields are missing from show api output\nexpected: {ApiConsts.fields}\nout keys: {api_conf.keys()}'
        verify_api_ca_configuration(None, True)

    with allure.step(f'Set ca-certificate to {ca}'):
        system.api.mtls.set(CA_CERTIFICATE, ca, apply=True).verify_result()
    with allure.step('Verify in show commands'):
        verify_api_ca_configuration(ca)

    with allure.step('check unset commands clear mtls config'):
        with allure.independent_step('check unset api'):
            with allure.step('run unset api'):
                system.api.unset(apply=True).verify_result()
            verify_api_ca_configuration(None)
        with allure.independent_step('check unset mtls'):
            with allure.step(f'Set ca-certificate to {ca}'):
                system.api.mtls.set(CA_CERTIFICATE, ca, apply=True).verify_result()
            with allure.step('run unset mtls'):
                system.api.mtls.unset(apply=True).verify_result()
            verify_api_ca_configuration(None)
        with allure.independent_step('check unset cacert field'):
            with allure.step(f'Set ca-certificate to {ca}'):
                system.api.mtls.set(CA_CERTIFICATE, ca, apply=True).verify_result()
            with allure.step('run unset mtls cacert'):
                system.api.mtls.unset(CA_CERTIFICATE, apply=True).verify_result()
            verify_api_ca_configuration(None)


@pytest.mark.mtls
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_api_mtls_set_bad_param(test_api):
    """
    Verify that set with bad param rejected

    1. Set api ca-certificate with bad param (CERT-ID or non existing/imported id)
    2. Verify command rejected
    3. Verify in show – expect no ca-cert installed to api
    """
    TestToolkit.tested_api = test_api

    system = System()
    rand_imported_cert: CertInfo = random.choice(TEST_CERTS)
    rand_str = ''.join(random.sample(string.ascii_lowercase, 6))
    bad_cas = [rand_str, rand_imported_cert.name]

    with allure.step('verify set with bad params rejected'):
        for bad_ca in bad_cas:
            with allure.independent_step(f'check bad param: {bad_ca}'):
                with allure.independent_step('check command is rejected'):
                    res = system.api.mtls.set(CA_CERTIFICATE, bad_ca, apply=True)
                    res.verify_result(False)
                    expected_err = ApiConsts.Mtls.Errors.CERT_DONT_EXIST.format(bad_ca)
                    assert expected_err in res.info, f'error message not as expected\nexpected: "{expected_err}"\nactual: {res.info}'
                with allure.independent_step('check no change in show mtls'):
                    verify_mtls_config('')


@pytest.mark.mtls
@pytest.mark.security
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_api_mtls_set_ca_without_cert_not_rejected(test_api):
    """
    Verify that set api CA not rejected when no cert was previously set

    1. Set CA
    2. Verify command success
    3. Verify in show – expect ca to be installed to api
    """
    TestToolkit.tested_api = test_api

    system = System()
    imported_cas = [cert.cacert_name for cert in TEST_CERTS]
    ca = random.choice(imported_cas)

    with allure.step(f'set CA: {ca} without setting cert explicitly, expect success'):
        system.api.mtls.set(CA_CERTIFICATE, ca, apply=True).verify_result()
    with allure.step('verify in show'):
        verify_api_ca_configuration(ca)


@pytest.mark.mtls
@pytest.mark.security
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
@pytest.mark.parametrize('addressing_type', [AddressingType.IPV4, AddressingType.IPV6])
def test_api_mtls_core_functionality(test_flow, addressing_type, engines, local_adminuser, dut_ipv6_addr):
    """
    Verify the core functionality:

    after setting ca-certificate, client can request only using suitable cert & ca (mtls)

    1. Bind cert & ca-cert to api
    2. Send client request using proper cert & cacert – expect success
    3. Send client request using non-proper cert/cacert – expect failure
    4. Unset ca-cert
    5. Send client request using any/no cert – expect success (server mtls off)
    """
    system = System()
    server_cert: CertInfo = random.choice(TEST_CERTS)
    server_ca: CertInfo = RandomizationTool.select_random_value(TEST_CERTS, [server_cert]).get_returned_value()
    ipv6_addr = dut_ipv6_addr if addressing_type == AddressingType.IPV6 else None

    with allure.step(f'set some cert: {server_cert.name}'):
        system.api.set(CERTIFICATE, server_cert.name).verify_result()
    with allure.step(f'set ca: {server_ca.cacert_name}'):
        system.api.mtls.set(CA_CERTIFICATE, server_ca.cacert_name, apply=True).verify_result()
    with allure.step('verify api server is mtls only'):
        verify_api_connection(test_flow, engines.dut, local_adminuser, True, server_cert, server_ca, ipv6_addr)
    with allure.step('unset ca'):
        system.api.mtls.unset(CA_CERTIFICATE, apply=True).verify_result()
    with allure.step('verify api server is not mtls only'):
        verify_api_connection(test_flow, engines.dut, local_adminuser, False, server_cert, server_ca, ipv6_addr)


@pytest.mark.mtls
@pytest.mark.security
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_api_mtls_delete_installed_ca(test_flow, engines, local_adminuser, import_missing_cas_after_test):
    """
    Verify that delete of ca-cert that is installed to api rejected

    1. Set api ca-certificate
    2. Try to delete that ca-certificate
    3. Verify reject
    4. Verify in show – expect ca-cert still installed
    5. Verify client cant request without suitable cert – expect fail
    """
    system = System()
    server_cert: CertInfo = random.choice(TEST_CERTS)
    server_ca: CertInfo = RandomizationTool.select_random_value(TEST_CERTS, [server_cert]).get_returned_value()

    with allure.step(f'set some cert: {server_cert.name}'):
        system.api.set(CERTIFICATE, server_cert.name).verify_result()
    with allure.step(f'set ca: {server_ca.cacert_name}'):
        system.api.mtls.set(CA_CERTIFICATE, server_ca.cacert_name, apply=True).verify_result()
    with allure.step(f'try delete ca "{server_ca.cacert_name}". expect fail'):
        res = system.security.ca_certificate.cert_id[server_ca.cacert_name].action_delete()
        res.verify_result(False)
        expected_err = ApiConsts.Mtls.Errors.INSTALLED_CA_DELETE_ERR.format(server_ca.cacert_name)
        assert expected_err in res.info, f'error message not as expected\nexpected: "{expected_err}"\nactual: {res.info}'
    with allure.step('verify no change show'):
        verify_api_ca_configuration(server_ca.cacert_name)
    with allure.step('verify api server is still mtls only'):
        verify_api_connection(test_flow, engines.dut, local_adminuser, True, server_cert, server_ca)


@pytest.mark.reboot
@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.mtls
@pytest.mark.security
@pytest.mark.parametrize('reboot_flow', RebootTestFlowType.ALL_TYPES)
def test_api_mtls_reboot(reboot_flow, engines, local_adminuser):
    """
    Verify mtls config and functionality after reboot

    1. Set api certificate & ca-certificate
    2. Save / no save
    3. Reboot
    4. Verify config in show
    5. Verify REST connection
    """
    with_save = reboot_flow == RebootTestFlowType.WITH_SAVE
    system = System()
    server_cert: CertInfo = random.choice(TEST_CERTS)
    server_ca: CertInfo = RandomizationTool.select_random_value(TEST_CERTS, [server_cert]).get_returned_value()

    with allure.step(f'set some cert: {server_cert.name}'):
        system.api.set(CERTIFICATE, server_cert.name).verify_result()
    with allure.step(f'set ca: {server_ca.cacert_name}'):
        system.api.mtls.set(CA_CERTIFICATE, server_ca.cacert_name, apply=True).verify_result()

    if with_save:
        with allure.step('save config'):
            NvueGeneralCli.save_config(engines.dut)

    with allure.step('reboot the system'):
        System().action_reboot('force').verify_result()

    with allure.step('verify show'):
        if with_save:
            verify_api_ca_configuration(server_ca.cacert_name)
        else:
            verify_api_ca_configuration(None)

    with allure.step(f'verify {"no " if not with_save else ""} mtls only connection'):
        if with_save:
            verify_api_connection(TestFlowType.ALL_TYPES, engines.dut, local_adminuser, True, server_cert, server_ca)
        else:
            verify_api_connection(TestFlowType.ALL_TYPES, engines.dut, local_adminuser, False, server_cert, server_ca)


# generator functions

def api_mtls_factory_reset_no_params_check():
    """
    Verify that mtls config is removed after these reset factory flavors

    The same for these flavors:
    - regular/no params (remove everything)
    - keep basic (remove everything except for some basic configuration)

    1. Set api mtls
    2. Save
    3. Do factory reset
    4. Verify no mtls configuration in show
    5. Verify no mtls connection
    """
    engines = TestToolkit.engines

    with allure.step('setup'):
        tmp_certs_dir, server_cert, server_ca = setup_mtls_checker(engines)

    yield  # factory reset

    try:
        with allure.step('verify after factory reset'):
            with allure.step('verify no mtls after this factory reset'):
                with allure.independent_step('verify mtls is not configured in show'):
                    verify_mtls_config('')
                with allure.independent_step('verify no mtls only connection'):
                    verify_api_connection(TestFlowType.ALL_TYPES, engines.dut,
                                          UserInfo(engines.dut.username, engines.dut.password, 'admin'),
                                          False, server_cert, server_ca)
    finally:
        cleanup_mtls_test(tmp_certs_dir, [server_cert], [server_ca])

    yield  # to prevent StopIteration on the 2nd next() call


def api_mtls_factory_reset_keep_only_files_check():
    """
    Verify that mtls config is removed after these reset factory flavors

    Keep only files - remove config but keep system files/logs
    * when a ca-cert was imported and bound to api, the cacert file should be kept and exist in the show ca-certificate, but it should not appear as installed

    1. Set api mtls
    2. Save
    3. Do factory reset
    4. Verify no mtls configuration in show
    5. Verify no mtls connection
    6. Verify in show ca-certificates – exist but not installed to api
    """
    setup_mtls_test()

    dut: LinuxSshEngine = TestToolkit.engines.dut
    system = System()
    server_cert: CertInfo = random.choice(TEST_CERTS)
    server_ca: CertInfo = RandomizationTool.select_random_value(TEST_CERTS, [server_cert]).get_returned_value()

    with allure.step(f'set some cert: {server_cert.name}'):
        system.api.set(CERTIFICATE, server_cert.name).verify_result()
    with allure.step(f'set ca: {server_ca.cacert_name}'):
        system.api.mtls.set(CA_CERTIFICATE, server_ca.cacert_name, apply=True).verify_result()
    with allure.step('save config'):
        NvueGeneralCli.save_config(dut)

    yield  # factory reset

    try:
        with allure.step('verify no mtls after this factory reset'):
            with allure.independent_step('verify mtls is not configured in show'):
                verify_api_ca_configuration(None)
            with allure.independent_step('verify no mtls only connection'):
                verify_api_connection(TestFlowType.ALL_TYPES, dut, UserInfo(dut.username, dut.password, 'admin'), False,
                                      server_cert, server_ca)
    finally:
        cleanup_mtls_test()

    yield  # to prevent StopIteration on the 2nd next() call


def api_mtls_factory_reset_keep_all_config_check():
    """
    Verify that mtls config is kept after this factory reset flavor

    Keep all config – removes everything except for saved configuration
    * when saved config includes ca/cert, the config should be kept and also the ca/cert files themselves.

    1. Set api mtls
    2. Save
    3. Do factory reset
    4. Verify mtls config in show
    5. Verify mtls connection only
    """
    engines = TestToolkit.engines

    with allure.step('setup'):
        tmp_certs_dir, server_cert, server_ca = setup_mtls_checker(engines)

    yield  # factory reset

    try:
        with allure.step('verify mtls after this factory reset'):
            with allure.independent_step('verify mtls is configured in show'):
                verify_api_ca_configuration(server_ca.cacert_name)
            with allure.independent_step('verify mtls only connection'):
                verify_api_connection(TestFlowType.ALL_TYPES, engines.dut,
                                      UserInfo(engines.dut.username, engines.dut.password, 'admin'),
                                      True, server_cert, server_ca)
    finally:
        cleanup_mtls_test(tmp_certs_dir, [server_cert], [server_ca])

    yield  # to prevent StopIteration on the 2nd next() call


def api_mtls_upgrade_check():
    """
    Verify that ca/certificates kept after upgrade

    1. bind cert & cacert
    2. save
    3. Upgrade
    4. Verify updated values in show kept
    5. Verify mtls connection
    """
    setup_mtls_test()

    dut: LinuxSshEngine = TestToolkit.engines.dut
    system = System()
    server_cert: CertInfo = random.choice(TEST_CERTS)
    server_ca: CertInfo = RandomizationTool.select_random_value(TEST_CERTS, [server_cert]).get_returned_value()

    with allure.step(f'set some cert: {server_cert.name}'):
        system.api.set(CERTIFICATE, server_cert.name).verify_result()
    with allure.step(f'set ca: {server_ca.cacert_name}'):
        system.api.mtls.set(CA_CERTIFICATE, server_ca.cacert_name, apply=True).verify_result()
    with allure.step('save config'):
        NvueGeneralCli.save_config(dut)

    yield  # upgrade

    try:
        with allure.step('verify mtls after this factory reset'):
            with allure.independent_step('verify mtls is configured in show'):
                verify_api_ca_configuration(server_ca.cacert_name)
            with allure.independent_step('verify mtls only connection'):
                verify_api_connection(TestFlowType.ALL_TYPES, dut, UserInfo(dut.username, dut.password, 'admin'), True,
                                      server_cert, server_ca)
    finally:
        cleanup_mtls_test()

    yield  # to prevent StopIteration on the 2nd next() call
