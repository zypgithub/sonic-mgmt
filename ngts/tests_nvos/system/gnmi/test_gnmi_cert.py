import random
import string

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import TestFlowType, ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.conftest import local_adminuser
from ngts.tests_nvos.system.gnmi.constants import CERTIFICATE, DEFAULT_CERTIFICATE, GnmicErr, GNMI_TEST_CERT
from ngts.tests_nvos.system.gnmi.helpers import load_certificate_into_gnmi, verify_gnmi_client


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_gnmi_cert_without_cli(test_flow, engines, local_adminuser, restore_gnmi_cert):
    """
    verify that gnmi works with certificate verification

    1. good-flow: load certificate into gnmi
        bad-flow: don't load certificate into gnmi
    2. run gnmi client without insecure flag
    3. good-flow: expect success
        bad-flow: expect fail
    """
    is_good_flow = test_flow == TestFlowType.GOOD_FLOW
    test_cert = GNMI_TEST_CERT
    if is_good_flow:
        with allure.step('load certificate into gnmi'):
            load_certificate_into_gnmi(engines.dut, test_cert)
    with allure.step(f'run gnmi client with{"" if is_good_flow else "out"} insecure flag - '
                     f'expect {"success" if is_good_flow else "fail"}'):
        verify_gnmi_client(test_flow, test_cert.dn or test_cert.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username,
                           local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL, cacert=test_cert.cacert)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('api', ApiType.ALL_TYPES)
