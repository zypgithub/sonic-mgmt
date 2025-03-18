import logging
import re
import os
import glob
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.constants.constants import InfraConst
from ngts.constants.performance_constants import PerfConsts, Cl_Consts
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.helpers.run_process_on_host import run_process_on_host

logger = logging.getLogger()


class CumulusGeneralCli(NvueGeneralCli):

    def __init__(self, engine, device):
        super().__init__(engine, device)

    def install_traffic_generator(self, latest_version=True):
        """
        Function verifies the traffic generator is functional post deploy on CL OS

        Function first unpack sdk verification git on top of switch
        install necessary packages for sdk verification git to be functional
        then, run test to verify  sdk verification git works correctly and
        is running traffic generation script.
        :return: None
        """
        with allure.step('Get SDK_VER git'):
            sdk_version = self.get_sdk_version()
            if latest_version:
                sdk_version = self.get_latest_sdk_version(cur_sdk_version=sdk_version)

            deb_file_path = os.path.join(PerfConsts.SDK_DEB_DIR_TEMPLATE.format(SDK_VERSION=sdk_version),
                                         PerfConsts.SDK_DEB_FILE_TEMPLATE.format(SDK_VERSION=sdk_version))
            self.engine.copy_file(source_file=f'{deb_file_path}',
                                  dest_file=f'{PerfConsts.SDK_DEB_FILE_TEMPLATE.format(SDK_VERSION=sdk_version)}',
                                  file_system='/tmp/', overwrite_file=True, verify_file=False)
            self.engine.run_cmd(f'sudo dpkg -i /tmp/{PerfConsts.SDK_DEB_FILE_TEMPLATE.format(SDK_VERSION=sdk_version)}')

            self.engine.copy_file(source_file=f'{PerfConsts.REQUIRMENTS_DIR}/{PerfConsts.REQUIRMENTS_FILE}',
                                  dest_file=f'./{PerfConsts.REQUIRMENTS_FILE}', file_system='/tmp/',
                                  overwrite_file=True, verify_file=False)

        with allure.step('pip dependencies'):
            self.install_pip_dependencies()

        with allure.step('apt get'):
            self.install_apt_get_pkg()

        with allure.step('Prepare SDK_VER git to run tests'):
            self.engine.run_cmd(f"sudo {Cl_Consts.CL_PYTHON_PATH} {PerfConsts.DVS_RUN_TEST_PATH} -si")

    def install_pip_dependencies(self):
        self.engine.run_cmd('sudo apt-get update -y')
        self.engine.run_cmd('sudo apt install python3.11 -y')
        self.engine.run_cmd('sudo mkdir /home/cumulus/venv')
        self.engine.run_cmd('sudo apt install python3.11-venv -y')
        self.engine.run_cmd('python -m venv sdk_env --system-site-packages')
        self.engine.run_cmd('sudo /home/cumulus/sdk_env/bin/pip install --upgrade pip --root-user-action=ignore')
        self.engine.run_cmd('sudo /home/cumulus/sdk_env/bin/pip install -r /tmp/requirements.txt --root-user-action=ignore')

    def install_apt_get_pkg(self):
        self.engine.run_cmd('sudo apt-get install build-essential -y')
        self.engine.run_cmd('sudo apt-get install swig -y')
        self.engine.run_cmd('sudo apt-get install kmod -y')
        self.engine.run_cmd('sudo apt-get install pciutils -y')
        self.engine.run_cmd('sudo apt-get install dmidecode -y')
        self.engine.run_cmd('sudo touch /var/log/syslog')
        self.engine.run_cmd('sudo apt-get install python3-dev -y')

    def get_sdk_version(self):
        sdk_version_output = self.engine.run_cmd(InfraConst.CMD_GET_SDK_VERSION, validate=True)
        sdk_version = re.search(r"SX-SDK ETH (\d+\.\d+\.\d+)", sdk_version_output).group(1)
        return sdk_version

    def _onie_nos_install_image(self, serial_engine, image_url, expected_patterns):
        logger.info('Install image using url')
        _, index = serial_engine.run_cmd(
            f'{NvosConst.ONIE_NOS_INSTALL_CMD} {image_url}', expected_patterns,
            timeout=self.device.install_from_onie_timeout)
        logger.info(f'"{expected_patterns[index]}" pattern found')
        if index == 1:  # found "boot:" pattern and waiting for enter
            return self._complete_cumulus_installation(serial_engine, num_of_attempts=3)
        return index

    def _complete_cumulus_installation(self, serial_engine, num_of_attempts):
        logger.info("Send enter to continue cumulus installation")
        _, index = serial_engine.run_cmd('\r', self.device.install_success_patterns,
                                         timeout=self.device.install_from_onie_timeout, send_without_enter=True)
        logger.info(f'"{self.device.install_success_patterns[index]}" pattern found')
        if index == 1 and num_of_attempts > 0:  # boot: pattern  -> enter and continue
            self._complete_cumulus_installation(serial_engine, --num_of_attempts)

    def remote_reboot(self, topology_obj):
        serial_engine = self.enter_serial_connection_context(topology_obj)

        super().remote_reboot(topology_obj)

        try:
            logging.info(f"Waiting for '{NvosConst.INSTALL_BOOT_PATTERN}' pattern")
            _, index = serial_engine.run_cmd('', [NvosConst.INSTALL_BOOT_PATTERN], timeout=60,
                                             send_without_enter=True)
            logger.info(f'"{NvosConst.INSTALL_BOOT_PATTERN}" pattern found')
            if index == 0:
                logging.info("sending enter")
                serial_engine.run_cmd('\r', expected_value='.*', send_without_enter=True)
        except BaseException:
            logging.info(f"{NvosConst.INSTALL_BOOT_PATTERN} was not found - will continue")

    def _wait_nos_to_become_functional(self, engine, topology_obj="", dut_alias=None, serial_engine=None):
        serial_engine = self.enter_serial_connection_context(topology_obj, dut_alias)

        with allure.step('Set default password'):
            logging.info(f"Login using default user {self.device.default_username}")
            _, index = serial_engine.run_cmd(self.device.default_username, ["Password:"], timeout=5)
            logging.info(f"Enter default password {self.device.manufacture_password}")
            _, index = serial_engine.run_cmd(self.device.manufacture_password, ["Current password:"], timeout=5)
            logging.info(f"Enter default password {self.device.manufacture_password} again")
            _, index = serial_engine.run_cmd(self.device.manufacture_password, ["New password:"], timeout=5)
            logging.info(f"Enter new password {self.device.default_password}")
            _, index = serial_engine.run_cmd(self.device.default_password, ["Retype new password:"], timeout=5)
            logging.info(f"Enter new password {self.device.default_password} again")
            _, index = serial_engine.run_cmd(self.device.default_password, '.*', timeout=10)

        with allure.step('Wait until switch is up'):
            engine.disconnect()  # force engines.dut to reconnect
            DutUtilsTool.wait_for_cumulus_to_become_functional(engine=engine)

    def init_telemetry_keys(self):
        pass

    def apply_basic_config(self, topology_obj, setup_name, platform_params, reload_before_qos=False,
                           disable_ztp=False, configure_dns=True):
        pass

    def disable_ztp(self, disable_ztp=False):
        pass

    def _verify_dockers_are_up(self, dockers_list):
        pass
