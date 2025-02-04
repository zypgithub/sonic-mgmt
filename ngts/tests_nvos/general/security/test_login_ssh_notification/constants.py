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
