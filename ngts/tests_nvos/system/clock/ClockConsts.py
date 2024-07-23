from ngts.nvos_constants.constants_nvos import SystemConsts
import os


class ClockConsts:
    TIMEZONE = SystemConsts.TIMEZONE    # 'timezone'
    DATETIME = SystemConsts.DATE_TIME   # 'date-time'

    DATETIME_MARGIN = 10  # tune this to decide what diff (in seconds) is ok between timedatectl and nv show system
    DEFAULT_TIMEZONE = "Etc/UTC"
    DST_TIMEZONE = "Etc/GMT+1"
    PATH_TIMEZONE_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'timezone.yaml')

    TIMEDATECTL_CMD = "timedatectl"
    TIMEDATECTL_TIMEZONE_FIELD_NAME = "Time zone"
    TIMEDATECTL_DATETIME_FIELD_NAME = "Local time"

    ERR_EMPTY_PARAM = ["Incomplete Command"]
    ERR_INVALID_TIMEZONE = ["is not one of"]
    ERR_INVALID_DATETIME = ["Invalid Command: action change system date-time"]
    ERR_INVALID_DATE = "'{}' is not a 'clock-date'."
    ERR_INVALID_TIME = "'{}' is not a 'clock-time'."
    ERR_DATETIME_NTP = ["Unable to change date and time in case NTP is enabled"]
    ERR_OPENAPI_DATETIME = ["Date-time internal error occurred"]

    NTP = 'ntp'
    STATE = 'state'
    ENABLED = 'enabled'
    DISABLED = 'disabled'

    WAIT_TIME = 6
    NUM_SAMPLES = 3  # configure how many samples in several tests

    MIN_SYSTEM_DATE = SystemConsts.MIN_SYSTEM_DATE
    MAX_SYSTEM_DATE = SystemConsts.MAX_SYSTEM_DATE
    MIN_SYSTEM_DATETIME = SystemConsts.MIN_SYSTEM_DATETIME
    MAX_SYSTEM_DATETIME = SystemConsts.MAX_SYSTEM_DATETIME
