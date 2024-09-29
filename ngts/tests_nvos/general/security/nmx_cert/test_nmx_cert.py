import random
import string
import time
from typing import List

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, TestFlowType
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Manager import Manager
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs
from ngts.tests_nvos.general.security.nmx_cert.conftest import clear_manager_config
from ngts.tests_nvos.general.security.nmx_cert.constants import Defaults, EncryptionMode, ENABLED, DISABLED, \
    UserCfgJsonFields, FILE_SHOULD_NOT_EXIST, NA, STATE, UserCfgJsonValues
from ngts.tests_nvos.general.security.nmx_cert.helpers import verify_manager_show, verify_cert_show, verify_cacert_show, \
    verify_encryption_show, verify_static_checks, run_manager_client_hello_request
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
            verify_static_checks({UserCfgJsonFields.CERTIFICATE: UserCfgJsonValues.CERTIFICATE.format(filename=cert.name),
                                  UserCfgJsonFields.PRIVATE_KEY: UserCfgJsonValues.PRIVATE_KEY.format(filename=cert.name),
                                  UserCfgJsonFields.CA_CERTIFICATE: UserCfgJsonValues.CA_CERTIFICATE.format(filename=cert.cacert_name)}, cert.name, cert.cacert_name)
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
                'verify fields in json'):
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
                                  UserCfgJsonFields.PRIVATE_KEY: None, UserCfgJsonFields.CA_CERTIFICATE: None}, FILE_SHOULD_NOT_EXIST,
                                 FILE_SHOULD_NOT_EXIST)
    with allure.step('check values after update manager'):
        for state in [ENABLED, DISABLED]:
            with allure.step(f'Run update manager: state {state}'):
                cluster.manager.action_update(state).verify_result()
            with allure.independent_step('Verify in manager show that related fields'):
                verify_manager_show(expect_state=state)
            with allure.independent_step('verify fields in json'):
                verify_static_checks({UserCfgJsonFields.STATE: state})
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
            for state in [ENABLED, DISABLED]:
                with allure.independent_step(f'verify update manager fail: state {state}'):
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
def test_cluster_manager_connection():
    """
    Verify that client can communicate with nmx-c
        * run with all possible encryption modes

    1.	Import and load cert & cacert
    2.	Update encryption mode
    3.	Run client request to nmx-c using matching cert & cacert of client side (– check encryption works?)
    4.	Expect success
    """
    cert1, cert2, cert3 = TestCert.cert_valid_1, TestCert.cert_valid_2, TestCert.cert_valid_3
    disabled, tls, mtls = EncryptionMode.DISABLED, EncryptionMode.TLS, EncryptionMode.MTLS

    class Test:
        cur_server_cert = None
        cur_server_ca = None
        cur_server_mode = None

        def __init__(self, name: str, server_cert: CertInfo, server_ca: CertInfo, server_mode: str, client_cert: CertInfo, client_ca: CertInfo, client_mode: str, expect_success: bool, skip_setup: bool = False):
            self.name = name
            self.server_cert = server_cert
            self.server_ca = server_ca
            self.server_mode = server_mode
            self.client_cert = client_cert
            self.client_ca = client_ca
            self.client_mode = client_mode
            self.expect_success = expect_success
            self.skip_setup = skip_setup

        def get_name(self) -> str:
            return f'[{TestFlowType.GOOD_FLOW if self.expect_success else TestFlowType.BAD_FLOW}] {self.name}'

        def setup(self, mngr: Manager, enable_mngr: bool = False):
            if self.skip_setup:
                return
            if enable_mngr:
                with allure.step('enable manager'):
                    mngr.action_update(ENABLED).verify_result()
            if self.server_cert.name != Test.cur_server_cert:
                with allure.step(f'update server cert: {self.server_cert.name}'):
                    mngr.certificate.action_update(self.server_cert.name).verify_result()
                    Test.cur_server_cert = self.server_cert.name
            if self.server_ca.cacert_name != Test.cur_server_ca:
                with allure.step(f'update server CA: {self.server_ca.cacert_name}'):
                    mngr.ca_certificate.action_update(self.server_ca.cacert_name).verify_result()
                    Test.cur_server_ca = self.server_ca.cacert_name
            if self.server_mode != Test.cur_server_mode:
                with allure.step(f'update server encryption: {self.server_mode}'):
                    mngr.encryption.action_update(self.server_mode).verify_result()
                    Test.cur_server_mode = self.server_mode

        def run_client_and_verify(self):
            run_manager_client_hello_request(self.client_mode, self.server_cert, self.server_ca, self.client_cert,
                                             self.client_ca).verify_result(self.expect_success)

    cases: List[Test] = [
        # basic - mode mismatch
        Test('server disabled client disabled', cert1, cert2, disabled, cert2, cert1, disabled, True, True),
        Test('server disabled client tls', cert1, cert2, disabled, cert2, cert1, tls, False),
        Test('server disabled client mtls', cert1, cert2, disabled, cert2, cert1, mtls, False),
        Test('server tls client disabled', cert1, cert2, tls, cert2, cert1, disabled, False),
        Test('server tls client tls', cert1, cert2, tls, cert2, cert1, tls, True),
        Test('server tls client mtls', cert1, cert2, tls, cert2, cert1, mtls, True),
        Test('server mtls client disabled', cert1, cert2, mtls, cert2, cert1, disabled, False),
        Test('server mtls client tls', cert1, cert2, mtls, cert2, cert1, tls, False),
        Test('server mtls client mtls', cert1, cert2, mtls, cert2, cert1, mtls, True),
        # for the basic good flows - test with ca/cert mismatch
        Test('server disabled client disabled - mismatch1', cert1, cert2, disabled, cert2, cert3, disabled, True),
        Test('server disabled client disabled - mismatch2', cert1, cert2, disabled, cert3, cert1, disabled, True),
        Test('server disabled client disabled - mismatch3', cert1, cert2, disabled, cert3, cert3, disabled, True),
        Test('server tls client tls - mismatch1', cert1, cert2, tls, cert2, cert3, tls, False),
        Test('server tls client tls - mismatch2', cert1, cert2, tls, cert3, cert1, tls, True),
        Test('server tls client tls - mismatch3', cert1, cert2, tls, cert3, cert3, tls, False),
        Test('server tls client mtls - mismatch1', cert1, cert2, tls, cert2, cert3, mtls, False),
        Test('server tls client mtls - mismatch2', cert1, cert2, tls, cert3, cert1, mtls, True),
        Test('server tls client mtls - mismatch3', cert1, cert2, tls, cert3, cert3, mtls, False),
        Test('server mtls client mtls - mismatch1', cert1, cert2, mtls, cert2, cert3, mtls, False),
        Test('server mtls client mtls - mismatch2', cert1, cert2, mtls, cert3, cert1, mtls, False),
        Test('server mtls client mtls - mismatch3', cert1, cert2, mtls, cert3, cert3, mtls, False),
    ]

    with allure.step('enable cluster'):
        cluster = Cluster()
        cluster.set(STATE, ENABLED, apply=True).verify_result()
    with allure.step('enable cluster manager'):
        cluster.manager.action_update(ENABLED).verify_result()
        time.sleep(2)

    with allure.step('run all cases'):
        for case in cases:
            with allure.independent_step(case.get_name()):
                with allure.step('set up'):
                    case.setup(cluster.manager)
                with allure.step(f'verify connection: {case.expect_success}'):
                    case.run_client_and_verify()


