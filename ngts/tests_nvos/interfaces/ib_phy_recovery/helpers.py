"""
IB PHY Recovery Helper Functions

This module provides reusable helper functions for IB PHY recovery tests.

Functions are organized into categories:
    - Port Selection: Get random ports for testing
    - Device Info: Get local port and MST device information
    - Error Injection: PREI register manipulation for fault simulation
    - Recovery Actions: Trigger recovery go-once
    - Counter Operations: Get, clear, and validate recovery counters
    - Configuration Validation: Validate mode, timeout, and defaults
    - Traffic Validation: Validate traffic counters
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

import pytest
from retry.api import retry_call

from ngts.nvos_constants.constants_nvos import ActionConsts, ApiType, ConfState, IbConsts, NvosConst
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import (
    IbInterfaceConsts,
    NvosConsts,
)
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.cluster.cluster_tools import summarize_switch_ports
from ngts.tools.test_utils import allure_utils as allure

from ngts.tests_nvos.interfaces.ib_phy_recovery.consts import (
    GoOnceConsts,
    IbPhyRecoveryCounters,
    IbPhyRecoveryConfig,
    IbPhyRecoveryTestConsts,
    PREIErrorInjection,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Port Selection Helpers
# =============================================================================

def get_random_ib_port_in_state(
    requested_state: str = NvosConsts.LINK_STATE_UP,
    port_type: str = IbInterfaceConsts.IB_PORT_TYPE
) -> Optional[Port]:
    """
    Select a random IB port in the requested state.

    Args:
        requested_state: Desired port state (up/down/all)
        port_type: Type of port to select (default: IB)

    Returns:
        Port object if found, None otherwise

    Example:
        port = get_random_ib_port_in_state(NvosConsts.LINK_STATE_UP)
        if port:
            print(f"Selected port: {port.name}")
    """
    port_result = RandomizationTool.select_random_port(
        requested_ports_state=requested_state,
        requested_ports_type=port_type
    )
    if not port_result.result:
        logger.warning(f"No port found in state {requested_state}: {port_result.info}")
        return None
    return port_result.get_returned_value()


def get_traffic_port() -> Optional[Port]:
    """
    Select a random port suitable for traffic testing.

    Returns:
        Port object if found, None otherwise
    """
    result = Tools.RandomizationTool.get_random_traffic_port()
    if not result.result:
        logger.warning(f"No traffic port available: {result.info}")
        return None
    ports = result.get_returned_value()
    return ports[0] if ports else None


def get_all_ib_ports_range() -> Optional[str]:
    """
    Get a summarized range string for ALL IB ports.

    Creates a port range string (e.g., "sw1-18p1-2") that can be used
    in NVUE commands to apply settings to all IB ports at once.

    Returns:
        Port range string like "sw1-18p1-2", or None if no ports found

    Example:
        range_str = get_all_ib_ports_range()
        if range_str:
            # Apply setting to all ports: nv set fae interface sw1-18p1-2 ...
            all_ports = Fae(port_name=range_str)
    """
    with allure.step("Get all IB ports and create range string"):
        port_requirements = PortRequirements()
        port_requirements.set_port_type(IbInterfaceConsts.IB_PORT_TYPE)
        all_ports = Port.get_list_of_ports(port_requirements_object=port_requirements)

        if not all_ports:
            logger.warning("No IB ports found")
            return None

        port_names = [port.name for port in all_ports]
        logger.info(f"Found {len(port_names)} IB ports: {port_names[:5]}... (showing first 5)")

        port_range = summarize_switch_ports(port_names)
        logger.info(f"Summarized IB port range: {port_range}")

        return port_range


# =============================================================================
# Device Information Helpers
# =============================================================================

def get_local_port_and_mst_device(port_name: str) -> Tuple[str, str]:
    """
    Get the local port number and MST device from a port's lane.

    For IB port sw9p1, retrieves info from sw9p1plX (plane/lane X):
        nv show fae interface sw9p1pl1
        -> primary-asic-device: /dev/mst/mt54004_pciconf2
        -> local-port: 51

    Tries lanes pl1, pl2, pl3, pl4 in order until one returns valid data.
    This handles cases where the primary lane is not pl1.

    Args:
        port_name: Port name (e.g., sw9p1)

    Returns:
        Tuple of (local_port, mst_device)

    Raises:
        ValueError: If unable to retrieve local_port or mst_device from any lane

    Example:
        local_port, mst_device = get_local_port_and_mst_device("sw9p1")
        print(f"Local port: {local_port}, MST device: {mst_device}")
    """
    lanes_to_try = IbPhyRecoveryConfig.LANES
    last_output = {}

    with allure.step(f"Get local port and MST device from {port_name} (trying lanes {lanes_to_try})"):
        for lane_suffix in lanes_to_try:
            lane_name = f"{port_name}{lane_suffix}"
            logger.debug(f"Trying lane: {lane_name}")

            try:
                fae = Fae(port_name=lane_name)
                output = OutputParsingTool.parse_json_str_to_dictionary(
                    fae.interface.show()
                ).get_returned_value()
                last_output = output

                # Get primary-asic-device value (can be dict or string depending on setup)
                primary_asic_device = output.get(IbInterfaceConsts.PRIMARY_ASIC_DEVICE)
                logger.debug(f"Lane {lane_name} - primary-asic-device type: "
                             f"{type(primary_asic_device).__name__}, value: {primary_asic_device}")

                # Extract local_port and mst_device based on structure type:
                # - Nested: primary-asic-device: {local-port: X, primary-asic-device: Y}
                # - Flat: primary-asic-device is directly the MST path, local-port at root
                if isinstance(primary_asic_device, dict):
                    local_port = str(primary_asic_device.get(IbInterfaceConsts.LOCAL_PORT, ""))
                    mst_device = primary_asic_device.get(IbInterfaceConsts.PRIMARY_ASIC_DEVICE, "")
                else:
                    local_port = ""
                    mst_device = primary_asic_device if isinstance(primary_asic_device, str) else ""

                # Fallback to root-level values if not found in nested structure
                local_port = local_port or str(output.get(IbInterfaceConsts.LOCAL_PORT, ""))
                mst_device = mst_device or str(output.get(IbInterfaceConsts.PRIMARY_ASIC_DEVICE, ""))

                # Check if we got valid values from this lane
                if local_port and mst_device:
                    logger.info(f"Port {port_name} (via {lane_name}): "
                                f"local_port={local_port}, mst_device={mst_device}")
                    return local_port, mst_device

                logger.debug(f"Lane {lane_name} did not return valid data: "
                             f"local_port='{local_port}', mst_device='{mst_device}'")

            except Exception as e:
                logger.debug(f"Lane {lane_name} failed with exception: {e}")
                continue

        # None of the lanes returned valid data
        raise ValueError(
            f"Could not retrieve local_port or mst_device for port {port_name} "
            f"from any lane ({lanes_to_try}). Last output: {last_output}"
        )


# =============================================================================
# Error Injection Helpers (PREI Register)
# =============================================================================

def inject_error_via_prei(
    engine,
    mst_device: str,
    local_port: str,
    error_type_admin: int = PREIErrorInjection.ERROR_TYPE_ADMIN_TRIGGER_RECOVERY,
    error_injection_time: int = PREIErrorInjection.BROKEN_CABLE
) -> ResultObj:
    """
    Inject error using PREI register to trigger/test PHY recovery.

    This is used to simulate cable/PHY issues for testing recovery behavior.

    Args:
        engine: DUT SSH engine
        mst_device: MST device path (e.g., /dev/mst/mt54004_pciconf2)
        local_port: Local port number (decimal string)
        error_type_admin: Error type (4 = trigger recovery)
        error_injection_time: Injection time
            - 0xFFFF: Always fail (broken cable simulation)
            - 5: Noise (flaky cable simulation)
            - 0: Disable

    Returns:
        ResultObj indicating success/failure

    Example:
        # Inject always-fail error (broken cable)
        inject_error_via_prei(engine, mst_device, local_port,
                             error_injection_time=PREIErrorInjection.BROKEN_CABLE)

        # Inject noise (flaky cable)
        inject_error_via_prei(engine, mst_device, local_port,
                             error_injection_time=PREIErrorInjection.FLAKY_CABLE)
    """
    from ngts.nvos_tools.infra.RegisterTool import RegisterTool

    try:
        output = RegisterTool.inject_prei_error(
            engine, mst_device, local_port, error_type_admin, error_injection_time
        )
        logger.info(f"PREI injection result: {output}")
        return ResultObj(True, info=f"PREI injection successful: {output}")
    except (OSError, TimeoutError, RuntimeError) as e:
        logger.error(f"PREI injection failed: {e}")
        return ResultObj(False, info=f"PREI injection failed: {e}")


def disable_error_injection(engine, mst_device: str, local_port: str) -> ResultObj:
    """
    Disable error injection on a port.

    Convenience function to disable PREI error injection.

    Args:
        engine: DUT SSH engine
        mst_device: MST device path
        local_port: Local port number

    Returns:
        ResultObj indicating success/failure
    """
    return inject_error_via_prei(
        engine,
        mst_device,
        local_port,
        error_type_admin=0,
        error_injection_time=PREIErrorInjection.DISABLED
    )


# =============================================================================
# Recovery Action Helpers
# =============================================================================

def trigger_recovery_go_once(port_name: str) -> ResultObj:
    """
    Trigger a single PHY recovery event using the action command.

    Command: nv action start fae interface <port> link phy-recovery

    Args:
        port_name: Port name to trigger recovery on

    Returns:
        ResultObj indicating success/failure

    Example:
        result = trigger_recovery_go_once("sw1p1")
        if result.result:
            print("Recovery triggered successfully")
    """
    with allure.step(f"Trigger recovery go-once on {port_name}"):
        fae = Fae(port_name=port_name)
        try:
            result = fae.port.interface.link.action(
                ActionConsts.START, main_param=("recovery", "phy-recovery")
            )
            if not result.result:
                logger.warning(f"Recovery trigger for {port_name} did not return expected output. "
                               f"Result: {result.info}")
            return result
        except (OSError, TimeoutError, RuntimeError) as e:
            logger.error(f"Recovery trigger failed: {e}")
            return ResultObj(False, info=f"Recovery trigger failed: {e}")


# =============================================================================
# Counter Operations
# =============================================================================

def get_phy_recovery_counters(port_name: str) -> Dict[str, int]:
    """
    Get PHY recovery counters from 'nv show interface <port> link phy detail'.

    Command: nv show interface <port> link phy detail
    Can filter with: grep -i recovery

    Args:
        port_name: Port name to get counters for

    Returns:
        Dictionary of recovery counter names to values

    Example:
        counters = get_phy_recovery_counters("sw1p1")
        successful = counters[IbPhyRecoveryCounters.SUCCESSFUL_RECOVERY_EVENTS]
    """
    with allure.step(f"Get PHY recovery counters for {port_name}"):
        port = Port(port_name, '', '')
        output = OutputParsingTool.parse_json_str_to_dictionary(
            port.interface.link.phy.detail.show()
        ).get_returned_value()

        counters = {}
        for counter_name in IbPhyRecoveryCounters.ALL_COUNTERS:
            value = output.get(counter_name, 0)
            try:
                counters[counter_name] = int(value) if value else 0
            except (ValueError, TypeError):
                counters[counter_name] = 0

        logger.info(f"Recovery counters for {port_name}: {counters}")
        return counters


def get_successful_recovery_events(port_name: str) -> int:
    """
    Get the successful-recovery-events counter value.

    This is the primary counter used to verify recovery events occurred.

    Args:
        port_name: Port name to get counter for

    Returns:
        Number of successful recovery events
    """
    counters = get_phy_recovery_counters(port_name)
    return counters.get(IbPhyRecoveryCounters.SUCCESSFUL_RECOVERY_EVENTS, 0)


def clear_recovery_counters(engine, port_name: str) -> ResultObj:
    """
    Clear PHY recovery counters for a port.

    Note: This is done by clearing interface counters.

    Args:
        engine: DUT SSH engine
        port_name: Port name to clear counters for

    Returns:
        ResultObj indicating success/failure
    """
    with allure.step(f"Clear recovery counters for {port_name}"):
        port = Port(port_name, '', '')
        return port.interface.counters.clear_counters(dut_engine=engine)


def wait_for_recovery_counters_update(
    port_name: Optional[str] = None,
    initial_count: Optional[int] = None,
    initial_total_count: Optional[int] = None,
    max_wait_seconds: int = IbPhyRecoveryTestConsts.RECOVERY_COUNTER_UPDATE_WAIT_SECONDS,
    poll_interval_seconds: int = 5
):
    """
    Wait for recovery counters to update with retry logic.

    If port_name and initial_count are provided, uses retry logic to poll
    until at least one of the recovery counters increases (more efficient than fixed sleep).
    When initial_total_count is also provided, success if either successful-recovery-events
    or total-successful-recovery-events increased. Otherwise, falls back to a fixed sleep.

    Args:
        port_name: Optional port name to check counters on
        initial_count: Optional initial successful-recovery-events count
        initial_total_count: Optional initial total-successful-recovery-events count.
            When provided together with initial_count, pass if either counter increased.
        max_wait_seconds: Maximum time to wait (default: 30 seconds)
        poll_interval_seconds: Interval between polls (default: 5 seconds)

    Returns:
        The final successful-recovery-events value if port_name was provided, None otherwise
    """
    if port_name and initial_count is not None:
        # Use retry logic to wait until at least one counter increases
        with allure.step(f"Wait for recovery counters to update on {port_name} (polling every {poll_interval_seconds}s)"):
            max_tries = max_wait_seconds // poll_interval_seconds

            def _check_counter_increased():
                counters = get_phy_recovery_counters(port_name)
                current_successful = counters.get(IbPhyRecoveryCounters.SUCCESSFUL_RECOVERY_EVENTS, 0)
                current_total = counters.get(IbPhyRecoveryCounters.TOTAL_SUCCESSFUL_RECOVERY_EVENTS, 0)

                successful_increased = current_successful > initial_count
                total_increased = (
                    initial_total_count is not None and
                    current_total > initial_total_count
                )
                if successful_increased or total_increased:
                    logger.info(
                        "Recovery counter(s) increased: successful-recovery-events %s -> %s, "
                        "total-successful-recovery-events %s -> %s",
                        initial_count, current_successful,
                        initial_total_count if initial_total_count is not None else "n/a",
                        current_total,
                    )
                    return current_successful
                total_msg = (
                    f", total-successful-recovery-events {initial_total_count} -> {current_total}"
                    if initial_total_count is not None else ""
                )
                raise AssertionError(
                    f"Neither counter increased: successful-recovery-events {initial_count} -> {current_successful}"
                    f"{total_msg}"
                )

            return retry_call(
                _check_counter_increased,
                exceptions=AssertionError,
                tries=max_tries,
                delay=poll_interval_seconds
            )
    else:
        # Fallback to fixed sleep for backward compatibility
        with allure.step(f"Wait {max_wait_seconds}s for counters to update"):
            time.sleep(max_wait_seconds)
        return None


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_recovery_counters_increased(
    before: Dict[str, int],
    after: Dict[str, int],
    counter_names: Optional[List[str]] = None
) -> ResultObj:
    """
    Validate that recovery counters have increased.

    Primary counter to check: successful-recovery-events

    Args:
        before: Counter values before recovery
        after: Counter values after recovery
        counter_names: Specific counters to check (default: successful-recovery-events)

    Returns:
        ResultObj indicating validation success/failure
    """
    if counter_names is None:
        counter_names = [IbPhyRecoveryCounters.SUCCESSFUL_RECOVERY_EVENTS]

    with allure.step("Validate recovery counters increased"):
        issues = []
        for counter in counter_names:
            before_val = before.get(counter, 0)
            after_val = after.get(counter, 0)
            if after_val <= before_val:
                issues.append(f"{counter}: before={before_val}, after={after_val}")

        if issues:
            return ResultObj(False, info=f"Counters did not increase: {issues}")
        return ResultObj(True, info="All specified counters increased")


def validate_traffic_counters_increased(port: Port, engine) -> ResultObj:
    """
    Validate that traffic counters have increased (traffic is flowing).

    Args:
        port: Port object to check
        engine: DUT SSH engine

    Returns:
        ResultObj indicating validation success/failure
    """
    with allure.step(f"Validate traffic counters for {port.name}"):
        output = OutputParsingTool.parse_json_str_to_dictionary(
            port.interface.counters.show(dut_engine=engine)
        ).get_returned_value()

        in_bytes = int(output.get(IbInterfaceConsts.LINK_STATS_IN_BYTES, 0))
        out_bytes = int(output.get(IbInterfaceConsts.LINK_STATS_OUT_BYTES, 0))

        if in_bytes > 0 or out_bytes > 0:
            return ResultObj(True, info=f"Traffic flowing: in={in_bytes}, out={out_bytes}")
        return ResultObj(False, info=f"No traffic: in={in_bytes}, out={out_bytes}")


def validate_link_state(port: Port, expected_state: str) -> ResultObj:
    """
    Validate that a port is in the expected link state.

    Args:
        port: Port object to check
        expected_state: Expected state (up/down)

    Returns:
        ResultObj indicating validation success/failure
    """
    with allure.step(f"Validate {port.name} is in {expected_state} state"):
        actual_state = port.interface.link.state.show()
        if expected_state.lower() in actual_state.lower():
            return ResultObj(True, info=f"Link state is {expected_state}")
        return ResultObj(False, info=f"Link state mismatch: expected {expected_state}, got {actual_state}")


def validate_ib_mode_set(selected_port, mode: str, timeout: Optional[int] = None):
    """
    Validate IB PHY recovery mode (logic-relock) is applied to the selected port.

    For IB interfaces, validates logic-relock-mode and logic-relock-timeout.

    Args:
        selected_port: Fae port object
        mode: Expected mode (enabled/disabled/fw-default)
        timeout: Expected timeout value (optional, range 0-255)

    Raises:
        AssertionError: If validation fails
    """
    with allure.step(f"Validate IB logic-relock mode {mode} is applied"):
        output = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.port.interface.link.phy_recovery.show()
        ).get_returned_value()

        # fw-default maps to disabled operationally
        expected_mode = IbPhyRecoveryConfig.DISABLED if mode == IbPhyRecoveryConfig.FW_DEFAULT else mode
        actual_mode = output.get(IbPhyRecoveryConfig.MODE)
        ValidationTool.compare_values(actual_mode, expected_mode).verify_result()

        if timeout is not None:
            actual_timeout = int(output.get(IbPhyRecoveryConfig.TIMEOUT, 0))
            ValidationTool.compare_values(actual_timeout, timeout).verify_result()


def validate_ib_default_config(selected_port):
    """
    Validate IB PHY recovery configuration has default values.

    For IB: logic-relock-mode=disabled, logic-relock-timeout=0

    Args:
        selected_port: Fae port object

    Raises:
        AssertionError: If validation fails
    """
    with allure.step("Check IB default config (logic-relock)"):
        output_fae_port = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.port.interface.link.phy_recovery.show()
        ).get_returned_value()

        filtered_out = {
            key: value for key, value in output_fae_port.items()
            if key in IbPhyRecoveryConfig.DEFAULT_CONFIG
        }
        ValidationTool.compare_dictionaries(
            filtered_out,
            IbPhyRecoveryConfig.DEFAULT_CONFIG
        ).verify_result()


# =============================================================================
# Configuration Application Helpers
# =============================================================================

def _is_bulk_operation(port_name: str) -> bool:
    """
    Check if port name represents a bulk operation (port range).

    Args:
        port_name: Port name to check (e.g., "sw1p1" or "sw1-72p1-2")

    Returns:
        True if bulk operation (port range), False otherwise

    Example:
        _is_bulk_operation("sw1p1")          # Returns False (single port)
        _is_bulk_operation("sw1-72p1-2")    # Returns True (port range)
    """
    return '-' in port_name and port_name.count('-') >= 2


def _bulk_apply_config(timeout_ms: int = IbPhyRecoveryTestConsts.BULK_APPLY_TIMEOUT_MS):
    """
    Apply staged configuration with extended timeout for bulk operations.

    This helper handles the 'nv config apply' command with appropriate timeout
    for bulk operations on many ports (e.g., 144 IB ports).

    Note: NVUE can legally return a "no config diff" message for idempotent applies
    (e.g., re-applying same values, unsetting already-default config). This is
    treated as success, consistent with NvueGeneralCli.apply_config behavior.

    Args:
        timeout_ms: Timeout in milliseconds for apply operation

    Raises:
        AssertionError: If config apply fails (excluding no-diff cases)
    """
    with allure.step(f"Apply config with extended timeout ({timeout_ms}ms)"):
        engine = TestToolkit.engines.dut
        start_time = time.perf_counter()
        output = engine.run_cmd('nv config apply -y', timeout=timeout_ms)
        duration = time.perf_counter() - start_time

        # Verify apply succeeded - treat "no config diff" as success (idempotent apply)
        is_applied = ConfState.APPLIED in output.lower()
        is_no_diff = NvosConst.NO_CONFIG_DIFF_APPLY_MSG in output

        logger.info(f"Bulk apply completed in {duration:.2f}s")

        if not (is_applied or is_no_diff):
            raise AssertionError(f"Config apply failed. Output: {output}")


def _apply_config_with_bulk_support(
    fae_port,
    config_key: Optional[str],
    config_value,
    step_description: str
):
    """
    Apply configuration with automatic bulk operation support.

    This common helper eliminates code duplication between apply_ib_mode,
    apply_ib_timeout, and unset_ib_config by handling both single port
    and bulk port range operations.

    Args:
        fae_port: Fae object (single port or port range like "sw1-18p1-2")
        config_key: Configuration key to set (or None for unset)
        config_value: Value to apply (or None for unset)
        step_description: Description for allure step

    Example:
        # Set mode to enabled
        _apply_config_with_bulk_support(
            fae_port, IbPhyRecoveryConfig.MODE, "enabled",
            "Apply logic-relock-mode=enabled"
        )

        # Unset configuration (pass None for config_key)
        _apply_config_with_bulk_support(
            fae_port, None, None,
            "Unset IB PHY recovery configuration"
        )
    """
    with allure.step(step_description):
        is_bulk = _is_bulk_operation(fae_port.port.name)
        use_staged_apply = is_bulk and TestToolkit.tested_api == ApiType.NVUE

        # Build common kwargs based on apply strategy
        if use_staged_apply:
            # Bulk NVUE: stage config without immediate apply
            apply_kwargs = {"apply": False}
        else:
            # Single port or OpenAPI: apply immediately with confirmation
            apply_kwargs = {"apply": True, "ask_for_confirmation": True}

        # Execute set or unset operation
        if config_key is None:
            fae_port.port.interface.link.phy_recovery.unset(**apply_kwargs).verify_result()
        else:
            fae_port.port.interface.link.phy_recovery.set(
                config_key, config_value, **apply_kwargs
            ).verify_result()

        # For bulk NVUE operations, apply staged config with extended timeout
        if use_staged_apply:
            _bulk_apply_config()

    # Wait for config to take effect
    with allure.step(f"Wait {IbPhyRecoveryTestConsts.CONFIG_APPLY_WAIT_SECONDS}s for config to take effect"):
        time.sleep(IbPhyRecoveryTestConsts.CONFIG_APPLY_WAIT_SECONDS)


def get_current_ib_mode(fae_port) -> str:
    """
    Get the current logic-relock-mode from a port.

    Args:
        fae_port: Fae object for a SINGLE port

    Returns:
        Current mode string (enabled/disabled/fw-default)
    """
    output = OutputParsingTool.parse_json_str_to_dictionary(
        fae_port.port.interface.link.phy_recovery.show()
    ).get_returned_value()

    current_mode = output.get(IbPhyRecoveryConfig.MODE, IbPhyRecoveryConfig.DEFAULT_MODE)
    logger.info(f"Current {IbPhyRecoveryConfig.MODE} for {fae_port.port.name}: {current_mode}")
    return current_mode


def apply_ib_mode(fae_port, mode: str) -> ResultObj:
    """
    Apply logic-relock-mode to the selected port(s).

    Uses extended timeout for bulk operations (port ranges) to handle
    the increased time needed to apply config to many ports (e.g., 144 IB ports).

    Args:
        fae_port: Fae object (can be single port or port range like "sw1-18p1-2")
        mode: Mode to apply (enabled/disabled/fw-default)

    Returns:
        ResultObj(True) on success

    Example:
        # Apply to single port
        apply_ib_mode(Fae(port_name="sw1p1"), IbPhyRecoveryConfig.ENABLED)

        # Apply to all ports
        apply_ib_mode(Fae(port_name="sw1-18p1-2"), IbPhyRecoveryConfig.ENABLED)
    """
    _apply_config_with_bulk_support(
        fae_port,
        IbPhyRecoveryConfig.MODE,
        mode,
        f"Apply {IbPhyRecoveryConfig.MODE}={mode}"
    )
    return ResultObj(True)


def apply_ib_mode_if_needed(fae_port, mode: str) -> bool:
    """
    Apply logic-relock-mode only if it's not already set to the desired value.

    Checks the current mode first and only applies if different.

    Args:
        fae_port: Fae object for a SINGLE port
        mode: Mode to apply (enabled/disabled/fw-default)

    Returns:
        True if mode was applied, False if already set

    Example:
        if apply_ib_mode_if_needed(fae_port, IbPhyRecoveryConfig.ENABLED):
            print("Mode was changed")
        else:
            print("Mode was already enabled")
    """
    current_mode = get_current_ib_mode(fae_port)

    # fw-default maps to disabled operationally
    effective_current = (
        IbPhyRecoveryConfig.DISABLED
        if current_mode == IbPhyRecoveryConfig.FW_DEFAULT
        else current_mode
    )
    effective_target = (
        IbPhyRecoveryConfig.DISABLED
        if mode == IbPhyRecoveryConfig.FW_DEFAULT
        else mode
    )

    if effective_current == effective_target:
        logger.info(f"Mode already set to {mode} (current: {current_mode}), skipping apply")
        with allure.step(f"Mode already {mode}, no change needed"):
            pass
        return False

    apply_ib_mode(fae_port, mode)
    return True


def apply_ib_timeout(fae_port, timeout: int) -> ResultObj:
    """
    Apply logic-relock-timeout to the selected port(s).

    Uses extended timeout for bulk operations (port ranges) to handle
    the increased time needed to apply config to many ports.

    Args:
        fae_port: Fae object (can be single port or port range like "sw1-18p1-2")
        timeout: Timeout value (0-255 for IB)

    Returns:
        ResultObj(True) on success

    Raises:
        ValueError: If timeout is out of range (0-255)
    """
    if not IbPhyRecoveryConfig.TIMEOUT_MIN <= timeout <= IbPhyRecoveryConfig.TIMEOUT_MAX:
        raise ValueError(
            f"Timeout {timeout} out of range "
            f"({IbPhyRecoveryConfig.TIMEOUT_MIN}-{IbPhyRecoveryConfig.TIMEOUT_MAX})"
        )

    _apply_config_with_bulk_support(
        fae_port,
        IbPhyRecoveryConfig.TIMEOUT,
        timeout,
        f"Apply {IbPhyRecoveryConfig.TIMEOUT}={timeout}"
    )
    return ResultObj(True)


def verify_ib_config(selected_port, mode: str, timeout: Optional[int] = None):
    """
    Verify mode and timeout are applied to the selected port with retries.

    Args:
        selected_port: Fae object for a SINGLE port (to verify settings)
        mode: Expected mode
        timeout: Expected timeout (optional)
    """
    retry_call(
        validate_ib_mode_set,
        [selected_port, mode, timeout],
        exceptions=AssertionError,
        tries=IbPhyRecoveryTestConsts.VALIDATE_RETRIES,
        delay=IbPhyRecoveryTestConsts.VALIDATE_RETRY_DELAY_SECONDS,
    )


def unset_ib_config(fae_port) -> ResultObj:
    """
    Unset IB PHY recovery configuration to restore defaults.

    Uses extended timeout for bulk operations (port ranges) to handle
    the increased time needed to apply config to many ports.

    Args:
        fae_port: Fae object (can be single port or port range like "sw1-18p1-2")

    Returns:
        ResultObj(True) on success

    Example:
        # Unset config on all ports
        unset_ib_config(Fae(port_name="sw1-72p1-2"))
    """
    _apply_config_with_bulk_support(
        fae_port,
        None,  # None indicates unset operation
        None,
        "Unset IB PHY recovery configuration"
    )
    return ResultObj(True)


def cleanup_phy_recovery_config(fae_port):
    """
    Reusable cleanup helper to unset PHY recovery config and verify defaults.

    This helper performs:
    1. Unsets the PHY recovery configuration to restore defaults
    2. Verifies the configuration was restored to default values with retries

    Args:
        fae_port: Fae object (single port or port range)

    Example:
        # In test cleanup (finally block)
        cleanup_phy_recovery_config(fae_port)

        # Or after traffic tests
        cleanup_phy_recovery_config(Fae(port_name=selected_port.name))
    """
    with allure.step("Cleanup: Unset configuration to return to defaults"):
        fae_port.port.interface.link.phy_recovery.unset(
            apply=True,
            ask_for_confirmation=True
        )

    with allure.step("Verify configuration restored to defaults"):
        retry_call(
            validate_ib_default_config,
            [fae_port],
            exceptions=AssertionError,
            tries=IbPhyRecoveryTestConsts.VALIDATE_RETRIES,
            delay=IbPhyRecoveryTestConsts.VALIDATE_RETRY_DELAY_SECONDS
        )


# =============================================================================
# Traffic Test Helpers
# =============================================================================

def _assert_both_host_interfaces_up(host_a, host_b):
    """Raise AssertionError if either host's IB interface is not Up. Used with retry_call."""
    ha_out = host_a.run_cmd(IbConsts.IB_DEV_2_NET_DEV)
    hb_out = host_b.run_cmd(IbConsts.IB_DEV_2_NET_DEV)
    if "(Up)" not in ha_out or "(Up)" not in hb_out:
        raise AssertionError(
            f"Host interfaces not Up. Host A: {ha_out.strip()}. Host B: {hb_out.strip()}"
        )


