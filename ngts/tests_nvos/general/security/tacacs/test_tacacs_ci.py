import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType, AuthMedium
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.constants import RemoteAaaType
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.generic_aaa_ci_testing import \
    generic_aaa_ci_test_auth
from ngts.tests_nvos.general.security.tacacs.constants import TacacsDockerServer1


@pytest.mark.security_ci
@pytest.mark.security
@pytest.mark.simx_security
@pytest.mark.parametrize('addressing_type', [random.choice(AddressingType.ALL_TYPES)])
def test_tacacs_auth(random_api, addressing_type, engines, topology_obj, request):
    """
    @summary: Basic test to verify authentication and authorization through tacacs, using SSH auth medium.

        Steps:
        1. configure tacacs server
        2. enable
        3. verify tacacs user can authenticate
    """
    tacacs = System().aaa.tacacs
    generic_aaa_ci_test_auth(test_api=test_api, addressing_type=addressing_type, engines=engines,
                             topology_obj=topology_obj, request=request,
                             remote_aaa_type=RemoteAaaType.TACACS,
                             remote_aaa_obj=tacacs,
                             server_by_addr_type=TacacsDockerServer1.SERVER_BY_ADDRESSING_TYPE,
                             skip_auth_mediums=[AuthMedium.OPENAPI, AuthMedium.RCON, AuthMedium.SCP])
