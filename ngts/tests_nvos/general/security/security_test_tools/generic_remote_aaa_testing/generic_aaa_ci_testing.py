from typing import Dict, List

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.RemoteAaaResource import RemoteAaaResource
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.constants import RemoteAaaType
from ngts.tests_nvos.general.security.security_test_tools.security_test_utils import verify_user_auth
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RemoteAaaServerInfo
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import wait_for_ldap_nvued_restart_workaround


def generic_aaa_ci_test_auth(test_api: str, addressing_type: str, engines, topology_obj, request,
                             remote_aaa_type: str,
                             remote_aaa_obj: RemoteAaaResource,
                             server_by_addr_type: Dict[str, RemoteAaaServerInfo],
                             skip_auth_mediums: List[str] = None):
    """
    @summary: Basic test to verify authentication and authorization through remote aaa, using SSH auth medium.

        Steps:
        1. configure aaa server
        2. enable aaa method
        3. verify remote user can authenticate
    @param test_api: run commands with NVUE / OpenApi
    @param addressing_type: whether to check connectivity with ipv4/ipv6/domain-name addressing
    @param engines: engines object
    @param topology_obj: topology object
    @param request: object containing pytest information about current test
    @param remote_aaa_type: name of he remote Aaa type (tacacs, ldap, radius)
    @param remote_aaa_obj: BaseComponent object representing the feature resource
    @param server_by_addr_type: dictionary containing server info, by addressing type
    @param skip_auth_mediums: auth mediums to skip from the test (optional)
    """
    assert remote_aaa_type in RemoteAaaType.ALL_TYPES, f'{remote_aaa_type} is not one of {RemoteAaaType.ALL_TYPES}'
    assert test_api in ApiType.ALL_TYPES, f'{test_api} is not one of {ApiType.ALL_TYPES}'
    assert addressing_type in AddressingType.ALL_TYPES, f'{addressing_type} is not one of {AddressingType.ALL_TYPES}'

    TestToolkit.tested_api = test_api
    item = request.node

    with allure.step(f'Configure {remote_aaa_type} server'):
        server = server_by_addr_type[addressing_type].copy()
        server.configure(engines)

    with allure.step(f'Enable {remote_aaa_type}'):
        remote_aaa_obj.enable(failthrough=True, apply=True, verify_res=False)
        if remote_aaa_type == RemoteAaaType.LDAP:
            wait_for_ldap_nvued_restart_workaround(item, engine_to_use=engines.dut)

    with allure.step(f'Verify auth with {remote_aaa_type} user'):
        user: UserInfo = server.users[0]
        verify_user_auth(engines, topology_obj, user, expect_login_success=True, skip_auth_mediums=skip_auth_mediums)
