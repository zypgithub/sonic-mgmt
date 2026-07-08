"""Pytest plumbing for the NVOS OTEL telemetry test suite.

Platform note: never call ``system.telemetry.set(state)`` or ``export.otlp.set``
directly for master enable — use :func:`~ngts.tests_nvos.system.telemetry.otel.helpers.stage_telemetry_master_state`
and :func:`~ngts.tests_nvos.system.telemetry.otel.helpers.apply_telemetry_configuration`
with ``suite.is_nvos`` (Cumulus: ``telemetry state``; NVOS: ``export otlp state``).
"""

import logging

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, TelemetryConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.telemetry.otel.cumulus import cache as telemetry_cache
from ngts.tests_nvos.system.telemetry.otel.cumulus.constants import CumulusOtelConst
from ngts.tests_nvos.system.telemetry.otel.helpers import (
    OtelSuiteContext,
    is_nvos_dut,
    setup_otel_suite,
    setup_otel_suite_secured,
    teardown_otel_suite,
)

logger = logging.getLogger(__name__)


def _ensure_nvue_api() -> None:
    """Module fixtures run before function-scoped ``test_api``; pin NVUE for setup."""
    TestToolkit.tested_api = ApiType.NVUE


@pytest.fixture(scope="module")
def otel_telemetry_cache():
    """Shared telemetry cache for Cumulus OTLP tests (test01/test05)."""
    telemetry_cache.clear_data()
    yield telemetry_cache
    telemetry_cache.clear_data()


@pytest.fixture(scope="module")
def otel_suite(engines, devices) -> OtelSuiteContext:
    """OTEL collectors + DUT OTLP (default export VRF)."""
    _ensure_nvue_api()
    suite = setup_otel_suite(engines, is_nvos=is_nvos_dut(devices))
    try:
        yield suite
    finally:
        teardown_otel_suite(engines, suite)


@pytest.fixture(scope="module")
def otel_suite_mgmt(engines, devices) -> OtelSuiteContext:
    """OTEL insecure suite for the ported mgmt-VRF tests.

    Cumulus exports over the ``mgmt`` VRF (sonic-mgmt / HA reachability). NVOS has
    no ``mgmt`` VRF, so it falls back to the ``default`` export VRF.
    """
    _ensure_nvue_api()
    is_nvos = is_nvos_dut(devices)
    export_vrf = (
        TelemetryConsts.Defaults.EXPORT_VRF
        if is_nvos
        else CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT
    )
    suite = setup_otel_suite(engines, export_vrf=export_vrf, is_nvos=is_nvos)
    try:
        yield suite
    finally:
        teardown_otel_suite(engines, suite)


@pytest.fixture(scope="module")
def otel_suite_secured(engines, devices) -> OtelSuiteContext:
    """OTEL suite with TLS on default export VRF (SSIM ``OtelDefaultVrfWithTLSConfig``)."""
    _ensure_nvue_api()
    suite = setup_otel_suite_secured(
        engines,
        export_vrf=CumulusOtelConst.TELEMETRY_EXPORT_VRF_DEFAULT,
        default_vrf_grpc_certificate=True,
        is_nvos=is_nvos_dut(devices),
    )
    try:
        yield suite
    finally:
        teardown_otel_suite(engines, suite)


@pytest.fixture(scope="module")
def otel_suite_mgmt_secured(engines, devices) -> OtelSuiteContext:
    """OTEL TLS suite for the ported secured mgmt-VRF tests.

    Cumulus uses the ``mgmt`` VRF with a destination certificate. NVOS has no
    ``mgmt`` VRF, so it exports over the ``default`` VRF with a gRPC-level
    certificate (same posture as :func:`otel_suite_secured`).
    """
    _ensure_nvue_api()
    is_nvos = is_nvos_dut(devices)
    if is_nvos:
        suite = setup_otel_suite_secured(
            engines,
            export_vrf=TelemetryConsts.Defaults.EXPORT_VRF,
            default_vrf_grpc_certificate=True,
            is_nvos=True,
        )
    else:
        suite = setup_otel_suite_secured(
            engines,
            export_vrf=CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT,
            default_vrf_grpc_certificate=False,
            enable_routing=False,
            enable_interface_histogram=True,
            is_nvos=False,
        )
    try:
        yield suite
    finally:
        teardown_otel_suite(engines, suite)


