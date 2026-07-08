"""Split-pipeline OTLP stats-group configuration (SSIM ``OtelSplitPipelineMgmtVrf*``)."""

from __future__ import annotations

import logging
import time
import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import TelemetryConsts
from ngts.tests_nvos.system.telemetry.otel.cumulus.constants import CumulusOtelConst
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.telemetry.otel.cumulus.data_collection import (
    ensure_asic_monitor_running,
    get_dut_hostname,
    restart_asic_monitor,
    restart_nvtelemetry,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.helpers import (
    _enable_histogram_root,
    enable_cumulus_lab_interface_histogram,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.sample_interval import (
    verify_metrics_sample_interval_server1,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.telemetry_health import (
    assert_otlp_session_established,
    cleanup_otlp_export_session,
    verify_otelcol_server_active,
    verify_otlp_client_active,
)
from ngts.tests_nvos.system.telemetry.otel.otel_collector import OtelCollector

logger = logging.getLogger(__name__)

_ENABLED = TelemetryConsts.State.ENABLED.value
_STATS_GROUP = CumulusOtelConst.SPLIT_PIPELINE_STATS_GROUP_ID


def _nv_apply(dut) -> None:
    dut.run_cmd("nv config apply -y", validate=True)
    time.sleep(10)


def _ensure_stats_group(dut, stats_group_id: str) -> None:
    dut.run_cmd(
        f"nv set system telemetry stats-group {stats_group_id}",
        validate=True,
    )


def apply_split_pipeline_test01_stats_group(
    dut,
    primary_collector_ip: str,
    *,
    stats_group_id: str = _STATS_GROUP,
    include_router_lldp: bool = False,
) -> None:
    """Apply SSIM split test01 ``test_01`` stats-group + root intervals on the DUT."""
    system = System()
    sg = stats_group_id
    with allure.step(f"Apply split-pipeline stats-group {sg} (mgmt VRF)"):
        _ensure_stats_group(dut, sg)
        dut.run_cmd("nv set system telemetry interface-stats sample-interval 10", validate=True)
        dut.run_cmd(
            "nv set system telemetry platform-stats export sample-interval 60",
            validate=True,
        )
        dut.run_cmd(
            "nv set system telemetry control-plane-stats export state enabled",
            validate=True,
        )
        dut.run_cmd(
            "nv set system telemetry control-plane-stats sample-interval 10",
            validate=True,
        )

        cmds = [
            f"nv set system telemetry stats-group {sg} histogram export state enabled",
            f"nv set system telemetry stats-group {sg} control-plane-stats export state enabled",
            f"nv set system telemetry stats-group {sg} control-plane-stats sample-interval 15",
            f"nv set system telemetry stats-group {sg} buffer-stats export state enabled",
            f"nv set system telemetry stats-group {sg} buffer-stats sample-interval 15",
            f"nv set system telemetry stats-group {sg} interface-stats export state enabled",
            f"nv set system telemetry stats-group {sg} interface-stats sample-interval 15",
            f"nv set system telemetry stats-group {sg} platform-stats export state enabled",
            f"nv set system telemetry stats-group {sg} platform-stats class cpu state enabled",
            f"nv set system telemetry stats-group {sg} platform-stats class cpu sample-interval 70",
            f"nv set system telemetry stats-group {sg} platform-stats class disk state enabled",
            f"nv set system telemetry stats-group {sg} platform-stats class disk sample-interval 70",
            (
                f"nv set system telemetry stats-group {sg} platform-stats class "
                "environment-sensor state enabled"
            ),
            (
                f"nv set system telemetry stats-group {sg} platform-stats class "
                "environment-sensor sample-interval 70"
            ),
            (
                f"nv set system telemetry stats-group {sg} platform-stats class "
                "file-system state enabled"
            ),
            (
                f"nv set system telemetry stats-group {sg} platform-stats class "
                "file-system sample-interval 70"
            ),
            f"nv set system telemetry stats-group {sg} platform-stats class memory state enabled",
            f"nv set system telemetry stats-group {sg} platform-stats class memory sample-interval 70",
            (
                f"nv set system telemetry export otlp grpc destination "
                f"{primary_collector_ip} stats-group {sg}"
            ),
        ]
        optional_cmds = []
        if include_router_lldp:
            optional_cmds.extend(
                [
                    f"nv set system telemetry stats-group {sg} router export state enabled",
                    f"nv set system telemetry stats-group {sg} lldp export state enabled",
                    f"nv set system telemetry stats-group {sg} lldp sample-interval 30",
                    (
                        f"nv set system telemetry stats-group {sg} platform-stats class "
                        "transceiver-info state enabled"
                    ),
                    (
                        f"nv set system telemetry stats-group {sg} platform-stats class "
                        "transceiver-info sample-interval 60"
                    ),
                    (
                        f"nv set system telemetry stats-group {sg} software-stats systemd "
                        "export state enabled"
                    ),
                    (
                        f"nv set system telemetry stats-group {sg} software-stats systemd "
                        "sample-interval 70"
                    ),
                ]
            )
        for cmd in cmds:
            dut.run_cmd(cmd, validate=True)
        for cmd in optional_cmds:
            dut.run_cmd(cmd, validate=False)

        system.telemetry.export.otlp.set(
            TelemetryConsts.STATE,
            _ENABLED,
            apply=False,
            dut_engine=dut,
        )
        _nv_apply(dut)


def prepare_split_pipeline_insecure_pre_run(
    dut,
    *,
    vrf: str = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT,
) -> None:
    hostname = get_dut_hostname(dut)
    with allure.step("Split-pipeline insecure pre-run (histogram baseline + service restart)"):
        system = System()
        _enable_histogram_root(system, dut)
        enable_cumulus_lab_interface_histogram(dut, hostname)
        dut.run_cmd("nv config apply -y", validate=True)
        time.sleep(10)
        restart_nvtelemetry(dut, vrf)
        restart_asic_monitor(dut, vrf)
        ensure_asic_monitor_running(dut, vrf)


def prepare_split_pipeline_secured_pre_run(
    dut,
    collector: OtelCollector,
    vrf: str = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT,
) -> None:
    """SSIM ``Test_Otel_Split_Mgmt_Vrf_Secured.pre_run_hook`` on mlx lab (no routing)."""
    with allure.step("Split-pipeline secured pre-run (restart OTLP session)"):
        cleanup_otlp_export_session(dut, collector, vrf=vrf)
        assert_otlp_session_established(collector)
        verify_otlp_client_active(dut, vrf)
        verify_otelcol_server_active(collector)


def run_split_pipeline_test01_verification(
    dut,
    collector: OtelCollector,
    cur_dir: str,
    *,
    vrf: str = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT,
    expected_gaps: dict | None = None,
    prepare_session: bool = True,
) -> None:
    """Shared test01 body: sample-interval validation for stats-group ``test_01``."""
    hostname = get_dut_hostname(dut)
    expected = expected_gaps or CumulusOtelConst.SPLIT_PIPELINE_TEST01_EXPECTED_GAPS
    verify_metrics_sample_interval_server1(
        dut,
        collector,
        hostname,
        cur_dir,
        vrf,
        expected,
        prepare_session=prepare_session,
    )


def apply_split_pipeline_mgmt_vrf_secured_base(
    dut,
    collector_ip: str,
    hostname: str,
) -> None:
    enable_cumulus_lab_interface_histogram(dut, hostname)
    apply_split_pipeline_test01_stats_group(
        dut, collector_ip, include_router_lldp=False
    )


def apply_split_pipeline_mgmt_vrf_insecure_base(
    dut,
    collector_ip: str,
    hostname: str,
) -> None:
    enable_cumulus_lab_interface_histogram(dut, hostname)
    vrf = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT
    restart_nvtelemetry(dut, vrf)
    restart_asic_monitor(dut, vrf)
