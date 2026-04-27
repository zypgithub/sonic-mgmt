"""
Cluster MPI + optional PREI (mlxreg) on the DUT during ansible-driven traffic.

Ported from the 15-04-2026 workflow: NVLink access port selection, Juliet ASIC
error-injection gate, delayed flaky PREI burst while MPI runs, and optional
interface error-counter snapshots. Shared by ``test_cluster_traffic_error.py``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional, Tuple

import pytest

from ngts.nvos_constants.constants_nvos import ActionConsts, OutputFormat
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tests_nvos.cluster.ansible_playbooks_tool import AnsiblePlaybooksTool
from ngts.tests_nvos.interfaces.ib_phy_recovery.consts import PREIErrorInjection
from ngts.tests_nvos.interfaces.ib_phy_recovery.helpers import (
    disable_error_injection,
    get_local_port_and_mst_device_nvlink,
    inject_error_via_prei,
)
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _prei_injection_enabled() -> bool:
    v = os.environ.get("CLUSTER_TRAFFIC_PREI_INJECTION", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _use_cluster_prei_injection(enable_prei: Optional[bool]) -> bool:
    v = os.environ.get("CLUSTER_TRAFFIC_PREI_INJECTION", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if enable_prei is False:
        return False
    if enable_prei is True:
        return True
    return _prei_injection_enabled()


def _link_counter_blob(show_dict: Dict[str, Any]) -> Dict[str, Any]:
    if not show_dict:
        return {}
    link = show_dict.get("link")
    if isinstance(link, dict):
        return link
    return show_dict


def _error_like_total(show_dict: Dict[str, Any]) -> int:
    d = _link_counter_blob(show_dict)
    keys = (
        IbInterfaceConsts.LINK_STATS_IN_ERRORS,
        IbInterfaceConsts.LINK_STATS_OUT_ERRORS,
        IbInterfaceConsts.LINK_STATS_IN_SYMBOL_ERRORS,
        IbInterfaceConsts.LINK_STATS_RCV_ICRC_ERRORS,
        IbInterfaceConsts.LINK_STATS_TX_PARITY_ERRORS,
    )
    total = 0
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        try:
            total += int(v)
        except (TypeError, ValueError):
            continue
    ib = show_dict.get("ib") if isinstance(show_dict, dict) else None
    if isinstance(ib, dict):
        errs = ib.get("errors")
        if isinstance(errs, dict):

            def _walk(obj: Any) -> None:
                nonlocal total
                if isinstance(obj, dict):
                    for x in obj.values():
                        _walk(x)
                    return
                try:
                    total += int(obj)
                except (TypeError, ValueError):
                    pass

            _walk(errs)
    return total


def snapshot_interface_counters_error_total(engine, iface: str) -> Tuple[Dict[str, Any], int]:
    port = Port(iface, "", "")
    raw = port.interface.counters.show(dut_engine=engine, output_format=OutputFormat.json)
    d = OutputParsingTool.parse_json_str_to_dictionary(raw).get_returned_value()
    if not isinstance(d, dict):
        return {}, 0
    return d, _error_like_total(d)


def _prei_watch_counter_fields(counters_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fields to compare immediately before vs after a PREI burst on ``nv show interface <port> counters``:
    ``link.carrier-down-count`` and ``out-drops`` (top-level or under ``link`` depending on NVUE shape).
    """
    if not isinstance(counters_dict, dict):
        return {"carrier-down-count": None, "out-drops": None}

    def _as_int(v: Any) -> Any:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return v

    link_blob = _link_counter_blob(counters_dict)
    carrier = None
    if isinstance(link_blob, dict):
        carrier = link_blob.get(IbInterfaceConsts.LINK_STATS_LINK_DOWNED)

    out_drops = counters_dict.get(IbInterfaceConsts.LINK_STATS_OUT_DROPS)
    if out_drops is None and isinstance(link_blob, dict):
        out_drops = link_blob.get(IbInterfaceConsts.LINK_STATS_OUT_DROPS)

    return {
        "carrier-down-count": _as_int(carrier),
        "out-drops": _as_int(out_drops),
    }


def _nv_show_fae_interface_counters_json(engine, iface: str) -> str:
    """``nv show fae interface <iface> counters`` (JSON string)."""
    return Fae(port_name=iface).interface.counters.show(
        dut_engine=engine, output_format=OutputFormat.json
    )