def setup_traffic_test(engines, devices, traffic_duration: str, server_output: str, client_output: str):
    """
    Common setup for traffic-based PHY recovery tests.

    Performs:
    1. Select random traffic port from configured traffic_ports (LINK-UP)
    2. Enable PHY recovery mode (logic-relock-mode) if not already enabled
    3. Record initial recovery counters (successful-recovery-events and total-successful-recovery-events)
    4. Start IB traffic using ib_send_lat between 2 hosts (ha -> hb)
       - Verifies both host interfaces are Up before starting
       - Runs for specified duration with output saved to files

    Args:
        engines: Test engines fixture (must have ha, hb, dut)
        devices: Test devices fixture
        traffic_duration: Traffic duration in seconds (string format for ib_send_lat)
        server_output: Server output file name (on host_a)
        client_output: Client output file name (on host_b)

    Returns:
        Tuple of (selected_port, initial_counters, traffic_start_time)

    Raises:
        pytest.skip: If no traffic ports available for the DUT IP

    Example:
        port, initial, start_time = setup_traffic_test(
            engines, devices,
            IbPhyRecoveryTestConsts.TRAFFIC_DURATION_7MIN_SECONDS,
            IbPhyRecoveryTestConsts.TRAFFIC_SERVER_OUTPUT_7MIN,
            IbPhyRecoveryTestConsts.TRAFFIC_CLIENT_OUTPUT_7MIN
        )
    """
    # Validate required engines for traffic tests
    required_engines = ['ha', 'hb', 'dut']
    for eng in required_engines:
        if not hasattr(engines, eng):
            pytest.skip(f"Required engine '{eng}' not available for traffic test")

    with allure.step("Get a random traffic port (LINK-UP)"):
        selected_port = get_traffic_port()
        if not selected_port:
            pytest.skip("No traffic ports available")
        logger.info(f"Selected traffic port: {selected_port.name}")

    fae_port = Fae(port_name=selected_port.name)

    with allure.step(f"Set {IbPhyRecoveryConfig.MODE} to {IbPhyRecoveryConfig.ENABLED} if not already enabled"):
        mode_was_changed = apply_ib_mode_if_needed(fae_port, IbPhyRecoveryConfig.ENABLED)
        logger.info(f"Mode was changed: {mode_was_changed}")

    with allure.step(f"Verify mode is {IbPhyRecoveryConfig.ENABLED} on port {selected_port.name}"):
        verify_ib_config(fae_port, IbPhyRecoveryConfig.ENABLED)

    with allure.step("Wait for both host interfaces to be Up before starting traffic"):
        start = time.time()
        retry_call(
            _assert_both_host_interfaces_up,
            [engines.ha, engines.hb],
            exceptions=AssertionError,
            tries=IbPhyRecoveryTestConsts.WAIT_HOST_INTERFACES_UP_TRIES,
            delay=IbPhyRecoveryTestConsts.WAIT_HOST_INTERFACES_UP_DELAY_SECONDS,
        )
        duration_sec = time.time() - start
        logger.info("Both host interfaces Up after %.1fs", duration_sec)
        allure.attach("wait_host_interfaces_up_duration_sec", f"{duration_sec:.1f}s")

    with allure.step("Record initial recovery counters (successful-recovery-events and total-successful-recovery-events)"):
        initial_counters = get_phy_recovery_counters(selected_port.name)
        initial_successful = initial_counters.get(IbPhyRecoveryCounters.SUCCESSFUL_RECOVERY_EVENTS, 0)
        initial_total = initial_counters.get(IbPhyRecoveryCounters.TOTAL_SUCCESSFUL_RECOVERY_EVENTS, 0)
        logger.info(
            "Initial recovery counters: successful-recovery-events=%s, total-successful-recovery-events=%s",
            initial_successful, initial_total,
        )

    with allure.step(f"Start IB traffic ({int(traffic_duration) // 60} minutes) between 2 hosts"):
        traffic_start_time = Tools.TrafficGeneratorTool.start_traffic_between_2_hosts(
            engines.ha,
            engines.hb,
            traffic_duration,
            server_output,
            client_output
        )
        logger.info(f"Traffic started at: {traffic_start_time}")

    return selected_port, initial_counters, traffic_start_time


