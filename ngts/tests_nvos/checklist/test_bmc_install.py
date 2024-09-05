import glob
import logging
import os.path
import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()
BMC_FW_LOCATION = '/auto/sw_system_release/low_level/openbmc/'
IMAGE_FILENAME = 'ec1736-apfw-4fe5.fwpkg'
BASE_VERSION_PATH = '/auto/sw_system_release/low_level/openbmc/88.0002.0453/dev/juliet-bmc/cec1736-apfw-4fe5.fwpkg'


@pytest.mark.bmc
def test_bmc_install(engines, devices):
    """
    @summary: test all these commands:
        nv show fae platform firmware bmc files
        nv action delete fae platform firmware bmc files <file-name>
        nv action fetch fae platform firmware bmc <remote-url-fetch>
        nv action install fae platform firmware bmc files <file-name> [force]
    Note: because firmware installation takes a long time and the test does it twice, one time it's done
    on NVUE and one time on OpenAPI.

    Note that a single image file contains two images (different versions). Running action-install on the
    file assumes that one of these is already installed, and triggers an installation of the other version.
    That's why this test uses only one file but actually swaps back-and-forth between two firmware versions.

    Test flow:
        Check if it is a Juliet device otherwise finish
        (On NVUE:)
        1. Gets the BMC name and name of currently-installed firmware version
        2. Fetch image file
        3. Assert the file now exists
        4. Install firmware and reboots
        (On OpenAPI:)
        5. Assert that the currently-installed firmware is the expected version
        6. Re-installs the original firmware and reboots
        (On NVUE:)
        7. Assert the current version is now the original version (from step 1)
        8. Delete the image file
        (On OpenAPI:)
        9. Fetch image file
        10. Delete the image file
        11. Assert the file no longer exists
    """
    with allure.step('Check is Juliet Device'):
        if not isinstance(devices.dut, JulietSwitch):
            pytest.skip("It's not a Juliet Switch. Skipping the test")

    with allure.step('Create System objects'):
        platform: Platform = Platform()
        fae: Fae = Fae()
        switch: JulietSwitch = devices.dut

    fw_files_path = _get_fw_images_paths()

    TestToolkit.tested_api = ApiType.NVUE
    with allure.step(f"With {TestToolkit.tested_api}"):
        initial_version, initial_version_path = _get_initial_version_path(fw_files_path, platform)
        initial_files = fae.platform.firmware.bmc.show_files_as_list()

        expected_version_path, image_filename = BASE_VERSION_PATH, IMAGE_FILENAME

        _fetch_image(expected_version_path, fae, image_filename, initial_files)

    try:
        _install_image(fae, image_filename, switch, platform)

    finally:
        TestToolkit.tested_api = ApiType.OPENAPI
        initial_files = fae.platform.firmware.bmc.show_files_as_list()

        _fetch_image(initial_version_path, fae, initial_version, initial_files)
        _install_image(fae, initial_version, switch, platform)

        TestToolkit.tested_api = ApiType.NVUE

        with allure.step("Deleting image file"):
            fae.platform.firmware.bmc.action_delete(image_filename).verify_result()
            fae.platform.firmware.bmc.action_delete(initial_version).verify_result()


def _install_image(fae, image_filename, switch, platform):
    with allure.step(f"Installing firmware and rebooting (with {TestToolkit.tested_api})"):
        result, _ = OperationTime.save_duration(
            "nv action install fae platform firmware bmc files",
            f"(file {image_filename})", test_bmc_install.__name__,
            fae.platform.firmware.bmc.action_install,
            image_filename, switch, expect_reboot=True)
        result.verify_result()
    with allure.step(f"With {TestToolkit.tested_api} again"):
        with allure.step("Asserting install was successful"):
            current_version = _get_bmc_firmware_actual_version(platform)
            assert current_version == image_filename, (
                f"Expected BMC FW version to be {image_filename} but actual version is {current_version}")
        with allure.step("Assert BMC status is ok"):
            inventory_output = OutputParsingTool.parse_json_str_to_dictionary(
                platform.inventory.show(PlatformConsts.FW_BMC)).get_returned_value()
            assert inventory_output[PlatformConsts.INV_STATE] == PlatformConsts.INV_OK


def _fetch_image(expected_version_path, fae, image_filename, initial_files):
    with allure.step("Fetch bmc image file"):
        fae.platform.firmware.bmc.action_fetch(expected_version_path).verify_result()

    with allure.step("Asserting fetch was successful"):
        file_list = fae.platform.firmware.bmc.show_files_as_list()
        assert set(file_list) == set(initial_files) | {image_filename}, (
            f"The `fetch` command was expected to only add the file {image_filename}, but the old file list is:\n"
            f"{initial_files}\n and the new file list is: {file_list}")


def _get_initial_version_path(fw_files_path, platform):
    with allure.step("Get BMC name and verify we have an image for it"):
        initial_version = _get_bmc_firmware_actual_version(platform)
        initial_version = initial_version.split('-')[0]  # This line needs to be removed. Currently file name and version are not the same.
        # /auto/mswg/release/bmc/juliet/V.88.0002.0453/cec1736-apfw-4fe5-transition.fwpkg  but name version is actually 88.0002.0453-001
        initial_version_path_list = [file for file in fw_files_path if initial_version in file]
        assert len(
            initial_version_path_list) > 0, f"Can't run test because there's no image file for restoring to the currently-"
        f"installed version. Current version is {initial_version} and the image files doesn't have it"
        initial_version_path = initial_version_path_list[0]
    return os.path.basename(initial_version_path), initial_version_path


def _get_fw_images_paths():
    with allure.step('Verify fw images we have'):
        fw_files_path = glob.glob(f"{BMC_FW_LOCATION}/**/*.fwpkg", recursive=True)
        # fw_files_path = [file for file in fw_files_path if 'transition' not in file] CURRENT BMC VERSION IS TRANSITION. So commenting out this line
        assert len(fw_files_path) > 0, "No fw images found to install"
    return fw_files_path


def _get_bmc_firmware_actual_version(platform: Platform) -> str:
    with allure.step("Get actual BMC fw version"):
        output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.firmware.bmc.show()).get_returned_value()
        return output[PlatformConsts.FW_ACTUAL]
