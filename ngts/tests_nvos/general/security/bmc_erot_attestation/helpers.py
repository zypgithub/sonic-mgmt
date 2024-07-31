import logging
import random
from typing import List, Tuple

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.TpmTool import TpmTool
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


def verify_component_outputs(component_name: str, component_obj: SpdmComponent, component_is_available: bool,
                             expect_cert=None,
                             expect_measurements=None) -> Tuple[dict, dict]:
    with allure.step('show component'):
        comp_out = OutputParsingTool.parse_json_str_to_dictionary(component_obj.show()).get_returned_value()
    with allure.step(f'verify fields {SpdmConsts.Component.fields} exist'):
        ValidationTool.verify_field_exist_in_json_output(comp_out, SpdmConsts.Component.fields).verify_result()
    with allure.step('show component certificate'):
        cert_out = OutputParsingTool.parse_json_str_to_dictionary(
            component_obj.certificates.show()).get_returned_value()
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

    if component_is_available:
        with allure.step('sanity check on values'):
            verify_cert_data_same_as_directly_from_bmc(cert_out)
            verify_measurements_data_same_as_directly_from_bmc(measurements_out)

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
    assert not issues, f'{component_name} - {err_msg_header}\nissues found:\n\t* ' + '\n\t* '.join(issues)


def verify_cert_data_same_as_directly_from_bmc(nv_cert: dict):
    dut_engine: LinuxSshEngine = TestToolkit.engines.dut
    with allure.step('compare certificates data from nv show to data received directly from BMC'):
        with allure.step('get nvos password to bmc from tpm'):
            tpm = TpmTool(dut_engine)
            bmc_password = tpm.get_tpm_cipher()[:11] + 'A!'
        with allure.step('get certificates data directly from bmc'):
            output_file = '/tmp/bmc-certs'
            dut_engine.run_cmd(f'curl -k -u admin:{bmc_password} -H "Content-Type: application/json" -X GET https://10.0.1.1/redfish/v1/Chassis/MGX_ERoT_BMC_0/Certificates/CertChain > {output_file}')
            dut_engine.run_cmd(f'echo "" >> {output_file}')
            bmc_cert_file_content = dut_engine.run_cmd(f'cat {output_file}')
            bmc_cert = OutputParsingTool.parse_json_str_to_dictionary(bmc_cert_file_content).get_returned_value()
            bmc_cert = {k: v for k, v in bmc_cert.items() if '@odata' not in k}
            dut_engine.run_cmd(f'rm -f {output_file}')
        with allure.step('compare the data of nv and bmc'):
            ValidationTool.compare_dictionaries(nv_cert, bmc_cert).verify_result()


def verify_measurements_data_same_as_directly_from_bmc(nv_measurements: dict):
    dut_engine: LinuxSshEngine = TestToolkit.engines.dut
    with allure.step('compare measurements data from nv show to data received directly from BMC'):
        with allure.step('get nvos password to bmc from tpm'):
            tpm = TpmTool(dut_engine)
            bmc_password = tpm.get_tpm_cipher()[:11] + 'A!'
        with allure.step('get measurements data directly from bmc'):
            output_file = '/tmp/bmc-measurements'
            dut_engine.run_cmd(f'curl -k -u admin:{bmc_password} -H "Content-Type: application/json" -X GET https://10.0.1.1/redfish/v1/ComponentIntegrity/MGX_ERoT_BMC_0/Actions/ComponentIntegrity.SPDMGetSignedMeasurements/data > {output_file}')
            dut_engine.run_cmd(f'echo "" >> {output_file}')
            bmc_measurements_file_content = dut_engine.run_cmd(f'cat {output_file}')
            bmc_measurements = OutputParsingTool.parse_json_str_to_dictionary(bmc_measurements_file_content).get_returned_value()
            bmc_measurements = {k: v for k, v in bmc_measurements.items() if '@odata' not in k}
            dut_engine.run_cmd(f'rm -f {output_file}')
        with allure.step('compare the data of nv and bmc'):
            ValidationTool.compare_dictionaries(nv_measurements, bmc_measurements).verify_result()

# def run_client_verify(dut_engine: LinuxSshEngine, cert_chain: str, measurements: str):
#     pass  # TODO: complete once we know how
