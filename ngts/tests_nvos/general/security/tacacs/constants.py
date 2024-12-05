from typing import Dict

from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AddressingType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import TacacsServerInfo
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo


class TacacsConsts:
    TIME_TILL_TACACS_CONF_TAKES_PLACE = 3

    AUTH_TYPES = [AaaConsts.PAP, AaaConsts.CHAP, AaaConsts.LOGIN]  # AaaConsts.MSCHAPV2

    VALID_VALUES = {
        AaaConsts.HOSTNAME: str,
        AaaConsts.TIMEOUT: list(range(1, 61)),
        AaaConsts.AUTH_TYPE: AUTH_TYPES,
        AaaConsts.SECRET: str,
        AaaConsts.PORT: list(range(AaaConsts.MIN_PORT, AaaConsts.MAX_PORT + 1)),
        # AaaConsts.RETRANSMIT: list(range(6)),
        AaaConsts.PRIORITY: list(range(1, 9))
    }

    DEFAULT_TACACS_CONF = {
        AaaConsts.AUTH_TYPE: AaaConsts.PAP,
        AaaConsts.HOSTNAME: {},
        AaaConsts.PORT: 49,
        AaaConsts.SECRET: '*',
        # AaaConsts.RETRANSMIT: 0,
        AaaConsts.TIMEOUT: 5,
    }

    DEFAULTS = {
        AaaConsts.TIMEOUT: 5,
        AaaConsts.AUTH_TYPE: AaaConsts.PAP,
        AaaConsts.PORT: 49,
        # AaaConsts.RETRANSMIT: 0,
        AaaConsts.PRIORITY: 1
    }

    FIELD_IS_NUMERIC = {
        AaaConsts.HOSTNAME: False,
        AaaConsts.TIMEOUT: True,
        AaaConsts.AUTH_TYPE: False,
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

    USERS_BY_AUTH_TYPE = {
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
        auth_type=AaaConsts.PAP,
        users=USERS,
        ipv4_addr=AaaConsts.PHYSICAL_AAA_SERVER_IPV4_ADDR,
        users_per_auth_type=USERS_BY_AUTH_TYPE,
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
    VM_SERVER_USERS_BY_AUTH_TYPE = {
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
        auth_type=AaaConsts.PAP,
        users=VM_SERVER_USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        users_per_auth_type=VM_SERVER_USERS_BY_AUTH_TYPE
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

    USERS_BY_AUTH_TYPE = {
        AaaConsts.PAP: USERS_PAP,
        AaaConsts.CHAP: USERS_CHAP,
        AaaConsts.LOGIN: USERS_LOGIN
    }

    SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=50,
        timeout=5,
        # retransmit=0,
        auth_type=AaaConsts.PAP,
        users=USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        docker_name='tacacs_container',
        users_per_auth_type=USERS_BY_AUTH_TYPE,
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

    USERS_BY_AUTH_TYPE = {
        AaaConsts.PAP: USERS_PAP,
        AaaConsts.CHAP: USERS_CHAP,
        AaaConsts.LOGIN: USERS_LOGIN
    }

    SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=52,
        timeout=5,
        # retransmit=0,
        auth_type=AaaConsts.PAP,
        users=USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        docker_name='nvos_tacacs',
        users_per_auth_type=USERS_BY_AUTH_TYPE
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

    USERS_BY_AUTH_TYPE = {
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
        auth_type=AaaConsts.PAP,
        users=USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        docker_name='nvos_tacacs2',
        users_per_auth_type=USERS_BY_AUTH_TYPE
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
