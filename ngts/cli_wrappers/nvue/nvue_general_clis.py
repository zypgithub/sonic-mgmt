from json.decoder import JSONDecodeError

from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from infra.tools.general_constants.constants import DefaultConnectionValues
from infra.tools.linux_tools.linux_tools import scp_file
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.sonic.sonic_general_clis import *
from ngts.constants.constants import InfraConst
from ngts.constants.constants import MarsConstants
from ngts.nvos_constants.constants_nvos import NvosConst, ActionConsts, SystemConsts, ConfState, TopologyConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.GrubMenuTool import GrubMenuTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.SerialConsoleTool import SerialConsoleTool
from ngts.tests_nvos.general.post_upgrade_switch.constants import InstallSteps
from ngts.tests_nvos.general.post_upgrade_switch.install_steps_timer import InstallStepsTimer
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.test_secure_boot.constants import SecureBootConsts
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class NvueGeneralCli(SonicGeneralCliDefault):
    """
    This class is for general cli commands for NVOS only
    Most of the methods are inherited from SonicGeneralCli
    """

    def __init__(self, engine, device=None, cli_obj=None, dut_alias='dut'):
        self.engine = engine
        self.device = device
        self.cli_obj = cli_obj
        self.dut_alias = dut_alias

    @retry(Exception, tries=5, delay=30)
    def generate_techsupport(self, duration=60):
        """
        Generate sysdump for a given time frame in seconds
        if 0/'0'/False so we will run it without the since option.
        :param duration: time frame in seconds
        :return: dump path
        """
        with allure.step('Generate Tech-support'):
            add_the_since_option = duration and duration != '0'
            since = 'since' if add_the_since_option else ''
            since_time = f"\"-{duration} seconds\"" if add_the_since_option else ''
            output = NvueSystemCli.action_generate_techsupport(self.engine, f'system tech-support {since} {since_time}')
            return SystemConsts.TECHSUPPORT_FILES_PATH + output.splitlines()[-2].split(" ")[-1]

    @retry(Exception, tries=25, delay=10)
    def verify_dockers_are_up(self, dockers_list=NvosConst.DOCKERS_LIST):
        """
        Verifying the dockers are in up state during a specific time interval
        :param dockers_list: list of dockers to check
        :return: None, raise error in case of one or more dockers are down
        """
        with allure.step("Validate dockers are up"):
            NvueGeneralCli._verify_dockers_are_up(self, dockers_list)

    def show_setup_versions(self):
        out = self.device.show_setup_versions(self.engine)
        return out

    def is_dut_supports_image(self, base_version_url, dut_name, cli_type) -> bool:
        """
        This method checks whether the given base version url is supported for the given dut , or not
        :return: True/False
        """
        image_supports = True
        logger.info(
            f"dut: {dut_name} {'supports' if image_supports else 'does not support'} version: {base_version_url}")
        return image_supports

    def _verify_dockers_are_up(self, dockers_list):
        """
        Verifying the dockers are in up state during a specific time interval
        :param dockers_list: list of dockers to check
        :return: None, raise error in case of one or more dockers are down
        """
        err_flag = True
        for docker in dockers_list:
            cmd_output = self.engine.run_cmd('docker ps | grep {}'.format(docker))
            if NvosConst.DOCKER_STATUS_UP not in cmd_output:
                logger.error("{} docker is not up".format(docker))
                err_flag = False
        assert err_flag, "one or more dockers are down"

    def verify_installed_extensions_running(self):
        """
        This method is not relevant for NVOS (at least for now)
        """
        pass

    def show_version(self, validate=False):
        return self.engine.run_cmd('nv show system version')

    def _get_image_path_and_url(self, nos_image: str):
        if nos_image.startswith('/auto/'):
            image_path = nos_image
            image_url = f"{MarsConstants.HTTP_SERVER_NBU_NFS}{image_path}"
        else:
            assert nos_image.startswith(
                'http://'), f'Argument "nos_image" should start with one of ["/auto/", "http://"]. ' \
                f'Actual "nos_image"={nos_image}'
            image_path = f'/auto/{nos_image.split("/auto/")[1]}'
            image_url = nos_image
        return image_path, image_url

    @retry(Exception, tries=3, delay=20)
    def _wget_image_on_onie(self, serial_engine, image_url, filename=None):
        """
        Download image using wget with retry logic to handle communication failures
        :param serial_engine: serial connection engine
        :param image_url: URL of the image to download
        :param filename: optional filename to save as (defaults to extracting from URL)
        :return: filename of downloaded image
        """
        InstallStepsTimer.add_timestamp(InstallSteps.ONIE_NOS_INSTALL, True)
        logger.info(f'Downloading image using wget: {image_url}')

        if filename is None:
            # Extract filename from URL
            filename = image_url.split('/')[-1]

        # Run wget command with retry logic
        wget_cmd = f'wget {image_url}'
        _, index = serial_engine.run_cmd(
            wget_cmd,
            ['100%', 'ERROR', 'failed', 'wget:'],
            timeout=60
        )

        if index == 0:  # Success - found '100%'
            logger.info(f'Successfully downloaded image: {filename}')
            return filename
        else:
            # Wget failed - raise exception to trigger retry
            raise Exception(f'wget failed with pattern index {index}')

    @retry(Exception, tries=3, delay=20)
    def _onie_nos_install_local_image(self, serial_engine, filename, expected_patterns):
        """
        Install image using onie-nos-install with local file
        :param serial_engine: serial connection engine
        :param filename: local filename to install
        :param expected_patterns: patterns to expect during installation
        :return: index of matched pattern
        """
        logger.info(f'Installing local image: {filename}')

        # Add ASIC type mismatch pattern to expected patterns
        asic_mismatch_pattern = "Do you still wish to install this image?"
        extended_patterns = expected_patterns + [asic_mismatch_pattern]

        _, index = serial_engine.run_cmd(
            f'{NvosConst.ONIE_NOS_INSTALL_CMD} {filename}',
            extended_patterns,
            timeout=self.device.install_from_onie_timeout
        )

        # Check if ASIC type mismatch occurred
        if index == len(expected_patterns):  # ASIC mismatch pattern matched
            logger.info(f"ASIC type mismatch detected for image: {filename}")
            logger.info("The image you're trying to install is of a different ASIC type as the running platform's ASIC")
            raise Exception(f"Image {filename} is not supported on this system - ASIC type mismatch")

        logger.info(f'"{expected_patterns[index]}" pattern found')
        return index

    def _onie_nos_install_image(self, serial_engine, image_url, expected_patterns):
        InstallStepsTimer.add_timestamp(InstallSteps.ONIE_NOS_INSTALL, True)
        logger.info('Install image using url')
        _, index = serial_engine.run_cmd(
            f'{NvosConst.ONIE_NOS_INSTALL_CMD} {image_url}', expected_patterns,
            timeout=self.device.install_from_onie_timeout)
        logger.info(f'"{expected_patterns[index]}" pattern found')
        return index

    def _scp_image(self, ssh_engine, image_path, file_name_on_switch):
        logger.info('onie-nos-install failed because of wget error. install with scp')
        with allure.step('Upload nvos to switch with scp'):
            if not image_path.startswith('/auto'):
                image_path = f'/auto/{image_path.split("/auto/")[1]}'
            scp_engine = LinuxSshEngine(ssh_engine.ip,
                                        DefaultConnectionValues.ONIE_USERNAME,
                                        DefaultConnectionValues.ONIE_PASSWORD)
            scp_file(scp_engine, image_path, file_name_on_switch, print_output=True)

    def _install_image_on_onie(self, serial_engine, ssh_engine, image_path, image_url):
        wget_error = False

        try:
            # Phase 1: Download image using wget with retry logic
            logger.info('Phase 1: Downloading image using wget with retry logic')
            downloaded_filename = self._wget_image_on_onie(serial_engine, image_url)

            # Phase 2: Install image using onie-nos-install
            logger.info('Phase 2: Installing downloaded image using onie-nos-install')
            found_pattern_index = self._onie_nos_install_local_image(
                serial_engine,
                downloaded_filename,
                self.device.install_success_patterns
            )
            logger.info(f'*** Image {image_path} successfully installed ***')
            InstallStepsTimer.add_timestamp(InstallSteps.INSTALL_SUCCESS)
            return
        except Exception as e:
            logger.info('Failed for wget error. Using SCP fallback')
            wget_error = True

        if wget_error:
            logger.info('Fallback: Using SCP to upload image')
            file_on_switch = '/tmp/nos.bin'
            self._scp_image(ssh_engine, image_path, file_on_switch)
            found_pattern_index = self._onie_nos_install_local_image(serial_engine, file_on_switch,
                                                                     self.device.install_success_patterns)
            assert found_pattern_index == self.device.install_patterns[self.device.login_pattern], \
                "Failed to install image on onie"

        logger.info(f'*** Image {image_path} successfully installed ***')
        InstallStepsTimer.add_timestamp(InstallSteps.INSTALL_SUCCESS)

    def install_nos_using_onie_in_serial(self, nos_image: str, ssh_engine, topology_obj, dut_alias='dut',
                                         serial_engine: PexpectSerialEngine = None):
        with allure.step("Get image path and url"):
            image_path, image_url = self._get_image_path_and_url(nos_image)

        with allure.step('Get serial connection'):
            serial_engine = serial_engine or self.enter_serial_connection_context(topology_obj, dut_alias)

        with allure.step(f'Install image {image_url} using {NvosConst.ONIE_NOS_INSTALL_CMD}'):
            self._install_image_on_onie(serial_engine, ssh_engine, image_path, image_url)

    def deploy_onie(self, image_path, in_onie, fw_pkg_path, platform_params, topology_obj, dut_alias='dut'):
        assert in_onie, 'NVOS install failed - not in ONIE'
        self.install_image_onie(self.engine, image_path, platform_params, topology_obj, dut_alias)

    def install_image_via_onie(self, topology_obj, image_path):
        self.deploy_image(topology_obj, image_path, None, None, None, 'onie', None, None, None)

    def deploy_image(self, topology_obj, image_path, apply_base_config=False, setup_name=None,
                     platform_params=None, deploy_type='sonic', reboot_after_install=None, fw_pkg_path=None,
                     set_timezone='Israel', disable_ztp=False, configure_dns=False, destination_hwsku=None,
                     setup_info=None, dut_alias='dut', deploy_fanout_threads=None,):
        with allure.step('Preparing switch for installation'):
            logger.info("Begin: Preparing switch for installation ")
            in_onie = self.prepare_for_installation(topology_obj, dut_alias)
            logger.info("End: Preparing switch for installation ")

        self.deploy_onie(image_path, in_onie, fw_pkg_path, platform_params, topology_obj, dut_alias)

    def install_image_onie(self, engine, image_path, platform_params, topology_obj, dut_alias='dut'):
        with allure.step('Create serial connection'):
            serial_engine = self.enter_serial_connection_context(topology_obj, dut_alias)
        with allure.step('Install image onie - NVOS'):
            self.install_nos_using_onie_in_serial(image_path, engine, topology_obj, dut_alias, serial_engine)

        with allure.step("Complete installation"):
            self._wait_nos_to_become_functional(engine, topology_obj, dut_alias, serial_engine)

    def _wait_nos_to_become_functional(self, engine, topology_obj="", dut_alias='dut', serial_engine: PexpectSerialEngine = None):
        with allure.step('Ping switch until shutting down'):
            ping_till_alive(should_be_alive=False, destination_host=engine.ip)
        with allure.step('Ping switch until back alive'):
            ping_till_alive(should_be_alive=True, destination_host=engine.ip)
        with allure.step('wait for System is ready in serial'):
            DutUtilsTool.wait_for_system_ready_in_serial(topology_obj, serial_engine, self.device.timeout_system_is_ready)
            InstallStepsTimer.add_timestamp(InstallSteps.SYSTEM_IS_READY_AFTER_MANUFACTURE)

    @staticmethod
    def diff_config(engine, revision_1='', revision_2='', output_type='json'):
        logging.info("Running 'nv config diff' on dut")
        cmd = 'nv config diff ' + revision_1 + ' ' + revision_2
        output = engine.run_cmd(cmd + ' --output {output_type}'.format(output_type=output_type))
        return output

    @staticmethod
    def history_config(engine, revision='', output_type='json'):
        logging.info("Running 'nv config history' on dut")
        cmd = 'nv config history ' + revision
        output = engine.run_cmd(cmd + ' --output {output_type}'.format(output_type=output_type))
        return output

    @staticmethod
    def show_config(engine, revision='applied', output_type='json', param=''):
        logging.info("Running 'nv config show' on dut")
        output = engine.run_cmd('nv config show {param} --rev {revision} --output {output_type}'.format(output_type=output_type, revision=revision, param=param))
        return output

    @staticmethod
    def replace_config(engine, file, output_type='json', verify_execution=False):
        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(engine)
        logging.info("Running 'nv config replace' on dut")
        if verify_execution:
            return SendCommandTool.execute_command(NvueGeneralCli._replace_config, engine, file, output_type).verify_result()
        else:
            return NvueGeneralCli._replace_config(engine, file, output_type)

    @staticmethod
    def _replace_config(engine, file, output_type='json'):
        output = engine.run_cmd('nv config replace {file} --output {output_type}'.format(file=file,
                                                                                         output_type=output_type))
        return output

    @staticmethod
    def patch_config(engine, file):
        logging.info("Running 'nv config patch' on dut")
        output = engine.run_cmd('nv config patch {file}'.format(file=file))
        return output

    @staticmethod
    def save_config(engine):
        logging.info("Running 'nv config save' on dut")
        output = engine.run_cmd('nv config save')

        return output

    @staticmethod
    def apply_config(engine, ask_for_confirmation=False, option='', validate_apply_message='', rev_id="",
                     skip_no_config_diff_err=True, verify_execution=False, client_certs_after_apply: CertInfo = None):
        """
        Apply configuration
        :param option: could be [-y, --assume-yes, --assume-no, --confirm-yes, --confirm-no, --confirm-status]
        :param engine: ssh engine object
        :param ask_for_confirmation: True or False
        """
        if verify_execution:
            return SendCommandTool.execute_command(NvueGeneralCli._apply_config, engine, ask_for_confirmation, option,
                                                   validate_apply_message, rev_id, skip_no_config_diff_err).verify_result()
        else:
            return NvueGeneralCli._apply_config(engine, ask_for_confirmation, option, validate_apply_message, rev_id, skip_no_config_diff_err)

    @staticmethod
    def _apply_config(engine, ask_for_confirmation=False, option='', validate_apply_message='', rev_id="",
                      skip_no_config_diff_err=True):
        """
        Apply configuration
        :param option: could be [-y, --assume-yes, --assume-no, --confirm-yes, --confirm-no, --confirm-status]
        :param engine: ssh engine object
        :param ask_for_confirmation: True or False
        """
        logging.info("Checking the config to be applied")
        NvueGeneralCli.diff_config(engine=engine)

        logging.info("Running 'nv {} config apply {} ' on dut".format(option, rev_id))
        if ask_for_confirmation:
            if isinstance(engine, PexpectSerialEngine):
                output = engine.run_cmd_and_get_output('nv config apply --assume-yes')
            else:
                output = engine.run_cmd_set(['nv config apply', 'y'], patterns_list=[r"Are you sure?"],
                                            tries_after_run_cmd=2)
            if NvosConst.DECLINED_APPLY_MSG in output:
                output = "Error: " + output
            elif NvosConst.Y_COMMAND_NOT_FOUND in output and ConfState.APPLIED in output:
                output = ConfState.APPLIED + NvueGeneralCli.get_rev_id(output)
            output = output.replace(NvosConst.Y_COMMAND_NOT_FOUND, "")
        elif validate_apply_message:
            output = engine.run_cmd('nv {option} config apply'.format(option=option))
            assert validate_apply_message in output, 'Message {0} not exist in output {1}'. \
                format(validate_apply_message, output)
        else:
            output = engine.run_cmd('nv {option} config apply {rev}'.format(option=option, rev=rev_id))

        if skip_no_config_diff_err and NvosConst.NO_CONFIG_DIFF_APPLY_MSG in output:
            output = ConfState.APPLIED

        return output

    @staticmethod
    def detach_config(engine):
        logging.info("Running 'nv config detach' on dut")
        output = engine.run_cmd('nv config detach')
        return output

    @staticmethod
    def attach_config(engine, rev_id):
        logging.info(f"Running 'nv -y config attach {rev_id}' on dut")
        output = engine.run_cmd(f'nv -y config attach {rev_id}')
        return output

    @staticmethod
    def delete_config(engine, rev_id):
        logging.info(f"Running 'nv config delete {rev_id}' on dut")
        output = engine.run_cmd(f'nv config delete {rev_id}')
        return output

    @staticmethod
    def revision_config(engine, output_type='json'):
        logging.info(f"Running 'nv config revision' on dut")
        output = engine.run_cmd(f'nv config revision -o {output_type}')
        return output

    @staticmethod
    def apply_empty_config(engine):
        logging.info("Running 'nv config apply empty' on dut")
        output = engine.run_cmd_set(['nv config apply empty', 'y'],
                                    patterns_list=[r"Are you sure?"],
                                    tries_after_run_cmd=1)
        if 'Declined apply after warnings' in output or "Aborted apply after warnings" in output:
            output = "Error: " + output
        elif 'y: command not found' in output and 'applied' in output:
            output = 'applied'
        return "applied" in output

    @staticmethod
    def list_commands(engine):
        logging.info("Running 'nv list-commands' on dut")
        output = engine.run_cmd('nv list-commands')
        return output

    @staticmethod
    def search_in_list_commands(engine, string):
        logging.info(f"Running 'nv list-commands | grep '{string}'' on dut")
        output = engine.run_cmd(f'nv list-commands | grep "{string}"')
        return output

    def reboot(self, engine, save_config=False, wait_after_ping=120):
        if save_config:
            logging.info("Saving the config")
            engine.run_cmd("nv config save")
        logging.info("Rebooting the dut using sudo reboot")
        engine.reload(['sudo reboot'], wait_after_ping=wait_after_ping)

    def get_asic_model(self, engine):
        output = engine.run_cmd("nv show platform -o json")
        try:
            output = json.loads(output)
        except JSONDecodeError as j:
            logging.error("Interface output is not a valid JSON object")
            logging.error(f"Output is : {output}")
            raise j
        return output['asic-model']

    def remote_reboot_nvue(self, topology_obj, dut_alias='dut'):
        '''
        @summary: perform remote reboot from the physical server using the noga remote reboot command,
        usually the command should be like this: '/auto/mswg/utils/bin/rreboot <ip|hostname>'
        '''
        # TODO align the remote reboot of NVOS with the general remote reboot function in general_clis_common
        alias_serial = dut_alias + '_serial'
        cmd = topology_obj.players[alias_serial]['attributes'].noga_query_data['attributes']['Specific'][
            'remote_reboot']
        assert cmd, "Reboot command is empty"

        server_ip = self.get_site_server_ip(topology_obj)

        # cmd = SshPassCmdBuilder(os.getenv("TEST_SERVER_USER"), os.getenv("TEST_SERVER_PASSWORD"), server_ip, cmd_to_execute=cmd).set_ssn().build()
        # CmdRunner().run_cmd_in_process(cmd)
        ssh_conn = LinuxSshEngine(ip=server_ip, username=os.getenv("TEST_SERVER_USER"),
                                  password=os.getenv("TEST_SERVER_PASSWORD"))
        ssh_conn.run_cmd(cmd)

    def get_site_server_ip(self, topology_obj):
        setup_site = topology_obj.players['dut_serial']['attributes'].noga_query_data['attributes']['Common']['Site']
        if setup_site and setup_site in TopologyConsts.site_server_ip.keys():
            server_ip = TopologyConsts.site_server_ip[setup_site]
        else:
            server_ip = TopologyConsts.site_server_ip[TopologyConsts.MTL]  # default
        return server_ip

    def enter_serial_connection_context(self, topology_obj, dut_alias='dut'):
        '''
        @summary: in this function we will execute the rcon command and return the serial engine
        :return: serial connection engine
        '''
        return SerialConsoleTool.get_serial_console_session(topology_obj, dut_alias)

    def enter_onie_mode(self, topology_obj, onie_menu_entry, dut_alias='dut'):
        '''
        @summary: In this function we want to enter ONIE install/update mode.

        We are doing so by the following steps:
            1. Create a serial engine
            2. Trigger remote reboot
            3. Wait for GRUB menu to appear:
                a. If the NVOS GRUB menu appears, select the ONIE entry (pressing down 2 key arrows)
                b. If the ONIE GRUB menu appears, do nothing — the selected entry will auto-trigger after 5 seconds

        @param onie_menu_entry: The GRUB menu entry to select under the ONIE bootloader.
                                Common values are:
                                  - 'ONIE: Install OS'
                                  - 'ONIE: Update ONIE'
        '''
        with allure.step("Initializing serial connection to device"):
            serial_engine = self.enter_serial_connection_context(topology_obj, dut_alias)

        with allure.step('Executing remote reboot'):
            self.remote_reboot_nvue(topology_obj, dut_alias)

        with allure.step('wait for NVOS/ONIE grub menu'):
            to = 360 if is_bug_active(4028150) else 240
            grub_menu_pointer = 0
            onie_menu_pointer = 1
            esc_grub_pointer = 2

            grub_menu_patterns = ['ONIE\\s+', onie_menu_entry, GrubMenuTool.GRUB_ESC_PATTERN]
            all_patterns = grub_menu_patterns + SecureBootConsts.INVALID_SIGNATURE
            output, respond = serial_engine.run_cmd('', all_patterns, timeout=to, send_without_enter=True)

        if respond != onie_menu_pointer:
            if respond == esc_grub_pointer:
                with allure.step('Grub menu new style handle'):
                    logger.info('Hit ESC on grub new style')
                    output, respond = serial_engine.run_cmd(GrubMenuTool.ESCAPE_CHAR, expected_value=all_patterns,
                                                            timeout=to, send_without_enter=True)
                    time.sleep(1)

            if respond >= len(grub_menu_patterns):
                with allure.step('Secure boot error - handle'):
                    with allure.step('hit Enter till no error message'):
                        while respond >= len(grub_menu_patterns):
                            logger.info('Hit Enter on secure boot error message')
                            output, respond = serial_engine.run_cmd("\r", expected_value=all_patterns, timeout=to,
                                                                    send_without_enter=True)
                            time.sleep(1)

            elif respond == grub_menu_pointer:
                with allure.step("System in NVOS grub menu, entering ONIE grub menu"):
                    GrubMenuTool.select_grub_menu_item(serial_engine, 'ONIE')

                    logger.info("Pressing Enter to enter ONIE grub menu")
                    _, respond = serial_engine.run_cmd('\r',
                                                       expected_value=[
                                                           'Due to security constraints, this option will uninstall your current OS',
                                                           'Answer "YES" to continue',
                                                           '\\*ONIE:.*'
                                                       ],
                                                       timeout=30, send_without_enter=True)

                    if respond != esc_grub_pointer:
                        with allure.step("MLNX-OS system. Enter 'YES' and wait till in ONIE grub menu"):
                            serial_engine.run_cmd('YES', onie_menu_entry, timeout=420)

        with allure.step(f'in ONIE grub menu: Go to {onie_menu_entry}'):
            GrubMenuTool.select_grub_menu_item(serial_engine, onie_menu_entry)

        with allure.step("Waiting for onie prompt"):
            self.wait_for_onie_prompt(serial_engine)

        with allure.step("Send 'onie-stop'"):
            self.send_onie_stop(serial_engine)

    def send_onie_stop(self, serial_engine):
        logger.info('Send: "\\r"')
        output, respond = serial_engine.run_cmd('\r', ['login:', 'ONIE:/ #'], timeout=5, send_without_enter=True)
        logger.info(f'index: {respond} ; output:\n{output}')
        if respond == 0:
            with allure.step('System is secured. Login to ONIE with credentials'):
                logger.info(f'Send line: "{DefaultConnectionValues.ONIE_USERNAME}"')
                output, respond = serial_engine.run_cmd(DefaultConnectionValues.ONIE_USERNAME, '[Pp]assword:',
                                                        timeout=10)
                logger.info(output)
                logger.info(f'Send line: "{DefaultConnectionValues.ONIE_PASSWORD}"')
                output, respond = serial_engine.run_cmd(DefaultConnectionValues.ONIE_PASSWORD, 'ONIE:~ #', timeout=20)
                logger.info(output)

        with allure.step('Send line: "onie-stop"'):
            output, respond = serial_engine.run_cmd('onie-stop', ['done.', 'discover'], timeout=10)
            logger.info(output)

            for _ in range(3):
                time.sleep(1)
                logger.info('Send new line')
                output, respond = serial_engine.run_cmd('\r', '.*', timeout=10, send_without_enter=True)
                logger.info(output)

    def prepare_for_installation(self, topology_obj, dut_alias='dut'):
        '''
        @summary: in this function we will enter onie install mode using remote reboot
        '''
        with allure.step('Prepare for installation: enter ONIE'):
            switch_in_onie = False
            try:
                self.enter_onie(topology_obj, 'ONIE: Install OS', dut_alias)
                switch_in_onie = True
            except Exception as err:
                logger.info("Got an exception: {}".format(str(err)))
                switch_in_onie = False
            finally:
                logger.info(f'Switch in onie: {switch_in_onie}')
                return switch_in_onie

    @retry(Exception, tries=4, delay=5)
    def wait_for_onie_prompt(self, serial_engine):
        serial_engine.run_cmd('\r', ['Please press Enter to activate this console', 'ONIE:/\\s+'], timeout=60)

    @retry(Exception, tries=3, delay=5)
    def enter_onie(self, topology_obj, onie_menu_entry, dut_alias='dut'):
        self.enter_onie_mode(topology_obj, onie_menu_entry, dut_alias)

    def confirm_in_onie_install_mode(self, topology_obj, dut_alias='dut'):
        pass

    @staticmethod
    def get_rev_id(output):
        """

        :param output:
        :return:
        """
        pattern = r"\[rev_id:\s(\d+)\]"
        match = re.search(pattern, output)
        if match:
            return ' ' + match.group(1)

        logger.warning("can't match rev_id after apply")
        return ''

    def get_config_db_from_running_config(self):
        config = self.engine.run_cmd('sudo sonic-cfggen -d --print-data', print_output=False)
        return json.loads(config)
