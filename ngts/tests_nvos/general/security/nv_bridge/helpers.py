"""
Helper functions for NV Bridge encryption tests.
"""

from __future__ import annotations

import logging
import time

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine

import ngts.tools.test_utils.allure_utils as allure
from ngts.ngts_types import EnginesT
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvBridgeTool import verify_nv_bridge_has_connection
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.helpers import (
    verify_file_exists_in_dut,
)
from ngts.tests_nvos.general.security.helpers import (
    get_test_certs_dir_location,
    import_cas_safely,
    import_certs_safely,
    setup_certs_for_tests,
)
from ngts.tests_nvos.general.security.nmx_cert.constants import (
    ALTERNATE_CERTIFICATE,
    CA_CERTIFICATE,
    CERTIFICATE,
    CLUSTER_INTERNAL_JSON_PATH,
    DISABLED,
    ENCRYPTION,
    ITEM_NOT_EXIST_ERR,
    STATE,
    SYSTEM_INTERNAL_JSON_PATH,
    ClusterInternalJsonFields,
    Defaults,
    FieldsInShowOf,
    SystemInternalJsonFields,
)
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player

logger = logging.getLogger(__name__)

# System internal certificate paths
SYSTEM_INTERNAL_CERT_PATH = "/etc/internal/cert/{}.crt"
SYSTEM_INTERNAL_KEY_PATH = "/etc/internal/cert/{}.key"
SYSTEM_INTERNAL_CACERT_PATH = "/etc/internal/ca_cert/{}.crt"
SYSTEM_INTERNAL_ALTERNATE_CERT_PATH = "/etc/internal/alt_cert/{}.crt"
SYSTEM_INTERNAL_ALTERNATE_KEY_PATH = "/etc/internal/alt_cert/{}.key"

# Cluster app internal certificate paths (different from manager paths)
CLUSTER_INTERNAL_CERT_PATH = "/etc/{}/int_cert/{}.crt"
CLUSTER_INTERNAL_KEY_PATH = "/etc/{}/int_cert/{}.key"
CLUSTER_INTERNAL_CACERT_PATH = "/etc/{}/int_ca_cert/{}.crt"
CLUSTER_INTERNAL_ALTERNATE_CERT_PATH = "/etc/{}/int_alt_cert/{}.crt"
CLUSTER_INTERNAL_ALTERNATE_KEY_PATH = "/etc/{}/int_alt_cert/{}.key"


def is_cluster_enabled() -> bool:
    """Check if cluster is enabled."""
    with allure.step("check if cluster is enabled"):
        output = OutputParsingTool.parse_json_str_to_dictionary(Cluster().show()).get_returned_value()
        return output.get(STATE) != DISABLED


def verify_item_not_exist(output: str) -> bool:
    """Verify that command output indicates item does not exist."""
    return ITEM_NOT_EXIST_ERR in output


def verify_component_show(
    component: BaseComponent,
    required_fields: list[str],
    value_expectations: dict[str, str | None | int],
    expect_success: bool = True,
):
    """
    Verify show command output for a component.

    Args:
        component: The component to verify show output for
        required_fields: List of fields that must exist in output
        value_expectations: Dict of field names to expected values
    """
    with allure.step(f"verify show: {component._resource_path}"):
        with allure.step("run show command"):
            output = component.show(should_succeed=expect_success)
            if not expect_success:
                return
        out = OutputParsingTool.parse_json_str_to_dictionary(output).verify_result()
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(out, required_fields, check_empty_values=False).verify_result()
        for field, expected in value_expectations.items():
            ValidationTool.verify_field_value_in_output(out, field, expected).verify_result()


def verify_system_internal_show(
    expect_cert: str = "",
    expect_cacert: str = "",
    expect_alt_cert: str = "",
    expect_encryption: str = Defaults.ENCRYPTION,
):
    """Verify system internal show command output."""
    verify_component_show(
        System().internal,
        FieldsInShowOf.INTERNAL,
        {
            CERTIFICATE: expect_cert,
            CA_CERTIFICATE: expect_cacert,
            ENCRYPTION: expect_encryption,
            ALTERNATE_CERTIFICATE: expect_alt_cert,
        },
    )