def teardown_traffic_test(
    engines, devices, selected_port, initial_counters,
    traffic_start_time, traffic_timeout: int, server_output: str, client_output: str
):
    """
    Common teardown for traffic-based PHY recovery tests.

    Performs:
    1. Stop traffic and verify results:
       - Verifies no 'error' or 'loss' in ib_send_lat output
       - Verifies client iterations == server iterations (all packets received)
    2. Verify at least one of successful-recovery-events or total-successful-recovery-events increased

    Note: Cleanup (kill_traffic_processes, cleanup_phy_recovery_config) should be
    handled in the calling test's finally block to ensure it runs even if this
    function fails.

    Args:
        engines: Test engines fixture
        devices: Test devices fixture
        selected_port: Port object from setup
        initial_counters: Initial counters from setup
        traffic_start_time: Traffic start time from setup
        traffic_timeout: Traffic timeout in seconds
        server_output: Server output file name
        client_output: Client output file name

    Example:
        try:
            teardown_traffic_test(...)
        finally:
            kill_traffic_processes(engines)
            cleanup_phy_recovery_config(Fae(port_name=selected_port.name))
    """
    try:
        with allure.step("Stop traffic and verify results"):
            # stop_traffic_between_2_hosts verifies:
            # 1. No 'error' or 'loss' in client/server output
            # 2. Client iterations == Server iterations (all packets received)
            # Returns the number of iterations completed
            num_of_iterations = Tools.TrafficGeneratorTool.stop_traffic_between_2_hosts(
                engines.ha,
                engines.hb,
                traffic_start_time,
                traffic_timeout,
                server_output,
                client_output
            )
            logger.info(f"Traffic completed successfully with {num_of_iterations} iterations")

        # Wait for recovery counters to update; pass if either counter increased
        initial_successful = initial_counters.get(IbPhyRecoveryCounters.SUCCESSFUL_RECOVERY_EVENTS, 0)
        initial_total = initial_counters.get(IbPhyRecoveryCounters.TOTAL_SUCCESSFUL_RECOVERY_EVENTS, 0)
        final_successful = wait_for_recovery_counters_update(
            port_name=selected_port.name,
            initial_count=initial_successful,
            initial_total_count=initial_total,
            max_wait_seconds=IbPhyRecoveryTestConsts.VALIDATE_RETRIES * IbPhyRecoveryTestConsts.VALIDATE_RETRY_DELAY_SECONDS,
            poll_interval_seconds=IbPhyRecoveryTestConsts.VALIDATE_RETRY_DELAY_SECONDS
        )
        logger.info("Recovery counter verification passed (at least one increased): %s -> %s", initial_successful, final_successful)

    except Exception as e:
        # Log link errors on traffic ports for debugging when traffic verification fails
        logger.error(f"Traffic verification failed: {e}")
        with allure.step("Debug: Check link errors on traffic ports"):
            error_result = Tools.TrafficValidatorTool.verify_no_link_errors(engines.dut, devices.dut)
            if not error_result.result:
                logger.error(f"Link errors found on traffic ports: {error_result.info}")
            else:
                logger.info("No link errors found on traffic ports")
            # Mark as ignored since we're just logging for debug purposes
            error_result.ignore_result()
        raise  # Re-raise the original exception
    # Note: Cleanup (kill_traffic_processes, cleanup_phy_recovery_config) should be
    # handled in the calling test's finally block to avoid duplicate cleanup


