"""Coexistence telemetry helpers (SSIM ``test_telemetry_coexistence.py`` mlx-lab parity)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.tests_nvos.system.telemetry.otel.cumulus import cache as telemetryCache
from ngts.tests_nvos.system.telemetry.otel.cumulus.catalog import (
    supported_metrics_for_secured_validation,
    supported_metrics_for_test01_validation,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.constants import CumulusOtelConst
from ngts.tests_nvos.system.telemetry.otel.cumulus.data_collection import (
    collect_and_cache_secured_otel_session,
    collect_cli_mgmt_vrf_session_data,
    collect_telemetry_data,
    cumulus_otel_artifact_path,
    get_cp_stat_sx_api_cli,
    get_dut_hostname,
    parse_telemetry_and_cache,
    truncate_collector_export,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.helpers import dut_root_on_nvme_storage
from ngts.tests_nvos.system.telemetry.otel.cumulus.lab_topology import (
    resolve_cumulus_lab_interfaces_on_dut,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.sample_interval import (
    check_metrics_within_range,
    get_dut_os_info,
    timegap_analysis_v2,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.split_pipeline import (
    apply_split_pipeline_test01_stats_group,
    prepare_split_pipeline_insecure_pre_run,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.validations import OtelDataValidations
from ngts.tests_nvos.system.telemetry.otel.otel_collector import OtelCollector

logger = logging.getLogger(__name__)


@dataclass
class CoexistenceCollectResult:
    """OTEL cache payload plus optional deferred gNMI session for module teardown."""

    otel_payload: Dict[str, Any]
    gnmi_session: Any = None


@dataclass
class CoexistenceInterfaceQosBundle:
    """Module-scoped lazy collector: run ``ensure_collected()`` from test body for Allure nesting."""

    cur_dir: str
    dut: Any
    collector: OtelCollector
    sonic_mgmt: Any
    collector_ips: Tuple[str, str]
    _collected: bool = False
    _gnmi_session: Any = None

    def ensure_collected(self, *, wait_sec: Optional[int] = None) -> None:
        """Idempotent OTEL+gNMI cache build; steps log under the active test."""
        if wait_sec is None:
            wait_sec = COEXISTENCE_INTERFACE_QOS_COLLECT_WAIT_SEC
        if self._collected:
            with allure.step('Reuse Interface/QoS coexistence cache (module singleton)'):
                try:
                    series = telemetryCache.get_data('gnmi-series-interface')
                    ts_count = len(series) if isinstance(series, dict) else 0
                except KeyError:
                    ts_count = 0
                allure.attach(
                    'cur_dir=%s gnmi_timestamps=%d' % (self.cur_dir, ts_count),
                    'interface_qos_cache_reuse',
                )
            return

        with allure.step('Build Interface/QoS coexistence OTEL+gNMI cache (first collect this module)'):
            result = collect_coexistence_interface_qos_cache(
                self.dut,
                self.collector,
                self.cur_dir,
                collector_ips=self.collector_ips,
                sonic_mgmt=self.sonic_mgmt,
                wait_sec=wait_sec,
                defer_gnmi_teardown=True,
            )
            self._gnmi_session = result.gnmi_session
            self._collected = True

    def teardown(self) -> None:
        if not self._collected or self._gnmi_session is None:
            return
        with allure.step('Teardown deferred Interface/QoS gNMI coexistence session'):
            from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_coexistence import (
                teardown_gnmi_coexistence_session,
            )

            teardown_gnmi_coexistence_session(self.dut, self._gnmi_session)
        self._gnmi_session = None
        self._collected = False


# SSIM ``Test_Telemetry_Coexistence_Smoke`` / Interface QoS shared excludes.
COEXISTENCE_OTEL_EXCLUDE_BASE: Tuple[str, ...] = (
    "nvswitch_ar_congestion_changes",
    "nvswitch_srv6_in_pkts",
    "nvswitch_srv6_no_sid_drops",
    "nvswitch_qos_trimmed_unicast_pkts",
    "nvswitch_interface_trimmed_unicast_pkts",
    "nvswitch_interface_trimmed_tx_unicast_pkts",
    "nvswitch_interface_tc_trimmed_unicast_pkts",
    "nvswitch_acl_set_ipv4_info",
    "nvswitch_acl_set_ipv6_info",
    "nvswitch_acl_set_l4_info",
    "nvswitch_acl_set_l2_info",
    "nvswitch_acl_interface_matched_pkts",
    "nvswitch_acl_interface_matched_bytes",
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
    "scrape_duration_seconds",
    "scrape_samples_post_metric_relabeling",
    "scrape_samples_scraped",
    "scrape_series_added",
    "up",
)

COEXISTENCE_OTEL_EXCLUDE_BGP_PEER: Tuple[str, ...] = (
    "nvrouting_bgp_peer_as",
    "nvrouting_bgp_peer_fsm_established_transitions",
    "nvrouting_bgp_peer_graceful_shutdown",
    "nvrouting_bgp_peer_info",
    "nvrouting_bgp_peer_last_established",
    "nvrouting_bgp_peer_local_as",
    "nvrouting_bgp_peer_rib_adj_in",
    "nvrouting_bgp_peer_rib_adj_in_installed",
    "nvrouting_bgp_peer_rib_adj_out_advertised",
    "nvrouting_bgp_peer_rx_updates",
    "nvrouting_bgp_peer_socket_in_queue",
    "nvrouting_bgp_peer_socket_out_queue",
    "nvrouting_bgp_peer_state",
    "nvrouting_bgp_peer_total_msgs_recvd",
    "nvrouting_bgp_peer_total_msgs_sent",
    "nvrouting_bgp_peer_tx_updates",
)

COEXISTENCE_SMOKE_COLLECT_WAIT_SEC = 150
COEXISTENCE_INTERFACE_QOS_COLLECT_WAIT_SEC = 120

# SSIM smoke ``test_03_validate_otel_time_gaps`` expected gaps (NGTS ``timegap_analysis_v2`` keys).
COEXISTENCE_SMOKE_TIME_GAPS: Dict[str, float] = {
    "histogram_gap": 1.1,
    "interface_stats_gap": 2.0,
    "control_stats_gap": 1.0,
    "platf_cpu_gap": 60.0,
    "platf_mem_gap": 60.0,
    "platf_file_gap": 60.0,
    "platf_envir_gap": 60.0,
    "platf_disk_gap": 60.0,
    "buffer_gap": 1.0,
    "phy_gap": 2.0,
    "frr_gap": 30.0,
    "lldp_gap": 5.0,
    "systemd_gap": 60.0,
    "ar_gap": 30.0,
}

INTERFACE_GNMI_TO_OTEL_METRIC: Dict[str, str] = {
    "in_broadcast_pkts": "nvswitch_interface_ether_stats_broadcast_pkts",
    "in_multicast_pkts": "nvswitch_interface_ether_stats_multicast_pkts",
    "in_octets": "nvswitch_interface_ether_stats_octets",
    "in_errors": "nvswitch_interface_if_in_errors",
}


def coexistence_otel_exclude_metrics(*, include_bgp_peer: bool = True) -> List[str]:
    """Deduped exclude list for Interface/QoS and Component/System suites."""
    combined: List[str] = list(COEXISTENCE_OTEL_EXCLUDE_BASE)
    if include_bgp_peer:
        combined.extend(COEXISTENCE_OTEL_EXCLUDE_BGP_PEER)
    seen = set()
    out: List[str] = []
    for name in combined:
        if name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _append_nvme_excludes(exclude: List[str], dut) -> List[str]:
    if dut_root_on_nvme_storage(dut):
        exclude.extend(
            [
                "node_disk_ata_rotation_rate_rpm",
                "node_disk_ata_write_cache",
                "node_disk_ata_write_cache_enabled",
                "node_cpu_core_throttles_total",
                "node_cpu_package_throttles_total",
            ]
        )
    return exclude


def gnmi_coexistence_cache_ready(series_key: str) -> bool:
    """True when gNMI series data was populated (SSIM ``collect_telemetry`` gnmi_jobs)."""
    try:
        series = telemetryCache.get_data(series_key)
    except KeyError:
        return False
    return isinstance(series, dict) and bool(series)


def skip_unless_gnmi_coexistence(series_key: str, *, context: str) -> None:
    if not gnmi_coexistence_cache_ready(series_key):
        pytest.skip(
            'gNMI coexistence cache %r missing for %s '
            '(no grpc-tunnel subscription data: check LLDP/BGP neighbor or gnmic on sonic-mgmt)'
            % (series_key, context)
        )


def assert_telemetry_cache_has_data(
    cache_keys: Sequence[Tuple[str, str]],
    *,
    context: str = '',
) -> None:
    """SSIM ``assert_telemetry_cache_has_data`` parity — hard-fail when cache keys are empty."""
    missing = []
    for label, key in cache_keys:
        try:
            data = telemetryCache.get_data(key)
        except KeyError:
            data = None
        if not data:
            missing.append('%s (%s)' % (label, key))
    if missing:
        prefix = 'telemetry cache missing data'
        if context:
            prefix += ' [%s]' % context
        pytest.fail('%s: %s' % (prefix, '; '.join(missing)))


def validate_coexistence_otel_metrics(
    dut,
    *,
    secured: bool = False,
    exclude_metrics: Optional[Iterable[str]] = None,
) -> None:
    """SSIM ``test_*_validate_otel_metrics_collection`` parity."""
    otel_data = telemetryCache.get_data("otel")
    metrics_timestamps = (otel_data or {}).get("metrics_timestamps")
    assert metrics_timestamps is not None, "metrics_timestamps missing from OTEL cache"

    hostname = get_dut_hostname(dut)
    excludes = list(exclude_metrics or coexistence_otel_exclude_metrics())
    excludes = _append_nvme_excludes(excludes, dut)

    if secured:
        total_metrics = supported_metrics_for_secured_validation(dut)
    else:
        total_metrics = supported_metrics_for_test01_validation(dut)

    otel_data_val = OtelDataValidations()
    with allure.step("Validate collected metrics (coexistence)"):
        otel_data_val.validate_collected_metrics(
            metrics_timestamps,
            hostname,
            total_metrics=total_metrics,
            exclude_metrics=excludes,
        )
        otel_data_val.validate_collected_metrics_attributes_count(
            metrics_timestamps,
            hostname,
            total_metrics=total_metrics,
            exclude_metrics=excludes,
        )


def validate_coexistence_otel_time_gaps(
    expected: Optional[Dict[str, float]] = None,
    *,
    tolerance: float = 0.25,
) -> None:
    """SSIM smoke ``test_03_validate_otel_time_gaps`` using cached ``time_gaps``."""
    otel_data = telemetryCache.get_data("otel")
    assert isinstance(otel_data, dict) and "time_gaps" in otel_data, (
        "OTEL time_gaps missing in cache; collection must set include_time_gaps=True"
    )
    actual = otel_data["time_gaps"]
    exp = dict(expected or COEXISTENCE_SMOKE_TIME_GAPS)
    with allure.step("Validate OTEL sample-interval time gaps (coexistence)"):
        check_metrics_within_range(exp, actual)


def validate_interface_stats_time_gap(*, max_gap: float = 4.0) -> None:
    """SSIM Interface/QoS ``test_04_otel_interface_stats_time_gap_analysis``."""
    time_gaps = telemetryCache.get_data("otel").get("time_gaps")
    assert time_gaps is not None, "time_gaps not available in OTEL cache"
    gap = time_gaps.get("interface_stats_gap")
    assert gap is not None, "interface_stats_gap not present in time_gaps"
    assert gap <= max_gap, f"Time gap analysis failed for Interface metrics: {gap}"


def validate_interface_broadcast_pkts_otel_cli(
    dut,
    *,
    interface: str,
    tolerance_percent: float = 20.0,
) -> None:
    """OTEL vs CLI for ``in_broadcast_pkts`` (SSIM test_05 OTEL portion only)."""
    metric = INTERFACE_GNMI_TO_OTEL_METRIC["in_broadcast_pkts"]
    otel_intf_stats = telemetryCache.get_data("otel").get("intf_stats") or {}
    cli_ingress = telemetryCache.get_data("cli").get("ingress_stats") or {}
    lab = resolve_cumulus_lab_interfaces_on_dut(dut, get_dut_hostname(dut))

    otel_data_val = OtelDataValidations()
    if not otel_intf_stats:
        pytest.skip("intf_stats missing; interface OTEL export not present in cache")

    attr_key = ("interface", interface,) + lab.labels
    if metric not in otel_intf_stats:
        pytest.skip(f"{metric} not in OTEL export on mlx lab")

    series = otel_intf_stats[metric]
    matched_key = None
    for key in series:
        if isinstance(key, tuple) and len(key) >= 2 and key[1] == interface:
            matched_key = key
            break
    if matched_key is None:
        pytest.skip(f"{metric} has no samples for interface {interface!r}")

    from statistics import mean

    d_otel = round(mean(series[matched_key]))
    ingress = cli_ingress.get(interface, {})
    pg0 = ingress.get("0", ingress) if isinstance(ingress, dict) else {}
    d_cli = int(pg0.get("rx-broadcast", pg0.get("broadcast", 0)) or 0)

    deviation = otel_data_val.get_percentage_deviation(d_cli, d_otel)
    if deviation > tolerance_percent:
        pytest.fail(
            f"{metric} OTEL vs CLI failed: otel={d_otel}, cli={d_cli}, "
            f"deviation={deviation:.1f}% (max {tolerance_percent}%)"
        )


def _enable_interface_qos_coexistence_exports(dut) -> None:
    """NVUE exports enabled in SSIM ``build_interface_telemetry_cache`` (no BGP peers on mlx)."""
    cmds = [
        "nv set system telemetry router export state enabled",
        "nv set system telemetry acl-stats export state enabled",
        "nv set system telemetry acl-stats class acl-set state enabled",
        "nv set system telemetry lldp export state enabled",
        "nv set system telemetry ai-ethernet-stats export state enabled",
        "nv set system telemetry interface-stats class phy state enabled",
        "nv set system telemetry software-stats systemd export state enabled",
        "nv set system telemetry software-stats systemd process-level enabled",
        "nv set system telemetry router bgp export state enabled",
        "nv set system telemetry router rib export state enabled",
        "nv set system telemetry buffer-stats export state enabled",
    ]
    with allure.step("Enable coexistence telemetry exports (Interface/QoS)"):
        for cmd in cmds:
            dut.run_cmd(cmd, validate=False)
        dut.run_cmd("nv config apply -y", validate=True)


def collect_coexistence_smoke_cache(
    dut,
    collector: OtelCollector,
    cur_dir: str,
    *,
    sonic_mgmt=None,
    vrf: str = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT,
    wait_sec: int = COEXISTENCE_SMOKE_COLLECT_WAIT_SEC,
    cleanup_session: bool = True,
    defer_gnmi_teardown: bool = False,
) -> CoexistenceCollectResult:
    """``Test_Telemetry_Coexistence_Smoke`` OTEL + gNMI (``OtelMgmtVrfWithTLSConfig``)."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_coexistence import (
        build_smoke_gnmi_jobs,
        run_gnmi_with_parallel_work,
    )

    telemetryCache.clear_data()
    gnmi_jobs = build_smoke_gnmi_jobs(dut, duration_sec=wait_sec)

    def _collect_otlp() -> Dict[str, Any]:
        return collect_and_cache_secured_otel_session(
            dut,
            collector,
            cur_dir,
            vrf=vrf,
            wait_sec=wait_sec,
            cleanup_session=cleanup_session,
        )

    gnmi_session = None
    if gnmi_jobs and sonic_mgmt is not None:
        otel_holder: Dict[str, Any] = {}

        def _otlp_and_store():
            otel_holder['payload'] = _collect_otlp()

        gnmi_session = run_gnmi_with_parallel_work(
            dut,
            sonic_mgmt,
            gnmi_jobs,
            _otlp_and_store,
            defer_teardown=defer_gnmi_teardown,
        )
        otel_payload = otel_holder['payload']
    else:
        if gnmi_jobs and sonic_mgmt is None:
            logger.warning('sonic_mgmt not provided; skipping smoke gNMI collection')
        otel_payload = _collect_otlp()

    artifact_path = cumulus_otel_artifact_path(cur_dir)
    hostname = get_dut_hostname(dut)
    otel_payload["time_gaps"] = timegap_analysis_v2(
        artifact_path,
        hostname,
        os_info=get_dut_os_info(dut),
    )
    telemetryCache.add_data("otel", otel_payload)
    return CoexistenceCollectResult(otel_payload=otel_payload, gnmi_session=gnmi_session)


