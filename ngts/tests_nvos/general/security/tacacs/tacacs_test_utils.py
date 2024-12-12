import random
from typing import Union

from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.Server import ServerId
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType, AuthMode
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RemoteAaaServerInfo, \
    update_active_aaa_server, TacacsServerInfo
from ngts.tests_nvos.general.security.tacacs.constants import TacacsConsts, TacacsDockerServer0, TacacsDockerServer1
from ngts.tools.test_utils import allure_utils as allure


def update_tacacs_server_auth_mode(engines, item, server_info: RemoteAaaServerInfo, server_resource: ServerId,
                                   auth_mode: str):
    assert auth_mode in AuthMode.ALL_TYPES, f'{auth_mode} is not one of {AuthMode.ALL_TYPES}'
    with allure.step(f'Set server auth-mode to: {auth_mode}'):
        server: Union[TacacsServerInfo, RemoteAaaServerInfo] = server_info
        server.update_auth_mode(auth_mode, item)
        update_active_aaa_server(item, server_info)


def get_two_different_tacacs_servers():
    server1: TacacsServerInfo = TacacsDockerServer0.SERVER_BY_ADDRESSING_TYPE[AddressingType.IPV4].copy()
    server2: TacacsServerInfo = TacacsDockerServer1.SERVER_BY_ADDRESSING_TYPE[AddressingType.IPV6].copy()
    auth_mode1 = random.choice(TacacsConsts.AUTH_MODES)
    auth_mode2 = RandomizationTool.select_random_value(TacacsConsts.AUTH_MODES,
                                                       forbidden_values=[auth_mode1]).get_returned_value()
    server1.update_auth_mode(auth_mode1, None, set_on_dut=False)
    server2.update_auth_mode(auth_mode2, None, set_on_dut=False)
    return server1, server2
