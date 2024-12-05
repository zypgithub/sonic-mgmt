
class LdapConsts:
    # keys
    HOSTNAME = 'hostname'
    PRIORITY = 'priority'
    SCOPE = 'scope'
    USERS = 'users'
    NESTED_USERS = "nested-users"
    USERNAME = 'username'
    PASSWORD = 'password'
    # show cmd fields
    PORT = 'port'
    BASE_DN = 'base-dn'
    BIND_DN = 'bind-dn'
    # LOGIN_ATTR = 'login-attribute'  not supported now
    # BIND_PASSWORD = 'password'
    SECRET = 'secret'
    TIMEOUT_BIND = 'timeout-bind'
    TIMEOUT = 'timeout-search'
    VERSION = 'version'
    # phase 2 show cmd fields
    SSL = 'ssl'
    SSL_CA_LIST = 'ca-list'
    SSL_CERT_VERIFY = 'cert-verify'
    SSL_MODE = 'mode'
    SSL_PORT = 'port'
    SSL_TLS_CIPHERS = 'tls-ciphers'
    SSL_CRL_LIST = 'crl-list'  # decided out of feature
    TLS_CRL_CHECK_FILE = 'tls-crl-check-file'  # decided out of feature
    TLS_CRL_CHECK_STATE = 'tls-crl-check-state'  # decided out of feature
    # phase 3 keys
    FILTER = 'filter'
    MAP = 'map'
    PASSWD = 'passwd'
    GROUP = 'group'
    SHADOW = 'shadow'
    UID = 'uid'
    UID_NUMBER = 'uidnumber'
    GID_NUMBER = 'gidnumber'
    USER_PASSWORD = 'userpassword'
    CN = 'cn'
    MEMBER_UID = 'memberuid'
    MEMBER = 'member'

    LDAP_FIELDS = [PORT, BASE_DN, BIND_DN, SECRET, TIMEOUT_BIND, TIMEOUT, VERSION]
    SSL_FIELDS = [SSL_CA_LIST, SSL_CERT_VERIFY, SSL_MODE, SSL_PORT, SSL_TLS_CIPHERS]

    # possible values
    NONE = 'none'
    DISABLED = 'disabled'
    ENABLED = 'enabled'
    DEFAULT = 'default'
    START_TLS = 'start-tls'
    DEFAULT_CA_LIST = 'default-ca-list'
    TLS_1_2 = 'TLS1.2'
    TLS_1_3 = 'TLS1.3'
    ALL = 'all'
    DEFAULT_CRL = 'default-crl'
    PORT_389 = '389'
    PORT_636 = '636'
    PORT_TLS = PORT_389
    PORTS_SSL = [PORT_389, PORT_636]

    POSSIBLE_PORTS = list(range(1, 65535 + 1))
    TEST_PORTS = list(range(1001, 65535 + 1))  # don't use system ports so the test won't be blocked

    VALID_VALUES = {
        PORT: TEST_PORTS,
        BASE_DN: str,
        BIND_DN: str,
        # LOGIN_ATTR: str,  not supported now
        SECRET: str,
        TIMEOUT_BIND: list(range(1, 60 + 1)),
        TIMEOUT: list(range(1, 60 + 1)),
        VERSION: [2, 3]
    }

    VALID_VALUES_SSL = {
        SSL_CA_LIST: [DEFAULT, NONE],
        SSL_CERT_VERIFY: [ENABLED, DISABLED],
        SSL_CRL_LIST: [DEFAULT, NONE],
        SSL_MODE: [NONE, START_TLS, SSL],
        SSL_PORT: TEST_PORTS,
        SSL_TLS_CIPHERS: [ALL, TLS_1_2, TLS_1_3]
    }

    ALL_VALID_VALUES = VALID_VALUES.copy()
    ALL_VALID_VALUES.update(VALID_VALUES_SSL)
    ALL_VALID_VALUES[PORT] = POSSIBLE_PORTS
    ALL_VALID_VALUES[SSL_PORT] = POSSIBLE_PORTS
    ALL_VALID_VALUES[PRIORITY] = [1, 2, 3, 4, 5, 6, 7, 8]

    # default values
    DEFAULTS = {
        PORT: 389,
        BASE_DN: 'ou=users,dc=example,dc=com',
        BIND_DN: '',
        # LOGIN_ATTR: 'cn',  not supported now
        SECRET: '*',
        TIMEOUT_BIND: 5,
        TIMEOUT: 5,
        VERSION: 3,
        # ssl defaults
        SSL_CA_LIST: DEFAULT,
        SSL_CERT_VERIFY: ENABLED,
        SSL_MODE: NONE,
        SSL_PORT: 636,
        SSL_TLS_CIPHERS: ALL
    }

    FIELD_IS_NUMERIC = {
        PORT: True,
        BASE_DN: False,
        BIND_DN: False,
        # LOGIN_ATTR: 'cn',  not supported now
        SECRET: False,
        TIMEOUT_BIND: True,
        TIMEOUT: True,
        VERSION: True,
        PRIORITY: True,
        # ssl defaults
        SSL_CA_LIST: False,
        SSL_CERT_VERIFY: False,
        SSL_CRL_LIST: False,
        SSL_MODE: False,
        SSL_PORT: True,
        SSL_TLS_CIPHERS: False
    }

    PHYSICAL_LDAP_SERVER = {
        "hostname": "10.7.34.20",
        "base-dn": "dc=itzgeek,dc=local",
        "bind-dn": "cn=ldapadm,dc=itzgeek,dc=local",
        "secret": "secret",
        # "login-attribute": "cn",  not supported now
        # "scope": "subtree", not supported now
        "port": "389",
        "timeout-bind": "1",
        "timeout-search": "1",
        "version": '3',
        "priority": '1',
        "users": [
            {
                'username': 'monitoruser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'monitor'
            },
            {
                'username': 'adminuser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'admin'
            }
        ],
        "nested-users": [
            {
                'username': 'nestedMonitorUser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'monitor'
            },
            {
                'username': 'nestedAdminUser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'monitor'
            }
        ]
    }

    DOCKER_LDAP_SERVER = {
        "hostname": "fdfd:fdfd:10:237:250:56ff:fe1b:56",
        "base-dn": "dc=itzgeek,dc=local",
        "bind-dn": "cn=ldapadm,dc=itzgeek,dc=local",
        "secret": "secret",
        # "login-attribute": "cn",  not supported now
        # "scope": "subtree", not supported now
        "port": "389",
        "timeout-bind": "1",
        "timeout-search": "1",
        "version": '3',
        "priority": '2',
        "users": [
            {
                'username': 'adminuser',  # TODO: change to volt once it is in
                'password': 'asdasd',  # TODO: change to volt once it is in
                'role': 'monitor'  # NOTE that adminuser in this server is with monitor permissions!
            },
            {
                'username': 'monitoruser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'monitor'
            },
            {
                'username': 'azmy',  # TODO: change to volt once it is in
                'password': 'azmy',  # TODO: change to volt once it is in
                'role': 'admin'
            },
            {
                'username': 'alon',  # TODO: change to volt once it is in
                'password': 'alon',  # TODO: change to volt once it is in
                'role': 'monitor'
            }
        ]
    }

    DOCKER_LDAP_SERVER_IPV4 = {
        "hostname": "10.237.0.86",
        "base-dn": "dc=itzgeek,dc=local",
        "bind-dn": "cn=ldapadm,dc=itzgeek,dc=local",
        "secret": "secret",
        # "login-attribute": "cn",  not supported now
        # "scope": "subtree", not supported now
        "port": "389",
        "timeout-bind": "1",
        "timeout-search": "1",
        "version": '3',
        "priority": '2',
        "users": [
            {
                'username': 'adminuser',  # TODO: change to volt once it is in
                'password': 'asdasd',  # TODO: change to volt once it is in
                'role': 'monitor'  # NOTE that adminuser in this server is with monitor permissions!
            },
            {
                'username': 'monitoruser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'monitor'
            },
            {
                'username': 'azmy',  # TODO: change to volt once it is in
                'password': 'azmy',  # TODO: change to volt once it is in
                'role': 'admin'
            },
            {
                'username': 'alon',  # TODO: change to volt once it is in
                'password': 'alon',  # TODO: change to volt once it is in
                'role': 'monitor'
            }
        ]
    }

    DOCKER_LDAP_SERVER_DNS = {
        "hostname": "fit-l-vrt-60-086",
        "base-dn": "dc=itzgeek,dc=local",
        "bind-dn": "cn=ldapadm,dc=itzgeek,dc=local",
        "secret": "secret",
        # "login-attribute": "cn",  not supported now
        # "scope": "subtree", not supported now
        "port": "389",
        "timeout-bind": "1",
        "timeout-search": "1",
        "version": '3',
        "priority": '3',
        "users": [
            {
                'username': 'adminuser',  # TODO: change to volt once it is in
                'password': 'asdasd',  # TODO: change to volt once it is in
                'role': 'monitor'  # NOTE that adminuser in this server is with monitor permissions!
            },
            {
                'username': 'monitoruser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'monitor'
            },
            {
                'username': 'azmy',  # TODO: change to volt once it is in
                'password': 'azmy',  # TODO: change to volt once it is in
                'role': 'admin'
            },
            {
                'username': 'alon',  # TODO: change to volt once it is in
                'password': 'alon',  # TODO: change to volt once it is in
                'role': 'monitor'
            }
        ]
    }

    DOCKER_LDAP_SERVER_DNS_WITH_CERT = {
        "hostname": "ldap.itzgeek.local",
        "base-dn": "dc=itzgeek,dc=local",
        "bind-dn": "cn=ldapadm,dc=itzgeek,dc=local",
        "secret": "secret",
        # "login-attribute": "cn", not supported now
        # "scope": "subtree", not supported now
        "port": "389",
        "timeout-bind": "1",
        "timeout-search": "1",
        "version": '3',
        "priority": '3',
        "users": [
            {
                'username': 'adminuser',  # TODO: change to volt once it is in
                'password': 'asdasd',  # TODO: change to volt once it is in
                'role': 'monitor'  # NOTE that adminuser in this server is with monitor permissions!
            },
            {
                'username': 'monitoruser',  # TODO: change to volt once it is in
                'password': 'asd',  # TODO: change to volt once it is in
                'role': 'monitor'
            },
            {
                'username': 'azmy',  # TODO: change to volt once it is in
                'password': 'azmy',  # TODO: change to volt once it is in
                'role': 'admin'
            },
            {
                'username': 'alon',  # TODO: change to volt once it is in
                'password': 'alon',  # TODO: change to volt once it is in
                'role': 'monitor'
            }
        ]
    }

    DOCKER_LDAP_SERVER_HOST_ALIAS_IPV4 = '10.237.0.86 ldap.itzgeek.local'
    DOCKER_LDAP_SERVER_HOST_ALIAS_IPV6 = 'fdfd:fdfd:10:237:250:56ff:fe1b:56 ldap.itzgeek.local'

    LDAP_SERVERS_LIST = [
        PHYSICAL_LDAP_SERVER,
        DOCKER_LDAP_SERVER
    ]

    DEFAULT_PRIORTIY = 1
    LDAP_LOW_TIMOEUT = '1'
    LDAP_HIGH_TIMEOUT = '60'
    MAX_PRIORITY = '8'
    LDAP_SLEEP_TO_APPLY_CONFIGURATIONS = 10

    # connection modes
    IPV4 = 'ipv4'
    IPV6 = 'ipv6'
    DNS = 'dns'

    SERVER_INFO = {
        IPV4: DOCKER_LDAP_SERVER_IPV4,
        IPV6: DOCKER_LDAP_SERVER,
        DNS: DOCKER_LDAP_SERVER_DNS
    }

    TLS = 'start-tls'
    CONNECTION_METHODS = [IPV4, IPV6, DNS]
    ENCRYPTION_MODES = [NONE, TLS, SSL]

    # DOCKER_LDAP_SERVER_CERT_PATH = \
    #     '/auto/sw_system_project/NVOS_INFRA/security/verification/ldap/custom_ldap_server_cert.pem'
    DOCKER_LDAP_SERVER_CERT_PATH = '/auto/sw_system_project/NVOS_INFRA/security/verification/ldap/LDAP_DOCKERS/ldap_final/ca/ca.pem'
    SWITCH_TMP_PATH = '/tmp'
    SERVER_CERT_FILE_IN_SWITCH = '/tmp/custom_ldap_server_cert.pem'
    SWITCH_CA_FILE = '/etc/ssl/certs/ca-certificates.crt'
    SWITCH_CA_BACKUP_FILE = '/tmp/backup_ca-certificates.crt'

    PERMISSION_DENIED = 'Permission denied'


