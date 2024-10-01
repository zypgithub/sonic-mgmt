import random
from typing import Union

from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.Hostname import HostnameId
from ngts.tests_nvos.general.security.radius.constants import RadiusConsts, RadiusVmServer, RadiusPhysicalServer
from ngts.tests_nvos.general.security.security_test_tools.constants import AuthType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RemoteAaaServerInfo, \
    update_active_aaa_server, RadiusServerInfo
from ngts.tools.test_utils import allure_utils as allure


def update_radius_server_auth_type(engines, item, server_info: RemoteAaaServerInfo, server_resource: HostnameId,
                                   auth_type: str):
    assert auth_type in AuthType.ALL_TYPES, f'{auth_type} is not one of {AuthType.ALL_TYPES}'
    with allure.step(f'Set server auth-type to: {auth_type}'):
        server: Union[RadiusServerInfo, RemoteAaaServerInfo] = server_info
        server.update_auth_type(auth_type, item)
        update_active_aaa_server(item, server_info)


def get_two_different_radius_servers():
    server1: RadiusServerInfo = random.choice(list(RadiusVmServer.SERVER_BY_ADDRESSING_TYPE.values())).copy()
    server2: RadiusServerInfo = random.choice(list(RadiusPhysicalServer.SERVER_BY_ADDRESSING_TYPE.values())).copy()

    auth_type1 = random.choice(RadiusConsts.AUTH_TYPES)
    auth_type2 = RandomizationTool.select_random_value(RadiusConsts.AUTH_TYPES,
                                                       forbidden_values=[auth_type1]).get_returned_value()
    server1.update_auth_type(auth_type1, None, set_on_dut=False)
    server2.update_auth_type(auth_type2, None, set_on_dut=False)
    return server1, server2
