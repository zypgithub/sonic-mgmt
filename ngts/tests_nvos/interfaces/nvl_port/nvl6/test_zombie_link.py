import pytest
import logging
from retry.api import retry_call

from ngts.nvos_constants.constants_nvos import ConfState
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts, TxBwLossMonitorConsts
from ngts.tests_nvos.interfaces.nvl_port.helpers import (
    select_random_nvl_port_name, skip_if_no_access_links
)
from ngts.tests_nvos.cluster.cluster_tools import summarize_switch_ports
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

# Shortcuts
ZLState = TxBwLossMonitorConsts.State
ZLMonitor = TxBwLossMonitorConsts.MonitorStatus

# Retry settings — FlexCounter polls monitor-status every ~10s
VALIDATE_RETRIES = 6
VALIDATE_RETRY_DELAY = 5


def _get_monitor(fae_obj):
    """Return the tx-bandwidth-loss-monitor BaseComponent for a Fae object."""
    return fae_obj.port.interface.link.tx_bandwidth_loss_monitor


def _validate_state(fae_obj, expected_oper_state, expected_applied_state, expected_monitor_status):
    """
    Validate tx-bandwidth-loss-monitor show output for both operational and applied columns.

    Calls ``nv show fae interface <if> link tx-bandwidth-loss-monitor`` twice:
    once for operational values (state + monitor-status) and once for the applied state.
    """
    monitor = _get_monitor(fae_obj)

    oper = OutputParsingTool.parse_json_str_to_dictionary(monitor.show()).get_returned_value()
    assert oper.get(TxBwLossMonitorConsts.STATE) == expected_oper_state, \
        f"Operational state: expected '{expected_oper_state}', got '{oper.get(TxBwLossMonitorConsts.STATE)}'"
    assert oper.get(TxBwLossMonitorConsts.MONITOR_STATUS) == expected_monitor_status, \
        f"Monitor status: expected '{expected_monitor_status}', got '{oper.get(TxBwLossMonitorConsts.MONITOR_STATUS)}'"

    applied = OutputParsingTool.parse_json_str_to_dictionary(
        monitor.show(rev=ConfState.APPLIED)).get_returned_value()
    assert applied.get(TxBwLossMonitorConsts.STATE) == expected_applied_state, \
        f"Applied state: expected '{expected_applied_state}', got '{applied.get(TxBwLossMonitorConsts.STATE)}'"


def _validate_state_with_retry(fae_obj, expected_oper_state, expected_applied_state, expected_monitor_status):
    """Validate state with retry to allow FlexCounter polling to update."""
    retry_call(
        _validate_state,
        fargs=[fae_obj, expected_oper_state, expected_applied_state, expected_monitor_status],
        exceptions=AssertionError,
        tries=VALIDATE_RETRIES,
        delay=VALIDATE_RETRY_DELAY,
    )


# ---------------------------------------------------------------------------
# Test 1 — Configuration (test plan 6.1)
# ---------------------------------------------------------------------------

@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_configuration(engines, devices, random_api):
    """
    Verify show, set, unset and invalid input on the tx-bandwidth-loss-monitor state knob.

    Steps:
    - Show default: state operational=disabled applied=fw-default, monitor-status=N/A
    - Set disabled -> apply -> verify
    - Set fw-default -> apply -> verify (back to default)
    - Set enabled -> apply -> verify
    - Set invalid value -> verify rejection
    - Cleanup: unset -> verify state returns to fw-default
    """
    with allure.step("Select a random port in up state"):
        port_result = RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_UP)
        if not port_result.result:
            pytest.skip(f"Skipping test - {port_result.info}")
        selected_port = Fae(port_name=port_result.get_returned_value().name)

    monitor = _get_monitor(selected_port)

    try:
        with allure.step("Verify default state (fw-default -> operational disabled)"):
            _validate_state(
                selected_port,
                TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS,
            )

        with allure.step("Set state to disabled and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.DISABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.DISABLED.value,
                                       ZLState.DISABLED.value, ZLMonitor.NA.value)

        with allure.step("Set state to fw-default and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.FW_DEFAULT.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)

        with allure.step("Set state to enabled and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.ENABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NORMAL.value)

        with allure.step("Set invalid state and verify rejection"):
            monitor.set(TxBwLossMonitorConsts.STATE, 'invalid-state',
                        expected_str=TxBwLossMonitorConsts.ERR_MSG_INVALID_STATE).verify_result()

    finally:
        with allure.step("Cleanup: unset and verify defaults restored"):
            monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                          ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)


# ---------------------------------------------------------------------------
# Test 2 — Link Events (test plan 7.1)
# ---------------------------------------------------------------------------

@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_link_state_down(engines, devices, random_api):
    """
    Verify that operational state and monitor-status update on link down / up events.

    Steps:
    - Ensure monitor is enabled and port is link-up -> monitor-status=normal
    - Admin-down port -> verify state operational=enabled, monitor-status=N/A
    - Admin-up port, wait for link-up -> verify monitor-status=normal
    """
    with allure.step("Select a random port in up state"):
        port_result = RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_UP)
        if not port_result.result:
            pytest.skip(f"Skipping test - {port_result.info}")
        port = port_result.get_returned_value()
        selected_port = Fae(port_name=port.name)

    monitor = _get_monitor(selected_port)

    try:
        with allure.step("Enable monitor and verify precondition"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.ENABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NORMAL.value)

        with allure.step("Admin-down port and verify monitor-status becomes N/A"):
            port.interface.link.state.set(
                op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True,
                ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NA.value)

        with allure.step("Admin-up port and verify monitor-status returns to normal"):
            port.interface.link.state.set(
                op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                ask_for_confirmation=True).verify_result()
            port.interface.wait_for_port_state(
                NvosConsts.LINK_STATE_UP).verify_result()
            _validate_state_with_retry(selected_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NORMAL.value)

    finally:
        with allure.step("Cleanup: bring port up, unset monitor state, and verify defaults restored"):
            port.interface.link.state.set(
                op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                ask_for_confirmation=True).verify_result()
            port.interface.wait_for_port_state(
                NvosConsts.LINK_STATE_UP).verify_result()
            monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                          ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)


