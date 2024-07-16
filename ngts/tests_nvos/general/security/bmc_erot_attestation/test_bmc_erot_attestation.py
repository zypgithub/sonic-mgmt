import random
from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.Spdm import SpdmComponentFields
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.bmc_erot_attestation.constants import VALID_NONCE_LEN, SpdmConsts, NOT_EMPTY
from ngts.tests_nvos.general.security.bmc_erot_attestation.helpers import get_component_obj, randomize_hex_str, \
    randomize_non_hex_str, assert_no_issues, add_issue_if, verify_component_outputs
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_list_supported_components(test_api):
    """
    Verify that the general show command lists the supported components

    1.	run show spdm
    2.	verify output gives the supported components
    """
    TestToolkit.tested_api = test_api
    with allure.step('run show spdm'):
        out: dict = OutputParsingTool.parse_json_str_to_dictionary(System().security.spdm.show()).get_returned_value()
    with allure.step('verify output gives the supported components '):
        missing_components = [c for c in SpdmConsts.fields if c not in out]
        extra_components = [c for c in out.keys() if c not in SpdmConsts.fields]
        assert not missing_components and not extra_components, f'show spdm content is wrong.\nexpected fields: {SpdmConsts.fields}\nactual: {list(out.keys())}'


@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_main_flow(test_api, clear_measurements, available_spdm_components):
    """
    Verify that show component works properly and shows certificate chain

    1.  show spdm
    2.  verify all components exist as fields
    3.  verify inner outputs before generate
        1.  show component  #, component measurements, component certificate
        2.  verify fields [certificate, measurements] exist
        3.  show component certificate
        4,  verify fields [CertificateString, CertificateType, CertificateUsageTypes, Id, Name, SPDM] exist
        5.  show component measurements
        6,  verify fields [HashingAlgorithm, SignedMeasurements, SigningAlgorithm, Version] exist
        7.  check initial values
            - available device:     default values
            - unavailable device:   N/As
        8.  sanity check on values
    3.  generate
    4.  verify inner outputs after generate
        1-6.sub steps 1-6 same as before generate (3)
        7.  check values
            - available device:     same certificate, non-default measurements
            - unavailable device:   N/As
        8.  sanity check on values
    """
    TestToolkit.tested_api = test_api
    spdm = System().security.spdm

    with allure.step('show spdm'):
        out = OutputParsingTool.parse_json_str_to_dictionary(spdm.show()).get_returned_value()
    with allure.step(f'verify all components ({SpdmConsts.fields}) exist as fields'):
        ValidationTool.verify_field_exist_in_json_output(out, SpdmConsts.fields).verify_result()

    for component in SpdmConsts.components:
        with allure.step(f'component: {component}'):
            component_obj = get_component_obj(component)
            component_is_available: bool = component in available_spdm_components
            with allure.step('verify inner outputs before generate'):
                cert_out, _ = verify_component_outputs(component, component_obj, component_is_available, None, None)
            with allure.step(f'generate measurements - expect success: {component_is_available}'):
                issues: List[str] = []
                with allure.step(f'Run generate with valid nonce - expect success: {component_is_available}'):
                    nonce = randomize_hex_str()
                    res = component_obj.action_generate(nonce)
                    add_issue_if(res.result != component_is_available, issues,
                                 f'{component} - generate with valid nonce {"succeeded" if res.result else "failed"} but expected to {"succeed" if component_is_available else "fail"}')
                with allure.step(f'Run generate without nonce param - expect success: {component_is_available}'):
                    res = component_obj.action_generate()
                    add_issue_if(res.result != component_is_available, issues,
                                 f'{component} - generate without nonce {"succeeded" if res.result else "failed"} but expected to {"succeed" if component_is_available else "fail"}')
                with allure.step('assert no issues'):
                    assert_no_issues(component, issues, 'some generate commands failed')
            with allure.step('verify inner outputs after generate'):
                verify_component_outputs(component, component_obj, component_is_available,
                                         expect_cert=cert_out[SpdmConsts.Component.Certificate.CERT_STRING],
                                         expect_measurements=NOT_EMPTY)