class LdapEncryptionModes:
    NONE = 'none'
    START_TLS = 'start-tls'
    SSL = 'ssl'
    ALL_MODES = [NONE, START_TLS, SSL]


class LdapFilterFields:
    PASSWD = LdapConsts.PASSWD
    GROUP = LdapConsts.GROUP
    SHADOW = LdapConsts.SHADOW
    ALL_FIELDS = [PASSWD, GROUP, SHADOW]


class LdapPasswdAttributes:
    UID = LdapConsts.UID
    UID_NUMBER = LdapConsts.UID_NUMBER
    GID_MUMBER = LdapConsts.GID_NUMBER
    USER_PASSWORD = LdapConsts.USER_PASSWORD
    ALL_ATTRIBUTES = [UID, UID_NUMBER, GID_MUMBER, USER_PASSWORD]


class LdapGroupAttributes:
    CN = LdapConsts.CN
    GID_NUMBER = LdapConsts.GID_NUMBER
    MEMBER_UID = LdapConsts.MEMBER_UID
    ALL_ATTRIBUTES = [CN, GID_NUMBER, MEMBER_UID]


class LdapShadowAttributes:
    USER_PASSWORD = LdapConsts.USER_PASSWORD
    MEMBER = LdapConsts.MEMBER
    UID = LdapConsts.UID
    ALL_ATTRIBUTES = [USER_PASSWORD, MEMBER, UID]


