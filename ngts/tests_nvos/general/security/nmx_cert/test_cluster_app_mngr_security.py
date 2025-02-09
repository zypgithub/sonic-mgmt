import random
import string
import time
from typing import List, Dict

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, TestFlowType, ClusterApps
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Manager import Manager
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.conftest import get_dut_hostname
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs
from ngts.tests_nvos.general.security.helpers import optional_cacert_types, setup_certs_for_tests, \
    cleanup_certs_for_tests
from ngts.tests_nvos.general.security.nmx_cert.conftest import clear_manager_config
from ngts.tests_nvos.general.security.nmx_cert.constants import Defaults, EncryptionMode, ENABLED, DISABLED, STATE, \
    APP_CONSTS
from ngts.tests_nvos.general.security.nmx_cert.helpers import verify_manager_show, verify_cert_show, verify_cacert_show, \
    verify_encryption_show, run_manager_hello_request, verify_files, enable_cluster, disable_cluster, \
    enable_cluster_app_manager_state, disable_cluster_app_manager_state, update_cluster_app_manager_state, \
    restore_cluster_app_manager_state
from ngts.tests_nvos.system.gnmi.conftest import scp_player, get_scp_player


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api, app_name, ca_type',
                         [(api, app, random.choice(optional_cacert_types())) for api in ApiType.ALL_TYPES for app in
                          ClusterApps.ALL_APPS])
