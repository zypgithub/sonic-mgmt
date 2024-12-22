import copy
import logging
import os
import os.path
from typing import Tuple

import allure

from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.Devices.IbDevice import IbSwitch
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot

logger = logging.getLogger()


def verify_installation(fae, firmware_component, image_consts, filename):
    with allure.step(f"Asserting install was successful"):
        firmware_shown = OutputParsingTool.parse_json_str_to_dictionary(
            fae.platform.firmware.show()).get_returned_value()
        expected_version = image_consts.version_names[filename]
        actual_firmware = firmware_shown[firmware_component][PlatformConsts.FW_ACTUAL]
        assert actual_firmware == expected_version, \
            f"Expected {filename} version: {expected_version}. Actual version: {actual_firmware}"


def set_firmware_property(firmware_component, property, value):
    logging.info(f"Set firmware {property} to {value}")
    firmware_component.set(property, value, apply=True)


def get_image_names(switch: IbSwitch) -> Tuple[str, str]:
    image_consts = switch.erot_fw_image_info
    prev_filename = os.path.basename(image_consts.previous_image_path)
    curr_filename = os.path.basename(image_consts.current_image_path)
    return prev_filename, curr_filename


class BaseFWUpgradeTest:

    def __init__(self, firmware_component):
        if isinstance(firmware_component, dict):
            self._firmware_components = firmware_component
            self._firmware_component = None
        else:
            self._firmware_component = firmware_component
            self._firmware_components = None

    def test_badflow(self, engines, switch, topology_obj, test_api, force):
        TestToolkit.tested_api = test_api
        filename, _ = get_image_names(switch)
        fw_component = self._firmware_component
        image_consts = switch.erot_fw_image_info

        with allure.step(f"Fetching PREVIOUS image"):
            fw_component.action_fetch(image_consts.previous_image_path).verify_result()

        fw_component.files.file_name[filename].action_delete()
        with allure.step("Trying to delete non-existing image"):
            fw_component.files.file_name[filename].action_delete(should_succeed=False)

        fetched_image_file = fw_component.files.file_name[filename]
        with allure.step("Trying to install non-existing image"):
            fetched_image_file.action_file_install(force=force).verify_result(False)

    def test(self, engines, switch, topology_obj, test_api):
        TestToolkit.tested_api = test_api
        prev_filename, curr_filename = get_image_names(switch)
        fw_component = self._firmware_component
        image_consts = switch.erot_fw_image_info
        fae = Fae()
        fw_components_names = switch.constants.erots.copy()
        fw_components_names.remove('ERoT_BMC_0')  # Bad BMC erot fw - hardware limitation, therefore removing 'ERoT_BMC_0' from install verification
        try:
            with allure.step(f"Fetching PREVIOUS image"):
                fw_component.action_fetch(image_consts.previous_image_path).verify_result()

            fw_component.files.verify_show_files_output(expected_files=[prev_filename])

            set_firmware_property(fw_component, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_CUSTOM)

            fetched_image_file = fw_component.files.file_name[prev_filename]
            fetched_image_file.action_file_install(force=False)

            recover_dut_with_remote_reboot(topology_obj, engines)

            for comp_name in fw_components_names:
                verify_installation(fae, comp_name, image_consts, filename=prev_filename)

            with allure.step(f"Fetching CURRENT image"):
                fw_component.action_fetch(image_consts.current_image_path).verify_result()

            fw_component.files.verify_show_files_output(expected_files=[prev_filename, curr_filename])

            fetched_image_file = fw_component.files.file_name[curr_filename]
            fetched_image_file.action_file_install(force=False)

            recover_dut_with_remote_reboot(topology_obj, engines)

            for comp_name in fw_components_names:
                verify_installation(fae, comp_name, image_consts, filename=curr_filename)

        finally:

            set_firmware_property(fw_component, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_DEFAULT)
            with allure.step("Deleting fw image files"):
                fw_component.files.delete_files([prev_filename, curr_filename])
                fw_component.files.verify_show_files_output()

    def test_list(self, engines, switch, topology_obj, test_api, fae):
        TestToolkit.tested_api = test_api
        prev_filename, curr_filename = get_image_names(switch)
        image_consts = switch.erot_fw_image_info
        erots = copy.deepcopy(self._firmware_components)
        del erots['ERoT_BMC_0']  # Bad BMC erot fw - hardware limitation, therefore removing 'ERoT_BMC_0' from install verification

        try:
            for comp_name, component in erots.items():

                with allure.step(f"Fetching PREVIOUS image for {comp_name}"):
                    component.action_fetch(image_consts.previous_image_path).verify_result()

                component.files.verify_show_files_output(expected_files=[prev_filename])

                set_firmware_property(component, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_CUSTOM)

                fetched_image_file = component.files.file_name[prev_filename]
                fetched_image_file.action_file_install().verify_result()

            recover_dut_with_remote_reboot(topology_obj, engines)

            for comp_name in erots.keys():
                verify_installation(fae, comp_name, image_consts, filename=prev_filename)

            for comp_name, component in erots.items():
                with allure.step(f"Fetching CURRENT image for {comp_name}"):
                    component.action_fetch(image_consts.current_image_path).verify_result()

                component.files.verify_show_files_output(expected_files=[prev_filename, curr_filename])

                set_firmware_property(component, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_CUSTOM)

                fetched_image_file = component.files.file_name[curr_filename]
                fetched_image_file.action_file_install().verify_result()

            recover_dut_with_remote_reboot(topology_obj, engines)

            for comp_name in erots.keys():
                verify_installation(fae, comp_name, image_consts, filename=curr_filename)

        finally:
            for comp_name, component in erots.items():
                with allure.step(f"Deleting fw image files of {comp_name}"):
                    set_firmware_property(component, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_DEFAULT)
                    component.files.delete_files([prev_filename, curr_filename])
                    component.files.verify_show_files_output()
