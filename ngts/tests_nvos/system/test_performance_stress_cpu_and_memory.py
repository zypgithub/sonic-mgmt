import concurrent.futures
import logging
import random
import re
import threading
import time

import pytest

from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.Devices.IbDevice import IbSwitch
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)

STRESS_DURATION_SECONDS = 120
THREAD_DRAIN_TIMEOUT = 60
MAX_TIME_PER_CONNECTION = 7.0
MAX_MEMORY_DELTA_AFTER_CONNECTIONS = 0.2
MAX_MEMORY_DELTA_DURING_TESTING = 0.5
MAX_MEMORY_DELTA_AFTER_TESTING = 0.1
MAX_DISK_IO_KB = 75000


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.ssh_config
@pytest.mark.system
def test_parallel_cli_commands(engines, devices):
    """
    Stress test: run parallel CLI sessions and verify system resource stability.

    Opens up to 40 SSH sessions and runs random CLI command lists (show system,
    show interface, config apply, show firmware, ibdiagnet) in parallel for 2 minutes.

    Validates:
        - SSH connection time < 7s per connection
        - Memory utilization delta < 20% after connections, < 50% during stress, < 10% after
        - Per-CPU busy delta within same thresholds
        - Total disk I/O during stress < 75,000 KB

    Test flow:
        1. Identify disk device for I/O tracking
        2. Open up to 40 SSH sessions (capped from max_sessions - 20)
        3. Capture memory/CPU baseline
        4. Run random CLI commands across all sessions for 120s
        5. Monitor memory/CPU in a separate thread every 10s
        6. After stress: validate memory, CPU, and disk I/O thresholds
        7. Close all sessions
    """
    system = System()
    sessions = []
    stop_event = threading.Event()

    with allure.step("Identify disk device for I/O tracking"):
        field_to_read = 'kB_wrtn'
        initial_output = OutputParsingTool.run_iostat_and_parse(engines.dut)
        disk_device = next((d for d in initial_output.keys() if not d.startswith('loop')), None)

    with allure.step('Get max SSH sessions'):
        ssh_output = OutputParsingTool.parse_json_str_to_dictionary(system.ssh_server.show()).get_returned_value()
        max_sessions = min(int(ssh_output[SystemConsts.SSH_CONFIG_MAX_SESSIONS]) - 20, 40)

    with allure.step('Capture memory and CPU before testing'):
        stats_before = collect_memory_cpu_stats(engines.dut)

    with allure.step(f'Create {max_sessions} SSH sessions'):
        start_time = time.time()
        for conn_no in range(max_sessions):
            logger.info(f"Creating connection {conn_no + 1}/{max_sessions}")
            connection = ConnectionTool.create_ssh_conn(
                engines.dut.ip, engines.dut.username, engines.dut.password
            ).get_returned_value()
            sessions.append(connection)

    with allure.step(f"Verify SSH connection time (expect < {MAX_TIME_PER_CONNECTION}s each)"):
        time_per_connection = (time.time() - start_time) / max_sessions
        assert time_per_connection < MAX_TIME_PER_CONNECTION, \
            f"SSH connection too slow: {time_per_connection:.2f}s per connection (max {MAX_TIME_PER_CONNECTION}s)"

    with allure.step(f'Capture memory and CPU after {max_sessions} connections'):
        stats_after_connections = collect_memory_cpu_stats(engines.dut)

    command_lists = build_command_lists(devices)

    with allure.step("Capture disk stats before stress"):
        pre_stress_output = OutputParsingTool.run_iostat_and_parse(engines.dut)
        pre_stress_kb = int(pre_stress_output[disk_device][field_to_read])

    try:
        with allure.step(f"Run {max_sessions} sessions in parallel for {STRESS_DURATION_SECONDS}s"):
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_sessions)
            monitor_future = executor.submit(monitor_memory_cpu, sessions[-1], stop_event)
            session_futures = [
                executor.submit(run_session, sessions[i], command_lists, stop_event)
                for i in range(max_sessions - 1)
            ]

            with allure.step(f"Stress running for {STRESS_DURATION_SECONDS} seconds"):
                time.sleep(STRESS_DURATION_SECONDS)
                stop_event.set()

            with allure.step("Waiting for threads to drain"):
                all_futures = [monitor_future] + session_futures
                done, not_done = concurrent.futures.wait(all_futures, timeout=THREAD_DRAIN_TIMEOUT)
                if not_done:
                    logger.warning(f"{len(not_done)} threads did not finish in {THREAD_DRAIN_TIMEOUT}s")

                stats_during = []
                try:
                    if monitor_future in done:
                        stats_during = monitor_future.result()
                except Exception as e:
                    logger.warning(f"Monitor thread failed: {e}")

                total_pick_counts = [0] * len(command_lists)
                for future in session_futures:
                    if future in done:
                        try:
                            pick_counts = future.result()
                            for i in range(len(pick_counts)):
                                total_pick_counts[i] += pick_counts[i]
                        except Exception as e:
                            logger.warning(f"Session thread failed: {e}")

            executor.shutdown(wait=False, cancel_futures=True)

            logger.info(f"Command list pick counts: {total_pick_counts}")
            with allure.step(f"Command list selection distribution: {total_pick_counts}"):
                pass

            with allure.step(f"Check disk usage against {MAX_DISK_IO_KB}KB threshold"):
                final_output = OutputParsingTool.run_iostat_and_parse(engines.dut)
                final_kb = int(final_output[disk_device][field_to_read])
                stress_delta_kb = final_kb - pre_stress_kb
                stress_rate = stress_delta_kb / STRESS_DURATION_SECONDS
                total_picks = sum(total_pick_counts)
                ratio = stress_delta_kb / MAX_DISK_IO_KB

                pick_details = '\n'.join(
                    f'  List {i + 1} [{total_pick_counts[i]:>3} picks]: {" -> ".join(cmds)}'
                    for i, cmds in enumerate(command_lists)
                )

                summary = (
                    f'Disk I/O Summary\n'
                    f'================\n'
                    f'Sessions: {max_sessions} | Stress duration: {STRESS_DURATION_SECONDS}s\n'
                    f'\n'
                    f'Stress:\n'
                    f'  Disk delta: {stress_delta_kb}KB\n'
                    f'  Stress rate: {stress_rate:.0f} KB/s\n'
                    f'  Ratio to threshold: {ratio:.2f} ({ratio * 100:.0f}%)\n'
                    f'\n'
                    f'Pick distribution:\n'
                    f'{pick_details}\n'
                    f'Total picks: {total_picks}\n'
                    f'\n'
                    f'Threshold: {MAX_DISK_IO_KB}KB'
                )

                allure.attach('Disk I/O Summary', summary)
                logger.info(f"Disk I/O: {stress_delta_kb}KB written, ratio={ratio:.2f} of {MAX_DISK_IO_KB}KB threshold")

                assert stress_delta_kb <= MAX_DISK_IO_KB, \
                    f"Disk I/O {stress_delta_kb}KB exceeds {MAX_DISK_IO_KB}KB threshold " \
                    f"({ratio:.2f}x). Rate: {stress_rate:.0f} KB/s over {STRESS_DURATION_SECONDS}s"

    finally:
        stop_event.set()

        with allure.step(f'Close {max_sessions} connections'):
            def safe_disconnect(conn):
                try:
                    conn.disconnect()
                except Exception as e:
                    logger.warning(f"Failed to disconnect session: {e}")

            dc_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_sessions)
            dc_futures = [dc_executor.submit(safe_disconnect, c) for c in sessions]
            concurrent.futures.wait(dc_futures, timeout=THREAD_DRAIN_TIMEOUT)
            not_closed = [f for f in dc_futures if not f.done()]
            if not_closed:
                logger.warning(f"{len(not_closed)} sessions did not close in {THREAD_DRAIN_TIMEOUT}s")
            dc_executor.shutdown(wait=False, cancel_futures=True)

        with allure.step('Capture memory and CPU after test'):
            try:
                stats_after = collect_memory_cpu_stats(engines.dut)
            except Exception as e:
                logger.warning(f"Failed to collect post-test stats: {e}")
                stats_after = None

        with allure.step("Validate memory and CPU throughout test"):
            validate_memory_and_cpu(stats_before, stats_after_connections, stats_during, stats_after)


