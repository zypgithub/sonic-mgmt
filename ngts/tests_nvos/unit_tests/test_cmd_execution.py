import re
from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.system.Certificate import CertId
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.sonic_mgmt_ci
@pytest.mark.parametrize('api', [ApiType.NVUE])
def test_result_obj_on_invalid_commands(api):
    """
    Verify that some resources operations (set, action, etc) return ResultObj with expected fields

    Any change to the infra in the flow of
    """

    TestToolkit.tested_api = api

    system = System()
    pwh = system.security.password_hardening
    usr = system.aaa.user.user_id[TEST_USR]
    cert = system.security.certificate.cert_id['cert1']

    class Case:
        def __init__(self, name: str, resource: BaseComponent, expected_res: bool, expected_info_substrings: List[str]):
            self.name: str = name
            self.resource: BaseComponent = resource
            self.expected_res: bool = expected_res
            self.expected_info_substrings: List[str] = expected_info_substrings

        def run_cmd(self) -> ResultObj:
            return None

        def verify_res_obj_result(self, res_obj: ResultObj):
            assert res_obj.result == self.expected_res, (f'result of result obj is not as expected. '
                                                         f'expected: {self.expected_res}. actual: {res_obj.result}')

        def verify_substr_in_res_obj_info(self, res_obj: ResultObj):
            missing_expected_substrings = [pattern for pattern in self.expected_info_substrings if
                                           not re.search(pattern, res_obj.info)]
            assert not missing_expected_substrings, (f'info of result obj does not contain all expected substrings.\n'
                                                     f'missing substrings: {missing_expected_substrings}\n'
                                                     f'actual info: {res_obj.info}\n'
                                                     f'all expected substrings: {self.expected_info_substrings}')

    class SetCase(Case):
        def __init__(self, name: str, resource: BaseComponent, param_name, param_val, apply: bool, expected_res: bool,
                     expected_info_substrings: List[str]):
            super().__init__(name, resource, expected_res, expected_info_substrings)
            self.param_name = param_name
            self.param_val = param_val
            self.apply: bool = apply

        def run_cmd(self) -> ResultObj:
            return self.resource.set(self.param_name, self.param_val, apply=self.apply)

    class ImportCertCase(Case):
        def __init__(self, name: str, resource: CertId, uri_bundle: str, expected_res: bool,
                     expected_info_substrings: List[str]):
            super().__init__(name, None, expected_res, expected_info_substrings)
            self.resource: CertId = resource
            self.uri_bundle: str = uri_bundle

        def run_cmd(self) -> ResultObj:
            return self.resource.action_import(uri_bundle=self.uri_bundle)

    cases: List[Case] = [
        SetCase('set - incomplete - no param', system, '', '', False, False, [f'{Messages.ERR_INCOMPLETE}.*{resource_path(system)}']),
        SetCase('set - incomplete - no value', pwh, 'state', '', False, False, [f'{Messages.ERR_INCOMPLETE}.*{resource_path(pwh)}']),
        SetCase('set - invalid user password - multiple errors', usr, 'password', TEST_USR, False, False, Messages.ERR_WEAK_PW),
        ImportCertCase('action import - bad scp url - timeout', cert, 'scp://root:12345@1.2.3.4/auto/sysgwork/lalala', False, [Messages.ERR_TIMEOUT]),
    ]

    with allure.step('verify several error messages are in result object info'):
        for case in cases:
            with allure.independent_step(case.name):
                with allure.step('run the command'):
                    res_obj: ResultObj = case.run_cmd()
                with allure.step('verify actual returned value is of type ResultObj'):
                    assert isinstance(res_obj, ResultObj), f'returned result of set is not of expected type ResultObj. actual type: {type(res_obj)}. res: {res_obj}'
                with allure.independent_step('verify result'):
                    case.verify_res_obj_result(res_obj)
                with allure.independent_step('verify info contains expected substr'):
                    case.verify_substr_in_res_obj_info(res_obj)


TEST_USR = 'usr'


class Messages:
    ERR_INCOMPLETE = 'Error: Incomplete Command:'
    ERR_WEAK_PW = [
        'Error: User.*: password does not meet the requirements',
        'Password should be different than username',
        'Password should contain at least.*characters',
        'Password should contain at least one uppercase character',
        'Password should contain at least one digit',
        'Password should contain at least one special character',
    ]
    ERR_TIMEOUT = 'Error: Timed out'


def resource_path(resource: BaseComponent) -> str:
    return resource.get_resource_path().replace('/', ' ').strip()