def verify_system_internal_json(
    dut_engine: LinuxSshEngine,
    expected_cert: str = "",
    expected_cacert: str = "",
    expected_alt_cert: str = "",
    expected_encryption: str = Defaults.ENCRYPTION,
):
    """Verify system internal json output."""
    with allure.step("verify system internal json"):
        output: str = dut_engine.run_cmd(f"sudo cat {SYSTEM_INTERNAL_JSON_PATH}; echo")
        output = OutputParsingTool.parse_json_str_to_dictionary(output).verify_result()
        cert_path = SYSTEM_INTERNAL_CERT_PATH.format(expected_cert) if expected_cert else ""
        cert_key_path = SYSTEM_INTERNAL_KEY_PATH.format(expected_cert) if expected_cert else ""

        cacert_path = SYSTEM_INTERNAL_CACERT_PATH.format(expected_cacert) if expected_cacert else ""

        alt_cert_path = SYSTEM_INTERNAL_ALTERNATE_CERT_PATH.format(expected_alt_cert) if expected_alt_cert else ""
        alt_cert_key_path = SYSTEM_INTERNAL_ALTERNATE_KEY_PATH.format(expected_alt_cert) if expected_alt_cert else ""

        with allure.independent_step("verify certificate path"):
            assert output.get(SystemInternalJsonFields.CERTIFICATE, "") == cert_path, (
                f"certificate path is not expected: {output.get(SystemInternalJsonFields.CERTIFICATE, '')} != {cert_path}"
            )
        with allure.independent_step("verify certificate private key path"):
            assert output.get(SystemInternalJsonFields.CERTIFICATE_PRIVATE_KEY, "") == cert_key_path, (
                f"certificate private key path is not expected: {output.get(SystemInternalJsonFields.CERTIFICATE_PRIVATE_KEY, '')} != {cert_key_path}"
            )
        with allure.independent_step("verify ca certificate path"):
            assert output.get(SystemInternalJsonFields.CA_CERTIFICATE, "") == cacert_path, (
                f"ca certificate path is not expected: {output.get(SystemInternalJsonFields.CA_CERTIFICATE, '')} != {cacert_path}"
            )
        with allure.independent_step("verify alternate certificate path"):
            assert output.get(SystemInternalJsonFields.ALTERNATE_CERTIFICATE, "") == alt_cert_path, (
                f"alternate certificate path is not expected: {output.get(SystemInternalJsonFields.ALTERNATE_CERTIFICATE, '')} != {alt_cert_path}"
            )
        with allure.independent_step("verify alternate certificate private key path"):
            assert output.get(SystemInternalJsonFields.ALTERNATE_CERTIFICATE_PRIVATE_KEY, "") == alt_cert_key_path, (
                f"alternate certificate private key path is not expected: {output.get(SystemInternalJsonFields.ALTERNATE_CERTIFICATE_PRIVATE_KEY, '')} != {alt_cert_key_path}"
            )
        with allure.independent_step("verify encryption"):
            out_encryption = output.get(SystemInternalJsonFields.ENCRYPTION, "")
            assert out_encryption == expected_encryption, f"encryption is not expected: {out_encryption} != {expected_encryption}"


