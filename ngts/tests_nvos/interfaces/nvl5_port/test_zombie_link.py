import pytest
import logging
from retry.api import retry_call

from ngts.nvos_constants.constants_nvos import ConfState
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts, TxBwLossMonitorConsts
from ngts.tests_nvos.interfaces.nvl5_port.helpers import (
    skip_if_no_access_links, skip_if_no_trunk_links
)
from ngts.tests_nvos.cluster.cluster_tools import summarize_switch_ports
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

# Shortcuts
ZLState = TxBwLossMonitorConsts.State
ZLMonitor = TxBwLossMonitorConsts.MonitorStatus

# Retry settings - FlexCounter polls monitor-status every ~10s
VALIDATE_RETRIES = 6
VALIDATE_RETRY_DELAY = 5


def _get_monitor(fae_obj):
    """Return the tx-bandwidth-loss-monitor BaseComponent for a Fae object."""
    return fae_obj.port.interface.link.tx_bandwidth_loss_monitor


def _is_port_up(fae_obj):
    """
    Check whether the port wrapped by ``fae_obj`` is currently in oper state ``up``.

    Reads ``nv show fae interface <port>`` and inspects ``link.state``.
    Used to decide whether to expect ``monitor-status=normal`` (link up) or
    ``N/A`` (link down) when the feature is enabled.
    """
    parsed = OutputParsingTool.parse_show_interface_output_to_dictionary(
        fae_obj.port.interface.show()).get_returned_value()
    link = parsed.get('link', {}) if isinstance(parsed, dict) else {}
    return link.get('state') == NvosConsts.LINK_STATE_UP


def _monitor_for_enabled(fae_obj):
    """
    Expected ``monitor-status`` value when the feature is enabled on this port:
    ``normal`` if the port link is up, otherwise ``N/A``.
    """
    return ZLMonitor.NORMAL.value if _is_port_up(fae_obj) else ZLMonitor.NA.value


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
# Test 1 - Configuration (test plan 6.1)
# ---------------------------------------------------------------------------

