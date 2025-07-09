import json
import logging

from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.tests_nvos.constants import FW_COMPONENT_FPGA
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool
from ngts.tests_nvos.constants import PRODUCTION, DEVELOPMENT
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class FWComponentsTool:
    PLATFORM_COMPONENTS_DICT = dict()

    @staticmethod
    def fetch_and_install_platfrom_component(platform_component, path, name, filename, topology_obj):
        with allure.step(f'Fetch {name} image from: {path}'):
            platform_component.action_fetch(path).verify_result()

        with allure.step(f'installing image {name}'):
            platform_component.files.file_name[filename].action_file_install_with_reboot(topology_obj=topology_obj)

    @staticmethod
    def verify_platform_component_version(platform_component, expected_version: str):
        with allure.step(f'Making sure component is now on version {expected_version}'):
            platform_component_output = OutputParsingTool.parse_json_str_to_dictionary(
                platform_component.show()).verify_result()
            output_version = platform_component_output[PlatformConsts.FW_ACTUAL]
            logger.info(f"Found version: {output_version}")

            assert output_version == expected_version, \
                f"firmware is {output_version}, expected {expected_version} after the install"

    @staticmethod
    def _get_fw_component_version_info(component_name, version):
        if component_name == FW_COMPONENT_FPGA:
            with allure.step("Check whether device has non encrypted FPGA"):
                encrypted_fpga = '_encrypted'
                non_encrypted_fpga_pns = {"692-9K36F-A5MV-JS0", "692-9K36F-00MV-JSL", "920-9K36F-00MV-ES1"}
                platform_output = OutputParsingTool.parse_show_output_to_dict(Platform().show()).get_returned_value()
                part_number = platform_output[PlatformConsts.FW_PART_NUMBER].strip()
                if part_number in non_encrypted_fpga_pns:
                    encrypted_fpga = ''
                component_name = f'{component_name}{encrypted_fpga}'
        device = TestToolkit.devices.dut
        fw_path = device.fw_versions_json_file_path
        with allure.step(f'Read platform components info from json {fw_path}'):
            if not FWComponentsTool.PLATFORM_COMPONENTS_DICT:
                with open(fw_path, 'r') as file:
                    FWComponentsTool.PLATFORM_COMPONENTS_DICT = json.load(file)
            platform_components_dict = FWComponentsTool.PLATFORM_COMPONENTS_DICT
            provisioning = DEVELOPMENT if SecureBootTool.is_dev_system(TestToolkit.engines.dut) else PRODUCTION
            component_image_info = platform_components_dict[provisioning][component_name][version]
            filename = getattr(component_image_info.keys(), "filename", None)
            if not filename:
                filename = component_image_info['path'].split("/")[-1]
            return component_image_info['path'], filename, component_image_info['version_name']

    @staticmethod
    def get_fw_component_version_dict(component_name, version):
        device = TestToolkit.devices.dut
        fw_path = device.fw_versions_json_file_path
        with allure.step(f'Read platform components info from json {fw_path}'):
            if not FWComponentsTool.PLATFORM_COMPONENTS_DICT:
                with open(fw_path, 'r') as file:
                    FWComponentsTool.PLATFORM_COMPONENTS_DICT = json.load(file)
            platform_components_dict = FWComponentsTool.PLATFORM_COMPONENTS_DICT
            provisioning = DEVELOPMENT if SecureBootTool.is_dev_system(TestToolkit.engines.dut) else PRODUCTION
            component_image_info = platform_components_dict[provisioning][component_name][version]
            return component_image_info

    @staticmethod
    def get_fw_component_version_latest(component_name):
        return FWComponentsTool._get_fw_component_version_info(component_name, "latest")

    @staticmethod
    def get_fw_component_version_previous(component_name):
        return FWComponentsTool._get_fw_component_version_info(component_name, "previous")