def _prei_watch_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in ("carrier-down-count", "out-drops"):
        a, b = before.get(k), after.get(k)
        if isinstance(a, int) and isinstance(b, int):
            out[k] = {"before": a, "after": b, "delta": b - a}
        else:
            out[k] = {"before": a, "after": b, "delta": None}
    return out


def _require_prei_tools_on_dut(engine) -> None:
    out = engine.run_cmd("command -v mlxreg >/dev/null 2>&1 && echo OK || echo MISSING")
    if "OK" not in (out or ""):
        pytest.skip("PREI requires `mlxreg` on the DUT (switch).")


@contextmanager
def _juliet_asic_error_injection_enabled(devices):
    inv = getattr(devices.dut, "platform_inventory_items_dict", {}) or {}
    if "bmc" not in inv:
        yield
        return
    fae = Fae()
    with allure.step("Enable ASIC error injection (required for PREI on this platform)"):
        fae.platform.asic.error_injection.action(
            ActionConsts.ENABLE, expected_output="Error injection has been"
        )
    try:
        yield
    finally:
        with allure.step("Disable ASIC error injection"):
            fae.platform.asic.error_injection.action(
                ActionConsts.DISABLE, expected_output="Error injection has been"
            )


def select_nvl_access_port_for_prei(engines, devices) -> str:
    access = getattr(devices.dut, "nvl_access_ports_list", None) or []
    if not access:
        pytest.skip("No NVL access ports — cannot run PREI on cluster ACP")

    pinned = os.environ.get("CLUSTER_PREI_PORT_NAME", "").strip() or "acp1"
    try_names = []
    if pinned in access:
        try_names.append(pinned)
    for n in access:
        if n not in try_names:
            try_names.append(n)

    for name in try_names:
        try:
            port = Port(name, "", "")
            state = port.interface.link.state.show(dut_engine=engines.dut)
            if _link_is_up(state):
                return name
        except Exception as e:
            logger.debug("link check %s: %s", name, e)
            continue

    pytest.skip(
        f"PREI needs a link-up NVL access port; tried {try_names[:5]}{'…' if len(try_names) > 5 else ''}"
    )


def _link_is_up(state: str) -> bool:
    return "up" in (state or "").lower()


def run_prei_flaky_burst(engine, port_name: str, burst_sec: Optional[int] = None) -> None:
    _require_prei_tools_on_dut(engine)
    burst = burst_sec if burst_sec is not None else _env_int("CLUSTER_PREI_BURST_SEC", 30)

    env_lp = os.environ.get("CLUSTER_PREI_LOCAL_PORT", "").strip()
    env_mst = os.environ.get("CLUSTER_PREI_MST_DEVICE", "").strip()
    if env_lp and env_mst:
        local_port, mst_device = env_lp, env_mst
    else:
        local_port, mst_device = get_local_port_and_mst_device_nvlink(port_name, dut_engine=engine)

    try:
        inject_error_via_prei(
            engine,
            mst_device,
            local_port,
            PREIErrorInjection.ERROR_TYPE_ADMIN_TRIGGER_RECOVERY,
            PREIErrorInjection.FLAKY_CABLE,
        ).verify_result()
        time.sleep(burst)
    finally:
        off = disable_error_injection(engine, mst_device, local_port)
        if not off.result:
            logger.error(
                "PREI disable failed after burst (port may retain injection): %s",
                off.info,
            )


