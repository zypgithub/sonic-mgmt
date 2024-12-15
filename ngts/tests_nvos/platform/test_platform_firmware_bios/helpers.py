from infra.tools.redmine.redmine_api import *
from ngts.nvos_constants.constants_nvos import ImageConsts, PlatformConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Tools import Tools

logger = logging.getLogger()


def get_bios_version(platform) -> str:
    with allure.step('get  BIOS version '):
        fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
        return fw_output[PlatformConsts.FW_BIOS][PlatformConsts.FW_ACTUAL]


def verify_current_version(original_version, system):
    with allure.step(f"Verify that current image is {original_version}"):
        current_version = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()[
            'image']
        assert current_version == original_version, f"Current version is invalid: {current_version}, expected: {original_version}"


def get_image_data(system) -> str:
    with allure.step("Save original installed image name"):
        original_images = system.image.get_image_field_values()
        original_image = original_images[ImageConsts.CURRENT_IMG]
        original_image_partition = system.image.get_image_partition(original_image, original_images)
        logger.info("Original image: {}, partition: {}".format(original_image, original_image_partition))
        return original_image_partition


def verify_bios_auto_update_value(platform, value):
    with allure.step(f'verify nv show platform firmware BIOS auto-update is {value}'):
        logging.info(f'verify nv show platform firmware BIOS auto-update is {value}')
        output = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.bios.show()).verify_result()
        assert value == output[PlatformConsts.FW_AUTO_UPDATE], f"auto-update should be {value}"


def verify_bios_version(engines, platform, expected_version: str):
    with allure.step(f'Making sure BIOS is now on version {expected_version}'):
        fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
        new_bios_version = fw_output[PlatformConsts.FW_BIOS][PlatformConsts.FW_ACTUAL]
        logger.info(f"Found BIOS version: {new_bios_version}")

        assert new_bios_version == expected_version, \
            f"BIOS firmware is {new_bios_version}, expected {expected_version} after the install"


def fetch_and_install_bios(platform, path, name, filename, topology_obj, system_is_ready_timeout):
    with allure.step(f'Fetch {name} Bios image from: {path}'):
        platform.firmware.bios.action_fetch(path).verify_result()

    with allure.step(f'installing Bios image {name}'):
        platform.firmware.bios.files.file_name[filename].action_file_install_with_reboot(topology_obj=topology_obj, system_is_ready_timeout=system_is_ready_timeout).verify_result()


def get_bios_info_from_device(device, version):
    with allure.step(f'get BIOS info from {device}'):
        bios_image_info = getattr(device.bios_image_info, version)
        return bios_image_info['path'], bios_image_info['filename'], bios_image_info['version_name'], bios_image_info['date']