def wait_for_traffic_running(
    engines,
    wait_seconds: int = IbPhyRecoveryTestConsts.TRAFFIC_RUNNING_WAIT_SECONDS,
    poll_interval: int = IbPhyRecoveryTestConsts.TRAFFIC_RUNNING_POLL_INTERVAL
) -> ResultObj:
    """
    Wait and verify that traffic processes are running on both hosts.

    This function polls both hosts to verify that ib_send_lat processes are active,
    ensuring traffic has started successfully before proceeding with the test.

    Args:
        engines: Test engines fixture (must have ha, hb attributes)
        wait_seconds: Total time to verify traffic is running (default: 60 seconds)
        poll_interval: Interval between polls (default: 10 seconds)

    Returns:
        ResultObj indicating success if traffic is running on both hosts throughout
        the wait period, or failure if traffic stops prematurely

    Example:
        result = wait_for_traffic_running(engines, wait_seconds=60)
        result.verify_result()
    """
    with allure.step(f"Verify traffic is running for {wait_seconds} seconds"):
        num_polls = wait_seconds // poll_interval

        for i in range(num_polls):
            # Check if ib_send_lat is running on both hosts
            server_pid = Tools.TrafficGeneratorTool.check_command_id_on_host(
                engines.ha, 'ib_send_lat'
            )
            client_pid = Tools.TrafficGeneratorTool.check_command_id_on_host(
                engines.hb, 'ib_send_lat'
            )

            if not server_pid or not client_pid:
                return ResultObj(
                    False,
                    info=f"Traffic stopped prematurely at poll {i + 1}/{num_polls}. "
                    f"Server PID: {server_pid or 'None'}, Client PID: {client_pid or 'None'}"
                )

            logger.info(
                f"Traffic running check {i + 1}/{num_polls}: "
                f"Server PID={server_pid}, Client PID={client_pid}"
            )
            time.sleep(poll_interval)

        # Final check after wait period
        server_pid = Tools.TrafficGeneratorTool.check_command_id_on_host(
            engines.ha, 'ib_send_lat'
        )
        client_pid = Tools.TrafficGeneratorTool.check_command_id_on_host(
            engines.hb, 'ib_send_lat'
        )

        if server_pid and client_pid:
            logger.info(
                f"Traffic verified running for {wait_seconds}s. "
                f"Server PID={server_pid}, Client PID={client_pid}"
            )
            return ResultObj(True, info=f"Traffic running successfully for {wait_seconds} seconds")

        return ResultObj(
            False,
            info=f"Traffic stopped at final check. "
            f"Server PID: {server_pid or 'None'}, Client PID: {client_pid or 'None'}"
        )


