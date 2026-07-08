"""
PLU PHY Recovery Constants

This module contains all constants for PLU PHY recovery tests.

Configuration uses `logic-relock-mode` and `logic-relock-timeout`.
Timeout range is 0-126.
Recovery counters are viewed via `nv show interface <port> link phy detail`.

Classes:
    PhyRecoveryConfig: Configuration parameter names, modes, and ranges
    PhyRecoveryTestConsts: General test timing and retry constants
    ErrorMessages: Expected error messages for negative testing
    GoOnceConsts: Go-once action related constants
"""


class PhyRecoveryConfig:
    """
    PHY recovery configuration constants.

    Uses:
        - logic-relock-mode
        - logic-relock-timeout

    Timeout range: 0-126
    """
    MODE = "logic-relock-mode"
    TIMEOUT = "logic-relock-timeout"

    ENABLED = "enabled"
    DISABLED = "disabled"
    FW_DEFAULT = "fw-default"
    MODES = [ENABLED, DISABLED, FW_DEFAULT]

    TIMEOUT_MIN = 0
    TIMEOUT_MAX = 126

    SUPPORTED_PORT_PREFIXES = ("sw", "acp")

    DEFAULT_MODE = DISABLED
    DEFAULT_TIMEOUT = 0

    # Default configuration dictionary for validation.
    # Timeout stored as string to match API response format.
    DEFAULT_CONFIG = {
        MODE: DISABLED,
        TIMEOUT: str(DEFAULT_TIMEOUT),
    }


class PhyRecoveryTestConsts:
    """
    Test timing and retry constants for PLU PHY recovery tests.
    """
    VALIDATE_RETRIES = 6
    VALIDATE_RETRY_DELAY_SECONDS = 5

    HIGHER_TIMEOUT_MIN = 101
    HIGHER_TIMEOUT_MAX = 126

    BETWEEN_TRIGGERS_WAIT_SECONDS = 5
    CONFIG_APPLY_WAIT_SECONDS = 10

    # Extended timeout for bulk port operations (many ports can take 40+ seconds).
    # Default SSH timeout is 10s which is insufficient for large port ranges.
    BULK_APPLY_TIMEOUT_MS = 120000  # 2 minutes in milliseconds


class ErrorMessages:
    """
    Expected error messages for negative testing (bad flow scenarios).

    Note: NVUE CLI and OpenAPI return different error message formats.
    Use tuples to match either API's error for the same invalid input.
    """
    # NVUE generic range error (same for all timeout violations)
    TIMEOUT_VALID_RANGE_NVUE = "Valid range for logic-relock-timeout is 0 - 126"

    # OpenAPI-specific error substrings
    TIMEOUT_BELOW_MIN_OPENAPI = "is less than the minimum of"
    TIMEOUT_ABOVE_MAX_OPENAPI = "is greater than the maximum of"
    TIMEOUT_NOT_INTEGER_OPENAPI = "is not of type 'integer'"

    # NVUE-specific error for non-integer value
    TIMEOUT_NOT_INTEGER_NVUE = "is not an integer"

    # Combined tuples matching both NVUE and OpenAPI error formats
    TIMEOUT_BELOW_MIN_ANY = (TIMEOUT_VALID_RANGE_NVUE, TIMEOUT_BELOW_MIN_OPENAPI)
    TIMEOUT_ABOVE_MAX_ANY = (TIMEOUT_VALID_RANGE_NVUE, TIMEOUT_ABOVE_MAX_OPENAPI)
    TIMEOUT_NOT_INTEGER_ANY = (TIMEOUT_NOT_INTEGER_NVUE, TIMEOUT_NOT_INTEGER_OPENAPI)

    BAD_MODE = "'bad-mode' is not one of"


class PhyRecoveryCounters:
    """
    Counter field names from ``nv show interface <port> link phy-detail``.

    These counters track PHY recovery events and are used to verify
    that recovery actions actually triggered firmware recovery.
    """
    TOTAL_SUCCESSFUL_RECOVERY_EVENTS = "total-successful-recovery-events"
    SUCCESSFUL_RECOVERY_EVENTS = "successful-recovery-events"


class GoOnceConsts:
    """
    Constants for the PHY recovery go-once action.

    Action command: nv action start fae interface <port> link phy-recovery
    """
    INVALID_PORT_TYPES = ["eth0", "lo"]

    SUCCESS_OUTPUT_NVUE = "Successfully triggered"
    SUCCESS_OUTPUT_OPENAPI = "phy recovery triggered"
    SUCCESS_OUTPUT = (SUCCESS_OUTPUT_NVUE, SUCCESS_OUTPUT_OPENAPI)

    LOG_MESSAGE = "Got phy recovery event for port"