@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_generate_with_bad_nonce_param(test_api, available_spdm_components):
    """
    Verify that generate command rejected when giving invalid nonce

    1.	run generate with non-hex string as nonce param
    2.	expect failure
    3.	run generate with hex string longer than 64 chars
    4.	expect failure
    5.	run generate with hex string shorter than 64 chars
    6.	expect failure
    """
    TestToolkit.tested_api = test_api
    for component in available_spdm_components:
        component_obj = get_component_obj(component)
        with allure.step(f'component: {component}'):
            issues: List[str] = []
            with allure.step('run generate with empty nonce param (incomplete)'):
                bad_nonce = ''
                res = component_obj.action_generate(bad_nonce)
                add_issue_if(res.result, issues,
                             f'generate with empty nonce (incomplete) - success but expected to fail\n{res.info}')
            with allure.step('run generate with non-hex string as nonce param'):
                bad_nonce = randomize_non_hex_str()
                res = component_obj.action_generate(bad_nonce)
                add_issue_if(res.result, issues,
                             f'generate with non hex nonce - success but expected to fail\n{res.info}')
            with allure.step(f'run generate with hex string longer than {VALID_NONCE_LEN} chars'):
                bad_nonce = randomize_hex_str(random.randint(VALID_NONCE_LEN + 1, 2 * VALID_NONCE_LEN))
                res = component_obj.action_generate(bad_nonce)
                add_issue_if(res.result, issues,
                             f'generate with too long hex nonce - success but expected to fail\n{res.info}')
            with allure.step(f'run generate with hex string shorter than {VALID_NONCE_LEN} chars'):
                bad_nonce = randomize_hex_str(random.randint(1, VALID_NONCE_LEN - 1))
                res = component_obj.action_generate(bad_nonce)
                add_issue_if(res.result, issues,
                             f'generate with too short hex nonce - success but expected to fail\n{res.info}')
            with allure.step('assert no issues'):
                assert not issues, f'found issues:\n' + '\n'.join(issues)


def test_generate_without_nonce_give_different_measurement(available_spdm_components):
    """
    Verify that when generating without nonce param multiple times it generates different measurements

    1.	generate without nonce
    2.	get measurements
    3.	generate without nonce
    4.	get measurements
    5.	verify measurements from step 2, 4 are different
    """
    for component in available_spdm_components:
        with allure.step(f'component: {component}'):
            component_obj = get_component_obj(component)
            with allure.step('generate without nonce'):
                component_obj.action_generate()  # .verify_result()
            with allure.step('get measurements'):
                measurements1 = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()[SpdmComponentFields.MEASUREMENTS]
            with allure.step('generate without nonce'):
                component_obj.action_generate()  # .verify_result()
            with allure.step('get measurements'):
                measurements2 = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()[SpdmComponentFields.MEASUREMENTS]
            with allure.step('verify measurements from step 2, 4 are different'):
                ValidationTool.compare_dictionaries(measurements1, measurements2).verify_result(False)


def test_generate_with_nonce_give_same_measurement(available_spdm_components):
    """
    Verify that when generating with nonce param multiple times it generates same measurements

    1.	generate with nonce
    2.	get measurements
    3.	generate with nonce
    4.	get measurements
    5.	verify measurements from step 2, 4 are same
    """
    for component in available_spdm_components:
        with allure.step(f'component: {component}'):
            component_obj = get_component_obj(component)
            rand_nonce = randomize_hex_str()
            with allure.step('generate without nonce'):
                component_obj.action_generate(rand_nonce)  # .verify_result()
            with allure.step('get measurements'):
                measurements1 = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()[SpdmComponentFields.MEASUREMENTS]
            with allure.step('generate without nonce'):
                component_obj.action_generate(rand_nonce)  # .verify_result()
            with allure.step('get measurements'):
                measurements2 = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()[SpdmComponentFields.MEASUREMENTS]
            with allure.step('verify measurements from step 2, 4 are different'):
                ValidationTool.compare_dictionaries(measurements1, measurements2).verify_result(True)


def test_reboot_system_keeps_data(available_spdm_components):
    """
    Verify that reboot keeps the results of the show

    1.	generate measurements for all components
    2.	run show and save outputs
    3.	reboot
    4.	run show components and compare outputs
    """
    outputs_before_reboot = {}
    issues: List[str] = []
    with allure.step('generate measurements and save show output for all components'):
        for component in available_spdm_components:
            with allure.step(f'component: {component}'):
                component_obj = get_component_obj(component)
                with allure.step('generate measurements for components'):
                    component_obj.action_generate().verify_result()
                with allure.step('save show output before reboot'):
                    out = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()
                    outputs_before_reboot[component] = out
    with allure.step('reboot the system'):
        System().action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()
    with allure.step('run show components and compare outputs'):
        for component in available_spdm_components:
            with allure.step(f'component: {component}'):
                component_obj = get_component_obj(component)
                with allure.step('save show output before reboot'):
                    out = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()
                    res: ResultObj = ValidationTool.compare_dictionaries(outputs_before_reboot[component], out)
                    add_issue_if(not res.result, issues, f'component: {component}\n{res.info}\n')
    with allure.step('verify no issues in the comparison'):
        assert_no_issues(component, issues, 'there are output mismatches before and after reboot')
