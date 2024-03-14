ENABLE = 'enable'
DISABLE = 'disable'

LOCAL = 'local'
LDAP = 'ldap'
DEFAULT = 'default'

IP = 'ip'
PORT = 'port'
BIND_DN = 'bind-dn'
BIND_PASSWORD = 'bind-password'
BASE_DN = 'base-dn'
BIND_TIMEOUT = 'bind-timeout'
TIMEOUT = 'timeout'
VERSION = 'version'

HOSTNAME = 'hostname'
PRIORITY = 'priority'

AUTH_LOGIN = 'aaa authentication login'
AUTH_FAILTHROUGH = 'aaa authentication failthrough'

USERS = 'users'
USERNAME = 'username'
PASSWORD = 'password'
ROLE = 'role'
ADMIN = 'admin'
MONITOR = 'monitor'

BIND_USERNAME = 'bind-username'
PLACEHOLDERS = {
    BASE_DN: '{BASE_DN}',
    USERNAME: '{USERNAME}',
    PASSWORD: '{PASSWORD}',
    BIND_USERNAME: '{BIND_USERNAME}',
    BIND_PASSWORD: '{BIND_PASSWORD}'
}

LDAP_SCRIPT_FILENAME = 'setup_ldap_server.sh'

SERVER_PORT = 389
SERVER_BASE_DN = 'dc=itzgeek,dc=local'

GLOBAL_FIELDS = [PORT, BIND_DN, BIND_PASSWORD, BASE_DN, BIND_TIMEOUT, TIMEOUT, VERSION]
