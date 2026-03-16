"""
NV Bridge Encryption Tests.

Tests for verifying system and cluster internal encryption functionality.

Test setup: NVL6 setups
Preconditions:
- The switch completed the init flow
- Cluster apps are started
- NV Bridge has to be configured
"""

from __future__ import annotations

import logging
import time

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import AclConsts, ApiType, ClusterApps
from ngts.nvos_tools.acl.acl import Acl, AclID
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.NvBridgeTool import NvBridgeTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OpenSslSClient import OpenSslSClient
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.nmx_cert.constants import (
    NV_BRIDGE_SERVER_PORT,
    EncryptionMode,
)
from ngts.tests_nvos.general.security.nmx_cert.helpers import (
    enable_cluster,
)
from ngts.tests_nvos.general.security.nv_bridge.helpers import (
    reset_cluster_app,
    rotate_cluster_internal_and_verify,
    rotate_system_internal_and_verify,
    verify_cluster_app_internal_cert_files,
    verify_cluster_app_internal_has_empty_defaults,
    verify_cluster_app_internal_json,
    verify_cluster_app_internal_show,
    verify_nv_bridge_has_connection,
    verify_system_internal_cert_files,
    verify_system_internal_has_empty_defaults,
    verify_system_internal_json,
    verify_system_internal_show,
    wait_for_cluster_app_update,
)

logger = logging.getLogger(__name__)


