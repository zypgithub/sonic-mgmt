import logging
import random
import string

import pytest

from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.FWComponentsTool import FWComponentsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.timeout(45 * MINUTE, func_only=True)
@pytest.mark.ssd
@pytest.mark.parametrize("platform_component_with_clear", ["ssd"], indirect=True)
def test_ssd_install(engines, devices, topology_obj, random_api, platform_component_with_clear, test_name, nv_command, show_platform_initial_state):
    """
    @summary: test all these commands:
        nv show platform firmware SSD files
        nv action delete platform firmware SSD files <file-name>
        nv action fetch platform firmware SSD <remote-url-fetch>
        nv action install platform firmware SSD files <file-name> [force|skip-reboot]

    Note: Test randomly chooses between 'skip-reboot', 'with-reboot', or 'double-install' to optimize test time while covering all installation modes.

    Test flow:
        1. Verify device is on latest version.
        2. Fetch and install SSD firmware using one of three modes:
           - skip-reboot: Install previous version once WITHOUT reboot (staged)
           - with-reboot: Install previous version WITH reboot (active immediately)
           - double-install: Install previous version twice WITHOUT reboot (tests staged firmware consistency)
        3. Verify:
           For skip-reboot/double-install modes: version remains latest (firmware staged, not activated).
           For with-reboot mode: version changed to previous.
        4. Restore to latest version using skip_version_check if needed.
    """
    TestToolkit.tested_api = random_api

    component_name = platform_component_with_clear.get_resource_basename().lower()
    # Get latest version info
    latest_path, latest_filename, latest_version_name = FWComponentsTool.get_fw_component_version_latest(component_name)

    try:
        # Get previous version info
        path, filename, version_name = FWComponentsTool.get_fw_component_version_previous(component_name)

        # Step 1: Verify device is on latest version
        with allure.step('Verify device is on latest SSD version'):
            BmcTool.verify_platform_component_version(platform_component_with_clear, latest_version_name)

        # Randomize installation mode: skip-reboot (1x without reboot), with-reboot (1x with reboot), or double-install (2x without reboot)
        install_mode = random.choice(['skip_reboot', 'with_reboot', 'double_install'])

        # Step 2: Fetches and installs SSD firmware according to installation mode
        if install_mode == 'with_reboot':
            with allure.step(f'Fetch and install SSD firmware {version_name} with reboot'):
                BmcTool.fetch_and_install_platform_component(platform_component=platform_component_with_clear, path=path,
                                                             name=version_name, filename=filename, topology_obj=topology_obj,
                                                             test_name=test_name).verify_result()

            # Verify reboot reason
            with allure.step('Verify reboot reason'):
                reboot_output = OutputParsingTool.parse_json_str_to_dictionary(
                    System().reboot.show(SystemConsts.REBOOT_REASON)
                ).get_returned_value()
                assert reboot_output["reason"].lower() == "reboot"
        else:
            # Get expected operation duration for SSD install without reboot
            duration_threshold = devices.dut.expected_operation_durations['install ssd']

            # Install previous version WITHOUT reboot (once for skip_reboot, twice for double_install)
            num_installs = 2 if install_mode == 'double_install' else 1
            for i in range(num_installs):
                with allure.step(f'Fetch and install SSD firmware {version_name} without reboot (attempt {i + 1}/{num_installs})'):
                    platform_component_with_clear.action_fetch(path).verify_result()
                    BmcTool.install_fw_image_without_reboot(platform_component=platform_component_with_clear,
                                                            test_name=test_name,
                                                            filename=filename).verify_result(expected_duration=duration_threshold)

        # Step 3: Verifies correct versioning for installed fw package
        expected_version = version_name if install_mode == 'with_reboot' else latest_version_name
        with allure.step(f'Verify SSD firmware version is {expected_version}'):
            BmcTool.verify_platform_component_version(platform_component_with_clear, expected_version)

    finally:
        # Step 4: Always restore to latest version for test isolation
        # Use skip_version_check=True if we used skip-reboot before (device is already on latest, just not activated)
        skip_version_check = install_mode != 'with_reboot'
        with allure.step(f'Fetch and install SSD firmware {latest_version_name}'):
            BmcTool.fetch_and_install_platform_component(platform_component=platform_component_with_clear, path=latest_path,
                                                         name=latest_version_name, filename=latest_filename, topology_obj=topology_obj,
                                                         test_name=test_name, skip_version_check=skip_version_check).verify_result()

        with allure.step(f'Verify SSD firmware version is {latest_version_name}'):
            BmcTool.verify_platform_component_version(platform_component_with_clear, latest_version_name)


@pytest.mark.ssd
@pytest.mark.parametrize("platform_component_with_clear", ["ssd"], indirect=True)
def test_ssd_firmware_rename_delete(engines, devices, random_api, platform_component_with_clear, test_name):
    """
    @summary: Test 'nv action rename platform firmware SSD files <file-name> <new-name>' command

    Test flow:
        1. Fetch an SSD firmware file
        2. Rename the file to a new name
        3. Verify the new name exists and old name doesn't
        4. Delete with new name (should succeed)
    """
    TestToolkit.tested_api = random_api

    component_name = platform_component_with_clear.get_resource_basename().lower()
    # Get latest firmware file info
    path, filename, version_name = FWComponentsTool.get_fw_component_version_latest(component_name)

    with allure.step(f"Fetch SSD firmware file: {filename}"):
        platform_component_with_clear.action_fetch(path).verify_result()
        fetched_file = platform_component_with_clear.files.file_name[filename]

    with allure.step("Rename file to new name with .ram extension"):
        new_name = RandomizationTool.get_random_string(15, ascii_letters=string.ascii_letters + string.digits) + '.ram'
        fetched_file.action_rename(new_name, rewrite_file_name=False).verify_result()

    with allure.step("Verify new file name exists and old name doesn't"):
        platform_component_with_clear.files.verify_show_files_output(
            expected_files=[new_name],
            unexpected_files=[filename]
        )

    with allure.step("Delete with new name (should succeed)"):
        platform_component_with_clear.files.file_name[new_name].action_delete().verify_result()

    with allure.step("Verify all files are deleted"):
        platform_component_with_clear.files.verify_show_files_output(expected_files=[])