def run_mpi_playbook_with_delayed_prei(
    engines,
    devices,
    ansible_inventory_file: str,
    playbook_key: str,
    component_paths_dict: Optional[dict] = None,
    inject_after_sec: Optional[int] = None,
    burst_sec: Optional[int] = None,
    prei_port_name: Optional[str] = None,
) -> bool:
    if component_paths_dict is None:
        component_paths_dict = {}

    delay = inject_after_sec if inject_after_sec is not None else _env_int("CLUSTER_PREI_INJECT_AFTER_SEC", 180)
    result: Dict[str, Any] = {"ok": False, "exc": None}

    def _mpi() -> None:
        try:
            result["ok"] = AnsiblePlaybooksTool.run_playbook_by_key(
                playbook_key, ansible_inventory_file, component_paths_dict
            )
        except Exception as e:
            result["exc"] = e
            result["ok"] = False

    th = threading.Thread(target=_mpi, name="cluster_mpi_playbook", daemon=False)
    th.start()
    time.sleep(delay)
    port = prei_port_name or select_nvl_access_port_for_prei(engines, devices)

    d_pre_prei, _ = snapshot_interface_counters_error_total(engines.dut, port)
    watch_before = _prei_watch_counter_fields(d_pre_prei)
    logger.info(
        "PREI watch BEFORE burst (port=%s, nv show interface counters): %s",
        port,
        watch_before,
    )
    allure.attach(
        "prei_interface_counters_watch_before_burst_%s" % port,
        "PREI port=%s before burst (watch fields): %s\n\nFull nv show interface %s counters (JSON):\n%s"
        % (
            port,
            json.dumps(watch_before, indent=2),
            port,
            json.dumps(d_pre_prei, indent=2, default=str),
        ),
    )

    fae_pre_raw = _nv_show_fae_interface_counters_json(engines.dut, port)
    logger.info("PREI FAE interface %s counters before burst: %s", port, fae_pre_raw)
    allure.attach(
        "prei_fae_interface_%s_counters_before_burst" % port,
        "nv show fae interface %s counters (before PREI burst):\n%s" % (port, fae_pre_raw),
    )

    with allure.step(
        "PREI flaky burst during MPI (port=%s, delay=%ss, burst=%ss)"
        % (port, delay, burst_sec if burst_sec is not None else _env_int("CLUSTER_PREI_BURST_SEC", 30))
    ):
        run_prei_flaky_burst(engines.dut, port, burst_sec=burst_sec)

    fae_post_raw = _nv_show_fae_interface_counters_json(engines.dut, port)
    logger.info("PREI FAE interface %s counters after burst: %s", port, fae_post_raw)
    allure.attach(
        "prei_fae_interface_%s_counters_after_burst" % port,
        "nv show fae interface %s counters (after PREI burst):\n%s" % (port, fae_post_raw),
    )

    d_post_prei, _ = snapshot_interface_counters_error_total(engines.dut, port)
    watch_after = _prei_watch_counter_fields(d_post_prei)
    delta = _prei_watch_delta(watch_before, watch_after)
    logger.info(
        "PREI watch AFTER burst (port=%s, nv show interface counters): %s",
        port,
        watch_after,
    )
    logger.info(
        "PREI watch DELTA burst (port=%s): carrier-down-count %s, out-drops %s",
        port,
        delta["carrier-down-count"],
        delta["out-drops"],
    )
    allure.attach(
        "prei_interface_counters_watch_after_burst_%s" % port,
        "PREI port=%s after burst (watch fields): %s\n\nPREI watch delta: %s\n"
        "(link.%s and %s often move on flaky cable injection; zeros can mean async NVUE or different fault path.)\n\n"
        "Full nv show interface %s counters after burst (JSON):\n%s"
        % (
            port,
            json.dumps(watch_after, indent=2),
            json.dumps(delta, indent=2, default=str),
            IbInterfaceConsts.LINK_STATS_LINK_DOWNED,
            IbInterfaceConsts.LINK_STATS_OUT_DROPS,
            port,
            json.dumps(d_post_prei, indent=2, default=str),
        ),
    )

    th.join()
    if result["exc"]:
        logger.error("MPI playbook thread failed: %s", result["exc"])
        return False
    return bool(result["ok"])


def _run_cluster_mpi_with_optional_prei(
    engines,
    devices,
    ansible_inventory_file: str,
    playbook_key: str,
    enable_prei: Optional[bool] = None,
    component_paths_dict: Optional[dict] = None,
) -> bool:
    if component_paths_dict is None:
        component_paths_dict = {}
    if not _use_cluster_prei_injection(enable_prei):
        return AnsiblePlaybooksTool.run_playbook_by_key(
            playbook_key, ansible_inventory_file, component_paths_dict
        )

    with _juliet_asic_error_injection_enabled(devices):
        prei_port = select_nvl_access_port_for_prei(engines, devices)
        _, err_before = snapshot_interface_counters_error_total(engines.dut, prei_port)
        logger.info("PREI mode: error-like counter total before MPI (port %s) = %s", prei_port, err_before)

        ok = run_mpi_playbook_with_delayed_prei(
            engines,
            devices,
            ansible_inventory_file,
            playbook_key,
            component_paths_dict=component_paths_dict,
            prei_port_name=prei_port,
        )

        _, err_after = snapshot_interface_counters_error_total(engines.dut, prei_port)
        logger.info(
            "PREI mode: error-like counter total after MPI (port %s) = %s (delta %+d)",
            prei_port,
            err_after,
            err_after - err_before,
        )
        allure.attach(
            "cluster_prei_error_counters",
            "PREI injection port=%s error-like counters: before=%s after=%s delta=%s"
            % (prei_port, err_before, err_after, err_after - err_before),
        )
        return ok
