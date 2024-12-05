import random
from typing import Union

from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.Hostname import HostnameId
from ngts.tests_nvos.general.security.security_test_tools.constants import AuthType, AddressingType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RemoteAaaServerInfo, \
    update_active_aaa_server, TacacsServerInfo
from ngts.tests_nvos.general.security.tacacs.constants import TacacsConsts, TacacsDockerServer0, TacacsDockerServer1
from ngts.tools.test_utils import allure_utils as allure


def update_tacacs_server_auth_type(engines, item, server_info: RemoteAaaServerInfo, server_resource: HostnameId,
                                   auth_type: str):
    assert auth_type in AuthType.ALL_TYPES, f'{auth_type} is not one of {AuthType.ALL_TYPES}'
    with allure.step(f'Set server auth-type to: {auth_type}'):
        server: Union[TacacsServerInfo, RemoteAaaServerInfo] = server_info
        server.update_auth_type(auth_type, item)
        update_active_aaa_server(item, server_info)


def get_two_different_tacacs_servers():
    server1: TacacsServerInfo = TacacsDockerServer0.SERVER_BY_ADDRESSING_TYPE[AddressingType.IPV4].copy()
    server2: TacacsServerInfo = TacacsDockerServer1.SERVER_BY_ADDRESSING_TYPE[AddressingType.IPV6].copy()
    auth_type1 = random.choice(TacacsConsts.AUTH_TYPES)
    auth_type2 = RandomizationTool.select_random_value(TacacsConsts.AUTH_TYPES,
                                                       forbidden_values=[auth_type1]).get_returned_value()
    server1.update_auth_type(auth_type1, None, set_on_dut=False)
    server2.update_auth_type(auth_type2, None, set_on_dut=False)
    return server1, server2
