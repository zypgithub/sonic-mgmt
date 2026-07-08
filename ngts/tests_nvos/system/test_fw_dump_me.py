from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tools.test_utils import allure_utils as allure
import logging
import pytest
import time
import random

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.disable_loganalyzer
def test_fw_dump_me(engines, devices):
    """
    Exercise the WARNING-severity FW-event path (distinct from test_fatal_mode,
    which covers the fatal crash -> reboot -> recovery flow).

    sxd_api_crash_fw.py raises a warning-severity "FW test event": SAI-IB writes
    a dump but the syncd docker does NOT crash and the system does NOT reboot.

    Test flow:
        1. Upload fw event script to switch
        2. Copy script to syncd-ibv0 container
        3. Capture pre-event boot time (to later prove no reboot happened)
        4. Execute fw event script
        5. Validate "FW test event" log and that an sai-dfw dump is created
        6. Validate the system stayed up: syncd still running + boot time unchanged
        7. Download the dump to a shared location, validate and delete
    """
    system = System(None)
    ibv_num = random.randint(0, devices.dut.asic_amount - 1)
    syncd_ibv = f"syncd-ibv0{ibv_num}"
    # SAI-IB dump rotation (SAI_KEY_WRN_DUMP_STORE_PATH) splits dumps by severity:
    #   fatal   -> /var/log/mellanox/sdk-dumps_devN/
    #   warning -> /var/log/mellanox/sdk-wrn-dumps_devN/
    # sxd_api_crash_fw.py raises a warning-severity FW event, so check the warning path.
    # (Fatal-severity dumps in sdk-dumps_devN/ are covered by test_fatal_mode.)
    sdk_dump_folder = f"/var/log/mellanox/sdk-wrn-dumps_dev{ibv_num}/"

    with allure.step('Upload sdk fw crush file to switch'):
        player_engine = engines['sonic_mgmt']
        player_engine.upload_file_using_scp(dest_username=devices.dut.default_username,
                                            dest_password=devices.dut.default_password,
                                            dest_folder=NvosConst.DESTINATION_FW_SCRIPT_PATH,
                                            dest_ip=engines.dut.ip,
                                            local_file_path=NvosConst.FW_DUMP_ME_SCRIPT_PATH)

    with allure.step('Copy sxd api crash fw file to the {} container'.format(syncd_ibv)):
        script_src = f'{NvosConst.DESTINATION_FW_SCRIPT_PATH}sxd_api_crash_fw.py'
        engines.dut.run_cmd(f'sudo docker cp {script_src} {syncd_ibv}:/tmp/')
        cmd_output = engines.dut.run_cmd('echo $?')
        assert '0' in cmd_output, "Docker copy finished with error"

    with allure.step('Delete all sdk dumps before fw crash script'):
        engines.dut.run_cmd('sudo rm -Rf {}sai-dfw*'.format(sdk_dump_folder))

    with allure.step("Rotate logs"):
        logging.info("Rotate logs")
        system.log.rotate_logs()

    with allure.step('Capture boot time before FW event (to prove no reboot)'):
        boot_time_before = engines.dut.run_cmd('uptime -s').strip()
        logging.info(f"Boot time before FW event: {boot_time_before}")

    try:
        with allure.step('Exec sxd api crash fw from {} docker'.format(syncd_ibv)):
            cmd_output = engines.dut.run_cmd(
                'docker exec -i {} bash -c "python /tmp/sxd_api_crash_fw.py --device_id 1"'.format(syncd_ibv))
            assert "trigger_stack_overflow" in cmd_output, "SXD API CRASH script failed"

        with allure.step("Run nv show system log command follow to view system logs"):
            logging.info("Run nv show system log command follow to view system logs")
            show_output = system.log.file.show_log(exit_cmd='q', expected_str=' ')

        with allure.step('Verify updated SDK message in the logs as expected'):
            logging.info('Verify updated SDK message in the logs as expected')
            ValidationTool.verify_expected_output(show_output, 'FW test event').verify_result()

        timeout_in_seconds = 30
        with allure.step(f'Validate if sdk_fw_dump created after {timeout_in_seconds} sec timeout'):
            time.sleep(timeout_in_seconds)
            cmd_output = engines.dut.run_cmd('ls {}'.format(sdk_dump_folder))
            assert 'sai-dfw' in cmd_output, \
                f"Warning-severity SDK dump not created in {sdk_dump_folder}"
            file_list = cmd_output.split()
            sai_dfw_files = [file for file in file_list if file.startswith("sai-dfw-")]
            sdk_dump = sai_dfw_files[0]

        with allure.step('Validate system stayed up: warning event must not crash syncd or reboot'):
            logging.info("Verify warning-severity FW event did not crash syncd or reboot the system")
            running = engines.dut.run_cmd('docker inspect -f "{{.State.Running}}" ' + syncd_ibv).strip()
            assert running == 'true', \
                f"{syncd_ibv} is not running after the FW event - a warning-severity event must not crash syncd"
            boot_time_after = engines.dut.run_cmd('uptime -s').strip()
            assert boot_time_after == boot_time_before, \
                (f"System rebooted (boot time {boot_time_before} -> {boot_time_after}) - "
                 f"a warning-severity FW event must not reboot the system")

        with allure.step('Validate upload sdkdump to sonic-mgmt'):
            logging.info('Validate upload sdkdump to sonic-mgmt')
            player_engine = engines['sonic_mgmt']
            player_engine.run_cmd(
                'sshpass -p {0} scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no {1}@{2}:{3}{4} {5}'.
                format(engines.dut.password, engines.dut.username, engines.dut.ip, sdk_dump_folder,
                       sdk_dump, NvosConst.MARS_RESULTS_FOLDER))

            cmd_output = player_engine.run_cmd('ls {0} | grep {1}'.format(NvosConst.MARS_RESULTS_FOLDER, sdk_dump))
            assert sdk_dump in cmd_output, 'sdk dump not in results folder'

            logging.info('Delete dump file in Mars directory')
            player_engine.run_cmd('rm -f {0}{1}'.format(NvosConst.MARS_RESULTS_FOLDER, sdk_dump))
    finally:
        # No recovery/reboot here: a warning-severity FW event does not crash the
        # system (unlike test_fatal_mode). Calling recover_after_fw_crash would
        # force an unnecessary reboot on IB base systems and hang on Taipan, whose
        # wait_on_system_reboot waits for an auto-reboot that never happens.
        with allure.step('Clean up warning-severity SDK dumps'):
            logging.info("Clean up warning-severity SDK dumps")
            engines.dut.run_cmd('sudo rm -Rf {}sai-dfw*'.format(sdk_dump_folder))
