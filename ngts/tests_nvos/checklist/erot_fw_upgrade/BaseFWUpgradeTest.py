import logging
import time
import random
from typing import Dict

from ngts.nvos_tools.platform.Platform import Platform
from ngts.tests_nvos.constants import MINUTE, FW_COMPONENT_EROT
from ngts.tools.test_utils import allure_utils as allure

from ngts.nvos_constants.constants_nvos import PlatformConsts, NvosConst
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.ErotComponent import ErotComponent
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.Fae import Fae

logger = logging.getLogger()


def verify_installation(erot_names, expected_version):
    platform = Platform()
    fae = Fae()
    fw_fields_to_check = [PlatformConsts.FW_ACTUAL, PlatformConsts.FW_BACKGROUND_COPY_STATUS,
                          PlatformConsts.FW_DEBUG_TOKEN_STATUS, PlatformConsts.FW_SLOT_STATUS_INACTIVE,
                          PlatformConsts.FW_SLOT_STATUS_ACTIVE, PlatformConsts.FW_AP_BOOT_STATUS]
    with allure.step(f"Asserting install was successful"):
        for erot_name in erot_names:
            firmware_shown: Dict[str, str] = OutputParsingTool.parse_json_str_to_dictionary(
                fae.platform.firmware.erot_id[erot_name].show()).get_returned_value()
            with allure.independent_step(f"Check actual firmware version matches expected {expected_version}"):
                actual_firmware = firmware_shown[PlatformConsts.FW_ACTUAL]
                assert actual_firmware == expected_version, \
                    f"Expected version: {expected_version}. Actual version: {actual_firmware}"
            with allure.independent_step(f"Verifying {erot_name} fields are not N/A"):
                for fw_field_name in fw_fields_to_check:
                    with allure.independent_step(f"Assert {fw_field_name} is not N/A for {erot_name}"):
                        field_state = firmware_shown[fw_field_name]
                        assert field_state != NvosConst.NOT_AVAILABLE, f"The {fw_field_name} should not be N/A"


def get_active_inactive_slots(erot_name):
    platform = Platform()
    with allure.step("Get active and inactive slot values"):
        firmware_shown: Dict[str, str] = OutputParsingTool.parse_json_str_to_dictionary(
            platform.firmware.erot_id[erot_name].show()).get_returned_value()
        active_field = PlatformConsts.FW_SLOT_STATUS_ACTIVE
        inactive_field = PlatformConsts.FW_SLOT_STATUS_INACTIVE
        return firmware_shown[active_field], firmware_shown[inactive_field]


def fetch_and_install_erot_image(fw_component: ErotComponent, path, version, filename, test_name: str = '') -> ResultObj:
    with allure.step(f"Fetching image {version} from {filename}"):
        fw_component.action_fetch(path).verify_result()

    fw_component.files.verify_show_files_output(expected_files=[filename])

    fetched_image_file = fw_component.files.file_name[filename]
    with allure.step(f"Installing image {version} from {filename} with reboot"):
        res_obj, _ = OperationTime.save_duration('install erot', '', test_name, fetched_image_file.action_file_install_with_reboot)
        res_obj.verify_result()
        return res_obj


def verify_active_inactive_slots(erot_name, active_slot, inactive_slot):
    platform = Platform()
    with allure.step(f"Verifying active and inactive slots for {erot_name}"):
        firmware_shown: Dict[str, str] = OutputParsingTool.parse_json_str_to_dictionary(
            platform.firmware.erot_id[erot_name].show()).get_returned_value()
        active_field = PlatformConsts.FW_SLOT_STATUS_ACTIVE
        inactive_field = PlatformConsts.FW_SLOT_STATUS_INACTIVE
        with allure.independent_step(f"Check active slot for {erot_name}"):
            assert firmware_shown[
                active_field] == inactive_slot, "The active slot should have changed to inactive value"
        with allure.independent_step(f"Check inactive slot for {erot_name}"):
            assert firmware_shown[
                inactive_field] == active_slot, "The inactive slot should have changed to active value"


class BaseFWUpgradeTest:

    def __init__(self, firmware_component: ErotComponent):
        self._firmware_component = firmware_component

    def test(self, engines, switch, topology_obj, test_api, test_name: str = ''):
        TestToolkit.tested_api = test_api
        fw_component = self._firmware_component
        prev_path, prev_filename, prev_version = BmcTool.get_fw_component_version_previous(FW_COMPONENT_EROT)
        curr_path, curr_filename, curr_version = BmcTool.get_fw_component_version_latest(FW_COMPONENT_EROT)
        fw_components_names = switch.constants.erots[:]
        component_name = random.choice(fw_components_names)
        try:
            active_slot, inactive_slot = get_active_inactive_slots(component_name)

            res_obj = fetch_and_install_erot_image(fw_component, prev_path, prev_version, prev_filename, test_name)
            with allure.step(f"verify operation time for install erot {prev_version!r} (duration: {res_obj.duration:.2f})"):
                OperationTime.verify_operation_time(res_obj.duration, 'install erot').verify_result()

            with allure.step(f"Sleep for {MINUTE} so the bg-copy will finish"):
                time.sleep(MINUTE)
            with allure.step(f"Verifying installation was successful for each erot component"):
                verify_installation(fw_components_names, prev_version)
                # Has bug opened
                # verify_active_inactive_slots(component_name, active_slot, inactive_slot)
        finally:
            res_obj = fetch_and_install_erot_image(fw_component, curr_path, curr_version, curr_filename, test_name)
            with allure.step(f"verify operation time for install erot {curr_version!r} (duration: {res_obj.duration:.2f})"):
                OperationTime.verify_operation_time(res_obj.duration, 'install erot').verify_result()

            with allure.step(f"Verifying installation was successful for each erot component"):
                verify_installation(fw_components_names, curr_version)
            with allure.step('delete fetched firmware image files'):
                fw_component.files.delete_all_existing_files()

    def test_fae(self, engines, switch, topology_obj, test_api):
        TestToolkit.tested_api = test_api
        prev_path, prev_filename, prev_version = BmcTool.get_fw_component_version_previous(FW_COMPONENT_EROT)
        curr_path, curr_filename, curr_version = BmcTool.get_fw_component_version_latest(FW_COMPONENT_EROT)
        fw_component = self._firmware_component
        erot_names = switch.constants.erots[:]
        component_name = fw_component.get_resource_basename()

        try:
            fetch_and_install_erot_image(fw_component, prev_path, prev_version, prev_filename)
            with allure.step(f"Sleep for {MINUTE} so the bg-copy will finish"):
                time.sleep(MINUTE)
            with allure.step(f"Verifying installation was successful only for {component_name}"):
                verify_installation([component_name], prev_version)
            with allure.step(f"Verifying installation was not performed for other erot components"):
                other_erot_names = [erot_name for erot_name in erot_names if erot_name != component_name]
                verify_installation(other_erot_names, curr_version)
        finally:
            fetch_and_install_erot_image(fw_component, curr_path, curr_version, curr_filename)
            with allure.step(f"Verifying installation was successful for {component_name}"):
                verify_installation([component_name], curr_version)
            with allure.step('delete fetched firmware image files'):
                fw_component.files.delete_all_existing_files()
