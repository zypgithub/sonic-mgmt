import logging
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.tests_nvos.conftest import ProxySshEngine
from ngts.tools.test_utils import allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
import shutil
import os
from ngts.constants.constants import LinuxConsts
from ngts.tests_nvos.general.security.authentication_restrictions.constants import RestrictionsConsts
from ngts.tests_nvos.system.clock.ClockConsts import ClockConsts
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils.nvos_general_utils import set_base_configurations_cl
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from infra.tools.linux_tools.linux_tools import scp_file
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine


logger = logging.getLogger()


class CumulusInstallationSteps:

    @staticmethod
    def pre_installation_steps(setup_info, base_version='', target_version=''):
        assert target_version, 'Argument "target_version" must be provided for installing Cumulus'

    @staticmethod
    def post_installation_steps(topology_obj, setup_info):
        """
        Post-installation steps for NVOS NOS
            Update /etc/sudoers file to permit NOPASSWD for sudo
        """
        cli_obj: NvueGeneralCli = setup_info['duts'][0]['cli_obj']
        dut_device = cli_obj.device
        devices = DeviceFactory.create_devices_object(topology_obj)
        serial_engine = ConnectionTool.create_serial_connection(topology_obj, devices)
        logging.info("Updating /etc/sudoers file to permit NOPASSWD for sudo")
        serial_engine.serial_engine.sendline("sudo sed -i --follow-symlinks 's/%sudo.*ALL=(ALL:ALL) ALL/%sudo ALL=(ALL:ALL) NOPASSWD: ALL/' /etc/sudoers")
        serial_engine.serial_engine.expect("password for cumulus:", timeout=15)
        serial_engine.serial_engine.sendline(dut_device.default_password)
        serial_engine.serial_engine.expect("$", timeout=15)
        logging.info("Updated /etc/sudoers file to permit NOPASSWD for sudo")
