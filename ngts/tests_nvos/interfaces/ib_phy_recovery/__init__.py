"""
IB PHY Recovery Module

This module provides constants, helpers, and utilities for testing IB (InfiniBand)
interface PHY recovery functionality.

Module Structure:
    - consts.py: Constants for IB PHY recovery (counters, config, error messages)
    - helpers.py: Reusable helper functions for PHY recovery tests

Usage:
    from ngts.tests_nvos.interfaces.ib_phy_recovery.consts import (
        IbPhyRecoveryCounters,
        IbPhyRecoveryConfig,
        PREIErrorInjection,
    )
    from ngts.tests_nvos.interfaces.ib_phy_recovery.helpers import (
        get_phy_recovery_counters,
        trigger_recovery_go_once,
        inject_error_via_prei,
    )
"""

from ngts.tests_nvos.interfaces.ib_phy_recovery.consts import (
    IbPhyRecoveryCounters,
    IbPhyRecoveryConfig,
    PREIErrorInjection,
    IbPhyRecoveryTestConsts,
    ErrorMessages,
    GoOnceConsts,
)

from ngts.tests_nvos.interfaces.ib_phy_recovery.helpers import (
    get_random_ib_port_in_state,
    get_traffic_port,
    get_local_port_and_mst_device,
    inject_error_via_prei,
    disable_error_injection,
    trigger_recovery_go_once,
    get_phy_recovery_counters,
    get_successful_recovery_events,
    clear_recovery_counters,
    validate_recovery_counters_increased,
    validate_traffic_counters_increased,
    wait_for_recovery_counters_update,
    wait_for_traffic_running,
    kill_traffic_processes,
    verify_traffic_stopped_and_cleanup,
    verify_traffic_restored,
    cleanup_phy_recovery_config,
    validate_link_state,
    validate_ib_mode_set,
    validate_ib_default_config,
    get_all_ib_ports_range,
    get_current_ib_mode,
    apply_ib_mode,
    apply_ib_mode_if_needed,
    apply_ib_timeout,
    verify_ib_config,
    unset_ib_config,
    setup_traffic_test,
    teardown_traffic_test,
    verify_link_recovery_and_traffic,
)

__all__ = [
    # Constants
    "IbPhyRecoveryCounters",
    "IbPhyRecoveryConfig",
    "PREIErrorInjection",
    "IbPhyRecoveryTestConsts",
    "ErrorMessages",
    "GoOnceConsts",
    # Helpers
    "get_random_ib_port_in_state",
    "get_traffic_port",
    "get_local_port_and_mst_device",
    "inject_error_via_prei",
    "disable_error_injection",
    "trigger_recovery_go_once",
    "get_phy_recovery_counters",
    "get_successful_recovery_events",
    "clear_recovery_counters",
    "validate_recovery_counters_increased",
    "validate_traffic_counters_increased",
    "wait_for_recovery_counters_update",
    "wait_for_traffic_running",
    "kill_traffic_processes",
    "verify_traffic_stopped_and_cleanup",
    "verify_traffic_restored",
    "cleanup_phy_recovery_config",
    "validate_link_state",
    "validate_ib_mode_set",
    "validate_ib_default_config",
    "get_all_ib_ports_range",
    "get_current_ib_mode",
    "apply_ib_mode",
    "apply_ib_mode_if_needed",
    "apply_ib_timeout",
    "verify_ib_config",
    "unset_ib_config",
    "setup_traffic_test",
    "teardown_traffic_test",
    "verify_link_recovery_and_traffic",
]
