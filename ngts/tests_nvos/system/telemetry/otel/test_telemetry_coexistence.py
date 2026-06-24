"""Cumulus lab: OTEL/gNMI telemetry coexistence (SSIM ``test_telemetry_coexistence.py``)."""

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.telemetry.otel.cumulus import cache as telemetryCache
from ngts.tests_nvos.system.telemetry.otel.cumulus.coexistence import (
    coexistence_otel_exclude_metrics,
    gnmi_coexistence_cache_ready,
    skip_unless_gnmi_coexistence,
    validate_coexistence_otel_metrics,
    validate_coexistence_otel_time_gaps,
    validate_interface_broadcast_pkts_otel_cli,
    validate_interface_stats_time_gap,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_coexistence import (
    COMPONENT_GNMI_ATTRS,
    INTERFACE_QOS_GNMI_ATTRS,
    SMOKE_LLDP_ATTRS,
    SYSTEM_GNMI_ATTRS,
    discover_lldp_neighbor_context,
    discover_storage_component_name,
    validate_gnmi_sample_interval_per_timestamp,
    validate_xpath_coverage_per_timestamp,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.lab_topology import (
    discover_swp_interfaces_on_dut,
    resolve_cumulus_lab_interfaces_on_dut,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.data_collection import get_dut_hostname

pytestmark = [
    pytest.mark.cumulus,
    pytest.mark.otel,
    pytest.mark.co_existence,
]


# --- Test_Telemetry_Coexistence_Smoke (OtelMgmtVrfWithTLSConfig / mgmt secured) ---


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_smoke_01_validate_otel_metrics_collection(
    engines, coexistence_smoke_cache, test_api
):
    """SSIM ``Test_Telemetry_Coexistence_Smoke::test_01_validate_otel_metrics_collection``."""
    TestToolkit.tested_api = test_api
    validate_coexistence_otel_metrics(engines.dut, secured=True)


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_smoke_02_gnmi_sample_interval_from_collection(
    engines, coexistence_smoke_cache, test_api
):
    """SSIM smoke test_02 — gNMI BGP/LLDP per-timestamp sample interval adherence."""
    TestToolkit.tested_api = test_api
    skip_unless_gnmi_coexistence("gnmi_timing", context="smoke BGP/LLDP sample interval")
    timing = telemetryCache.get_data("gnmi_timing")
    assert isinstance(timing, dict), "GNMI timing data missing"
    if gnmi_coexistence_cache_ready("gnmi-series-bgp"):
        assert timing.get("bgp") is not None, "Missing GNMI timing entry for BGP"
        validate_gnmi_sample_interval_per_timestamp(
            models=("bgp",),
            sample_interval=4,
            tolerance=0.25,
        )
    if gnmi_coexistence_cache_ready("gnmi-series-lldp"):
        assert timing.get("lldp") is not None, "Missing GNMI timing entry for LLDP"
        validate_gnmi_sample_interval_per_timestamp(
            models=("lldp",),
            sample_interval=5,
            tolerance=0.25,
        )


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_smoke_03_validate_otel_time_gaps(
    engines, coexistence_smoke_cache, test_api
):
    """SSIM ``Test_Telemetry_Coexistence_Smoke::test_03_validate_otel_time_gaps``."""
    TestToolkit.tested_api = test_api
    validate_coexistence_otel_time_gaps()


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_smoke_04_gnmi_lldp_xpath_coverage_per_timestamp_strict(
    engines, coexistence_smoke_cache, test_api
):
    """SSIM smoke test_04 — strict LLDP xpath coverage per timestamp."""
    TestToolkit.tested_api = test_api
    skip_unless_gnmi_coexistence(
        "gnmi-series-lldp",
        context="smoke strict LLDP xpath coverage",
    )
    lab = resolve_cumulus_lab_interfaces_on_dut(engines.dut)
    lldp_ctx = discover_lldp_neighbor_context(engines.dut, preferred_iface=lab.test_iface)
    assert lldp_ctx is not None, "LLDP neighbor context missing on mlx lab"
    validate_xpath_coverage_per_timestamp(
        model="lldp",
        attrs=SMOKE_LLDP_ATTRS,
        populate_kwargs=lldp_ctx,
        series_key="gnmi-series-lldp",
        group_size=1,
    )


# --- Test_Telemetry_Interface_QoS_Validation_Coexistence (split pipeline mgmt) ---


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_interface_qos_01_gnmi_interface_xpath_coverage_per_timestamp(
    engines, coexistence_interface_qos_cache, test_api
):
    """SSIM Interface/QoS test_01 — gNMI interface xpath coverage."""
    TestToolkit.tested_api = test_api
    coexistence_interface_qos_cache.ensure_collected()
    with allure.step('Verify gNMI interface cache is populated'):
        skip_unless_gnmi_coexistence(
            "gnmi-series-interface",
            context="Interface/QoS xpath coverage",
        )
    with allure.step('Resolve lab interface for xpath population'):
        lab = resolve_cumulus_lab_interfaces_on_dut(engines.dut)
        allure.attach(lab.test_iface, 'test_iface')
    with allure.step('Validate interface xpath coverage per timestamp (group_size=2)'):
        validate_xpath_coverage_per_timestamp(
            model="interface",
            attrs=INTERFACE_QOS_GNMI_ATTRS,
            populate_kwargs={"interface": lab.test_iface},
            series_key="gnmi-series-interface",
            group_size=2,
        )


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_interface_qos_02_validate_otel_metrics_collection(
    engines, coexistence_interface_qos_cache, test_api
):
    """SSIM ``Test_Telemetry_Interface_QoS_Validation_Coexistence::test_02``."""
    TestToolkit.tested_api = test_api
    coexistence_interface_qos_cache.ensure_collected()
    validate_coexistence_otel_metrics(
        engines.dut,
        secured=False,
        exclude_metrics=coexistence_otel_exclude_metrics(),
    )


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_interface_qos_03_gnmi_interface_sample_interval_adherence(
    engines, coexistence_interface_qos_cache, test_api
):
    """SSIM Interface/QoS test_03 — gNMI interface sample-interval adherence."""
    TestToolkit.tested_api = test_api
    coexistence_interface_qos_cache.ensure_collected()
    skip_unless_gnmi_coexistence("gnmi-series-interface", context="Interface sample interval")
    validate_gnmi_sample_interval_per_timestamp(
        models=("interface",),
        sample_interval=5,
        tolerance=0.25,
    )


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_interface_qos_04_otel_interface_stats_time_gap_analysis(
    engines, coexistence_interface_qos_cache, test_api
):
    """SSIM Interface/QoS test_04 — interface_stats_gap threshold."""
    TestToolkit.tested_api = test_api
    coexistence_interface_qos_cache.ensure_collected()
    validate_interface_stats_time_gap()


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_interface_qos_05_interface_in_broadcast_pkts(
    engines, coexistence_interface_qos_cache, test_api
):
    """SSIM Interface/QoS test_05 — OTEL vs CLI for in_broadcast_pkts (GNMI portion skipped on mlx)."""
    TestToolkit.tested_api = test_api
    coexistence_interface_qos_cache.ensure_collected()
    lab = resolve_cumulus_lab_interfaces_on_dut(engines.dut, get_dut_hostname(engines.dut))
    swps = discover_swp_interfaces_on_dut(engines.dut)
    iface = lab.test_iface if lab.test_iface in swps else (swps[0] if swps else lab.test_iface)
    validate_interface_broadcast_pkts_otel_cli(engines.dut, interface=iface)


# --- Test_Telemetry_Component_System_Validation_Coexistence ---


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_component_system_01_gnmi_system_xpath_coverage_per_timestamp(
    engines, coexistence_component_system_cache, test_api
):
    """SSIM Component/System test_01 — gNMI system xpath coverage."""
    TestToolkit.tested_api = test_api
    skip_unless_gnmi_coexistence(
        "gnmi-series-system",
        context="Component/System system xpath coverage",
    )
    validate_xpath_coverage_per_timestamp(
        model="system",
        attrs=SYSTEM_GNMI_ATTRS,
        populate_kwargs={"mount_point": "/"},
        series_key="gnmi-series-system",
        group_size=2,
    )


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_component_system_02_gnmi_component_xpath_coverage_per_timestamp(
    engines, coexistence_component_system_cache, test_api
):
    """SSIM Component/System test_02 — gNMI component xpath coverage."""
    TestToolkit.tested_api = test_api
    skip_unless_gnmi_coexistence(
        "gnmi-series-component",
        context="Component/System component xpath coverage",
    )
    component_name = discover_storage_component_name(engines.dut)
    validate_xpath_coverage_per_timestamp(
        model="component",
        attrs=COMPONENT_GNMI_ATTRS,
        populate_kwargs={"component_name": component_name},
        series_key="gnmi-series-component",
        group_size=2,
    )


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_component_system_03_validate_otel_metrics_collection(
    engines, coexistence_component_system_cache, test_api
):
    """SSIM ``Test_Telemetry_Component_System_Validation_Coexistence::test_03``."""
    TestToolkit.tested_api = test_api
    excludes = coexistence_otel_exclude_metrics() + [
        "nvswitch_dot1x_interface_info",
        "nvswitch_dot1x_ipv6_profile_info",
        "nvswitch_dot1x_ipv6_profile_property_info",
        "nvswitch_dot1x_ipv6_profile_summary",
        "nvswitch_dot1x_radius_client_info",
        "nvswitch_dot1x_radius_server_info",
        "nvswitch_dot1x_reauth_timeouts",
        "nvswitch_dot1x_supplicant_eapol_counters",
        "nvswitch_dot1x_supplicant_status",
        "nvswitch_dot1x_supplicant_summary",
        "nvswitch_dot1x_system_info",
    ]
    validate_coexistence_otel_metrics(
        engines.dut,
        secured=False,
        exclude_metrics=excludes,
    )