def collect_coexistence_interface_qos_cache(
    dut,
    collector: OtelCollector,
    cur_dir: str,
    *,
    collector_ips: tuple[str, str],
    sonic_mgmt=None,
    wait_sec: int = COEXISTENCE_INTERFACE_QOS_COLLECT_WAIT_SEC,
    defer_gnmi_teardown: bool = False,
) -> CoexistenceCollectResult:
    """``Test_Telemetry_Interface_QoS_Validation_Coexistence`` OTEL + gNMI cache."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_coexistence import (
        build_interface_qos_gnmi_jobs,
        run_gnmi_with_parallel_work,
    )

    telemetryCache.clear_data()
    primary_collector_ip = collector_ips[0]
    with allure.step('Prepare split-pipeline mgmt VRF OTEL (test01 stats-group)'):
        prepare_split_pipeline_insecure_pre_run(dut)
        apply_split_pipeline_test01_stats_group(dut, primary_collector_ip)
        _enable_interface_qos_coexistence_exports(dut)

    vrf = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT
    cp_stats_pre = get_cp_stat_sx_api_cli(dut)
    gnmi_jobs = build_interface_qos_gnmi_jobs(dut, duration_sec=wait_sec)
    otel_holder: Dict[str, Any] = {}

    def _collect_otlp_and_cli():
        with allure.step('Collect OTLP export and CLI baseline (parallel with gNMI)'):
            truncate_collector_export(collector)
            collect_telemetry_data(dut, collector, vrf, wait_sec, None, cur_dir)
            artifact_path = cumulus_otel_artifact_path(cur_dir)
            hostname = get_dut_hostname(dut)
            otel_holder['payload'] = parse_telemetry_and_cache(
                OtelDataValidations(),
                artifact_path=artifact_path,
                hostname=hostname,
                include_time_gaps=True,
                dut=dut,
            )
            otel_holder['cli'] = collect_cli_mgmt_vrf_session_data(dut, cp_stats_pre=cp_stats_pre)

    gnmi_session = None
    collect_result = None
    try:
        if gnmi_jobs and sonic_mgmt is not None:
            with allure.step(
                'Run gNMI dial-out + OTLP in parallel (wait_sec=%d, jobs=%d)'
                % (wait_sec, len(gnmi_jobs))
            ):
                gnmi_session = run_gnmi_with_parallel_work(
                    dut,
                    sonic_mgmt,
                    gnmi_jobs,
                    _collect_otlp_and_cli,
                    defer_teardown=defer_gnmi_teardown,
                )
        else:
            _collect_otlp_and_cli()

        with allure.step('Assert telemetry cache has OTEL + gNMI interface series'):
            telemetryCache.add_data('cli', otel_holder['cli'])
            assert_telemetry_cache_has_data(
                [
                    ('OTEL', 'otel'),
                    ('GNMI interface series', 'gnmi-series-interface'),
                ],
                context='Interface/QoS coexistence',
            )
        collect_result = CoexistenceCollectResult(
            otel_payload=otel_holder['payload'],
            gnmi_session=gnmi_session,
        )
        return collect_result
    finally:
        if collect_result is None and gnmi_session is not None and defer_gnmi_teardown:
            from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_coexistence import (
                teardown_gnmi_coexistence_session,
            )

            teardown_gnmi_coexistence_session(dut, gnmi_session)


def collect_coexistence_component_system_cache(
    dut,
    collector: OtelCollector,
    cur_dir: str,
    *,
    collector_ips: tuple[str, str],
    sonic_mgmt=None,
    wait_sec: int = COEXISTENCE_INTERFACE_QOS_COLLECT_WAIT_SEC,
    defer_gnmi_teardown: bool = False,
) -> CoexistenceCollectResult:
    """``Test_Telemetry_Component_System_Validation_Coexistence`` OTEL + gNMI cache."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_coexistence import (
        build_component_system_gnmi_jobs,
        run_gnmi_with_parallel_work,
    )

    telemetryCache.clear_data()
    primary_collector_ip = collector_ips[0]
    prepare_split_pipeline_insecure_pre_run(dut)
    apply_split_pipeline_test01_stats_group(dut, primary_collector_ip)
    _enable_interface_qos_coexistence_exports(dut)

    vrf = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT
    cp_stats_pre = get_cp_stat_sx_api_cli(dut)
    gnmi_jobs = build_component_system_gnmi_jobs(dut, duration_sec=wait_sec)
    otel_holder: Dict[str, Any] = {}

    def _collect_otlp_and_cli():
        truncate_collector_export(collector)
        collect_telemetry_data(dut, collector, vrf, wait_sec, None, cur_dir)
        artifact_path = cumulus_otel_artifact_path(cur_dir)
        hostname = get_dut_hostname(dut)
        otel_holder['payload'] = parse_telemetry_and_cache(
            OtelDataValidations(),
            artifact_path=artifact_path,
            hostname=hostname,
            include_time_gaps=True,
            dut=dut,
        )
        otel_holder['cli'] = collect_cli_mgmt_vrf_session_data(dut, cp_stats_pre=cp_stats_pre)

    gnmi_session = None
    if gnmi_jobs and sonic_mgmt is not None:
        gnmi_session = run_gnmi_with_parallel_work(
            dut,
            sonic_mgmt,
            gnmi_jobs,
            _collect_otlp_and_cli,
            defer_teardown=defer_gnmi_teardown,
        )
    else:
        _collect_otlp_and_cli()

    telemetryCache.add_data('cli', otel_holder['cli'])
    return CoexistenceCollectResult(
        otel_payload=otel_holder['payload'],
        gnmi_session=gnmi_session,
    )
