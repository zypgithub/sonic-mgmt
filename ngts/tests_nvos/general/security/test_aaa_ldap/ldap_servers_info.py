from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import LdapServerInfo
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo


class LdapServers:
    GLOBAL_BASE_DN = 'dc=itzgeek,dc=local'
    GLOBAL_BIND_DN = 'cn=ldapadm,dc=itzgeek,dc=local'
    GLOBAL_VERSION = 3

    PHYSICAL_SERVER = LdapServerInfo(
        hostname=AaaConsts.PHYSICAL_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=389,
        base_dn=GLOBAL_BASE_DN,
        bind_dn=GLOBAL_BIND_DN,
        timeout_bind=5,
        timeout_search=5,
        version=GLOBAL_VERSION,
        users=[
            UserInfo(
                username='adminuser',
                password='asd',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='monitoruser',
                password='asd',
                role=AaaConsts.MONITOR
            )
        ]
    )

    DOCKER_SERVER_IPV4 = LdapServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=389,
        base_dn=GLOBAL_BASE_DN,
        bind_dn=GLOBAL_BIND_DN,
        timeout_bind=5,
        timeout_search=5,
        version=GLOBAL_VERSION,
        ssl_port=636,
        users=[
            # UserInfo(
            #     username='adminuser',
            #     password='asdasd',
            #     role=AaaConsts.ADMIN
            # ),
            # UserInfo(
            #     username='monitoruser',
            #     password='asd',
            #     role=AaaConsts.MONITOR
            # ),
            UserInfo(
                username='azmy',
                password='azmy',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='alon',
                password='alon',
                role=AaaConsts.MONITOR
            )
        ]
    )
    DOCKER_SERVER_IPV6 = DOCKER_SERVER_IPV4.copy()
    DOCKER_SERVER_IPV6.hostname = AaaConsts.VM_AAA_SERVER_IPV6_ADDR
    DOCKER_SERVER_DN = DOCKER_SERVER_IPV4.copy()
    DOCKER_SERVER_DN.hostname = AaaConsts.VM_AAA_SERVER_DN

    DOCKER_SERVERS = {
        AaaConsts.IPV4: DOCKER_SERVER_IPV4,
        AaaConsts.IPV6: DOCKER_SERVER_IPV6,
        AaaConsts.DN: DOCKER_SERVER_DN
    }

    DOCKER_SERVER_DN_WITH_CERT = DOCKER_SERVER_IPV4.copy()
    DOCKER_SERVER_DN_WITH_CERT.hostname = 'ldap.itzgeek.local'


class LdapServersP3:
    BASE_DN = 'dc=itzgeek,dc=local'
    BIND_DN = 'cn=ldapadm,dc=itzgeek,dc=local'
    VERSION = 3

    LDAP1_IPV4 = LdapServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=391,
        base_dn=BASE_DN,
        bind_dn=BIND_DN,
        timeout_bind=5,
        timeout_search=5,
        version=VERSION,
        ssl_port=392,
        users=[
            UserInfo(
                username='ldap1adm1',
                password='ldap1adm1',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='ldap1adm2',
                password='ldap1adm2',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='ldap1adm3',
                password='ldap1adm3',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='ldap1mon1',
                password='ldap1mon1',
                role=AaaConsts.MONITOR
            ),
            UserInfo(
                username='ldap1mon2',
                password='ldap1mon2',
                role=AaaConsts.MONITOR
            )
        ]
    )
    LDAP1_IPV6 = LDAP1_IPV4.copy()
    LDAP1_IPV6.hostname = AaaConsts.VM_AAA_SERVER_IPV6_ADDR
    LDAP1_DN = LDAP1_IPV4.copy()
    LDAP1_DN.hostname = AaaConsts.VM_AAA_SERVER_DN

    LDAP2_IPV4 = LdapServerInfo(
        hostname=AaaConsts.VM_AAA_SERVER_IPV4_ADDR,
        priority=1,
        secret='secret',
        port=2389,
        base_dn=BASE_DN,
        bind_dn=BIND_DN,
        timeout_bind=5,
        timeout_search=5,
        version=VERSION,
        ssl_port=2636,
        users=[
            UserInfo(
                username='ldap2adm1',
                password='ldap2adm1',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='ldap2adm2',
                password='ldap2adm2',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='ldap2adm3',
                password='ldap2adm3',
                role=AaaConsts.ADMIN
            ),
            UserInfo(
                username='ldap2mon1',
                password='ldap2mon1',
                role=AaaConsts.MONITOR
            ),
            UserInfo(
                username='ldap2mon2',
                password='ldap2mon2',
                role=AaaConsts.MONITOR
            )
        ]
    )
    LDAP2_IPV6 = LDAP2_IPV4.copy()
    LDAP2_IPV6.hostname = AaaConsts.VM_AAA_SERVER_IPV6_ADDR
    LDAP2_DN = LDAP2_IPV4.copy()
    LDAP2_DN.hostname = AaaConsts.VM_AAA_SERVER_DN

    LDAP1_SERVERS = {
        AaaConsts.IPV4: LDAP1_IPV4,
        AaaConsts.IPV6: LDAP1_IPV6,
        AaaConsts.DN: LDAP1_DN
    }