def build_command_lists(devices) -> list:
    """Build CLI command lists for stress testing. IB switches get an extra ibdiagnet list."""
    cmds_list1 = ['nv show system -o json']
    cmds_list2 = ["nv set system message pre-login 'test'", "nv config apply", "nv show system message -o json"]
    cmds_list3 = ['nv show ib device -o json']
    cmds_list4 = ['nv show platform firmware -o json']
    cmds_list5 = ['nv action run ib cmd "ibdiagnet --get_cable_info"']
    cmds_list6 = ['nv show interface -o json']
    if isinstance(devices.dut, IbSwitch):
        return [cmds_list1, cmds_list2, cmds_list3, cmds_list4, cmds_list5, cmds_list6]
    return [cmds_list1, cmds_list2, cmds_list3, cmds_list4, cmds_list6]


def run_session(session, commands_list: list, stop_event: threading.Event) -> list:
    """Run random CLI commands on a session until stop_event is set. Returns per-list pick counts."""
    pick_counts = [0] * len(commands_list)
    while not stop_event.is_set():
        list_index = random.randint(0, len(commands_list) - 1)
        commands = commands_list[list_index]
        pick_counts[list_index] += 1
        with allure.step(f"Running command list {list_index + 1}: {commands}"):
            for cmd in commands:
                if stop_event.is_set():
                    break
                try:
                    session.run_cmd(cmd)
                except Exception as e:
                    logger.warning(f"Command failed: {cmd}: {e}")
                    break
            if not stop_event.is_set():
                stop_event.wait(timeout=7)
    return pick_counts


