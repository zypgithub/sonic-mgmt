"""
gNMI rate limiting (Envoy): unary Capabilities under/over limit, recovery, ON_CHANGE + unary stress,
restart under load. Overload yields local_rate_limited on clients.
"""
import threading
import time

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi import constants as gnmi_consts
from ngts.tests_nvos.system.gnmi import helpers as gnmi_helpers


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_rate_limit_under_threshold(engines, devices):
    """
    Capabilities stays under the global gNMI rate limit with no errors.

    Test flow:
        1. Validate gNMI is running
        2. Single client: throttled Capabilities (~half the limit)
        3. Assert no rate-limit or RPC failures
        4. Max subscribers: parallel clients, same aggregate rate
        5. Assert no rate-limit or RPC failures
    """
    system = System()
    with allure.step("Validate gNMI enabled and running"):
        gnmi_helpers.validate_gnmi_enabled_and_running(system.gnmi_server, engines)

    dut = engines.dut
    username = devices.dut.default_username
    password = devices.dut.default_password
    client = GnmiClient(
        dut.ip,
        GnmiConsts.GNMI_DEFAULT_PORT,
        username,
        password,
        cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
    )
    # Throttle to ~30 req/min (under 60 limit): sleep interval seconds between requests
    rpm_target = gnmi_consts.GNMI_RATE_LIMIT_REQ_PER_MIN // 2
    interval = 60.0 / rpm_target

    success, fail, rate_limit_failures, sample_error = 0, 0, 0, ""
    end_time = time.time() + gnmi_consts.RAMP_DURATION_SEC
    with allure.step(f"Phase 1: single client ~{rpm_target} rpm, {gnmi_consts.RAMP_DURATION_SEC}s"):
        while time.time() < end_time:
            with allure.independent_step("Capabilities request"):
                _, err = client.gnmic_capabilities(skip_cert_verify=True, cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC)
                if gnmi_helpers.is_gnmi_failure(err):
                    fail += 1
                    if gnmi_helpers.is_gnmi_rate_limit_error(err):
                        rate_limit_failures += 1
                    if not sample_error:
                        sample_error = (err or "").strip()[:gnmi_consts.SAMPLE_ERROR_MAX_LEN]
                else:
                    success += 1
            time.sleep(interval)

    gnmi_helpers.attach_rate_limit_result(
        success, fail, sample_error, gnmi_consts.RAMP_DURATION_SEC, "Under threshold: phase 1 single-client ramp",
        rate_limit_failures=rate_limit_failures,
    )

    with allure.step("Assert no rate-limit errors (phase 1)"):
        assert rate_limit_failures == 0, (
            f"Expected no rate-limit errors. "
            f"rate_limit_failures={rate_limit_failures}, other_failures={fail - rate_limit_failures}. "
            f"Sample: {sample_error}"
        )
    with allure.step("Assert no RPC failures (phase 1)"):
        assert fail == 0, f"Expected no failures when under rate limit. success={success} fail={fail}"

    aggregate_rpm_multi = gnmi_consts.GNMI_RATE_LIMIT_REQ_PER_MIN // 2
    rpm_per_client_multi = max(1, aggregate_rpm_multi // gnmi_consts.MAX_GNMI_SUBSCRIBERS)
    interval_multi = 60.0 / rpm_per_client_multi
    results_multi = [None] * gnmi_consts.MAX_GNMI_SUBSCRIBERS
    first_error_multi = {}
    lock_multi = threading.Lock()

    def run_under_threshold_capabilities_multi(thread_id):
        c = GnmiClient(
            dut.ip,
            GnmiConsts.GNMI_DEFAULT_PORT,
            username,
            password,
            cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
        )
        s, f, rl = 0, 0, 0
        until = time.time() + gnmi_consts.RAMP_DURATION_SEC
        while time.time() < until:
            with allure.independent_step(f"Client {thread_id} capabilities request"):
                _, err = c.gnmic_capabilities(skip_cert_verify=True, cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC)
                if gnmi_helpers.is_gnmi_failure(err):
                    f += 1
                    if gnmi_helpers.is_gnmi_rate_limit_error(err):
                        rl += 1
                    with lock_multi:
                        if "err" not in first_error_multi:
                            first_error_multi["err"] = (err or "").strip()[:gnmi_consts.SAMPLE_ERROR_MAX_LEN]
                else:
                    s += 1
            time.sleep(interval_multi)
        results_multi[thread_id] = (s, f, rl)

    with allure.step(
        f"Phase 2: {gnmi_consts.MAX_GNMI_SUBSCRIBERS} clients ~{rpm_per_client_multi} rpm, {gnmi_consts.RAMP_DURATION_SEC}s"
    ):
        phase2_start = time.time()
        # daemon=True + bounded join so a hung gnmic subprocess cannot hang the suite;
        # workers are deadline-bounded, so a still-alive thread after the bounded join
        # indicates a real stuck process and must fail the test.
        threads_multi = [
            threading.Thread(
                target=run_under_threshold_capabilities_multi,
                args=(i,),
                daemon=True,
                name=f"under-thr-phase2-{i}",
            )
            for i in range(gnmi_consts.MAX_GNMI_SUBSCRIBERS)
        ]
        for t in threads_multi:
            t.start()
        phase2_alive = gnmi_helpers.shutdown_threads(
            threads_multi, gnmi_consts.CAPABILITIES_FLOOD_THREAD_JOIN_TIMEOUT_SEC
        )
        assert not phase2_alive, (
            f"Phase-2 under-threshold worker(s) still alive after bounded join: "
            f"{[t.name for t in phase2_alive]}"
        )
        phase2_elapsed_sec = time.time() - phase2_start

    ms = sum(r[0] for r in results_multi if r is not None)
    mf = sum(r[1] for r in results_multi if r is not None)
    mrl = sum(r[2] for r in results_multi if r is not None)
    sample_multi = first_error_multi.get("err", "")

    gnmi_helpers.attach_rate_limit_result(
        ms,
        mf,
        sample_multi,
        phase2_elapsed_sec,
        "Under threshold: phase 2 max parallel clients",
        rate_limit_failures=mrl,
    )

    with allure.step("Assert no rate-limit errors (phase 2)"):
        assert mrl == 0, (
            f"Expected no rate-limit errors with {gnmi_consts.MAX_GNMI_SUBSCRIBERS} clients under threshold. "
            f"rate_limit_failures={mrl}, other_failures={mf - mrl}. Sample: {sample_multi}"
        )
    with allure.step("Assert no RPC failures (phase 2)"):
        assert mf == 0, (
            f"Expected no failures with {gnmi_consts.MAX_GNMI_SUBSCRIBERS} clients under threshold. "
            f"success={ms} fail={mf}"
        )


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_rate_limit_over_threshold(engines, devices):
    """
    Parallel Capabilities exceeds the limit; expect rate limiting, then reachability.

    Test flow:
        1. Validate gNMI is running
        2. Flood Capabilities from parallel clients
        3. Skip if RPM too low; assert rate-limit and failures
        4. Pause; verify Capabilities still works
    """
    system = System()
    with allure.step("Validate gNMI enabled and running"):
        gnmi_helpers.validate_gnmi_enabled_and_running(system.gnmi_server, engines)

    dut = engines.dut
    username = devices.dut.default_username
    password = devices.dut.default_password
    timeout_sec = gnmi_consts.PER_REQUEST_TIMEOUT_OVER_THRESHOLD_SEC

    with allure.step(f"Flood Capabilities ({gnmi_consts.NUM_CLIENTS_OVER_THRESHOLD} clients)"):
        results, elapsed_sec, first_error = gnmi_helpers.run_parallel_capabilities_flood(
            dut,
            username,
            password,
            duration_sec=gnmi_consts.RAMP_DURATION_SEC,
            num_clients=gnmi_consts.NUM_CLIENTS_OVER_THRESHOLD,
            cmd_timeout_sec=timeout_sec,
        )

    total_success = sum(r[0] for r in results if r is not None)
    total_fail = sum(r[1] for r in results if r is not None)
    total_rate_limit_failures = sum(r[2] for r in results if r is not None)
    total_requests = total_success + total_fail
    sample_error = first_error.get("err", "")

    achieved_rpm = total_requests * (60.0 / elapsed_sec) if elapsed_sec > 0 else 0.0
    min_rpm_required = gnmi_consts.GNMI_RATE_LIMIT_REQ_PER_MIN * gnmi_consts.MIN_RPM_FRACTION_TO_REQUIRE_RATE_LIMIT

    gnmi_helpers.attach_rate_limit_result(
        total_success, total_fail, sample_error, elapsed_sec, "Ramp over threshold",
        rate_limit_failures=total_rate_limit_failures,
    )

    with allure.step("Skip if load below threshold"):
        if achieved_rpm < min_rpm_required:
            pytest.skip(
                f"Environment could not generate enough load: achieved {achieved_rpm:.1f} req/min "
                f"< {min_rpm_required:.0f} req/min (fraction of {gnmi_consts.GNMI_RATE_LIMIT_REQ_PER_MIN} limit). "
                f"Cannot reliably assert rate-limit behavior. Total requests={total_requests}, elapsed={elapsed_sec:.1f}s."
            )

    with allure.step("Assert rate-limit errors"):
        assert total_rate_limit_failures > 0, (
            f"Expected at least one rate-limit error at {achieved_rpm:.1f} req/min. "
            f"rate_limit_failures={total_rate_limit_failures}, other_failures={total_fail - total_rate_limit_failures}. "
            f"Sample: {sample_error}"
        )
    with allure.step("Assert RPC failures"):
        assert total_fail > 0, (
            f"Expected failures when over threshold at {achieved_rpm:.1f} req/min. "
            f"success={total_success} fail={total_fail}"
        )

    time.sleep(gnmi_consts.POST_OVERLOAD_PAUSE_SEC)

    with allure.step("Capabilities after overload"):
        check_client = GnmiClient(
            dut.ip,
            GnmiConsts.GNMI_DEFAULT_PORT,
            username,
            password,
            cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
        )
        gnmi_helpers.capabilities_until_success_after_restart(
            check_client, "Post unary overload reachability"
        )


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_rate_limit_recovers_after_over_threshold(engines, devices):
    """
    After overload and rate limiting, a low-rate client recovers without restarting gNMI.

    Test flow:
        1. Validate gNMI is running
        2. Parallel overload until rate limited
        3. Single client low rate (drain window, then check)
        4. Assert clean Capabilities after drain
    """
    system = System()
    with allure.step("Validate gNMI enabled and running"):
        gnmi_helpers.validate_gnmi_enabled_and_running(system.gnmi_server, engines)

    dut = engines.dut
    username = devices.dut.default_username
    password = devices.dut.default_password
    timeout_sec = gnmi_consts.PER_REQUEST_TIMEOUT_OVER_THRESHOLD_SEC

    with allure.step(f"Overload {gnmi_consts.RECOVERY_OVERLOAD_SEC}s ({gnmi_consts.NUM_CLIENTS_OVER_THRESHOLD} clients)"):
        results, p1_elapsed, first_error = gnmi_helpers.run_parallel_capabilities_flood(
            dut,
            username,
            password,
            duration_sec=gnmi_consts.RECOVERY_OVERLOAD_SEC,
            num_clients=gnmi_consts.NUM_CLIENTS_OVER_THRESHOLD,
            cmd_timeout_sec=timeout_sec,
        )

    total_success = sum(r[0] for r in results if r is not None)
    total_fail = sum(r[1] for r in results if r is not None)
    total_rl = sum(r[2] for r in results if r is not None)
    total_req = total_success + total_fail
    achieved_rpm = total_req * (60.0 / p1_elapsed) if p1_elapsed > 0 else 0.0
    min_rpm_required = gnmi_consts.GNMI_RATE_LIMIT_REQ_PER_MIN * gnmi_consts.MIN_RPM_FRACTION_TO_REQUIRE_RATE_LIMIT
    sample_error = first_error.get("err", "")

    gnmi_helpers.attach_rate_limit_result(
        total_success,
        total_fail,
        sample_error,
        p1_elapsed,
        "Recovery phase 1 overload",
        rate_limit_failures=total_rl,
    )

    with allure.step("Assert overload hit rate limiting"):
        if achieved_rpm < min_rpm_required:
            pytest.skip(
                f"Phase 1 load too low ({achieved_rpm:.1f} req/min); cannot verify recovery from overload."
            )
        assert total_rl > 0, f"Expected rate-limit errors in phase 1 at ~{achieved_rpm:.1f} req/min"

    client = GnmiClient(
        dut.ip,
        GnmiConsts.GNMI_DEFAULT_PORT,
        username,
        password,
        cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
    )
    rpm_low = gnmi_consts.GNMI_RATE_LIMIT_REQ_PER_MIN // 2
    interval = 60.0 / rpm_low
    success2, fail2, rl2 = 0, 0, 0
    sample2 = ""
    post_drain_success, post_drain_fail, post_drain_rl = 0, 0, 0

    with allure.step(
        f"Low rate ~{rpm_low} rpm, {gnmi_consts.RECOVERY_LOW_RATE_SEC}s (drain {gnmi_consts.RECOVERY_DRAIN_SEC}s)"
    ):
        p2_start = time.time()
        drain_end = p2_start + gnmi_consts.RECOVERY_DRAIN_SEC
        while time.time() < p2_start + gnmi_consts.RECOVERY_LOW_RATE_SEC:
            _, err = client.gnmic_capabilities(skip_cert_verify=True, cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC)
            in_post_drain = time.time() >= drain_end
            if gnmi_helpers.is_gnmi_failure(err):
                fail2 += 1
                if gnmi_helpers.is_gnmi_rate_limit_error(err):
                    rl2 += 1
                if in_post_drain:
                    post_drain_fail += 1
                    if gnmi_helpers.is_gnmi_rate_limit_error(err):
                        post_drain_rl += 1
                if not sample2:
                    sample2 = (err or "").strip()[:gnmi_consts.SAMPLE_ERROR_MAX_LEN]
            else:
                success2 += 1
                if in_post_drain:
                    post_drain_success += 1
            time.sleep(interval)
        p2_elapsed = time.time() - p2_start

    gnmi_helpers.attach_rate_limit_result(
        success2,
        fail2,
        sample2,
        p2_elapsed,
        "Recovery phase 2 low rate",
        rate_limit_failures=rl2,
    )
    gnmi_helpers.attach_plain_summary(
        f"After overload (all phase-2 samples): success={success2} fail={fail2} rate_limit_fail={rl2}\n"
        f"Post-drain window (after {gnmi_consts.RECOVERY_DRAIN_SEC}s): success={post_drain_success} "
        f"fail={post_drain_fail} rate_limit_fail={post_drain_rl}.\n",
        "Recovery summary",
    )

    with allure.step("Assert recovery after drain"):
        assert post_drain_success > 0, (
            f"Expected at least one successful low-rate request in post-drain window; "
            f"post_drain_success={post_drain_success}, sample={sample2}"
        )
        assert post_drain_rl == 0, (
            f"Expected no local_rate_limited after drain window; got {post_drain_rl}. "
            f"other_fail={post_drain_fail - post_drain_rl} sample={sample2}"
        )
        assert post_drain_fail == 0, (
            f"Expected no failures at ~{rpm_low} rpm after recovery (post-drain). "
            f"post_drain_success={post_drain_success} post_drain_fail={post_drain_fail}"
        )


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_rate_limit_stream_on_change_over_threshold(engines, devices):
    """
    ON_CHANGE subscribe is clean at slow NVUE rate; under unary flood, Capabilities hits rate limit.

    Test flow:
        1. Validate gNMI is running
        2. Slow toggles + ON_CHANGE stream — no failures
        3. Fast toggles + parallel Capabilities + ON_CHANGE stream
        4. Assert Capabilities rate-limited; attach stream outcome
        5. Capabilities after stress
    """
    system = System()
    with allure.step("Validate gNMI enabled and running"):
        gnmi_helpers.validate_gnmi_enabled_and_running(system.gnmi_server, engines)

    dut = engines.dut
    username = devices.dut.default_username
    password = devices.dut.default_password
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value
    prefix = f"interfaces/interface[name={selected_port.name}]"
    path = "state/description"
    extra_on_change = "--stream-mode on-change"
    timeout_fast = gnmi_consts.PER_REQUEST_TIMEOUT_OVER_THRESHOLD_SEC

    def run_toggle(interval_sec, stop_ev, counter):
        vals = ("rl-oc-rate-a", "rl-oc-rate-b")
        i = 0
        while not stop_ev.is_set():
            selected_port.interface.set(NvosConst.DESCRIPTION, vals[i % 2], apply=True).verify_result()
            counter[0] += 1
            i += 1
            if stop_ev.wait(timeout=interval_sec):
                break

    def run_toggle_until_deadline(high_end, counter, stop_ev):
        """Toggle as fast as NVUE allows until wall-clock deadline (no sleep beyond pacing apply)."""
        vals = ("rl-oc-rate-a", "rl-oc-rate-b")
        i = 0
        while not stop_ev.is_set() and time.time() < high_end:
            selected_port.interface.set(NvosConst.DESCRIPTION, vals[i % 2], apply=True).verify_result()
            counter[0] += 1
            i += 1
            remaining = high_end - time.time()
            if remaining <= 0:
                break
            # Wait in a way that can be interrupted so the worker exits promptly when stop_ev is set.
            if stop_ev.wait(timeout=min(gnmi_consts.ON_CHANGE_HIGH_TOGGLE_INTERVAL_SEC, remaining)):
                break

    client = GnmiClient(
        dut.ip,
        GnmiConsts.GNMI_DEFAULT_PORT,
        username,
        password,
        cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
    )

    with allure.step("ON_CHANGE low rate + slow toggles"):
        stop1 = threading.Event()
        ctr1 = [0]
        t1 = threading.Thread(target=run_toggle, args=(gnmi_consts.ON_CHANGE_LOW_TOGGLE_INTERVAL_SEC, stop1, ctr1))
        t1.start()
        out1, err1 = gnmi_helpers.stream_subscribe_for_duration(
            client,
            prefix,
            path,
            gnmi_consts.ON_CHANGE_LOW_PHASE_SEC,
            extra_subscribe_flags=extra_on_change,
        )
        stop1.set()
        t1.join()
        assert not gnmi_helpers.output_shows_rate_limit_or_grpc_failure(out1, err1), (
            f"Low-rate ON_CHANGE stream should not fail. err={err1[:gnmi_consts.SAMPLE_ERROR_MAX_LEN]}"
        )

    with allure.step("ON_CHANGE high load + Capabilities flood"):
        ctr2 = [0]
        cap_agg = {"success": 0, "fail": 0, "rate_limit": 0}
        cap_lock = threading.Lock()
        high_start = time.time()
        high_end = high_start + gnmi_consts.ON_CHANGE_HIGH_PHASE_SEC
        # Explicit stop event so workers can be shut down deterministically (not only via deadline).
        stop_high = threading.Event()

        def cap_worker():
            c = GnmiClient(
                dut.ip,
                GnmiConsts.GNMI_DEFAULT_PORT,
                username,
                password,
                cmd_time=timeout_fast,
            )
            while not stop_high.is_set() and time.time() < high_end:
                _, err = c.gnmic_capabilities(skip_cert_verify=True, cmd_time=timeout_fast)
                with cap_lock:
                    if gnmi_helpers.is_gnmi_failure(err):
                        cap_agg["fail"] += 1
                        if gnmi_helpers.is_gnmi_rate_limit_error(err):
                            cap_agg["rate_limit"] += 1
                    else:
                        cap_agg["success"] += 1

        # daemon=True is a safety net so a stuck worker cannot keep the interpreter
        # alive past the suite; the explicit stop_high + alive-check assert below is the
        # primary mechanism for clean shutdown.
        cap_threads = [
            threading.Thread(target=cap_worker, daemon=True)
            for _ in range(gnmi_consts.NUM_ON_CHANGE_HIGH_CAPABILITY_SPAMMERS)
        ]
        for t in cap_threads:
            t.start()
        toggle_t = threading.Thread(
            target=run_toggle_until_deadline, args=(high_end, ctr2, stop_high), daemon=True
        )
        toggle_t.start()

        client2 = GnmiClient(
            dut.ip,
            GnmiConsts.GNMI_DEFAULT_PORT,
            username,
            password,
            cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
        )
        try:
            out2, err2 = gnmi_helpers.stream_subscribe_for_duration(
                client2,
                prefix,
                path,
                gnmi_consts.ON_CHANGE_HIGH_PHASE_SEC,
                extra_subscribe_flags=extra_on_change,
            )
        finally:
            # Signal workers to stop before joining. Without this, they only stop when
            # the wall-clock deadline passes, and nothing forces termination on error.
            stop_high.set()

        cap_alive = gnmi_helpers.shutdown_threads(
            cap_threads, gnmi_consts.ON_CHANGE_CAP_THREAD_JOIN_TIMEOUT_SEC
        )
        toggle_alive = gnmi_helpers.shutdown_threads(
            [toggle_t], gnmi_consts.ON_CHANGE_TOGGLE_THREAD_JOIN_TIMEOUT_SEC
        )
        assert not cap_alive, (
            f"ON_CHANGE cap_worker thread(s) still alive after stop + join: "
            f"{[t.name for t in cap_alive]}"
        )
        assert not toggle_alive, (
            f"ON_CHANGE toggle thread still alive after stop + join: "
            f"{[t.name for t in toggle_alive]}"
        )

        cap_total = cap_agg["success"] + cap_agg["fail"]
        cap_rpm = cap_total * (60.0 / gnmi_consts.ON_CHANGE_HIGH_PHASE_SEC) if gnmi_consts.ON_CHANGE_HIGH_PHASE_SEC else 0.0
        toggles_per_min = ctr2[0] * (60.0 / gnmi_consts.ON_CHANGE_HIGH_PHASE_SEC) if gnmi_consts.ON_CHANGE_HIGH_PHASE_SEC else 0.0
        min_rpm_required = gnmi_consts.GNMI_RATE_LIMIT_REQ_PER_MIN * gnmi_consts.MIN_RPM_FRACTION_TO_REQUIRE_RATE_LIMIT
        gnmi_helpers.attach_plain_summary(
            f"High phase: NVUE toggles≈{ctr2[0]} (~{toggles_per_min:.1f}/min on subscribed path)\n"
            f"Parallel capabilities: total={cap_total} (~{cap_rpm:.1f}/min) "
            f"success={cap_agg['success']} fail={cap_agg['fail']} rate_limit={cap_agg['rate_limit']}\n"
            f"ON_CHANGE stream stderr sample:\n{(err2 or '')[:gnmi_consts.SAMPLE_ERROR_MAX_LEN]}",
            "ON_CHANGE high-load summary",
        )

    stream_hit = gnmi_helpers.output_shows_rate_limit_or_grpc_failure(out2, err2)
    with allure.step("Assert Capabilities rate-limited"):
        if cap_rpm < min_rpm_required:
            pytest.skip(
                f"Could not generate enough unary load with stream: ~{cap_rpm:.1f} req/min "
                f"< {min_rpm_required:.0f} req/min."
            )
        assert cap_agg["rate_limit"] > 0, (
            f"Expected capabilities to see local_rate_limited under combined load "
            f"(cap_rpm≈{cap_rpm:.1f}). fail={cap_agg['fail']} rl={cap_agg['rate_limit']}"
        )

    with allure.step("Attach stream outcome vs unary limit"):
        if stream_hit:
            gnmi_helpers.attach_plain_summary(
                "Subscribe stream showed rate-limit or gRPC-class errors while unary was limited.",
                "ON_CHANGE stream: errors observed",
            )
        else:
            gnmi_helpers.attach_plain_summary(
                "Subscribe stream stderr/stdout had no matched failure markers while parallel "
                "capabilities hit local_rate_limited; global limit may apply primarily to unary RPCs.",
                "ON_CHANGE stream: clean under unary rate limit",
            )

    with allure.step("Capabilities after ON_CHANGE"):
        _, err = client.gnmic_capabilities(skip_cert_verify=True, cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC)
        assert not gnmi_helpers.is_gnmi_failure(err), f"gNMI capabilities failed after ON_CHANGE test: {err}"


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_rate_limit_restart_gnmi_under_load(engines, devices):
    """
    NVUE restart of gNMI while Capabilities flood runs; service returns and limiting still applies.

    Test flow:
        1. Validate gNMI is running
        2. Start flood threads and warm up
        3. Disable/enable gNMI via NVUE
        4. Validate gNMI; pause flood, drain, Capabilities check
        5. Resume flood; assert limiting still seen
        6. Pause flood, drain; Capabilities must succeed (no errors) once rate drops
        7. Stop threads
    """
    system = System()
    dut = engines.dut
    username = devices.dut.default_username
    password = devices.dut.default_password
    timeout_sec = gnmi_consts.PER_REQUEST_TIMEOUT_OVER_THRESHOLD_SEC
    stop_attackers = threading.Event()
    pause_attackers = threading.Event()
    post_restart = {"rl": 0, "fail": 0, "ok": 0}
    post_restart_lock = threading.Lock()

    def attacker_loop():
        client = GnmiClient(
            dut.ip,
            GnmiConsts.GNMI_DEFAULT_PORT,
            username,
            password,
            cmd_time=timeout_sec,
        )
        while not stop_attackers.is_set():
            while pause_attackers.is_set() and not stop_attackers.is_set():
                time.sleep(0.05)
            if stop_attackers.is_set():
                break
            _, err = client.gnmic_capabilities(skip_cert_verify=True, cmd_time=timeout_sec)
            if stop_attackers.is_set():
                break
            with post_restart_lock:
                if gnmi_helpers.is_gnmi_failure(err):
                    post_restart["fail"] += 1
                    if gnmi_helpers.is_gnmi_rate_limit_error(err):
                        post_restart["rl"] += 1
                else:
                    post_restart["ok"] += 1

    # daemon=True is a safety net so a stuck attacker cannot survive the suite; the
    # stop_attackers event + alive-check assert in the finally block is the primary shutdown path.
    threads = [
        threading.Thread(target=attacker_loop, daemon=True)
        for _ in range(gnmi_consts.NUM_CLIENTS_OVER_THRESHOLD)
    ]

    with allure.step("Validate gNMI enabled and running"):
        gnmi_helpers.validate_gnmi_enabled_and_running(system.gnmi_server, engines)

    # One parent step for the whole time attacker threads run so GnmiClient's per-RPC Allure
    # nested steps land here (allure_commons seeds worker-thread context from the main thread).
    with allure.step(
        f"Capabilities flood during restart scenario ({gnmi_consts.NUM_CLIENTS_OVER_THRESHOLD} threads)"
    ):
        with allure.step(f"Start {gnmi_consts.NUM_CLIENTS_OVER_THRESHOLD} attacker threads"):
            for t in threads:
                t.start()
        try:
            with allure.step(f"Warm up {gnmi_consts.RESTART_UNDER_LOAD_WARMUP_SEC}s"):
                time.sleep(gnmi_consts.RESTART_UNDER_LOAD_WARMUP_SEC)

            with allure.step("NVUE restart gNMI"):
                with allure.step("Disable gNMI + apply"):
                    with post_restart_lock:
                        post_restart["rl"] = 0
                        post_restart["fail"] = 0
                        post_restart["ok"] = 0
                    system.gnmi_server.disable_gnmi_server(apply=False)
                    NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation=True)
                with allure.step(f"Wait {gnmi_consts.GNMI_RESTART_POST_DISABLE_WAIT_SEC}s"):
                    time.sleep(gnmi_consts.GNMI_RESTART_POST_DISABLE_WAIT_SEC)
                with allure.step("Enable gNMI + apply"):
                    system.gnmi_server.enable_gnmi_server(apply=False)
                    NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation=True)
                with allure.step(f"Wait {gnmi_consts.GNMI_RESTART_POST_ENABLE_WAIT_SEC}s"):
                    time.sleep(gnmi_consts.GNMI_RESTART_POST_ENABLE_WAIT_SEC)

            with allure.step("Validate gNMI after restart"):
                gnmi_helpers.wait_for_gnmi_ready(engines)
                gnmi_helpers.validate_gnmi_enabled_and_running(system.gnmi_server, engines)

            with allure.step("Pause flood; Capabilities reachability"):
                check_client = GnmiClient(
                    dut.ip,
                    GnmiConsts.GNMI_DEFAULT_PORT,
                    username,
                    password,
                    cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
                )
                pause_attackers.set()
                try:
                    with allure.step(f"Drain {gnmi_consts.RESTART_CAPABILITIES_PAUSE_DRAIN_SEC}s"):
                        time.sleep(gnmi_consts.RESTART_CAPABILITIES_PAUSE_DRAIN_SEC)
                    gnmi_helpers.capabilities_until_success_after_restart(
                        check_client, "Post-restart gNMI reachability"
                    )
                finally:
                    pause_attackers.clear()

            with allure.step("Resume flood; assert limiting"):
                with allure.step(f"Observe flood {gnmi_consts.RESTART_POST_ENABLE_VERIFY_FLOOD_SEC}s"):
                    time.sleep(gnmi_consts.RESTART_POST_ENABLE_VERIFY_FLOOD_SEC)
                with allure.step("Attach outcomes; assert limiting"):
                    summary = (
                        f"Post-restart sample (attackers still running): ok={post_restart['ok']} "
                        f"fail={post_restart['fail']} rate_limit={post_restart['rl']}\n"
                    )
                    gnmi_helpers.attach_plain_summary(summary, "Restart under load: post-enable client outcomes")
                    assert post_restart["rl"] > 0 or post_restart["fail"] > 0, (
                        "Expected continued load after restart to hit rate limit or other RPC failures; "
                        f"got ok={post_restart['ok']} fail={post_restart['fail']} rl={post_restart['rl']}"
                    )

            with allure.step(
                "Pause flood; drain; verify Capabilities clean after rate drops (no errors)"
            ):
                settle_client = GnmiClient(
                    dut.ip,
                    GnmiConsts.GNMI_DEFAULT_PORT,
                    username,
                    password,
                    cmd_time=gnmi_consts.PER_REQUEST_TIMEOUT_SEC,
                )
                pause_attackers.set()
                with allure.step(
                    f"Drain {gnmi_consts.RESTART_POST_LIMITING_DRAIN_SEC}s while flood paused"
                ):
                    time.sleep(gnmi_consts.RESTART_POST_LIMITING_DRAIN_SEC)
                gnmi_helpers.capabilities_until_success_after_restart(
                    settle_client,
                    "After limiting: Capabilities with no gNMI errors",
                )
                # Leave pause set until outer finally stops threads (avoid a brief window with no pause).

        finally:
            with allure.step("Stop flood threads"):
                stop_attackers.set()
                # Clear pause so any worker blocked in the pause loop observes stop_attackers.
                pause_attackers.clear()
                still_alive = gnmi_helpers.shutdown_threads(
                    threads, gnmi_consts.ATTACKER_THREAD_JOIN_TIMEOUT_SEC
                )
                assert not still_alive, (
                    f"Attacker thread(s) still alive after stop_attackers.set() + join: "
                    f"{[t.name for t in still_alive]}. They may leak into subsequent tests."
                )
