import logging
import pytest

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import OutputFormat, PlatformConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import NvosConst, SystemConsts

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.cumulus
@pytest.mark.simx
@pytest.mark.nvos_ci
@pytest.mark.nvos_chipsim_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_platform(engines, test_api, devices):
    """
    Validates the output of nv show platform.
    The OpenAPI test checks the JSON output while the NVUE test checks the auto output.
    Test flow:
        1. nv show platform (json output for OpenAPI test, auto output for NVUE test)
        2. Parse output to dict
        3. Validate all keys (field names) exist and there are no extra keys
        4. Validate all values are correct
    """
    TestToolkit.tested_api = test_api
    with allure.step("Create system object"):
        platform = Platform()

    output_format = OutputFormat.auto if test_api == ApiType.NVUE else OutputFormat.json
    output = OutputParsingTool.parse_show_output_to_dict(platform.show(output_format=output_format),
                                                         output_format=output_format).get_returned_value()

    #   WA to support Q3200_RA and QM3400 for Crocodile product name
    if devices.dut.asic_type == NvosConst.QTM3 and SystemConsts.PRODUCT_NAME in output.keys() and \
       output[SystemConsts.PRODUCT_NAME] in "Q3200_RA":
        output[SystemConsts.PRODUCT_NAME] = devices.dut.show_platform_output[SystemConsts.PRODUCT_NAME]

    ValidationTool.validate_output_of_show(output, TestToolkit.devices.dut.show_platform_output).verify_result()


@pytest.mark.platform
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_platform_chassis_location(engines, test_api, devices):
    """
    Validates the output of nv show platform chassis-location.
    The OpenAPI test checks the JSON output while the NVUE test checks the auto output.
    Runs only on Juliet setups. The test assumes the setup is standalone.
    Test flow:
        1. nv show platform chassis-location
        2. Parse output to dict
        3. Validate all keys (field names) exist and there are no extra keys
        4. Validate all values are correct
    """
    with allure.step("Create system object"):
        platform = Platform()

    if devices.dut.is_standalone:
        with allure.step("verifying output for standalone switch"):
            output_dict = OutputParsingTool.parse_show_output_to_dict(platform.chassis_location.show()).get_returned_value()
            ValidationTool.compare_dictionaries(output_dict, PlatformConsts.CHASSIS_LOCATION_STANDALONE_DICT).verify_result()
    else:
        with allure.step("verifying output for non - standalone switch"):
            output_dict = OutputParsingTool.parse_show_output_to_dict(platform.chassis_location.show()).get_returned_value()
            ValidationTool.validate_output_of_show(output_dict, TestToolkit.devices.dut.show_platform_chassis_location_output).verify_result()
