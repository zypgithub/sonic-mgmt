import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.radius.constants import RadiusVmServer
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType, AuthMedium
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.constants import RemoteAaaType
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.generic_aaa_ci_testing import \
    generic_aaa_ci_test_auth


@pytest.mark.security_ci
@pytest.mark.security
@pytest.mark.simx_security
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
@pytest.mark.parametrize('addressing_type', [random.choice(AddressingType.ALL_TYPES)])
def test_radius_auth(test_api, addressing_type, engines, topology_obj, request):
    """
    @summary: Basic test to verify authentication and authorization through radius, using SSH auth medium.

        Steps:
        1. configure radius server
        2. enable
        3. verify radius user can authenticate
    """
    radius = System().aaa.radius
    generic_aaa_ci_test_auth(test_api=test_api, addressing_type=addressing_type, engines=engines,
                             topology_obj=topology_obj, request=request,
                             remote_aaa_type=RemoteAaaType.RADIUS,
                             remote_aaa_obj=radius,
                             server_by_addr_type=RadiusVmServer.SERVER_BY_ADDRESSING_TYPE,
                             skip_auth_mediums=[AuthMedium.OPENAPI, AuthMedium.RCON, AuthMedium.SCP])
