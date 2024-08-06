import glob
import logging
import os.path
from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot

logger = logging.getLogger()
BMC_FW_LOCATION = '/auto/sw_system_release/low_level/openbmc/'


@pytest.mark.bmc
def test_bmc_install(engines, devices, topology_obj):
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
    device = devices.dut
    with allure.step('Check whether device has BMC'):
        bmc_base_version_path = getattr(device, 'bmc_base_version_path', None)
        if bmc_base_version_path is None:
            pytest.skip("Device does not have BMC. Skipping the test")

    with allure.step('Create System objects'):
        platform: Platform = Platform()
        fae: Fae = Fae()

    TestToolkit.tested_api = ApiType.NVUE
    with allure.step(f"With {TestToolkit.tested_api}"):
        initial_version, initial_version_path = _get_initial_version_and_path(platform)
        allure.attach("bmc_initial_version", f"{initial_version=}, {initial_version_path=}")
        base_version = _get_version_from_path(bmc_base_version_path)
        allure.attach("bmc_base_version", f"{base_version=}, {bmc_base_version_path=}")
        with allure.step("Assert versions are different"):
            if base_version == initial_version:
                raise Exception(f"Can't run test because the BMC version we want to install is the same as the version "
                                f"already installed: {initial_version}")

        initial_files = fae.platform.firmware.bmc.show_files_as_list()
        base_version_filename = _fetch_image(bmc_base_version_path, fae, initial_files)

    try:
        _install_image(fae, base_version_filename, base_version, engines, topology_obj, platform)

    finally:
        TestToolkit.tested_api = ApiType.OPENAPI
        initial_files = fae.platform.firmware.bmc.show_files_as_list()

        initial_version_filename = _fetch_image(initial_version_path, fae, initial_files)
        _install_image(fae, initial_version_filename, initial_version, engines, topology_obj, platform)

        TestToolkit.tested_api = ApiType.NVUE

        with allure.step("Deleting image file"):
            fae.platform.firmware.bmc.action_delete(base_version_filename).verify_result()
            fae.platform.firmware.bmc.action_delete(initial_version_filename).verify_result()


def _install_image(fae, image_filename, expected_version, engines, topology_obj, platform):
    switch = engines.dut
    with allure.step(f"Installing firmware and rebooting (with {TestToolkit.tested_api})"):
        result, duration = OperationTime.save_duration(
            "nv action install fae platform firmware bmc files",
            f"(file {image_filename})", test_bmc_install.__name__,
            fae.platform.firmware.bmc.action_install,
            image_filename, switch, expect_reboot=False)
        result.verify_result()
        OperationTime.verify_operation_time(duration, 'install bmc')
        recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)

    with allure.step(f"With {TestToolkit.tested_api} again"):
        with allure.step("Asserting install was successful"):
            current_version = _get_bmc_firmware_actual_version(platform)
            assert current_version == expected_version
        with allure.step("Assert BMC status is ok"):
            inventory_output = OutputParsingTool.parse_json_str_to_dictionary(
                platform.inventory.show(PlatformConsts.FW_BMC)).get_returned_value()
            assert inventory_output[PlatformConsts.INV_STATE] == PlatformConsts.INV_OK


def _fetch_image(expected_version_path, fae, initial_files):
    with allure.step("Fetch bmc image file"):
        fae.platform.firmware.bmc.action_fetch(expected_version_path).verify_result()

    with allure.step("Asserting fetch was successful"):
        file_list = fae.platform.firmware.bmc.show_files_as_list()
        image_filename = os.path.basename(expected_version_path)
        assert set(file_list) == set(initial_files) | {image_filename}, (
            f"The `fetch` command was expected to only add the file {image_filename}, but the old file list is:\n"
            f"{initial_files}\n and the new file list is: {file_list}")
        return image_filename


def _get_initial_version_and_path(platform):
    with allure.step("Get BMC name and verify we have an image for it"):
        initial_version = _get_bmc_firmware_actual_version(platform)
        initial_version_path_list = _get_fw_images_paths(initial_version)
        initial_version_path = initial_version_path_list[0]
        logger.info(f"{initial_version=}, {initial_version_path=}")
        return initial_version, initial_version_path


def _get_fw_images_paths(version: str) -> List[str]:
    with allure.step('Verify fw images we have'):
        fw_files_path = glob.glob(os.path.join(BMC_FW_LOCATION, version, "**", "*.fwpkg"), recursive=True)
        fw_files_path = [file for file in fw_files_path if 'transition' not in file]
        if not fw_files_path:
            raise Exception("No fw images found to install")
        logger.info(f"Firmware images found for {version=}: {fw_files_path}")
        return fw_files_path


def _get_bmc_firmware_actual_version(platform: Platform) -> str:
    with allure.step("Get actual BMC fw version"):
        output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.firmware.bmc.show()).get_returned_value()
        return output[PlatformConsts.FW_ACTUAL]


def _get_version_from_path(path: str) -> str:
    path_as_list = path.split(os.sep)
    ret = path_as_list[path_as_list.index("openbmc") + 1]
    logger.info(f"Detected version name {ret} for path {path}")
    return ret
