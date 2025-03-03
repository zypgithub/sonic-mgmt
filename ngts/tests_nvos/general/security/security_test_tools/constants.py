# aaa constants


class AaaConsts:
    USER = 'user'
    PASSWORD = 'password'
    ROLE = 'role'
    ADMIN = 'admin'
    MONITOR = 'monitor'
    USERNAME = 'username'

    LOCALADMIN = 'localadmin'
    LOCALMONITOR = 'localmonitor'
    STRONG_PASSWORD = 'Your_password1'

    SERVER = 'server'
    TIMEOUT = 'timeout'
    AUTH_TYPE = 'auth-type'
    AUTHENTICATION_MODE = 'mode'
    SERVER_AUTH_MODE = 'auth-mode'
    SECRET = 'secret'
    PORT = 'port'
    RETRANSMIT = 'retransmit'
    PRIORITY = 'priority'
    STATISTICS = 'statistics'

    IPV4 = 'ipv4'
    IPV6 = 'ipv6'
    DN = 'dn'

    MIN_PORT = 1
    MAX_PORT = 65535
    AAA_SERVER_BAD_PORT = 123

    PAP = 'pap'
    CHAP = 'chap'
    MSCHAPV2 = 'mschapv2'
    LOGIN = 'login'

    PHYSICAL_AAA_SERVER_IPV4_ADDR = '10.7.34.20'
    PHYSICAL_AAA_SERVER_IPV6_ADDR = 'fdfd:fdfd:7:34:46a8:42ff:fe27:8ab4'
    PHYSICAL_AAA_SERVER_DN = 'fit-def-20'
    VM_AAA_SERVER_IPV4_ADDR = '10.237.0.86'
    VM_AAA_SERVER_IPV6_ADDR = 'fdfd:fdfd:10:237:250:56ff:fe1b:56'
    VM_AAA_SERVER_DN = 'fit-l-vrt-60-086.mtl.labs.mlnx'

    ENABLED = 'enabled'
    DISABLED = 'disabled'


class UserRole:
    ADMIN = 'admin'
    MONITOR = 'monitor'
    ALL_ROLES = [ADMIN, MONITOR]


# aaa authentication constants
class AuthConsts:
    AUTHENTICATION = 'authentication'
    ORDER = 'order'
    LOCAL = 'local'
    LDAP = 'ldap'
    RADIUS = 'radius'
    TACACS = 'tacacs'
    FALLBACK = 'fallback'
    FAILTHROUGH = 'failthrough'

    SHOW_COMMAND = 'nv show system'
    SET_COMMAND = 'nv set system security password-hardening len-min 6'
    SWITCH_PROMPT_PATTERN = '.+@.+:.+\\$'
    PERMISSION_ERROR = 'Error: You do not have permission to execute that command.'

    LOGIN_FAIL_ERR = 'login fail'
    SHOW_FAIL_ERR = 'show fail'
    SET_FAIL_ERR = 'set fail'
    UNSET_FAIL_ERR = 'unset fail'

    USERS = 'users'

    # path consts
    SHARED_VERIFICATION_SECURITY_DIR = '/auto/sw_system_project/NVOS_INFRA/security/verification'
    SHARED_VERIFICATION_SCP_DIR = f'{SHARED_VERIFICATION_SECURITY_DIR}/scp/scp_test_files'
    SHARED_VERIFICATION_SCP_UPLOAD_TEST_FILE_NAME = 'shared_scp_upload_test_file.txt'

    SWITCH_SCP_TEST_DIR = '/tmp/scp_test_dir'
    SWITCH_ADMINS_DIR = f'{SWITCH_SCP_TEST_DIR}/admin_users_dir'
    SWITCH_MONITORS_DIR = f'{SWITCH_SCP_TEST_DIR}/non_privileged_dir'
    SWITCH_SCP_DOWNLOAD_TEST_FILE_NAME = 'switch_scp_download_test_file.txt'
    SWITCH_ADMIN_SCP_DOWNLOAD_TEST_FILE = f'{SWITCH_ADMINS_DIR}/{SWITCH_SCP_DOWNLOAD_TEST_FILE_NAME}'
    SWITCH_MONITOR_SCP_DOWNLOAD_TEST_FILE = f'{SWITCH_MONITORS_DIR}/{SWITCH_SCP_DOWNLOAD_TEST_FILE_NAME}'

    SWITCH_ROOT_DIR = '/etc'
    SWITCH_ROOT_FILE_NAME = 'shadow'


class AddressingType:
    IPV4 = 'ipv4'
    IPV6 = 'ipv6'
    DN = 'dn'
    ALL_TYPES = [IPV4, IPV6, DN]


class AuthType:
    PAP = 'pap'
    CHAP = 'chap'
    # MSCHAPV2 = 'mschapv2'
    LOGIN = 'login'
    ALL_TYPES = [PAP, CHAP, LOGIN]


class AuthMode:
    PAP = 'pap'
    CHAP = 'chap'
    LOGIN = 'login'
    ALL_TYPES = [PAP, CHAP, LOGIN]


class AuthMedium:
    # possible authentication mediums
    SSH = 'SSH'
    OPENAPI = 'OpenApi'
    RCON = 'RCON'
    SCP = 'SCP'
    ALL_MEDIUMS = [SSH, OPENAPI, RCON, SCP]


class AccountingConsts:
    ACCOUNTING = 'accounting'
    STATE = 'state'
    DISABLED = 'disabled'
    ENABLED = 'enabled'

    VALUES = {
        STATE: [DISABLED, ENABLED]
    }

    DEFAULT = {
        STATE: DISABLED
    }


class AccountingFields:
    STATE = AccountingConsts.STATE
    ALL_FIELDS = [STATE]
