from typing import Dict

from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AddressingType, AccountingConsts, \
    AuthConsts, AuthMedium, UserRole
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import TacacsServerInfo, \
    UsersPerAuthMedium
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo


class TacacsConsts:
    TIME_TILL_TACACS_CONF_TAKES_PLACE = 3

    TACACS_FIELDS = [AaaConsts.PORT, AaaConsts.TIMEOUT, AccountingConsts.ACCOUNTING, AuthConsts.AUTHENTICATION]
    AUTH_MODES = [AaaConsts.PAP, AaaConsts.CHAP, AaaConsts.LOGIN]  # AaaConsts.MSCHAPV2

    VALID_VALUES = {
        AaaConsts.SERVER: str,
        AaaConsts.TIMEOUT: list(range(1, 61)),
        AaaConsts.AUTHENTICATION_MODE: AUTH_MODES,
        AaaConsts.SERVER_AUTH_MODE: AUTH_MODES,
        AaaConsts.SECRET: str,
        AaaConsts.PORT: list(range(AaaConsts.MIN_PORT, AaaConsts.MAX_PORT + 1)),
        # AaaConsts.RETRANSMIT: list(range(6)),
        AaaConsts.PRIORITY: list(range(1, 9))

    }

    DEFAULT_TACACS_CONF = {
        AaaConsts.SERVER: {},
        AaaConsts.PORT: 49,
        AaaConsts.SECRET: '*',
        # AaaConsts.RETRANSMIT: 0,
        AaaConsts.TIMEOUT: 5,
    }

    DEFAULT_TACACS_AUTHENTICATION_CONF = {
        AaaConsts.AUTHENTICATION_MODE: AaaConsts.PAP,
    }

    DEFAULTS = {
        AaaConsts.TIMEOUT: 5,
        AaaConsts.AUTHENTICATION_MODE: AaaConsts.PAP,
        AaaConsts.SERVER_AUTH_MODE: AaaConsts.PAP,
        AaaConsts.PORT: 49,
        # AaaConsts.RETRANSMIT: 0,
        AaaConsts.PRIORITY: 1
    }

    FIELD_IS_NUMERIC = {
        AaaConsts.SERVER: False,
        AaaConsts.TIMEOUT: True,
        AaaConsts.AUTHENTICATION_MODE: False,
        AaaConsts.SERVER_AUTH_MODE: False,
        AaaConsts.SECRET: False,
        AaaConsts.PORT: True,
        # AaaConsts.RETRANSMIT: True,
        AaaConsts.PRIORITY: True
    }


class TacacsPhysicalServer:
    USERS = [
        UserInfo(
            username='adminuser',
            password='adminadmin',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='monitoruser',
            password='testing',
            role=AaaConsts.MONITOR
        )
    ]

    USERS_BY_AUTH_MODE = {
        AaaConsts.PAP: USERS,
        AaaConsts.CHAP: USERS,
        AaaConsts.LOGIN: USERS
    }

    SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.PHYSICAL_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='testing-tacacs',
        port=49,
        timeout=5,
        # retransmit=0,
        auth_mode=AaaConsts.PAP,
        users=USERS,
        ipv4_addr=AaaConsts.PHYSICAL_AAA_SERVER_IPV4_ADDR,
        users_per_auth_mode=USERS_BY_AUTH_MODE,
    )
    SERVER_IPV6 = SERVER_IPV4.copy()
    SERVER_IPV6.hostname = AaaConsts.PHYSICAL_AAA_SERVER_IPV6_ADDR
    SERVER_DN = SERVER_IPV4.copy()
    SERVER_DN.hostname = AaaConsts.PHYSICAL_AAA_SERVER_DN

    SERVER_BY_ADDRESSING_TYPE = {
        AddressingType.IPV4: SERVER_IPV4,
        AddressingType.IPV6: SERVER_IPV6,
        AddressingType.DN: SERVER_DN
    }


