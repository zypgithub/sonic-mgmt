import re


class LoginSSHNotificationConsts:
    '''
    contains all the constants used in
    the login ssh notification test file
    '''

    # dictionary keys
    LAST_SUCCESSFUL_LOGIN_DATE = 'last_successful_login_date'
    LAST_SUCCESSFUL_LOGIN_TIME = 'last_successful_login_time'
    LAST_SUCCESSFUL_LOGIN_IP = 'last_successful_login_ip'
    LAST_UNSUCCESSFUL_LOGIN_DATE = 'last_unsuccessful_login_date'
    LAST_UNSUCCESSFUL_LOGIN_TIME = 'last_unsuccessful_login_time'
    LAST_UNSUCCESSFUL_LOGIN_IP = 'last_unsuccessful_login_ip'
    NUMBER_OF_UNSUCCESSFUL_ATTEMPTS_SINCE_LAST_LOGIN = 'number_of_unsuccessful_attempts_since_last_login'
    RECORD_PERIOD = 'login-record-period'
    NUMBER_OF_SUCCESSFUL_CONNECTIONS_IN_THE_LAST_RECORD_PERIOD = 'number_of_successful_connections_in_the_last_record_period'
    PASSWORD_CHANGED_MESSAGE = 'password_changed_message'
    ROLE_CHANGED_MESSAGE = 'role_changed_message'

    # REGEX
    SRC_IP_ADDRESS_REGEX = 'src\\s+(\\d+\\.\\d+\\.\\d+\\.\\d+)'

    # REGEX
    LAST_SUCCESSFUL_LOGIN_DATE_REGEX = re.compile(r'Last login:\s+([a-zA-Z0-9]*\s+[a-zA-Z0-9]*\s+[a-zA-Z0-9]*\s+\d+:\d+:\d+\s+[a-zA-Z0-9]*\s+[a-zA-Z0-9]*)')
    LAST_UNSUCCESSFUL_LOGIN_DATE_REGEX = re.compile(r'Last failed login:\s+([a-zA-Z0-9]*\s+[a-zA-Z0-9]*\s+[a-zA-Z0-9]*\s+\d+:\d+:\d+\s+[a-zA-Z0-9]*\s+[a-zA-Z0-9]*)')
    LAST_SUCCESSFUL_LOGIN_IP_REGEX = re.compile(r'Last login:.*from\s+([0-9a-zA-Z:\.]*)')
    LAST_UNSUCCESSFUL_LOGIN_IP_REGEX = re.compile(r'Last failed login:.*from\s+([0-9a-zA-Z:\.]*)')
    NUMBER_OF_UNSUCCESSFUL_ATTEMPTS_SINCE_LAST_LOGIN_REGEX = re.compile(r'There were\s+(\d+).*failed login attempts since the last successful login')
    RECORD_PERIOD_REGEX = re.compile(r'Number of total successful connections since last (\d+)')
    NUMBER_OF_SUCCESSFUL_CONNECTIONS_IN_THE_LAST_RECORD_PERIOD_REGEX = re.compile(r'Number of total successful connections since last.*days:.*(\d+)')
    PASSWORD_CHANGED_MESSAGE_REGEX = re.compile(r'Your.*password.*been changed since.*last login')
    ROLE_CHANGED_MESSAGE_REGEX = re.compile(r'Your.*capability.*been changed since.*last login')
    LINUX_DATE_REGEX = re.compile(r'([a-zA-Z0-9]*\s+[a-zA-Z0-9]*\s+[a-zA-Z0-9]*\s+\d+:\d+:\d+\s+[a-zA-Z0-9]*\s+[a-zA-Z0-9]*)')

    # dict
    LOGIN_SSH_NOTIFICATION_REGEX_DICT = {
        LAST_SUCCESSFUL_LOGIN_DATE: LAST_SUCCESSFUL_LOGIN_DATE_REGEX,
        LAST_UNSUCCESSFUL_LOGIN_DATE: LAST_UNSUCCESSFUL_LOGIN_DATE_REGEX,
        LAST_SUCCESSFUL_LOGIN_IP: LAST_SUCCESSFUL_LOGIN_IP_REGEX,
        LAST_UNSUCCESSFUL_LOGIN_IP: LAST_UNSUCCESSFUL_LOGIN_IP_REGEX,
        NUMBER_OF_UNSUCCESSFUL_ATTEMPTS_SINCE_LAST_LOGIN: NUMBER_OF_UNSUCCESSFUL_ATTEMPTS_SINCE_LAST_LOGIN_REGEX,
        RECORD_PERIOD: RECORD_PERIOD_REGEX,
        NUMBER_OF_SUCCESSFUL_CONNECTIONS_IN_THE_LAST_RECORD_PERIOD: NUMBER_OF_SUCCESSFUL_CONNECTIONS_IN_THE_LAST_RECORD_PERIOD_REGEX,
        PASSWORD_CHANGED_MESSAGE: PASSWORD_CHANGED_MESSAGE_REGEX,
        ROLE_CHANGED_MESSAGE: ROLE_CHANGED_MESSAGE_REGEX
    }

    PASSWORD_MIN_LEN = 1
    PASSWORD_MAX_LEN = 10
    ADMIN_CAPABITILY = 'admin'
    MONITOR_CAPABITILY = 'monitor'

    MAX_TIME_DELTA_BETWEEEN_CONNECTIONS = 150
    MIN_RECORD_PERIOD_VAL = 1
    MAX_RECORD_PERIOD_VAL = 30
    AUTH_LOGS_SHARED_LOCATION = '/auto/sw_system_project/NVOS_INFRA/security/verification/login_ssh_notification/logs/*'
    AUTH_LOG_DIR_SWITCH_PATH = '/var/log'
    AUTH_LOG_FILE_SWITCH_PATH = f'{AUTH_LOG_DIR_SWITCH_PATH}/auth.log'
    TMP_TEST_DIR_SWITCH_PATH = '/tmp/test_dir'
    MAX_LOGIN_TIME = 10

    PASSWORD_UPDATE_WAIT_TIME = 3

    # Compiled regex pattern for SSH login notification error detection
    # Combines multiple error patterns for efficient single-pass matching
    SSH_LOGIN_ERROR_PATTERN = re.compile(
        r':\s*line\s+\d+:|syntax error|invalid date|Permission denied',
        re.IGNORECASE
    )
    ALLOW_USERS = 'allow-users'
    NVUE_MONITOR_ROLE = 'nvue-monitor'

    # SSH server config param names (for allow-user / switchd tests)
    # Top-level keys in system.ssh_server.show() output
    SSH_AUTHENTICATION_RETRIES = 'authentication-retries'
    SSH_LOGIN_TIMEOUT = 'login-timeout'
    SSH_MAX_SESSIONS_PER_CONNECTION = 'max-sessions-per-connection'
    SSH_MAX_UNAUTHENTICATED = 'max-unauthenticated'
    SSH_MAX_UNAUTHENTICATED_THROTTLE_START = 'throttle-start'  # nested key under max-unauthenticated in show output
    SSH_PERMIT_ROOT_LOGIN = 'permit-root-login'
    SSH_PORT = 'port'

    # SSH server config values (for set commands and show verification)
    SSH_AUTH_RETRIES_VAL = 6
    SSH_LOGIN_TIMEOUT_VAL = 120
    SSH_MAX_SESSIONS_PER_CONNECTION_VAL = 30
    SSH_MAX_SESSIONS_PER_CONNECTION_VAL_102 = 102
    # Limit used in test_verify_max_session_per_connection to enforce max (open 30, then 31st must fail)
    SSH_MAX_SESSIONS_PER_CONNECTION_LIMIT = 12
    SSH_MAX_UNAUTHENTICATED_THROTTLE_START_30 = 'throttle-start 30'  # value for set(max-unauthenticated, ...)
    SSH_MAX_UNAUTHENTICATED_THROTTLE_START_VAL = 30  # expected value in show output max-unauthenticated.throttle-start
    SSH_PERMIT_ROOT_LOGIN_ENABLED = 'enabled'
    SSH_PERMIT_ROOT_LOGIN_DISABLED = 'disabled'
    SSH_PERMIT_ROOT_LOGIN_PROHIBIT_PASSWORD = 'prohibit-password'
    SSH_PERMIT_ROOT_LOGIN_FORCED_COMMANDS_ONLY = 'forced-commands-only'
    SSH_PORT_VAL = 22

    # Expected value for max-unauthenticated in show() output; ValidationTool.verify_field_value_in_output
    # supports nested dict and will verify this sub-dict against output["max-unauthenticated"].
    SSH_MAX_UNAUTHENTICATED_EXPECTED_IN_SHOW = {
        SSH_MAX_UNAUTHENTICATED_THROTTLE_START: SSH_MAX_UNAUTHENTICATED_THROTTLE_START_VAL,
    }

    # Param -> value for system.ssh_server.set(param, value) (CLI format)
    SSH_SERVER_OPTIONS_FOR_SET = {
        SSH_AUTHENTICATION_RETRIES: SSH_AUTH_RETRIES_VAL,
        SSH_LOGIN_TIMEOUT: SSH_LOGIN_TIMEOUT_VAL,
        SSH_MAX_SESSIONS_PER_CONNECTION: SSH_MAX_SESSIONS_PER_CONNECTION_VAL,
        SSH_MAX_UNAUTHENTICATED: SSH_MAX_UNAUTHENTICATED_THROTTLE_START_30,
        SSH_PERMIT_ROOT_LOGIN: SSH_PERMIT_ROOT_LOGIN_ENABLED,
    }

    # (field, expected_value) for ValidationTool.validate_fields_values_in_output after show().
    # For nested keys (e.g. max-unauthenticated.throttle-start) expected_value is a dict; the tool recurses.
    SSH_SERVER_OPTIONS_FOR_SHOW_VERIFY = [
        (SSH_AUTHENTICATION_RETRIES, SSH_AUTH_RETRIES_VAL),
        (SSH_LOGIN_TIMEOUT, SSH_LOGIN_TIMEOUT_VAL),
        (SSH_MAX_SESSIONS_PER_CONNECTION, SSH_MAX_SESSIONS_PER_CONNECTION_VAL),
        (SSH_MAX_UNAUTHENTICATED, SSH_MAX_UNAUTHENTICATED_EXPECTED_IN_SHOW),
        (SSH_PERMIT_ROOT_LOGIN, SSH_PERMIT_ROOT_LOGIN_ENABLED),
    ]
    # Subset for tests that only set max-sessions, max-unauthenticated throttle-start, and permit-root-login
    SSH_SERVER_OPTIONS_FOR_SHOW_VERIFY_NV_SHOW = [
        (SSH_MAX_SESSIONS_PER_CONNECTION, SSH_MAX_SESSIONS_PER_CONNECTION_VAL),
        (SSH_MAX_UNAUTHENTICATED, SSH_MAX_UNAUTHENTICATED_EXPECTED_IN_SHOW),
        (SSH_PERMIT_ROOT_LOGIN, SSH_PERMIT_ROOT_LOGIN_ENABLED),
    ]
    # Subset for test_verify_reboot: only options set there (auth-retries, login-timeout, port). allow-users added in test.
    SSH_PORT_EXPECTED_IN_SHOW = {str(SSH_PORT_VAL): {}}
    SSH_SERVER_OPTIONS_FOR_SHOW_VERIFY_REBOOT = [
        (SSH_AUTHENTICATION_RETRIES, SSH_AUTH_RETRIES_VAL),
        (SSH_LOGIN_TIMEOUT, SSH_LOGIN_TIMEOUT_VAL),
        (SSH_PORT, SSH_PORT_EXPECTED_IN_SHOW),
    ]
