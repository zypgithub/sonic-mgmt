from typing import List, Optional, Callable

from typing_extensions import TypeAlias

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import TestFlowType
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.MTLSableServerResource import MTLSableServerResource
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs
from ngts.tests_nvos.general.security.mtls.generic_testing.constants import CA_CERTIFICATE
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.general.security.test_api_server_security.constants import INSTALLED, TEST_CERTS
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure


def verify_ca_configuration(resource: MTLSableServerResource, installed_app_name, expected_ca=None, verify_mtls_fields: List[str] = None):
    with allure.step(f'verify in show that {f"ca `{expected_ca}`" if expected_ca else "no ca"} configured for {resource.get_resource_basename()} mtls'):
        with allure.independent_step(f'check in mtls show'):
            verify_mtls_config(resource, expected_ca, verify_mtls_fields)
        with allure.independent_step('check in ca-certs show'):
            verify_installed_cacert(installed_app_name, expected_ca)  # TODO: there's a bug 4063802


def verify_mtls_config(resource: MTLSableServerResource, expected_ca=None, expected_fields=None):
    mtls_conf = OutputParsingTool.parse_json_str_to_dictionary(resource.mtls.show()).get_returned_value()
    if not expected_ca:
        assert mtls_conf == {}, f'mtls config not as expected.\nexpected nothing\nactual: {mtls_conf}'
    else:
        if expected_fields:
            assert all(field in mtls_conf for field in expected_fields), f'some of expected fields are missing from show mtls output\nexpected: {expected_fields}\nout keys: {mtls_conf.keys()}'
        assert CA_CERTIFICATE in mtls_conf, f'field "{CA_CERTIFICATE}" missing in mtls show output'
        assert mtls_conf[CA_CERTIFICATE] == expected_ca, f'value of "{CA_CERTIFICATE}" in mtls show not as expected\nexpected: {expected_ca}\nactual: {mtls_conf[CA_CERTIFICATE]}'


def verify_installed_cacert(installed_app_name, expect_installed_ca=None):
    cas_resource = System().security.ca_certificate
    with allure.step(f'find CAs that are installed on {installed_app_name}'):
        cas_show = OutputParsingTool.parse_json_str_to_dictionary(cas_resource.show()).get_returned_value()
        installed_cas = [ca for ca in cas_show if installed_app_name in cas_show[ca][INSTALLED]]
    if expect_installed_ca:
        with allure.step(f'verify only installed CA is: {expect_installed_ca}'):
            assert installed_cas == [expect_installed_ca], (f'unexpected CAs installed on {installed_app_name}.\n'
                                                            f'expected: {expect_installed_ca}\nactual: {installed_cas}')
    else:
        with allure.step(f"verify all imported cas are not installed for: {installed_app_name}"):
            assert not installed_cas, f'CAs unexpectedly installed on {installed_app_name}: {installed_cas}'


VerifyConnFunc: TypeAlias = Callable[[str, UserInfo, bool, bool, Optional[CertInfo], Optional[CertInfo], Optional[int]], None]
VerifyBuilderFunc: TypeAlias = Callable[[str, Optional[UserInfo], bool, Optional[CertInfo], bool, Optional[CertInfo], Optional[int]], None]


def verify_connection(test_flow, dut: LinuxSshEngine, user: UserInfo, expect_mtls: bool, server_cert: CertInfo, server_ca: CertInfo,
                      non_matching_client_cert_should_work: bool, verify_connection_func: VerifyConnFunc, dut_ipv6_addr=None,
                      test_certs: List[CertInfo] = TEST_CERTS):
    addr = dut_ipv6_addr or dut.ip
    matching_cert: CertInfo = server_ca
    matching_ca: CertInfo = server_cert
    non_matching_cert: CertInfo = RandomizationTool.select_random_value(test_certs,
                                                                        [matching_cert]).get_returned_value()
    non_matching_ca: CertInfo = RandomizationTool.select_random_value(test_certs, [matching_ca]).get_returned_value()

    if expect_mtls:
        with allure.step('verify mtls only'):
            if test_flow == TestFlowType.ALL_TYPES or test_flow == TestFlowType.GOOD_FLOW:
                with allure.independent_step('goodflow - use suitable cert & cacert on client side'):
                    verify_connection_func(addr, user, True, False, matching_ca, matching_cert)
                if non_matching_client_cert_should_work:
                    with allure.independent_step('goodflow - bad cert & good cacert on client side'):
                        verify_connection_func(addr, user, True, False, matching_ca, non_matching_cert)
            if test_flow == TestFlowType.ALL_TYPES or test_flow == TestFlowType.BAD_FLOW:
                # bug #4064106 still active - [Functional] [mTLS] api mtls is working with an imported ca-cert but not set to api mtls
                # bug rejected because even if a CA is imported in the switch it's used in mtls
                # on gnmi mtls on the other hand - only the installed CA takes place (not using all linux CA pool)
                if not non_matching_client_cert_should_work:
                    with allure.independent_step('badflow - bad cert & good cacert on client side'):
                        verify_connection_func(addr, user, False, False, matching_ca, non_matching_cert)
                with allure.independent_step('badflow - good cert & bad cacert on client side'):
                    verify_connection_func(addr, user, False, False, non_matching_ca, matching_cert)
                with allure.independent_step('badflow - bad cert & bad cacert on client side'):
                    verify_connection_func(addr, user, False, False, non_matching_ca, non_matching_cert)
                with allure.independent_step('badflow - run insecure'):
                    verify_connection_func(addr, user, False, True)
    else:
        with allure.step('verify no mtls - insecure works'):
            if test_flow == TestFlowType.ALL_TYPES or test_flow == TestFlowType.GOOD_FLOW:
                with allure.independent_step('goodflow - run insecure'):
                    verify_connection_func(addr, user, True, True)


def setup_steps():
    CurlTool('', '', '', verify_tools_installed=True)
    scp_player = get_scp_player(TestToolkit.engines)
    import_test_certs(scp_player, TestToolkit.engines.dut, TEST_CERTS)


def cleanup_steps():
    with allure.step('cleanup'):
        System().api.unset(apply=True).verify_result()