@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_configuration(engines, devices, random_api):
    """
    Verify show, set, unset and invalid input on the tx-bandwidth-loss-monitor state knob.

    Steps:
    - Show default: state operational=disabled applied=fw-default, monitor-status=N/A
    - Set disabled -> apply -> verify
    - Set enabled -> apply -> verify
    - Set fw-default -> apply -> verify (back to default)
    - Set invalid value -> verify rejection
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

        with allure.step("Set state to enabled and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.ENABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NORMAL.value)

        with allure.step("Set state to fw-default and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.FW_DEFAULT.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)

        with allure.step("Set invalid state and verify rejection"):
            monitor.set(TxBwLossMonitorConsts.STATE, 'invalid-state',
                        expected_str=TxBwLossMonitorConsts.ERR_MSG_INVALID_STATE).verify_result()

    finally:
        with allure.step("Cleanup: unset to restore defaults"):
            monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                          ask_for_confirmation=True).verify_result()


# ---------------------------------------------------------------------------
# Test 2 - Link Events (test plan 7.1)
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
        with allure.step("Cleanup: bring port up and unset monitor state"):
            port.interface.link.state.set(
                op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                ask_for_confirmation=True).verify_result()
            port.interface.wait_for_port_state(
                NvosConsts.LINK_STATE_UP).verify_result()
            monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                          ask_for_confirmation=True).verify_result()


# ---------------------------------------------------------------------------
# Test 3 - Range-based configuration on access ports
# ---------------------------------------------------------------------------

def _run_range_state_test(group_all_ports, verify_port_name):
    """
    Sweep tx-bandwidth-loss-monitor state on a port range; verify on a single port.

    - Set disabled on the range -> verify oper=applied=disabled, monitor=N/A on verify_port.
    - Set enabled  on the range -> verify oper=applied=enabled,  monitor=normal on verify_port.
    - Cleanup: unset on the range -> verify defaults restored on verify_port.
    """
    all_ports = Fae(port_name=group_all_ports)
    verify_port = Fae(port_name=verify_port_name)
    range_monitor = _get_monitor(all_ports)

    try:
        with allure.step(f"Set disabled on range {group_all_ports} and verify on {verify_port_name}"):
            range_monitor.set(TxBwLossMonitorConsts.STATE, ZLState.DISABLED.value,
                              apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(verify_port, ZLState.DISABLED.value,
                                       ZLState.DISABLED.value, ZLMonitor.NA.value)

        with allure.step(f"Set enabled on range {group_all_ports} and verify on {verify_port_name}"):
            range_monitor.set(TxBwLossMonitorConsts.STATE, ZLState.ENABLED.value,
                              apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(verify_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, ZLMonitor.NORMAL.value)

    finally:
        with allure.step(f"Cleanup: unset on range {group_all_ports} to restore defaults"):
            range_monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                                ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(verify_port,
                                       TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                                       TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS)


@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_access_ports(engines, devices, random_api, standalone_system, has_loopbox):
    """
    @summary:
        Verify tx-bandwidth-loss-monitor state can be configured on a range of
        access ports (acp), e.g.
        ``nv set fae interface acp1-72 link tx-bandwidth-loss-monitor state disabled``.

    Steps:
    1. Skip if no access links (testbed gate).
    2. Skip if no acp port is currently in UP state (runtime safety).
    3. Build access-port range as ``acp1-<N>``.
    4. Sweep state disabled -> enabled on the range, verify on the chosen UP acp port.
    5. Cleanup: unset on the range and verify defaults restored.
    """
    skip_if_no_access_links(has_loopbox, standalone_system)

    with allure.step("Pick a random acp port currently in UP state"):
        port_result = RandomizationTool.select_random_port(
            requested_ports_state=NvosConsts.LINK_STATE_UP, interface_type='acp')
        if not port_result.result:
            pytest.skip(f"Skipping test - no acp ports in UP state: {port_result.info}")
        port_name = port_result.get_returned_value().name

    group_all_ports = f'acp1-{len(devices.dut.nvl5_access_ports_list)}'
    _run_range_state_test(group_all_ports=group_all_ports, verify_port_name=port_name)


# ---------------------------------------------------------------------------
# Test 4 - Range-based configuration on trunk ports
# ---------------------------------------------------------------------------

@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_trunk_ports(engines, devices, random_api, standalone_system, has_loopbox):
    """
    @summary:
        Verify tx-bandwidth-loss-monitor state can be configured on a range of
        trunk ports (sw), e.g.
        ``nv set fae interface sw1-32 link tx-bandwidth-loss-monitor state disabled``.

    Steps:
    1. Skip if no trunk links (testbed gate).
    2. Skip if no sw port is currently in UP state (runtime safety).
    3. Build trunk-port range using ``summarize_switch_ports``.
    4. Sweep state disabled -> enabled on the range, verify on the chosen UP sw port.
    5. Cleanup: unset on the range and verify defaults restored.
    """
    skip_if_no_trunk_links(devices)

    with allure.step("Pick a random sw port currently in UP state"):
        port_result = RandomizationTool.select_random_port(
            requested_ports_state=NvosConsts.LINK_STATE_UP, interface_type='sw')
        if not port_result.result:
            pytest.skip(f"Skipping test - no sw ports in UP state: {port_result.info}")
        port_name = port_result.get_returned_value().name

    group_all_ports = summarize_switch_ports(devices.dut.nvl5_trunk_ports_list)
    _run_range_state_test(group_all_ports=group_all_ports, verify_port_name=port_name)


# ---------------------------------------------------------------------------
# Test 5 - External FNM port configuration
# ---------------------------------------------------------------------------

@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_monitor_fnm_port(engines, devices, random_api):
    """
    Verify tx-bandwidth-loss-monitor state knob on an external FNM port
    (e.g. ``fnm1`` / ``fnm2``). Internal FAE-only FNM ports (``fnma*``) are
    out of scope for this test.

    Steps:
    - Pick a random external FNM port
    - Verify default state (operational=disabled, applied=fw-default, monitor=N/A)
    - Set disabled -> verify
    - Set enabled -> verify
    - Cleanup: unset from enabled state -> verify defaults restored (validates unset
      actually transitions state, not a no-op).
    """
    with allure.step("Select a random external FNM port"):
        fnm_ports = devices.dut.nvl5_fnm_ports
        if not fnm_ports:
            pytest.skip("Skipping test - no external FNM ports on this device")
        fnm_port_name = RandomizationTool.select_random_value(fnm_ports).get_returned_value()
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

        with allure.step(f"Set state to disabled on {fnm_port_name} and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.DISABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.DISABLED.value,
                                       ZLState.DISABLED.value, ZLMonitor.NA.value)

        with allure.step(f"Set state to enabled on {fnm_port_name} and verify"):
            monitor.set(TxBwLossMonitorConsts.STATE, ZLState.ENABLED.value,
                        apply=True, ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(selected_port, ZLState.ENABLED.value,
                                       ZLState.ENABLED.value, _monitor_for_enabled(selected_port))

    finally:
        with allure.step(f"Cleanup: unset on {fnm_port_name} from enabled and verify defaults restored"):
            monitor.unset(op_param=TxBwLossMonitorConsts.STATE, apply=True,
                          ask_for_confirmation=True).verify_result()
            _validate_state_with_retry(
                selected_port,
                TxBwLossMonitorConsts.DEFAULT_OPER_STATE,
                TxBwLossMonitorConsts.DEFAULT_APPLIED_STATE,
                TxBwLossMonitorConsts.DEFAULT_MONITOR_STATUS,
            )
