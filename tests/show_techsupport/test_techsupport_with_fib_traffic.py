import logging
import pytest
import time

from datetime import datetime
from random import randint

from tests.common.dualtor.mux_simulator_control import mux_server_url             # noqa: F401
from tests.common.fixtures.fib_utils import fib_info_files, single_fib_for_duts   # noqa: F401
from tests.common.fixtures.ptfhost_utils import copy_ptftests_directory           # noqa: F401
from tests.common.fixtures.ptfhost_utils import ptf_test_port_map_active_active
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import is_ipv6_only_topology, wait_until
from tests.ptf_runner import ptf_runner
from test_techsupport import SUCCESS_CODE

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]

PTF_QLEN = 20000
TECHSUPPORT_TIMEOUT = 900
FIB_TRAFFIC_STARTED_PATTERN = "Sent Ether"
FIB_TRAFFIC_FAILURE_PATTERN = "Traceback|AssertionError|FAILED|FAILURES"


@pytest.fixture(scope="module")
def ignore_ttl(duthosts):
    # Multi-ASIC packets can be routed through internal hops, which changes TTL.
    for duthost in duthosts:
        if duthost.sonichost.is_multi_asic:
            return True
    return False


def is_fib_traffic_started(ptfhost, log_file):
    result = ptfhost.shell(
        f"test -f {log_file} && grep -q '{FIB_TRAFFIC_STARTED_PATTERN}' {log_file}",
        module_ignore_errors=True
    )
    return result["rc"] == SUCCESS_CODE


def is_fib_traffic_running(ptfhost, log_file):
    result = ptfhost.shell(f"pgrep -f {log_file}", module_ignore_errors=True)
    return result["rc"] == SUCCESS_CODE and len(result["stdout_lines"]) > 0


def start_fib_traffic(request, ptfhost, tbinfo, duthosts, fib_info_files,
                      ignore_ttl, single_fib_for_duts, duts_running_config_facts, duts_minigraph_facts):
    timestamp = datetime.now().strftime('%Y-%m-%d-%H:%M:%S.%f')
    log_file = f"/tmp/techsupport_fib_traffic.FibTest.{timestamp}.log"
    switch_type = duthosts[0].facts.get('switch_type')
    asic_type = duthosts[0].facts['asic_type']
    mux_server_url = None
    active_active_ports_mux_status = None
    if 'dualtor' in tbinfo['topo']['name']:
        mux_server_url = request.getfixturevalue("mux_server_url")
        active_active_ports_mux_status = request.getfixturevalue("mux_status_from_nic_simulator")()

    ptf_runner(
        ptfhost,
        "ptftests",
        "fib_test.FibTest",
        platform_dir="ptftests",
        params={
            "fib_info_files": fib_info_files[:3],
            "ptf_test_port_map": ptf_test_port_map_active_active(
                ptfhost,
                tbinfo,
                duthosts,
                mux_server_url,
                duts_running_config_facts,
                duts_minigraph_facts,
                active_active_ports_mux_status
            ),
            "ipv4": not is_ipv6_only_topology(tbinfo),
            "ipv6": True,
            "testbed_mtu": 1514,
            "test_balancing": False,
            "ignore_ttl": ignore_ttl,
            "single_fib_for_duts": single_fib_for_duts,
            "switch_type": switch_type,
            "asic_type": asic_type,
            "topo_type": tbinfo['topo']['type']
        },
        log_file=log_file,
        qlen=PTF_QLEN,
        socket_recv_size=16384,
        is_python3=True,
        async_mode=True
    )

    pytest_assert(
        wait_until(10, 1, 0, is_fib_traffic_started, ptfhost, log_file),
        f"FIB traffic did not send packets before techsupport started. PTF log: {log_file}"
    )
    return log_file


def stop_fib_traffic(ptfhost, log_file):
    result = ptfhost.shell(f"pgrep -f {log_file}", module_ignore_errors=True)
    for pid in result.get("stdout_lines", []):
        ptfhost.shell(f"kill {pid}", module_ignore_errors=True)


def validate_fib_traffic_result(ptfhost, log_file):
    pytest_assert(
        is_fib_traffic_started(ptfhost, log_file),
        f"FIB traffic did not send any packet. PTF log: {log_file}"
    )
    result = ptfhost.shell(
        f"grep -E -q '{FIB_TRAFFIC_FAILURE_PATTERN}' {log_file}",
        module_ignore_errors=True
    )
    pytest_assert(
        result["rc"] != SUCCESS_CODE,
        f"FIB traffic failed. PTF log: {log_file}"
    )


def get_techsupport_cmd(duthost, since):
    opt = "-r" if duthost.sonic_release not in ["201811", "201911"] else ""
    return f'show techsupport {opt} --since="{since}"'


def start_techsupport(duthost, since):
    logger.debug("Running show techsupport with FIB traffic ... ")
    return duthost.command(
        get_techsupport_cmd(duthost, since),
        module_ignore_errors=True,
        module_async=True
    )


def run_techsupport_with_fib_traffic(request, duthost, ptfhost, tbinfo, duthosts, fib_info_files, ignore_ttl,
                                     single_fib_for_duts, duts_running_config_facts, duts_minigraph_facts, since):
    traffic_log_files = []
    traffic_log_file = start_fib_traffic(
        request,
        ptfhost,
        tbinfo,
        duthosts,
        fib_info_files,
        ignore_ttl,
        single_fib_for_duts,
        duts_running_config_facts,
        duts_minigraph_facts
    )
    traffic_log_files.append(traffic_log_file)
    pool, async_result = start_techsupport(duthost, since)
    result = None

    try:
        start_time = time.time()
        while not async_result.ready():
            if time.time() - start_time > TECHSUPPORT_TIMEOUT:
                pytest.fail("show techsupport command failed to finish within timeout")

            if not is_fib_traffic_running(ptfhost, traffic_log_file):
                logger.info("FIB traffic finished while show techsupport is still running. PTF log: %s", traffic_log_file)
                traffic_log_file = start_fib_traffic(
                    request,
                    ptfhost,
                    tbinfo,
                    duthosts,
                    fib_info_files,
                    ignore_ttl,
                    single_fib_for_duts,
                    duts_running_config_facts,
                    duts_minigraph_facts
                )
                traffic_log_files.append(traffic_log_file)
            time.sleep(1)

        result = async_result.get()
    finally:
        for log_file in traffic_log_files:
            stop_fib_traffic(ptfhost, log_file)
        pool.terminate()
        pool.join()

    return result, traffic_log_files


def test_techsupport_with_fib_traffic(request, duthosts, enum_rand_one_per_hwsku_hostname,
                                      ptfhost, tbinfo, fib_info_files, ignore_ttl,  # noqa F811
                                      single_fib_for_duts, duts_running_config_facts,  # noqa F811
                                      duts_minigraph_facts, copy_ptftests_directory):  # noqa F811
    """
    Verify show techsupport can finish while FIB-style PTF traffic is running.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    since = request.config.getoption("--logs_since") or f"{randint(1, 5)} minute ago"

    result, traffic_log_files = run_techsupport_with_fib_traffic(
        request,
        duthost,
        ptfhost,
        tbinfo,
        duthosts,
        fib_info_files,
        ignore_ttl,
        single_fib_for_duts,
        duts_running_config_facts,
        duts_minigraph_facts,
        since
    )

    pytest_assert(
        result['rc'] == SUCCESS_CODE,
        f"Failed to create techsupport. \nstdout:{result['stdout']}. \nstderr:{result['stderr']}"
    )
    for traffic_log_file in traffic_log_files:
        validate_fib_traffic_result(ptfhost, traffic_log_file)
