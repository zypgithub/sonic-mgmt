import logging
import random
from typing import List, Tuple

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.Spdm import SpdmComponent, SPDMComponents, COMPONENT_TO_SPDM_OBJ_FIELD
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.bmc_erot_attestation.constants import VALID_NONCE_LEN, SpdmConsts, NOT_EMPTY
from ngts.tools.test_utils import allure_utils as allure


def get_component_obj(component_name: str) -> SpdmComponent:
    assert component_name in SPDMComponents.ALL_SUPPORTED_COMPONENTS, f'given component name "{component_name} not in {SPDMComponents.ALL_SUPPORTED_COMPONENTS}'
    component_field_name = COMPONENT_TO_SPDM_OBJ_FIELD[component_name]
    spdm = System().security.spdm
    assert hasattr(spdm, component_field_name), f'spdm object does not have component field "{component_field_name}"'
    return getattr(spdm, component_field_name)


def randomize_hex_str(length: int = VALID_NONCE_LEN) -> str:
    random_valid_nonce = ''.join(random.choice('0123456789ABCDEFabcdef') for _ in range(length))
    logging.info(f'randomized nonce: random_valid_nonce')
    return random_valid_nonce


def randomize_non_hex_str(length: int = VALID_NONCE_LEN) -> str:
    idx_for_non_hex_char = random.randint(0, length)
    prefix = ''.join(random.choice('0123456789ABCDEFabcdef') for _ in range(idx_for_non_hex_char))
    suffix = ''.join(random.choice('0123456789ABCDEFabcdef') for _ in range(length - idx_for_non_hex_char - 1))
    non_hex_char = random.choice('hijklmnopqrstuvwxyzHIJKLMNOPQRSTUVWXYZ')
    rand_non_hex_nonce = prefix + non_hex_char + suffix
    logging.info(f'randomized non hex str:\n\t"{prefix}" "{non_hex_char}" "{suffix}"\n\t"{rand_non_hex_nonce}"')
    return rand_non_hex_nonce


# def check_component_outputs(component_obj: SpdmComponent, expect_cert_chain=None, expect_measurements=None,
#                             compare_values_to_bmc: bool = True, do_client_verify: bool = False):
#     dut: LinuxSshEngine = TestToolkit.engines.dut
#     out = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()
#     checks = {SpdmComponentFields.CERT_CHAIN: expect_cert_chain, SpdmComponentFields.MEASUREMENTS: expect_measurements}
#     for field_to_check, expected_value in checks.items():
#         if expected_value is not None:
#             with allure.step(f'check field: {field_to_check}'):
#                 if expected_value != ExpectCodes.DONT_COMPARE:
#                     with allure.step('verify value is as expected'):
#                         actual_value = out[field_to_check]
#                         cond = (isinstance(actual_value,
#                                            str) and actual_value != '') if expected_value == ExpectCodes.NOT_EMPTY_STR else actual_value == expected_value
#                         assert cond, f'value of field "{field_to_check}" is not as expected.\nexpected: {expected_value}\nactual: {actual_value}'
#                 if compare_values_to_bmc:
#                     with allure.step(f'sanity check for: {field_to_check}'):
#                         value_from_bmc = get_value_from_bmc(component_obj, field_to_check)
#                         assert actual_value == value_from_bmc, f'value of field "{field_to_check}" in show different from value returned directly from BMC.\nvalue in show: {actual_value}\nvalue from BMC: {value_from_bmc}'
#     if do_client_verify:
#         with allure.step('do client attestation verification'):
#             run_client_verify(dut, out[SpdmComponentFields.CERT_CHAIN], out[SpdmComponentFields.MEASUREMENTS])


# def get_value_from_bmc(component_obj, field_to_check):
#     return ''  # TODO: complete


# def run_client_verify(dut_engine: LinuxSshEngine, cert_chain: str, measurements: str):
#     pass  # TODO: complete once we know how


