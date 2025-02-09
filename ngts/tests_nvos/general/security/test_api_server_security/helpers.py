from typing import List

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import TestFlowType
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.conftest import get_dut_hostname
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs, import_certificates
from ngts.tests_nvos.general.security.helpers import cleanup_certs_for_tests, setup_certs_for_tests
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.general.security.test_api_server_security.constants import API_INSTALLED, INSTALLED, TEST_CERTS, \
    ApiConsts, CA_CERTIFICATE, CERTIFICATE
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure


def verify_installed_cacert(all_ca_names, expect_installed_ca):
    system = System()
    if expect_installed_ca is None:
        cacerts_conf = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.ca_certificate.show()).get_returned_value()
        assert all(API_INSTALLED not in cacerts_conf[ca][INSTALLED] for ca in
                   all_ca_names), f'some ca is unexpectedly installed for api\ncas info:\n{cacerts_conf}'
    else:
        cacert_conf = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.ca_certificate.cert_id[expect_installed_ca].show()).get_returned_value()
        assert API_INSTALLED in cacert_conf[
            INSTALLED], f'ca "{expect_installed_ca}" is not installed for api as expected\nca info:\n{cacert_conf}'


def verify_mtls_config(expected_cacert, expected_fields=None):
    mtls_conf = OutputParsingTool.parse_json_str_to_dictionary(System().api.mtls.show()).get_returned_value()
    if not expected_cacert:
        assert mtls_conf == {}, f'mtls config not as expected.\nexpected nothing\nactual: {mtls_conf}'
    else:
        if expected_fields:
            assert all(field in mtls_conf for field in
                       ApiConsts.Mtls.fields), f'some of expected fields are missing from show mtls output\nexpected: {ApiConsts.Mtls.fields}\nout keys: {mtls_conf.keys()}'
        assert mtls_conf[
            CA_CERTIFICATE] == expected_cacert, f'value of "{CA_CERTIFICATE}" in mtls show not as expected\nexpected: {expected_cacert}\nactual: {mtls_conf[CA_CERTIFICATE]}'


def verify_api_ca_configuration(expected_ca, verify_mtls_fields=False):
    with allure.step(
            f'verify in show that {f"ca `{expected_ca}`" if expected_ca else "no ca"} configured for api mtls'):
        with allure.independent_step(f'check in mtls show'):
            verify_mtls_config(expected_ca if expected_ca else '',
                               verify_mtls_fields)  # with allure.independent_step('check in ca-certs show'):   # TODO: there's a bug 4063802  #     verify_installed_cacert(TEST_CACERT_NAMES, expected_ca if expected_ca else None)