def open_port_via_sys_control_plane_acl(acl_name: str, port: int, rule_id: str = "20") -> AclID:
    """
    Open a TCP port via system control-plane ACL.

    Args:
        acl_name: Name of the ACL to create
        port: TCP port number to open
        rule_id: Rule ID for the ACL rule

    Returns:
        Acl object for later cleanup
    """
    with allure.step(f"Create ACL {acl_name} to permit TCP port {port}"):
        acl = Acl()
        mgmt_port0 = Port("eth0")
        acl.set(acl_name).verify_result()
        acl_obj = acl.acl_id[acl_name]
        acl_obj.set(AclConsts.TYPE, "ipv4").verify_result()

        acl_obj.rule.set(rule_id).verify_result()
        rule_obj = acl_obj.rule.rule_id[rule_id]
        rule_obj.action.set(AclConsts.PERMIT).verify_result()
        rule_obj.match.ip.set_protocol("tcp").verify_result()
        rule_obj.match.ip.tcp.dest_port.set(port).verify_result()

    with allure.step(f"Attach ACL {acl_name} to sys control-plane inbound"):
        mgmt_port0.interface.acl.acl_id[acl_name].inbound.set(AclConsts.CONTROL_PLANE).verify_result()

    logger.info(f"ACL {acl_name} configured to permit TCP port {port}")
    return acl_obj


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nv_bridge
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_bridge_system_encryption_show(engines, devices, test_api):
    """
    Test Objective: Verify system internal encryption default field and values

    Test Flow:
    1. Run nv show system internal - Verify command has default empty fields
    """
    TestToolkit.tested_api = test_api

    with allure.step("Verify nv show system internal has default empty fields"):
        verify_system_internal_show()


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("disable_cluster")
@pytest.mark.parametrize("app_name", [ClusterApps.NMX_CONTROLLER])
def test_bridge_cluster_encryption_show(engines, devices, random_api, app_name):
    """
    Test Objective: Verify cluster internal encryption default field and values

    Test Flow:
    1. Run nv show cluster apps <app> internal - Verify command is pruned
       when cluster is disabled
    2. Enable cluster
    3. Run nv show cluster apps <app> internal - Verify command has default
       empty fields
    """
    TestToolkit.tested_api = random_api

    with allure.step(f"Verify nv show cluster apps {app_name} internal is pruned when cluster is disabled"):
        verify_cluster_app_internal_show(app_name, expect_success=False)

    with allure.step("Enable cluster"):
        enable_cluster(force_wait=True)

    with allure.step(f"Verify nv show cluster apps {app_name} internal has default empty fields"):
        verify_cluster_app_internal_has_empty_defaults(app_name)


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("restore_system_internal_config")
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_bridge_system_encryption_set(engines, devices, test_api, import_certs_with_alt: tuple[CertInfo, CertInfo, CertInfo]):
    """
    Test Objective: Verify system internal encryption action update works as
    expected

    Test Flow:
    1. Import certificate and ca-certificate (done by fixture)
    2. Enable cluster and start cluster apps
    3. Run nv show system internal - Verify command has default empty fields
    4. nv action update system internal certificate - Update system internal
       certificate and verify show and verify cert at path exists
    5. nv action update system internal ca-certificate - Update system internal
       ca-certificate and verify show and verify ca-cert at path exists
    6. nv action update system internal encryption - Update system internal
       encryption and verify show
    7. Run nv show system internal - Verify command has all the required values
    """
    TestToolkit.tested_api = test_api
    system = System()
    with allure.step("Import bridge certificate"):
        bridge_cert, bridge_alt_cert, _ = import_certs_with_alt

    with allure.step("Verify nv show system internal has default empty fields"):
        verify_system_internal_show()

    with allure.step("Update system internal certificate"):
        system.internal.certificate.action_update(bridge_cert.name).verify_result()
        with allure.step("Verify show reflects certificate update"):
            verify_system_internal_show(expect_cert=bridge_cert.name)
        with allure.step("Verify certificate file exists"):
            verify_system_internal_cert_files(engines.dut, expected_cert_id=bridge_cert.name)

    with allure.step("Update system internal ca-certificate"):
        system.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        with allure.step("Verify show reflects ca-certificate update"):
            verify_system_internal_show(expect_cert=bridge_cert.name, expect_cacert=bridge_cert.cacert_name)
        with allure.step("Verify ca-certificate file exists"):
            verify_system_internal_cert_files(engines.dut, expected_cert_id=bridge_cert.name, expected_cacert_id=bridge_cert.cacert_name)

    with allure.step("Update system internal encryption to mtls"):
        system.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()
        with allure.step("Verify show reflects encryption update"):
            verify_system_internal_show(
                expect_cert=bridge_cert.name, expect_cacert=bridge_cert.cacert_name, expect_encryption=EncryptionMode.MTLS
            )
            verify_system_internal_json(
                engines.dut,
                expected_cert=bridge_cert.name,
                expected_cacert=bridge_cert.cacert_name,
                expected_encryption=EncryptionMode.MTLS,
            )

    with allure.step("Verify nv show system internal has all required values"):
        verify_system_internal_show(
            expect_cert=bridge_cert.name, expect_cacert=bridge_cert.cacert_name, expect_encryption=EncryptionMode.MTLS
        )


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("enable_cluster")
def test_bridge_cluster_encryption_set(
    engines, devices, random_api, restore_cluster_app_internal_config, import_certs_with_alt: tuple[CertInfo, CertInfo, CertInfo]
):
    """
    Test Objective: Verify cluster internal encryption actions work as expected

    Test Flow:
    1. Enable cluster and start cluster apps
    2. Import certificate and ca-certificate
    3. nv show cluster apps <app> internal - Verify command has default
       empty fields
    4. nv action update cluster apps <app> internal certificate - Update
       cluster internal certificate and verify show and verify cert at
       path exists
    5. nv action update cluster apps <app> internal ca-certificate - Update
       cluster internal ca-certificate and verify show and verify ca-cert
       at path exists
    6. nv action update cluster apps <app> internal encryption - Update
       cluster internal encryption and verify show
    7. nv show cluster apps <app> internal - Verify all updated fields
       are seen
    """
    TestToolkit.tested_api = random_api
    cluster = Cluster()
    app_name = restore_cluster_app_internal_config
    app = cluster.apps.app_name[app_name]
    bridge_cert, bridge_alt_cert, _ = import_certs_with_alt

    with allure.step(f"Verify nv show cluster apps {app_name} internal has default empty fields"):
        verify_cluster_app_internal_has_empty_defaults(app_name)

    with allure.step(f"Update cluster apps {app_name} internal certificate"):
        app.internal.certificate.action_update(bridge_cert.name).verify_result()
        with allure.step("Verify show reflects certificate update"):
            verify_cluster_app_internal_show(app_name, expect_cert=bridge_cert.name)

        with allure.step("Verify certificate file exists"):
            verify_cluster_app_internal_cert_files(app_name, engines.dut, expected_cert_id=bridge_cert.name)

    with allure.step(f"Update cluster apps {app_name} internal ca-certificate"):
        app.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        with allure.step("Verify show reflects ca-certificate update"):
            verify_cluster_app_internal_show(app_name, expect_cert=bridge_cert.name, expect_cacert=bridge_cert.cacert_name)
        with allure.step("Verify ca-certificate file exists"):
            verify_cluster_app_internal_cert_files(
                app_name, engines.dut, expected_cert_id=bridge_cert.name, expected_cacert_id=bridge_cert.cacert_name
            )

    with allure.step(f"Update cluster apps {app_name} internal encryption to mtls"):
        app.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()
        wait_for_cluster_app_update(cluster, engines.dut)
        with allure.step("Verify show reflects encryption update"):
            verify_cluster_app_internal_show(
                app_name, expect_cert=bridge_cert.name, expect_cacert=bridge_cert.cacert_name, expect_encryption=EncryptionMode.MTLS
            )

    with allure.step(f"Verify nv show cluster apps {app_name} internal shows all updated fields"):
        verify_cluster_app_internal_show(
            app_name, expect_cert=bridge_cert.name, expect_cacert=bridge_cert.cacert_name, expect_encryption=EncryptionMode.MTLS
        )


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("enable_cluster", "restore_cluster_app_internal_config", "restore_system_internal_config")
def test_bridge_cluster_rotation(
    engines, devices, random_api, restore_cluster_app_internal_config, import_certs_with_alt: tuple[CertInfo, CertInfo, CertInfo]
):
    """
    Test Objective: Verify certificate rotation flow with connection verification
    for both system internal and cluster internal encryption.

    Test Flow:
    1. Enable cluster and import certificates (done by fixtures)
    2. Configure system internal with cert, ca-cert, and mtls
    3. Configure cluster app with cert, ca-cert, and mtls
    4. Reset cluster app and verify initial connection
    5. Rotation cycle 1 - system internal:
       - Add alternate cert, rotate, verify connection
    6. Restore system alt-cert and verify connection
    7. Rotation cycle 2 - cluster internal:
       - Add alternate cert, rotate, verify connection
    8. Restore cluster alt-cert and verify connection
    9. Rotation cycle 3 - rotate system internal with reset
    10. Rotation cycle 4 - rotate cluster internal with reset
    """
    TestToolkit.tested_api = random_api
    cluster = Cluster()
    system = System()
    app_name = restore_cluster_app_internal_config
    app = cluster.apps.app_name[app_name]
    bridge_cert, bridge_alt_cert, _ = import_certs_with_alt

    with allure.step("Configure system internal with cert, ca-cert, mtls"):
        system.internal.certificate.action_update(bridge_cert.name).verify_result()
        system.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        system.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()

        with allure.step("Verify system internal configuration"):
            verify_system_internal_show(
                expect_cert=bridge_cert.name,
                expect_cacert=bridge_cert.cacert_name,
                expect_encryption=EncryptionMode.MTLS,
            )
            verify_system_internal_cert_files(
                engines.dut,
                expected_cert_id=bridge_cert.name,
                expected_cacert_id=bridge_cert.cacert_name,
            )

    with allure.step(f"Configure cluster {app_name} with cert, ca-cert, mtls"):
        app.internal.certificate.action_update(bridge_cert.name).verify_result()
        app.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        app.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()

        with allure.step(f"Verify cluster {app_name} internal configuration"):
            verify_cluster_app_internal_show(
                app_name,
                expect_cert=bridge_cert.name,
                expect_cacert=bridge_cert.cacert_name,
                expect_encryption=EncryptionMode.MTLS,
            )
            verify_cluster_app_internal_cert_files(
                app_name,
                engines.dut,
                expected_cert_id=bridge_cert.name,
                expected_cacert_id=bridge_cert.cacert_name,
            )

    with allure.step("Reset cluster app and verify initial connection"):
        reset_cluster_app(cluster, app_name, engines.dut)
        verify_nv_bridge_has_connection(engines.dut, expect_connection=True)

    with allure.step("Rotation cycle 1 - rotate system internal"):
        system.internal.alternate_certificate.action_update(bridge_alt_cert.name).verify_result()
        verify_system_internal_show(
            expect_cert=bridge_cert.name,
            expect_cacert=bridge_cert.cacert_name,
            expect_alt_cert=bridge_alt_cert.name,
            expect_encryption=EncryptionMode.MTLS,
        )
        verify_system_internal_cert_files(
            engines.dut,
            expected_cert_id=bridge_cert.name,
            expected_cacert_id=bridge_cert.cacert_name,
            expected_alt_cert_id=bridge_alt_cert.name,
        )
        current_sys_cert = bridge_cert.name
        current_sys_alt = bridge_alt_cert.name
        current_sys_cert, current_sys_alt = rotate_system_internal_and_verify(
            system,
            cluster,
            app_name,
            engines.dut,
            bridge_cert.cacert_name,
            current_sys_cert,
            current_sys_alt,
            EncryptionMode.MTLS,
        )
        verify_nv_bridge_has_connection(engines.dut, expect_connection=True)

    with allure.step("Restore system alt-cert and verify connection"):
        system.internal.alternate_certificate.action_restore().verify_result()
        wait_for_cluster_app_update(cluster, engines.dut)
        verify_nv_bridge_has_connection(engines.dut, expect_connection=True)

    with allure.step("Rotation cycle 2 - rotate cluster internal"):
        app.internal.alternate_certificate.action_update(bridge_alt_cert.name).verify_result()
        verify_cluster_app_internal_show(
            app_name,
            expect_cert=bridge_cert.name,
            expect_cacert=bridge_cert.cacert_name,
            expect_encryption=EncryptionMode.MTLS,
            expect_alt_cert=bridge_alt_cert.name,
        )
        verify_cluster_app_internal_cert_files(
            app_name,
            engines.dut,
            expected_cert_id=bridge_cert.name,
            expected_cacert_id=bridge_cert.cacert_name,
            expected_alt_cert_id=bridge_alt_cert.name,
        )
        current_cluster_cert = bridge_cert.name
        current_cluster_alt = bridge_alt_cert.name
        current_cluster_cert, current_cluster_alt = rotate_cluster_internal_and_verify(
            app,
            cluster,
            app_name,
            engines.dut,
            bridge_cert.cacert_name,
            current_cluster_cert,
            current_cluster_alt,
            EncryptionMode.MTLS,
        )
        verify_nv_bridge_has_connection(engines.dut, expect_connection=True)

    with allure.step("Restore cluster alt-cert and verify connection"):
        app.internal.alternate_certificate.action_restore().verify_result()
        wait_for_cluster_app_update(cluster, engines.dut)
        verify_nv_bridge_has_connection(engines.dut, expect_connection=True)

    with allure.step("Rotation cycle 3 - rotate system internal with reset"):
        system.internal.alternate_certificate.action_update(bridge_cert.name).verify_result()
        current_sys_cert, current_sys_alt = rotate_system_internal_and_verify(
            system,
            cluster,
            app_name,
            engines.dut,
            bridge_cert.cacert_name,
            current_sys_cert,
            current_sys_alt,
            EncryptionMode.MTLS,
            should_reset=True,
        )

    with allure.step("Rotation cycle 4 - rotate cluster internal with reset"):
        app.internal.alternate_certificate.action_update(bridge_cert.name).verify_result()
        current_cluster_cert, current_cluster_alt = rotate_cluster_internal_and_verify(
            app,
            cluster,
            app_name,
            engines.dut,
            bridge_cert.cacert_name,
            current_cluster_cert,
            current_cluster_alt,
            EncryptionMode.MTLS,
            should_reset=True,
        )

    logger.info(
        f"Rotation flow completed. "
        f"System cert: {current_sys_cert}, alt: {current_sys_alt}. "
        f"Cluster cert: {current_cluster_cert}, alt: {current_cluster_alt}."
    )


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("enable_cluster", "restore_system_internal_config")
def test_bridge_main_flow(
    engines, devices, random_api, import_certs_with_alt: tuple[CertInfo, CertInfo, CertInfo], restore_cluster_app_internal_config
):
    """
    Test Objective: Verify NV Bridge encryption main flow with grpc requests.

    Test Flow:
    1. Enable cluster and start cluster apps (done by fixture)
    2. Import certs and ca-certs (done by fixture)
    3. Update cluster internal with certificate, ca-certificate, and mtls
    4. Verify basic grpc hello request to bridge (plaintext)
    5. Configure NV Bridge (system internal) with certificate, ca-certificate
       and mtls
    6. Perform encrypted grpc request to bridge
    """
    cluster = Cluster()
    system = System()
    app_name = restore_cluster_app_internal_config
    app = cluster.apps.app_name[app_name]
    bridge_cert, bridge_alt_cert, _ = import_certs_with_alt

    nv_bridge_tool = NvBridgeTool(host=engines.dut.ip)

    with allure.step("Update cluster internal with cert, ca-cert, mtls"):
        app.internal.certificate.action_update(bridge_cert.name).verify_result()
        app.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        app.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()
        wait_for_cluster_app_update(cluster, engines.dut)

        with allure.step("Verify cluster internal configuration"):
            verify_cluster_app_internal_show(
                app_name,
                expect_cert=bridge_cert.name,
                expect_cacert=bridge_cert.cacert_name,
                expect_encryption=EncryptionMode.MTLS,
            )
            verify_cluster_app_internal_json(
                engines.dut,
                app_name,
                expected_cert=bridge_cert.name,
                expected_cacert=bridge_cert.cacert_name,
                expected_encryption=EncryptionMode.MTLS,
            )

    with allure.step("Verify basic grpc hello request to bridge (plaintext)"):
        nv_bridge_tool.run_bridge_hello(plaintext=True, expect_success=True)

    with allure.step("Configure NV Bridge with cert, ca-cert, mtls"):
        system.internal.certificate.action_update(bridge_cert.name).verify_result()
        system.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        system.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()
        wait_for_cluster_app_update(cluster, engines.dut)

        with allure.step("Verify system internal configuration"):
            verify_system_internal_show(
                expect_cert=bridge_cert.name,
                expect_cacert=bridge_cert.cacert_name,
                expect_encryption=EncryptionMode.MTLS,
            )
            verify_system_internal_json(
                engines.dut,
                expected_cert=bridge_cert.name,
                expected_cacert=bridge_cert.cacert_name,
                expected_encryption=EncryptionMode.MTLS,
            )

    with allure.step("Perform encrypted grpc request to bridge"):
        nv_bridge_tool.run_bridge_hello(
            client_cert=bridge_cert,
            client_cacert=bridge_cert,
            plaintext=False,
            expect_success=True,
        )


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("enable_cluster")
def test_bridge_tls_handshake_verification(
    engines,
    devices,
    random_api,
    import_certs_with_alt: tuple[CertInfo, CertInfo, CertInfo],
    restore_cluster_app_internal_config,
    restore_system_internal_config,
):
    """
    Test Objective: Verify TLS handshake using OpenSSL s_client after
    configuring cluster and system internal encryption.

    Test Flow:
    1. Enable cluster and start cluster apps (done by fixture)
    2. Import certs and ca-certs (done by fixture)
    3. Configure cluster internal with cert, ca-cert, and mtls
    4. Verify TLS handshake on cluster internal port (9381) succeeds
    5. Verify TLS handshake on cluster internal port fails with invalid certs
    6. Configure system internal with cert, ca-cert, and mtls
    7. Verify TLS handshake on system internal port (50052) succeeds
    8. Verify TLS handshake on system internal port fails with invalid certs
    """
    TestToolkit.tested_api = random_api
    cluster = Cluster()
    system = System()
    app_name = restore_cluster_app_internal_config
    app = cluster.apps.app_name[app_name]
    bridge_cert, _, mismatched_cert = import_certs_with_alt
    dut_ip = engines.dut.ip

    with allure.step("Configure cluster internal with cert, ca-cert, mtls"):
        wait_for_cluster_app_update(cluster, engines.dut)
        app.internal.certificate.action_update(bridge_cert.name).verify_result()
        app.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        app.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()

        verify_cluster_app_internal_show(
            app_name,
            expect_cert=bridge_cert.name,
            expect_cacert=bridge_cert.cacert_name,
            expect_encryption=EncryptionMode.MTLS,
        )

    # acl_name = "AAA-nmx-c-verification"
    # acl_obj = open_port_via_sys_control_plane_acl(acl_name, NV_BRIDGE_CLIENT_PORT)

    # cluster_client = OpenSslSClient(dut_ip, NV_BRIDGE_CLIENT_PORT)

    # with allure.step("Verify TLS handshake on cluster internal port succeeds"):
    #     result = cluster_client.verify_successful_handshake(
    #         ca_file=bridge_cert.cacert,
    #         cert=bridge_cert.public,
    #         key=bridge_cert.private,
    #     )
    #     logger.info(
    #         f"Cluster internal TLS verified: return_code={result.return_code}, tls={result.tls_version}, alpn={result.alpn_protocol}"
    #     )

    # with allure.step("Verify TLS handshake fails with invalid certs"):
    #     _verify_tls_handshake_negative_scenarios(cluster_client, bridge_cert, mismatched_cert, "Cluster")

    with allure.step("Configure system internal with cert, ca-cert, mtls"):
        system.internal.certificate.action_update(bridge_cert.name).verify_result()
        system.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        system.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()
        wait_for_cluster_app_update(cluster, engines.dut)
        # Need additional 2 sec for bridge to be fully encrypted
        time.sleep(2)

        verify_system_internal_show(
            expect_cert=bridge_cert.name,
            expect_cacert=bridge_cert.cacert_name,
            expect_encryption=EncryptionMode.MTLS,
        )

    system_client = OpenSslSClient(dut_ip, NV_BRIDGE_SERVER_PORT)

    with allure.step("Verify TLS handshake on system internal port succeeds"):
        result = system_client.verify_successful_handshake(
            ca_file=bridge_cert.cacert,
            cert=bridge_cert.public,
            key=bridge_cert.private,
            alpn="h2",
        )
        logger.info(
            f"System internal TLS verified: return_code={result.return_code}, tls={result.tls_version}, alpn={result.alpn_protocol}"
        )

    with allure.step("Verify TLS handshake fails with invalid certs"):
        _verify_tls_handshake_negative_scenarios(system_client, bridge_cert, mismatched_cert, "Bridge server")


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("enable_cluster", "restore_system_internal_config")
def test_bridge_cluster_encryption_negative(
    engines, devices, random_api, import_certs_with_alt: tuple[CertInfo, CertInfo, CertInfo], restore_cluster_app_internal_config
):
    """
    Test Objective: Verify all negative nv-bridge cases for cluster.

    Test Flow:
    1. Enable cluster and start cluster apps (done by fixture)
    2. Import certs and ca-certs (done by fixture)
    3. Verify nv show cluster apps <app> internal has default empty fields
    4. Try to enable mtls encryption without cert and ca-cert - expect fail
    5. Update cluster cert only
    6. Try to enable mtls encryption without ca-cert - expect fail
    7. Update ca-cert that didn't sign the cert - expect fail
    8. Update cluster cert and matching ca-cert - expect success
    9. Set system with another cert and ca-cert (mismatched)
    10. Perform request with system cert - expect fail
    11. Perform request with cluster cert - expect fail
    """
    cluster = Cluster()
    app_name = restore_cluster_app_internal_config
    app = cluster.apps.app_name[app_name]
    bridge_cert, bridge_alt_cert, mismatched_cert = import_certs_with_alt

    with allure.step(f"Verify nv show cluster apps {app_name} internal has default empty fields"):
        verify_cluster_app_internal_has_empty_defaults(app_name)

    with allure.step("Try to enable mtls encryption without cert and ca-cert - expect fail"):
        result = app.internal.encryption.action_update(EncryptionMode.MTLS)
        result.verify_result(should_succeed=False)

    with allure.step(f"Update cluster apps {app_name} internal certificate only"):
        app.internal.certificate.action_update(bridge_cert.name).verify_result()

    with allure.step("Try to enable mtls encryption without ca-cert - expect fail"):
        result = app.internal.encryption.action_update(EncryptionMode.MTLS)
        result.verify_result(should_succeed=False)

    with allure.step("Update ca-cert that didn't sign the cert - expect fail on applying mtls"):
        result = app.internal.ca_certificate.action_update(mismatched_cert.cacert_name)
        result.verify_result()

    with allure.step("Try to enable mtls encryption with incorrect ca-cert - expect fail"):
        result = app.internal.encryption.action_update(EncryptionMode.MTLS)
        result.verify_result(should_succeed=False)

    with allure.step(f"Update cluster apps {app_name} with matching cert and ca-cert"):
        app.internal.ca_certificate.action_update(bridge_cert.cacert_name).verify_result()
        app.internal.encryption.action_update(EncryptionMode.MTLS).verify_result()
        wait_for_cluster_app_update(cluster, engines.dut)


