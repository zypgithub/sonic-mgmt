import concurrent.futures
import random
import select
import string
import time

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
from ngts.tests_nvos.general.security.helpers import remove_etc_host_mapping_to_dn, add_etc_host_mapping_to_dn
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.helpers.pytest_helpers import get_cur_test_param_value
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import CERTIFICATE, DEFAULT_CERTIFICATE, GnmicErr, \
    MAX_GNMI_CONNECTIVITY_TIME, GNMI_TEST_CERT, ETC_HOSTS, GnmiMode
from ngts.tests_nvos.system.gnmi.helpers import verify_gnmi_client, get_timestamp_of_first_gnmi_response, \
    validate_gnmi_is_running_and_stream_updates


@pytest.fixture(scope='module', autouse=True)
def import_test_certs(import_required_test_certs):
    pass


@pytest.fixture()
def add_etc_host_mapping_for_ipv6_cert_test(request, engines, dut_ipv6_addr):
    should_run = get_cur_test_param_value(request, 'addressing_type') == AddressingType.IPV6
    cert = GNMI_TEST_CERT
    if should_run:
        with allure.step(f'add ipv6 mapping of new dut hostname to {ETC_HOSTS}'):
            remove_etc_host_mapping_to_dn(cert.dn)
            add_etc_host_mapping_to_dn(cert.dn, dut_ipv6_addr)
    yield
    if should_run:
        with allure.step(f'remove ipv6 mapping of new dut hostname to {ETC_HOSTS} and restore ipv4 mapping'):
            remove_etc_host_mapping_to_dn(cert.dn)
            add_etc_host_mapping_to_dn(cert.dn, engines.dut.ip)


# @pytest.mark.system
# @pytest.mark.gnmi
# @pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
# def test_gnmi_cert_without_cli(test_flow, engines, local_adminuser, restore_gnmi_cert):
#     """
#     verify that gnmi works with certificate verification
#
#     1. good-flow: load certificate into gnmi
#         bad-flow: don't load certificate into gnmi
#     2. run gnmi client without insecure flag
#     3. good-flow: expect success
#         bad-flow: expect fail
#     """
#     is_good_flow = test_flow == TestFlowType.GOOD_FLOW
#     test_cert = GNMI_TEST_CERT
#     if is_good_flow:
#         with allure.step('load certificate into gnmi'):
#             load_certificate_into_gnmi(engines.dut, test_cert)
#     with allure.step(f'run gnmi client with{"" if is_good_flow else "out"} insecure flag - '
#                      f'expect {"success" if is_good_flow else "fail"}'):
#         verify_gnmi_client(test_flow, test_cert.dn or test_cert.ip, GnmiConsts.GNMI_DEFAULT_PORT,
#                            local_adminuser.username,
#                            local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL, cacert=test_cert.cacert)


def check_gnmi_cert_cli(api):
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
    check_gnmi_cert_cli(api)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('api', ApiType.ALL_TYPES)
def test_gnmi_cert_cli_when_gnmi_disabled(api):
    """
    verify gnmi certificate related cli work properly

    0. disable gnmi
    1. verify in show that certificate field exists and is set to default
    2. set gnmi certificate
    3. verify in show the new certificate
    4. unset gnmi certificate
    5. verify in show the default certificate value
    6. set gnmi certificate (again)
    7. unset gnmi (entire endpoint)
    8. verify in show the default certificate value
    """
    with allure.step('disable gnmi'):
        System().gnmi_server.set('state', 'disabled', apply=True).verify_result()

    check_gnmi_cert_cli(api)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
