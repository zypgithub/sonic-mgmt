from enum import Enum

from ngts.nvos_constants.constants_nvos import ApiType


class CpoConsts:
    """Constants for ELS CPO / Fiber Tuning testing."""

    # ── Enums ──────────────────────────────────────────────────────────

    class State(Enum):
        ENABLED = 'enabled'
        DISABLED = 'disabled'

    class InitState(Enum):
        COMPLETED = 'completed'
        FAILED = 'failed'
        NOT_REACHED = 'not-reached'

    class ReadyState(Enum):
        READY = 'ready'
        NOT_READY = 'not-ready'
        INITIALIZING = 'initializing'

    class FineTuneStatus(Enum):
        SUCCESS = 'success'
        FAILED = 'failed'
        IN_PROGRESS = 'in-progress'

    ELS = 'els'

    # ── CPO Field Names ────────────────────────────────────────────────

    ELS_INITIALIZATION_STATE = 'els-initialization-state'
    FIBER_CHECK_STATE = 'fiber-check-state'
    LASER_TUNING_STATE = 'laser-tuning-state'
    LASER_UP_STATE = 'laser-up-state'

    # ── ELS Initialization Fields ──────────────────────────────────────

    FIBER_CHECK = 'fiber-check'
    LASER_TUNING = 'laser-tuning'
    LASER_UP = 'laser-up'
    ERROR = 'error'

    # ── Commands ───────────────────────────────────────────────────────

    ELS_INITIALIZATION = 'els-initialization'
    ELS_INITIALIZATION_PER_LASER = 'els-initialization-per-laser'

    # ── Default Values ─────────────────────────────────────────────────

    DEFAULT_STATE = State.ENABLED.value
    LASER_UP_DEFAULT_STATE = State.DISABLED.value
    TIMEOUT_AFTER_ELS_INITIALIZATION = 400  # [sec]

    # ── Valid States ───────────────────────────────────────────────────

    VALID_STATES = [State.ENABLED.value, State.DISABLED.value]
    VALID_INIT_STATES = [InitState.COMPLETED.value, InitState.FAILED.value, InitState.NOT_REACHED.value]
    VALID_READY_STATES = [ReadyState.READY.value, ReadyState.NOT_READY.value, ReadyState.INITIALIZING.value]

    # ── Field Mappings ─────────────────────────────────────────────────

    CPO_FIELDS = [
        ELS_INITIALIZATION_STATE,
        FIBER_CHECK_STATE,
        LASER_TUNING_STATE,
        LASER_UP_STATE,
    ]

    CPO_FIELD_DEFAULTS = {
        ELS_INITIALIZATION_STATE: DEFAULT_STATE,
        FIBER_CHECK_STATE: DEFAULT_STATE,
        LASER_TUNING_STATE: DEFAULT_STATE,
        LASER_UP_STATE: LASER_UP_DEFAULT_STATE,
    }

    ELS_INIT_DEFAULT_DICT = {
        FIBER_CHECK: InitState.COMPLETED.value,
        LASER_TUNING: InitState.COMPLETED.value,
        LASER_UP: 'N/A',
    }

    ELS_INIT_PER_LASER_DEFAULT_DICT = {
        ERROR: "",
        FIBER_CHECK: InitState.COMPLETED.value,
        LASER_TUNING: InitState.COMPLETED.value,
        LASER_UP: 'N/A',
    }

    # ── Laser / Module Constants ───────────────────────────────────────

    LASER_FIELDS = [FIBER_CHECK, LASER_TUNING, LASER_UP, ERROR]

    # ── Error Messages ─────────────────────────────────────────────────

    INVALID_ELS_INDEX_ERROR = "Invalid ELS index, expected range: 1-18"
    CANNOT_TUNE_NON_ELS_ERROR = "Can not tune non-ELS transceiver"

    # ── ELS Fine Tuning ────────────────────────────────────────────────

    ELS_FINE_TUNING = 'els-fine-tuning'
    FINE_TUNING_STATE = 'fine-tuning-state'
    FINE_TUNING_INTERVAL = 'fine-tuning-interval'
    LAST_FINE_TUNE_STATUS = 'last-fine-tune-status'
    LAST_FINE_TUNE_TS = 'last-fine-tune-ts'
    FINE_TUNE_TIMER_SERVICE = 'els-fiber-fine-tune.timer'
    FINE_TUNE_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'

    DEFAULT_FINE_TUNING_INTERVAL = 180
    MAX_FINE_TUNING_INTERVAL = 86400

    VALID_FINE_TUNE_STATUSES = [FineTuneStatus.SUCCESS.value, FineTuneStatus.FAILED.value,
                                FineTuneStatus.IN_PROGRESS.value, '']

    INVALID_FINE_TUNE_STATES = ['invalid_value', '123']

    _NVUE_RANGE_ERR = 'Valid range for fine-tuning-interval is 180 - 86400'
    INVALID_FINE_TUNE_INTERVAL_CASES = {
        ApiType.NVUE: [
            (-1, _NVUE_RANGE_ERR),
            (0, _NVUE_RANGE_ERR),
            (179, _NVUE_RANGE_ERR),
            (86401, _NVUE_RANGE_ERR),
            ('abc', 'is not an integer'),
            ('1.5', 'is not an integer'),
        ],
        ApiType.OPENAPI: [
            (-1, 'is less than the minimum of'),
            (0, 'is less than the minimum of'),
            (179, 'is less than the minimum of'),
            (86401, 'is greater than the maximum of'),
            ('abc', 'is not of type'),
            ('1.5', 'is not of type'),
        ],
    }

    # ── Timezone Constants (fine-tuning timezone test) ──────────────────

    TIMEZONE_CANDIDATES = [
        'US/Eastern', 'US/Pacific', 'Europe/London', 'Asia/Tokyo',
        'Australia/Sydney', 'Asia/Kolkata', 'America/Chicago',
    ]

    # ── Traffic Constants (fine-tuning traffic test) ───────────────────

    TRAFFIC_DURATION_10MIN_SECONDS = '600'
    TRAFFIC_TIMEOUT_10MIN_SECONDS = 610
    TRAFFIC_SERVER_OUTPUT_10MIN = 'els_fine_tuning_10min_server_output.txt'
    TRAFFIC_CLIENT_OUTPUT_10MIN = 'els_fine_tuning_10min_client_output.txt'