@pytest.mark.system
@pytest.mark.security
@pytest.mark.nmx
@pytest.mark.usefixtures("restore_system_internal_config")
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_bridge_system_encryption_negative(
    engines,
    devices,
    test_api,
    import_certs: tuple[CertInfo, CertInfo],
):
    """
    Test Objective: Verify all negative nv-bridge cases for system.

    Test Flow:
    1. Import certs and ca-certs (done by fixture)
    2. Enable cluster and start cluster apps
    3. Verify nv show system internal has default empty fields
    4. Try to update mtls encryption without cert and ca-cert - expect fail
    5. Update system cert only
    6. Try to update mtls encryption without ca-cert - expect fail
    7. Update ca-cert that didn't sign the cert - expect fail
    """
    TestToolkit.tested_api = test_api
    system = System()
    bridge_cert, mismatched_cert = import_certs

    with allure.step("Verify nv show system internal has default empty fields"):
        verify_system_internal_has_empty_defaults()

    with allure.step("Try to update mtls encryption without cert and ca-cert - expect fail"):
        result = system.internal.encryption.action_update(EncryptionMode.MTLS)
        result.verify_result(should_succeed=False)

    with allure.step("Update system cert only"):
        system.internal.certificate.action_update(bridge_cert.name).verify_result()

    with allure.step("Try to update mtls encryption without ca-cert - expect fail"):
        result = system.internal.encryption.action_update(EncryptionMode.MTLS)
        result.verify_result(should_succeed=False)

    with allure.step("Update ca-cert that didn't sign the cert"):
        result = system.internal.ca_certificate.action_update(mismatched_cert.cacert_name)
        result.verify_result()

    with allure.step("Try to update mtls encryption with bad ca-cert - expect fail"):
        result = system.internal.encryption.action_update(EncryptionMode.MTLS)
        result.verify_result(should_succeed=False)


