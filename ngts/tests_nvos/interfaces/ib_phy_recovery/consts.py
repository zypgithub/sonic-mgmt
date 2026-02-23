"""
IB PHY Recovery Constants

This module contains all constants for IB (InfiniBand) PHY recovery tests.

Key Differences from NVLink:
    - IB uses `logic-relock-mode` and `logic-relock-timeout` (NOT serdes-eq)
    - IB timeout range is 0-126 (NVLink is 0-2550)
    - Recovery counters are viewed via `nv show interface <port> link phy detail`

Classes:
    IbPhyRecoveryCounters: Recovery counter names and defaults
    IbPhyRecoveryConfig: Configuration parameter names, modes, and ranges
    PREIErrorInjection: PREI register error injection parameters
    IbPhyRecoveryTestConsts: General test timing and retry constants
    ErrorMessages: Expected error messages for negative testing
    GoOnceConsts: Go-once action related constants
"""


class IbPhyRecoveryCounters:
    """
    Constants for IB PHY recovery counters.

    Recovery counters are obtained via:
        nv show interface <port> link phy detail

    Can be filtered with:
        nv show interface <port> link phy detail | grep -i recovery

    Primary counter for validation: `successful-recovery-events`
    """
    # Primary counter to verify recovery events
    SUCCESSFUL_RECOVERY_EVENTS = "successful-recovery-events"

    # Additional recovery-related counters from phy detail output
    TOTAL_SUCCESSFUL_RECOVERY_EVENTS = "total-successful-recovery-events"
    TIME_IN_LAST_LOGIC_RECOVERY_EVENT = "time-in-last-logic-recovery-event"
    TIME_SINCE_LAST_RECOVERY = "time-since-last-recovery"
    LAST_LOGIC_RECOVERY_ATTEMPTS = "last-logic-recovery-attempts"
    TIME_BETWEEN_LAST_TWO_RECOVERIES = "time-between-last-two-recoveries"
    UNINTENTIONAL_LINK_DOWN_EVENTS = "unintentional-link-down-events"
    INTENTIONAL_LINK_DOWN_EVENTS = "intentional-link-down-events"

    # All recovery counter names for comprehensive checks
    ALL_COUNTERS = [
        SUCCESSFUL_RECOVERY_EVENTS,
        TOTAL_SUCCESSFUL_RECOVERY_EVENTS,
        TIME_IN_LAST_LOGIC_RECOVERY_EVENT,
        TIME_SINCE_LAST_RECOVERY,
        LAST_LOGIC_RECOVERY_ATTEMPTS,
        TIME_BETWEEN_LAST_TWO_RECOVERIES,
        UNINTENTIONAL_LINK_DOWN_EVENTS,
        INTENTIONAL_LINK_DOWN_EVENTS,
    ]

    # Default values (should be 0 initially on fresh system)
    DEFAULT_VALUES = {
        SUCCESSFUL_RECOVERY_EVENTS: 0,
        TOTAL_SUCCESSFUL_RECOVERY_EVENTS: 0,
        TIME_IN_LAST_LOGIC_RECOVERY_EVENT: 0,
        TIME_SINCE_LAST_RECOVERY: 0,
        LAST_LOGIC_RECOVERY_ATTEMPTS: 0,
        TIME_BETWEEN_LAST_TWO_RECOVERIES: 0,
    }


class IbPhyRecoveryConfig:
    """
    IB-specific PHY recovery configuration constants.

    IMPORTANT: For IB interfaces, we use:
        - logic-relock-mode (NOT serdes-eq-mode which is for NVLink)
        - logic-relock-timeout (NOT serdes-eq-timeout which is for NVLink)

    Timeout range for IB: 0-126
    Timeout range for NVLink: 0-2550 (different!)
    """
    # Mode attribute names (IB uses logic-relock)
    MODE = "logic-relock-mode"
    TIMEOUT = "logic-relock-timeout"

    # Valid modes
    ENABLED = "enabled"
    DISABLED = "disabled"
    FW_DEFAULT = "fw-default"
    MODES = [ENABLED, DISABLED, FW_DEFAULT]

    # Timeout range for IB (0-126, different from NVLink's 0-2550)
    TIMEOUT_MIN = 0
    TIMEOUT_MAX = 126

    # Default values
    DEFAULT_MODE = DISABLED
    DEFAULT_TIMEOUT = 0

    # Default configuration dictionary for validation
    # Note: TIMEOUT stored as string to match API response format
    DEFAULT_CONFIG = {
        MODE: DISABLED,
        TIMEOUT: str(DEFAULT_TIMEOUT),
    }

    # Lane suffixes to try when getting local port info
    # (pl1 is usually primary, but we try others as fallback)
    LANES = ["pl1", "pl2", "pl3", "pl4"]


