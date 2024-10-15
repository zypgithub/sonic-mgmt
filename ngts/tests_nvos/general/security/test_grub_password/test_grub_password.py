import random

import pexpect
import pytest

from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.track_serial_console
def test_grub_password(topology_obj, engines, serial_engine, devices):
    '''
    @summary:
        This test case will check that entering grub command line will requires
        password, the username and password are defined at build stage.
        to enter grub cli, either you can press 'e' to 'c' when grub menu is presented.
        'e' - used to enter edit line
        'c' - grub command line
    :param serial_engine: pexpect serial engine
    '''
    try:
        with allure.step("Rebooting and entering grub cli"):
            serial_engine.serial_engine.sendline("sudo reboot now")
            serial_engine.serial_engine.expect("select which entry is highlighted", timeout=180)

        cli_grub_activation_character = random.choice(['e', 'c'])
        with allure.step("Entering cli command-line using {} character".format(cli_grub_activation_character)):
            serial_engine.serial_engine.send(cli_grub_activation_character)
            res_index = serial_engine.serial_engine.expect(['username', pexpect.TIMEOUT], timeout=30)

        with allure.step('Verify grub is password protected'):
            assert res_index == 0, f"Didn't get username/password prompt " \
                f"when entered '{cli_grub_activation_character}' in grub menu"
    finally:
        with allure.step("Test is Done. remote reboot to recover"):
            with allure.step('run remote reboot'):
                NvueGeneralCli(engines.dut, devices.dut).remote_reboot(topology_obj)
            with allure.step('Ping switch until shutting down'):
                ping_till_alive(should_be_alive=False, destination_host=serial_engine.ip)
            with allure.step('wait for System is ready'):
                DutUtilsTool.wait_for_system_ready_in_serial(topology_obj, serial_engine, devices.dut.system_is_ready_wait_timeout)