def verify_cluster_app_internal_json(
    dut_engine: LinuxSshEngine,
    app_name: str,
    expected_cert: str = "",
    expected_cacert: str = "",
    expected_alt_cert: str = "",
    expected_encryption: str = Defaults.ENCRYPTION,
):
    """Verify cluster app internal json output."""
    with allure.step("verify cluster app internal json"):
        output: str = dut_engine.run_cmd(f"sudo cat {CLUSTER_INTERNAL_JSON_PATH}; echo")
        output = OutputParsingTool.parse_json_str_to_dictionary(output).verify_result()
        cert_path = CLUSTER_INTERNAL_CERT_PATH.format(app_name, expected_cert) if expected_cert else ""
        cert_key_path = CLUSTER_INTERNAL_KEY_PATH.format(app_name, expected_cert) if expected_cert else ""
        cacert_path = CLUSTER_INTERNAL_CACERT_PATH.format(app_name, expected_cacert) if expected_cacert else ""
        alt_cert_path = CLUSTER_INTERNAL_ALTERNATE_CERT_PATH.format(app_name, expected_alt_cert) if expected_alt_cert else ""
        alt_cert_key_path = CLUSTER_INTERNAL_ALTERNATE_KEY_PATH.format(app_name, expected_alt_cert) if expected_alt_cert else ""

        full_app_name = "nmx-controller" if "nmx-c" in app_name else "nmx-telemetry"
        with allure.independent_step("verify certificate path"):
            cert_value = output.get(ClusterInternalJsonFields.CERTIFICATE.format(full_app_name), "")
            assert cert_value == cert_path, f"certificate path is not expected: {cert_value} != {cert_path}"
        with allure.independent_step("verify certificate private key path"):
            cert_key_value = output.get(
                ClusterInternalJsonFields.CERTIFICATE_PRIVATE_KEY.format(full_app_name),
                "",
            )
            assert cert_key_value == cert_key_path, f"certificate private key path is not expected: {cert_key_value} != {cert_key_path}"
        with allure.independent_step("verify ca certificate path"):
            cacert_value = output.get(ClusterInternalJsonFields.CA_CERTIFICATE.format(full_app_name), "")
            assert cacert_value == cacert_path, f"ca certificate path is not expected: {cacert_value} != {cacert_path}"
        with allure.independent_step("verify alternate certificate path"):
            alt_cert_value = output.get(
                ClusterInternalJsonFields.ALTERNATE_CERTIFICATE.format(full_app_name),
                "",
            )
            assert alt_cert_value == alt_cert_path, f"alternate certificate path is not expected: {alt_cert_value} != {alt_cert_path}"
        with allure.independent_step("verify alternate certificate private key path"):
            alt_cert_key_value = output.get(
                ClusterInternalJsonFields.ALTERNATE_CERTIFICATE_PRIVATE_KEY.format(full_app_name),
                "",
            )
            assert alt_cert_key_value == alt_cert_key_path, (
                f"alternate certificate private key path is not expected: {alt_cert_key_value} != {alt_cert_key_path}"
            )
        with allure.independent_step("verify encryption"):
            out_encryption = output.get(ClusterInternalJsonFields.ENCRYPTION.format(full_app_name), "")
            assert out_encryption == expected_encryption, f"encryption is not expected: {out_encryption} != {expected_encryption}"


def verify_cluster_app_internal_show(
    app_name: str,
    expect_cert: str = "",
    expect_cacert: str = "",
    expect_encryption: str = Defaults.ENCRYPTION,
    expect_alt_cert: str = "",
    expect_success: bool = True,
):
    """Verify cluster app internal show command output."""
    verify_component_show(
        Cluster().apps.app_name[app_name].internal,
        FieldsInShowOf.INTERNAL,
        {
            CERTIFICATE: expect_cert,
            CA_CERTIFICATE: expect_cacert,
            ENCRYPTION: expect_encryption,
            ALTERNATE_CERTIFICATE: expect_alt_cert,
        },
        expect_success=expect_success,
    )


