import random
import string

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType, TestFlowType
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.nmx_cert.conftest import clear_manager_config, import_test_certs
from ngts.tests_nvos.general.security.nmx_cert.constants import Defaults, EncryptionMode, ENABLED, DISABLED, \
    UserCfgJsonFields, FILE_SHOULD_NOT_EXIST, NA, STATE, UserCfgJsonValues
from ngts.tests_nvos.general.security.nmx_cert.helpers import verify_manager_show, verify_cert_show, verify_cacert_show, \
    verify_encryption_show, verify_client_connection, verify_static_checks
from ngts.tests_nvos.system.gnmi.conftest import scp_player, get_scp_player


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
    # TODO: https://redmine.mellanox.com/issues/3993304
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    cert = TestCert.cert_valid_1
    with allure.step('Verify outputs contain the required fields'):
        with allure.independent_step('verify manager show'):
            verify_manager_show()
        with allure.independent_step('verify cert show'):
            verify_cert_show()
        with allure.independent_step('verify cacert show'):
            verify_cacert_show()
        with allure.independent_step('verify encryption show'):
            verify_encryption_show()
    with allure.step('check values after update ca/certificate'):
        with allure.step('Run update ca/certificate'):
            cluster.manager.certificate.action_update(cert.name).verify_result()
            cluster.manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        with allure.independent_step('Verify in show that the related fields change accordingly'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(expect_cert=cert.name, expect_cacert=cert.cacert_name)
            with allure.independent_step('verify cert show'):
                verify_cert_show(expect_cert_id=cert.name)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(expect_cert_id=cert.cacert_name)
        with allure.independent_step('verify files and fields in json'):
            verify_static_checks({UserCfgJsonFields.CERTIFICATE: UserCfgJsonValues.CERTIFICATE,
                                  UserCfgJsonFields.PRIVATE_KEY: UserCfgJsonValues.PRIVATE_KEY,
                                  UserCfgJsonFields.CA_CERTIFICATE: UserCfgJsonValues.CA_CERTIFICATE}, cert.name, cert.cacert_name)
    with allure.step('check values after update encryption'):
        for mode in EncryptionMode.ALL_MODES:
            with allure.step(f'Run update encryption: {mode}'):
                cluster.manager.encryption.action_update(mode).verify_result()
            with allure.independent_step('Verify in show that related field updates accordingly'):
                with allure.independent_step('verify manager show'):
                    verify_manager_show(expect_encryption=mode)
                with allure.independent_step('verify encryption show'):
                    verify_encryption_show(expect_mode=mode)
            with allure.independent_step('verify fields in json'):
                verify_static_checks({UserCfgJsonFields.ENCRYPTION: mode})
    with allure.step('check values after restore encryption'):
        with allure.step('Run restore encryption'):
            cluster.manager.encryption.action_restore().verify_result()
        with allure.independent_step('Verify in show that related fields restored to default'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(expect_encryption=Defaults.ENCRYPTION)
            with allure.independent_step('verify encryption show'):
                verify_encryption_show(expect_mode=Defaults.ENCRYPTION)
        with allure.independent_step(
                'verify fields in json'):  # TODO: uncomment after bug close: https://redmine.mellanox.com/issues/3993304
            verify_static_checks({UserCfgJsonFields.ENCRYPTION: None})
    with allure.step('check values after restore ca/certificate'):
        with allure.step('Run restore ca/certificate'):
            cluster.manager.certificate.action_restore().verify_result()
            cluster.manager.ca_certificate.action_restore().verify_result()
        with allure.independent_step('Verify in show that related fields restored to default'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT)
            with allure.independent_step('verify cert show'):
                verify_cert_show(expect_cert_id=Defaults.CERT)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(expect_cert_id=Defaults.CACERT)
        with allure.independent_step('verify files and fields in json deleted'):
            verify_static_checks({UserCfgJsonFields.CERTIFICATE: None,
                                  # TODO: uncomment after bug close: https://redmine.mellanox.com/issues/3993304
                                  UserCfgJsonFields.PRIVATE_KEY: None, UserCfgJsonFields.CA_CERTIFICATE: None}, FILE_SHOULD_NOT_EXIST,
                                 FILE_SHOULD_NOT_EXIST)
    with allure.step('check values after update manager'):
        with allure.step('Run update manager (enable manager communication)'):
            cluster.manager.action_update().verify_result()
        with allure.independent_step('Verify in manager show that related fields'):
            verify_manager_show(expect_state=ENABLED)
        with allure.independent_step('verify fields in json'):
            verify_static_checks({UserCfgJsonFields.STATE: ENABLED})
    with allure.step('check values after restore manager'):
        with allure.step('Run restore manager (disable manager communication)'):
            cluster.manager.action_restore().verify_result()
        with allure.independent_step('Verify in manager show that related fields restored to default'):
            verify_manager_show(expect_state=DISABLED)
        with allure.independent_step('verify fields in json'):
            verify_static_checks({UserCfgJsonFields.STATE: DISABLED})
    with allure.step('check values after disable cluster'):
        with allure.step('disable cluster'):
            cluster.set(STATE, DISABLED, apply=True).verify_result()
        with allure.independent_step('Verify outputs contain the required fields'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(NA, NA, NA, NA)
            with allure.independent_step('verify cert show'):
                verify_cert_show(NA)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(NA)
            with allure.independent_step('verify encryption show'):
                verify_encryption_show(NA)
        with allure.independent_step('verify files and fields in json deleted'):
            verify_static_checks({UserCfgJsonFields.CERTIFICATE: None,
                                  # TODO: uncomment after bug close: https://redmine.mellanox.com/issues/3993304
                                  UserCfgJsonFields.PRIVATE_KEY: None, UserCfgJsonFields.CA_CERTIFICATE: None,
                                  UserCfgJsonFields.ENCRYPTION: None, UserCfgJsonFields.STATE: DISABLED}, FILE_SHOULD_NOT_EXIST,
                                 FILE_SHOULD_NOT_EXIST)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_manager_cmd_fail_when_cluster_off(test_api):
    """
    Verify that:
        1. update/restore manager commands fail when cluster disabled
        2. show commands show empty output (- should be rejected but that's current implementation)

    1.	Make sure cluster disabled
    2.	Run manager update/restore command
    3.	Verify failed and show doesn’t change
    """
    # TODO: https://redmine.mellanox.com/issues/3993892
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    cert = TestCert.cert_valid_1
    with allure.step('Make sure cluster disabled'):
        cluster.set(STATE, DISABLED, apply=True).verify_result()
    with allure.step('verify show outputs NAs'):
        with allure.independent_step('verify manager show'):
            verify_manager_show(NA, NA, NA, NA)
        with allure.independent_step('verify cert show'):
            verify_cert_show(NA)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(NA)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(NA)
    with allure.step('check manager update/restore commands fail'):
        with allure.independent_step('update commands'):
            with allure.independent_step('verify update manager fail'):
                cluster.manager.action_update().verify_result(False)
            with allure.independent_step('verify update certificate fail'):
                cluster.manager.certificate.action_update(cert.name).verify_result(False)
            with allure.independent_step('verify update ca_certificate fail'):
                cluster.manager.ca_certificate.action_update(cert.cacert_name).verify_result(False)
            with allure.independent_step('verify update encryption fail'):
                cluster.manager.encryption.action_update().verify_result(False)
        with allure.step('restore commands'):
            with allure.independent_step('verify restore manager fail'):
                cluster.manager.action_restore().verify_result(False)
            with allure.independent_step('verify restore certificate fail'):
                cluster.manager.certificate.action_restore().verify_result(False)
            with allure.independent_step('verify restore ca_certificate fail'):
                cluster.manager.ca_certificate.action_restore().verify_result(False)
            with allure.independent_step('verify restore encryption fail'):
                cluster.manager.encryption.action_restore().verify_result(False)
    with allure.step('Verify show doesn’t change - outputs NAs'):
        with allure.independent_step('verify manager show'):
            verify_manager_show(NA, NA, NA, NA)
        with allure.independent_step('verify cert show'):
            verify_cert_show(NA)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(NA)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(NA)
    with allure.step('enable cluster and verify all fields were not changed and still default'):
        with allure.step('enable cluster'):
            cluster.set(STATE, ENABLED, apply=True).verify_result()
        with allure.independent_step('verify manager show'):
            verify_manager_show(expect_state=Defaults.STATE, expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                expect_encryption=Defaults.ENCRYPTION)
        with allure.independent_step('verify cert show'):
            verify_cert_show(expect_cert_id=Defaults.CERT)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(expect_cert_id=Defaults.CACERT)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_delete_cert_fail_when_is_used(test_api, scp_player, engines, import_certs_back_after_test):
    """
    Verify that we cannot delete certs when are used (updated) for cluster manager config

    0.  import ca/certs
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
        cluster.manager.show()
    with allure.step('try delete bound ca/cert and verify fail'):
        with allure.independent_step('Try to delete certs - expect fail'):
            security = System().security
            with allure.independent_step('try delete cert - expect fail'):
                security.certificate.cert_id[cert.name].action_delete().verify_result(False)
            with allure.independent_step('try delete cert - expect fail'):
                security.ca_certificate.cert_id[cert.cacert_name].action_delete().verify_result(False)
        with allure.independent_step('Verify that there’s no change in related fields'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(expect_cert=cert.name, expect_cacert=cert.cacert_name)
            with allure.independent_step('verify cert show'):
                verify_cert_show(expect_cert_id=cert.name)
            with allure.independent_step('verify cacert show'):
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
    with allure.step('Run update to cert-id that was not imported - expect fail'):
        with allure.independent_step('run update commands - expect fail'):
            with allure.independent_step('update cert - expect fail'):
                manager.certificate.action_update(rand_str).verify_result(False)
            with allure.independent_step('update cacert - expect fail'):
                manager.ca_certificate.action_update(rand_str).verify_result(False)
            with allure.independent_step('update encryption - expect fail'):
                manager.encryption.action_update(rand_str).verify_result(False)
        with allure.step("Verify in show that related fields don’t change"):
            with allure.independent_step('verify manager show'):
                verify_manager_show(expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                    expect_encryption=Defaults.ENCRYPTION)
            with allure.independent_step('verify cert show'):
                verify_cert_show(expect_cert_id=Defaults.CERT)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(expect_cert_id=Defaults.CACERT)
            with allure.independent_step('verify encryption show'):
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
        verify_cacert_show(expect_cert_id=cert.cacert_name)


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
    pytest.skip('currently skipping until getting image with NMX-C server')

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
    pytest.skip('currently skipping until getting image with NMX-C server')

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
                                 {mode: mode == EncryptionMode.DISABLED for mode in EncryptionMode.ALL_MODES},
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
    pytest.skip('currently skipping until getting image with NMX-C server')

    manager = Cluster().manager
    nmx_c_cert = client_cert = nmx_c_cacert = client_cacert = TestCert.cert_valid_1

    with allure.step('update certs & encryption mode'):
        manager.certificate.action_update(nmx_c_cert.name).verify_result()
        manager.ca_certificate.action_update(nmx_c_cacert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])).verify_result()
    with allure.step('disable cluster manager'):
        manager.action_restore().verify_result()
    with allure.step('verify client cannot connect at all'):
        verify_client_connection(TestFlowType.BAD_FLOW, {mode: False for mode in EncryptionMode.ALL_MODES}, nmx_c_cert,
                                 client_cert, nmx_c_cacert, client_cacert)


@pytest.mark.nmx
@pytest.mark.security
def test_no_connection_after_restore_cluster():
    """
    Verify that after disabling cluster (restore) – client cannot connect at all

    1.	update certs & encryption mode
    2.	disable cluster     # TODO: can disable when everything is loaded? What happens then?
    3.	verify client cannot connect at all
    """
    pytest.skip('currently skipping until getting image with NMX-C server')

    cluster = Cluster()
    nmx_c_cert = client_cert = nmx_c_cacert = client_cacert = TestCert.cert_valid_1

    with allure.step('update certs & encryption mode'):
        cluster.manager.certificate.action_update(nmx_c_cert.name).verify_result()
        cluster.manager.ca_certificate.action_update(nmx_c_cacert.cacert_name).verify_result()
        cluster.manager.encryption.action_update(
            random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])).verify_result()
    with allure.step('disable cluster'):
        cluster.set(STATE, DISABLED, apply=True).verify_result()
    with allure.step('verify client cannot connect at all'):
        verify_client_connection(TestFlowType.BAD_FLOW, {mode: False for mode in EncryptionMode.ALL_MODES}, nmx_c_cert,
                                 client_cert, nmx_c_cacert, client_cacert)


@pytest.mark.system
@pytest.mark.gnmi
def test_nmx_cert_reboot_case(engines):
    """
    Verify that certificates and encryption mode are kept after reboot

    1.	load cert & cacert
    2.	Update encryption mode
    3.	Reboot
    4.	Verify updated values in show kept
    """
    cluster = Cluster()
    manager = cluster.manager
    cert = TestCert.cert_valid_1
    encryption_mode = random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])
    with allure.step('load cert & cacert'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Update encryption mode'):
        manager.encryption.action_update(encryption_mode)
    with allure.step('reboot the system'):
        System().action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()
        engines.dut.disconnect()
    with allure.step('re-enable cluster after reboot'):
        cluster.set(STATE, ENABLED, apply=True).verify_result()
    with allure.step('Verify updated values in show kept'):
        verify_manager_show(expect_cert=cert.name, expect_cacert=cert.cacert_name, expect_encryption=encryption_mode)
        verify_cert_show(expect_cert_id=cert.name)
        verify_cacert_show(expect_cert_id=cert.cacert_name)
        verify_encryption_show(
            expect_mode=encryption_mode)  # TODO: should also perform communication check, or fields values enough?


def factory_reset_nmx_cert_check():
    """
    Verify that certificates and encryption mode cleared to default after factory reset

    1.	Import and load cert & cacert
    2.	Update encryption mode
    3.	Factory reset
    4.	Verify values in show restored to defaults
    """
    dut_device: BaseDevice = TestToolkit.devices.dut
    should_check_nmx: bool = dut_device.has_nmx

    if should_check_nmx:
        scp_player = get_scp_player(TestToolkit.engines)
        cert = TestCert.cert_valid_1
        manager = Cluster().manager
        clear_manager_config()
        encryption_mode = random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])
        with allure.step('Import and load cert & cacert'):
            import_test_certs(scp_player, TestToolkit.engines.dut, [cert])
            manager.certificate.action_update(cert.name).verify_result()
            manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        with allure.step('Update encryption mode'):
            manager.encryption.action_update(encryption_mode).verify_result()
    else:
        with allure.step('Not checking NMX on this dut device'):
            pass

    yield  # factory reset

    if should_check_nmx:
        with allure.step('Verify values in show restored to defaults '):
            verify_manager_show(expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                expect_encryption=Defaults.ENCRYPTION)
            verify_cert_show(expect_cert_id=Defaults.CERT)
            verify_cacert_show(expect_cert_id=Defaults.CACERT)
            verify_encryption_show(expect_mode=Defaults.ENCRYPTION)
    else:
        with allure.step('Not checking NMX on this dut device'):
            pass

    yield  # to prevent StopIteration on the 2nd next() call


factory_reset_nmx_cert_checker = factory_reset_nmx_cert_check()  # generator
