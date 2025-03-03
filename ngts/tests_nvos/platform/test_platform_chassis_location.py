import copy
import logging
import pytest

from ngts.nvos_tools.Devices.IbDevice import JulietAriel
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import ChassisLocationConsts
from ngts.nvos_constants.constants_nvos import ApiType

logger = logging.getLogger()


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

    output_dict = OutputParsingTool.parse_show_output_to_dict(platform.chassis_location.show()).get_returned_value()

    expected_standalone_dict = copy.deepcopy(ChassisLocationConsts.EXPECTED_STANDALONE_DICT)

    # Check if devices.dut is an instance of JulietAriel and update the topology-id (https://redmine.mellanox.com/issues/4275347)
    if isinstance(devices.dut, JulietAriel):
        expected_standalone_dict[ChassisLocationConsts.TOPO_ID] = ChassisLocationConsts.OBERON_36

    if output_dict[ChassisLocationConsts.CHAS_SN] == ChassisLocationConsts.NA:
        with allure.step("verifying output for standalone switch"):
            ValidationTool.compare_dictionaries(output_dict, expected_standalone_dict).verify_result()
    else:
        with allure.step("verifying output for non - standalone switch"):
            ValidationTool.validate_output_of_show(output_dict,
                                                   devices.dut.show_platform_chassis_location_output).verify_result()