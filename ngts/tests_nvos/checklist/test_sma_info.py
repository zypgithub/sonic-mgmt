import pytest
import random

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts, NvosConst
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.sma
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_show_sma_firmware(engines, devices, test_api):
    """
    Test nv show (fae) platform firmware <sma-component>
    Basic test to show that firmware sma have all necessary fields and are not N/A.

    Steps:
    1. Do nv show platform firmware.
    2. Do nv show fae platform firmware.
    3. Verify both basic and fae show commands have all necessary fields and are not N/A.

    """
    # Skip test if device has no SMA components (e.g., RosalindSwitch hardware)
    if not devices.dut.sma_components:
        pytest.skip(f"Device {devices.dut.__class__.__name__} has no SMA components - skipping SMA test")

    TestToolkit.tested_api = test_api
    platform = Platform()
    fae = Fae()
    with allure.step("Parse basic nv show platform firmware"):
        regular_output = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).get_returned_value()
    with allure.step("Parse fae nv show fae platform firmware"):
        fae_output = OutputParsingTool.parse_json_str_to_dictionary(fae.platform.firmware.show()).get_returned_value()
    with allure.step("Verify smas firmware fields"):
        with allure.independent_step("Verify smas exist in platform firmware"):
            sma_names_list = devices.dut.sma_components
            _verify_smas_firmware_fields(sma_names_list, regular_output, devices)
        with allure.independent_step("Verify smas exist in fae platform firmware"):
            sma_names_list_fae = [item for item in sma_names_list if item != PlatformConsts.FW_SMA]
            _verify_smas_firmware_fields(sma_names_list_fae, fae_output, devices)


def _verify_smas_firmware_fields(sma_names_list, output_dict, devices):
    ValidationTool.verify_field_exist_in_json_output(output_dict, sma_names_list).verify_result()

    # Get list of ERoT components from device (e.g., ['EROT-BMC', 'EROT-CPU'])
    erot_components = getattr(getattr(devices.dut, 'constants', None), 'erots', [])

    with allure.step(f"Verify none of the smas have N/A in {PlatformConsts.FW_ACTUAL}"):
        for sma_name in sma_names_list:
            sma_dict = output_dict[sma_name]

            # Check if this component name appears in any ERoT component name
            # e.g., 'BMC' appears in 'EROT-BMC' → use ERoT fields
            # e.g., 'SMA' doesn't appear in 'EROT-BMC' or 'EROT-CPU' → use basic fields
            is_erot_component = any(sma_name in erot_name for erot_name in erot_components)
            expected_fields = PlatformConsts.FW_FIELDS if is_erot_component else PlatformConsts.FW_BASIC_FIELDS

            with allure.independent_step(f"Verify {sma_name} has required fields"):
                ValidationTool.verify_field_exist_in_json_output(sma_dict, expected_fields).verify_result()

            # SMA part-number is not available via BMC/Redfish API - skip validation for SMA
            # Only check actual-firmware for SMA components
            fw_fields_to_check = [PlatformConsts.FW_ACTUAL]

            for fw_field in fw_fields_to_check:
                with allure.independent_step(f"Check that {fw_field} in {sma_name} is not {NvosConst.NOT_AVAILABLE}"):
                    ValidationTool.verify_field_value_in_output(sma_dict, fw_field,
                                                                NvosConst.NOT_AVAILABLE,
                                                                should_be_equal=False).verify_result()