def test_cluster_app_mngr_security_cli(test_api, app_name, engines, ca_type):
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
    app = cluster.apps.app_name[app_name]
    cert = TestCert.cert_valid_1

    consts = APP_CONSTS[app_name]

    with allure.step('Verify outputs contain the required fields'):
        with allure.independent_step('verify manager show'):
            verify_manager_show(app_name)
        with allure.independent_step('verify cert show'):
            verify_cert_show(app_name)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(app_name)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(app_name)
    with allure.step('check values after update ca/certificate'):
        with allure.step('Run update ca/certificate'):
            app.manager.certificate.action_update(cert.name).verify_result()
            app.manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        with allure.independent_step('Verify in show that the related fields change accordingly'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(app_name, expect_cert=cert.name, expect_cacert=cert.cacert_name)
            with allure.independent_step('verify cert show'):
                verify_cert_show(app_name, expect_cert_id=cert.name)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(app_name, expect_cert_id=cert.cacert_name)
        with allure.independent_step('verify files and fields in json'):
            verify_files(app_name, engines.dut, {
                consts.user_config_json_fields.certificate: consts.cert_public_key_path.format(cert.name),
                consts.user_config_json_fields.private_key: consts.cert_private_key_path.format(cert.name),
                consts.user_config_json_fields.ca_certificate: consts.cacert_path.format(cert.cacert_name),
            }, cert.name, cert.cacert_name)
    with allure.step('check values after update encryption'):
        for mode in EncryptionMode.ALL_MODES:
            with allure.step(f'Run update encryption: {mode}'):
                app.manager.encryption.action_update(mode).verify_result()
            with allure.independent_step('Verify in show that related field updates accordingly'):
                with allure.independent_step('verify manager show'):
                    verify_manager_show(app_name, expect_encryption=mode)
                with allure.independent_step('verify encryption show'):
                    verify_encryption_show(app_name, expect_mode=mode)
            with allure.independent_step('verify files and fields in json'):
                verify_files(app_name, engines.dut, {
                    consts.user_config_json_fields.certificate: consts.cert_public_key_path.format(cert.name),
                    consts.user_config_json_fields.private_key: consts.cert_private_key_path.format(cert.name),
                    consts.user_config_json_fields.ca_certificate: consts.cacert_path.format(cert.cacert_name),
                    consts.user_config_json_fields.encryption: mode,
                }, cert.name, cert.cacert_name)
    with allure.step('check values after restore encryption'):
        with allure.step('Run restore encryption'):
            app.manager.encryption.action_restore().verify_result()
        with allure.independent_step('Verify in show that related fields restored to default'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(app_name, expect_encryption=Defaults.ENCRYPTION)
            with allure.independent_step('verify encryption show'):
                verify_encryption_show(app_name, expect_mode=Defaults.ENCRYPTION)
        with allure.independent_step('verify files and fields in json'):
            verify_files(app_name, engines.dut, {
                consts.user_config_json_fields.certificate: consts.cert_public_key_path.format(cert.name),
                consts.user_config_json_fields.private_key: consts.cert_private_key_path.format(cert.name),
                consts.user_config_json_fields.ca_certificate: consts.cacert_path.format(cert.cacert_name),
            }, cert.name, cert.cacert_name)
    with allure.step('check values after restore ca/certificate'):
        with allure.step('Run restore ca/certificate'):
            app.manager.certificate.action_restore().verify_result()
            app.manager.ca_certificate.action_restore().verify_result()
        with allure.independent_step('Verify in show that related fields restored to default'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(app_name, expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT)
            with allure.independent_step('verify cert show'):
                verify_cert_show(app_name, expect_cert_id=Defaults.CERT)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(app_name, expect_cert_id=Defaults.CACERT)
        with allure.independent_step('verify files and fields in json'):
            verify_files(app_name, engines.dut)
    with allure.step('check values after update manager'):
        for state in [ENABLED, DISABLED]:
            with allure.step(f'Run update manager: state {state}'):
                update_cluster_app_manager_state(app.manager, state)
            with allure.independent_step('Verify in manager show that related fields'):
                verify_manager_show(app_name, expect_state=state)
            with allure.independent_step('verify files and fields in json'):
                verify_files(app_name, engines.dut, {consts.user_config_json_fields.state: state})
    with allure.step('check values after restore manager'):
        with allure.step('Run restore manager (disable manager communication)'):
            restore_cluster_app_manager_state(app.manager)
        with allure.independent_step('Verify in manager show that related fields restored to default'):
            verify_manager_show(app_name, expect_state=DISABLED)
            with allure.independent_step('verify files and fields in json'):
                verify_files(app_name, engines.dut, {consts.user_config_json_fields.state: DISABLED})
    with allure.step('check values after disable cluster'):
        with allure.step('disable cluster'):
            disable_cluster()
        with allure.independent_step('Verify outputs contain the required fields'):
            with allure.independent_step('verify manager show - expect item does not exist'):
                verify_manager_show(app_name, expect_item_not_exist=True)
            with allure.independent_step('verify cert show - expect item does not exist'):
                verify_cert_show(app_name, expect_item_not_exist=True)
            with allure.independent_step('verify cacert show - expect item does not exist'):
                verify_cacert_show(app_name, expect_item_not_exist=True)
            with allure.independent_step('verify encryption show - expect item does not exist'):
                verify_encryption_show(app_name, expect_item_not_exist=True)
        with allure.independent_step('verify files and fields in json deleted'):
            verify_files(app_name, engines.dut)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api, app_name, ca_type',
                         [(api, app, random.choice(optional_cacert_types())) for api in ApiType.ALL_TYPES for app in
                          ClusterApps.ALL_APPS])
def test_cluster_app_mngr_security_cli_fail_when_cluster_off(test_api, app_name, ca_type):
    """
    Verify that:
        1. update/restore manager commands fail when cluster disabled
        2. show commands show empty output (- should be rejected but that's current implementation)

    1.	Make sure cluster disabled
    2.	Run manager update/restore command
    3.	Verify failed and show doesn’t change
    """
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    app = cluster.apps.app_name[app_name]
    cert = TestCert.cert_valid_1
    with allure.step('Make sure cluster disabled'):
        cluster.set(STATE, DISABLED, apply=True).verify_result()
    with allure.step('verify show outputs NAs'):
        with allure.independent_step('verify manager show'):
            verify_manager_show(app_name, expect_item_not_exist=True)
        with allure.independent_step('verify cert show'):
            verify_cert_show(app_name, expect_item_not_exist=True)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(app_name, expect_item_not_exist=True)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(app_name, expect_item_not_exist=True)
    with allure.step('check manager update/restore commands fail'):
        with allure.independent_step('update commands'):
            for state in [ENABLED, DISABLED]:
                with allure.independent_step(f'verify update manager fail: state {state}'):
                    app.manager.action_update().verify_result(False)
            with allure.independent_step('verify update certificate fail'):
                app.manager.certificate.action_update(cert.name).verify_result(False)
            with allure.independent_step('verify update ca_certificate fail'):
                app.manager.ca_certificate.action_update(cert.cacert_name).verify_result(False)
            with allure.independent_step('verify update encryption fail'):
                app.manager.encryption.action_update().verify_result(False)
        with allure.step('restore commands'):
            with allure.independent_step('verify restore manager fail'):
                app.manager.action_restore().verify_result(False)
            with allure.independent_step('verify restore certificate fail'):
                app.manager.certificate.action_restore().verify_result(False)
            with allure.independent_step('verify restore ca_certificate fail'):
                app.manager.ca_certificate.action_restore().verify_result(False)
            with allure.independent_step('verify restore encryption fail'):
                app.manager.encryption.action_restore().verify_result(False)
    with allure.step('Verify show doesn’t change - outputs NAs'):
        with allure.independent_step('verify manager show'):
            verify_manager_show(app_name, expect_item_not_exist=True)
        with allure.independent_step('verify cert show'):
            verify_cert_show(app_name, expect_item_not_exist=True)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(app_name, expect_item_not_exist=True)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(app_name, expect_item_not_exist=True)
    with allure.step('enable cluster and verify all fields were not changed and still default'):
        with allure.step('enable cluster'):
            enable_cluster()
        with allure.independent_step('verify manager show'):
            verify_manager_show(app_name, expect_state=Defaults.STATE, expect_cert=Defaults.CERT,
                                expect_cacert=Defaults.CACERT,
                                expect_encryption=Defaults.ENCRYPTION)
        with allure.independent_step('verify cert show'):
            verify_cert_show(app_name, expect_cert_id=Defaults.CERT)
        with allure.independent_step('verify cacert show'):
            verify_cacert_show(app_name, expect_cert_id=Defaults.CACERT)
        with allure.independent_step('verify encryption show'):
            verify_encryption_show(app_name, expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api, app_name, ca_type',
                         [(api, app, random.choice(optional_cacert_types())) for api in ApiType.ALL_TYPES for app in
                          ClusterApps.ALL_APPS])
def test_delete_cert_allowed_when_bound_to_cluster_app_mngr(test_api, app_name, scp_player, engines, ca_type):
    """
    Verify that we are allowed delete certs when are used (updated) for cluster manager config

    according to:
    https://redmine.mellanox.com/issues/4006597
    this operation is allowed even when ca/cert bound to cluster app manager

    0.  import ca/certs
    1.	Update certs
    2.	Try to remove certs
    3.	Verify success and that there’s no change in related fields
    """
    TestToolkit.tested_api = test_api
    cluster = Cluster()
    app = cluster.apps.app_name[app_name]
    cert = TestCert.cert_valid_1
    with allure.step('Update certs'):
        app.manager.certificate.action_update(cert.name).verify_result()
        app.manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        app.manager.show()
    with allure.step('try delete bound ca/cert and verify fail'):
        with allure.independent_step('Try to delete certs - expect fail'):
            security = System().security
            with allure.independent_step('try delete cert - expect success'):
                security.certificate.cert_id[cert.name].action_delete().verify_result()
            with allure.independent_step('try delete cert - expect success'):
                security.ca_certificate.cert_id[cert.cacert_name].action_delete().verify_result()
        with allure.independent_step('Verify that there’s no change in related fields'):
            with allure.independent_step('verify manager show'):
                verify_manager_show(app_name, expect_cert=cert.name, expect_cacert=cert.cacert_name)
            with allure.independent_step('verify cert show'):
                verify_cert_show(app_name, expect_cert_id=cert.name)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(app_name, expect_cert_id=cert.cacert_name)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api, app_name, ca_type',
                         [(api, app, random.choice(optional_cacert_types())) for api in ApiType.ALL_TYPES for app in
                          ClusterApps.ALL_APPS])
def test_update_cluster_app_mngr_security_bad_param(test_api, app_name, ca_type):
    """
    Verify that updating with bad param fails, and show output is not changed

    1.	Run update to cert-id that was not imported
    2.	Verify error
    3.	Verify in show that related field doesn’t change
    """
    TestToolkit.tested_api = test_api
    manager = Cluster().apps.app_name[app_name].manager
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
                verify_manager_show(app_name, expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                    expect_encryption=Defaults.ENCRYPTION)
            with allure.independent_step('verify cert show'):
                verify_cert_show(app_name, expect_cert_id=Defaults.CERT)
            with allure.independent_step('verify cacert show'):
                verify_cacert_show(app_name, expect_cert_id=Defaults.CACERT)
            with allure.independent_step('verify encryption show'):
                verify_encryption_show(app_name, expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api, app_name, ca_type',
                         [(api, app, random.choice(optional_cacert_types())) for api in ApiType.ALL_TYPES for app in
                          ClusterApps.ALL_APPS])
def test_update_cluster_app_mngr_encryption_fail_when_cert_not_bound(test_api, app_name, ca_type):
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
    manager = Cluster().apps.app_name[app_name].manager
    with allure.step('Try configure tls'):
        res = manager.encryption.action_update(EncryptionMode.TLS)
    with allure.step('Verify error and show output is not changed'):
        res.verify_result(False)
        verify_manager_show(app_name, expect_encryption=Defaults.ENCRYPTION)
        verify_encryption_show(app_name, expect_mode=Defaults.ENCRYPTION)
    with allure.step('Try configure mtls'):
        res = manager.encryption.action_update(EncryptionMode.MTLS)
    with allure.step('Verify error and show output is not changed'):
        res.verify_result(False)
        verify_manager_show(app_name, expect_encryption=Defaults.ENCRYPTION)
        verify_encryption_show(app_name, expect_mode=Defaults.ENCRYPTION)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('test_api, app_name, ca_type',
                         [(api, app, random.choice(optional_cacert_types())) for api in ApiType.ALL_TYPES for app in
                          ClusterApps.ALL_APPS])
def test_restore_cluster_app_mngr_cert_fail_when_in_encryption_mode(test_api, app_name, ca_type):
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
    manager = Cluster().apps.app_name[app_name].manager
    cert = TestCert.cert_valid_1

    with allure.step('Load certificate'):
        manager.certificate.action_update(cert.name).verify_result()
    with allure.step('Configure tls'):
        manager.encryption.action_update(EncryptionMode.TLS).verify_result()
    with allure.step('Try restore certificate'):
        res = manager.certificate.action_restore()
    with allure.step('Verify error and show is not changed'):
        res.verify_result(False)
        verify_manager_show(app_name, expect_cert=cert.name)
        verify_cert_show(app_name, expect_cert_id=cert.name)
    with allure.step('Load ca-cert'):
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
    with allure.step('Configure mtls'):
        manager.encryption.action_update(EncryptionMode.MTLS).verify_result()
    with allure.step('Try restore certificate'):
        res = manager.certificate.action_restore()
    with allure.step('Verify error and show is not changed'):
        res.verify_result(False)
        verify_manager_show(app_name, expect_cert=cert.name)
        verify_cert_show(app_name, expect_cert_id=cert.name)
    with allure.step('Try restore ca-certificate'):
        res = manager.certificate.action_restore()
    with allure.step('Verify error and show is not changed'):
        res.verify_result(False)
        verify_manager_show(app_name, expect_cacert=cert.cacert_name)
        verify_cacert_show(app_name, expect_cert_id=cert.cacert_name)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('app_name, ca_type',
                         [(app, random.choice(optional_cacert_types())) for app in ClusterApps.ALL_APPS])
def test_cluster_app_mngr_connection(app_name, ca_type):
    """
    Verify communication of app with manager

    Test in multiple ca/cert/encryption configurations
    """
    cert1, cert2, cert3 = TestCert.cert_valid_1, TestCert.cert_valid_2, TestCert.cert_valid_3
    disabled, tls, mtls = EncryptionMode.DISABLED, EncryptionMode.TLS, EncryptionMode.MTLS

    class Test:
        cur_server_cert = None
        cur_server_ca = None
        cur_server_mode = None

        def __init__(self, name: str, server_cert: CertInfo, server_ca: CertInfo, server_mode: str,
                     client_cert: CertInfo, client_ca: CertInfo, client_mode: str, expect_success: bool,
                     skip_setup: bool = False):
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
                    enable_cluster_app_manager_state(mngr)
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
            run_manager_hello_request(app_name, self.client_mode, self.server_cert, self.server_ca, self.client_cert,
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
        app = cluster.apps.app_name[app_name]
        enable_cluster()
    with allure.step('enable cluster manager'):
        enable_cluster_app_manager_state(app.manager)

    with allure.step('run all cases'):
        for case in cases:
            with allure.independent_step(case.get_name()):
                with allure.step('set up'):
                    case.setup(app.manager)
                with allure.step(f'verify connection: {case.expect_success}'):
                    case.run_client_and_verify()


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('app_name, ca_type',
                         [(app, random.choice(optional_cacert_types())) for app in ClusterApps.ALL_APPS])
def test_cluster_app_mngr_connection_after_restore_encryption(app_name, ca_type):
    """
    Verify that after encryption mode – manager can connect only insecurely

    1.	update cert & cacert & m/tls
    2.	restore encryption
    3.	verify client can connect only with NONE
    """

    cert = TestCert.cert_valid_1

    with allure.step('enable cluster'):
        enable_cluster()
    with allure.step('enable cluster manager'):
        manager = Cluster().apps.app_name[app_name].manager
        enable_cluster_app_manager_state(manager)
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
            with allure.independent_step(
                    f'verify client connection: client mode: {client_mode}. expect success: {expect_success}'):
                run_manager_hello_request(app_name, client_mode, cert, cert, cert, cert).verify_result(expect_success)


def verify_no_client_connection(app_name, server_cert: CertInfo, server_ca: CertInfo, skip_etc_mapping: bool = False):
    for client_mode in EncryptionMode.ALL_MODES:
        with allure.independent_step(f'verify client connection: client mode: {client_mode}. expect success: False'):
            run_manager_hello_request(app_name, client_mode, server_cert, server_ca, server_ca,
                                      server_cert, skip_etc_mapping=skip_etc_mapping).verify_result(False)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('app_name, ca_type',
                         [(app, random.choice(optional_cacert_types())) for app in ClusterApps.ALL_APPS])
def test_cluster_app_mngr_no_connection_when_state_disabled(app_name, ca_type):
    """
    Verify that when cluster manager state disabled (restore/update disabled) – client cannot connect at all

    1.	update certs & encryption mode
    2.	disable cluster manager
    3.	verify client cannot connect at all
    """
    cert = TestCert.cert_valid_1

    with allure.step('enable cluster'):
        enable_cluster()

    with allure.step('enable cluster manager'):
        manager = Cluster().apps.app_name[app_name].manager
        enable_cluster_app_manager_state(manager)

    with allure.step('update encryption'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice(EncryptionMode.ALL_MODES)).verify_result()

    with allure.step('disable manager (update to disabled)'):
        disable_cluster_app_manager_state(manager)

    with allure.step('verify cluster manager client cannot connect'):
        verify_no_client_connection(app_name, cert, cert)

    with allure.step('enable cluster manager'):
        enable_cluster_app_manager_state(manager)

    with allure.step('disable manager (restore)'):
        restore_cluster_app_manager_state(manager)

    with allure.step('verify cluster manager client cannot connect'):
        verify_no_client_connection(app_name, cert, cert)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('app_name, ca_type',
                         [(app, random.choice(optional_cacert_types())) for app in ClusterApps.ALL_APPS])
def test_cluster_app_mngr_no_connection_when_cluster_disabled(app_name, ca_type, engines):
    """
    Verify that after disabling cluster (restore) – client cannot connect at all

    1.	update certs & encryption mode
    2.	disable cluster
    3.	verify client cannot connect at all
    """
    cert = TestCert.cert_valid_1

    with allure.step('enable cluster'):
        cluster = Cluster()
        enable_cluster()

    with allure.step('enable cluster manager'):
        manager = cluster.apps.app_name[app_name].manager
        enable_cluster_app_manager_state(manager)

    with allure.step('update encryption'):
        manager.certificate.action_update(cert.name).verify_result()
        manager.ca_certificate.action_update(cert.cacert_name).verify_result()
        manager.encryption.action_update(random.choice(EncryptionMode.ALL_MODES)).verify_result()

    with allure.step('disable cluster'):
        disable_cluster()

    with allure.step('verify cluster manager client cannot connect'):
        verify_no_client_connection(app_name, cert, cert)


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('ca_type', optional_cacert_types())
def test_cluster_app_mngr_security_reboot_case(engines, ca_type):
    """
    Verify that certificates and encryption mode are kept after reboot

    1.	load cert & cacert
    2.	Update encryption mode
    3.	Reboot
    4.	Verify updated values in show kept
    5.  verify connection works with the configured mode
    """
    apps = ClusterApps.ALL_APPS

    cert: Dict[str, CertInfo] = {ClusterApps.NMX_CONTROLLER: TestCert.cert_valid_1,
                                 ClusterApps.NMX_TELEMETRY: TestCert.cert_valid_2}
    encryption_mode: Dict[str, str] = {app_name: random.choice(EncryptionMode.ALL_MODES) for app_name in apps}

    cluster = Cluster()

    with allure.step('enable cluster'):
        enable_cluster()

    for app_name in apps:
        manager = cluster.apps.app_name[app_name].manager
        with allure.step(f'enable {app_name} cluster manager'):
            enable_cluster_app_manager_state(manager)
        with allure.step(f'bind cert & cacert to {app_name}'):
            manager.certificate.action_update(cert[app_name].name).verify_result()
            manager.ca_certificate.action_update(cert[app_name].cacert_name).verify_result()
        with allure.step(f'Update {app_name} encryption mode'):
            manager.encryption.action_update(encryption_mode[app_name]).verify_result()

    with allure.step('save config'):
        NvueGeneralCli.save_config(engines.dut)

    with allure.step('reboot the system'):
        System().action_reboot('force').verify_result()
        engines.dut.disconnect()

    with allure.step('Verify updated values in show kept'):
        for app_name in apps:
            with allure.independent_step(f'app: {app_name}'):
                app_cert = cert[app_name]
                app_encryption = encryption_mode[app_name]
                with allure.independent_step('verify manager show'):
                    verify_manager_show(app_name, expect_cert=app_cert.name, expect_cacert=app_cert.cacert_name,
                                        expect_encryption=encryption_mode[app_name])
                with allure.independent_step('verify cert show'):
                    verify_cert_show(app_name, expect_cert_id=app_cert.name)
                with allure.independent_step('verify cacert show'):
                    verify_cacert_show(app_name, expect_cert_id=app_cert.cacert_name)
                with allure.independent_step('verify encryption show'):
                    verify_encryption_show(app_name, expect_mode=app_encryption)
                with allure.independent_step(f'verify connection. mode: {app_encryption}'):
                    run_manager_hello_request(app_name, app_encryption, app_cert, app_cert, app_cert,
                                              app_cert).verify_result(True)


def setup_cluster_app_mngr_security_checker(engines):
    scp_player = get_scp_player(engines)
    dut_hostname = get_dut_hostname(engines)
    cluster = Cluster()
    use_external = random.choice([False, True])
    encryption_mode = random.choice([EncryptionMode.TLS, EncryptionMode.MTLS])

    with allure.step('prepare certs'):
        tmp_certs_dir, nmx_certs = setup_certs_for_tests('nmx', ['nmx-cert1', 'nmx-cert2'],
                                                         engines, dut_hostname, False, scp_player)
        certs: Dict[str, CertInfo] = {ClusterApps.NMX_CONTROLLER: nmx_certs[0],
                                      ClusterApps.NMX_TELEMETRY: nmx_certs[1]}
    with allure.step('enable cluster and clear managers config'):
        for app_name in ClusterApps.ALL_APPS:
            clear_manager_config(app_name)
    with allure.step(f'Import and load cert & {"external" if use_external else "global"} cacert'):
        import_test_certs(scp_player, TestToolkit.engines.dut, list(certs.values()), use_external)
    for app_name in ClusterApps.ALL_APPS:
        with allure.step(f'bind ca/cert to {app_name}'):
            cluster.apps.app_name[app_name].manager.certificate.action_update(
                certs[app_name].name).verify_result()
            cluster.apps.app_name[app_name].manager.ca_certificate.action_update(
                certs[app_name].cacert_name).verify_result()
        with allure.step(f'Update encryption mode to {app_name}'):
            cluster.apps.app_name[app_name].manager.encryption.action_update(encryption_mode).verify_result()
        with allure.step(f'Enable {app_name} manager'):
            cluster.apps.app_name[app_name].manager.action_update(ENABLED).verify_result()
    with allure.step('save config'):
        NvueGeneralCli.save_config(engines.dut)

    return tmp_certs_dir, nmx_certs, encryption_mode


def cluster_app_mngr_security_factory_reset_no_params_check():
    """
    Verify that certificates and encryption mode cleared to default after factory reset

    1.	Import and load cert & cacert
    2.	Update encryption mode
    3.	Factory reset
    4.	Verify values in show restored to defaults
    """
    engines = TestToolkit.engines
    devices = TestToolkit.devices

    if devices.dut.has_nmx:
        with allure.step('setup'):
            tmp_certs_dir, nmx_certs, encryption_mode = setup_cluster_app_mngr_security_checker(engines)
            certs: Dict[str, CertInfo] = {ClusterApps.NMX_CONTROLLER: nmx_certs[0],
                                          ClusterApps.NMX_TELEMETRY: nmx_certs[1]}

    yield  # factory reset

    try:
        if devices.dut.has_nmx:
            with allure.step('verify after factory reset'):
                with allure.step('enable cluster'):
                    enable_cluster()
                for app_name in ClusterApps.ALL_APPS:
                    with allure.independent_step(app_name):
                        with allure.independent_step('Verify values in show restored to defaults'):
                            verify_manager_show(app_name, expect_cert=Defaults.CERT, expect_cacert=Defaults.CACERT,
                                                expect_encryption=Defaults.ENCRYPTION)
                        with allure.independent_step('verify no manager client connection'):

                            verify_no_client_connection(app_name, certs[app_name], certs[app_name], True)
    finally:
        cleanup_certs_for_tests(tmp_certs_dir, nmx_certs)

    yield  # to prevent StopIteration on the 2nd next() call


cluster_app_mngr_security_factory_reset_no_params_checker = cluster_app_mngr_security_factory_reset_no_params_check()  # generator


def cluster_app_mngr_security_factory_reset_keep_all_config_check():
    """
    Verify that certificates and encryption mode cleared to default after factory reset

    1.	Import and load cert & cacert
    2.	Update encryption mode
    3.	Factory reset
    4.	verify everything is kept
    """
    engines = TestToolkit.engines
    devices = TestToolkit.devices

    if devices.dut.has_nmx:
        with allure.step('setup'):
            tmp_certs_dir, nmx_certs, encryption_mode = setup_cluster_app_mngr_security_checker(engines)
            certs: Dict[str, CertInfo] = {ClusterApps.NMX_CONTROLLER: nmx_certs[0],
                                          ClusterApps.NMX_TELEMETRY: nmx_certs[1]}

    yield  # factory reset

    try:
        if devices.dut.has_nmx:
            with allure.step('verify after factory reset'):
                for app_name in ClusterApps.ALL_APPS:
                    with allure.independent_step(app_name):
                        cert = certs[app_name]
                        with allure.independent_step('Verify values in show kept'):
                            verify_manager_show(app_name, expect_cert=cert.name, expect_cacert=cert.cacert_name,
                                                expect_encryption=encryption_mode)
                        with allure.independent_step(f'verify client connection: client mode: {encryption_mode}. expect success: True'):
                            run_manager_hello_request(app_name, encryption_mode, cert, cert, cert, cert, skip_etc_mapping=True).verify_result()
    finally:
        cleanup_certs_for_tests(tmp_certs_dir, nmx_certs)

    yield  # to prevent StopIteration on the 2nd next() call


@pytest.mark.nmx
@pytest.mark.security
@pytest.mark.parametrize('ca_type', [random.choice(optional_cacert_types())])
def test_cluster_app_mngr_connection_combined(ca_type):
    """
    Verify communication of app with manager

    Test in multiple ca/cert/encryption configurations
    """

    c1, c2, c3 = TestCert.cert_valid_1, TestCert.cert_valid_2, TestCert.cert_valid_3
    disabled, tls, mtls = EncryptionMode.DISABLED, EncryptionMode.TLS, EncryptionMode.MTLS
    up, down = ENABLED, DISABLED

    nmx_c, nmx_t = ClusterApps.NMX_CONTROLLER, ClusterApps.NMX_TELEMETRY
    cluster = Cluster()

    class Case:
        def __init__(self, name: str, c_state: str, c_cert: CertInfo, c_ca: CertInfo, c_encryption: str, t_state: str,
                     t_cert: CertInfo, t_ca: CertInfo, t_encryption: str, skip_badflow_check: bool = False):
            self.name: str = name
            self.c_state: str = c_state
            self.c_cert: CertInfo = c_cert
            self.c_ca: CertInfo = c_ca
            self.c_encryption: str = c_encryption
            self.t_state: str = t_state
            self.t_cert: CertInfo = t_cert
            self.t_ca: CertInfo = t_ca
            self.t_encryption: str = t_encryption
            self.skip_badflow_check: bool = skip_badflow_check

        def setup(self):
            with allure.step(f'setup case: {self.name}'):
                self.__setup_app(nmx_c, self.c_state, self.c_cert, self.c_ca, self.c_encryption)
                self.__setup_app(nmx_t, self.t_state, self.t_cert, self.t_ca, self.t_encryption)

        def verify(self):
            with allure.step(f'verify that client of each app can connect only with the matching configuration'):
                with allure.independent_step('good flow: check clients with matching configurations'):
                    self.__verify_goodflow()
                if not self.skip_badflow_check:
                    with allure.step('bad flow: check clients with opposite configurations'):
                        self.__verify_badflow()

        def cleanup(self):
            for app in ClusterApps.ALL_APPS:
                clear_manager_config(app)

        def __setup_app(self, app: str, state: str, cert: CertInfo, ca: CertInfo, encryption: str):
            with allure.step(f'setup {app}'):
                if state == DISABLED:
                    return
                mngr: Manager = cluster.apps.app_name[app].manager
                enable_cluster_app_manager_state(mngr)
                if encryption == EncryptionMode.DISABLED:
                    return
                mngr.certificate.action_update(cert.name).verify_result()
                if encryption == EncryptionMode.MTLS:
                    mngr.ca_certificate.action_update(ca.cacert_name).verify_result()
                mngr.encryption.action_update(encryption)

        def __verify_goodflow(self):
            with allure.step('good flow: check clients with matching configurations'):
                with allure.independent_step(nmx_c):
                    run_manager_hello_request(nmx_c, self.c_encryption, self.c_cert, self.c_ca, self.c_ca,
                                              self.c_cert).verify_result(True)
                with allure.independent_step(nmx_t):
                    run_manager_hello_request(nmx_t, self.t_encryption, self.t_cert, self.t_ca, self.t_ca,
                                              self.t_cert).verify_result(True)

        def __verify_badflow(self):
            with allure.step('bad flow: check clients with opposite configurations'):
                with allure.independent_step(nmx_c):
                    run_manager_hello_request(nmx_c, self.t_encryption, self.t_cert, self.t_ca, self.t_ca,
                                              self.t_cert).verify_result(False)
                with allure.independent_step(nmx_t):
                    run_manager_hello_request(nmx_t, self.c_encryption, self.c_cert, self.c_ca, self.c_ca,
                                              self.c_cert).verify_result(False)

    cases: List[Case] = [
        Case('same config', up, c1, c2, tls, up, c1, c2, tls, True),
        Case('same encryption different certs', up, c1, c2, tls, up, c2, c1, tls),
        Case('different encryption different certs', up, c1, c2, tls, up, c2, c1, mtls),
    ]

    with allure.step('enable cluster'):
        enable_cluster()

    with allure.step('run all cases'):
        for case in cases:
            with allure.independent_step(case.name):
                with allure.step('setup'):
                    case.setup()
                with allure.independent_step('verify connection'):
                    case.verify()
                with allure.step('cleanup'):
                    case.cleanup()
