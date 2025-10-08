"""
Constants for Stress Mode Testing

This module contains all constants used for testing the stress mode feature.

Stress mode is a special operational mode designed for traffic stress testing.
When enabled, it disables certain system features to optimize performance and
prevent interruptions during stress scenarios:
  - Flex counters are disabled to reduce system overhead
  - Fatal mode automatic recovery actions are suppressed
  - L1 power saving is disabled to ensure stable links
"""


class StressModeConsts:
    """Constants related to stress mode configuration and validation"""

    # Stress Mode State DB Configuration
    STATE_DB_TABLE = "STRESS_MODE|GLOBAL"
    STATE_FIELD = "state"
    STATE_ENABLED = "enabled"
    STATE_DISABLED = "disabled"

    # Syslog Messages
    SYSLOG_STRESS_MODE_STARTED = "Stress Mode successfully enabled"
    SYSLOG_STRESS_MODE_STOPPED = "Stress Mode successfully disabled"


class FlexCounterConsts:
    """Constants for Flex Counter DB validation"""

    # Flex Counter Database
    DB_NAME = "FLEX_COUNTER_DB"
    GROUP_TABLE_PREFIX = "FLEX_COUNTER_GROUP_TABLE:"

    # Flex Counter Fields
    FLEX_COUNTER_STATUS = "FLEX_COUNTER_STATUS"

    # Expected Values
    STATUS_DISABLED = "disable"


class FatalModeConsts:
    """Constants for Fatal Mode configuration"""

    # Syslog Messages
    FATAL_RECOVERY_ACTIONS_SUPPRESSED_MSG = "suppressing fatal recovery actions"


class PowerSavingConsts:
    """Constants for L1 power saving configuration"""

    # PPSLC Register (Port Power Saving Link Configuration)
    PPSLC_REGISTER = "PPSLC"
    L1_REQ_EN_DISABLED = "0"
    L1_REQ_EN_ENABLED = "1"

    # PPSLS Register (Port Power Saving Link State)
    PPSLS_REGISTER = "PPSLS"
    L1_CAP_FIELD = "l1_cap"
    L1_CAP_DISABLED = "0"  # L1 power saving disabled (expected in stress mode)
    L1_CAP_ENABLED = "1"   # L1 power saving enabled (normal mode)


class DatabaseConsts:
    """Database names used for stress mode configuration"""

    STATE_DB = "STATE_DB"
    FLEX_COUNTER_DB = "FLEX_COUNTER_DB"