def monitor_memory_cpu(session, stop_event: threading.Event) -> list:
    """Sample memory and CPU every 10s until stop_event is set. Returns list of stat snapshots."""
    samples = []
    while not stop_event.is_set():
        try:
            logger.info("Checking memory and CPU")
            samples.append(collect_memory_cpu_stats(session))
        except Exception as e:
            logger.warning(f"Failed to collect memory/CPU sample: {e}")
        stop_event.wait(timeout=10)
    return samples


def collect_memory_cpu_stats(engine) -> dict:
    """Collect memory utilization and per-CPU busy % from the device. Returns e.g. {'memory_utilization': 0.45, 'CPU_all': 0.12, ...}."""
    with allure.step("Run memory and mpstat commands"):
        memory_output = OutputParsingTool.parse_json_str_to_dictionary(
            engine.run_cmd('nv show system memory -o json')).verify_result()
        mpstat_output = engine.run_cmd('mpstat -P ALL')
        return parse_memory_and_mpstat(memory_output, mpstat_output)


def parse_memory_and_mpstat(memory: dict, mp_stat: str) -> dict:
    """Parse 'nv show system memory' JSON and 'mpstat -P ALL' text into a flat dict of utilization values."""
    with allure.step("Parse memory and mpstat outputs"):
        result_dict = {
            "memory_utilization": round(
                memory[SystemConsts.MEMORY_PHYSICAL_KEY][SystemConsts.CPU_UTILIZATION_KEY] / 100, 2
            )
        }
        pattern = r"(\d{2}:\d{2}:\d{2} (?:AM|PM) ) (.{3})(.*)(\d{2}\.\d{2})"
        for match in re.findall(pattern, mp_stat):
            assert len(match) == 4, "mpstat parsing issue, we expect to match 4 groups"
            cpu_id = match[1].strip()
            busy_percent = round(1 - (float(match[3]) / 100), 2)
            key = 'CPU_all' if cpu_id.startswith('a') else f"CPU{cpu_id}"
            result_dict[key] = busy_percent
        return result_dict


def validate_memory_and_cpu(before_testing: dict, after_connections: dict, during_testing: list, after_testing: dict) -> None:
    """Assert that memory/CPU deltas stay within thresholds at each test phase."""
    with allure.step("Log all stats"):
        logger.info(f"Memory/CPU before testing: {before_testing}")
        logger.info(f"Memory/CPU after connections: {after_connections}")
        logger.info(f"Memory/CPU during testing: {during_testing}")
        logger.info(f"Memory/CPU after testing: {after_testing}")

    with allure.step("Validate memory and CPU after connections"):
        for key in after_connections:
            delta = after_connections[key] - before_testing[key]
            assert delta < MAX_MEMORY_DELTA_AFTER_CONNECTIONS, \
                f"Unexpected change in {key}: delta={delta:.2f} (max {MAX_MEMORY_DELTA_AFTER_CONNECTIONS}). " \
                f"Before: {before_testing}, After connections: {after_connections}"

    if during_testing:
        with allure.step("Validate memory and CPU during testing"):
            for sample in during_testing:
                for key in sample:
                    delta = sample[key] - before_testing[key]
                    assert delta < MAX_MEMORY_DELTA_DURING_TESTING, \
                        f"Unexpected change in {key}: delta={delta:.2f} (max {MAX_MEMORY_DELTA_DURING_TESTING}). " \
                        f"Before: {before_testing}, During: {sample}"

    if after_testing:
        with allure.step("Validate memory and CPU after testing"):
            for key in after_testing:
                delta = after_testing[key] - before_testing[key]
                assert delta < MAX_MEMORY_DELTA_AFTER_TESTING, \
                    f"Unexpected change in {key}: delta={delta:.2f} (max {MAX_MEMORY_DELTA_AFTER_TESTING}). " \
                    f"Before: {before_testing}, After: {after_testing}"
