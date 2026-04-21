import logging
import threading
import time
import pytest

from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import BmcUsers
from ngts.nvos_tools.infra.BmcTool import BmcTool

logger = logging.getLogger()


def _ssh_engine_from_create(result_obj, label, *, peer_description="DUT"):
    """
    Consume ``ConnectionTool.create_ssh_conn``'s ResultObj and return a ``LinuxSshEngine``.

    ``create_ssh_conn`` validates reachability via ``is_connected()`` before reporting success.
    On failure it can leave ``returned_value`` as an exception / error string; callers must not
    treat a bare ``returned_value`` as an engine. We assert success, engine type, and mark the
    ResultObj consumed.
    """
    if not result_obj.result:
        detail = result_obj.returned_value
        if detail is None:
            detail = result_obj.info
        pytest.fail(
            f"{label}: could not open SSH session to {peer_description}: {detail}"
        )
    engine = result_obj.returned_value
    if not isinstance(engine, LinuxSshEngine):
        pytest.fail(
            f"{label}: expected LinuxSshEngine after successful create_ssh_conn, "
            f"got {type(engine).__name__}: {engine!r}"
        )
    result_obj.ignore_result()
    return engine


def _bmc_ssh_engine(ip, username, password, label):
    """
    Open SSH to the BMC without ``ConnectionTool.create_ssh_conn``.

    BMC busybox/ash environments typically do not ship ``lslogins``, so
    ``ConnectionTool.is_connected()`` / ``create_ssh_conn`` fails with e.g.
    ``lslogins: command not found`` even when SSH is fine. We instantiate
    ``LinuxSshEngine`` and run a minimal command to prove the session works.
    """
    engine = LinuxSshEngine(ip=ip, username=username, password=password)
    probe_token = "nvos_bmc_ssh_ok"
    try:
        out = engine.run_cmd(f"echo {probe_token}")
    except Exception as ex:
        pytest.fail(
            f"{label}: BMC SSH session not usable "
            f"(does not use ConnectionTool.create_ssh_conn: BMC often lacks lslogins): {ex}"
        )
    if probe_token not in (out or ""):
        pytest.fail(
            f"{label}: BMC SSH echo probe failed (unexpected output): {out!r}"
        )
    return engine


