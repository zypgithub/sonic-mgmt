import random
import string
import threading
import time

import pytest

from ngts.nvos_constants.constants_nvos import SystemConsts, SSDConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.FWComponentsTool import FWComponentsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine  # type: ignore
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive


@pytest.mark.timeout(60 * MINUTE, func_only=True)
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
    install_mode = None
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

            with allure.step('Verify reboot reason'):
                reboot_output = OutputParsingTool.parse_json_str_to_dictionary(
                    System().reboot.show(SystemConsts.REBOOT_REASON)
                ).get_returned_value()
                assert reboot_output["reason"].lower() == "reboot"

            with allure.step('Verify SSD dump files in tech-support'):
                _verify_ssd_dump_in_techsupport(engines, test_name)

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
        skip_version_check = install_mode is not None and install_mode != 'with_reboot'
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


@pytest.mark.timeout(30 * MINUTE, func_only=True)
@pytest.mark.ssd
@pytest.mark.disable_loganalyzer  # Disable log analyzer - SSH timeouts and connection errors are EXPECTED during power shutdown
@pytest.mark.parametrize("platform_component_with_clear", ["ssd"], indirect=True)
def test_ssd_install_interruption_recovery(engines, devices, topology_obj, random_api, platform_component_with_clear, test_name, show_platform_initial_state):
    """
    @summary: Test SSD firmware installation interruption recovery.
              Verify that the system maintains firmware integrity and recovers to a healthy,
              functional state when installation is unexpectedly interrupted by power shutdown.

    Test flow:
        1. Verify device is on latest SSD version
        2. Fetch SSD firmware (previous version)
        3. Start installation and interrupt with power shutdown after 3-8 seconds(randomly chosen)
        4. Wait for system to recover and become accessible
        5. Verify firmware version is consistent (either original or new, not corrupted)
        6. Restore to latest firmware version
    """
    TestToolkit.tested_api = random_api
    ssd_component = platform_component_with_clear
    # Initialize cleanup variables
    install_engine = None
    shutdown_engine = None
    install_thread = None
    shutdown_thread = None
    recovered_version = None

    # Get latest version info
    latest_path, latest_filename, latest_version_name = FWComponentsTool.get_fw_component_version_latest(ssd_component.get_resource_basename().lower())

    try:
        # Step 1: Verify device is on latest version
        with allure.step('Verify device is on latest SSD version'):
            FWComponentsTool.verify_platform_component_version(ssd_component, latest_version_name)

        # Step 2: Fetch previous SSD firmware
        ssd_previous_path, ssd_previous_filename, ssd_previous_version = FWComponentsTool.get_fw_component_version_previous('ssd')
        with allure.step(f'Fetch SSD firmware {ssd_previous_version}'):
            ssd_component.action_fetch(ssd_previous_path).verify_result()

        # install_engine: Runs installation command that gets interrupted mid-execution.
        install_engine = LinuxSshEngine(
            ip=engines.dut.ip,
            username=engines.dut.username,
            password=engines.dut.password
        )
        # shutdown_engine: Triggers power shutdown command
        shutdown_engine = LinuxSshEngine(
            ip=engines.dut.ip,
            username=engines.dut.username,
            password=engines.dut.password
        )

        engines.dut.disconnect()
        # installation takes approximately 9 seconds, commit happens after ~7 seconds
        delay = random.randint(3, 8)
        shutdown_triggered = threading.Event()

        # Step 3: Start installation and schedule power shutdown
        with allure.step(f'Start SSD installation and interrupt with power shutdown after {delay} seconds'):
            install_thread = _run_installation(
                install_engine=install_engine,
                ssd_component=ssd_component,
                filename=ssd_previous_filename,
                shutdown_triggered=shutdown_triggered
            )
            time.sleep(delay)
            shutdown_thread = _trigger_shutdown(shutdown_engine, shutdown_triggered)
            time.sleep(2)  # Give thread time to send command before system goes down

        # Step 4: Wait for system to recover
        with allure.step('Wait for system to recover and become accessible'):
            ping_till_alive(should_be_alive=True, destination_host=engines.dut.ip, tries=600)

            # Wait for SSH to be ready before checking system status
            time.sleep(30)

            # Wait for NVOS to become functional (will auto-reconnect if needed)
            DutUtilsTool.wait_for_nvos_to_become_functional(engines.dut).verify_result()

        # Step 5: Verify firmware version consistency
        with allure.step('Verify firmware version is consistent (not corrupted)'):
            recovered_output = OutputParsingTool.parse_json_str_to_dictionary(
                ssd_component.show()
            ).get_returned_value()
            recovered_version = recovered_output['actual-firmware']
            assert recovered_version != "N/A" and recovered_version in [latest_version_name, ssd_previous_version], \
                f"Firmware version inconsistent: {recovered_version} (expected: {latest_version_name} or {ssd_previous_version})"

    finally:
        # Clean up threads and SSH engines
        if install_thread is not None:
            install_thread.join(timeout=1)
        if shutdown_thread is not None:
            shutdown_thread.join(timeout=1)
        if install_engine is not None:
            install_engine.disconnect()
        if shutdown_engine is not None:
            shutdown_engine.disconnect()

        # Step 6: Restore to latest firmware version (only if needed)
        if recovered_version is None or recovered_version != latest_version_name:
            with allure.step(f'Restore SSD firmware to {latest_version_name}'):
                BmcTool.fetch_and_install_platform_component(platform_component=ssd_component, path=latest_path,
                                                             name=latest_version_name, filename=latest_filename, topology_obj=topology_obj,
                                                             test_name=test_name, skip_version_check=True).verify_result()

                # Verify restoration
                BmcTool.verify_platform_component_version(ssd_component, latest_version_name)