def kill_traffic_processes(engines) -> None:
    """
    Kill any remaining ib_send_lat traffic processes on both hosts.

    This is a cleanup helper that ensures traffic processes are terminated.
    Intended for use in finally blocks to guarantee cleanup even if test fails.

    Args:
        engines: Test engines fixture (must have ha, hb attributes)

    Example:
        try:
            # test logic
        finally:
            kill_traffic_processes(engines)
    """
    with allure.step("Kill any remaining traffic processes"):
        # Kill on both hosts - use SIGINT for graceful termination first
        engines.ha.run_cmd("pkill -SIGINT -f ib_send_lat || true", validate=False)
        engines.hb.run_cmd("pkill -SIGINT -f ib_send_lat || true", validate=False)
        logger.info("Sent SIGINT to any remaining ib_send_lat processes")

        # Give processes time to terminate gracefully
        time.sleep(IbPhyRecoveryTestConsts.TRAFFIC_KILL_GRACE_PERIOD_SECONDS)

        # Force kill if still running
        engines.ha.run_cmd("pkill -9 -f ib_send_lat || true", validate=False)
        engines.hb.run_cmd("pkill -9 -f ib_send_lat || true", validate=False)
        logger.info("Force killed any remaining ib_send_lat processes")


def verify_traffic_stopped_and_cleanup(engines) -> ResultObj:
    """
    Verify that traffic stopped (client death is expected during error injection) and cleanup.

    During error injection, the traffic client typically dies because the link is broken.
    This is EXPECTED behavior when simulating a broken cable. This function:
    1. Checks if traffic processes are still running (logs status)
    2. Kills any remaining ib_send_lat processes on both hosts
    3. Returns success - client death is expected, not a failure

    Args:
        engines: Test engines fixture (must have ha, hb attributes)

    Returns:
        ResultObj indicating cleanup success and what was found

    Example:
        # After error injection period
        result = verify_traffic_stopped_and_cleanup(engines)
        logger.info(f"Traffic cleanup: {result.info}")
    """
    with allure.step("Verify traffic stopped and cleanup remaining processes"):
        # Check current state of traffic processes
        server_running = False
        client_running = False

        with allure.step("Check traffic process status on hosts"):
            # Check server (host_a)
            server_check = engines.ha.run_cmd("pgrep -f ib_send_lat || echo 'not_running'", validate=False)
            server_running = 'not_running' not in server_check
            logger.info(f"Traffic server (host_a) running: {server_running}")

            # Check client (host_b)
            client_check = engines.hb.run_cmd("pgrep -f ib_send_lat || echo 'not_running'", validate=False)
            client_running = 'not_running' not in client_check
            logger.info(f"Traffic client (host_b) running: {client_running}")

        status_msg = (f"Server running: {server_running}, Client running: {client_running}. "
                      "Client death during error injection is expected behavior.")

        # Use the shared cleanup function
        kill_traffic_processes(engines)

        return ResultObj(True, info=status_msg)


