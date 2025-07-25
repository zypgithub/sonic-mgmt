import logging
import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.ValidationTool import ValidationTool, ExpectedString
from ngts.nvos_constants.constants_nvos import CumulusConsts
from ngts.nvos_tools.platform.Platform import Platform

logger = logging.getLogger()


@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_asic_default_fields_values(test_api, devices):
    """
    Validate ASIC default fields values.
        Test flow:
            1. Validate nv show platform asic output
            2. Validate nv show platform asic ASIC output
    """
    TestToolkit.tested_api = test_api
    platform = Platform()

    asic_temperature_fields = {}
    for field in CumulusConsts.PLATFORM_ASIC_TEMPERATURE_FIELDS:
        asic_temperature_fields[field] = ExpectedString(regex=".*")

    with allure.step("Check nv show platform asic"):
        asic_output = OutputParsingTool.parse_json_str_to_dictionary(platform.asic.show(output_format='json')).get_returned_value()

        with allure.step("Verify default fields"):
            ValidationTool.verify_field_exist_in_json_output(asic_output, devices.dut.asic_numbers).verify_result()

        with allure.step("Check only positive integers inside"):
            for asic, values in asic_output.items():
                assert isinstance(values, dict), f"Error: ASIC value in {asic} is not a dict"

    with allure.step("Check nv show platform asic ASIC"):
        for asic_num in devices.dut.asic_numbers:
            asic_output = OutputParsingTool.parse_json_str_to_dictionary(platform.asic.show(asic_num, output_format='json')).get_returned_value()

            with allure.step("Verify default fields"):
                ValidationTool.verify_field_exist_in_json_output(asic_output,
                                                                 CumulusConsts.PLATFORM_ASIC_OUTPUT_FIELDS.keys()).verify_result()

            with allure.step("Validate temperature fields values"):
                ValidationTool.validate_output_of_show(
                    devices.dut.normalize_platform_asic_temperature_output(asic_output.get('temperature', {})),
                    asic_temperature_fields,
                ).verify_result()


@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_asic_temperature_show(devices, test_api):
    """
    Test nv show platform asic <asic-id> temperature command for ETH/Cumulus devices.

    Validates temperature monitoring for each ASIC including:
        - Temperature fields exist (state, current, min, max, crit)
        - Temperature state is valid (ok, high, low, critical)
        - Temperature values are within expected ranges
    """
    TestToolkit.tested_api = test_api
    platform = Platform()

    asic_temperature_fields_with_ranges = _asic_temperature_fields_with_ranges()

    for asic_id in devices.dut.asic_numbers:
        with allure.step(f"Validate temperature data for {asic_id}"):
            with allure.step(f"Get temperature output for {asic_id}"):
                asic_output = OutputParsingTool.parse_json_str_to_dictionary(
                    platform.asic.asic_id[asic_id].temperature.show(output_format='json')
                ).get_returned_value()

            with allure.step("Validate required temperature fields exist"):
                ValidationTool.verify_field_exist_in_json_output(asic_output, CumulusConsts.PLATFORM_ASIC_TEMPERATURE_FIELDS).verify_result()

            with allure.step("Validate temperature state and value ranges"):
                ValidationTool.validate_output_of_show(
                    devices.dut.normalize_platform_asic_temperature_output(asic_output),
                    asic_temperature_fields_with_ranges,
                ).verify_result()


@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_asic_resource_show(devices, test_api):
    """
    Test nv show platform asic <asic-id> resource command for ETH/Cumulus devices.

    Validates ASIC resource usage including:
        - Global and ACL resource sections exist
        - Resource data structure is valid (dictionary format)
        - All required resource sections are present
    """
    TestToolkit.tested_api = test_api
    platform = Platform()

    for asic_id in devices.dut.asic_numbers:
        with allure.step(f"Validate resource data for {asic_id}"):
            with allure.step(f"Get resource output for {asic_id}"):
                resource_output = OutputParsingTool.parse_json_str_to_dictionary(
                    platform.asic.asic_id[asic_id].show('resource', output_format='json')
                ).get_returned_value()

            with allure.step("Validate required resource sections exist"):
                ValidationTool.verify_field_exist_in_json_output(
                    resource_output, CumulusConsts.PLATFORM_ASIC_RESOURCE_SECTIONS
                ).verify_result()

            with allure.step("Validate resource data structure"):
                for section in CumulusConsts.PLATFORM_ASIC_RESOURCE_SECTIONS:
                    assert isinstance(resource_output[section], dict), (
                        f"Section '{section}' is not a dictionary for ASIC {asic_id}"
                    )