def _verify_ssd_dump_in_techsupport(engines, test_name):
    """
    Verify that SSD dump files exist in tech-support.
    Checks for ssd.dump and the binary log file referenced in ssd.dump.
    """
    system = System()
    tech_support_dir = system.techsupport.action_generate(test_name=test_name)[0].replace('.tar.gz', '')
    system.techsupport.extract_techsupport_files(engines.dut)

    # Get all files in dump folder
    dump_files_list = system.techsupport.get_techsupport_files_list(engines.dut, 'dump')
    assert SSDConsts.SSD_DUMP_FILENAME in dump_files_list, f'{SSDConsts.SSD_DUMP_FILENAME} not found in tech-support'

    # Extract binary log filename from ssd.dump
    binary_log_filename = engines.dut.run_cmd(
        f"grep 'The binary log was written to file :' {tech_support_dir}/dump/{SSDConsts.SSD_DUMP_FILENAME} | awk '{{print $NF}}'"
    ).strip()
    assert binary_log_filename, f'Binary log filename not found in {SSDConsts.SSD_DUMP_FILENAME}'

    # Verify binary log file exists in dump folder
    assert binary_log_filename in dump_files_list, \
        f'{binary_log_filename} not found in tech-support dump folder'


def _run_installation(install_engine, ssd_component, filename, shutdown_triggered):
    """Run SSD installation in separate thread."""
    def run_installation():
        try:
            ssd_component.files.file_name[filename].action_file_install(
                force=False,
                dut_engine=install_engine
            ).verify_result()
        except Exception as e:
            if not shutdown_triggered.is_set():
                raise  # Unexpected failure before shutdown
            # Expected interruption after shutdown - just log it
            allure.attach(
                f"Installation interrupted by power shutdown\nException: {type(e).__name__}\nDetails: {str(e)}",
                "Installation Interruption"
            )

    install_thread = threading.Thread(target=run_installation)
    install_thread.daemon = True
    install_thread.start()
    return install_thread


def _trigger_shutdown(shutdown_engine, shutdown_triggered):
    """Trigger shutdown in a separate thread."""
    def trigger_shutdown():
        try:
            shutdown_triggered.set()  # Mark shutdown as triggered
            shutdown_engine.run_cmd(
                'sudo bash -c "echo 1 > /var/run/hw-management/system/pwr_cycle"',
                timeout=3
            )
        except Exception:
            # System shutting down or connection failed - this is expected
            # Catch ALL exceptions to prevent pytest warnings about unhandled thread exceptions
            pass

    shutdown_thread = threading.Thread(target=trigger_shutdown)
    shutdown_thread.daemon = True
    shutdown_thread.start()
    return shutdown_thread