def verify_traffic_restored(engines, players, interfaces, setup_name, wait_time: int = 10) -> ResultObj:
    """
    Verify that traffic is working again after link recovery.

    This function:
    1. Waits for the link to stabilize
    2. Verifies host interfaces are Up
    3. Sends a one-shot IB traffic test to confirm connectivity

    Args:
        engines: Test engines fixture
        players: Players fixture
        interfaces: Interfaces fixture
        setup_name: Setup name
        wait_time: Time to wait for link stabilization (default: 10 seconds)

    Returns:
        ResultObj indicating traffic verification success/failure

    Example:
        # After recovery trigger and waiting
        result = verify_traffic_restored(engines, players, interfaces, setup_name)
        result.verify_result()
    """
    with allure.step(f"Wait {wait_time}s for link to stabilize"):
        time.sleep(wait_time)

    with allure.step("Verify host interfaces are Up"):
        ha_output = engines.ha.run_cmd(IbConsts.IB_DEV_2_NET_DEV)
        hb_output = engines.hb.run_cmd(IbConsts.IB_DEV_2_NET_DEV)

        ha_up = '(Up)' in ha_output
        hb_up = '(Up)' in hb_output

        logger.info(f"Host A interface Up: {ha_up} - {ha_output.split()[0] if ha_output else 'N/A'}")
        logger.info(f"Host B interface Up: {hb_up} - {hb_output.split()[0] if hb_output else 'N/A'}")

        if not (ha_up and hb_up):
            return ResultObj(False, info=f"Host interfaces not Up. HA: {ha_up}, HB: {hb_up}")

    with allure.step("Send IB traffic to verify connectivity restored"):
        traffic_result = Tools.TrafficGeneratorTool.send_ib_traffic(
            players, interfaces, setup_name, should_success=True
        )

        if traffic_result.result:
            logger.info("Traffic successfully restored after recovery")
            return ResultObj(True, info="Traffic restored and working")
        else:
            logger.error(f"Traffic verification failed: {traffic_result.info}")
            return ResultObj(False, info=f"Traffic failed after recovery: {traffic_result.info}")