@pytest.mark.nmx
@pytest.mark.security
def test_connection_after_restore_encryption():
    """
    Verify that after encryption mode – client can connect only in None mode

    1.	update cert & cacert & m/tls
    2.	restore encryption
    3.	verify client can connect only with NONE
    """

    cert = TestCert.cert_valid_1

    with allure.step('enable cluster'):
        cluster = Cluster()
        cluster.set(STATE, ENABLED, apply=True).verify_result()
    with allure.step('enable cluster manager'):
        manager = cluster.manager
        cluster.manager.action_update(ENABLED).verify_result()
    with allure.step('update encryption'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])).verify_result()
    with allure.step('restore encryption'):
        manager.encryption.action_restore().verify_result()
    with allure.step('verify only non secured client request works'):
        cases = {
            EncryptionMode.DISABLED: True,
            EncryptionMode.TLS: False,
            EncryptionMode.MTLS: False,
        }
        time.sleep(2)
        for client_mode, expect_success in cases.items():
            with allure.independent_step(f'verify client connection: client mode: {client_mode}. expect success: {expect_success}'):
                run_manager_client_hello_request(client_mode, cert, cert, cert, cert).verify_result(expect_success)


def verify_no_client_connection(server_cert: CertInfo, server_ca: CertInfo):
    for client_mode in EncryptionMode.ALL_MODES:
        with allure.independent_step(f'verify client connection: client mode: {client_mode}. expect success: False'):
            run_manager_client_hello_request(client_mode, server_cert, server_ca, server_ca, server_cert).verify_result(False)