def verify_system_internal_cert_files(
    dut_engine: LinuxSshEngine,
    expected_cert_id: str = "",
    expected_cacert_id: str = "",
    expected_alt_cert_id: str = "",
):
    """Verify system internal certificate files exist."""
    with allure.step("verify system internal cert files"):
        if expected_cert_id:
            verify_file_exists_in_dut(
                SYSTEM_INTERNAL_CERT_PATH.format(expected_cert_id),
                dut_engine,
                should_exist=True,
            )
            verify_file_exists_in_dut(
                SYSTEM_INTERNAL_KEY_PATH.format(expected_cert_id),
                dut_engine,
                should_exist=True,
            )
        if expected_alt_cert_id:
            verify_file_exists_in_dut(
                SYSTEM_INTERNAL_ALTERNATE_CERT_PATH.format(expected_alt_cert_id),
                dut_engine,
                should_exist=True,
            )
            verify_file_exists_in_dut(
                SYSTEM_INTERNAL_ALTERNATE_KEY_PATH.format(expected_alt_cert_id),
                dut_engine,
                should_exist=True,
            )
        if expected_cacert_id:
            verify_file_exists_in_dut(
                SYSTEM_INTERNAL_CACERT_PATH.format(expected_cacert_id),
                dut_engine,
                should_exist=True,
            )


def verify_cluster_app_internal_cert_files(
    app_name: str,
    dut_engine: LinuxSshEngine,
    expected_cert_id: str = "",
    expected_cacert_id: str = "",
    expected_alt_cert_id: str = "",
):
    """Verify cluster app internal certificate files exist."""
    with allure.step(f"verify {app_name} internal cert files"):
        if expected_cert_id:
            verify_file_exists_in_dut(
                CLUSTER_INTERNAL_CERT_PATH.format(app_name, expected_cert_id),
                dut_engine,
                should_exist=True,
            )
            verify_file_exists_in_dut(
                CLUSTER_INTERNAL_KEY_PATH.format(app_name, expected_cert_id),
                dut_engine,
                should_exist=True,
            )
        if expected_alt_cert_id:
            verify_file_exists_in_dut(
                CLUSTER_INTERNAL_ALTERNATE_CERT_PATH.format(app_name, expected_alt_cert_id),
                dut_engine,
                should_exist=True,
            )
            verify_file_exists_in_dut(
                CLUSTER_INTERNAL_ALTERNATE_KEY_PATH.format(app_name, expected_alt_cert_id),
                dut_engine,
                should_exist=True,
            )
        if expected_cacert_id:
            verify_file_exists_in_dut(
                CLUSTER_INTERNAL_CACERT_PATH.format(app_name, expected_cacert_id),
                dut_engine,
                should_exist=True,
            )


def wait_for_cluster_app_update(cluster: Cluster, engine: LinuxSshEngine):
    """Wait for cluster app state update to propagate."""
    with allure.step("wait for cluster app update"):
        ClusterTools.wait_for_apps_to_be_in_wanted_state(
            cluster,
            cluster_expected_state="enabled",
            nmx_c_expected_state="up",
            engine=engine,
        )
        time.sleep(1)


def verify_system_internal_has_empty_defaults():
    """Verify system internal show has default empty values."""
    verify_system_internal_show(
        expect_cert=Defaults.CERT,
        expect_cacert=Defaults.CACERT,
        expect_alt_cert=Defaults.ALTERNATE_CERTIFICATE,
        expect_encryption=Defaults.ENCRYPTION,
    )


def verify_cluster_app_internal_has_empty_defaults(app_name: str):
    """Verify cluster app internal show has default empty values."""
    verify_cluster_app_internal_show(
        app_name,
        expect_cert=Defaults.CERT,
        expect_cacert=Defaults.CACERT,
        expect_encryption=Defaults.ENCRYPTION,
        expect_alt_cert=Defaults.ALTERNATE_CERTIFICATE,
    )


def generate_internal_certs(engines: EnginesT, location_name: str, hostname: str) -> tuple[CertInfo, CertInfo]:
    certs_location = get_test_certs_dir_location(location_name, hostname)
    scp_player = get_scp_player(engines)
    certs_location, certs = setup_certs_for_tests(
        certs_dirname_prefix=certs_location,
        certs_names=["client", "server"],
        engines=engines,
        dut_hostname=hostname,
        scp_player=scp_player,
        dut_ip=engines.dut.ip,
        create_chain=False,
    )
    client_cert = certs[0]
    server_cert = certs[-1]
    return server_cert, client_cert