class TacacsVmServer:
    VM_SERVER_USERS = [
        UserInfo(
            username='adminuser',
            password='adminuser',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='monitoruser',
            password='monitoruser',
            role=AaaConsts.MONITOR
        )
    ]
    VM_SERVER_USERS_PAP = [UserInfo(user.username, user.password + '_pap', user.role) for user in VM_SERVER_USERS]
    VM_SERVER_USERS_CHAP = [UserInfo(user.username, user.password + '_chap', user.role) for user in VM_SERVER_USERS]
    VM_SERVER_USERS_LOGIN = [UserInfo(user.username, user.password + '_login', user.role) for user in VM_SERVER_USERS]
    VM_SERVER_USERS_BY_AUTH_MODE = {
        AaaConsts.PAP: VM_SERVER_USERS_PAP,
        AaaConsts.CHAP: VM_SERVER_USERS_CHAP,
        AaaConsts.LOGIN: VM_SERVER_USERS_LOGIN
    }

    VM_SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=49,
        timeout=5,
        # retransmit=0,
        auth_mode=AaaConsts.PAP,
        users=VM_SERVER_USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        users_per_auth_mode=VM_SERVER_USERS_BY_AUTH_MODE
    )

    VM_SERVER_DN = VM_SERVER_IPV4.copy()
    VM_SERVER_DN.hostname = AaaConsts.VM_AAA_SERVER_DN

    VM_SERVERS: Dict[str, TacacsServerInfo] = {
        AaaConsts.IPV4: VM_SERVER_IPV4,
        AaaConsts.DN: VM_SERVER_DN
    }


class TacacsDockerServer0:
    USERS = [
        UserInfo(
            username='tac0adm',
            password='tac0adm',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='tac0mon',
            password='tac0mon',
            role=AaaConsts.MONITOR
        ),
    ]
    USERS_PAP = [UserInfo(user.username, user.password + '_pap', user.role) for user in USERS]
    USERS_CHAP = [UserInfo(user.username, user.password + '_chap', user.role) for user in USERS]
    USERS_LOGIN = [UserInfo(user.username, user.password + '_login', user.role) for user in USERS]

    USERS_BY_AUTH_MODE = {
        AaaConsts.PAP: USERS_PAP,
        AaaConsts.CHAP: USERS_CHAP,
        AaaConsts.LOGIN: USERS_LOGIN
    }

    users_per_medium: UsersPerAuthMedium = {
        AuthMedium.SSH: {
            UserRole.ADMIN: [UserInfo('tac0adm-ssh', 'tac0adm-ssh_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac0mon-ssh', 'tac0mon-ssh_pap', UserRole.MONITOR)],
        },
        AuthMedium.OPENAPI: {
            UserRole.ADMIN: [UserInfo('tac0adm-rest', 'tac0adm-rest_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac0mon-rest', 'tac0mon-rest_pap', UserRole.MONITOR)],
        },
        AuthMedium.RCON: {
            UserRole.ADMIN: [UserInfo('tac0adm-rcon', 'tac0adm-rcon_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac0mon-rcon', 'tac0mon-rcon_pap', UserRole.MONITOR)],
        },
        AuthMedium.SCP: {
            UserRole.ADMIN: [UserInfo('tac0adm-scp', 'tac0adm-scp_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac0mon-scp', 'tac0mon-scp_pap', UserRole.MONITOR)],
        }
    }

    SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=50,
        timeout=5,
        # retransmit=0,
        auth_mode=AaaConsts.PAP,
        users=USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        docker_name='tacacs_container',
        users_per_auth_mode=USERS_BY_AUTH_MODE,
        users_per_auth_medium=users_per_medium
    )
    SERVER_IPV6 = SERVER_IPV4.copy()
    SERVER_IPV6.hostname = AaaConsts.VM_AAA_SERVER_IPV6_ADDR
    SERVER_DN = SERVER_IPV4.copy()
    SERVER_DN.hostname = AaaConsts.VM_AAA_SERVER_DN

    SERVER_BY_ADDRESSING_TYPE = {
        AddressingType.IPV4: SERVER_IPV4,
        AddressingType.IPV6: SERVER_IPV6,
        AddressingType.DN: SERVER_DN
    }


