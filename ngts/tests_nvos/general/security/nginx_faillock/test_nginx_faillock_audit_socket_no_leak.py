"""
Regression: nginx workers leaking AUDIT-related descriptors on PAM faillock auth paths.

Historical failure mode: failed NVUE basic-auth cycles left audit netlink resources open until
the worker hit the per-process open-file limit; REST and PAM then misbehaved.

Manual repro pattern::

    # several requests with wrong password, pause, one with correct password (from DUT)
    curl -k -u admin:<wrong> https://127.0.0.1:<open-api-port>/nvue_v1/system
    curl -k -u admin:<correct> https://127.0.0.1:<open-api-port>/nvue_v1/system

Worker PIDs via ``pgrep``; count ``lsof`` rows like
``nginx … <fd>u netlink … AUDIT`` (netlink audit socket), not arbitrary ``AUDIT`` substrings.

Temporarily lowers ``fail-delay`` / ``lockout-reattempt`` for speed, then ``nv unset`` those
fields only — ``lockout-attempts`` is never modified.

``DEFAULT_CYCLES`` controls how many times the cycle repeats. ``MAX_AUDIT_LINE_GROWTH`` bounds
allowed growth vs baseline (0 = strict).
"""

from __future__ import annotations

import logging
import re
import shlex
import time

import pytest

from devts.infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine


from ngts.nvos_constants.constants_nvos import ApiType, SystemConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.Restrictions import Restrictions
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.authentication_restrictions.constants import RestrictionsConsts
from ngts.tests_nvos.general.security.security_test_tools.security_test_utils import run_nginx
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)

NVUE_SYSTEM_URL_SUFFIX = "/nvue_v1/system"

# Failed auths per cycle (each expect HTTP 401). Kept at default ``lockout-attempts`` (5) without
# exceeding it so we never tune ``lockout-attempts`` in this test.
FAILED_AUTH_ATTEMPTS_PER_CYCLE = 5
# Shorter than factory ``lockout-reattempt`` (15s) so the loop finishes faster; reverted via unset.
FAST_LOCKOUT_REATTEMPT_SEC = 3
WAIT_AFTER_FAILED_AUTHS_SEC = FAST_LOCKOUT_REATTEMPT_SEC + 1

HTTP_UNAUTHORIZED = "401"
HTTP_OK = "200"

DEFAULT_CYCLES = 10
MAX_AUDIT_LINE_GROWTH = 1
DEFAULT_BAD_PASSWORD = "asd"

# ``lsof`` line shape (spaces flexible), e.g.
# nginx   1324 root   17u  netlink                         0t0 325089733 AUDIT
_LSOF_NETLINK_AUDIT_LINE = re.compile(
    r"^\S+\s+\d+\s+\S+\s+\S+u\s+netlink\s+.*\bAUDIT\s*$",
    re.MULTILINE,
)


def _dut_open_api_port(dut: LinuxSshEngine) -> str:
    """HTTPS port for NVUE/OpenAPI as seen by the topology (AIR vs standard lab)."""
    port = getattr(dut, "open_api_port", None)
    return str(port).strip() if port else SystemConsts.EXTERNAL_API_PORT_DEFAULT


def _http_code_from_curl_stdout(out: str) -> str:
    """Take the last line that looks like an HTTP status (avoids MOTD/profile noise on stdout)."""
    for line in reversed(out.strip().splitlines()):
        s = line.strip()
        if len(s) == 3 and s.isdigit():
            return s
    pytest.fail(f"no 3-digit HTTP status in curl output: {out!r}")


def _nvue_system_http_code_via_dut_curl(
    dut: LinuxSshEngine, port: str, user: str, password: str
) -> str:
    """
    GET ``/nvue_v1/system`` over HTTPS from the DUT to loopback (runner does not need L3 to NVUE).

    Uses ``bash --noprofile --norc`` so a login shell does not run ``/etc/profile.d/*`` (those print
    banners and break parsing). Credentials are passed as a single ``-u`` argument via ``shlex.quote``.

    Writes the status code to a temp file then ``cat``s it: some SSH stacks drop very short,
    no-newline stdout from ``curl -w``, which previously yielded an empty string.

    ``LinuxSshEngine.run_cmd`` does not accept ``sanitized_cmd`` (unlike some base SSH helpers),
    so the executed command string may appear in infra logs; credentials are still shell-escaped.

    Returns HTTP status code as a string (e.g. ``401``, ``200``).
    """
    tmp_path = f"/tmp/nvue_faillock_http_{time.time_ns()}.txt"
    tmp_q = shlex.quote(tmp_path)
    auth_q = shlex.quote(f"{user}:{password}")
    url = shlex.quote(f"https://127.0.0.1:{port}{NVUE_SYSTEM_URL_SUFFIX}")
    inner = (
        f"set -e; rm -f {tmp_q}; "
        f'curl -k -s -o /dev/null -w "%{{http_code}}\\n" -u {auth_q} {url} > {tmp_q}; '
        f"test -s {tmp_q}; cat {tmp_q}; rm -f {tmp_q}"
    )
    cmd = "bash --noprofile --norc -c " + shlex.quote(inner)
    out = dut.run_cmd(cmd, validate=True).strip()
    return _http_code_from_curl_stdout(out)


def _nginx_worker_pids(dut: LinuxSshEngine) -> list[int]:
    """PIDs of nginx worker processes on the DUT (no ``grep`` self-match)."""
    out = dut.run_cmd("pgrep -f 'nginx: worker' || true")
    return sorted({int(x) for x in out.split() if x.isdigit()})