# ---------------------------------------------------------------------------
# Test 3 — Range-based configuration (access ports)
# ---------------------------------------------------------------------------

@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_range(engines, devices, random_api, standalone_system, has_loopbox, is_simx):
    """
    Verify tx-bandwidth-loss-monitor state can be set on a range of access ports
    (e.g. ``nv set fae interface acp1-72 link tx-bandwidth-loss-monitor state disabled``).

    Steps:
    - Build access-port range (acp<a>-<b>)
    - Set disabled on range -> verify on a random single port
    - Set enabled on range -> verify on a random single port
    - Unset on range -> verify defaults restored on single port
    """
    skip_if_no_access_links(has_loopbox, standalone_system, is_simx)

    with allure.step("Build access port range"):
        access_ports = devices.dut.nvl_access_ports_list
        port_range = summarize_switch_ports(access_ports)
        all_ports = Fae(port_name=port_range)

    with allure.step("Select a random access port for single-port verification"):
        verify_port_name = select_random_nvl_port_name(devices, 'acp')
        verify_port = Fae(port_name=verify_port_name)

    range_monitor = _get_monitor(all_ports)

    try:
        with allure.step(f"Set disabled on range {port_range} and verify on {verify_port_name}"):
            range_monitor.set(TxBwLossMonitorConsts.STATE, ZLState.DISABLED.value,
                              apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(verify_port, ZLState.DISABLED.value,
                                       ZLState.DISABLED.value, ZLMonitor.NA.value)

        with allure.step(f"Set enabled on range {port_range} and verify on {verify_port_name}"):
            range_monitor.set(TxBwLossMonitorConsts.STATE, ZLState.ENABLED.value,
                              apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(verify_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NORMAL.value)

    finally:
        with allure.step("Cleanup: unset on range to restore defaults"):
            range_monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                                ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(verify_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)


# ---------------------------------------------------------------------------
# Test 4 — Internal FNM ports
# ---------------------------------------------------------------------------

@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_internal_fnm_port(engines, devices, random_api):
    """
    Verify tx-bandwidth-loss-monitor is configurable on internal FNM ports.

    Internal FNM ports (fnmaXpY) connect ASICs together and are LinkUp by default,
    so the tx-bandwidth-loss-monitor feature must be exposed and behave the same
    as on access/trunk ports.

    Steps (mirrors test_tx_bw_loss_monitor_configuration, but on an internal FNM port):
    - Show default: state operational=disabled applied=fw-default, monitor-status=N/A
    - Set disabled -> apply -> verify
    - Set fw-default -> apply -> verify (back to default)
    - Set enabled -> apply -> verify (monitor-status=normal since port is link-up)
    - Set invalid value -> verify rejection
    - Cleanup: unset -> verify state returns to fw-default
    """
    if not getattr(devices.dut, 'nvl_internal_fnm_ports', None):
        pytest.skip("No nvl_internal_fnm_ports defined for this device")

    with allure.step("Select a random internal FNM port"):
        fnm_port_name = RandomizationTool.select_random_value(
            devices.dut.nvl_internal_fnm_ports).get_returned_value()
        selected_port = Fae(port_name=fnm_port_name)

    monitor = _get_monitor(selected_port)

    try:
        with allure.step(f"Verify default state on {fnm_port_name}"):
            _validate_state(
                selected_port,
                TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS,
            )

        with allure.step("Set state to disabled and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.DISABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.DISABLED.value,
                                       ZLState.DISABLED.value, ZLMonitor.NA.value)

        with allure.step("Set state to fw-default and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.FW_DEFAULT.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)

        with allure.step("Set state to enabled and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.ENABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NORMAL.value)

        with allure.step("Set invalid state and verify rejection"):
            monitor.set(TxBwLossMonitorConsts.STATE, 'invalid-state',
                        expected_str=TxBwLossMonitorConsts.ERR_MSG_INVALID_STATE).verify_result()

    finally:
        with allure.step("Cleanup: unset and verify defaults restored"):
            monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                          ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)
