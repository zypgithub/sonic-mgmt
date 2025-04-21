import logging
import pytest

from ngts.nvos_tools.Devices.IbDevice import JulietSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import PlatformConsts, NvosConst, ImageConsts
from ngts.nvos_constants.constants_nvos import ApiType, OutputFormat
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.cumulus
@pytest.mark.nvos_ci
@pytest.mark.nvl_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(2 * MINUTE, func_only=True)
def test_show_platform_firmware(engines, devices, test_api, output_format):
    """Tests nv show platform firmware"""
    TestToolkit.tested_api = test_api
    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("Test output of nv show platform firmware"):
        firmware_items = devices.dut.constants.firmware
        if devices.dut.constants.erots:
            firmware_items = devices.dut.constants.firmware + devices.dut.constants.erots + ['EROT']
        validate_firmware_keys(platform, firmware_items, engines.dut)

    with allure.step("Test specific firmware components"):
        validate_firmware_components(platform, firmware_items, engines.dut)


def validate_firmware_keys(platform, firmware_items, dut_engine):
    all_output = OutputParsingTool.parse_show_output_to_dict(
        platform.firmware.show(dut_engine=dut_engine, output_format=OutputFormat.json),
        output_format=OutputFormat.json, field_name_dict=PlatformConsts.FW_FIELD_NAME_DICT).get_returned_value()
    ValidationTool.validate_set_equal(all_output.keys(), firmware_items)


def validate_firmware_components(platform, firmware_items, dut_engine):
    errors = {}
    for component in firmware_items:
        try:
            with allure.step(f"Test output of nv show platform firmware {component}"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    platform.firmware.show(component, dut_engine=dut_engine, output_format=OutputFormat.json),
                    output_format=OutputFormat.json, field_name_dict=PlatformConsts.FW_FIELD_NAME_DICT).get_returned_value()
                if component != 'transceiver':  # Transceiver firmware shows N/A when not specifying a transceiver
                    assert output[PlatformConsts.FW_ACTUAL] not in {'', NvosConst.NOT_AVAILABLE}, \
                        f"{component}.{PlatformConsts.FW_ACTUAL} is empty or N/A"
                with allure.step(f"Compare {component} output against {component} entry in general output"):
                    all_output = OutputParsingTool.parse_show_output_to_dict(
                        platform.firmware.show(dut_engine=dut_engine, output_format=OutputFormat.json),
                        output_format=OutputFormat.json, field_name_dict=PlatformConsts.FW_FIELD_NAME_DICT).get_returned_value()
                    diff = ValidationTool.get_dictionaries_diff(all_output[component], output)
                    assert not diff, (
                        f"The following fields are missing in 'nv show platform firmware {component}' or have a "
                        f"different value compared to 'nv show platform firmware': {diff}"
                    )
        except Exception as e:
            errors[component] = e

    assert not errors, f"Test failed for components {list(errors.keys())}. Errors were:\n" + \
        '\n\n'.join(
        f"{component}:\n{type(error).__name__}: {error}" for component, error in errors.items())