class PREIErrorInjection:
    """
    PREI (PHY Recovery Error Injection) register constants.

    Used for error injection via mlxreg to simulate cable/PHY issues.

    Command format:
        sudo mlxreg -d <mst_dev> --reg_name PREI \
            --set 'local_port=<port>,error_type_admin=<type>,error_injection_time=<time>' --yes

    error_type_admin=4: Trigger recovery
    error_injection_time values:
        - 0xFFFF: Always fail (simulates broken cable) - recovery always fails
        - 5: Noise injection (simulates flaky cable) - intermittent errors
        - 0x0000: Disable error injection
    """

    # Error type that triggers recovery
    ERROR_TYPE_ADMIN_TRIGGER_RECOVERY = 4

    # Error injection time values
    # Note: Per documentation test plan, values are:
    #   - 0xFFFF = always-fail (broken cable simulation - recovery always fails)
    #   - 5 = noise injection (flaky cable simulation - intermittent errors)
    TIME_ALWAYS_FAIL = 0xFFFF  # Broken cable simulation - recovery always fails
    TIME_NOISE = 5             # Flaky cable simulation - intermittent errors
    TIME_DISABLE = 0           # Disable error injection

    # Descriptive aliases
    BROKEN_CABLE = TIME_ALWAYS_FAIL
    FLAKY_CABLE = TIME_NOISE
    DISABLED = TIME_DISABLE


class IbPhyRecoveryTestConsts:
    """
    General test timing and retry constants for IB PHY recovery tests.
    """
    # Counter update wait time (recovery counters can take up to 30 seconds to update)
    RECOVERY_COUNTER_UPDATE_WAIT_SECONDS = 30

    # Retry settings for validation
    VALIDATE_RETRIES = 6
    VALIDATE_RETRY_DELAY_SECONDS = 5

    # Timeout constants for IB PHY recovery test scenarios
    DEFAULT_TIMEOUT = 0
    HIGHER_TIMEOUT_MIN = 101
    HIGHER_TIMEOUT_MAX = 126

    # Number of triggers/injections for testing
    NUM_RECOVERY_GO_ONCE_TRIGGERS = 3
    NUM_NOISE_INJECTIONS = 3

    # Wait times for various operations
    ERROR_INJECTION_WAIT_SECONDS = 10
    BETWEEN_TRIGGERS_WAIT_SECONDS = 5
    LINK_STABILIZATION_WAIT_SECONDS = 10
    CONFIG_APPLY_WAIT_SECONDS = 10  # Wait for config to take effect after apply
    # Wait for both host IB interfaces Up after PHY recovery config (retries × delay ≈ max wait)
    WAIT_HOST_INTERFACES_UP_TRIES = 12   # 12 × 5s = 60s max
    WAIT_HOST_INTERFACES_UP_DELAY_SECONDS = 5

    # Noise injection test - run for 5 minutes with random delays
    NOISE_INJECTION_TOTAL_DURATION_SECONDS = 300  # 5 minutes
    NOISE_INJECTION_MIN_DELAY_SECONDS = 3
    NOISE_INJECTION_MAX_DELAY_SECONDS = 10

    # Always fail injection test - run continuously for 3 minutes
    ALWAYS_FAIL_DURATION_SECONDS = 180  # 3 minutes

    # Extended timeout for bulk port operations (144 IB ports can take 40+ seconds)
    # Default SSH timeout is 10s which is insufficient for large port ranges
    BULK_APPLY_TIMEOUT_MS = 120000  # 2 minutes in milliseconds

    # Traffic test constants
    TRAFFIC_DURATION_SECONDS = 60
    TRAFFIC_SERVER_OUTPUT_FILE = "/tmp/ib_recovery_server.log"
    TRAFFIC_CLIENT_OUTPUT_FILE = "/tmp/ib_recovery_client.log"

    # Long-running traffic test constants
    # 2 minutes for go-once test (quick recovery test)
    TRAFFIC_DURATION_2MIN_SECONDS = '120'  # 2 minutes (string format for ib_send_lat command)
    TRAFFIC_TIMEOUT_2MIN_SECONDS = 130     # 2 minutes + 10 seconds buffer
    TRAFFIC_SERVER_OUTPUT_2MIN = 'ib_phy_recovery_2min_server_output.txt'
    TRAFFIC_CLIENT_OUTPUT_2MIN = 'ib_phy_recovery_2min_client_output.txt'

    # 7 minutes for error injection tests (longer to cover injection + recovery)
    TRAFFIC_DURATION_7MIN_SECONDS = '420'  # 7 minutes (string format for ib_send_lat command)
    TRAFFIC_TIMEOUT_7MIN_SECONDS = 430     # 7 minutes + 10 seconds buffer
    TRAFFIC_SERVER_OUTPUT_7MIN = 'ib_phy_recovery_7min_server_output.txt'
    TRAFFIC_CLIENT_OUTPUT_7MIN = 'ib_phy_recovery_7min_client_output.txt'

    # Traffic running verification constants
    TRAFFIC_RUNNING_WAIT_SECONDS = 60      # Wait time to verify traffic is running
    TRAFFIC_RUNNING_POLL_INTERVAL = 10     # Poll interval for traffic running check
    TRAFFIC_KILL_GRACE_PERIOD_SECONDS = 2  # Grace period after SIGINT before SIGKILL


