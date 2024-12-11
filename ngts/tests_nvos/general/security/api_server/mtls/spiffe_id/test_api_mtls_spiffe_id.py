import random
from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.helpers import generate_rand_spiffe_id
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.security
@pytest.mark.mtls
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_api_spiffe_id_cli(test_api, local_admin_users: List[UserInfo], local_monitor_users: List[UserInfo]):
    """
    Verify that all CLI work and check values change properly in show

    Steps:
    1. Run show commands
    2. Verify outputs contain the required fields
    3. Run set command
    4. Verify in show commands
    5. Unset
    6. Verify in show commands
    """
    TestToolkit.update_apis(test_api)
    system = System()
    rand_user: UserInfo = random.choice(local_admin_users)
    user_obj = system.aaa.user.user_id[rand_user.username]
    spifs = [generate_rand_spiffe_id() for _ in range(3)]
    spif1 = spifs[0]

    with allure.step('Run show commands and verify outputs contain the required fields'):
        out = OutputParsingTool.parse_json_str_to_dictionary(user_obj.spiffe_id.show()).get_returned_value()
        assert out == {}, f'output of general spiffe resource is not empty as expected. actual: {out}'
        out = user_obj.spiffe_id.spiffe[spif1].show()
        # TODO: check how it should that its not exists be and assert it
    with allure.step('Set multiple spiffes to single user'):
        for spif in spifs:
            with allure.independent_step(spif):
                user_obj.spiffe_id.spiffe[spif].set().verify_result()
    with allure.step('apply'):
        user_obj._cli_wrapper.apply_config(verify_execution=True)
    with allure.step('Verify in show commands'):
        with allure.independent_step('general spiffe-id show of a user'):
            out = OutputParsingTool.parse_json_str_to_dictionary(user_obj.spiffe_id.show()).get_returned_value()
            expected = {spif: {} for spif in spifs}
            assert out == expected, f'output of general spiffe resource is not as expected:\nexpected: {expected}\nactual: {out}'
        with allure.step('check show of specific spiffe'):
            for spif in spifs:
                with allure.independent_step(spif):
                    out = OutputParsingTool.parse_json_str_to_dictionary(user_obj.spiffe_id.spiffe[spif].show()).get_returned_value()
                    assert out == {}, f'output of specific spiffe is not empty as expected.\nactual: {out}'
    with allure.step('Unset and verify in show'):
        with allure.independent_step('unset specific spif'):
            with allure.step('unset'):
                user_obj.spiffe_id.spiffe[spif1].unset(apply=True).verify_result()
            with allure.step('verify deleted in show'):
                out = OutputParsingTool.parse_json_str_to_dictionary(user_obj.spiffe_id.show()).get_returned_value()
                assert out != {}, f'show output is unexpectedly empty after unsetting a single spiffe'
                assert spif1 not in out, f'spiffe "{spif1}" unexpectedly exist in show output after unset'
        with allure.independent_step('unset all spifs'):
            with allure.step('unset'):
                user_obj.spiffe_id.spiffe.unset(apply=True).verify_result()
            with allure.step('verify deleted in show'):
                out = OutputParsingTool.parse_json_str_to_dictionary(user_obj.spiffe_id.show()).get_returned_value()
                assert out == {}, f'show output is not empty after unsetting all spiffes'
