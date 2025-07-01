from typing import Dict

from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AddressingType, AccountingConsts, \
    AuthConsts
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import TacacsServerInfo
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo


class TacacsConsts:
    TIME_TILL_TACACS_CONF_TAKES_PLACE = 3

    TACACS_FIELDS = [AaaConsts.PORT, AaaConsts.TIMEOUT, AccountingConsts.ACCOUNTING, AuthConsts.AUTHENTICATION]
    AUTH_MODES = [AaaConsts.PAP, AaaConsts.CHAP, AaaConsts.LOGIN]

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


class TacacsSkynetServer:
    USERS = [
        UserInfo(
            username='admin',
            password='admin',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='monitor',
            password='monitor_login',
            role=AaaConsts.MONITOR
        )
    ]
    USERS_PAP = [UserInfo(user.username, user.password, user.role) for user in USERS]
    USERS_CHAP = [UserInfo(user.username, user.password, user.role) for user in USERS]
    USERS_LOGIN = [UserInfo(user.username, user.password, user.role) for user in USERS]

    USERS_BY_AUTH_MODE = {
        AaaConsts.PAP: USERS_PAP,
        AaaConsts.CHAP: USERS_CHAP,
        AaaConsts.LOGIN: USERS_LOGIN
    }

    SERVER_IPV4 = TacacsServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='nvos_skynet',
        port=54,
        timeout=5,
        auth_mode=AaaConsts.PAP,
        users=USERS_PAP,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        docker_name='nvos_skynet_tacacs',
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
