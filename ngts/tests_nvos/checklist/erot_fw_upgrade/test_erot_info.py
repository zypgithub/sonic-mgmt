import pytest

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts, NvosConst
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.erot
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_erot_firmware(engines, devices, test_api):
    """
    Test nv show (fae) platform firmware <erot-component>
    Basic test to show that firmware erot have all necessary fields and are not N/A.

    Steps:
    1. Do nv show platform firmware.
    2. Do nv show fae platform firmware.
    3. Verify both basic and fae show commands have all necessary fields and are not N/A.

    """
    TestToolkit.tested_api = test_api
    platform = Platform()
    fae = Fae()
    with allure.step("Parse basic nv show platform firmware"):
        regular_output = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).get_returned_value()
    with allure.step("Parse fae nv show fae platform firmware"):
        fae_output = OutputParsingTool.parse_json_str_to_dictionary(fae.platform.firmware.show()).get_returned_value()
    erots_names_list = devices.dut.constants.erots[:]
    with allure.step("Verify erots firmware fields"):
        with allure.independent_step("Verify erots exist in platform firmware"):
            _verify_erots_firmware_fields(erots_names_list, regular_output)
        with allure.independent_step("Verify erots exist in fae platform firmware"):
            _verify_erots_firmware_fields(erots_names_list, fae_output)


def _verify_erots_firmware_fields(erots_names_list, output_dict):
    ValidationTool.verify_field_exist_in_json_output(output_dict, erots_names_list).verify_result()
    with allure.step(f"Verify none of the erots have N/A in {PlatformConsts.FW_ACTUAL}"):
        for erot_name in erots_names_list:
            with allure.independent_step(f"Verify {erot_name} has required fields"):
                erot_dict = output_dict[erot_name]
                ValidationTool.verify_field_exist_in_json_output(erot_dict, PlatformConsts.FW_FIELDS).verify_result()
            # TODO: Currently active and inactive non-supported
            fw_fields_to_check = [PlatformConsts.FW_ACTUAL, PlatformConsts.FW_BACKGROUND_COPY_STATUS,
                                  PlatformConsts.FW_DEBUG_TOKEN_STATUS]
            for fw_field in fw_fields_to_check:
                with allure.independent_step(f"Check that {fw_field} in {erot_name} is not {NvosConst.NOT_AVAILABLE}"):
                    ValidationTool.verify_field_value_in_output(erot_dict, fw_field,
                                                                NvosConst.NOT_AVAILABLE,
                                                                should_be_equal=False).verify_result()