@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_asic_resource_acl_show(devices, test_api):
    """
    Test nv show platform asic <asic-id> resource acl command for ETH/Cumulus devices.

    Validates ACL (Access Control List) resource usage for each ASIC:
        - ACL output structure is valid
        - At least one ACL table exists
        - Each ACL table has required fields (acl-18b, acl-36b, acl-54b, rule-count)
        - All ACL fields are integers
    """
    TestToolkit.tested_api = test_api
    platform = Platform()

    for asic_id in devices.dut.asic_numbers:
        with allure.step(f"Validate ACL resource data for {asic_id}"):
            with allure.step(f"Get ACL resource output for {asic_id}"):
                acl_output = OutputParsingTool.parse_json_str_to_dictionary(
                    platform.asic.asic_id[asic_id].show('resource acl', output_format='json')
                ).get_returned_value()

            with allure.step("Validate ACL output structure"):
                assert isinstance(acl_output, dict), f"ACL output is not a dictionary for ASIC {asic_id}"
                assert len(acl_output) > 0, f"No ACL tables found for ASIC {asic_id}"

            with allure.step("Validate each ACL table structure and fields"):
                for table_name, table_data in acl_output.items():
                    assert isinstance(table_data, dict), (
                        f"ACL table '{table_name}' is not a dictionary for ASIC {asic_id}"
                    )
                    ValidationTool.verify_field_exist_in_json_output(
                        table_data, CumulusConsts.PLATFORM_ASIC_RESOURCE_ACL_TABLE_FIELDS
                    ).verify_result()
                    for field in CumulusConsts.PLATFORM_ASIC_RESOURCE_ACL_TABLE_FIELDS:
                        assert isinstance(table_data[field], int), (
                            f"Field '{field}' is not an integer in ACL table '{table_name}' for ASIC {asic_id}"
                        )


@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_asic_resource_global_show(devices, test_api):
    """
    Test nv show platform asic <asic-id> resource global command for ETH/Cumulus devices.

    Validates global resource usage for each ASIC:
        - Global output structure is valid
        - At least one global resource exists
        - Each resource has required 'used' field (integer)
        - Optional fields validated if present (max, percentage)
    """
    TestToolkit.tested_api = test_api
    platform = Platform()

    for asic_id in devices.dut.asic_numbers:
        with allure.step(f"Validate global resource data for {asic_id}"):
            with allure.step(f"Get global resource output for {asic_id}"):
                global_output = OutputParsingTool.parse_json_str_to_dictionary(
                    platform.asic.asic_id[asic_id].show('resource global', output_format='json')
                ).get_returned_value()

            with allure.step("Validate global output structure"):
                assert isinstance(global_output, dict), f"Global output is not a dictionary for ASIC {asic_id}"
                assert len(global_output) > 0, f"No global resources found for ASIC {asic_id}"

            with allure.step("Validate each resource entry structure and fields"):
                for resource_name, resource_data in global_output.items():
                    assert isinstance(resource_data, dict), (
                        f"Resource '{resource_name}' is not a dictionary for ASIC {asic_id}"
                    )
                    ValidationTool.verify_field_exist_in_json_output(
                        resource_data, CumulusConsts.PLATFORM_ASIC_RESOURCE_GLOBAL_REQUIRED_FIELDS
                    ).verify_result()
                    assert isinstance(resource_data['used'], int), (
                        f"Field 'used' is not an integer in resource '{resource_name}' for ASIC {asic_id}"
                    )
                    for field in CumulusConsts.PLATFORM_ASIC_RESOURCE_GLOBAL_OPTIONAL_FIELDS:
                        if field in resource_data:
                            if field == 'percentage':
                                assert isinstance(resource_data[field], (int, float)), (
                                    f"Field '{field}' is not a number in resource '{resource_name}' for ASIC {asic_id}"
                                )
                            else:
                                assert isinstance(resource_data[field], int), (
                                    f"Field '{field}' is not an integer in resource '{resource_name}' for ASIC {asic_id}"
                                )


def _asic_temperature_fields_with_ranges():
    """Build temperature validation dict from CumulusConsts range constants."""
    states_regex = "^(%s)$" % "|".join(CumulusConsts.PLATFORM_ASIC_TEMPERATURE_STATES)
    return {
        'state': ExpectedString(regex=states_regex),
        'current': ExpectedString(
            range_min=CumulusConsts.PLATFORM_ASIC_TEMP_CURRENT_MIN,
            range_max=CumulusConsts.PLATFORM_ASIC_TEMP_CURRENT_MAX,
        ),
        'min': ExpectedString(
            range_min=CumulusConsts.PLATFORM_ASIC_TEMP_MIN_MIN,
            range_max=CumulusConsts.PLATFORM_ASIC_TEMP_MIN_MAX,
        ),
        'max': ExpectedString(
            range_min=CumulusConsts.PLATFORM_ASIC_TEMP_MAX_MIN,
            range_max=CumulusConsts.PLATFORM_ASIC_TEMP_MAX_MAX,
        ),
        'crit': ExpectedString(
            range_min=CumulusConsts.PLATFORM_ASIC_TEMP_CRIT_MIN,
            range_max=CumulusConsts.PLATFORM_ASIC_TEMP_CRIT_MAX,
        ),
    }