def _audit_lsof_lines(dut: LinuxSshEngine, pids: list[int]) -> int:
    """
    Sum **netlink AUDIT** ``lsof`` rows per worker PID (matches ``netlink`` … ``AUDIT`` line tail).

    ``sudo lsof`` must succeed; failures raise (no treating errors as zero lines).
    """
    total = 0
    for pid in pids:
        out = dut.run_cmd(f"sudo lsof -p {pid}", validate=True)
        for line in out.splitlines():
            if line.startswith("COMMAND"):
                continue
            if _LSOF_NETLINK_AUDIT_LINE.match(line.rstrip("\r")):
                total += 1
    return total


def _apply_fast_fail_auth_profile(restrictions: Restrictions) -> None:
    """
    Shorten wait-oriented knobs only; does not touch ``lockout-attempts``.

    Reverted with ``nv unset`` on those same fields (defaults), not a snapshot — avoids carrying
    prior lab-specific values for fields we never changed.
    """
    restrictions.set(RestrictionsConsts.FAIL_DELAY, 0, apply=True).verify_result()
    restrictions.set(
        RestrictionsConsts.LOCKOUT_REATTEMPT, FAST_LOCKOUT_REATTEMPT_SEC, apply=True
    ).verify_result()


def _unset_temporary_restriction_tuning(restrictions: Restrictions) -> None:
    """``nv unset`` only what `_apply_fast_fail_auth_profile` set (back to platform defaults)."""
    restrictions.unset(RestrictionsConsts.FAIL_DELAY, apply=True).verify_result()
    restrictions.unset(RestrictionsConsts.LOCKOUT_REATTEMPT, apply=True).verify_result()


@pytest.mark.security
@pytest.mark.system
def test_nginx_faillock_audit_socket_no_leak(engines):
    """
    Verify nginx workers do not leak AUDIT-related ``lsof`` lines during repeated
    failed-then-success NVUE basic auth (faillock path).

    Each cycle: ``FAILED_AUTH_ATTEMPTS_PER_CYCLE`` NVUE GETs with bad password (expect
    ``HTTP_UNAUTHORIZED``), ``WAIT_AFTER_FAILED_AUTHS_SEC`` sleep, then one GET with good password
    (expect ``HTTP_OK``). Assert summed AUDIT lines do not grow beyond ``MAX_AUDIT_LINE_GROWTH``
    vs baseline on the **same** worker PID set.
    """
    port = _dut_open_api_port(engines.dut)
    user = engines.dut.username
    good_pw = engines.dut.password
    bad_pw = DEFAULT_BAD_PASSWORD
    cycles = DEFAULT_CYCLES

    run_nginx(engines)
    dut = engines.dut

    if "ok" not in dut.run_cmd("command -v lsof >/dev/null 2>&1 && echo ok || echo no"):
        pytest.skip("lsof not on DUT")

    system = System(force_api=ApiType.NVUE)
    restrictions = system.aaa.authentication.restrictions

    try:
        _apply_fast_fail_auth_profile(restrictions)

        with allure.step("baseline: nginx worker PIDs + AUDIT lsof lines"):
            baseline_pids = _nginx_worker_pids(dut)
            assert baseline_pids, "no nginx worker PIDs from pgrep -f 'nginx: worker'"
            baseline = _audit_lsof_lines(dut, baseline_pids)
            logger.info(
                "nginx worker pids=%s baseline_AUDIT_lsof_lines=%s",
                baseline_pids,
                baseline,
            )

        with allure.step(
            f"{cycles}x cycle: {FAILED_AUTH_ATTEMPTS_PER_CYCLE}x {HTTP_UNAUTHORIZED}, "
            f"{WAIT_AFTER_FAILED_AUTHS_SEC}s wait, 1x {HTTP_OK}"
        ):
            for n in range(1, cycles + 1):
                for _ in range(FAILED_AUTH_ATTEMPTS_PER_CYCLE):
                    code = _nvue_system_http_code_via_dut_curl(dut, port, user, bad_pw)
                    assert code == HTTP_UNAUTHORIZED, f"cycle {n}: expected {HTTP_UNAUTHORIZED}, got {code}"
                time.sleep(WAIT_AFTER_FAILED_AUTHS_SEC)
                code = _nvue_system_http_code_via_dut_curl(dut, port, user, good_pw)
                assert code == HTTP_OK, f"cycle {n}: expected {HTTP_OK}, got {code}"

        with allure.step("final: same nginx workers, AUDIT lsof lines must not grow vs baseline"):
            pids_end = _nginx_worker_pids(dut)
            assert pids_end, "no nginx worker after test"
            assert sorted(pids_end) == sorted(baseline_pids), (
                "nginx worker PID set changed during test; baseline vs final AUDIT sums would not "
                f"be comparable (baseline={baseline_pids}, final={pids_end})"
            )
            final = _audit_lsof_lines(dut, pids_end)
            delta = final - baseline
            logger.info(
                "final_AUDIT_lsof_lines=%s delta=%s (max_extra=%s)",
                final,
                delta,
                MAX_AUDIT_LINE_GROWTH,
            )
            assert delta <= MAX_AUDIT_LINE_GROWTH, (
                f"AUDIT lsof sum must not exceed baseline by more than {MAX_AUDIT_LINE_GROWTH}: "
                f"baseline={baseline} final={final} delta={delta}"
            )
    finally:
        with allure.step("Unset temporary AAA restriction tuning (fail-delay, lockout-reattempt)"):
            _unset_temporary_restriction_tuning(restrictions)