@pytest.fixture(scope="module")
def otel_mgmt_insecure_validation_cache(engines, otel_suite_mgmt, tmp_path_factory):
    """``Test_Otel_Mgmt_Vrf_Insecure`` shared OTLP + CLI cache (test02a–test03e)."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.data_collection import (
        collect_and_cache_mgmt_vrf_insecure_validation_session,
    )

    cur_dir = str(tmp_path_factory.mktemp("otel_mgmt_insecure_validation"))
    collector_ips = (otel_suite_mgmt.primary_ip, otel_suite_mgmt.secondary_ip)
    collect_and_cache_mgmt_vrf_insecure_validation_session(
        engines.dut,
        otel_suite_mgmt.primary,
        cur_dir,
        collector_ips=collector_ips,
    )
    yield cur_dir


def _teardown_deferred_gnmi_session(dut, gnmi_session) -> None:
    """SSIM ``post_suite_hook`` parity: remove grpc-tunnel after coexistence tests."""
    if gnmi_session is None:
        return
    from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_coexistence import (
        teardown_gnmi_coexistence_session,
    )

    teardown_gnmi_coexistence_session(dut, gnmi_session)


@pytest.fixture(scope="module")
def coexistence_smoke_cache(engines, otel_suite_mgmt_secured, tmp_path_factory):
    """``Test_Telemetry_Coexistence_Smoke`` OTEL cache (secured mgmt VRF)."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.coexistence import (
        collect_coexistence_smoke_cache,
    )

    cur_dir = str(tmp_path_factory.mktemp("coexistence_smoke"))
    collect_result = collect_coexistence_smoke_cache(
        engines.dut,
        otel_suite_mgmt_secured.primary,
        cur_dir,
        sonic_mgmt=engines.sonic_mgmt,
        defer_gnmi_teardown=True,
    )
    yield cur_dir
    _teardown_deferred_gnmi_session(engines.dut, collect_result.gnmi_session)


@pytest.fixture(scope="module")
def coexistence_interface_qos_cache(engines, otel_suite_mgmt, tmp_path_factory):
    """Lazy Interface/QoS bundle; call ``ensure_collected()`` from test body for Allure nesting."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.coexistence import (
        CoexistenceInterfaceQosBundle,
    )

    bundle = CoexistenceInterfaceQosBundle(
        cur_dir=str(tmp_path_factory.mktemp("coexistence_interface_qos")),
        dut=engines.dut,
        collector=otel_suite_mgmt.primary,
        sonic_mgmt=engines.sonic_mgmt,
        collector_ips=(otel_suite_mgmt.primary_ip, otel_suite_mgmt.secondary_ip),
    )
    yield bundle
    bundle.teardown()


@pytest.fixture(scope="module")
def coexistence_component_system_cache(engines, otel_suite_mgmt, tmp_path_factory):
    """``Test_Telemetry_Component_System_Validation_Coexistence`` OTEL cache."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.coexistence import (
        collect_coexistence_component_system_cache,
    )

    cur_dir = str(tmp_path_factory.mktemp("coexistence_component_system"))
    collector_ips = (otel_suite_mgmt.primary_ip, otel_suite_mgmt.secondary_ip)
    collect_result = collect_coexistence_component_system_cache(
        engines.dut,
        otel_suite_mgmt.primary,
        cur_dir,
        collector_ips=collector_ips,
        sonic_mgmt=engines.sonic_mgmt,
        defer_gnmi_teardown=True,
    )
    yield cur_dir
    _teardown_deferred_gnmi_session(engines.dut, collect_result.gnmi_session)


@pytest.fixture(scope="module")
def otel_cli_coverage_baseline(engines, otel_suite_mgmt) -> OtelSuiteContext:
    """``OtelMgmtVrfNoTLSConfig`` NVUE baseline for unset CLI coverage tests."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.cli_unset_coverage import (
        apply_otel_cli_coverage_baseline,
    )

    _ensure_nvue_api()
    collector_ips = (otel_suite_mgmt.primary_ip, otel_suite_mgmt.secondary_ip)
    apply_otel_cli_coverage_baseline(engines.dut, collector_ips)
    try:
        yield otel_suite_mgmt
    finally:
        _ensure_nvue_api()
        apply_otel_cli_coverage_baseline(engines.dut, collector_ips)
