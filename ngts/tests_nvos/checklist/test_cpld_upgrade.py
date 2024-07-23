import logging
import os.path

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot

logger = logging.getLogger()


@pytest.mark.cpld
def test_cpld_upgrade(engines, devices, topology_obj):
    """
    @summary: test all these commands:
        nv show fae platform firmware cpld files
        nv action delete fae platform firmware cpld files <file-name>
        nv action fetch fae platform firmware cpld <remote-url-fetch>
        nv action install fae platform firmware cpld files <file-name> [force]
    Note: because the test takes a long time, half of it runs on NVUE and half on OpenAPI

    Test flow:
        1. Fetch old CPLD firmware images (two files: BURN and REFRESH)
        2. Assert the images exist now
        3. Install them (BURN, then REFRESH, then reboot system)
        4. Assert the current CPLD firmware version is the one just installed
        5. Delete the images that were used for installation
        6. Assert the images no longer exist
        7. Repeat steps 1-6 on for the new CPLD firmware image
    """
    with allure.step('Create System objects'):
        platform = Platform()
        fae = Fae()

    device = devices.dut
    if not (device.current_cpld_version and device.previous_cpld_version):
        raise NotImplementedError(f"{type(device)} does not have 'current_cpld_version' or 'previous_cpld_version'")

    try:
        TestToolkit.tested_api = ApiType.NVUE
        with allure.step(f"Fetch, install and assert old CPLD version (through {TestToolkit.tested_api})"):
            _firmware_install_test(devices, fae, platform, devices.dut.previous_cpld_version, engines, topology_obj)
    finally:
        TestToolkit.tested_api = ApiType.OPENAPI
        with allure.step(f"Cleanup: Fetch, install and assert original CPLD version (through {TestToolkit.tested_api})"):
            _firmware_install_test(devices, fae, platform, devices.dut.current_cpld_version, engines, topology_obj)


def _firmware_install_test(devices, fae: Fae, platform: Platform, image_consts: BaseSwitch.CpldImageConsts,
                           engines, topology_obj):
    refresh_filename = os.path.basename(image_consts.refresh_image_path)  # will be empty for switches that have no REFRESH file
    burn_filename = os.path.basename(image_consts.burn_image_path)
    if refresh_filename:
        file_names = {burn_filename, refresh_filename}
    else:
        file_names = {burn_filename}
    logger.info(f"{file_names=} {type(devices.dut)=}")

    with allure.step(f"Asserting the image files don't exist yet"):
        initial_files = fae.platform.firmware.cpld.show_files_as_list()
        assert not (file_names & set(initial_files)), ("Can't test `fetch` because file is already present: " +
                                                       str(set(initial_files) & file_names))

    with allure.step(f"Fetching BURN image"):
        fae.platform.firmware.cpld.action_fetch(image_consts.burn_image_path).verify_result()

    if refresh_filename:
        with allure.step(f"Fetching REFRESH image"):
            fae.platform.firmware.cpld.action_fetch(image_consts.refresh_image_path).verify_result()

    with allure.step(f"Asserting fetch was successful"):
        file_list = fae.platform.firmware.cpld.show_files_as_list()
        assert set(file_list) == set(initial_files) | file_names, \
            f"Expected new files {file_names} but the old file list is {initial_files} " \
            f"and the new one is {file_list}"

    try:
        with allure.step(f"Installing BURN image {burn_filename}"):
            result, _ = OperationTime.save_duration(
                "nv action install fae platform firmware cpld files (BURN)", burn_filename, test_cpld_upgrade.__name__,
                fae.platform.firmware.cpld.action_install,
                burn_filename, device=devices.dut, expect_reboot=False)
            result.verify_result()

        if refresh_filename:
            with allure.step(f"Installing REFRESH image (and rebooting) {refresh_filename}"):
                fae.platform.firmware.cpld.action_install(refresh_filename, device=devices.dut, expect_reboot=True
                                                          ).verify_result()
        else:
            recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)

        with allure.step(f"Asserting install was successful"):
            firmware_shown = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).get_returned_value()
            for cpld_number, expected_version in image_consts.version_names.items():
                actual_firmware = firmware_shown[cpld_number][PlatformConsts.FW_ACTUAL]
                assert actual_firmware == expected_version, \
                    f"Expected {cpld_number} version: {expected_version}. Actual version: {actual_firmware}"

    except Exception as e:
        logger.error(f"{type(e).__name__}: {e}")
        raise

    finally:
        for file_name in file_names:
            with allure.step(f"Deleting image file {file_name}"):
                fae.platform.firmware.cpld.action_delete(file_name).verify_result()

        with allure.step(f"Asserting delete was successful"):
            final_file_list = fae.platform.firmware.cpld.show_files_as_list()
            assert set(initial_files) == set(final_file_list), (
                f"File list is expected to be the same at the start and end of the test, but the initial file list is:\n"
                f"{initial_files}\nAnd at the end of the test the list is:\n{final_file_list}")
