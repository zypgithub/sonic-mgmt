"""
Test gNMI server status: counters, client list, clear, and persistence across NVUE restart.

Steps from test_steps.txt (see PLAN_TEST_GNMI_SERVER_STATUS.md).
"""
import logging
import time

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.constants.constants import GnmiConsts
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, GnmiServerStatus
from ngts.tests_nvos.system.gnmi.helpers import (
    parse_gnmi_status,
    validate_gnmi_enabled_and_running,
)

logger = logging.getLogger()

# Invalid YANG path to trigger rejected subscription (non-existent in schema)
INVALID_YANG_PREFIX = "invalid-path-not-in-schema"
INVALID_YANG_PATH = "nonexistent-leaf"

# Wait after stopping subscription / restarting nvued before re-checking status
WAIT_AFTER_STOP_SUBSCRIPTION_SEC = 3
WAIT_AFTER_NVUED_RESTART_SEC = 10


def _get_counter(status_dict, key, default=0):
    """Get counter value from status dict; handle nested or flat structure."""
    if isinstance(status_dict, dict) and key in status_dict:
        val = status_dict[key]
        return int(val) if val is not None else default
    return default


def _get_clients(status_dict):
    """Get client list from status dict."""
    clients = status_dict.get(GnmiServerStatus.CLIENT)
    if clients is None:
        return []
    if isinstance(clients, dict) and len(clients) == 0:
        return []
    return clients if isinstance(clients, list) else [clients]


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_server_status_counters_and_persistence(engines, devices):
    """
    Validate gNMI server status: counters, client list, clear, and persistence across NVUE restart.

    Test flow (from test_steps.txt):
        1. Show - store starting counter values, expect no clients
        2. Rejected subscription - expect +1 received-subscription-requests, +1 rejected-subscriptions
        3. Capabilities - expect +1 received-capabilities-requests
        4. Valid subscription - expect +1 total-active-subscriptions, +1 received-subscription-requests, 1 client
        5. Show invalid client - expect empty client list
        6. Clear - received/rejected/caps counters reset to 0, total-active-subscriptions and client state unchanged
        7. Stop subscription - total-active-subscriptions 0, no clients
        8. Valid sub, rejected sub, capabilities - counters increment from 0
        9. Restart NVUE
        10. Show - counters same as before restart
    """
    system = System()
    gnmi_status = system.gnmi_server.status
    dut = engines.dut
    username = devices.dut.default_username
    password = devices.dut.default_password

    with allure.step("Validate gNMI server enabled and running"):
        validate_gnmi_enabled_and_running(system.gnmi_server, engines)

    client = GnmiClient(
        dut.ip,
        GnmiConsts.GNMI_DEFAULT_PORT,
        username,
        password,
        cmd_time=10,
    )
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value

    # --- Step 1: Show (initial) - store starting counter values ---
    with allure.step("Step 1: Show status - store starting values, expect no clients"):
        out1 = gnmi_status.show(dut_engine=dut)
        status1 = parse_gnmi_status(out1)
        exp_total_active = _get_counter(status1, GnmiServerStatus.TOTAL_ACTIVE_SUBSCRIPTIONS)
        exp_received_subs = _get_counter(status1, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS)
        exp_rejected = _get_counter(status1, GnmiServerStatus.REJECTED_SUBSCRIPTIONS)
        exp_caps = _get_counter(status1, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS)
        assert len(_get_clients(status1)) == 0

    # --- Step 2: Rejected subscription (invalid YANG path) ---
    with allure.step("Step 2: Set up rejected gNMI subscription (invalid YANG path)"):
        client.gnmic_subscribe(
            INVALID_YANG_PREFIX,
            INVALID_YANG_PATH,
            GnmiMode.ONCE,
            username=username,
            password=password,
            skip_cert_verify=True,
            cmd_time=5,
        )
        exp_received_subs += 1
        exp_rejected += 1
        out2 = gnmi_status.show(dut_engine=dut)
        status2 = parse_gnmi_status(out2)
        assert _get_counter(status2, GnmiServerStatus.TOTAL_ACTIVE_SUBSCRIPTIONS) == exp_total_active
        assert _get_counter(status2, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS) == exp_received_subs
        assert _get_counter(status2, GnmiServerStatus.REJECTED_SUBSCRIPTIONS) == exp_rejected
        assert _get_counter(status2, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS) == exp_caps

    # --- Step 3: Send capabilities ---
    with allure.step("Step 3: Send capabilities"):
        client.gnmic_capabilities(skip_cert_verify=True, username=username, password=password)
        exp_caps += 1
        out3 = gnmi_status.show(dut_engine=dut)
        status3 = parse_gnmi_status(out3)
        assert _get_counter(status3, GnmiServerStatus.TOTAL_ACTIVE_SUBSCRIPTIONS) == exp_total_active
        assert _get_counter(status3, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS) == exp_received_subs
        assert _get_counter(status3, GnmiServerStatus.REJECTED_SUBSCRIPTIONS) == exp_rejected
        assert _get_counter(status3, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS) == exp_caps

    # --- Step 4: Valid subscription, show, show clients, show client X ---
    with allure.step("Step 4: Set up gNMI subscription and show status / clients / client X"):
        sub_process = client.gnmic_subscribe_interface_and_keep_session_alive(
            GnmiMode.STREAM,
            selected_port.name,
            username=username,
            password=password,
            skip_cert_verify=True,
        )
        time.sleep(2)
        exp_total_active += 1
        exp_received_subs += 1
        out4 = gnmi_status.show(dut_engine=dut)
        status4 = parse_gnmi_status(out4)
        assert _get_counter(status4, GnmiServerStatus.TOTAL_ACTIVE_SUBSCRIPTIONS) == exp_total_active
        assert _get_counter(status4, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS) == exp_received_subs
        assert _get_counter(status4, GnmiServerStatus.REJECTED_SUBSCRIPTIONS) == exp_rejected
        assert _get_counter(status4, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS) == exp_caps
        clients4 = _get_clients(status4)
        assert len(clients4) == 1
        # Client id is 1-based index: one client -> "client 1", two clients -> "client 1" / "client 2"
        client_id = "1"
        out_client_x = gnmi_status.show(op_param=f"client {client_id}", dut_engine=dut)
        client_x_parsed = parse_gnmi_status(out_client_x)
        first_client = clients4[0]
        addr = first_client.get(GnmiServerStatus.CLIENT_ADDRESS, "")
        assert client_x_parsed.get(GnmiServerStatus.CLIENT_ADDRESS) == addr or GnmiServerStatus.CLIENT_ADDRESS in str(client_x_parsed)

    # --- Step 5: Show client Y (invalid) ---
    with allure.step("Step 5: Show client Y (invalid id) - expect empty client list"):
        invalid_id = "invalid-client-id-999"
        output = gnmi_status.show(
            op_param=f"client {invalid_id}",
            dut_engine=dut,
        )
        parsed = parse_gnmi_status(output)
        assert len(_get_clients(parsed)) == 0, (
            f"Expected empty client list for invalid client id, got: {_get_clients(parsed)}"
        )

    # --- Step 6: Clear, then show ---
    with allure.step("Step 6: Clear status, then show - active subs unchanged, counters reset to zero"):
        gnmi_status.action_clear().verify_result()
        exp_received_subs = 0
        exp_rejected = 0
        exp_caps = 0
        out6 = gnmi_status.show(dut_engine=dut)
        status6 = parse_gnmi_status(out6)
        assert _get_counter(status6, GnmiServerStatus.TOTAL_ACTIVE_SUBSCRIPTIONS) == exp_total_active
        assert _get_counter(status6, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS) == exp_received_subs
        assert _get_counter(status6, GnmiServerStatus.REJECTED_SUBSCRIPTIONS) == exp_rejected
        assert _get_counter(status6, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS) == exp_caps
        clients6 = _get_clients(status6)
        assert len(clients6) == 1

    # --- Step 7: Stop subscription ---
    with allure.step("Step 7: Stop subscription - expect total-active-subscriptions 0, no clients"):
        client.close_session_and_get_out_and_err(sub_process)
        time.sleep(WAIT_AFTER_STOP_SUBSCRIPTION_SEC)
        exp_total_active = 0
        out7 = gnmi_status.show(dut_engine=dut)
        status7 = parse_gnmi_status(out7)
        assert _get_counter(status7, GnmiServerStatus.TOTAL_ACTIVE_SUBSCRIPTIONS) == exp_total_active
        assert _get_counter(status7, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS) == exp_received_subs
        assert _get_counter(status7, GnmiServerStatus.REJECTED_SUBSCRIPTIONS) == exp_rejected
        assert _get_counter(status7, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS) == exp_caps
        assert len(_get_clients(status7)) == 0

    # --- Step 8: Valid sub, rejected sub, capabilities again ---
    with allure.step("Step 8: Setup valid subscribe (once), rejected subscribe, capabilities"):
        client.gnmic_subscribe_interface(
            GnmiMode.ONCE,
            selected_port.name,
            username=username,
            password=password,
            skip_cert_verify=True,
            cmd_time=5,
        )
        client.gnmic_subscribe(
            INVALID_YANG_PREFIX,
            INVALID_YANG_PATH,
            GnmiMode.ONCE,
            username=username,
            password=password,
            skip_cert_verify=True,
            cmd_time=5,
        )
        client.gnmic_capabilities(skip_cert_verify=True, username=username, password=password)
        exp_received_subs += 2
        exp_rejected += 1
        exp_caps += 1
        out8 = gnmi_status.show(dut_engine=dut)
        status8 = parse_gnmi_status(out8)
        assert _get_counter(status8, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS) == exp_received_subs
        assert _get_counter(status8, GnmiServerStatus.REJECTED_SUBSCRIPTIONS) == exp_rejected
        assert _get_counter(status8, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS) == exp_caps

    # --- Step 9: Restart NVUE ---
    with allure.step("Step 9: Restart NVUE"):
        def get_pid_of_nvued():
            pid_str = dut.run_cmd("sudo systemctl show nvued | grep ^MainPID")
            return int(pid_str.split("=")[1])

        pid_before = get_pid_of_nvued()
        dut.run_cmd("sudo systemctl restart nvued")
        time.sleep(WAIT_AFTER_NVUED_RESTART_SEC)
        pid_after = get_pid_of_nvued()
        assert pid_before != pid_after, "nvued was not restarted"

    # --- Step 10: Show after restart - counters same as before restart ---
    with allure.step("Step 10: Show status after restart - counters same as before restart"):
        out10 = gnmi_status.show(dut_engine=dut)
        status10 = parse_gnmi_status(out10)
        assert _get_counter(status10, GnmiServerStatus.RECEIVED_SUBSCRIPTION_REQUESTS) == exp_received_subs, (
            "received-subscription-requests should persist across nvued restart"
        )
        assert _get_counter(status10, GnmiServerStatus.REJECTED_SUBSCRIPTIONS) == exp_rejected, (
            "rejected-subscriptions should persist across nvued restart"
        )
        assert _get_counter(status10, GnmiServerStatus.RECEIVED_CAPABILITIES_REQUESTS) == exp_caps, (
            "received-capabilities-requests should persist across nvued restart"
        )
