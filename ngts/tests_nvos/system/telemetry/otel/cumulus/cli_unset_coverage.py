"""NV unset CLI coverage baseline and helpers (SSIM ``Test_Otel_Mgmt_Vrf_Insecure_CLI_Coverage``)."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Tuple

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import ConfState, TelemetryConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.telemetry.otel.cumulus.constants import CumulusOtelConst
from ngts.tests_nvos.system.telemetry.otel.cumulus.cli_telemetry import list_swp_interfaces
from ngts.tests_nvos.system.telemetry.otel.cumulus.helpers import (
    apply_otel_mgmt_vrf_no_tls_telemetry_config,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.lab_topology import (
    discover_swp_interfaces_on_dut,
)

logger = logging.getLogger(__name__)


def get_cumulus_version_tuple(dut) -> Tuple[int, int]:
    """Parse ``product-release`` from ``nv show system version``."""
    parsed = System().version.parse_show(dut_engine=dut)
    if not isinstance(parsed, dict):
        return 0, 0
    release = parsed.get("product-release") or parsed.get("version") or ""
    match = re.match(r"(\d+)\.(\d+)", str(release))
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


def require_cumulus_at_least(dut, min_version: str) -> None:
    """Skip when DUT Cumulus version is below ``min_version`` (SSIM ``check_version``)."""
    required = tuple(int(part) for part in min_version.split(".")[:2])
    current = get_cumulus_version_tuple(dut)
    if current < required:
        pytest.skip(
            f"Cumulus {current[0]}.{current[1]} < required {min_version} for this unset test"
        )


def _nv_apply(dut) -> None:
    dut.run_cmd("nv config apply -y", validate=True)


def _system_telemetry_node(path: str) -> BaseComponent:
    return BaseComponent(System().telemetry, path=path)


def _iface_telemetry_node(iface: str, path: str) -> BaseComponent:
    return BaseComponent(Interface(None, port_name=iface), path=f'/telemetry{path}')


def _telemetry_applied_show(dut, path: str) -> Dict[str, Any]:
    parsed = _system_telemetry_node(path).parse_show(
        rev=ConfState.APPLIED, dut_engine=dut
    )
    return parsed if isinstance(parsed, dict) else {}


def _iface_telemetry_applied_show(dut, iface: str, path: str) -> Dict[str, Any]:
    parsed = _iface_telemetry_node(iface, path).parse_show(
        rev=ConfState.APPLIED, dut_engine=dut
    )
    return parsed if isinstance(parsed, dict) else {}


def _interface_label_pairs() -> List[Tuple[str, str]]:
    labels = CumulusOtelConst.INTF_LABELS
    return [(labels[i], labels[i + 1]) for i in range(0, len(labels), 2)]


def _configure_interface_telemetry_cli_baseline(dut) -> None:
    """SSIM ``OtelMgmtVrfNoTLSConfig.configure_topo`` spine ``swp`` loop (lines 62-128).

    Per interface, in order: full histogram (PG/TC 0-7, rx-byte + crc), then labels l1-l10.
    """
    ifaces = discover_swp_interfaces_on_dut(dut)
    label_pairs = _interface_label_pairs()
    with allure.step(
        f"Configure interface histogram + labels on {len(ifaces)} swp(s) (SSIM spine swp loop)"
    ):
        for iface in ifaces:
            for pg in range(8):
                dut.run_cmd(
                    f"nv set interface {iface} telemetry histogram "
                    f"ingress-buffer priority-group {pg}",
                    validate=True,
                )
            for tc in range(8):
                dut.run_cmd(
                    f"nv set interface {iface} telemetry histogram "
                    f"egress-buffer traffic-class {tc}",
                    validate=True,
                )
                dut.run_cmd(
                    f"nv set interface {iface} telemetry histogram "
                    f"latency traffic-class {tc}",
                    validate=True,
                )
            for counter_type in ("rx-byte", "crc"):
                dut.run_cmd(
                    f"nv set interface {iface} telemetry histogram "
                    f"counter counter-type {counter_type}",
                    validate=True,
                )
            for label_id, description in label_pairs:
                dut.run_cmd(
                    f"nv set interface {iface} telemetry label {label_id} "
                    f'description "{description}"',
                    validate=True,
                )
        _nv_apply(dut)


def _set_device_labels(dut) -> None:
    """SSIM ``OtelMgmtVrfNoTLSConfig`` system telemetry device labels (lines 339-359)."""
    with allure.step("Configure system telemetry device labels (CLI coverage)"):
        for label_id, description in CumulusOtelConst.DEVICE_LABELS:
            dut.run_cmd(
                f"nv set system telemetry label {label_id} "
                f'description "{description}"',
                validate=True,
            )
        _nv_apply(dut)


def _restore_otlp_mgmt_insecure_destinations(dut, collector_ips: Iterable[str]) -> None:
    """Re-establish OTLP export after per-test ``clear_config`` (SSIM ``post_run_hook`` parity).

    NGTS ``clear_config`` resets the DUT to factory YAML between tests, which drops
    ``grpc insecure`` and collector destinations from ``otel_suite_mgmt``. Without this
    step, baseline restore fails ``nv config apply`` with missing-certificate errors.
    """
    from ngts.tests_nvos.system.telemetry.otel.helpers import (
        configure_switch_otlp_grpc_dual_destination,
    )

    ips = list(collector_ips)
    if len(ips) < 2:
        pytest.fail(
            f"CLI coverage baseline requires primary + secondary collector IPs, got {ips!r}"
        )
    with allure.step("Restore mgmt VRF insecure OTLP dual destinations"):
        configure_switch_otlp_grpc_dual_destination(
            dut,
            primary_ip=ips[0],
            secondary_ip=ips[1],
            export_vrf=CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT,
            insecure=True,
        )


def apply_otel_cli_coverage_baseline(
    dut,
    collector_ips: Iterable[str],
) -> None:
    """``OtelMgmtVrfNoTLSConfig`` baseline for unset CLI tests (mlx lab, no BGP/leaves).

    SSIM ``configure_topo`` order:
    1. Per-interface histogram + interface labels on every spine ``swp`` (lines 62-128).
    2. System telemetry tree + device labels (lines 237-359).
    3. OTLP destinations + ``grpc insecure`` (``configure_topo_post_boot`` / post_run).
    4. Stats-group + root telemetry + ``asic-monitor`` via
       :func:`apply_otel_mgmt_vrf_no_tls_telemetry_config` (interface histogram skipped).
    """
    _configure_interface_telemetry_cli_baseline(dut)
    _set_device_labels(dut)
    _restore_otlp_mgmt_insecure_destinations(dut, collector_ips)
    apply_otel_mgmt_vrf_no_tls_telemetry_config(
        dut,
        collector_ips=collector_ips,
        enable_interface_histogram=False,
    )


def unset_interface_histogram_ingress_pg(dut, iface: str, pg: str) -> None:
    _iface_telemetry_node(iface, '/histogram/ingress-buffer/priority-group').unset(
        str(pg), dut_engine=dut
    )


def unset_interface_histogram_egress_tc(dut, iface: str, tc: str) -> None:
    _iface_telemetry_node(iface, '/histogram/egress-buffer/traffic-class').unset(
        str(tc), dut_engine=dut
    )


def unset_interface_histogram_latency_tc(dut, iface: str, tc: str) -> None:
    _iface_telemetry_node(iface, '/histogram/latency/traffic-class').unset(
        str(tc), dut_engine=dut
    )


def unset_interface_histogram_counter(dut, iface: str, counter_type: str = "rx-byte") -> None:
    _iface_telemetry_node(iface, '/histogram/counter/counter-type').unset(
        counter_type, dut_engine=dut
    )


def unset_interface_label(dut, iface: str, label_id: str, *, key: str = "") -> None:
    BaseComponent(
        Interface(None, port_name=iface), path=f'/telemetry/label/{label_id}'
    ).unset(key, dut_engine=dut)


def get_interface_telemetry_labels_applied(dut, iface: str) -> Dict[str, Any]:
    return _iface_telemetry_applied_show(dut, iface, '/label')


def unset_system_telemetry_interface_stats_egress_tc(dut, tc: str) -> None:
    _system_telemetry_node('/interface-stats/egress-buffer/traffic-class').unset(
        str(tc), dut_engine=dut
    )


def unset_system_telemetry_interface_stats_ingress_pg(dut, pg: str) -> None:
    _system_telemetry_node('/interface-stats/ingress-buffer/priority-group').unset(
        str(pg), dut_engine=dut
    )


def unset_system_otlp_destination_port(dut, destination_id: str) -> None:
    BaseComponent(
        System().telemetry.export.otlp.grpc.destination,
        path=f'/{destination_id}',
    ).unset('port', dut_engine=dut)


def get_system_interface_stats_egress_tc_applied(dut) -> Dict[str, Any]:
    return _telemetry_applied_show(
        dut, '/interface-stats/egress-buffer/traffic-class'
    )


def unset_system_telemetry_label(dut, label_id: str, *, key: str = "") -> None:
    BaseComponent(System().telemetry.label, path=f'/{label_id}').unset(
        key, dut_engine=dut
    )


def get_system_telemetry_labels_applied(dut) -> Dict[str, Any]:
    return _telemetry_applied_show(dut, '/label')


def unset_system_interface_stats_class_phy(dut, *, key: str = "", value: str = "") -> None:
    op_param = f"{key} {value}".strip() if key else ""
    System().telemetry.interface_stats.cls.phy.unset(op_param, dut_engine=dut)


def get_system_interface_stats_class_phy_applied(dut) -> Dict[str, Any]:
    return _telemetry_applied_show(dut, '/interface-stats/class/phy')


def unset_system_platform_stats_class(
    dut, platform_class: str, *, key: str = "", value: str = ""
) -> None:
    system = System()
    node = system.telemetry.platform_stats.cls.categories.get(platform_class)
    if node is None:
        node = BaseComponent(system.telemetry.platform_stats.cls, path=f'/{platform_class}')
    op_param = f"{key} {value}".strip() if key else ""
    node.unset(op_param, dut_engine=dut)


def get_system_platform_stats_class_applied(dut, platform_class: str) -> Dict[str, Any]:
    return _telemetry_applied_show(dut, f'/platform-stats/class/{platform_class}')


def unset_system_platform_stats_class_platform_info(
    dut, *, key: str = "", value: str = ""
) -> None:
    """SSIM test05a: ``nv unset system telemetry platform-stats class platform-info``."""
    unset_system_platform_stats_class(
        dut, TelemetryConsts.PLATFORM_CLASS_PLATFORM_INFO, key=key, value=value
    )


def get_system_platform_stats_class_platform_info_applied(dut) -> Dict[str, Any]:
    return get_system_platform_stats_class_applied(
        dut, TelemetryConsts.PLATFORM_CLASS_PLATFORM_INFO
    )


def apply_unset_changes(dut) -> None:
    with allure.step("Apply NVUE after unset operations"):
        _nv_apply(dut)


def swp_interfaces_for_unset(dut) -> List[str]:
    try:
        return list_swp_interfaces(dut)
    except Exception:  # noqa: BLE001
        return list(discover_swp_interfaces_on_dut(dut))
