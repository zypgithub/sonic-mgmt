import logging
import pytest

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import PlatformConsts, NvosConst, ImageConsts
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.cumulus
@pytest.mark.nvos_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_platform_firmware(engines, devices, test_api, output_format):
    """Tests nv show platform firmware"""
    TestToolkit.tested_api = test_api
    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("Test output of nv show platform firmware"):
        firmware_items = devices.dut.constants.firmware
        all_output = OutputParsingTool.parse_show_output_to_dict(
            platform.firmware.show(output_format=output_format),
            output_format=output_format, field_name_dict=PlatformConsts.FW_FIELD_NAME_DICT).get_returned_value()
        ValidationTool.validate_set_equal(all_output.keys(), firmware_items)

    with allure.step("Test specific firmware components"):
        errors = {}
        for component in firmware_items:
            try:
                with allure.step(f"Test output of nv show platform firmware {component}"):
                    output = OutputParsingTool.parse_show_output_to_dict(
                        platform.firmware.show(component, output_format=output_format),
                        output_format=output_format, field_name_dict=PlatformConsts.FW_FIELD_NAME_DICT).get_returned_value()
                    assert output[PlatformConsts.FW_ACTUAL] not in {'', NvosConst.NOT_AVAILABLE}, \
                        f"{component}.{PlatformConsts.FW_ACTUAL} is empty or N/A"
                    with allure.step(f"Compare {component} output against {component} entry in general output"):
                        diff = ValidationTool.get_dictionaries_diff(all_output[component], output)
                        assert not diff, (
                            f"The following fields are missing in 'nv show platform firmware {component}' or have a "
                            f"different value compared to 'nv show platform firmware': {diff}"
                        )
            except Exception as e:
                errors[component] = e

        assert not errors, f"Test failed for components {list(errors.keys())}. Errors were:\n" + \
            '\n\n'.join(f"{component}:\n{type(error).__name__}: {error}" for component, error in errors.items())
