import random

import pexpect
import pytest

from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.GrubMenuTool import GrubMenuTool


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
        dut_device: BaseDevice = devices.dut
        with allure.step("Rebooting and entering grub cli"):
            serial_engine.serial_engine.sendline("sudo reboot now")
            serial_engine.serial_engine.expect(GrubMenuTool.GRUB_ESC_PATTERN, timeout=dut_device.timeout_reboot_to_grub_menu)
            serial_engine.run_cmd(GrubMenuTool.ESCAPE_CHAR, expected_value='select which entry is highlighted',
                                  timeout=dut_device.timeout_reboot_to_grub_menu,
                                  send_without_enter=True)

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
                NvueGeneralCli(engines.dut, devices.dut).remote_reboot_nvue(topology_obj)
            with allure.step('Ping switch until shutting down'):
                ping_till_alive(should_be_alive=False, destination_host=serial_engine.ip)
            with allure.step('wait for System is ready'):
                DutUtilsTool.wait_for_system_ready_in_serial(topology_obj, serial_engine, devices.dut.timeout_system_is_ready)
