import random
import string
from typing import List

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType, TestFlowType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.nmx_cert.constants import Defaults, EncryptionMode, ENABLED, DISABLED, STATE
from ngts.tests_nvos.general.security.nmx_cert.helpers import verify_manager_show, verify_cert_show, verify_cacert_show, \
    verify_encryption_show, verify_client_connection
from ngts.tests_nvos.system.gnmi.conftest import scp_player


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_manager_cli(test_api):
    """
    Verify that all CLI work and check values change properly in show

    1.	Run show commands
    2.	Verify outputs contain the required fields
    3.	Run update ca/certificate
    4.	Verify in show that the related fields change accordingly
    5.	Run restore ca/certificate
    6.	Verify in show that related fields restored to default
    7.	Run update encryption (to all options)
    8.	Verify in show that related field updates accordingly
    """
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    cert = TestCert.cert_valid_1
    # TODO: add more static checks: config.json and cert files
    with allure.step('Verify outputs contain the required fields'):
        verify_manager_show()
        verify_cert_show()
        verify_cacert_show()
        verify_encryption_show()  # TODO: is there show encryption?
    with allure.step('Run update ca/certificate'):
        cluster.manager.certificate.action_update(cert.name).verify_result()
        cluster.manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Verify in show that the related fields change accordingly'):
        verify_manager_show(expect_cert=cert.name, expect_cacert=cert.cacert_name)
        verify_cert_show(expect_cert_id=cert.name)
        verify_cacert_show(expect_cert_id=cert.cacert_name)
    with allure.step('Run restore ca/certificate'):
        cluster.manager.certificate.action_restore().verify_result()
        cluster.manager.ca_certificate.action_restore().verify_result()
    with allure.step('Verify in show that related fields restored to default'):
        verify_manager_show(expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT)
        verify_cert_show(expect_cert_id=Defaults.CERT)
        verify_cacert_show(expect_cert_id=Defaults.CACERT)
    for mode in EncryptionMode.ALL_MODES:
        with allure.step(f'Run update encryption: {mode}'):
            cluster.manager.encryption.action_update(mode).verify_result()
        with allure.step('Verify in show that related field updates accordingly'):
            verify_manager_show(expect_encryption=mode)
            verify_encryption_show(expect_mode=mode)
    with allure.step('Run restore encryption'):
        cluster.manager.encryption.action_restore().verify_result()
    with allure.step('Verify in show that related fields restored to default'):
        verify_manager_show(expect_encryption=Defaults.ENCRYPTION)
        verify_encryption_show(expect_mode=Defaults.ENCRYPTION)
    with allure.step('Run update manager (enable manager communication)'):
        cluster.manager.action_update().verify_result()
    with allure.step('Verify in show that related fields'):
        verify_manager_show(expect_state=ENABLED)  # TODO: is there state field?
    with allure.step('Run restore manager (disable manager communication)'):
        cluster.manager.action_update().verify_result()
    with allure.step('Verify in show that related fields restored to default'):
        verify_manager_show(expect_state=DISABLED)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_manager_cmd_fail_when_cluster_off(test_api):
    """
    Verify that update/restore manager commands fail when cluster disabled

    1.	Make sure cluster disabled
    2.	Run manager update/restore command
    3.	Verify failed and show doesn’t change
    """
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    cert = TestCert.cert_valid_1
    with allure.step('Make sure cluster disabled'):
        cluster.set(STATE, DISABLED).verify_result()
    with allure.step('Run manager update/restore command'):
        results: List[ResultObj] = []
        with allure.step('run update commands'):
            results.append(cluster.manager.action_update())
            results.append(cluster.manager.certificate.action_update(cert.name))
            results.append(cluster.manager.ca_certificate.action_update(cert.cacert_name))
            results.append(cluster.manager.encryption.action_update())
        with allure.step('run restore commands'):
            results.append(cluster.manager.encryption.action_restore())
            results.append(cluster.manager.certificate.action_restore())
            results.append(cluster.manager.ca_certificate.action_restore())
            results.append(cluster.manager.action_restore())
    with allure.step('Verify failed and show doesn’t change'):
        with allure.step('verify all commands failed'):
            for result in results:
                result.verify_result(False)
        with allure.step('verify no change in related fields'):
            verify_manager_show(expect_state=Defaults.STATE, expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                expect_encryption=Defaults.ENCRYPTION)
            verify_cert_show(expect_cert_id=Defaults.CERT)
            verify_cacert_show(expect_cert_id=Defaults.CACERT)
            verify_encryption_show(expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_manager_cmd_fail_when_manager_off(test_api):
    """
    Verify that update/restore inner manager commands fail when cluster manager disabled

    1.	Make sure cluster enabled, cluster manager disabled
    2.	Run inner manager update/restore command
    3.	Verify failed and show doesn’t change

    """
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    cert = TestCert.cert_valid_1
    with allure.step('Make sure cluster enabled, cluster manager disabled'):
        cluster.set(STATE, ENABLED).verify_result()
        cluster.manager.action_restore().verify_result()
    with allure.step('Run manager update/restore command'):
        results: List[ResultObj] = []
        with allure.step('run update commands'):
            results.append(cluster.manager.certificate.action_update(cert.name))
            results.append(cluster.manager.ca_certificate.action_update(cert.cacert_name))
            results.append(cluster.manager.encryption.action_update())
        with allure.step('run restore commands'):
            results.append(cluster.manager.encryption.action_restore())
            results.append(cluster.manager.certificate.action_restore())
            results.append(cluster.manager.ca_certificate.action_restore())
    with allure.step('Verify failed and show doesn’t change'):
        with allure.step('verify all commands failed'):
            for result in results:
                result.verify_result(False)
        with allure.step('verify no change in related fields'):
            verify_manager_show(expect_state=DISABLED, expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                expect_encryption=Defaults.ENCRYPTION)
            verify_cert_show(expect_cert_id=Defaults.CERT)
            verify_cacert_show(expect_cert_id=Defaults.CACERT)
            verify_encryption_show(expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_delete_cert_fail_when_is_used(test_api):
    """
    Verify that we cannot delete certs when are used (updated) for cluster manager config

    1.	Update certs
    2.	Try to remove certs
    3.	Verify fail and that there’s no change in related fields
    """
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    cert = TestCert.cert_valid_1
    with allure.step('Update certs'):
        cluster.manager.certificate.action_update(cert.name).verify_result()
        cluster.manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Try to remove certs'):
        security = System().security
        res_cert = security.certificate.cert_id[cert.name].action_delete()
        res_cacert = security.ca_certificate.cert_id[cert.cacert_name].action_delete()
    with allure.step('Verify fail and that there’s no change in related fields'):
        res_cert.verify_result(False)
        res_cacert.verify_result(False)
        verify_manager_show(expect_cert=cert.name, expect_cacert=cert.cacert_name)
        verify_cert_show(expect_cert_id=cert.name)
        verify_cacert_show(expect_cert_id=cert.cacert_name)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_update_bad_param(test_api):
    """
    Verify that updating with bad param fails, and show output is not changed

    1.	Run update to cert-id that was not imported
    2.	Verify error
    3.	Verify in show that related field doesn’t change
    """
    TestToolkit.tested_api = test_api
    manager = Cluster().manager
    rand_str = ''.join(random.choice(string.ascii_lowercase) for _ in range(6))
    with allure.step('Run update to cert-id that was not imported'):
        res_cert = manager.certificate.action_update(rand_str)
        res_cacert = manager.ca_certificate.action_update(rand_str)
        res_encryption = manager.encryption.action_update(rand_str)
    with allure.step('Verify error'):
        res_cert.verify_result(False)
        res_cacert.verify_result(False)
        res_encryption.verify_result(False)
    with allure.step("Verify in show that related fields don’t change"):
        verify_manager_show(expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                            expect_encryption=Defaults.ENCRYPTION)
        verify_cert_show(expect_cert_id=Defaults.CERT)
        verify_cacert_show(expect_cert_id=Defaults.CACERT)
        verify_encryption_show(expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_update_encryption_without_required_cert(test_api):
    """
    Verify that:
        1. can’t configure tls when certificate is not loaded.
        2. can’t configure mtls when ca-certificate is not loaded.

    Setup: clear ca/certificate
    1.	Try configure tls
    2.	Verify error and show output is not changed
    3.	Try configure mtls
    4.	Verify error and show output is not changed
    """
    TestToolkit.tested_api = test_api
    manager = Cluster().manager
    with allure.step('Try configure tls'):
        res = manager.encryption.action_update(EncryptionMode.TLS)
    with allure.step('Verify error and show output is not changed'):
        res.verify_result(False)
        verify_manager_show(expect_encryption=Defaults.ENCRYPTION)
        verify_encryption_show(expect_mode=Defaults.ENCRYPTION)
    with allure.step('Try configure mtls'):
        res = manager.encryption.action_update(EncryptionMode.MTLS)
    with allure.step('Verify error and show output is not changed'):
        res.verify_result(False)
        verify_manager_show(expect_encryption=Defaults.ENCRYPTION)
        verify_encryption_show(expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_restore_cert_when_in_encryption_mode(test_api):
    """
    Verify that clearing ca/certificate fails when encryption mode is m/tls, and show output is not changed

    1.	Load certificate
    2.	Configure tls
    3.	Try restore certificate
    4.	Verify error and show is not changed
    5.	Load ca-cert
    6.	Configure mtls
    7.	Try restore certificate
    8.	Verify error and show is not changed
    9.	Try restore ca-cert
    10.	Verify error and show is not changed
    """
    TestToolkit.tested_api = test_api
    manager = Cluster().manager
    cert = TestCert.cert_valid_1

    with allure.step('Load certificate'):
        manager.certificate.action_update(cert.name).verify_result()
    with allure.step('Configure tls'):
        manager.encryption.action_update(EncryptionMode.TLS).verify_result()
    with allure.step('Try restore certificate'):
        res = manager.certificate.action_restore()
    with allure.step('Verify error and show is not changed'):
        res.verify_result(False)
        verify_manager_show(expect_cert=cert.name)
        verify_cert_show(expect_cert_id=cert.name)
    with allure.step('Load ca-cert'):
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Configure mtls'):
        manager.encryption.action_update(EncryptionMode.MTLS).verify_result()
    with allure.step('Try restore certificate'):
        res = manager.certificate.action_restore()
    with allure.step('Verify error and show is not changed'):
        res.verify_result(False)
        verify_manager_show(expect_cert=cert.name)
        verify_cert_show(expect_cert_id=cert.name)
    with allure.step('Try restore ca-certificate'):
        res = manager.certificate.action_restore()
    with allure.step('Verify error and show is not changed'):
        res.verify_result(False)
        verify_manager_show(expect_cacert=cert.cacert_name)
        verify_cacert_show(expect_cert_id=cert.cacert_name.name)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_connection_after_update_encryption(test_flow):
    """
    Verify that client can communicate with nmx-c
        * run with all possible encryption modes

    1.	Import and load cert & cacert
    2.	Update encryption mode
    3.	Run client request to nmx-c using matching cert & cacert of client side (– check encryption works?)
    4.	Expect success
    """
    test_is_good_flow = test_flow == TestFlowType.GOOD_FLOW
    # test_is_good_flow = encryption_mode == EncryptionMode.MTLS

    manager = Cluster().manager

    nmx_c_cert = TestCert.cert_valid_1
    client_cert = TestCert.cert_valid_2

    nmx_c_cacert = client_cert if test_is_good_flow else nmx_c_cert
    client_cacert = nmx_c_cert if test_is_good_flow else client_cert

    with allure.step('load cert & cacert to nmx-c'):
        manager.certificate.action_update(nmx_c_cert.name).verify_result()
        manager.ca_certificate.action_update(nmx_c_cacert.cacert_name).verify_result()
    with allure.step('verify connection using all encryption modes'):
        verify_client_connection(test_is_good_flow, {mode: True for mode in EncryptionMode.ALL_MODES}, nmx_c_cert,
                                 client_cert, nmx_c_cacert, client_cacert)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_connection_after_restore_encryption(test_flow):
    """
    Verify that after encryption mode – client can connect only in None mode

    1.	update cert & cacert & m/tls
    2.	restore encryption
    3.	verify client can connect only with NONE
    """
    manager = Cluster().manager
    nmx_c_cert = client_cert = nmx_c_cacert = client_cacert = TestCert.cert_valid_1

    with allure.step('update cert & cacert & m/tls'):
        manager.certificate.action_update(nmx_c_cert.name).verify_result()
        manager.ca_certificate.action_update(nmx_c_cacert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])).verify_result()
    with allure.step('restore encryption'):
        manager.encryption.action_restore().verify_result()
    with allure.step('verify client can connect only with NONE'):
        verify_client_connection(test_flow == TestFlowType.ALL_TYPES,
                                 {mode: mode == EncryptionMode.NONE for mode in EncryptionMode.ALL_MODES},
                                 nmx_c_cert, client_cert, nmx_c_cacert, client_cacert)


@pytest.mark.nmx
@pytest.mark.security
def test_no_connection_after_restore_manager():
    """
    Verify that after disabling cluster manager (restore) – client cannot connect at all

    1.	update certs & encryption mode
    2.	disable cluster manager     # TODO: can disable when everything is loaded? What happens then?
    3.	verify client cannot connect at all
    """
    manager = Cluster().manager
    nmx_c_cert = client_cert = nmx_c_cacert = client_cacert = TestCert.cert_valid_1

    with allure.step('update certs & encryption mode'):
        manager.certificate.action_update(nmx_c_cert.name).verify_result()
        manager.ca_certificate.action_update(nmx_c_cacert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])).verify_result()
    with allure.step('disable cluster manager'):
        manager.action_restore().verify_result()
    with allure.step('verify client cannot connect at all'):
        verify_client_connection(TestFlowType.BAD_FLOW, {mode: False for mode in EncryptionMode.ALL_MODES},
                                 nmx_c_cert, client_cert, nmx_c_cacert, client_cacert)