class TacacsDockerServer1:
    USERS = [
        UserInfo(
            username='tac1adm1',
            password='tac1adm1',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='tac1adm2',
            password='tac1adm2',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='tac1mon1',
            password='tac1mon1',
            role=AaaConsts.MONITOR
        ),
        UserInfo(
            username='tac1mon2',
            password='tac1mon2',
            role=AaaConsts.MONITOR
        )
    ]
    USERS_PAP = [UserInfo(user.username, user.password + '_pap', user.role) for user in USERS]
    USERS_CHAP = [UserInfo(user.username, user.password + '_chap', user.role) for user in USERS]
    USERS_LOGIN = [UserInfo(user.username, user.password + '_login', user.role) for user in USERS]

    USERS_BY_AUTH_MODE = {
        AaaConsts.PAP: USERS_PAP,
        AaaConsts.CHAP: USERS_CHAP,
        AaaConsts.LOGIN: USERS_LOGIN
    }

    users_per_medium: UsersPerAuthMedium = {
        AuthMedium.SSH: {
            UserRole.ADMIN: [UserInfo('tac1adm-ssh', 'tac1adm-ssh_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac1mon-ssh', 'tac1mon-ssh_pap', UserRole.MONITOR)],
        },
        AuthMedium.OPENAPI: {
            UserRole.ADMIN: [UserInfo('tac1adm-rest', 'tac1adm-rest_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac1mon-rest', 'tac1mon-rest_pap', UserRole.MONITOR)],
        },
        AuthMedium.RCON: {
            UserRole.ADMIN: [UserInfo('tac1adm-rcon', 'tac1adm-rcon_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac1mon-rcon', 'tac1mon-rcon_pap', UserRole.MONITOR)],
        },
        AuthMedium.SCP: {
            UserRole.ADMIN: [UserInfo('tac1adm-scp', 'tac1adm-scp_pap', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('tac1mon-scp', 'tac1mon-scp_pap', UserRole.MONITOR)],
        }
    }

    SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=52,
        timeout=5,
        # retransmit=0,
        auth_mode=AaaConsts.PAP,
        users=USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        docker_name='nvos_tacacs',
        users_per_auth_mode=USERS_BY_AUTH_MODE,
        users_per_auth_medium=users_per_medium
    )
    SERVER_IPV6 = SERVER_IPV4.copy()
    SERVER_IPV6.hostname = AaaConsts.VM_AAA_SERVER_IPV6_ADDR
    SERVER_DN = SERVER_IPV4.copy()
    SERVER_DN.hostname = AaaConsts.VM_AAA_SERVER_DN

    SERVER_BY_ADDRESSING_TYPE = {
        AddressingType.IPV4: SERVER_IPV4,
        AddressingType.IPV6: SERVER_IPV6,
        AddressingType.DN: SERVER_DN
    }


class TacacsDockerServer2:
    USERS = [
        UserInfo(
            username='tac2adm1',
            password='tac2adm1',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='tac2adm2',
            password='tac2adm2',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='tac2mon',
            password='tac2mon',
            role=AaaConsts.MONITOR
        ),
        UserInfo(
            username='tac2mon2',
            password='tac2mon2',
            role=AaaConsts.MONITOR
        )
    ]
    USERS_PAP = [UserInfo(user.username, user.password + '_pap', user.role) for user in USERS]
    USERS_CHAP = [UserInfo(user.username, user.password + '_chap', user.role) for user in USERS]
    USERS_LOGIN = [UserInfo(user.username, user.password + '_login', user.role) for user in USERS]

    USERS_BY_AUTH_MODE = {
        AaaConsts.PAP: USERS_PAP,
        AaaConsts.CHAP: USERS_CHAP,
        AaaConsts.LOGIN: USERS_LOGIN
    }

    SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=53,
        timeout=5,
        # retransmit=0,
        auth_mode=AaaConsts.PAP,
        users=USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        docker_name='nvos_tacacs2',
        users_per_auth_mode=USERS_BY_AUTH_MODE
    )
    SERVER_IPV6 = SERVER_IPV4.copy()
    SERVER_IPV6.hostname = AaaConsts.VM_AAA_SERVER_IPV6_ADDR
    SERVER_DN = SERVER_IPV4.copy()
    SERVER_DN.hostname = AaaConsts.VM_AAA_SERVER_DN

    SERVER_BY_ADDRESSING_TYPE = {
        AddressingType.IPV4: SERVER_IPV4,
        AddressingType.IPV6: SERVER_IPV6,
        AddressingType.DN: SERVER_DN
    }
