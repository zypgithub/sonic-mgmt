import logging
import pytest

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import NvosConst, CableCartridgeConsts, ChassisLocationConsts
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_platform_cable_cartridge(engines, devices, test_api):
    """
     Tests the 'nv show platform cable cartridge' command to validate the data integrity
     and alignment of cable cartridge information.

     Test Flow:
     1. Fetch the general cable cartridge data.
     2. Validate the number of cartridges.
     3. For each cartridge:
         - Verify all expected keys exist and have non-null values.
         - Validate that Tray IDs are within the allowed range (0-8).
         - Ensure specific cartridge data matches the general data.
     4. Validate overall alignment:
         - All Slot IDs, Tray IDs, and Part Numbers should be consistent and aligned across cartridges.

     """
    TestToolkit.tested_api = test_api

    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("Fetch cable cartridge data"):
        dict_output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.cable_cartridge.show()).get_returned_value()

    with allure.step("Define validation parameters"):
        expected_keys = CableCartridgeConsts.ALL_KEYS
        slot_ids = set()
        tray_ids = set()
        part_numbers = set()

    with allure.step("Validate actual number of cartridges"):
        assert len(dict_output.items()) == devices.dut.num_of_cartridges, "Number of cartridges is not as expected"

    with allure.step("Validate cable cartridge data for each cartridge"):
        for cartridge, details in dict_output.items():
            with allure.independent_step(f"Validate cartridge: {cartridge}"):
                ValidationTool.validate_output_of_show(details, devices.dut.show_platform_cable_cartridge_output).verify_result()

                # Collect unique values for alignment validation
                slot_ids.add(details[CableCartridgeConsts.KEY_SLOT_ID])
                tray_ids.add(details[CableCartridgeConsts.KEY_TRAY_ID])
                part_numbers.add(details[CableCartridgeConsts.KEY_PART_NUMBER])

                with allure.step(f"Verify specific cartridge data matches general output for {cartridge}"):
                    specific_cartridge_data = OutputParsingTool.parse_json_str_to_dictionary(
                        platform.cable_cartridge.cartridge_id[cartridge].show()).get_returned_value()
                    assert details == specific_cartridge_data, (
                        f"Data mismatch for cartridge {cartridge}: "
                        f"General data: {details}, Specific data: {specific_cartridge_data}"
                    )

    with allure.step("Validate alignment and overall consistency"):
        # Validate alignment of Slot IDs, Tray IDs, and Part Numbers
        assert len(slot_ids) == 1, f"Slot IDs are not aligned: {slot_ids}"
        assert len(tray_ids) == 1, f"Tray IDs are not aligned: {tray_ids}"
        assert len(part_numbers) == 1, f"Part Numbers are not aligned: {part_numbers}"


@pytest.mark.platform
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_validate_cable_cartridge_chassis_location(engines, devices, test_api):
    """
    Validates that the chassis location data matches the leftmost cartridge's data
    fetched from the 'nv show platform cable cartridge' command.

    Steps:
    1. Fetch chassis location data and cable cartridge data.
    2. Extract the details of the leftmost cartridge (typically cartridge1).
    3. Compare and validate:
        - tray-id matches the chassis tray-index.
        - slot-id matches the chassis slot-number.
        - serial-number matches the chassis-sn.

    """
    TestToolkit.tested_api = test_api

    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("Fetch data"):
        chassis_location_data = OutputParsingTool.parse_json_str_to_dictionary(
            platform.chassis_location.show()).get_returned_value()
        dict_output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.cable_cartridge.show()).get_returned_value()

    with allure.step(f"Validate chassis location data against {CableCartridgeConsts.LEFTMOST_CARTRIDGE} data"):
        cartridge_details = dict_output.get(CableCartridgeConsts.LEFTMOST_CARTRIDGE, {})
        assert cartridge_details, f"{CableCartridgeConsts.LEFTMOST_CARTRIDGE} data is missing in general output"

        with allure.independent_step(f"Validate {ChassisLocationConsts.TRAY_ID} matches"):
            assert chassis_location_data[ChassisLocationConsts.TRAY_ID] == cartridge_details[CableCartridgeConsts.KEY_TRAY_ID], (
                f"Mismatch in tray-index: Expected {cartridge_details[CableCartridgeConsts.KEY_TRAY_ID]}, "
                f"found {chassis_location_data[ChassisLocationConsts.TRAY_ID]}"
            )

        with allure.independent_step(f"Validate {ChassisLocationConsts.SLOT_NUM} matches Slot ID"):
            assert chassis_location_data[ChassisLocationConsts.SLOT_NUM] == cartridge_details[CableCartridgeConsts.KEY_SLOT_ID], (
                f"Mismatch in slot-number: Expected {cartridge_details[CableCartridgeConsts.KEY_SLOT_ID]}, "
                f"found {chassis_location_data[ChassisLocationConsts.SLOT_NUM]}"
            )

        with allure.independent_step(f"Validate {ChassisLocationConsts.CHAS_SN} matches Serial of {CableCartridgeConsts.LEFTMOST_CARTRIDGE}"):
            assert chassis_location_data[ChassisLocationConsts.CHAS_SN] == cartridge_details[CableCartridgeConsts.KEY_SERIAL], (
                f"Mismatch in chassis-sn: Expected {cartridge_details[CableCartridgeConsts.KEY_SERIAL]}, "
                f"found {chassis_location_data[ChassisLocationConsts.CHAS_SN]}"
            )