@pytest.mark.nmx
@pytest.mark.security
def test_no_connection_after_restore_cluster():
    """
    Verify that after disabling cluster (restore) – client cannot connect at all

    1.	update certs & encryption mode
    2.	disable cluster     # TODO: can disable when everything is loaded? What happens then?
    3.	verify client cannot connect at all

    """
    cluster = Cluster()
    nmx_c_cert = client_cert = nmx_c_cacert = client_cacert = TestCert.cert_valid_1

    with allure.step('update certs & encryption mode'):
        cluster.manager.certificate.action_update(nmx_c_cert.name).verify_result()
        cluster.manager.ca_certificate.action_update(nmx_c_cacert.cacert_name).verify_result()
        cluster.manager.encryption.action_update(
            random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])).verify_result()
    with allure.step('disable cluster'):
        cluster.set(STATE, DISABLED).verify_result()
    with allure.step('verify client cannot connect at all'):
        verify_client_connection(TestFlowType.BAD_FLOW, {mode: False for mode in EncryptionMode.ALL_MODES},
                                 nmx_c_cert, client_cert, nmx_c_cacert, client_cacert)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('encryption_mode', [EncryptionMode.TLS, EncryptionMode.MTLS])
def test_nmx_cert_reboot_case(encryption_mode):
    """
    Verify that certificates and encryption mode are kept after reboot

    1.	load cert & cacert
    2.	Update encryption mode
    3.	Reboot
    4.	Verify updated values in show kept
    """
    manager = Cluster().manager
    cert = TestCert.cert_valid_1

    with allure.step('load cert & cacert'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Update encryption mode'):
        manager.encryption.action_update(encryption_mode)
    with allure.step('reboot the system'):
        System().action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()
    with allure.step('Verify updated values in show kept'):
        verify_manager_show(expect_cert=cert.name, expect_cacert=cert.cacert_name, expect_encryption=encryption_mode)
        verify_cert_show(expect_cert_id=cert.name)
        verify_cacert_show(expect_cert_id=cert.cacert_name)
        verify_encryption_show(expect_mode=encryption_mode)
    # TODO: should also perform communication check, or fields values enough?


@pytest.mark.usefixtures('scp_player', 'setup_import_certs')
def factory_reset_nmx_cert_check(scp_player, setup_import_certs):
    """
    Verify that certificates and encryption mode cleared to default after factory reset

    1.	Import and load cert & cacert
    2.	Update encryption mode
    3.	Factory reset
    4.	Verify values in show restored to defaults
    """
    cert = TestCert.cert_valid_1
    manager = Cluster().manager
    encryption_mode = random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])

    with allure.step('Import and load cert & cacert'):
        # import_certificates(scp_player, engines.dut, [cert])  # TODO: check if usefixtures work
        # import_certificates(scp_player, engines.dut, [cert], True)
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Update encryption mode'):
        manager.encryption.action_update(encryption_mode).verify_result()

    yield  # factory reset

    with allure.step('Verify values in show restored to defaults '):
        verify_manager_show(expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                            expect_encryption=Defaults.ENCRYPTION)
        verify_cert_show(expect_cert_id=Defaults.CERT)
        verify_cacert_show(expect_cert_id=Defaults.CACERT)
        verify_encryption_show(expect_mode=Defaults.ENCRYPTION)

    yield  # to prevent StopIteration on the 2nd next() call


factory_reset_nmx_cert_checker = factory_reset_nmx_cert_check(None, None)  # generator
