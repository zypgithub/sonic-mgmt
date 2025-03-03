from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AddressingType, AuthMedium, \
    UserRole
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RadiusServerInfo, \
    UsersPerAuthMedium
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo


class RadiusConsts:
    TIME_TILL_RADIUS_CONF_TAKES_PLACE = 3

    RADIUS_FIELDS = [AaaConsts.AUTH_TYPE, AaaConsts.PORT, AaaConsts.RETRANSMIT, AaaConsts.STATISTICS, AaaConsts.TIMEOUT]
    AUTH_TYPES = [AaaConsts.PAP, AaaConsts.CHAP, AaaConsts.MSCHAPV2]

    VALID_VALUES = {
        AaaConsts.SERVER: str,
        AaaConsts.TIMEOUT: list(range(1, 61)),
        AaaConsts.AUTH_TYPE: AUTH_TYPES,
        AaaConsts.SECRET: str,
        AaaConsts.PORT: list(range(AaaConsts.MIN_PORT, AaaConsts.MAX_PORT + 1)),
        AaaConsts.RETRANSMIT: list(range(11)),
        AaaConsts.STATISTICS: [AaaConsts.DISABLED, AaaConsts.ENABLED],
        AaaConsts.PRIORITY: list(range(1, 9))
    }

    DEFAULT_RADIUS_CONF = {
        AaaConsts.AUTH_TYPE: AaaConsts.MSCHAPV2,
        AaaConsts.SERVER: {},
        AaaConsts.PORT: 1812,
        AaaConsts.SECRET: '*',
        AaaConsts.RETRANSMIT: 0,
        AaaConsts.STATISTICS: AaaConsts.DISABLED,
        AaaConsts.TIMEOUT: 5,
    }

    DEFAULTS = {
        AaaConsts.TIMEOUT: 3,
        AaaConsts.AUTH_TYPE: AaaConsts.MSCHAPV2,
        AaaConsts.PORT: 1812,
        AaaConsts.RETRANSMIT: 0,
        AaaConsts.STATISTICS: AaaConsts.DISABLED,
        AaaConsts.PRIORITY: 1
    }

    FIELD_IS_NUMERIC = {
        AaaConsts.SERVER: False,
        AaaConsts.TIMEOUT: True,
        AaaConsts.AUTH_TYPE: False,
        AaaConsts.SECRET: False,
        AaaConsts.PORT: True,
        AaaConsts.RETRANSMIT: True,
        AaaConsts.STATISTICS: False,
        AaaConsts.PRIORITY: True
    }


class RadiusPhysicalServer:
    USERS = [
        UserInfo(
            username='pradadm1',
            password='pradadm1',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='pradmon1',
            password='pradmon1',
            role=AaaConsts.MONITOR
        ),
        UserInfo(
            username='pradadm2',
            password='pradadm2',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='pradmon2',
            password='pradmon2',
            role=AaaConsts.MONITOR
        ),
        # UserInfo(
        #     username='admin',
        #     password='adminadmin',
        #     role=AaaConsts.ADMIN
        # ),
        # UserInfo(
        #     username='testing',
        #     password='testing',
        #     role=AaaConsts.MONITOR
        # )
    ]

    users_per_medium: UsersPerAuthMedium = {
        AuthMedium.SSH: {
            UserRole.ADMIN: [UserInfo('pradadm-ssh', 'pradadm-ssh', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('pradmon-ssh', 'pradmon-ssh', UserRole.MONITOR)],
        },
        AuthMedium.OPENAPI: {
            UserRole.ADMIN: [UserInfo('pradadm-rest', 'pradadm-rest', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('pradmon-rest', 'pradmon-rest', UserRole.MONITOR)],
        },
        AuthMedium.RCON: {
            UserRole.ADMIN: [UserInfo('pradadm-rcon', 'pradadm-rcon', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('pradmon-rcon', 'pradmon-rcon', UserRole.MONITOR)],
        },
        AuthMedium.SCP: {
            UserRole.ADMIN: [UserInfo('pradadm-scp', 'pradadm-scp', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('pradmon-scp', 'pradmon-scp', UserRole.MONITOR)],
        }
    }

    SERVER_IPV4 = RadiusServerInfo(
        hostname=AaaConsts.PHYSICAL_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='testing-radius',
        port=1812,
        timeout=5,
        # retransmit=0,
        auth_type=AaaConsts.PAP,
        users=USERS,
        ipv4_addr=AaaConsts.PHYSICAL_AAA_SERVER_IPV4_ADDR,
        users_per_auth_medium=users_per_medium
    )
    # SERVER_IPV6 = SERVER_IPV4.copy()
    # SERVER_IPV6.hostname = AaaConsts.PHYSICAL_AAA_SERVER_IPV6_ADDR
    # SERVER_DN = SERVER_IPV4.copy()
    # SERVER_DN.hostname = AaaConsts.PHYSICAL_AAA_SERVER_DN

    SERVER_BY_ADDRESSING_TYPE = {
        AddressingType.IPV4: SERVER_IPV4,
        # AddressingType.IPV6: SERVER_IPV6,
        # AddressingType.DN: SERVER_DN
    }


class RadiusVmServer:
    USERS = [
        UserInfo(
            username='rad1adm1',
            password='rad1adm1',
            role=AaaConsts.ADMIN
        ),
        UserInfo(
            username='rad1mon1',
            password='rad1mon1',
            role=AaaConsts.MONITOR
        ),
    ]

    users_per_medium: UsersPerAuthMedium = {
        AuthMedium.SSH: {
            UserRole.ADMIN: [UserInfo('rad1adm-ssh', 'rad1adm-ssh', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('rad1mon-ssh', 'rad1mon-ssh', UserRole.MONITOR)],
        },
        AuthMedium.OPENAPI: {
            UserRole.ADMIN: [UserInfo('rad1adm-rest', 'rad1adm-rest', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('rad1mon-rest', 'rad1mon-rest', UserRole.MONITOR)],
        },
        AuthMedium.RCON: {
            UserRole.ADMIN: [UserInfo('rad1adm-rcon', 'rad1adm-rcon', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('rad1mon-rcon', 'rad1mon-rcon', UserRole.MONITOR)],
        },
        AuthMedium.SCP: {
            UserRole.ADMIN: [UserInfo('rad1adm-scp', 'rad1adm-scp', UserRole.ADMIN)],
            UserRole.MONITOR: [UserInfo('rad1mon-scp', 'rad1mon-scp', UserRole.MONITOR)],
        }
    }

    SERVER_IPV4 = RadiusServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='testing123',
        port=1812,
        timeout=5,
        # retransmit=0,
        auth_type=AaaConsts.PAP,
        users=USERS,
        ipv4_addr=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
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
