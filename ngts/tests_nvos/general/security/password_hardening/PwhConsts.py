class PwhConsts:
    MAX_VALID_PASSWORD_LEN = 511
    ERR_MAX_PASSWORD_LEN = 'Password should contain at most 511 characters'

    # pwh field names
    STATE = 'state'
    EXPIRATION = 'expiration'
    EXPIRATION_WARNING = 'expiration-warning'
    HISTORY_CNT = 'history-cnt'
    REJECT_USER_PASSW_MATCH = 'reject-user-passw-match'
    LEN_MIN = 'len-min'
    LOWER_CLASS = 'lower-class'
    UPPER_CLASS = 'upper-class'
    DIGITS_CLASS = 'digits-class'
    SPECIAL_CLASS = 'special-class'

    FIELDS = [STATE, EXPIRATION, EXPIRATION_WARNING, HISTORY_CNT, REJECT_USER_PASSW_MATCH, LEN_MIN, LOWER_CLASS,
              UPPER_CLASS, DIGITS_CLASS, SPECIAL_CLASS]

    # possible pwh field values
    ENABLED = 'enabled'
    DISABLED = 'disabled'

    # pwh field minimal values
    MIN = {
        EXPIRATION: -1,
        EXPIRATION_WARNING: -1,
        HISTORY_CNT: 1,
        LEN_MIN: 6
    }

    # pwh field minimal values
    MAX = {
        EXPIRATION: 365,
        EXPIRATION_WARNING: 30,
        HISTORY_CNT: 100,
        LEN_MIN: 32
    }

    # pwh valid field values
    VALID_VALUES = {
        STATE: [ENABLED, DISABLED],
        EXPIRATION: list(map(str, list(range(MIN[EXPIRATION], MAX[EXPIRATION] + 1)) + [-1, 0])),
        EXPIRATION_WARNING: list(map(str, list(range(MIN[EXPIRATION_WARNING], MAX[EXPIRATION_WARNING] + 1)) + [-1, 0])),
        HISTORY_CNT: list(map(str, list(range(MIN[HISTORY_CNT], MAX[HISTORY_CNT] + 1)))),
        REJECT_USER_PASSW_MATCH: [ENABLED, DISABLED],
        LEN_MIN: list(map(str, list(range(MIN[LEN_MIN], MAX[LEN_MIN] + 1)))),
        LOWER_CLASS: [ENABLED, DISABLED],
        UPPER_CLASS: [ENABLED, DISABLED],
        DIGITS_CLASS: [ENABLED, DISABLED],
        SPECIAL_CLASS: [ENABLED, DISABLED]
    }

    # pwh default configuration
    DEFAULTS = {
        STATE: ENABLED,
        EXPIRATION: '180',
        EXPIRATION_WARNING: '15',
        HISTORY_CNT: '10',
        REJECT_USER_PASSW_MATCH: ENABLED,
        LEN_MIN: '8',
        LOWER_CLASS: ENABLED,
        UPPER_CLASS: ENABLED,
        DIGITS_CLASS: ENABLED,
        SPECIAL_CLASS: ENABLED
    }

    # pwh configuration when feature (state) is disabled
    DISABLED_CONF = {
        STATE: DISABLED,
        EXPIRATION: '99999',
        EXPIRATION_WARNING: '7',
        HISTORY_CNT: '0',
        REJECT_USER_PASSW_MATCH: DISABLED,
        LEN_MIN: '1',
        LOWER_CLASS: DISABLED,
        UPPER_CLASS: DISABLED,
        DIGITS_CLASS: DISABLED,
        SPECIAL_CLASS: DISABLED
    }

    # consts for tests
    ADMIN_TEST_USR = "test_admin"
    MONITOR_TEST_USR = "test_monitor"
    USER_OBJ = 'user_object'
    USER = 'user'
    PW = 'password'
    ROLE = 'role'
    MONITOR = 'monitor'
    ADMIN = 'admin'

    # expected error messages
    ERR_ITEM_NOT_EXIST = 'The requested item does not exist.'
    ERR_INVALID_SET_CMD = 'Invalid Command: set system security password-hardening'
    ERR_INCOMPLETE_SET_CMD = 'Error: Incomplete Command'
    ERR_INVALID_SET_ENABLE_DISABLED = """is not one of ["enabled", "disabled"]"""
    ERR_PW_SHOULD_CONTAIN = 'Password should contain at least '
    ERR_MAX_RANGE = 'Error: At {}: {} is greater than the maximum of {}'
    ERR_MIN_RANGE = 'Error: At {}: {} is less than the minimum of {}'
    ERR_RANGE = 'Error: Valid range for {} is {} - {}'
    ERR_VALUE_LESS_THAN_MIN = "Error: At {}: {} is less than the minimum of {}"
    ERR_VALUE_GREATER_THAN_MAX = "Error: At {}: {} is greater than the maximum of {}"
    ERR_EXP_WARN_LEQ_EXP = 'expiration-warning should be equal or smaller than expiration'
    ERR_INTEGER_EXPECTED = "Error: '{}' is not an integer"

    WEAK_PW_ERRORS = {
        HISTORY_CNT: 'Password should be different than',
        REJECT_USER_PASSW_MATCH: 'Password should be different than username',
        LEN_MIN: ERR_PW_SHOULD_CONTAIN,
        LOWER_CLASS: ERR_PW_SHOULD_CONTAIN + 'one lowercase character',
        UPPER_CLASS: ERR_PW_SHOULD_CONTAIN + 'one uppercase character',
        DIGITS_CLASS: ERR_PW_SHOULD_CONTAIN + 'one digit',
        SPECIAL_CLASS: ERR_PW_SHOULD_CONTAIN + 'one special character'
    }

    # chars of each class
    LOWER_CHARS = 'abcdefghijklmnopqrstuvwxyz'
    UPPER_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    DIGITS_CHARS = '1234567890'
    SPECIAL_CHARS = "~@%^*_=+[{}]:',/"

    # configurable parameter to the test
    NUM_SAMPLES = 6
    EXPECT_TIMEOUT = 3
    SSH_PORT = 22

    # regex
    REGEX_TIME = r"\d{2}:\d{2}:\d{2}"
    REGEX_NUMERIC = r"^-?\d+$"

    # expiration prompted warnings
    PROMPT_PW_EXPIRED = ['New password', 'You must change your password now!']
    PROMPT_EXPIRATION_WARNING = ['Warning: your password will expire in']  # ['$']
    MSG_PW_EXPIRED = 'You must change your password now and login again'
    MSG_EXPIRATION_WARNING = 'Warning: your password will expire in'

    # 'chage' keys
    CHAGE_EXPIRATION = 'Maximum number of days between password change'
    CHAGE_EXPIRATION_WARNING = 'Number of days of warning before password expires'
