"""Cumulus lab: NV unset CLI coverage (SSIM ``Test_Otel_Mgmt_Vrf_Insecure_CLI_Coverage``)."""

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.telemetry.otel.cumulus.cli_unset_coverage import (
    apply_unset_changes,
    get_interface_telemetry_labels_applied,
    get_system_interface_stats_egress_tc_applied,
    require_cumulus_at_least,
    swp_interfaces_for_unset,
    unset_interface_histogram_counter,
    unset_interface_histogram_egress_tc,
    unset_interface_histogram_ingress_pg,
    unset_interface_histogram_latency_tc,
    unset_interface_label,
    unset_system_otlp_destination_port,
    unset_system_platform_stats_class,
    unset_system_platform_stats_class_platform_info,
    get_system_platform_stats_class_platform_info_applied,
    unset_system_telemetry_interface_stats_egress_tc,
    unset_system_telemetry_interface_stats_ingress_pg,
    unset_system_telemetry_label,
    unset_system_interface_stats_class_phy,
)

pytestmark = [
    pytest.mark.cumulus,
    pytest.mark.otel,
    pytest.mark.otel_unset,
    pytest.mark.skip_clear_config,
]


@pytest.fixture(autouse=True)
def _require_cli_coverage_baseline(otel_cli_coverage_baseline):
    """Module baseline from ``OtelMgmtVrfNoTLSConfig`` (see conftest)."""
    return otel_cli_coverage_baseline


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test01a_otlp_interface_unset_cli_validations(engines, test_api):
    """SSIM test01a: unset interface histogram ingress PG and egress TC."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.10.0")
    for iface in swp_interfaces_for_unset(engines.dut):
        for pg in ("0", "1", "2"):
            unset_interface_histogram_ingress_pg(engines.dut, iface, pg)
        for tc in ("0", "1", "6", "7"):
            unset_interface_histogram_egress_tc(engines.dut, iface, tc)
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test01b_otlp_interface_unset_cli_validations(engines, test_api):
    """SSIM test01b: unset interface histogram latency TC and counter."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.11.0")
    for iface in swp_interfaces_for_unset(engines.dut):
        for tc in ("0", "1", "2", "3", "4", "7"):
            unset_interface_histogram_latency_tc(engines.dut, iface, tc)
        unset_interface_histogram_counter(engines.dut, iface, "rx-byte")
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test01c_otlp_interface_unset_cli_validations(engines, test_api):
    """SSIM test01c: unset interface telemetry labels l1–l4."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.12.0")
    labels = ("mgmtVrfNoTls-l1", "mgmtVrfNoTls-l2", "mgmtVrfNoTls-l3", "mgmtVrfNoTls-l4")
    for iface in swp_interfaces_for_unset(engines.dut):
        for label in labels:
            unset_interface_label(engines.dut, iface, label)
    # SSIM queues label unsets without apply; test02 applies and verifies l5–l10 remain.


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test02_otlp_interface_unset_cli_validations(engines, test_api):
    """SSIM test02: unset label description then label; verify l5–l10 remain."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.12.0")
    labels = ("mgmtVrfNoTls-l1", "mgmtVrfNoTls-l2", "mgmtVrfNoTls-l3", "mgmtVrfNoTls-l4")
    ifaces = swp_interfaces_for_unset(engines.dut)
    for iface in ifaces:
        for label in labels:
            unset_interface_label(engines.dut, iface, label, key="description")
            unset_interface_label(engines.dut, iface, label)
    apply_unset_changes(engines.dut)

    expected = {
        f"mgmtVrfNoTls-l{i}": {"description": f"Management VRF Insecure Label-{i}"}
        for i in range(5, 11)
    }
    out = get_interface_telemetry_labels_applied(engines.dut, ifaces[0])
    assert out == expected, "nv unset interface telemetry label failed"


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test03a_otlp_system_unset_cli_validations(engines, otel_cli_coverage_baseline, test_api):
    """SSIM test03a: unset system interface-stats TC/PG and secondary destination port."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.10.0")
    for tc in ("0", "1", "4"):
        unset_system_telemetry_interface_stats_egress_tc(engines.dut, tc)
        apply_unset_changes(engines.dut)
        out = get_system_interface_stats_egress_tc_applied(engines.dut)
        assert str(tc) not in out, (
            "nv unset system telemetry interface-stats egress-buffer traffic-class failed"
        )
    unset_system_otlp_destination_port(
        engines.dut, otel_cli_coverage_baseline.secondary_ip
    )
    for pg in ("0", "5", "6", "7"):
        unset_system_telemetry_interface_stats_ingress_pg(engines.dut, pg)
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test03b_otlp_system_unset_cli_validations(engines, test_api):
    """SSIM test03b: unset system telemetry labels device-l1..l4."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.11.0")
    for label in ("device-l1", "device-l2", "device-l3", "device-l4"):
        unset_system_telemetry_label(engines.dut, label)
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test03c_otlp_system_unset_cli_validations(engines, test_api):
    """SSIM test03c: unset interface-stats class phy state; unset device labels."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.13.0")
    unset_system_interface_stats_class_phy(engines.dut, key="state", value="enabled")
    for label in ("device-l1", "device-l2", "device-l3", "device-l4"):
        unset_system_telemetry_label(engines.dut, label)
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test04a_otlp_system_unset_cli_validations(engines, test_api):
    """SSIM test04a: unset system telemetry interface-stats class phy."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.13.0")
    unset_system_interface_stats_class_phy(engines.dut)
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test04b_otlp_system_unset_cli_validations(engines, test_api):
    """SSIM test04b: unset system telemetry label description then label."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.12.0")
    for label in ("device-l1", "device-l2", "device-l3", "device-l4"):
        unset_system_telemetry_label(engines.dut, label, key="description")
        unset_system_telemetry_label(engines.dut, label)
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test05_otlp_system_unset_cli_validations(engines, test_api):
    """SSIM test05: unset platform-stats class cpu/disk/environment/file-system/memory."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.11.0")
    for platform_class in (
        "cpu",
        "disk",
        "environment-sensor",
        "file-system",
        "memory",
    ):
        unset_system_platform_stats_class(
            engines.dut, platform_class, key="sample-interval", value=""
        )
        unset_system_platform_stats_class(
            engines.dut, platform_class, key="state", value=""
        )
    apply_unset_changes(engines.dut)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test05a_otlp_system_unset_cli_validations(engines, test_api):
    """SSIM test05a: unset root platform-info sample-interval, state, then class."""
    TestToolkit.tested_api = test_api
    require_cumulus_at_least(engines.dut, "5.14.0")
    unset_system_platform_stats_class_platform_info(
        engines.dut, key="sample-interval", value=""
    )
    apply_unset_changes(engines.dut)
    out = get_system_platform_stats_class_platform_info_applied(engines.dut)
    assert out.get("sample-interval") == 60, (
        "nv unset system telemetry platform-stats class platform-info sample-interval failed"
    )
    unset_system_platform_stats_class_platform_info(engines.dut, key="state", value="")
    apply_unset_changes(engines.dut)
    out = get_system_platform_stats_class_platform_info_applied(engines.dut)
    assert out.get("state") == "enabled", (
        "nv unset system telemetry platform-stats class platform-info state failed"
    )
    unset_system_platform_stats_class_platform_info(engines.dut)
    apply_unset_changes(engines.dut)
    out = get_system_platform_stats_class_platform_info_applied(engines.dut)
    assert out == {"sample-interval": 60, "state": "enabled"}, (
        "nv unset system telemetry platform-stats class platform-info failed"
    )
