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
FPGA_FW_LOCATION = '/auto/sw_system_release/fpga/juliet'


@pytest.mark.fpga
def test_fpga_install(engines, devices, topology_obj):
    """
    @summary: test all these commands:
        nv show fae platform firmware fpga files
        nv action delete fae platform firmware fpga files <file-name>
        nv action fetch fae platform firmware fpga <remote-url-fetch>
        nv action install fae platform firmware fpga files <file-name> [force]
    Note: because firmware installation takes a long time and the test does it twice, one time it's done
    on NVUE and one time on OpenAPI.

    Test flow:
        Check if it is fpga compatible device.
        (On NVUE:)
            1. Gets the fpga installed initial version.
            2. Gets older fpga firmware.
            3. Assert the older version and installed are different.
            4. Install firmware and do remote reboot
        (On OpenAPI:)
            5. Assert that the currently-installed firmware is the expected version
            6. Re-installs the original firmware and reboots
        (On NVUE:)
            7. Assert the current version is now the original version (from step 1)
            8. Delete both image files.
            9. Assert the file no longer exists
    """
    device = devices.dut
    fpga_older_version_path = _verify_fpga_compatible(device)

    with allure.step('Create System objects'):
        platform: Platform = Platform()
        fae: Fae = Fae()

    TestToolkit.tested_api = ApiType.NVUE
    with allure.step(f"With {TestToolkit.tested_api}"):
        initial_version, initial_version_path = _get_initial_version_and_path(platform)
        allure.attach("fpga_initial_version", f"{initial_version=}, {initial_version_path=}")
        older_version = _get_version_from_path(fpga_older_version_path)
        allure.attach("fpga_older_version", f"{older_version=}, {fpga_older_version_path=}")
        with allure.step("Assert versions are different"):
            if older_version == initial_version:
                raise Exception(f"Can't run test because the fpga version we want to install is the same as the version "
                                f"already installed: {initial_version}")

        initial_files = fae.platform.firmware.fpga.show_files_as_list()
        older_version_filename = _fetch_image(fpga_older_version_path, fae, initial_files)

    try:
        _install_image(fae, older_version_filename, older_version, engines, topology_obj, platform)

    finally:
        TestToolkit.tested_api = ApiType.OPENAPI
        initial_files = fae.platform.firmware.fpga.show_files_as_list()

        initial_version_filename = _fetch_image(initial_version_path, fae, initial_files)
        _install_image(fae, initial_version_filename, initial_version, engines, topology_obj, platform)

        TestToolkit.tested_api = ApiType.NVUE

        with allure.step("Deleting image file"):
            fae.platform.firmware.fpga.action_delete(older_version_filename).verify_result()
            fae.platform.firmware.fpga.action_delete(initial_version_filename).verify_result()


def _verify_fpga_compatible(device):
    with allure.step('Check whether device has fpga'):
        fpga_older_version_path = getattr(device, 'fpga_older_version_path', None)
        if fpga_older_version_path is None:
            pytest.skip("Device does not have fpga. Skipping the test")
    return fpga_older_version_path


def _install_image(fae, image_filename, expected_version, engines, topology_obj, platform):
    switch = engines.dut
    with allure.step(f"Installing firmware and rebooting (with {TestToolkit.tested_api})"):
        result, duration = OperationTime.save_duration(
            "nv action install fae platform firmware fpga files",
            f"(file {image_filename})", test_fpga_install.__name__,
            fae.platform.firmware.fpga.action_install,
            image_filename, switch, expect_reboot=False)
        result.verify_result()
        OperationTime.verify_operation_time(duration, 'install fpga')
        recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)

    with allure.step(f"With {TestToolkit.tested_api} again"):
        with allure.step("Asserting install was successful"):
            current_version = _get_fpga_firmware_actual_version(platform)
            assert current_version == expected_version


def _fetch_image(expected_version_path, fae, initial_files):
    with allure.step("Fetch fpga image file"):
        fae.platform.firmware.fpga.action_fetch(expected_version_path).verify_result()

    with allure.step("Asserting fetch was successful"):
        file_list = fae.platform.firmware.fpga.show_files_as_list()
        image_filename = os.path.basename(expected_version_path)
        assert set(file_list) == set(initial_files) | {image_filename}, (
            f"The `fetch` command was expected to only add the file {image_filename}, but the old file list is:\n"
            f"{initial_files}\n and the new file list is: {file_list}")
        return image_filename


def _get_initial_version_and_path(platform):
    with allure.step("Get fpga name and verify we have an image for it"):
        initial_version = _get_fpga_firmware_actual_version(platform)
        initial_version_path_list = _get_fw_images_paths("V" + initial_version.replace(".", "_"))
        initial_version_path = initial_version_path_list[0]
        logger.info(f"{initial_version=}, {initial_version_path=}")
        return initial_version, initial_version_path


def _get_fw_images_paths(version: str) -> List[str]:
    with allure.step('Verify fw images we have'):
        fw_files_path = glob.glob(os.path.join(FPGA_FW_LOCATION, version, "**", "*.fwpkg"), recursive=True)
        fw_files_path = [file for file in fw_files_path if 'transition' not in file]
        if not fw_files_path:
            raise Exception("No fw images found to install")
        logger.info(f"Firmware images found for {version=}: {fw_files_path}")
        return fw_files_path


def _get_fpga_firmware_actual_version(platform: Platform) -> str:
    with allure.step("Get actual fpga fw version"):
        output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.firmware.fpga.show()).get_returned_value()
        return output[PlatformConsts.FW_ACTUAL]


def _get_version_from_path(path: str) -> str:
    path_as_list = path.split(os.sep)
    path_version = path_as_list[path_as_list.index("juliet") + 1]
    ret = path_version.replace("V", "").replace("_", ".")  # V0_15 to 0.15 as read from BMC
    logger.info(f"Detected version name {ret} for path {path}")
    return ret