@pytest.mark.parametrize('addressing_type', [AddressingType.IPV4, AddressingType.IPV6])
def test_gnmi_cert_set_cert(test_flow, addressing_type, local_adminuser, add_etc_host_mapping_for_ipv6_cert_test):
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
        verify_gnmi_client(test_flow, cert.dn or cert.ip, GnmiConsts.GNMI_DEFAULT_PORT, local_adminuser.username,
                           local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL, cacert=cert.cacert)
    with allure.step('run client with skip-verify flag - expect success'):
        verify_gnmi_client(TestFlowType.GOOD_FLOW, cert.dn or cert.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username, local_adminuser.password, True, GnmicErr.CERT_VERIFY_FAIL)


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


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_set_cert_response_time(local_adminuser):
    """
    Check how long it takes from the time setting certificate, till clients using the CA-cert receive data

    1. set cert-1 to gnmi
    2. run client using ca-cert of another cert (cert-2)
    3. set cert-2 to gnmi
    4. receive data wit client
    5. measure time between steps 3 and 4
    """
    cert1 = TestCert.cert_valid_1
    cert2 = TestCert.cert_valid_2

    with concurrent.futures.ThreadPoolExecutor() as executor:
        with allure.step(f'set gnmi cert1: {cert1.name}'):
            gnmi = System().gnmi_server
            gnmi.set(CERTIFICATE, cert1.name, apply=True).verify_result()
        with allure.step(f'in background - run client using cacert of cert2: {cert2.name}'):
            client_thread = executor.submit(get_timestamp_of_first_gnmi_response, *(local_adminuser, cert2))
        with allure.step(f'set gnmi cert2: {cert2.name}'):
            gnmi.set(CERTIFICATE, cert2.name, apply=True).verify_result()
            apply_timestamp = time.time()
        with allure.step(f'wait and get timestamp of first response after cert change'):
            response_timestamp = client_thread.result()
            interval_result = response_timestamp - apply_timestamp
        with allure.step(f'interval result: {interval_result} seconds. assert < limit ({MAX_GNMI_CONNECTIVITY_TIME})'):
            assert interval_result < MAX_GNMI_CONNECTIVITY_TIME, (
                f'gnmi connectivity time was too long after certificate change.\n'
                f'expected limit: {MAX_GNMI_CONNECTIVITY_TIME} seconds\n'
                f'actual: {interval_result} seconds')


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_cert_rotation(engines, devices):
    """
    Check gnmi rotation works when changing certificate on fly

    1. Set cert-1 to gnmi
    2. Run client using ca-cert1 and subscribe
    3. Set cert-2 to gnmi
    4. Verify connection was not interrupted
    5. Verify still receiving new data
    """
    cert1 = TestCert.cert_valid_1
    cert2 = TestCert.cert_valid_2
    cert3 = TestCert.cert_ca_mismatch
    gnmi = System().gnmi_server
    username = devices.dut.default_username
    password = devices.dut.default_password

    with allure.step(f'set gnmi cert: {cert1.name}'):
        gnmi.set(CERTIFICATE, cert1.name, apply=True).verify_result()

    with allure.step('Subscribe to gnmi client stream'):
        client = GnmiClient(cert1.dn, GnmiConsts.GNMI_DEFAULT_PORT, username, password,
                            cacert=cert1.cacert)
        _, _, gnmi_process = client.gnmic_subscribe(prefix='platform-general', path='', mode=GnmiMode.STREAM,
                                                    cacert=cert1.cacert, keep_session_alive=True)

    output, err = read_process_for_specified_time(gnmi_process, GnmiConsts.SLEEP_TIME_FOR_UPDATE)
    validate_gnmi_streaming_output(output, err)

    with allure.step(f'change gnmi cert to: {cert2.name}'):
        gnmi.set(CERTIFICATE, cert2.name, apply=True).verify_result()

    with allure.step('Verify still receiving updated after changing to other valid cert'):
        output, err = read_process_for_specified_time(gnmi_process, GnmiConsts.SLEEP_TIME_FOR_UPDATE)
        validate_gnmi_streaming_output(output, err)

    with allure.step(f'change gnmi cert to invalid: {cert3.name}'):
        gnmi.set(CERTIFICATE, cert3.name, apply=True).verify_result()

    output, err = read_process_for_specified_time(gnmi_process, GnmiConsts.SLEEP_TIME_FOR_UPDATE)
    validate_gnmi_streaming_output(output, err)


def validate_gnmi_streaming_output(output, err):
    with allure.step("Validate gnmi streaming is working and doesn't contain certification errors"):
        has_failure = False
        for line_error in err:
            if "failed to verify certificate" in line_error:
                has_failure = True
                break
        assert not has_failure, "The gnmi error contain certificate validation error"
        assert output, "No streaming from gnmi was received"


def validate_gnmi_mismatch(err):
    with allure.step("Validate gnmi streaming is not working and contains certification errors"):
        for line_error in err:
            if "failed to verify certificate" in line_error:
                assert True
        assert False, "We should see cert validation fail"


def read_process_for_specified_time(process, timeout):
    with allure.step(f"Reading gnmi stream stdout and stderr for {timeout}s"):
        output = []
        err = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            out_ready, _, _ = select.select([process.stdout], [], [], 0.1)
            err_ready, _, _ = select.select([process.stderr], [], [], 0.1)
            for stream in out_ready:
                line = stream.readline()
                if line:
                    output.append(line.decode('utf-8').strip())

            for stream in err_ready:
                line = stream.readline()
                if line:
                    err.append(line.decode('utf-8').strip())

        return output, err