def verify_component_outputs(component_name: str, component_obj: SpdmComponent, component_is_available: bool,
                             expect_cert=None,
                             expect_measurements=None) -> Tuple[dict, dict]:
    with allure.step('show component'):
        comp_out = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()
    with allure.step(f'verify fields {SpdmConsts.Component.fields} exist'):
        ValidationTool.verify_field_exist_in_json_output(comp_out, SpdmConsts.Component.fields).verify_result()
    with allure.step('show component certificate'):
        cert_out = OutputParsingTool.parse_json_str_to_dictionary(component_obj.certificate.show()).get_returned_value()
    with allure.step(f'verify fields {SpdmConsts.Component.Certificate.fields} exist'):
        ValidationTool.verify_field_exist_in_json_output(cert_out,
                                                         SpdmConsts.Component.Certificate.fields).verify_result()
    with allure.step('show component measurements'):
        measurements_out = OutputParsingTool.parse_json_str_to_dictionary(
            component_obj.measurements.show()).get_returned_value()
    with allure.step(f'verify fields {SpdmConsts.Component.Measurements.fields} exist'):
        ValidationTool.verify_field_exist_in_json_output(measurements_out,
                                                         SpdmConsts.Component.Measurements.fields).verify_result()
        if component_is_available:
            with allure.step('check values'):
                verify_component_values(component_name, expect_cert, expect_measurements, cert_out, measurements_out)
        else:
            with allure.step('check component has NA values'):
                verify_component_values_na(component_name, cert_out, measurements_out)

    with allure.step('sanity check on values'):
        with allure.step('compare show value to value receiving directly from bmc'):
            # TODO: complete
            pass
            # value_from_bmc = get_measurements_from_bmc()
            # as
    return cert_out, measurements_out


def verify_component_values_na(component_name: str, cert_out, measurements_out):
    issues: List[str] = []

    for field, expected_value in SpdmConsts.Component.Certificate.na_values.items():
        add_issue_if(cert_out[field] != expected_value, issues,
                     f'certificate field "{field}" not as expected.\nexpected: {expected_value}\nactual: {cert_out[field]}')
    for field, expected_value in SpdmConsts.Component.Measurements.na_values.items():
        add_issue_if(measurements_out[field] != expected_value, issues,
                     f'measurements field "{field}" not as expected.\nexpected: {expected_value}\nactual: {measurements_out[field]}')
    with allure.step('assert no issues in the checks'):
        assert_no_issues(component_name, issues, 'some values are not NA')


def verify_component_values(component_name: str, expect_cert, expect_measurements, cert_out, measurements_out):
    issues: List[str] = []

    if expect_cert:
        with allure.step('check certificate value'):
            add_issue_if(cert_out[SpdmConsts.Component.Certificate.CERT_STRING] != expect_cert, issues,
                         f'certificate field "{SpdmConsts.Component.Certificate.CERT_STRING}" is not as expected.\n'
                         f'expected: {expect_cert}\nactual: {cert_out[SpdmConsts.Component.Certificate.CERT_STRING]}')
    else:
        with allure.step('check certificate is not empty'):
            add_issue_if(cert_out[SpdmConsts.Component.Certificate.CERT_STRING] == '', issues,
                         f'certificate field "{SpdmConsts.Component.Certificate.CERT_STRING}" is unexpectedly empty')

    if expect_measurements:
        if expect_measurements is NOT_EMPTY:
            with allure.step('check measurements value is not empty'):
                add_issue_if(measurements_out[SpdmConsts.Component.Measurements.SIGNED_MEASUREMENTS] == '', issues,
                             f'measurements field "{SpdmConsts.Component.Measurements.SIGNED_MEASUREMENTS}" is unexpectedly empty')
        else:
            with allure.step('check measurements value'):
                add_issue_if(
                    measurements_out[SpdmConsts.Component.Measurements.SIGNED_MEASUREMENTS] != expect_measurements,
                    issues,
                    f'measurements field "{SpdmConsts.Component.Measurements.SIGNED_MEASUREMENTS}" is not as expected.\n'
                    f'expected: {expect_measurements}\nactual: {measurements_out[SpdmConsts.Component.Measurements.SIGNED_MEASUREMENTS]}')
    else:
        with allure.step('verify measurements initial values'):
            for field, expected_value in SpdmConsts.Component.Measurements.initial_values.items():
                add_issue_if(measurements_out[field] != expected_value, issues,
                             f'measurements field "{field}" not as expected.\nexpected: {expected_value}\nactual: {measurements_out[field]}')

    with allure.step('assert no issues in the checks'):
        assert_no_issues(component_name, issues, 'some outputs are not as expected')


def add_issue_if(issue_cond: bool, issues: List[str], issue_msg: str):
    if issue_cond:
        issues.append(issue_msg)


def assert_no_issues(component_name: str, issues: List[str], err_msg_header: str = ''):
    assert not issues, f'{component_name} - {err_msg_header}\nissues found:\n\t*' + '\n\t*'.join(issues)
