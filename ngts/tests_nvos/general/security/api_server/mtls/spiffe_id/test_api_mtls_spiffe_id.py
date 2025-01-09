import random
from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.constants import INVALID_SPIFFE_ERR, INCOMPLETE_ERR, \
    SPIFFE_UNIQUENESS_ERR
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.helpers import generate_rand_spiffe_id
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.helpers.general_helpers import generate_rand_str, verify_result_obj_failure
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.security
@pytest.mark.mtls
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_api_spiffe_cli(test_api, local_admin_users: List[UserInfo]):
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
                    out = OutputParsingTool.parse_json_str_to_dictionary(
                        user_obj.spiffe_id.spiffe[spif].show()).get_returned_value()
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


@pytest.mark.security
@pytest.mark.mtls
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_api_spiffe_invalid_value(test_api, local_adminuser: UserInfo):
    """
    Verify that set with bad param rejected
    Steps:
    1. Set invalid spiffe (empty, bad formatted string, too long?, too short?)
    2. Verify set command rejected
    3. Verify in show – expect the value doesn’t exist
    """
    TestToolkit.update_apis(test_api)
    user_obj = System().aaa.user.user_id[local_adminuser.username]

    class Case:
        def __init__(self, name: str, spif_val: str, expected_err: str):
            self.name: str = name
            self.spif_val: str = name
            self.expected_err: str = expected_err

    cases: List[Case] = [
        Case('empty spif ""', '', INCOMPLETE_ERR),
        Case('rand str (not well spiffe formatted)', generate_rand_str(10), INVALID_SPIFFE_ERR),
        Case('too long spif', generate_rand_spiffe_id(50, 50), 'TODO'),  # TODO: check
        Case('too short spif', generate_rand_spiffe_id(1, 1), 'TODO'),  # TODO: check
    ]

    with allure.step('Set invalid spiffes and verify err'):
        for case in cases:
            with allure.independent_step(case.name):
                res: ResultObj = user_obj.spiffe_id.spiffe[case.spif_val].set()
                verify_result_obj_failure(res, case.expected_err)
    with allure.step('Verify in show – expect the value doesn’t exist'):
        out = OutputParsingTool.parse_json_str_to_dictionary(user_obj.spiffe_id.show()).get_returned_value()
        existing_invalid_spiffs = [case.spif_val for case in cases if case.spif_val in out]
        assert not existing_invalid_spiffs, f'invalid values "{existing_invalid_spiffs}" exist in show spiffe output: {out}'


@pytest.mark.security
@pytest.mark.mtls
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_api_spiffe_uniqueness_apply_together(test_api, local_admin_users: List[UserInfo]):
    """
    Verify that can’t set same SPIFFE to multiple users

    Steps:
    1. Set spiffe1 to user1
    2. Set spiffe1 to user2
    3. apply them together
    4. Verify apply failed
    5. verify both users don't have spiffe1
    """
    TestToolkit.update_apis(test_api)
    system = System()
    user1, user2 = local_admin_users[0], local_admin_users[1]
    user1_obj, user2_obj = system.aaa.user.user_id[user1.username], system.aaa.user.user_id[user2.username]
    spif = generate_rand_spiffe_id()

    with allure.step('test applying same spiffe to 2 users fail (apply on both users together)'):
        with allure.step(f'set spiffe "{spif}" to both users'):
            user1_obj.spiffe_id.spiffe[spif].set().verify_result()
            res: ResultObj = user2_obj.spiffe_id.spiffe[spif].set(apply=True)
        with allure.independent_step('verify failure'):
            verify_result_obj_failure(res, SPIFFE_UNIQUENESS_ERR.format(spif))
        with allure.independent_step("verify both users don't have the spiffe"):
            for user in [user1, user2]:
                with allure.independent_step(user.username):
                    user_obj = system.aaa.user.user_id[user.username]
                    out = OutputParsingTool.parse_json_str_to_dictionary(user_obj.spiffe_id.show()).get_returned_value()
                    assert spif not in out, f'spif "{spif}" unexpectedly found in user ({user.username}) spiffes\n{out}'


@pytest.mark.security
@pytest.mark.mtls
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_api_spiffe_uniqueness_apply_separately(test_api, local_admin_users: List[UserInfo]):
    """
    Verify that can’t set same SPIFFE to multiple users

    Steps:
    1. Set spiffe1 to user1 + apply
    2. Set spiffe1 to user2 + apply
    3. Verify 2nd apply failed
    4. verify user1 has spiffe1, but user2 doesn't have spiffe1
    """
    TestToolkit.update_apis(test_api)
    system = System()
    user1, user2 = local_admin_users[0], local_admin_users[1]
    user1_obj, user2_obj = system.aaa.user.user_id[user1.username], system.aaa.user.user_id[user2.username]
    spif = generate_rand_spiffe_id()

    with allure.step('test applying same spiffe to 2 users fail (apply separately)'):
        with allure.step(f'set spiffe "{spif}" to both users'):
            user1_obj.spiffe_id.spiffe[spif].set(apply=True).verify_result()
            res: ResultObj = user2_obj.spiffe_id.spiffe[spif].set(apply=True)
        with allure.independent_step('verify failure for 2nd user apply'):
            verify_result_obj_failure(res, SPIFFE_UNIQUENESS_ERR.format(spif))
        with allure.independent_step(f"verify only user1 ({user1.username}) has spiffe"):
            with allure.independent_step(user1.username):
                out = OutputParsingTool.parse_json_str_to_dictionary(user1_obj.spiffe_id.show()).get_returned_value()
                assert spif in out, f'spif "{spif}" unexpectedly missing in user1 ({user1.username}) spiffes\n{out}'
            with allure.independent_step(user2.username):
                out = OutputParsingTool.parse_json_str_to_dictionary(user2_obj.spiffe_id.show()).get_returned_value()
                assert spif not in out, f'spif "{spif}" unexpectedly found in user2 ({user2.username}) spiffes\n{out}'