class ErrorMessages:
    """
    Expected error messages for negative testing (bad flow scenarios).

    Used to verify that invalid inputs are properly rejected with
    appropriate error messages.

    Note: NVUE CLI and OpenAPI return different error message formats.
    Use tuples to match either API's error for the same invalid input.

    NVUE CLI returns a generic range error for all timeout violations:
        "Valid range for logic-relock-timeout is 0 - 126"

    OpenAPI returns a specific error per violation type:
        Below min:   "<val> is less than the minimum of <min>"
        Above max:   "<val> is greater than the maximum of <max>"
        Non-integer: "'<val>' is not of type 'integer'"
    """
    # --- Timeout error messages ---

    # NVUE generic range error (same for all timeout violations)
    TIMEOUT_VALID_RANGE_NVUE = "Valid range for logic-relock-timeout is 0 - 126"

    # OpenAPI-specific error substrings (value-independent)
    TIMEOUT_BELOW_MIN_OPENAPI = "is less than the minimum of"
    TIMEOUT_ABOVE_MAX_OPENAPI = "is greater than the maximum of"
    TIMEOUT_NOT_INTEGER_OPENAPI = "is not of type 'integer'"

    # NVUE-specific error for non-integer value (e.g. "'x' is not an integer")
    TIMEOUT_NOT_INTEGER_NVUE = "is not an integer"

    # Combined tuples matching both NVUE and OpenAPI error formats
    TIMEOUT_BELOW_MIN_ANY = (TIMEOUT_VALID_RANGE_NVUE, TIMEOUT_BELOW_MIN_OPENAPI)
    TIMEOUT_ABOVE_MAX_ANY = (TIMEOUT_VALID_RANGE_NVUE, TIMEOUT_ABOVE_MAX_OPENAPI)
    TIMEOUT_NOT_INTEGER_ANY = (TIMEOUT_NOT_INTEGER_NVUE, TIMEOUT_NOT_INTEGER_OPENAPI)

    # --- Mode error messages ---

    # Error when setting invalid mode (same for NVUE and OpenAPI)
    BAD_MODE = "'bad-mode' is not one of"


class GoOnceConsts:
    """
    Constants for the PHY recovery go-once action.

    Action command: nv action start fae interface <port> link phy-recovery
    """
    # Invalid port types that should fail go-once action
    INVALID_PORT_TYPES = ["eth0", "lo"]  # mgmt and loopback ports

    # Expected output when action succeeds
    # NVUE returns: "Successfully triggered phy recovery..."
    # OpenAPI may return: "phy recovery triggered" or similar
    # Using tuple to match any of these possible success messages
    SUCCESS_OUTPUT_NVUE = "Successfully triggered"
    SUCCESS_OUTPUT_OPENAPI = "phy recovery triggered"
    SUCCESS_OUTPUT = (SUCCESS_OUTPUT_NVUE, SUCCESS_OUTPUT_OPENAPI)

    # Expected log message in syslog after successful action
    # Actual log format: "Got phy recovery event for port Infiniband<N>pl<M>"
    LOG_MESSAGE = "Got phy recovery event for port"
