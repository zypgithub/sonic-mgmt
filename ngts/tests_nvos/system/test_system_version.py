import logging
import random
import pytest

logger = logging.getLogger()
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.version
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_version(test_api, engines, devices, nv_command):
    """
    Run show system version command and verify version values
        Test flow
        1. run show system version
        2. validate values in db
    """
    TestToolkit.tested_api = test_api

    with allure.step('Run show system command and verify that each field has a value'):
        version_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.version.show()).get_returned_value()
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
            version_output, nv_command.system.get_expected_fields(devices.dut, 'version')).verify_result()


@pytest.mark.version
@pytest.mark.system
def test_show_system_version_image(test_api, engines, devices, nv_command):
    """
    Test 'nv show system version image' command output
    """
    with allure.step("Run show command to view system version image"):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.version.image.show()).get_returned_value()
        expected_fields = [SystemConsts.VERSION_BUILD_ID, SystemConsts.VERSION_BUILD_DATE]
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output_dictionary, expected_fields).verify_result()


@pytest.mark.version
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_version_packages(engines, test_api, output_format, nv_command):
    """nv show system version packages"""
    TestToolkit.tested_api = test_api

    with allure.step("Check show software output"):
        output = OutputParsingTool.parse_show_output_to_dict(nv_command.system.version.packages.show(output_format=output_format),
                                                             output_format=output_format).get_returned_value()
        assert output, f"'nv show system version packages' returned empty output"
        if test_api == ApiType.OPENAPI:
            installed_str = "installed"
            ValidationTool.validate_set_equal(output.keys(), {installed_str}).verify_result()
            output = output[installed_str]
        ValidationTool.validate_set_equal(tuple(output.values())[0].keys(), SystemConsts.SW_FIELD_NAMES
                                          ).verify_result()


@pytest.mark.version
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_version_packages_installed(engines, test_api, output_format, nv_command):
    """`nv show system version packages installed` and `nv show system version packages installed <software-id>`"""
    TestToolkit.tested_api = test_api

    with allure.step("Check show software installed output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            nv_command.system.version.packages.installed.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert output, f"'nv show system version packages installed' returned empty output"
        ValidationTool.validate_set_equal(tuple(output.values())[0].keys(), SystemConsts.SW_FIELD_NAMES
                                          ).verify_result()

    with allure.step("Verify output for a specific SW"):
        random_software = random.choice(tuple(output.keys()))
        logging.info(f"Verify fields for {random_software}")
        specific_output = OutputParsingTool.parse_show_output_to_dict(
            nv_command.system.version.packages.installed.show(op_param=random_software, output_format=output_format),
            output_format=output_format).get_returned_value()
        ValidationTool.validate_set_equal(specific_output.keys(), SystemConsts.SW_FIELD_NAMES).verify_result()