@pytest.mark.nmx
@pytest.mark.security
def test_no_connection_when_manager_state_disabled():
    """
    Verify that when cluster manager state disabled (restore/update disabled) – client cannot connect at all

    1.	update certs & encryption mode
    2.	disable cluster manager
    3.	verify client cannot connect at all
    """
    cert = TestCert.cert_valid_1

    with allure.step('enable cluster'):
        cluster = Cluster()
        cluster.set(STATE, ENABLED, apply=True).verify_result()

    with allure.step('enable cluster manager'):
        manager = cluster.manager
        manager.action_update(ENABLED).verify_result()

    with allure.step('update encryption'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice(EncryptionMode.ALL_MODES)).verify_result()

    with allure.step('disable manager (update to disabled)'):
        manager.action_update(DISABLED).verify_result()
        time.sleep(2)

    with allure.step('verify cluster manager client cannot connect'):
        verify_no_client_connection(cert, cert)

    with allure.step('enable cluster manager'):
        cluster.manager.action_update(ENABLED).verify_result()

    with allure.step('disable manager (restore)'):
        manager.action_restore().verify_result()
        time.sleep(2)

    with allure.step('verify cluster manager client cannot connect'):
        verify_no_client_connection(cert, cert)


@pytest.mark.nmx
@pytest.mark.security
def test_no_connection_after_disable_cluster():
    """
    Verify that after disabling cluster (restore) – client cannot connect at all

    1.	update certs & encryption mode
    2.	disable cluster
    3.	verify client cannot connect at all
    """
    cert = TestCert.cert_valid_1

    with allure.step('enable cluster'):
        cluster = Cluster()
        cluster.set(STATE, ENABLED, apply=True).verify_result()

    with allure.step('enable cluster manager'):
        manager = cluster.manager
        manager.action_update(ENABLED).verify_result()

    with allure.step('update encryption'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice(EncryptionMode.ALL_MODES)).verify_result()

    with allure.step('disable cluster'):
        cluster.set(STATE, DISABLED, apply=True).verify_result()

    with allure.step('verify cluster manager client cannot connect'):
        verify_no_client_connection(cert, cert)


@pytest.mark.nmx
@pytest.mark.security
def test_nmx_cert_reboot_case(engines):
    """
    Verify that certificates and encryption mode are kept after reboot

    1.	load cert & cacert
    2.	Update encryption mode
    3.	Reboot
    4.	Verify updated values in show kept
    5.  verify connection works with the configured mode
    """
    cluster = Cluster()
    manager = cluster.manager
    cert = TestCert.cert_valid_1
    encryption_mode = random.choice(EncryptionMode.ALL_MODES)

    with allure.step('enable cluster'):
        cluster.set(STATE, ENABLED, apply=True).verify_result()

    with allure.step('enable cluster manager'):
        manager.action_update(ENABLED).verify_result()

    with allure.step('load cert & cacert'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Update encryption mode'):
        manager.encryption.action_update(encryption_mode)

    with allure.step('save config'):
        NvueGeneralCli.save_config(engines.dut)

    with allure.step('reboot the system'):
        System().action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()
        engines.dut.disconnect()

    with allure.step('Verify updated values in show kept'):
        with allure.independent_step('verify manager show'):
            verify_manager_show(expect_cert=cert.name, expect_cacert=cert.cacert_name, expect_encryption=encryption_mode)
        with allure.independent_step('verify cert show'):
            verify_cert_show(expect_cert_id=cert.name)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(expect_cert_id=cert.cacert_name)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(expect_mode=encryption_mode)
        with allure.independent_step(f'verify connection. mode: {encryption_mode}'):
            run_manager_client_hello_request(encryption_mode, cert, cert, cert, cert).verify_result(True)


def nmx_cert_factory_reset_no_params_check():
    """
    Verify that certificates and encryption mode cleared to default after factory reset

    1.	Import and load cert & cacert
    2.	Update encryption mode
    3.	Factory reset
    4.	Verify values in show restored to defaults
    """
    dut_device: BaseDevice = TestToolkit.devices.dut
    should_check_nmx: bool = dut_device.has_nmx
    scp_player = get_scp_player(TestToolkit.engines)
    cert = TestCert.cert_valid_1
    manager = Cluster().manager
    clear_manager_config()
    encryption_mode = random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])

    if should_check_nmx:
        with allure.step('enable cluster and clear manager config'):
            clear_manager_config()
        with allure.step('Import and load cert & cacert'):
            import_test_certs(scp_player, TestToolkit.engines.dut, [cert])
            manager.certificate.action_update(cert.name).verify_result()
            manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        with allure.step('Update encryption mode'):
            manager.encryption.action_update(encryption_mode).verify_result()

    yield  # do factory reset

    if should_check_nmx:
        with allure.step('Verify values in show restored to defaults'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                    expect_encryption=Defaults.ENCRYPTION)
            with allure.independent_step('verify cert show'):
                verify_cert_show(expect_cert_id=Defaults.CERT)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(expect_cert_id=Defaults.CACERT)
            with allure.independent_step('verify encryption show'):
                verify_encryption_show(expect_mode=Defaults.ENCRYPTION)

    yield  # to prevent StopIteration on the 2nd next() call


factory_reset_nmx_cert_checker = nmx_cert_factory_reset_no_params_check()  # generator
