import logging

import pytest

from ngts.nvos_constants.constants_nvos import CertificateFiles, SyslogConsts, OpenApiReqType, ApiType, SystemConsts, \
    TestFlowType
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.constants import TestCert, GET_SYSTEM_VERSION_PATH, CertMsgs
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api, test_flow', [(ApiType.NVUE, TestFlowType.GOOD_FLOW), (ApiType.NVUE, TestFlowType.BAD_FLOW), (ApiType.OPENAPI, TestFlowType.GOOD_FLOW)])
def test_certificate_commands(engines, test_api, test_flow):
    """
    Test certificate mgmt commands:
        1. nv action import system security certificate <cert-id_1> uri-bundle <https://URI>
        2. nv action import system security certificate <cert-id_2> uri-public-key <scp://URI> uri-private-key <scp://URI>
        3. nv set system api certificate <cert-id_1>
        4. nv action delete system security certificate
    """
    TestToolkit.tested_api = test_api
    system = System()
    player = get_scp_player(engines)
    cert_id_bundle = 'cert_id_1'
    cert_id_public_private = "cert_id_2"
    cert_list = []
    test_cert = TestCert.cert_valid_1

    with allure.step(f'import cert {test_cert.name} named {cert_id_bundle} uri-bundle with URI'):
        bundle_uri = generate_scp_uri_using_player(player, test_cert.p12_bundle)
        system.security.certificate.cert_id[cert_id_bundle].action_import(uri_bundle=bundle_uri,
                                                                          passphrase=test_cert.p12_password).verify_result()
        verify_imported_certificate(engines, system, cert_id=cert_id_bundle,
                                    first_arg=CertificateFiles.PASSPHRASE, second_arg=CertificateFiles.URI_BUNDLE,
                                    test_api=test_api)
        cert_list.append(cert_id_bundle)

    with allure.step(f'import cert {test_cert.name} named {cert_id_public_private} with public and private key'):
        public_uri = generate_scp_uri_using_player(player, test_cert.public)
        private_uri = generate_scp_uri_using_player(player, test_cert.private)
        system.security.certificate.cert_id[cert_id_public_private].action_import(uri_private_key=private_uri,
                                                                                  uri_public_key=public_uri).verify_result()
        verify_imported_certificate(engines, system, cert_id=cert_id_public_private,
                                    first_arg=CertificateFiles.PRIVATE_KEY_FILE,
                                    second_arg=CertificateFiles.PUBLIC_KEY_FILE, test_api=test_api)
        cert_list.append(cert_id_public_private)

    with allure.step(f'Install certificate'):
        for cert in cert_list:
            system.api.set(CertificateFiles.CERTIFICATE, cert, apply=True).verify_result()
            verify_show_api_output(system, cert)

    with allure.step("Verify certificate installation"):
        _verify_certificate(system, cert_list)

    with allure.step("Run open api command using imported certificate"):
        if test_flow == TestFlowType.GOOD_FLOW:
            client = CurlTool(server_host=test_cert.dn, username=engines.dut.username,
                              password=engines.dut.password, cacert=test_cert.cacert)
            out, err = client.request(request_type=OpenApiReqType.GET, path=GET_SYSTEM_VERSION_PATH,
                                      skip_cert_verify=False)
            verify_output(out, err, True)
        else:
            mismatch_cert = TestCert.cert_ca_mismatch
            client = CurlTool(server_host=test_cert.dn, username=engines.dut.username, password=engines.dut.password,
                              cacert=mismatch_cert.cacert)
            out, err = client.request(request_type=OpenApiReqType.GET, path=GET_SYSTEM_VERSION_PATH,
                                      skip_cert_verify=False)
            verify_output(out, err, False)

    with allure.step(f'Unset certificates'):
        system.api.unset(op_param=CertificateFiles.CERTIFICATE, apply=True).verify_result()
        verify_show_api_output(system, CertificateFiles.DEFAULT_CERTIFICATE)

    with allure.step('delete imported certificates'):
        for cert in cert_list:
            system.security.certificate.cert_id[cert].action_delete().verify_result()


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ca_certificate_commands(engines, test_api):
    TestToolkit.tested_api = test_api
    system = System()
    player = get_scp_player(engines)
    ca_cert_id = "ca_cert_id"
    test_cert = TestCert.cert_mgmt_test_cacert

    with allure.step(f'import system security ca-certificate {ca_cert_id} with URI'):
        uri = generate_scp_uri_using_player(player, test_cert.public)
        system.security.ca_certificate.cert_id[ca_cert_id].action_import(uri=uri).verify_result()
        verify_imported_certificate(engines, system, ca_cert_id, CertificateFiles.URI, test_api=test_api,
                                    check_cacert=True)

    with allure.step("Verify certificate installation"):
        _verify_certificate(system, [ca_cert_id], True)

    with allure.step('delete imported ca-certificates'):
        for cert in [ca_cert_id]:
            system.security.ca_certificate.cert_id[cert].action_delete().verify_result()


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
@pytest.mark.parametrize('test_flow', [TestFlowType.GOOD_FLOW])
def test_import_certificate_with_long_passphrase(test_api, test_flow, engines):
    """
    test that users able to import certificate bundle with long passphrase
    """
    TestToolkit.tested_api = test_api
    test_cert = TestCert.cert_valid_1_long_passphrase
    cert_id_bundle = test_cert.name
    system = System()
    player = get_scp_player(engines)

    with allure.step(f'import cert {test_cert.name} named {cert_id_bundle} uri-bundle with URI'):
        bundle_uri = generate_scp_uri_using_player(player, test_cert.p12_bundle)
        system.security.certificate.cert_id[cert_id_bundle].action_import(uri_bundle=bundle_uri,
                                                                          passphrase=test_cert.p12_password).verify_result()
        verify_imported_certificate(engines, system, cert_id=cert_id_bundle,
                                    first_arg=CertificateFiles.PASSPHRASE, second_arg=CertificateFiles.URI_BUNDLE,
                                    test_api=test_api)

    with allure.step(f'Install certificate'):
        system.api.set(CertificateFiles.CERTIFICATE, cert_id_bundle, apply=True).verify_result()
        verify_show_api_output(system, cert_id_bundle)

    with allure.step("Verify certificate installation"):
        _verify_certificate(system, [cert_id_bundle])

    with allure.step("Run open api command using imported certificate"):
        if test_flow == TestFlowType.GOOD_FLOW:
            client = CurlTool(server_host=test_cert.dn, username=engines.dut.username,
                              password=engines.dut.password, cacert=test_cert.cacert)
            out, err = client.request(request_type=OpenApiReqType.GET, path=GET_SYSTEM_VERSION_PATH,
                                      skip_cert_verify=False)
            verify_output(out, err, True)
        else:
            mismatch_cert = TestCert.cert_ca_mismatch
            client = CurlTool(server_host=test_cert.dn, username=engines.dut.username, password=engines.dut.password,
                              cacert=mismatch_cert.cacert)
            out, err = client.request(request_type=OpenApiReqType.GET, path=GET_SYSTEM_VERSION_PATH,
                                      skip_cert_verify=False)
            verify_output(out, err, False)