class LdapDefaults:
    GLOBAL_DEFAULTS = {
        LdapConsts.PORT: 389,
        LdapConsts.BASE_DN: 'ou=users,dc=example,dc=com',
        LdapConsts.BIND_DN: '',
        # LOGIN_ATTR: 'cn',  not supported now
        LdapConsts.SECRET: '*',
        LdapConsts.TIMEOUT_BIND: 5,
        LdapConsts.TIMEOUT: 5,
        LdapConsts.VERSION: 3,
        LdapConsts.HOSTNAME: {}
    }

    SSL_DEFAULTS = {
        LdapConsts.SSL_CA_LIST: LdapConsts.DEFAULT,
        LdapConsts.SSL_CERT_VERIFY: LdapConsts.ENABLED,
        LdapConsts.SSL_MODE: LdapConsts.NONE,
        LdapConsts.SSL_PORT: 636,
        LdapConsts.SSL_TLS_CIPHERS: LdapConsts.ALL
    }

    FILTER_DEFAULTS = {
        LdapFilterFields.PASSWD: '(objectClass=posixAccount)',
        LdapFilterFields.GROUP: '(objectClass=posixGroup)',
        LdapFilterFields.SHADOW: '(objectClass=shadowAccount)'
    }

    MAP_PASSWD_DEFAULTS = {
        LdapPasswdAttributes.UID: '',
        LdapPasswdAttributes.UID_NUMBER: '',
        LdapPasswdAttributes.GID_MUMBER: '',
        LdapPasswdAttributes.USER_PASSWORD: ''
    }

    MAP_GROUP_DEFAULTS = {
        LdapGroupAttributes.CN: '',
        LdapGroupAttributes.GID_NUMBER: '',
        LdapGroupAttributes.MEMBER_UID: ''
    }

    MAP_SHADOW_DEFAULTS = {
        LdapShadowAttributes.USER_PASSWORD: '',
        LdapShadowAttributes.MEMBER: '',
        LdapShadowAttributes.UID: ''
    }
