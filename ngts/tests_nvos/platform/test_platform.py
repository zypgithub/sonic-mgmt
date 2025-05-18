import logging
import pytest

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import OutputFormat, PlatformConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import NvosConst, SystemConsts

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.cumulus
@pytest.mark.simx
@pytest.mark.nvos_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_platform(engines, test_api, devices, nv_command):
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
    output = OutputParsingTool.parse_show_output_to_dict(nv_command.platform.show()).get_returned_value()
    ValidationTool.validate_output_of_show(output, TestToolkit.devices.dut.show_platform_output).verify_result()