def import_internal_certs(engines: EnginesT, bridge_certs: list[CertInfo], bridge_ca_certs: list[CertInfo]) -> None:
    scp_player = get_scp_player(engines)

    with allure.step("import test certs"):
        import_certs_safely(bridge_certs, scp_player)
        import_cas_safely(bridge_ca_certs, scp_player)


def reset_cluster_app(cluster, app_name: str, engine: LinuxSshEngine, wait_time: int = 5) -> None:
    """
    Reset a cluster app's internal connections.

    Args:
        cluster: Cluster object
        app_name: Name of the app to reset (e.g., nmx-controller)
        engine: Engine to connect to
        wait_time: Seconds to wait after reset (kept for compatibility, unused)
    """
    with allure.step(f"Reset cluster app {app_name} internal connections"):
        app = cluster.apps.app_name[app_name]
        app.internal.connections.action_reset(dut_engine=engine).verify_result()
        wait_for_cluster_app_update(cluster, engine)


def rotate_system_internal_and_verify(
    system,
    cluster,
    app_name: str,
    dut_engine: LinuxSshEngine,
    cacert_name: str,
    current_cert: str,
    current_alt: str,
    encryption_mode: str,
    should_reset: bool = False,
) -> tuple[str, str]:
    """
    Rotate system internal certificate and verify connection.

    Args:
        system: System object
        cluster: Cluster object
        app_name: Name of the cluster app
        dut_engine: SSH engine to DUT
        cacert_name: CA certificate name
        current_cert: Current certificate name (before rotation)
        current_alt: Current alternate certificate name (before rotation)
        encryption_mode: Expected encryption mode
        should_reset: If we want to reset connection

    Returns:
        Tuple of (new_cert, new_alt) after rotation (swapped)
    """
    with allure.step("Rotate system internal certificate"):
        system.internal.certificate.action_rotate().verify_result()
        new_cert, new_alt = current_alt, current_cert
        with allure.step("Verify system cert swapped"):
            verify_system_internal_show(
                expect_cert=new_cert,
                expect_cacert=cacert_name,
                expect_alt_cert=new_alt,
                expect_encryption=encryption_mode,
            )
        if should_reset:
            reset_cluster_app(cluster, app_name, dut_engine)
            wait_for_cluster_app_update(cluster, dut_engine)
        verify_nv_bridge_has_connection(dut_engine, expect_connection=True)
    return new_cert, new_alt


def rotate_cluster_internal_and_verify(
    app,
    cluster,
    app_name: str,
    dut_engine: LinuxSshEngine,
    cacert_name: str,
    current_cert: str,
    current_alt: str,
    encryption_mode: str,
    should_reset: bool = False,
) -> tuple[str, str]:
    """
    Rotate cluster internal certificate and verify connection.

    Args:
        app: Cluster app object
        cluster: Cluster object
        app_name: Name of the cluster app
        dut_engine: SSH engine to DUT
        cacert_name: CA certificate name
        current_cert: Current certificate name (before rotation)
        current_alt: Current alternate certificate name (before rotation)
        encryption_mode: Expected encryption mode
        should_reset: If we want to reset connection

    Returns:
        Tuple of (new_cert, new_alt) after rotation (swapped)
    """
    with allure.step("Rotate cluster internal certificate"):
        app.internal.certificate.action_rotate().verify_result()
        new_cert, new_alt = current_alt, current_cert
        wait_for_cluster_app_update(cluster, dut_engine)
        with allure.step("Verify cluster cert swapped"):
            verify_cluster_app_internal_show(
                app_name,
                expect_cert=new_cert,
                expect_cacert=cacert_name,
                expect_alt_cert=new_alt,
                expect_encryption=encryption_mode,
            )
        if should_reset:
            reset_cluster_app(cluster, app_name, dut_engine)
            wait_for_cluster_app_update(cluster, dut_engine)
        verify_nv_bridge_has_connection(dut_engine, expect_connection=True)
    return new_cert, new_alt
