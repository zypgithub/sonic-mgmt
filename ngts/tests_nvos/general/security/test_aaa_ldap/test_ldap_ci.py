import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType, AuthMedium
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.constants import RemoteAaaType
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.generic_aaa_ci_testing import \
    generic_aaa_ci_test_auth
from ngts.tests_nvos.general.security.test_aaa_ldap.ldap_servers_info import LdapServersP3


@pytest.mark.security_ci
@pytest.mark.security
@pytest.mark.simx_security
@pytest.mark.parametrize('addressing_type', [random.choice(AddressingType.ALL_TYPES)])
def test_ldap_auth_ci(random_api, addressing_type, engines, topology_obj, request):
    """
    @summary: Basic test to verify authentication and authorization through LDAP, using SSH auth medium.

        Steps:
        1. configure LDAP server
        2. enable LDAP
        3. verify LDAP user can authenticate
    """
    ldap = System().aaa.ldap
    generic_aaa_ci_test_auth(test_api=test_api, addressing_type=addressing_type, engines=engines,
                             topology_obj=topology_obj, request=request,
                             remote_aaa_type=RemoteAaaType.LDAP,
                             remote_aaa_obj=ldap,
                             server_by_addr_type=LdapServersP3.LDAP1_SERVERS,
                             skip_auth_mediums=[AuthMedium.OPENAPI, AuthMedium.RCON, AuthMedium.SCP])