def verify_link_recovery_and_traffic(engines, devices, players, interfaces, setup_name, selected_port, wait_time: int = 10):
    """
    Verify that link recovers after error injection and traffic works again.

    This function waits for the link to recover (typically ~10 seconds) and then
    verifies traffic can flow again by sending a one-shot traffic test.

    Args:
        engines: Test engines fixture
        devices: Test devices fixture
        players: Players fixture
        interfaces: Interfaces fixture
        setup_name: Setup name
        selected_port: Port that was injected with errors
        wait_time: Time to wait for link recovery (default: 10 seconds)

    Example:
        # After disabling error injection
        verify_link_recovery_and_traffic(
            engines, devices, players, interfaces, setup_name, selected_port
        )
    """
    with allure.step(f"Wait {wait_time}s for link to recover after stopping error injection"):
        time.sleep(wait_time)

    with allure.step("Verify traffic is restored after recovery"):
        port_obj = Port(selected_port.name, '', '')
        link_state = port_obj.interface.link.state.show()
        logger.info(f"Link state after recovery: {link_state}")

        restored_traffic = Tools.TrafficGeneratorTool.send_ib_traffic(
            players, interfaces, setup_name, should_success=True
        )
        restored_traffic.verify_result()
        logger.info("Traffic successfully restored after error injection stopped")
