import logging
import re
import os
import glob
import time
import pexpect
from retry import retry

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.constants.constants import InfraConst
from ngts.constants.performance_constants import PerfConsts, Cl_Consts
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.GrubMenuTool import GrubMenuTool
from ngts.tests_nvos.general.security.test_secure_boot.constants import SecureBootConsts
from ngts.scripts.sonic_deploy.cumulus_only_methods import CumulusInstallationSteps

logger = logging.getLogger()


class CumulusGeneralCli(NvueGeneralCli):

    def __init__(self, engine, device):
        super().__init__(engine, device)

    def install_traffic_generator(self, latest_version=False):
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
            sdk_branch = self.get_sdk_branch(sdk_version)
            if latest_version:
                sdk_version = self.get_latest_sdk_version(cur_sdk_version=sdk_version, sdk_branch=sdk_branch)

            deb_file_path = os.path.join(Cl_Consts.SDK_DEB_DIR_TEMPLATE.format(SDK_VERSION=sdk_version),
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
            self.overlay_perf_sys_sdk_to_sys_sdk(sdk_branch)
            self.engine.run_cmd(f"sudo {Cl_Consts.CL_PYTHON_PATH} {PerfConsts.DVS_RUN_TEST_PATH} -si")

    def install_pip_dependencies(self):
        with allure.step('Install pip dependencies'):
            self.engine.run_cmd('sudo apt-get update -y', timeout=60, retry_run=True)
            self.engine.run_cmd('sudo apt install python3.11 -y', timeout=60, retry_run=True)
            self.engine.run_cmd('sudo mkdir /home/cumulus/venv', timeout=20, retry_run=True)
            self.engine.run_cmd('sudo apt install python3.11-venv -y', timeout=120, retry_run=True)
            self.engine.run_cmd('python -m venv sdk_env --system-site-packages', timeout=120, retry_run=True)
            self.engine.run_cmd('sudo /home/cumulus/sdk_env/bin/pip install --upgrade pip --root-user-action=ignore', timeout=120, retry_run=True)
            self.engine.send_cmd_with_retry('sudo /home/cumulus/sdk_env/bin/pip install -r /tmp/requirements.txt --root-user-action=ignore', retries=5, timeout=120)

    def install_apt_get_pkg(self):
        with allure.step('Install apt-get packages'):
            self.engine.run_cmd('sudo apt-get install build-essential -y', timeout=120, retry_run=True)
            self.engine.run_cmd('sudo apt-get install swig -y', timeout=60, retry_run=True)
            self.engine.run_cmd('sudo apt-get install kmod -y', timeout=60, retry_run=True)
            self.engine.run_cmd('sudo apt-get install pciutils -y', timeout=60, retry_run=True)
            self.engine.run_cmd('sudo apt-get install dmidecode -y', timeout=60, retry_run=True)
            self.engine.run_cmd('sudo touch /var/log/syslog', timeout=20, retry_run=True)
            self.engine.run_cmd('sudo apt-get install python3-dev -y', timeout=60, retry_run=True)

    def get_sdk_version(self):
        with allure.step('Get SDK version'):
            sdk_version_output = self.engine.run_cmd(InfraConst.CMD_GET_SDK_VERSION, validate=True)
            sdk_version = re.search(r"SX-SDK ETH (\d+\.\d+\.\d+)", sdk_version_output).group(1)
            return sdk_version

    def _onie_nos_install_image(self, serial_engine, image_url, expected_patterns):
        with allure.step('Install image using ONIE'):
            logger.info('Install image using url')
            _, index = serial_engine.run_cmd(
                f'{NvosConst.ONIE_NOS_INSTALL_CMD} {image_url}', expected_patterns,
                timeout=self.device.install_from_onie_timeout)
            logger.info(f'"{expected_patterns[index]}" pattern found')
            if index == 1:  # found "boot:" pattern and waiting for enter
                return self._complete_cumulus_installation(serial_engine, num_of_attempts=3)
            return index

    def _complete_cumulus_installation(self, serial_engine, num_of_attempts):
        with allure.step('Complete Cumulus installation'):
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
        with allure.step('wait for System is ready in serial'):
            logger.info(f"Waiting for system to be ready")
            system_ready_pattern = 'login:'
            serial_engine.run_cmd('', system_ready_pattern, timeout=2 * self.device.timeout_system_is_ready, send_without_enter=True)
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

    def modify_sudoers_for_cumulus(self):
        with allure.step('Modify sudoers for cumulus user'):
            self.engine.run_cmd(f'echo {self.device.password} | sudo -S echo')
            # Create a temporary sudoers file with the new entry
            sudoers_entry = "cumulus ALL=(ALL) NOPASSWD: ALL\n"

            # Add the entry to sudoers using visudo
            cmd = f'echo "{sudoers_entry}" | sudo EDITOR="tee -a" visudo'
            self.engine.run_cmd(cmd)

            # Verify the entry was added
            sudoers_content = self.read_file('/etc/sudoers', is_sudo=True)
            assert "cumulus ALL=(ALL) NOPASSWD: ALL" in sudoers_content, "Failed to add cumulus user to sudoers file"

    def init_telemetry_keys(self):
        pass

    def apply_basic_config(self, topology_obj, setup_name, platform_params, reload_before_qos=False,
                           disable_ztp=False, configure_dns=True):
        pass

    def disable_ztp(self, disable_ztp=False):
        pass

    def _verify_dockers_are_up(self, dockers_list):
        pass

    def enter_onie_mode(self, topology_obj, onie_menu_entry, dut_alias='dut'):
        '''
        @summary: In this function we want to enter ONIE install/update mode.

        We are doing so by the following steps:
            1. Create a serial engine
            2. Check if the switch is in ONIE install mode
            3. Try to set GRUB to boot ONIE on next reboot (grub-reboot)
            4. Trigger remote reboot
            5. Actively spam ESC keys to interrupt GRUB and catch the menu
            6. Wait for GRUB menu to appear:
                a. If the NVOS GRUB menu appears, select the ONIE entry (pressing down 2 key arrows)
                b. If the ONIE GRUB menu appears, do nothing — the selected entry will auto-trigger after 5 seconds
            7. If login prompt is detected (missed GRUB), retry from Cumulus

        @param onie_menu_entry: The GRUB menu entry to select under the ONIE bootloader.
                                Common values are:
                                  - 'ONIE: Install OS'
                                  - 'ONIE: Update ONIE'
        '''
        with allure.step(f"Initializing serial connection to {dut_alias}"):
            serial_engine = self.enter_serial_connection_context(topology_obj, dut_alias)

        with allure.step('Confirm ONIE boot mode'):
            if self._check_if_in_onie_install_mode(serial_engine):
                return

        with allure.step('Try to set GRUB to boot ONIE on next reboot'):
            self._try_set_grub_reboot_to_onie()

        with allure.step(f'Executing remote reboot on {dut_alias}'):
            self.remote_reboot_nvue(topology_obj, dut_alias)

        with allure.step('wait for NVOS/ONIE grub menu'):
            grub_menu_pointer = 0
            onie_menu_pointer = 1
            cumulus_esc_pointer = 2
            login_prompt_pointer = 3

            grub_menu_patterns = ['ONIE\\s+', onie_menu_entry, GrubMenuTool.CUMULUS_ESC_PATTERN, 'login:']
            all_patterns = grub_menu_patterns + SecureBootConsts.INVALID_SIGNATURE

            # Actively spam ESC keys to catch GRUB menu before it times out
            respond = self._wait_for_grub_with_key_spam(serial_engine, all_patterns, timeout=240)

        if respond == login_prompt_pointer:
            # Missed GRUB window, switch booted to Cumulus - need to reboot from within
            with allure.step('Missed GRUB window, rebooting from Cumulus to ONIE'):
                logger.info('Switch booted to login prompt - missed GRUB window. Trying grub-reboot method.')
                self._reboot_to_onie_from_cumulus(serial_engine, topology_obj, dut_alias, onie_menu_entry)
                return

        if respond != onie_menu_pointer:
            if respond == cumulus_esc_pointer:
                with allure.step('Grub menu new style handle'):
                    logger.info('Hit ESC on grub new style')
                    output, respond = serial_engine.run_cmd(GrubMenuTool.ESCAPE_CHAR, expected_value=all_patterns,
                                                            timeout=240, send_without_enter=True)
                    time.sleep(1)

            if respond >= len(grub_menu_patterns):
                with allure.step('Secure boot error - handle'):
                    with allure.step('hit Enter till no error message'):
                        while respond >= len(grub_menu_patterns):
                            logger.info('Hit Enter on secure boot error message')
                            output, respond = serial_engine.run_cmd("\r", expected_value=all_patterns, timeout=240,
                                                                    send_without_enter=True)
                            time.sleep(1)

            elif respond == grub_menu_pointer:
                with allure.step("System in NVOS grub menu, entering ONIE grub menu"):
                    GrubMenuTool.select_grub_menu_item(serial_engine, 'ONIE')

                    logger.info("Pressing Enter to enter ONIE grub menu")
                    _, respond = serial_engine.run_cmd('\r', expected_value='.*', timeout=30, send_without_enter=True)

        with allure.step(f'in ONIE grub menu: Go to {onie_menu_entry}'):
            GrubMenuTool.select_grub_menu_item(serial_engine, onie_menu_entry)

        with allure.step("Waiting for onie prompt"):
            self.wait_for_onie_prompt(serial_engine)

        with allure.step("Send 'onie-stop'"):
            self.send_onie_stop(serial_engine)

    def _try_set_grub_reboot_to_onie(self):
        '''
        Try to set GRUB to boot ONIE on the next reboot using grub-reboot command.
        This is a best-effort operation - if it fails, we'll fall back to manual GRUB navigation.
        '''
        with allure.step('Try to set GRUB to boot ONIE on next reboot'):
            try:
                logger.info("Trying to set GRUB to boot ONIE on next reboot via grub-reboot")
                # Try different possible ONIE entry names
                for onie_entry in ['ONIE', 'ONIE>ONIE: Install OS', '2', '2>0']:
                    try:
                        output = self.engine.run_cmd(f'sudo grub-reboot "{onie_entry}"', timeout=10)
                        if 'error' not in output.lower() and 'not found' not in output.lower():
                            logger.info(f"Successfully set grub-reboot to '{onie_entry}'")
                            return True
                    except Exception:
                        continue
                logger.info("grub-reboot command not available or failed - will rely on manual GRUB navigation")
            except Exception as e:
                logger.info(f"Could not set grub-reboot: {e} - will rely on manual GRUB navigation")
            return False

    def _wait_for_grub_with_key_spam(self, serial_engine, patterns, timeout=240):
        '''
        Wait for GRUB menu patterns while actively sending ESC keys to interrupt GRUB timeout.
        This increases the chances of catching the GRUB menu before it auto-boots.
        '''
        with allure.step('Wait for GRUB menu with key spam'):
            logger.info("Waiting for GRUB menu while spamming ESC keys to interrupt boot")
            start_time = time.time()
            key_spam_interval = 0.3  # Send ESC every 300ms

            while (time.time() - start_time) < timeout:
                try:
                    # Send ESC key to interrupt GRUB if it's showing
                    serial_engine.run_cmd(GrubMenuTool.ESCAPE_CHAR, '.*', timeout=0.1, send_without_enter=True)
                except pexpect.exceptions.TIMEOUT:
                    pass

                try:
                    # Check for expected patterns with short timeout
                    output, respond = serial_engine.run_cmd('', patterns, timeout=key_spam_interval, send_without_enter=True)
                    logger.info(f'Pattern found at index {respond}: "{patterns[respond]}"')
                    return respond
                except pexpect.exceptions.TIMEOUT:
                    continue

            raise Exception(f"Timeout waiting for GRUB patterns after {timeout} seconds")

    def _reboot_to_onie_from_cumulus(self, serial_engine, topology_obj, dut_alias, onie_menu_entry):
        '''
        When the GRUB window is missed and the switch boots to Cumulus login,
        login to Cumulus, set grub-reboot to ONIE, and reboot.
        '''
        with allure.step('Reboot to ONIE from Cumulus'):
            logger.info("Logging into Cumulus to set grub-reboot and trigger reboot to ONIE")

            # Login to Cumulus via serial
            try:
                serial_engine.run_cmd(self.device.default_username, ['[Pp]assword:'], timeout=10)
                serial_engine.run_cmd(self.device.default_password, ['\\$', '#', 'cumulus@'], timeout=10)
            except Exception as e:
                logger.warning(f"Login with default password failed: {e}, trying alternate passwords")
                try:
                    serial_engine.run_cmd(self.device.manufacture_password, ['\\$', '#', 'cumulus@'], timeout=10)
                except Exception:
                    logger.error("Failed to login to Cumulus - cannot proceed with grub-reboot method")
                    raise

            # Set grub-reboot to ONIE
            logger.info("Setting grub-reboot to ONIE")
            serial_engine.run_cmd('sudo grub-reboot ONIE', ['\\$', '#'], timeout=10)

            # Reboot
            logger.info("Rebooting switch to ONIE")
            serial_engine.run_cmd('sudo reboot', '.*', timeout=5, send_without_enter=False)

            # Wait for GRUB menu with key spam
            grub_menu_patterns = ['ONIE\\s+', onie_menu_entry, GrubMenuTool.CUMULUS_ESC_PATTERN]
            all_patterns = grub_menu_patterns + SecureBootConsts.INVALID_SIGNATURE

            respond = self._wait_for_grub_with_key_spam(serial_engine, all_patterns, timeout=240)

            if respond == 0:  # ONIE\s+ pattern - we're in GRUB menu showing ONIE
                GrubMenuTool.select_grub_menu_item(serial_engine, 'ONIE')
                serial_engine.run_cmd('\r', expected_value='.*', timeout=30, send_without_enter=True)

            # Navigate to the ONIE install entry
            GrubMenuTool.select_grub_menu_item(serial_engine, onie_menu_entry)

            # Wait for ONIE prompt
            self.wait_for_onie_prompt(serial_engine)

            # Send onie-stop
            self.send_onie_stop(serial_engine)

    @retry(exceptions=Exception, tries=2, delay=1)
    def _check_if_in_onie_install_mode(self, serial_engine):
        with allure.step('Check if in ONIE install mode'):
            try:
                output = serial_engine.run_cmd('\r', [], timeout=5, send_without_enter=False)
                output, respond = serial_engine.run_cmd('cat /proc/cmdline', ["boot_reason=install"], timeout=10, send_without_enter=False)
                logger.info('Switch is in ONIE install mode, sending onie-stop')
                self.send_onie_stop(serial_engine)
                return True
            except Exception as e:
                logger.info(f'Switch is not in ONIE install mode')
                return False

    def pre_installation_steps(self, context, threads_dict):
        """Execute Cumulus pre-installation steps"""
        with allure.step('Pre installation steps'):
            CumulusInstallationSteps.pre_installation_steps(context.setup_info, context.base_version, context.target_version)

    def post_installation_steps(self, context, image_helper=None):
        """Execute Cumulus post-installation steps"""
        with allure.step('Post installation steps'):
            CumulusInstallationSteps.post_installation_steps(context.setup_info, context.is_performance)

    def deploy_image_steps(self, topology_obj, setup_name, platform_params, image_url, deploy_type,
                           apply_base_config, reboot_after_install, is_shutdown_bgp, fw_pkg_path,
                           target_image_url='', destination_hwsku=None, setup_info=None, dut_alias=None,
                           fanout_deploy_threads=None, serial_log_analyzers=None, dut_ip='',
                           fanout_target_version=None):
        """Execute Cumulus deploy image steps"""
        with allure.step('Deploy image steps'):
            super().deploy_image_steps(topology_obj, setup_name, platform_params, image_url, deploy_type,
                                       apply_base_config, reboot_after_install, is_shutdown_bgp, fw_pkg_path,
                                       target_image_url, destination_hwsku, setup_info, dut_alias,
                                       fanout_deploy_threads, serial_log_analyzers, dut_ip, fanout_target_version)
