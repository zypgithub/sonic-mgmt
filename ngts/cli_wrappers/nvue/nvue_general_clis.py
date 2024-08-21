from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from infra.tools.general_constants.constants import DefaultConnectionValues
from infra.tools.linux_tools.linux_tools import scp_file
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.sonic.sonic_general_clis import *
from ngts.constants.constants import InfraConst
from ngts.constants.constants import MarsConstants
from ngts.nvos_constants.constants_nvos import NvosConst, ActionConsts, SystemConsts, ConfState
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.tests_nvos.general.security.test_secure_boot.constants import SecureBootConsts
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()
server_ip = "10.237.22.60"


class NvueGeneralCli(SonicGeneralCliDefault):

    """
    This class is for general cli commands for NVOS only
    Most of the methods are inherited from SonicGeneralCli
    """

    def __init__(self, engine, device=None):
        self.engine = engine
        self.device = device

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

    def is_dut_supports_image(self, base_version_url, dut_name) -> bool:
        """
        This method checks whether the given base version url is supported for the given dut , or not
        :return: True/False
        """
        image_supports = True
        logger.info(f"dut: {dut_name} {'supports' if image_supports else 'does not support'} version: {base_version_url}")
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

    def _onie_nos_install_image(self, serial_engine, image_url, expected_patterns):
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
            scp_engine = LinuxSshEngine(ssh_engine.ip, DefaultConnectionValues.ONIE_USERNAME,
                                        DefaultConnectionValues.ONIE_PASSWORD)
            scp_file(scp_engine, image_path, file_name_on_switch)

    def _install_image_on_onie(self, serial_engine, ssh_engine, image_path, image_url):
        wget_error = False

        for _ in range(3):
            wget_error = False
            found_pattern_index = self._onie_nos_install_image(serial_engine, image_url,
                                                               self.device.install_success_patterns +
                                                               [NvosConst.INSTALL_WGET_ERROR])
            if found_pattern_index == len(self.device.install_success_patterns):    # wget error
                logger.info('Failed for wget error. wait and retry')
                time.sleep(20)
                wget_error = True
            else:
                break

        if wget_error:
            file_on_switch = '/tmp/nos.bin'
            self._scp_image(ssh_engine, image_path, file_on_switch)
            found_pattern_index = self._onie_nos_install_image(serial_engine, file_on_switch,
                                                               self.device.install_success_patterns)
            assert found_pattern_index == self.device.install_patterns[self.device.login_pattern], \
                "Failed to install image on onie"

        logger.info(f'*** Image {image_path} successfully installed ***')

    def install_nos_using_onie_in_serial(self, nos_image: str, ssh_engine, topology_obj):
        with allure.step("Get image path and url"):
            image_path, image_url = self._get_image_path_and_url(nos_image)

        with allure.step('Create serial connection'):
            serial_engine = self.enter_serial_connection_context(topology_obj)

        with allure.step(f'Install image {image_url} using {NvosConst.ONIE_NOS_INSTALL_CMD}'):
            self._install_image_on_onie(serial_engine, ssh_engine, image_path, image_url)

    def deploy_onie(self, image_path, in_onie, fw_pkg_path, platform_params, topology_obj):
        assert in_onie, 'NVOS install failed - not in ONIE'
        self.install_image_onie(self.engine, image_path, platform_params, topology_obj)

    def install_image_via_onie(self, topology_obj, image_path):
        self.deploy_image(topology_obj, image_path, None, None, None, 'onie', None, None, None)

    def deploy_image(self, topology_obj, image_path, apply_base_config=False, setup_name=None,
                     platform_params=None, deploy_type='sonic', reboot_after_install=None, fw_pkg_path=None,
                     set_timezone='Israel', disable_ztp=False, configure_dns=False, destination_hwsku=None,
                     setup_info=None, dut_alias=None, deploy_fanout_threads=None):
        if image_path.startswith('http'):
            image_path = '/auto/' + image_path.split('/auto/')[1]

        with allure.step('Preparing switch for installation'):
            logger.info("Begin: Preparing switch for installation ")
            in_onie = self.prepare_for_installation(topology_obj)
            logger.info("End: Preparing switch for installation ")

        self.deploy_onie(image_path, in_onie, fw_pkg_path, platform_params, topology_obj)

    def install_image_onie(self, engine, image_path, platform_params, topology_obj):
        with allure.step('Install image onie - NVOS'):
            # SonicOnieCli(dut_ip, dut_ssh_port).install_image(image_path=image_path, platform_params=platform_params,
            #                                                  topology_obj=topology_obj)
            self.install_nos_using_onie_in_serial(image_path, engine, topology_obj)

        with allure.step("Complete installation"):
            self._wait_nos_to_become_functional(engine, topology_obj)

    def _wait_nos_to_become_functional(self, engine, topology_obj=""):
        with allure.step('Ping switch until shutting down'):
            ping_till_alive(should_be_alive=False, destination_host=engine.ip)
        with allure.step('Ping switch until back alive'):
            ping_till_alive(should_be_alive=True, destination_host=engine.ip)
        with allure.step('Wait until switch is up'):
            engine.disconnect()  # force engines.dut to reconnect
            DutUtilsTool.wait_for_nvos_to_become_functional(engine=engine)

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
    def show_config(engine, revision='applied', output_type='json'):
        logging.info("Running 'nv config show' on dut")
        output = engine.run_cmd('nv config show --rev {revision} --output {output_type}'.format(output_type=output_type,
                                                                                                revision=revision))
        return output

    @staticmethod
    def replace_config(engine, file, output_type='json'):
        logging.info("Running 'nv config replace' on dut")
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
                     skip_no_config_diff_err=True):
        """
        Apply configuration
        :param option: could be [-y, --assume-yes, --assume-no, --confirm-yes, --confirm-no, --confirm-status]
        :param engine: ssh engine object
        :param ask_for_confirmation: True or False
        """
        logging.info("Checking the config to be applied")
        NvueGeneralCli.diff_config(engine=engine)

        logging.info("Running 'nv config apply {} ' on dut".format(rev_id))
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

    @staticmethod
    def upgrade_dut(engine, path_to_image):
        """
        Installing the provided image on dut
        """
        logging.info("Installing {}".format(path_to_image))

        with allure.step("Copying image to dut"):
            logging.info("Copy image from {src} to {dest}".format(src=path_to_image,
                                                                  dest=NvosConst.IMAGES_PATH_ON_SWITCH))
            if not path_to_image.startswith('http'):
                image_path = '{}{}'.format(InfraConst.HTTP_SERVER, path_to_image)
                engine.run_cmd('sudo curl {} -o {}'.format(image_path, NvosConst.IMAGES_PATH_ON_SWITCH), validate=True)

        with allure.step("Installing image {}".format(NvosConst.IMAGES_PATH_ON_SWITCH)):
            NvueSystemCli.action_image(engine=engine, action_str=ActionConsts.INSTALL,
                                       action_component_str="image", op_param=NvosConst.IMAGES_PATH_ON_SWITCH)

        with allure.step("Reboot dut"):
            NvueGeneralCli.reboot(engine)

        with allure.step("Verifying NVOS initialized successfully"):
            NvueGeneralCli.verify_dockers_are_up()
            DutUtilsTool.wait_for_nvos_to_become_functional(engine).verify_result()

    def remote_reboot(self, topology_obj):
        '''
        @summary: perform remote reboot from the physical server using the noga remote reboot command,
        usually the command should be like this: '/auto/mswg/utils/bin/rreboot <ip|hostname>'
        '''
        cmd = topology_obj.players['dut_serial']['attributes'].noga_query_data['attributes']['Specific'][
            'remote_reboot']
        assert cmd, "Reboot command is empty"
        ssh_conn = LinuxSshEngine(ip=server_ip, username=os.getenv("TEST_SERVER_USER"),
                                  password=os.getenv("TEST_SERVER_PASSWORD"))
        ssh_conn.run_cmd(cmd)

    def enter_serial_connection_context(self, topology_obj):
        '''
        @summary: in this function we will execute the rcon command and return the serial engine
        :return: serial connection engine
        '''
        att = topology_obj.players['dut_serial']['attributes'].noga_query_data['attributes']
        # add connection options to pass connection problems
        extended_rcon_command = att['Specific']['serial_conn_cmd'].split(' ')
        extended_rcon_command.insert(1, DefaultConnectionValues.BASIC_SSH_CONNECTION_OPTIONS)
        extended_rcon_command = ' '.join(extended_rcon_command)
        serial_engine = PexpectSerialEngine(ip=att['Specific']['ip'],
                                            username=att['Topology Conn.']['CONN_USER'],
                                            password=att['Topology Conn.']['CONN_PASSWORD'],
                                            rcon_command=extended_rcon_command,
                                            timeout=120)
        # we don't want to login to switch because we are doing remote reboot
        serial_engine.create_serial_engine(login_to_switch=False)
        return serial_engine

    def enter_onie_install_mode(self, topology_obj):
        '''
        @summary: in this function we want to enter install mode,
        we are doing so by the following step:
            1.create a serial engine
            2.remote reboot
            3.wait till GRUB menu appears:
                a. if the NVOS grub menu appears then select ONIE entry (pressing down 2 key arrows)
                b. if the ONIE grub menu appears just do nothing (the install entry will be marked and after 5 secs it
                will enter the install mode)
        '''

        with allure.step("Initializing serial connection to device"):
            serial_engine = self.enter_serial_connection_context(topology_obj)

        with allure.step('Executing remote reboot'):
            self.remote_reboot(topology_obj)

        with allure.step('wait for NVOS/ONIE grub menu'):
            logger.info("Enter ONIE install mode")
            logger.info("Wait for NVOS/ONIE grub menu")
            # Set timeout based on the active status of Redmine issue #4028150
            to = 360 if is_redmine_issue_active([4028150])[0] else 240
            onie_grub_menu_pattern = '\\*ONIE: Install OS'
            grub_menu_patterns = ['ONIE\\s+', onie_grub_menu_pattern]
            all_patterns = grub_menu_patterns + SecureBootConsts.INVALID_SIGNATURE
            output, respond = serial_engine.run_cmd('', all_patterns, timeout=to, send_without_enter=True)

        if respond != 1:
            if respond >= len(grub_menu_patterns):
                with allure.step('Secure boot error - handle'):
                    with allure.step('hit Enter till no error message'):
                        while respond >= len(grub_menu_patterns):
                            logger.info('Hit Enter on secure boot error message')
                            output, respond = serial_engine.run_cmd("\r", expected_value=all_patterns, timeout=to, send_without_enter=True)
                            time.sleep(1)

            elif respond == 0:
                with allure.step("System in NVOS grub menu, entering ONIE grub menu"):
                    for i in range(2):
                        logger.info("Sending one arrow down")
                        serial_engine.run_cmd("\x1b[B", expected_value='.*', send_without_enter=True)
                        time.sleep(0.3)
                    logger.info("Onie option selected")

                    logger.info("Pressing Enter to enter ONIE grub menu")
                    _, respond = serial_engine.run_cmd('\r',
                                                       expected_value=['Due to security constraints, '
                                                                       'this option will uninstall your current OS',
                                                                       'Answer "YES" to continue', '\\*ONIE:.*'],
                                                       timeout=30, send_without_enter=True)

                    if respond != 2:
                        with allure.step("MLNX-OS system. Enter 'YES' and wait till in ONIE grub menu"):
                            serial_engine.run_cmd('YES', onie_grub_menu_pattern, timeout=420)

            with allure.step('in ONIE grub menu: Go up to onie install mode'):
                with allure.step("Send up arrows for case default mode is Rescue"):
                    for i in range(5):
                        logger.info("Sending one arrow up")
                        serial_engine.run_cmd("\x1b[A", expected_value='.*', send_without_enter=True)
                        time.sleep(0.3)

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
                output, respond = serial_engine.run_cmd(DefaultConnectionValues.ONIE_USERNAME, '[Pp]assword:', timeout=10)
                logger.info(output)
                logger.info(f'Send line: "{DefaultConnectionValues.ONIE_PASSWORD}"')
                output, respond = serial_engine.run_cmd(DefaultConnectionValues.ONIE_PASSWORD, 'ONIE:~ #', timeout=20)
                logger.info(output)

        with allure.step('Send line: "onie-stop"'):
            output, respond = serial_engine.run_cmd('onie-stop', 'done.', timeout=10)
            logger.info(output)

            for _ in range(3):
                time.sleep(1)
                logger.info('Send new line')
                output, respond = serial_engine.run_cmd('\r', '.*', timeout=10, send_without_enter=True)
                logger.info(output)

    def prepare_for_installation(self, topology_obj):
        '''
        @summary: in this function we will enter onie install mode using remote reboot
        '''
        with allure.step('Prepare for installation: enter ONIE'):
            switch_in_onie = False
            try:
                self.enter_onie(topology_obj)
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
    def enter_onie(self, topology_obj):
        self.enter_onie_install_mode(topology_obj)

    def confirm_in_onie_install_mode(self, topology_obj):
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
