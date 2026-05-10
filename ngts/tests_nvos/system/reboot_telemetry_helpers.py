"""
NVUE + gNMI reboot telemetry: counters, last reboot reason/type, details, and time.

Use at test start to confirm NVUE and gNMI counters agree; after a reboot, the test passes
``RebootReasonCategory`` (USER_INITIATED, CRITICAL_ERROR, or POWER_FAILURE) and the exact
expected details string and expected user substring; the framework verifies counters, NVUE
reason-type, user, gentime, ``nv show system reboot`` top-level ``reason`` key, gNMI enum,
and matching detail strings on both sides. Reboot history is covered separately by
``test_reboot_command`` via ``system.reboot.history.show()``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Tuple

import ngts.tools.test_utils.allure_utils as allure
from ngts.constants.constants import GnmiConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.mapping.helpers import parse_gnmic_flat_output, run_gnmic_once_flat


class RebootReasonCategory(Enum):
    USER_INITIATED = "user_initiated"
    CRITICAL_ERROR = "critical_error"
    POWER_FAILURE = "power_failure"


# gNMI leaf last-reboot-reason values (OpenConfig / platform ENUM)
GNMI_LAST_REBOOT_REASON: Dict[RebootReasonCategory, str] = {
    RebootReasonCategory.USER_INITIATED: "REBOOT_USER_INITIATED",
    RebootReasonCategory.CRITICAL_ERROR: "REBOOT_CRITICAL_ERROR",
    RebootReasonCategory.POWER_FAILURE: "REBOOT_POWER_FAILURE",
}

# NVUE `reason-type` display strings (nv show system reboot reason)
NVUE_REASON_TYPE: Dict[RebootReasonCategory, str] = {
    RebootReasonCategory.USER_INITIATED: "user-initiated",
    RebootReasonCategory.CRITICAL_ERROR: "critical-error",
    RebootReasonCategory.POWER_FAILURE: "power-failure",
}

# NVUE counter leaf names (nv show system reboot counters) / gNMI reboot-counters/* suffix
COUNTER_KEY: Dict[RebootReasonCategory, str] = {
    RebootReasonCategory.USER_INITIATED: "user-initiated",
    RebootReasonCategory.CRITICAL_ERROR: "critical-error",
    RebootReasonCategory.POWER_FAILURE: "power-failure",
}

COUNTER_KEYS_NO_TOTAL = ("user-initiated", "power-failure", "critical-error")
COUNTER_KEYS_ALL = (*COUNTER_KEYS_NO_TOTAL, "total")

# NVUE reboot telemetry JSON (`nv show system reboot`, `... reboot reason`, `... reboot history` entries, etc.)
# can include reason-type values like "Critical Error". SendCommandTool treats the bare substring "Error" as a
# failure keyword; exempt it for those outputs only.
REBOOT_REASON_SHOW_EXEMPTED_ERR_MSGS = ("Error",)


def _int_from_value(value: Any) -> int:
    if value is None:
        raise ValueError("missing counter value")
    if isinstance(value, bool):
        raise ValueError(f"unexpected bool counter: {value}")
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.startswith(("0x", "0X")):
        return int(s, 16)
    return int(s, 10)


def _get_json_dict(output: str) -> Dict[str, Any]:
    return OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()


def _pick_key(d: Dict[str, Any], *candidates: str) -> Any:
    for k in candidates:
        if k in d:
            return d[k]
    return None


def gnmi_client_for_dut(engine_dut, device_dut) -> GnmiClient:
    return GnmiClient(
        engine_dut.ip,
        int(GnmiConsts.GNMI_DEFAULT_PORT),
        device_dut.default_username,
        device_dut.default_password,
        verify_tools_installed=True,
    )


def _gnmi_state_leaf_path(leaf: str) -> str:
    return f"components/component[name=CHASSIS]/state/{leaf}"


def get_nvue_reboot_counters(system) -> Dict[str, int]:
    """Parse `nv show system reboot counters` JSON."""
    with allure.step("NVUE: read system reboot counters"):
        raw = system.reboot.counters.show()
        data = _get_json_dict(raw)
        return normalize_nvue_counter_dict(data)


def normalize_nvue_counter_dict(data: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key in COUNTER_KEYS_ALL:
        val = _pick_key(data, key, key.replace("-", "_"))
        if val is not None:
            out[key] = _int_from_value(val)
    return out


def _sum_of_reboot_cause_counters(counters: Dict[str, int]) -> int:
    return sum(counters[k] for k in COUNTER_KEYS_NO_TOTAL)


def _assert_total_matches_sum_of_causes(counters: Dict[str, int], label: str) -> None:
    expected = _sum_of_reboot_cause_counters(counters)
    actual = counters["total"]
    assert actual == expected, (
        f"{label}: reboot counter `total` ({actual}) must equal sum of cause counters ({expected}): "
        f"{counters!r}"
    )


def _assert_all_counters_zero(counters: Dict[str, int], label: str) -> None:
    non_zero = {k: v for k, v in counters.items() if v != 0}
    assert not non_zero, f"{label}: expected all reboot counters to be 0 after factory reset, got {non_zero!r}"


def get_gnmi_reboot_counters(client: GnmiClient) -> Dict[str, int]:
    """Read reboot-counters/* leaves under the CHASSIS component state."""
    with allure.step("gNMI: read reboot-counters"):
        out: Dict[str, int] = {}
        for key in COUNTER_KEYS_ALL:
            path = _gnmi_state_leaf_path(f"reboot-counters/{key}")
            flat_out, _duration = run_gnmic_once_flat(path, client=client)
            val = parse_gnmic_flat_output(flat_out)
            if val is None or val == "":
                raise AssertionError(f"gNMI returned no value for {path!r}. Output: {flat_out!r}")
            out[key] = _int_from_value(val)
        return out


def get_nvue_last_reboot_reason(system) -> Dict[str, Any]:
    """Parse `nv show system reboot reason` JSON (reason, reason-type, gentime, user)."""
    with allure.step("NVUE: read system reboot reason"):
        raw = system.reboot.reason.show(exempted_err_msgs=REBOOT_REASON_SHOW_EXEMPTED_ERR_MSGS)
        return _get_json_dict(raw)


def get_gnmi_last_reboot_state(client: GnmiClient) -> Dict[str, str]:
    """Read last-reboot-time, last-reboot-reason, last-reboot-details from gNMI (CHASSIS)."""
    with allure.step("gNMI: read last reboot state"):
        state: Dict[str, str] = {}
        for leaf in ("last-reboot-time", "last-reboot-reason", "last-reboot-details"):
            path = _gnmi_state_leaf_path(leaf)
            flat_out, _duration = run_gnmic_once_flat(path, client=client)
            val = parse_gnmic_flat_output(flat_out)
            state[leaf] = "" if val is None else str(val).strip()
        return state


@dataclass
class RebootTelemetrySnapshot:
    nvue_counters: Dict[str, int]
    gnmi_counters: Dict[str, int]


def take_reboot_telemetry_snapshot(system, gnmi_client: GnmiClient) -> RebootTelemetrySnapshot:
    nvue_counters = get_nvue_reboot_counters(system)
    gnmi_counters = get_gnmi_reboot_counters(gnmi_client)
    return RebootTelemetrySnapshot(
        nvue_counters=nvue_counters,
        gnmi_counters=gnmi_counters,
    )


def _assert_nvue_gnmi_counters_agree(snapshot: RebootTelemetrySnapshot) -> None:
    """NVUE and gNMI must expose the same reboot counter values; totals must match sum of cause counters."""
    missing_nvue = set(COUNTER_KEYS_ALL) - set(snapshot.nvue_counters.keys())
    missing_gnmi = set(COUNTER_KEYS_ALL) - set(snapshot.gnmi_counters.keys())
    assert not missing_nvue, f"NVUE counters missing keys: {missing_nvue}. Got: {snapshot.nvue_counters!r}"
    assert not missing_gnmi, f"gNMI counters missing keys: {missing_gnmi}. Got: {snapshot.gnmi_counters!r}"
    _assert_total_matches_sum_of_causes(snapshot.nvue_counters, "NVUE")
    _assert_total_matches_sum_of_causes(snapshot.gnmi_counters, "gNMI")
    for k in COUNTER_KEYS_ALL:
        nv = snapshot.nvue_counters[k]
        gv = snapshot.gnmi_counters[k]
        assert nv == gv, (
            f"Reboot counter mismatch for {k!r}: NVUE={nv}, gNMI={gv}"
        )


def assert_nvue_gnmi_counters_match(snapshot: RebootTelemetrySnapshot) -> None:
    """At test start: NVUE and gNMI reboot counters must match for all known keys."""
    with allure.step("Verify NVUE and gNMI reboot counters match"):
        _assert_nvue_gnmi_counters_agree(snapshot)


def _counter_delta(before: Dict[str, int], after: Dict[str, int], key: str) -> int:
    return after[key] - before[key]


def verify_reboot_telemetry_after_reboot(
    snapshot_before: RebootTelemetrySnapshot,
    system,
    gnmi_client: GnmiClient,
    expected_category: RebootReasonCategory,
    expected_details: str,
    expected_user: str,
    reset_factory: bool = False,
) -> None:
    """
    expected_category: one of: USER_INITIATED, CRITICAL_ERROR, POWER_FAILURE and represent last-reboot-cause and the NVUE reason-type
    expected_details: the exact detail string for NVUE ``reason`` and gNMI ``last-reboot-details``
    expected_user: the exact user string matched as a substring in NVUE ``user``
    reset_factory: if True, reboot counters are expected to be reset to 0 (instead of incrementing by 1)
    """
    def _check() -> None:
        snap_after = take_reboot_telemetry_snapshot(system, gnmi_client)
        cat_key = COUNTER_KEY[expected_category]

        if reset_factory:
            _assert_all_counters_zero(snap_after.nvue_counters, "NVUE")
            _assert_all_counters_zero(snap_after.gnmi_counters, "gNMI")
        else:
            d_cat_nvue = _counter_delta(snapshot_before.nvue_counters, snap_after.nvue_counters, cat_key)
            assert d_cat_nvue == 1, (
                f"NVUE: expected {cat_key!r} counter +1 after reboot, got delta={d_cat_nvue}. "
                f"before={snapshot_before.nvue_counters!r} after={snap_after.nvue_counters!r}"
            )

            d_cat_gnmi = _counter_delta(snapshot_before.gnmi_counters, snap_after.gnmi_counters, cat_key)
            d_tot_gnmi = _counter_delta(snapshot_before.gnmi_counters, snap_after.gnmi_counters, "total")
            d_tot_nvue = _counter_delta(snapshot_before.nvue_counters, snap_after.nvue_counters, "total")
            assert d_cat_gnmi == 1, (
                f"gNMI: expected {cat_key!r} counter +1 after reboot, got delta={d_cat_gnmi}. "
                f"before={snapshot_before.gnmi_counters!r} after={snap_after.gnmi_counters!r}"
            )
            assert d_tot_gnmi == 1, (
                f"gNMI: expected total counter +1 after reboot, got delta={d_tot_gnmi}. "
                f"before={snapshot_before.gnmi_counters!r} after={snap_after.gnmi_counters!r}"
            )
            assert d_tot_nvue == 1, (
                f"NVUE: expected total counter +1 after reboot, got delta={d_tot_nvue}. "
                f"before={snapshot_before.nvue_counters!r} after={snap_after.nvue_counters!r}"
            )

        _assert_nvue_gnmi_counters_agree(snap_after)

        reboot_top = _get_json_dict(
            system.reboot.show(exempted_err_msgs=REBOOT_REASON_SHOW_EXEMPTED_ERR_MSGS)
        )
        assert "reason" in reboot_top, (
            f"nv show system reboot: missing top-level 'reason' key, keys={list(reboot_top.keys())!r}"
        )

        nvue_reason = get_nvue_last_reboot_reason(system)
        reason_type = _pick_key(nvue_reason, "reason-type", "reason_type")
        nvue_detail = _pick_key(nvue_reason, "reason", "detail")
        assert reason_type is not None, f"NVUE reboot reason missing reason-type: {nvue_reason!r}"
        assert str(reason_type).strip() == NVUE_REASON_TYPE[expected_category], (
            f"NVUE reason-type: expected {NVUE_REASON_TYPE[expected_category]!r}, got {reason_type!r}"
        )

        nvue_user_raw = _pick_key(nvue_reason, "user")
        assert nvue_user_raw is not None, f"NVUE reboot reason missing user: {nvue_reason!r}"
        nvue_user_s = str(nvue_user_raw).strip()
        exp_user = (expected_user or "").strip()
        assert exp_user, "expected_user must be non-empty for NVUE user substring check"
        assert exp_user in nvue_user_s, (
            f"NVUE user: expected substring {exp_user!r} in {nvue_user_s!r}"
        )

        gnmi_state = get_gnmi_last_reboot_state(gnmi_client)
        gnmi_enum = GNMI_LAST_REBOOT_REASON[expected_category]
        assert gnmi_state.get("last-reboot-reason") == gnmi_enum, (
            f"gNMI last-reboot-reason: expected {gnmi_enum!r}, got {gnmi_state.get('last-reboot-reason')!r}"
        )

        assert nvue_detail is not None, f"NVUE reboot reason missing reason/details: {nvue_reason!r}"
        exp = expected_details.strip()
        nvue_s = str(nvue_detail).strip()
        gnmi_s = (gnmi_state.get("last-reboot-details") or "").strip()

        assert nvue_s == exp, f"NVUE reason: expected {exp!r}, got {nvue_s!r}"
        assert gnmi_s == exp, f"gNMI last-reboot-details: expected {exp!r}, got {gnmi_s!r}"

        gentime = _pick_key(nvue_reason, "gentime", "gen-time")
        lr_time = gnmi_state.get("last-reboot-time", "")
        assert gentime, f"NVUE gentime empty: {nvue_reason!r}"
        assert lr_time, f"gNMI last-reboot-time empty: {gnmi_state!r}"

    with allure.step(
        f"Verify reboot telemetry ({expected_category.name}, details={expected_details!r}, user~={expected_user!r}, reset_factory={reset_factory})"
    ):
        ValidationTool.retry_until_valid(_check, tries=6, delay=10, description="Wait for reboot telemetry to settle")


def diff_counters(
    before: RebootTelemetrySnapshot, after: RebootTelemetrySnapshot
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Return (nvue_delta, gnmi_delta) per counter key for debugging."""
    nvue = {k: after.nvue_counters[k] - before.nvue_counters[k] for k in COUNTER_KEYS_ALL}
    gnmi = {k: after.gnmi_counters[k] - before.gnmi_counters[k] for k in COUNTER_KEYS_ALL}
    return nvue, gnmi
