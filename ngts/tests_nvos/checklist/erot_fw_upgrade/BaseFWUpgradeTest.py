import copy
import logging
import os
import allure
import os.path

from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot

logger = logging.getLogger()


def verify_installation(fae, firmware_component, expected_version, filename):
    with allure.step(f"Asserting install was successful"):
        firmware_shown = OutputParsingTool.parse_json_str_to_dictionary(
            fae.platform.firmware.show()).get_returned_value()
        actual_firmware = firmware_shown[firmware_component][PlatformConsts.FW_ACTUAL]
        assert actual_firmware == expected_version, \
            f"Expected {filename} version: {expected_version}. Actual version: {actual_firmware}"


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
        fw_component = self._firmware_component
        component_name = fw_component.get_resource_basename().lower()
        path, filename, version = BmcTool.get_fw_component_version_previous(component_name)

        with allure.step(f"Fetching PREVIOUS image"):
            fw_component.action_fetch(path).verify_result()

        fw_component.files.file_name[filename].action_delete()
        with allure.step("Trying to delete non-existing image"):
            fw_component.files.file_name[filename].action_delete(should_succeed=False)

        fetched_image_file = fw_component.files.file_name[filename]
        with allure.step("Trying to install non-existing image"):
            fetched_image_file.action_file_install(force=force).verify_result(False)

    def test(self, engines, switch, topology_obj, test_api):
        TestToolkit.tested_api = test_api
        fw_component = self._firmware_component
        component_name = fw_component.get_resource_basename().lower()
        prev_path, prev_filename, prev_version = BmcTool.get_fw_component_version_previous(component_name)
        curr_path, curr_filename, curr_version = BmcTool.get_fw_component_version_latest(component_name)
        fae = Fae()
        fw_components_names = switch.constants.erots.copy()
        fw_components_names.remove(
            'ERoT_BMC_0')  # Bad BMC erot fw - hardware limitation, therefore removing 'ERoT_BMC_0' from install verification
        try:
            with allure.step(f"Fetching PREVIOUS image"):
                fw_component.action_fetch(prev_path).verify_result()

            fw_component.files.verify_show_files_output(expected_files=[prev_filename])

            fetched_image_file = fw_component.files.file_name[prev_filename]
            fetched_image_file.action_file_install(force=False)

            recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)

            for comp_name in fw_components_names:
                verify_installation(fae, comp_name, prev_version, filename=prev_filename)

        finally:
            try:
                with allure.step(f"Fetching CURRENT image"):
                    fw_component.action_fetch(curr_path).verify_result()

                fw_component.files.verify_show_files_output(expected_files=[prev_filename, curr_filename])

                fetched_image_file = fw_component.files.file_name[curr_filename]
                fetched_image_file.action_file_install(force=False)

                recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)

                for comp_name in fw_components_names:
                    verify_installation(fae, comp_name, curr_version, filename=curr_filename)
            finally:
                with allure.step('delete fetched firmware image files'):
                    files = fw_component.files.get_files()
                    fw_component.files.delete_files(files_to_delete=files)

    def test_list(self, engines, switch, topology_obj, test_api, fae):
        TestToolkit.tested_api = test_api
        prev_path, prev_filename, prev_version = BmcTool.get_fw_component_version_previous("erot")
        curr_path, curr_filename, curr_version = BmcTool.get_fw_component_version_latest("erot")
        erots = copy.deepcopy(self._firmware_components)
        del erots[
            'ERoT_BMC_0']  # Bad BMC erot fw - hardware limitation, therefore removing 'ERoT_BMC_0' from install verification

        try:
            for comp_name, component in erots.items():
                with allure.step(f"Fetching PREVIOUS image for {comp_name}"):
                    component.action_fetch(prev_path).verify_result()

                component.files.verify_show_files_output(expected_files=[prev_filename])

                fetched_image_file = component.files.file_name[prev_filename]
                fetched_image_file.action_file_install().verify_result()

            recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)

            for comp_name in erots.keys():
                verify_installation(fae, comp_name, prev_version, filename=prev_filename)

        finally:
            try:
                for comp_name, component in erots.items():
                    with allure.step(f"Fetching CURRENT image for {comp_name}"):
                        component.action_fetch(curr_path).verify_result()

                    component.files.verify_show_files_output(expected_files=[prev_filename, curr_filename])

                    fetched_image_file = component.files.file_name[curr_filename]
                    fetched_image_file.action_file_install().verify_result()

                recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)

                for comp_name in erots.keys():
                    verify_installation(fae, comp_name, curr_version, filename=curr_filename)
            finally:
                for comp_name, component in erots.items():
                    with allure.step(f"Deleting fw image files of {comp_name}"):
                        files = comp_name.files.get_files()
                        comp_name.files.delete_files(files_to_delete=files)