def _verify_certificate(system, cert_list, check_cacert: bool = False):
    with allure.step('verify the show command output'):
        for cert in cert_list:
            verify_show_security_ouput(system, cert, True, check_cacert)


def verify_output(out, err, should_pass):
    if should_pass:
        assert SystemConsts.VERSION_IMAGE in out, f"Failed to send open api command using certificate.\n Expected to find {SystemConsts.VERSION_IMAGE} in out. Got: {out}"
    else:
        assert CertMsgs.SSL_CERTIFICATE_PROBLEM in err, f"Open api command passed while expected to fail.\n Expected to find {CertMsgs.SSL_CERTIFICATE_PROBLEM} in err. Got: {err}"


def verify_show_api_output(system, expected_cert_id):
    show_api_output = OutputParsingTool.parse_json_str_to_dictionary(system.api.show()).get_returned_value()
    certificate_value = show_api_output.get(CertificateFiles.CERTIFICATE, None)
    assert certificate_value, f"{CertificateFiles.CERTIFICATE} not found in the output"
    assert certificate_value == expected_cert_id, \
        f'Expected: "{CertificateFiles.CERTIFICATE}": "{expected_cert_id} \n " \
            Got: "{CertificateFiles.CERTIFICATE}": "{certificate_value}"'


def verify_show_security_ouput(system, cert_id, should_exist, check_cacert: bool = False):
    resource = system.security.ca_certificate if check_cacert else system.security.certificate
    with allure.step(f"Verify {cert_id} exists in show output"):
        show_output = resource.show()
        if should_exist:
            assert cert_id in show_output, f"Expected to find {cert_id} in show output. Got: {show_output}"
        else:
            assert cert_id not in show_output, f"Expected not to find {cert_id} in show output. Got: {show_output}"


def verify_imported_certificate(engines, system, cert_id, first_arg, test_api, second_arg="",
                                check_cacert: bool = False):
    verify_show_security_ouput(system, cert_id, True, check_cacert)

    if test_api == ApiType.NVUE:
        with allure.step('verify the password is hidden in the logs'):
            with allure.step('Check history command'):
                history_output = engines.dut.run_cmd('history 4')
                str_to_serach = f"{first_arg} *" + (f" {second_arg} *" if second_arg else "")
                assert str_to_serach in history_output, "the password is not hidden in 'history' command"
            with allure.step('Check logs'):
                logs_output = engines.dut.run_cmd(f'tail -4 {SyslogConsts.NVUE_LOG_PATH}')
                logs_output_1 = engines.dut.run_cmd(f'tail -4 {SyslogConsts.NVUE_LOG_PATH}.1')
                assert str_to_serach in logs_output or str_to_serach in logs_output_1, "the password is not hidden in syslog"