def _normalize_iorw_output(raw):
    """Normalize SSH command output for stable string comparison."""
    if not raw:
        return ""
    text = raw.replace("\r", "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _collect_uniform_iorw_baseline(engine, cmd, worker_label):
    """
    Collect a stable baseline from `engine` before parallel workers run.

    Baseline mismatches fail the test immediately; they must not populate the
    same channel as parallel-storm mismatches (see `_parallel_bounded_read_worker`).
    """
    base_output = ""
    for i in range(5):
        logger.info(
            "%s baseline sample #%s at %s", worker_label, i, time.time()
        )
        out = _normalize_iorw_output(engine.run_cmd(cmd))
        if not out:
            pytest.fail(f"Baseline for {worker_label}: empty read output (sample #{i})")
        if base_output == "":
            base_output = out
        elif out != base_output:
            pytest.fail(
                f"Baseline for {worker_label}: output mismatch; "
                f"expected={base_output!r} actual={out!r}"
            )
    logger.info("Baseline for %s: %s", worker_label, base_output)
    return base_output


def _wait_iorw_recovery(
    engine,
    cmd,
    baseline,
    *,
    label,
    settle_s=1.0,
    consecutive_ok=5,
    timeout_s=45.0,
    poll_interval_s=0.25,
):
    """
    After parallel stress: let the path settle, then require `consecutive_ok` matching reads
    on `baseline` within `timeout_s` (polling every `poll_interval_s`).
    """
    time.sleep(settle_s)
    deadline = time.time() + timeout_s
    streak = 0
    last_out = None
    while time.time() < deadline:
        last_out = _normalize_iorw_output(engine.run_cmd(cmd))
        if last_out == baseline:
            streak += 1
            if streak >= consecutive_ok:
                logger.info(
                    "%s recovery OK: %s consecutive reads matched baseline after %.2fs settle",
                    label,
                    streak,
                    settle_s,
                )
                return
        else:
            streak = 0
            logger.info(
                "%s recovery poll: mismatch (reset streak); actual=%r",
                label,
                last_out,
            )
        time.sleep(poll_interval_s)
    pytest.fail(
        f"{label}: CPLD read did not stabilize to baseline within {timeout_s}s "
        f"(needed {consecutive_ok} consecutive matches). "
        f"baseline={baseline!r} last_read={last_out!r}"
    )


def _parallel_bounded_read_worker(
    thread_label,
    engine,
    stop_event,
    failure_lock,
    failure_msg,
    start_time,
    read_barrier,
    cmd,
    base_output,
):
    """CPLD read loop after `base_output` was fixed on main; `read_barrier` aligns parallel storm."""

    while time.time() < start_time:
        time.sleep(0.05)

    # Unblock together so the first (and ongoing) SSH read bursts overlap maximally.
    read_barrier.wait()

    deadline = time.time() + 60
    iter = 1

    while time.time() < deadline and not stop_event.is_set():
        logger.info(f"Thread:{thread_label}, Time:{time.time()}, Iter #{iter}, deadline:{deadline}")
        out = _normalize_iorw_output(engine.run_cmd(cmd))
        if out != base_output:
            with failure_lock:
                if failure_msg[0] is None:
                    failure_msg[0] = (
                        f"{thread_label}: output mismatch; "
                        f"expected={base_output!r} actual={out!r}"
                    )
            stop_event.set()
            return
        iter = iter + 1


@pytest.mark.platform
def test_platform_cpld_parellel_read_error(engines, topology_obj):
    """
    CPLD / iorw parallel read consistency

    Test flow:
    1. Log in to the switch (use existing DUT SSH session).
    2. Open three worker SSH sessions and collect five-run baselines on the main thread (one per worker).
    3. Start thread1: bounded loop of sudo iorw -r; each output must equal that session's baseline.
    4. Start thread2: bounded loop of sudo iorw -r -b 0x2500 -l32; match that session's baseline.
    5. Start thread3: bounded BMC i2ctransfer reads; match that session's baseline.
    6. Workers synchronize on a threading.Barrier so all three begin the read loop together.
    7. Main thread waits for all workers to finish. The test passes only if at least one worker
       records an output mismatch during the parallel storm; baseline inconsistency fails earlier.
    8. Recovery: after worker SSH teardown, brief settle then DUT polling until several
       consecutive reads match thread1/thread2 stabilized baselines (or timeout).

    Note: The DUT kernel or CPLD driver may still serialize access to the same device; the barrier
    maximizes overlap from the test harness (three independent SSH sessions, aligned start).
    """

    iorw_read = "sudo iorw -r"
    iorw_read_32 = "sudo iorw -r -b 0x2500 -l32"
    iorw_read_32_bmc = "i2ctransfer -f -y 5 w2@0x31 0x25 0x00 r32"

    conn1 = None
    conn2 = None
    conn3 = None
    dut = engines.dut

    root_pass = BmcUsers.root.another_password
    with allure.step("get bmc addresses"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)
    bmc_ip_address = ip_addresses["IPv4"]

    conn1 = _ssh_engine_from_create(
        ConnectionTool.create_ssh_conn(dut.ip, dut.username, dut.password), "thread1"
    )
    conn2 = _ssh_engine_from_create(
        ConnectionTool.create_ssh_conn(dut.ip, dut.username, dut.password), "thread2"
    )
    conn3 = _bmc_ssh_engine(bmc_ip_address, "root", root_pass, "thread3")

    stop_event = threading.Event()
    failure_lock = threading.Lock()
    failure_msg = [None]

    recovery_ref_iorw = None
    recovery_ref_iorw32 = None

    try:
        start = time.time() + 5
        read_barrier = threading.Barrier(3)

        with allure.step("Collect per-session iorw baselines (main thread, before parallel storm)"):
            base_output_1 = _collect_uniform_iorw_baseline(conn1, iorw_read, "thread1")
            base_output_2 = _collect_uniform_iorw_baseline(conn2, iorw_read_32, "thread2")
            base_output_bmc = _collect_uniform_iorw_baseline(
                conn3, iorw_read_32_bmc, "thread3"
            )

        recovery_ref_iorw = base_output_1
        recovery_ref_iorw32 = base_output_2

        with allure.step("Create thread1 (parallel bounded CPLD reads)"):
            thread1 = threading.Thread(
                target=_parallel_bounded_read_worker,
                args=(
                    "thread1",
                    conn1,
                    stop_event,
                    failure_lock,
                    failure_msg,
                    start,
                    read_barrier,
                    iorw_read,
                    base_output_1,
                ),
                name="cpld-iorw-thread1",
            )
        with allure.step("Create thread2 (parallel bounded CPLD reads)"):
            thread2 = threading.Thread(
                target=_parallel_bounded_read_worker,
                args=(
                    "thread2",
                    conn2,
                    stop_event,
                    failure_lock,
                    failure_msg,
                    start,
                    read_barrier,
                    iorw_read_32,
                    base_output_2,
                ),
                name="cpld-iorw-thread2",
            )
        with allure.step("Create thread3 (parallel bounded CPLD reads)"):
            thread3 = threading.Thread(
                target=_parallel_bounded_read_worker,
                args=(
                    "thread3",
                    conn3,
                    stop_event,
                    failure_lock,
                    failure_msg,
                    start,
                    read_barrier,
                    iorw_read_32_bmc,
                    base_output_bmc,
                ),
                name="bmc-iorw-thread2",
            )
        with allure.step("Start thread1, thread2 and thread3 (parallel bounded CPLD reads)"):
            thread1.start()
            thread2.start()
            thread3.start()

        # Workers: ~5s wall-clock align + barrier + 60s loop; headroom for slow SSH.
        join_timeout = 90
        with allure.step("Wait for all worker threads to finish"):
            thread1.join(timeout=join_timeout)
            thread2.join(timeout=join_timeout)
            thread3.join(timeout=join_timeout)

        if failure_msg[0] is None:
            pytest.fail(
                "Expected at least one CPLD read mismatch under parallel stress, but all threads "
                "finished with consistent output (no mismatch observed)."
            )
        logger.info("Parallel CPLD read mismatch observed (expected for pass): %s", failure_msg[0])
    finally:
        with allure.step("Close extra SSH sessions used by worker threads"):
            for conn in (conn1, conn2, conn3):
                if conn is None:
                    continue
                try:
                    conn.disconnect()
                except Exception as ex:
                    logger.warning("disconnect failed: %s", ex)
                finally:
                    logger.info(f"Disconnected: {conn}")

    # Runs only when the parallel-storm assertions above succeeded; avoids masking pytest.fail from
    # that step with recovery failures (recovery must not live in finally).
    with allure.step("Confirm CPLD read recovery (settle + consecutive matching polls)"):
        time.sleep(1.0)
        if recovery_ref_iorw is not None:
            _wait_iorw_recovery(
                dut,
                iorw_read,
                recovery_ref_iorw,
                settle_s=0.0,
                label="DUT sudo iorw -r vs thread1 baseline",
            )
        if recovery_ref_iorw32 is not None:
            _wait_iorw_recovery(
                dut,
                iorw_read_32,
                recovery_ref_iorw32,
                settle_s=0.0,
                label="DUT sudo iorw -r -b 0x2500 -l32 vs thread2 baseline",
            )

    with allure.step("Validate system health should be OK"):
        system = System()
        system.validate_health_status("OK")