def _verify_tls_handshake_negative_scenarios(
    client: OpenSslSClient,
    valid_cert: CertInfo,
    invalid_cert: CertInfo,
    service_name: str,
) -> None:
    """
    Verify TLS handshake fails with various invalid certificate scenarios.

    Args:
        client: OpenSslSClient instance to use for verification.
        valid_cert: Valid certificate that should work.
        invalid_cert: Invalid/mismatched certificate for negative tests.
        service_name: Name of service for logging (e.g., "Cluster", "System").
    """
    with allure.step(f"Verify {service_name} TLS fails with wrong client cert"):
        result = client.verify_handshake_fails(
            ca_file=valid_cert.cacert,
            cert=invalid_cert.public,
            key=invalid_cert.private,
            expected_error=r"(unknown ca|alert)",
        )
        logger.info(f"{service_name} TLS failure (wrong cert): return_code={result.return_code}, error={result.error_message}")

    with allure.step(f"Verify {service_name} TLS fails with wrong CA"):
        result = client.verify_handshake_fails(
            ca_file=invalid_cert.cacert,
            cert=valid_cert.public,
            key=valid_cert.private,
            expected_return_code=20,
            expected_error=r"unable to get local issuer certificate",
        )
        logger.info(f"{service_name} TLS failure (wrong CA): return_code={result.return_code}, error={result.error_message}")

    with allure.step(f"Verify {service_name} TLS fails with no client cert"):
        result = client.verify_handshake_fails(
            ca_file=valid_cert.cacert,
            expected_error=r"(certificate required|unknown ca|alert)",
        )
        logger.info(f"{service_name} TLS failure (no cert): return_code={result.return_code}, error={result.error_message}")

    with allure.step(f"Verify {service_name} TLS fails with no CA"):
        result = client.verify_handshake_fails(
            cert=valid_cert.public,
            key=valid_cert.private,
            expected_error=r"(self[- ]signed|unable to get local issuer|verify)",
        )
        logger.info(f"{service_name} TLS failure (no CA): return_code={result.return_code}, error={result.error_message}")
