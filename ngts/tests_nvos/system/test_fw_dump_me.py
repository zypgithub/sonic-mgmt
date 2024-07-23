from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from infra.tools.general_constants.constants import DefaultConnectionValues
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
    Test flow:
        1. Upload fw crush script to switch
        2. Copy script to syncd-ibv0 container
        3. Execute fw stuck script
        4. Validate logs and sdk dump created
        5. Try to download sdk dump to shared location
        6. Validate and delete
    """
    system = System(None)
    ibv_num = str(random.randint(0, devices.dut.asic_amount - 1) if hasattr(devices.dut, 'asic_amount') else '')
    # just multi asic systems have asic_amount attribute
    syncd_ibv = "syncd-ibv0{}".format(ibv_num)
    sdk_dump_folder = "/var/log/mellanox/sdk-dumps{}/".format('_dev{}'.format(ibv_num) if ibv_num else '')

    with allure.step('Upload sdk fw crush file to switch'):
        player_engine = engines['sonic_mgmt']
        player_engine.upload_file_using_scp(dest_username=devices.dut.default_username,
                                            dest_password=devices.dut.default_password,
                                            dest_folder=NvosConst.DESTINATION_FW_SCRIPT_PATH,
                                            dest_ip=engines.dut.ip,
                                            local_file_path=NvosConst.FW_DUMP_ME_SCRIPT_PATH)

    with allure.step('Copy sxd api crash fw file to the {} container'.format(syncd_ibv)):
        engines.dut.run_cmd('sudo docker cp /var/tmp/sxd_api_crash_fw.py {}:/tmp/'.format(syncd_ibv))
        cmd_output = engines.dut.run_cmd('echo $?')
        assert '0' in cmd_output, "Docker copy finished with error"

    with allure.step('Delete all sdk dumps before fw crash script'):
        engines.dut.run_cmd('sudo rm -Rf {}sai-dfw*'.format(sdk_dump_folder))

    with allure.step("Rotate logs"):
        logging.info("Rotate logs")
        system.log.rotate_logs()

    try:
        with allure.step('Exec sxd api crash fw from {} docker'.format(syncd_ibv)):
            cmd_output = engines.dut.run_cmd(
                'docker exec -i {} bash -c "python /tmp/sxd_api_crash_fw.py --device_id 1"'.format(syncd_ibv))
            assert "trigger_stack_overflow" in cmd_output, "SXD API CRASH script failed"

        with allure.step("Run nv show system log command follow to view system logs"):
            logging.info("Run nv show system log command follow to view system logs")
            show_output = system.log.show_log(exit_cmd='q', expected_str=' ')

        with allure.step('Verify updated SDK message in the logs as expected'):
            logging.info('Verify updated SDK message in the logs as expected')
            ValidationTool.verify_expected_output(show_output, 'FW test event').verify_result()

        timeout_in_seconds = 30
        with allure.step(f'Validate if sdk_fw_dump created after {timeout_in_seconds} sec timeout'):
            time.sleep(timeout_in_seconds)
            cmd_output = engines.dut.run_cmd('ls {}'.format(sdk_dump_folder))
            assert 'sai-dfw' in cmd_output, "Sdk dump not created"
            sdk_dump = cmd_output.split()[0]

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
        with allure.step('Reboot system'):
            logging.info("Reboot system")
            system.reboot.action_reboot(params='force').verify_result()
