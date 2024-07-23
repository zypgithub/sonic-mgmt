import logging
import string
from typing import Tuple
import string
import time

import pytest


from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.redmine.redmine_api import *
from ngts.nvos_constants.constants_nvos import ImageConsts, PlatformConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Tools import Tools

logger = logging.getLogger()


def verify_bios_version(devices, platform, is_current_bios=False):
    expected_version = ""
    if is_current_bios:
        expected_version = devices.dut.current_bios_version_name
    else:
        expected_version = devices.dut.previous_bios_version_name

    with allure.step('making sure BIOS is now on version {}'.format(expected_version)):
        fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
        installed_bios_version = fw_output[PlatformConsts.FW_BIOS][PlatformConsts.FW_ACTUAL]
        logger.info("Found BIOS version: {}".format(installed_bios_version))

        assert installed_bios_version == expected_version, \
            "BIOS firmware is {}, expected {} after the install".format(installed_bios_version,
                                                                        expected_version)


def install_bios(devices, fae, version_name):
    if version_name == devices.dut.previous_bios_version_name:
        path = devices.dut.previous_bios_version_path
    else:
        path = devices.dut.current_bios_version_path
    with allure.step('Fetch previous Bios image from: {}'.format(path)):
        fae.platform.firmware.bios.action_fetch(path).verify_result()

    with allure.step('installing Bios image {}'.format(version_name)):
        fae.platform.firmware.install_bios_firmware(bios_image_path=devices.dut.get_bios_file_name(), device=devices.dut)


def install_image_and_verify(orig_engine, image_name, system, test_name=''):
    with allure.step("Installing image {}".format(image_name)):
        new_engine = LinuxSshEngine(orig_engine.ip, orig_engine.username,
                                    TestToolkit.devices.dut.get_default_password_by_version(""))
        OperationTime.save_duration('image install', '', test_name,
                                    system.image.files.file_name[image_name].action_file_install_with_reboot,
                                    "", True, None, None, new_engine)

    with allure.step('replace dut engine'):
        TestToolkit.engines.dut = new_engine  # if install succeeded, need to replace dut engine

    with allure.step("Verify installed image"):
        time.sleep(5)
        verify_current_version(normalize_image_name(image_name), system)


def verify_current_version(original_version, system):
    with allure.step(f"Verify that current image is {original_version}"):
        current_version = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()['image']
        assert current_version == original_version, f"Current version is invalid: {current_version}, expected: {original_version}"


def normalize_image_name(image_name):
    return image_name.replace("-amd64", "").replace(".bin", "")


def cleanup_test(system, original_image_partition, fetched_image_files, orig_engine=None):
    with allure.step("Cleanup step"):
        with allure.step("Set the original image to be booted next and verify"):
            system.image.boot_next_and_verify(original_image_partition)

        with allure.step("Reboot the system"):
            system.reboot.action_reboot(recovery_engine=orig_engine)

        with allure.step('restore original dut engine'):
            TestToolkit.engines.dut = orig_engine or TestToolkit.engines.dut

        with allure.step("Delete all images that have been fetch during the test and verify"):
            system.image.files.delete_files(fetched_image_files)
            system.image.files.verify_show_files_output(unexpected_files=fetched_image_files)


def get_image_data_and_fetch_image(system, image_version):
    original_image_partition = get_image_data(system)

    with allure.step(f"Fetch image {image_version}"):
        # player = TestToolkit.engines['sonic_mgmt']
        player = ConnectionTool.create_ssh_conn('10.237.116.70', 'root', '12345').verify_result()

        system.image.action_fetch(ImageConsts.SCP_PATH_SERVER.format(username=player.username, password=player.password,
                                                                     ip=player.ip, path=image_version))
    image_name = image_version.split("/")[-1]
    return original_image_partition, image_name


def get_image_data(system):
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
