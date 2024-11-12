import json
import logging
import os
import random
from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, TestFlowType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.Spdm import SpdmComponentFields
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.bmc.bmc_erot_attestation.constants import VALID_NONCE_LEN, SpdmConsts, NOT_EMPTY
from ngts.tests_nvos.general.security.bmc.bmc_erot_attestation.helpers import get_component_obj, randomize_hex_str, \
    randomize_non_hex_str, verify_component_outputs, run_client_verification, \
    run_client_measurements_verification_usecanse
from ngts.tests_nvos.general.security.helpers import add_issue_if, assert_no_issues
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.bmc
@pytest.mark.erot
@pytest.mark.security
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


@pytest.mark.bmc
@pytest.mark.erot
@pytest.mark.security
def test_available_components(available_spdm_components):
    """
    Check which components ERoTs are available
    """
    unavailable_erots = [erot for erot in SpdmConsts.components if erot not in available_spdm_components]
    assert not unavailable_erots, f'unavailable SPDM ERoTs: {unavailable_erots}'


@pytest.mark.bmc
@pytest.mark.erot
@pytest.mark.security
@pytest.mark.parametrize("component, test_api",
                         [(component, random.choice(ApiType.ALL_TYPES)) for component in SpdmConsts.components])
def test_main_flow(component, test_api, available_spdm_components):
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

    # for component in [SPDMComponents.BMC]:  #SpdmConsts.components:
    with allure.step(f'component: {component}'):
        component_obj = get_component_obj(component)
        component_is_available: bool = component in available_spdm_components
        with allure.step('verify inner outputs before generate'):
            cert_out, _ = verify_component_outputs(component, component_obj, component_is_available, None, None)
        with allure.step(f'generate measurements - expect success: {component_is_available}'):
            issues: List[str] = []
            with allure.step(f'Run generate without nonce param - expect success: {component_is_available}'):
                res = component_obj.action_generate()
                add_issue_if(res.result != component_is_available, issues,
                             f'{component} - generate without nonce {"succeeded" if res.result else "failed"} but expected to {"succeed" if component_is_available else "fail"}')
            with allure.step(f'Run generate with valid nonce - expect success: {component_is_available}'):
                rand_nonce = randomize_hex_str()
                res = component_obj.action_generate(rand_nonce)
                add_issue_if(res.result != component_is_available, issues,
                             f'{component} - generate with valid nonce {"succeeded" if res.result else "failed"} but expected to {"succeed" if component_is_available else "fail"}')
            with allure.step('assert no issues'):
                assert_no_issues(component, issues, 'some generate commands failed')
        with allure.step('verify inner outputs after generate'):
            verify_component_outputs(component, component_obj, component_is_available,
                                     expect_cert=cert_out[SpdmConsts.Component.Certificates.CERT_STRING],
                                     expect_measurements=NOT_EMPTY)
        if component_is_available:
            run_client_measurements_verification_usecanse(component_obj,
                                                          rand_nonce.lower())  # TODO: lower until talk with lev about request nonce and capitals


@pytest.mark.bmc
@pytest.mark.erot
@pytest.mark.security
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


@pytest.mark.bmc
@pytest.mark.erot
@pytest.mark.security
def test_generate_give_different_measurement(available_spdm_components):
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
                component_obj.action_generate().verify_result()
            with allure.step('get measurements'):
                measurements1 = \
                    OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()[
                        SpdmComponentFields.MEASUREMENTS]
            with allure.step('generate without nonce'):
                component_obj.action_generate().verify_result()
            with allure.step('get measurements'):
                measurements2 = \
                    OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()[
                        SpdmComponentFields.MEASUREMENTS]
            with allure.step('verify measurements from step 2, 4 are different'):
                ValidationTool.compare_dictionaries(measurements1, measurements2).verify_result(False)


@pytest.mark.bmc
@pytest.mark.erot
@pytest.mark.security
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


@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_dummy_attestation_verification(test_flow):
    """
    this is as unit-test to run_client_verification helper function, to make sure it fails for invalid nonce too
    """
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    test_is_good_flow = test_flow == TestFlowType.GOOD_FLOW
    correct_nonce = '5b017bcbe464aa0d5d4d029f7d6c77afee391d5e3f2ad7bdbc6045350d12bc35'
    invalid_nonce = '5b017bcbe464aa0d5d4d029f7d6c76afee391d5e3f2ad7bdbc6045350d12bc35'
    example_nonce = correct_nonce if test_is_good_flow else invalid_nonce
    example_component_data_json_file = os.path.join(cur_dir, 'dummy_bmc_nvue_response.json')
    with allure.step('get component data'):
        with open(example_component_data_json_file, 'r') as file:
            component_data = json.load(file)
    with allure.step('show cert chain'):
        cert_chain_str = component_data[SpdmComponentFields.CERTIFICATES][SpdmConsts.Component.Certificates.CERT_STRING]
        logging.info(f'certificate chain str:\n{cert_chain_str}')
    with allure.step('show measurements'):
        measurements_data = component_data[SpdmComponentFields.MEASUREMENTS]
        logging.info(f'measurements data:\n{measurements_data}')
    with allure.step('verify'):
        run_client_verification(cert_chain_str, measurements_data, example_nonce, test_is_good_flow)