def test_gnmi_cert_cli(api):
    """
    verify gnmi certificate related cli work properly

    1. verify in show that certificate field exists and is set to default
    2. set gnmi certificate
    3. verify in show the new certificate
    4. unset gnmi certificate
    5. verify in show the default certificate value
    6. set gnmi certificate (again)
    7. unset gnmi (entire endpoint)
    8. verify in show the default certificate value
    """
    TestToolkit.tested_api = api
    cert = TestCert.cert_valid_1

    with allure.step('verify in show that certificate field exists and is set to default'):
        gnmi = System().gnmi_server
        out = OutputParsingTool.parse_json_str_to_dictionary(gnmi.show()).get_returned_value()
        assert CERTIFICATE in out, f'field "{CERTIFICATE}" was not found in show gnmi output\n{out}'
        assert out[CERTIFICATE] == DEFAULT_CERTIFICATE, (f'value of field "{CERTIFICATE}" not as expected (default)\n'
                                                         f'expected (default): {DEFAULT_CERTIFICATE}\n'
                                                         f'actual: {out[CERTIFICATE]}')
    with allure.step('set gnmi certificate'):
        gnmi.set(CERTIFICATE, cert.name, apply=True).verify_result()
    with allure.step('verify in show the new certificate'):
        out = OutputParsingTool.parse_json_str_to_dictionary(gnmi.show()).get_returned_value()
        assert out[CERTIFICATE] == cert.name, (f'value of field "{CERTIFICATE}" not as expected\n'
                                               f'expected: {cert.name}\n'
                                               f'actual: {out[CERTIFICATE]}')
    with allure.step('unset gnmi certificate'):
        gnmi.unset(CERTIFICATE, apply=True).verify_result()
    with allure.step('verify in show the default certificate value'):
        out = OutputParsingTool.parse_json_str_to_dictionary(gnmi.show()).get_returned_value()
        assert out[CERTIFICATE] == DEFAULT_CERTIFICATE, (f'value of field "{CERTIFICATE}" not as expected (default)\n'
                                                         f'expected (default): {DEFAULT_CERTIFICATE}\n'
                                                         f'actual: {out[CERTIFICATE]}')
    with allure.step('set gnmi certificate'):
        gnmi.set(CERTIFICATE, cert.name, apply=True).verify_result()
    with allure.step('unset gnmi (entire resource/endpoint)'):
        gnmi.unset(apply=True).verify_result()
    with allure.step('verify default certificate value in show'):
        out = OutputParsingTool.parse_json_str_to_dictionary(gnmi.show()).get_returned_value()
        assert out[CERTIFICATE] == DEFAULT_CERTIFICATE, (f'value of field "{CERTIFICATE}" not as expected (default)\n'
                                                         f'expected (default): {DEFAULT_CERTIFICATE}\n'
                                                         f'actual: {out[CERTIFICATE]}')


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_gnmi_cert_set_cert(test_flow, local_adminuser):
    """
    verify that set command loads the certificate into gnmi,
        so clients with the right CA crt can communicate with gnmi with/out skip-verify flag

    1. set gnmi cert
    2. run client without skip-verify flag, using right CA crt - expect success
    3. run client with skip-verify flag - expect success
    """
    cert = TestCert.cert_valid_1 if test_flow == TestFlowType.GOOD_FLOW else TestCert.cert_ca_mismatch
    with allure.step('set gnmi certificate'):
        System().gnmi_server.set(CERTIFICATE, cert.name, apply=True).verify_result()
    with allure.step(
            f'run client without skip-verify flag, using right CA crt - expect {"success" if test_flow == TestFlowType.GOOD_FLOW else "fail"}'):
        verify_gnmi_client(test_flow, cert.dn or cert.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username,
                           local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL, cacert=cert.cacert)
    with allure.step('run client with skip-verify flag - expect success'):
        verify_gnmi_client(TestFlowType.GOOD_FLOW, cert.dn or cert.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username,
                           local_adminuser.password, True, GnmicErr.CERT_VERIFY_FAIL)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_cert_set_non_existing_cert(engines, local_adminuser):
    """
    verify that when trying to set gnmi certificate with id of non-existing certificate, there is failure

    1. set non existing gnmi cert - expect command fails
    2. run client without skip-verify flag, using right CA crt - expect fail
    """
    with allure.step('set non existing gnmi certificate'):
        bad_cert_id = ''.join(random.choice(string.ascii_letters) for _ in range(10))
        System().gnmi_server.set(CERTIFICATE, bad_cert_id, apply=True).verify_result(False)
        NvueGeneralCli.detach_config(engines.dut)
    with allure.step('run client without skip-verify flag, using some CA crt - expect fail'):
        verify_gnmi_client(TestFlowType.BAD_FLOW, engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username, local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL,
                           cacert=TestCert.cert_valid_1.cacert)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_cert_unset_cert(local_adminuser):
    """
    Verify that after unset gnmi certificate, client cannot communicate with gnmi using the CA that supports the cert

    1.	Unset gnmi cert
    2.	Run client with CA cert that supports the cleared cert
    3.	Expect fail
    4.	Set cert again
    5.	Unset entire gnmi
    6.	Run client with CA cert that supports that cert
    7.	Expect fail
    """
    cert = TestCert.cert_valid_1
    with allure.step('set gnmi certificate'):
        gnmi = System().gnmi_server
        gnmi.set(CERTIFICATE, cert.name, apply=True).verify_result()
    with allure.step('unset gnmi certificate'):
        gnmi.unset(CERTIFICATE, apply=True).verify_result()
    with allure.step('run client without skip-verify flag, using right CA crt - expect fail'):
        verify_gnmi_client(TestFlowType.BAD_FLOW, cert.ip or cert.dn, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username, local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL,
                           cacert=cert.cacert)
    with allure.step('set gnmi certificate'):
        gnmi.set(CERTIFICATE, cert.name, apply=True).verify_result()
    with allure.step('unset all gnmi'):
        gnmi.unset(apply=True).verify_result()
    with allure.step('run client without skip-verify flag, using right CA crt - expect fail'):
        verify_gnmi_client(TestFlowType.BAD_FLOW, cert.ip or cert.dn, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username, local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL,
                           cacert=cert.cacert)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_cert_set_cert_after_unset(local_adminuser):
    """
    Verify that can set certificate after unset, and that it works

    1.	Unset gnmi cert
    2.	Set back gnmi cert
    3.	Run client with CA that supports that cert
    4.	Expect success
    """
    cert = TestCert.cert_valid_1
    with allure.step('set gnmi certificate after unset'):
        with allure.step('set'):
            gnmi = System().gnmi_server
            gnmi.set(CERTIFICATE, cert.name, apply=True).verify_result()
        with allure.step('unset'):
            gnmi.unset(CERTIFICATE, apply=True).verify_result()
        with allure.step('set'):
            gnmi.set(CERTIFICATE, cert.name, apply=True).verify_result()
    with allure.step('run client without skip-verify flag, using right CA crt - expect success'):
        verify_gnmi_client(TestFlowType.GOOD_FLOW, cert.ip or cert.dn, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username, local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL,
                           cacert=cert.cacert)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_delete_cert_in_use_by_gnmi():
    """
    Verify that delete certificate that is in use by gnmi fails

    1.	set gnmi cert
    2.	delete that cert from the system
    3.	verify failure
    """
    cert = TestCert.cert_valid_1
    with allure.step('set gnmi certificate'):
        system = System()
        system.gnmi_server.set(CERTIFICATE, cert.name, apply=True).verify_result()
    with allure.step('delete that certificate from the system'):
        res = system.security.certificate.cert_id[cert.name].action_delete()
    with allure.step('verify fail'):
        res.verify_result(False)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_reboot_system(engines, local_adminuser):
    """
    Verify that gnmi keeps using certificate after reboot only after save

    1.	set gnmi cert (don't save)
    2.	reboot
    3.  verify cert doesn't appear in show
    4.	try using the cert - expect fail
    5.  set gnmi cert again (and save)
    6.  reboot
    7.  verify cert appears in show
    8.  try using the cert - expect success
    """
    cert = TestCert.cert_valid_1
    with allure.step(f'save config with test user "{local_adminuser.username}"'):
        NvueGeneralCli.save_config(engines.dut)
    try:
        with allure.step('set gnmi certificate'):
            system = System()
            system.gnmi_server.set(CERTIFICATE, cert.name, apply=True).verify_result()
        with allure.step('reboot the system'):
            system.action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()
        with allure.step("verify cert doesn't appear in show"):
            out = OutputParsingTool.parse_json_str_to_dictionary(system.gnmi_server.show()).get_returned_value()
            assert cert.name != out[
                CERTIFICATE], f'{cert.name} unexpectedly appears in show gnmi output after reboot (without save)'
        with allure.step('try using the cert - expect fail'):
            verify_gnmi_client(TestFlowType.BAD_FLOW, cert.ip or cert.dn, GnmiConsts.GNMI_DEFAULT_PORT,
                               local_adminuser.username, local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL,
                               cacert=cert.cacert)
        with allure.step('set gnmi cert again (and save)'):
            with allure.step('set gnmi certificate'):
                system.gnmi_server.set(CERTIFICATE, cert.name, apply=True).verify_result()
            with allure.step('save config'):
                NvueGeneralCli.save_config(engines.dut)
        with allure.step('reboot the system'):
            system.action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()
        with allure.step("verify cert appears in show"):
            out = OutputParsingTool.parse_json_str_to_dictionary(system.gnmi_server.show()).get_returned_value()
            assert cert.name == out[
                CERTIFICATE], f'{cert.name} does not appear in show gnmi output after reboot (with save)\nout:\n{out}'
        with allure.step('try using the cert - expect fail'):
            verify_gnmi_client(TestFlowType.GOOD_FLOW, cert.ip or cert.dn, GnmiConsts.GNMI_DEFAULT_PORT,
                               local_adminuser.username, local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL,
                               cacert=cert.cacert)
    finally:
        with allure.step('remove test configurations from saved config'):
            system.aaa.user.user_id[local_adminuser.username].unset().verify_result()
            system.gnmi_server.unset(apply=True).verify_result()
            NvueGeneralCli.save_config(engines.dut)