def verify_api_connection(test_flow, dut: LinuxSshEngine, user: UserInfo, expect_mtls: bool, server_cert: CertInfo,
                          server_ca: CertInfo, dut_ipv6_addr=None):
    curl = CurlTool(dut_ipv6_addr or dut.ip, user.username, user.password)

    def _run_curl_and_verify(expect_success: bool, run_insecure: bool, client_cacert: CertInfo = None,
                             client_cert: CertInfo = None):
        req_type = 'GET'
        req_path = '/nvue_v1/system/version'
        cacert = client_cacert.cacert if client_cacert else ''
        resolve_dn = client_cacert.dn if client_cacert else ''

        exc = ''
        curl_success = True
        output = ''
        try:
            out, err = curl.request(request_type=req_type, path=req_path, skip_cert_verify=run_insecure, cacert=cacert,
                                    client_cert=client_cert, resolve_dn=resolve_dn)
            output = f'{out}\n{err}'
            assert all(err not in output for err in
                       ApiConsts.Mtls.Errors.MTLS_ERRORS), f'curl got error "{ApiConsts.Mtls.Errors.FAILED_TO_VERIFY_SERVER_ERR}"\n'
        except AssertionError as e:
            curl_success = False
            exc = e
        assert curl_success == expect_success, (
            f'curl {"fail but expected success" if expect_success else "success but expected fail"}\n'
            f'client cert: {client_cert.name if client_cert else ""}\n'
            f'client ca: {client_cacert.cacert_name if client_cacert else ""}\n'
            f'out: {output}\n'
            f'exception: {exc}')

    matching_cert: CertInfo = server_ca
    matching_ca: CertInfo = server_cert
    non_matching_cert: CertInfo = RandomizationTool.select_random_value(TEST_CERTS,
                                                                        [matching_cert]).get_returned_value()
    non_matching_ca: CertInfo = RandomizationTool.select_random_value(TEST_CERTS, [matching_ca]).get_returned_value()

    if expect_mtls:
        with allure.step('verify mtls only'):
            if test_flow == TestFlowType.ALL_TYPES or test_flow == TestFlowType.GOOD_FLOW:
                with allure.independent_step('goodflow - use suitable cert & cacert on client side'):
                    _run_curl_and_verify(True, False, matching_ca, matching_cert)
            if test_flow == TestFlowType.ALL_TYPES or test_flow == TestFlowType.BAD_FLOW:
                # bug #4064106 still active - [Functional] [mTLS] api mtls is working with an imported ca-cert but not set to api mtls
                # bug rejected because even if a CA is imported in the switch it's used in mtls
                # with allure.independent_step('badflow - bad cert & good cacert on client side'):
                #     _run_curl_and_verify(False, False, matching_ca, non_matching_cert)
                with allure.independent_step('badflow - good cert & bad cacert on client side'):
                    _run_curl_and_verify(False, False, non_matching_ca, matching_cert)
                with allure.independent_step('badflow - bad cert & bad cacert on client side'):
                    _run_curl_and_verify(False, False, non_matching_ca, non_matching_cert)
                with allure.independent_step('badflow - run insecure'):
                    _run_curl_and_verify(False, True)
    else:
        with allure.step('verify no mtls - insecure works'):
            if test_flow == TestFlowType.ALL_TYPES or test_flow == TestFlowType.GOOD_FLOW:
                with allure.independent_step('goodflow - run insecure'):
                    _run_curl_and_verify(True, True)


def setup_mtls_test():
    CurlTool('', '', '', verify_tools_installed=True)
    scp_player = get_scp_player(TestToolkit.engines)
    import_test_certs(scp_player, TestToolkit.engines.dut, TEST_CERTS)


def cleanup_mtls_test(tmp_certs_dir=None, certs: List[CertInfo] = None, cas: List[CertInfo] = None):
    with allure.step('cleanup'):
        System().api.unset(apply=True).verify_result()
    if tmp_certs_dir and certs:
        with allure.step('remove certs from dut and local'):
            cleanup_certs_for_tests(tmp_certs_dir, certs, cas)


def setup_mtls_checker(engines):
    scp_player = get_scp_player(engines)
    dut_hostname = get_dut_hostname(engines)
    system = System()

    with allure.step('verify player has curl'):
        CurlTool('', '', '', verify_tools_installed=True)
    with allure.step('prepare certs'):
        tmp_certs_dir, certs = setup_certs_for_tests('mtls', ['mtls-cert1', 'mtls-cert2'],
                                                     engines, dut_hostname, False, scp_player)
        server_cert: CertInfo = certs[0]
        server_ca: CertInfo = certs[1]
    with allure.step('import server ca/certs'):
        import_certificates(scp_player, engines.dut, [server_cert])
        import_certificates(scp_player, engines.dut, [server_ca], True)
    with allure.step(f'set cert: {server_cert.name}'):
        system.api.set(CERTIFICATE, server_cert.name).verify_result()
    with allure.step(f'set ca: {server_ca.cacert_name}'):
        system.api.mtls.set(CA_CERTIFICATE, server_ca.cacert_name, apply=True).verify_result()
    with allure.step('save config'):
        NvueGeneralCli.save_config(engines.dut)

    return tmp_certs_dir, server_cert, server_ca
