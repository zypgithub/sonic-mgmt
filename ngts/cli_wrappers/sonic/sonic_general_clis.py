import re
import allure
import logging
import time
import netmiko
import json
import traceback
import os
from retry import retry
from retry.api import retry_call
import xml.etree.ElementTree as ET

from ngts.cli_util.cli_constants import SonicConstant
from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon
from ngts.cli_wrappers.linux.linux_general_clis import LinuxGeneralCli
from ngts.helpers.run_process_on_host import run_process_on_host
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.constants.constants import SonicConst, InfraConst, ConfigDbJsonConst, PerformanceSetupConstants, \
    AppExtensionInstallationConstants, DefaultCredentialConstants, BluefieldConstants, \
    PlatformTypesConstants, PerfConsts
from ngts.helpers.breakout_helpers import get_port_current_breakout_mode, get_all_split_ports_parents, \
    get_split_mode_supported_breakout_modes, get_split_mode_supported_speeds, get_all_unsplit_ports
from ngts.cli_util.cli_parsers import generic_sonic_output_parser
import ngts.helpers.json_file_helper as json_file_helper
from ngts.helpers.interface_helpers import get_dut_default_ports_list
from ngts.helpers.config_db_utils import save_config_db_json
from ngts.helpers.sonic_branch_helper import get_sonic_branch
from ngts.tests.nightly.app_extension.app_extension_helper import get_installed_mellanox_extensions
from ngts.cli_wrappers.sonic.sonic_onie_clis import SonicOnieCli, OnieInstallationError, get_latest_onie_version
from infra.tools.utilities.onie_sonic_clis import SonicOnieCli as SonicOnieCliDevts
from infra.tools.general_constants.constants import SonicSimxConstants, SonicHostsConstants
from ngts.cli_wrappers.sonic.sonic_chassis_clis import SonicChassisCli
from ngts.scripts.check_and_store_sanitizer_dump import check_sanitizer_and_store_dump
from infra.tools.nvidia_air_tools.air import get_dhcp_ips_dict
from infra.tools.general_constants.constants import DefaultTestServerCred
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from infra.tools.topology_tools.nogaq import get_noga_entire_resource_data
from ngts.tools.infra import update_platform_info_files
from ngts.helpers.secure_boot_helper import SecureBootHelper

logger = logging.getLogger()
DUMMY_COMMAND = 'echo dummy_command'


class SonicGeneralCli:

    def __new__(cls, **kwargs):
        branch = kwargs.get('branch')
        engine = kwargs['engine']
        cli_obj = kwargs.get('cli_obj')
        dut_alias = kwargs.get('dut_alias', 'dut')

        supported_cli_classes = {'default': SonicGeneralCliDefault(engine, cli_obj, dut_alias),
                                 '202012': SonicGeneralCli202012(engine, cli_obj, dut_alias)}

        cli_class = supported_cli_classes.get(branch, supported_cli_classes['default'])
        cli_class_name = cli_class.__class__.__name__
        logger.info(f'Going to use General CLI class: {cli_class_name}')

        return cli_class


class SonicGeneralCliDefault(GeneralCliCommon):
    """
    This class is for general cli commands for sonic only
    """
    _is_simx_moose = None

    def __init__(self, engine, cli_obj, dut_alias):
        self.engine = engine
        self.cli_obj = cli_obj
        self.dut_alias = dut_alias
        self.backup_logs_stored = False

    def show_feature_status(self):
        """
        This method show feature status on the sonic switch
        :return: command output
        """
        return self.engine.run_cmd('show feature status')

    def show_and_parse_feature_status(self):
        """
        This method show feature status on the sonic switch
        :return: command output
        """
        output_content = self.show_feature_status()
        return generic_sonic_output_parser(output_content, output_key="Feature")

    def set_feature_state(self, feature_name, state):
        """
        This method to set feature state on the sonic switch
        :param feature_name: the feature name
        :param state: state
        """
        self.engine.run_cmd('sudo config feature state {} {}'.format(feature_name, state), validate=True)

    def get_installer_delimiter(self):
        dash_installer = 'sonic-installer'
        delimiter = '_'
        output = self.engine.run_cmd('which {}'.format(dash_installer))
        if dash_installer in output:
            delimiter = '-'
        return delimiter

    def install_image(self, image_path, delimiter='-', is_skipping_migrating_package=False, validate=True):
        if not is_skipping_migrating_package:
            output = self.engine.run_cmd('sudo sonic{}installer install {} -y'.
                                         format(delimiter, image_path), validate=validate)
        else:
            output = self.engine.run_cmd('sudo sonic{}installer install {} -y --skip-package-migration'.
                                         format(delimiter, image_path), validate=validate)
        return output

    def get_image_binary_version(self, image_path, delimiter='-'):
        output = self.engine.run_cmd('sudo sonic{}installer binary{}version {}'.
                                     format(delimiter, delimiter, image_path),
                                     validate=True)
        return output

    def get_image_sonic_version(self):
        output = self.engine.run_cmd('sudo show boot')
        current_image = re.search(r"Current:\s*SONiC-OS-([\d|\w|\-]*)\..*", output, re.IGNORECASE).group(1)
        return current_image

    def set_default_image(self, image_binary, delimiter='-'):
        output = self.engine.run_cmd('sudo sonic{}installer set{}default {}'.format(delimiter, delimiter, image_binary),
                                     validate=True)
        return output

    def set_next_boot_entry_to_onie(self):
        self.engine.run_cmd('sudo grub-editenv /host/grub/grubenv set next_entry=ONIE', validate=True)

    def get_sonic_image_list(self, delimiter='-'):
        output = self.engine.run_cmd('sudo sonic{}installer list'.format(delimiter), validate=True)
        return output

    def load_configuration(self, config_file):
        self.engine.run_cmd('sudo config load -y {}'.format(config_file), validate=True)

    def reload_configuration(self, force=False):
        cmd = 'sudo config reload -y'
        if force:
            cmd += ' -f'
        self.engine.run_cmd(cmd, validate=True)

    def save_configuration(self):
        self.engine.run_cmd('sudo config save -y', validate=True)

    def download_file_from_http_url(self, url, target_file_path):
        self.engine.run_cmd('sudo curl {} -o {}'.format(url, target_file_path), validate=True)

    def check_and_apply_dns(self):
        if not self.cli_obj.ip.is_static_dns_supported():
            with allure.step('Apply DNS servers configuration after reboot/reload'):
                self.cli_obj.ip.apply_dns_servers_into_resolv_conf()

    def reboot_reload_flow(self, r_type='reboot', ports_list=None, topology_obj=None, wait_after_ping=45,
                           reload_force=False):
        """
        Wrapper for reboot and reload methods - which executes appropriate method based on reboot/reload type
        """
        if r_type == SonicConst.CONFIG_RELOAD_CMD:
            self.reload_flow(ports_list, topology_obj, reload_force)
        else:
            self.reboot_flow(r_type, ports_list, topology_obj, wait_after_ping)

    def reboot_flow(self, reboot_type='reboot', ports_list=None, topology_obj=None, wait_after_ping=45):
        """
        Rebooting switch by given way(reboot, fast-reboot, warm-reboot) and validate dockers and ports state
        :param reboot_type: reboot type
        :param ports_list: list of the ports to check status after reboot
        :param topology_obj: topology object
        :param wait_after_ping: how long in second wait after ping before ssh connection
        :return: None, raise error in case of unexpected result
        """
        ports_list = self.get_ports_list_reboot_reload_flow(ports_list, topology_obj)
        with allure.step('Reboot switch by CLI - sudo {}'.format(reboot_type)):
            self.safe_reboot_flow(topology_obj, reboot_type, wait_after_ping=wait_after_ping)
            self.port_reload_reboot_checks(ports_list)
            self.check_and_apply_dns()

    def safe_reboot_flow(self, topology_obj, reboot_type='reboot', wait_after_ping=45):
        logs_in_tmpfs = self.is_logs_in_tmpfs()
        self.copy_logs_before_reboot(logs_in_tmpfs)
        self.engine.reload([f'sudo {reboot_type}'], wait_after_ping=wait_after_ping)
        self.restore_logs_after_reboot(logs_in_tmpfs)
        sanitizer = topology_obj.players['dut']['sanitizer']
        if sanitizer:
            test_name = os.environ.get('PYTEST_CURRENT_TEST').split(':')[-1].split(' ')[0]
            dumps_folder = os.environ.get(InfraConst.ENV_LOG_FOLDER)
            check_sanitizer_and_store_dump(self.engine, dumps_folder, test_name)

    def reload_flow(self, ports_list=None, topology_obj=None, reload_force=False):
        """
        Reloading switch and validate dockers and ports state
        :param ports_list: list of the ports to check status after reboot
        :param topology_obj: topology object
        :param reload_force: provide if want to do reload with -f flag(force)
        :return: None, raise error in case of unexpected result
        """
        ports_list = self.get_ports_list_reboot_reload_flow(ports_list, topology_obj)
        with allure.step('Reloading dut'):
            logger.info("Reloading dut")
            self.reload_configuration(reload_force)
            self.port_reload_reboot_checks(ports_list)
            self.check_and_apply_dns()

    def get_ports_list_reboot_reload_flow(self, ports_list, topology_obj):
        if not (ports_list or topology_obj):
            raise Exception('ports_list or topology_obj must be passed to reload_flow method')
        if not ports_list:
            ports_list = topology_obj.players_all_ports[self.dut_alias]
        # in perf setup, expected ports in up state are left_tg: (Ethernet0::252, 4), right_tg: (Ethernet256::508, 4)
        if self.cli_obj.dut_alias in [PerfConsts.LEFT_TG_ALIAS, PerfConsts.RIGHT_TG_ALIAS]:
            ports_list = self.get_performance_ports_list(topology_obj)
        return ports_list

    def get_performance_ports_list(self, topology_obj):
        """
        Method returns ports list of traffic generator from performance setup, which connected to DUT
        :return: TG ports list
        """
        ports_list = []
        switch_name = topology_obj.players[self.cli_obj.dut_alias]['attributes'].noga_query_data['attributes']['Common']['Name']
        noga_entire_data = get_noga_entire_resource_data(resource_name=switch_name)
        for resource in noga_entire_data:
            if 'etp' in resource['name'] and switch_name not in resource['connected with']:
                ports_list.append(resource['if'])
        return ports_list

    def port_reload_reboot_checks(self, ports_list):
        self.verify_dockers_are_up()
        self.cli_obj.interface.check_link_state(ports_list)

    def is_logs_in_tmpfs(self):
        log_filesystem = self.engine.run_cmd("df --output=fstype -h /var/log")
        logs_in_tmpfs = log_filesystem and "tmpfs" in log_filesystem
        config_db = self.get_config_db()
        platform = config_db['DEVICE_METADATA']['localhost']['platform']
        return logs_in_tmpfs or platform in PlatformTypesConstants.LOGS_ON_TMPFS_PLATFORMS

    def copy_logs_before_reboot(self, logs_in_tmpfs):
        if logs_in_tmpfs:
            # If it is not the first reboot in this test run, needs to backup also syslog.99
            if not self.backup_logs_stored:
                syslogs_99 = ''
                sairedis_99 = ''
                swss_99 = ''
            else:
                syslogs_99 = '/host/syslog.99'
                sairedis_99 = '/var/log/swss/sairedis.rec.99'
                swss_99 = '/var/log/swss/swss.rec.99'
            backup_log_cmds = [
                "sudo su",
                f"cat {syslogs_99} /var/log/syslog.1 /var/log/syslog > /host/syslog.99 || true",
                f"cat {sairedis_99} /var/log/swss/sairedis.rec.1 /var/log/swss/sairedis.rec > "
                f"/host/sairedis.rec.99 || true",
                f"cat {swss_99} /var/log/swss/swss.rec.1 /var/log/swss/swss.rec > /host/swss.rec.99 || true",
                "exit"
            ]
            self.engine.run_cmd_set(backup_log_cmds)
            self.backup_logs_stored = True

    def restore_logs_after_reboot(self, logs_in_tmpfs):
        if logs_in_tmpfs:
            restore_backup_cmds = ["sudo su",
                                   "mv /host/syslog.99 /var/log/",
                                   "mv /host/sairedis.rec.99 /var/log/swss/",
                                   "mv /host/swss.rec.99 /var/log/swss/",
                                   "exit"]
            self.engine.run_cmd_set(restore_backup_cmds)

    def validate_dockers_are_up_reboot_if_fail(self, retries=2):
        """
        Reboot and validate docker containers are up on the switch
        :param retries: int how many times do reboot of switch
        """
        initial_count = retries
        while retries:
            try:
                self.verify_dockers_are_up()
                break
            except BaseException:
                logger.error('Caught exception {} during verifying docker containers are up.'
                             ' Rebooting dut and try again, try number {}'.format(traceback.print_exc(),
                                                                                  initial_count - retries + 1))
                self.engine.reload(['sudo reboot'])
            retries = retries - 1

    # Add 6 tries due to fw update would add external delay to syncd container boot up
    @retry(Exception, tries=21, delay=10)
    def verify_dockers_are_up(self, dockers_list=None):
        """
        Verifying the dockers are in up state during a specific time interval
        :param dockers_list: list of dockers to check
        :return: None, raise error in case of unexpected result
        """
        with allure.step('Check that dockers in UP state'):
            self._verify_dockers_are_up(dockers_list)

    def _verify_dockers_are_up(self, dockers_list):
        """
        Verifying the dockers are in up state
        :param dockers_list: list of dockers to check
        :return: None, raise error in case of unexpected result
        """
        if dockers_list is None:
            dockers_list = SonicConst.DOCKERS_LIST_LEAF

            # Try to get extended docker list for DUT type ToRRouter
            try:
                config_db = self.get_config_db()
                if self.is_bluefield(config_db['DEVICE_METADATA']['localhost']['hwsku']):
                    dockers_list = SonicConst.DOCKERS_LIST_BF
                elif config_db['DEVICE_METADATA']['localhost']['type'] == 'ToRRouter':
                    dockers_list = SonicConst.DOCKERS_LIST_TOR
                # in performance setup the docker dhcp_relay is disabled on TG switches to exclude multicast
                if self.cli_obj.dut_alias in ['left_tg', 'right_tg']:
                    if 'dhcp_relay' in dockers_list:
                        dockers_list.remove('dhcp_relay')
            except json.JSONDecodeError:
                logger.warning('Can not get device type from config_db.json. Unable to parse config_db.json file')
            except KeyError:
                logger.warning('Can not get device type from config_db.json. Key does not exist')

        for docker in dockers_list:
            try:
                self.engine.run_cmd('docker ps | grep {}'.format(docker), validate=True)
            except BaseException:
                raise Exception("{} docker is not up".format(docker))

    def verify_processes_of_dockers(self, docker_list, hwsku):
        """
        Verifying the processes of dockers are in RUNNING state
        :param dockers_list: list of dockers to check
        :return: None, raise error in case of unexpected result
        """
        success = True
        if self.is_bluefield(hwsku):
            expected_processes = SonicConst.DAEMONS_DICT_BF
        else:
            expected_processes = SonicConst.DAEMONS_DICT

        for docker in docker_list:
            running_processes = []
            processes_output = self.engine.run_cmd(f'docker exec {docker} supervisorctl status')
            for process_info in processes_output.splitlines():
                logger.info(f"process info:   {process_info}")
                process_name = process_info.split()[0].strip()
                process_status = process_info.split()[1].strip()
                if process_name in expected_processes[docker] and process_status == "RUNNING":
                    running_processes.append(process_name)
            if len(running_processes) != len(expected_processes[docker]):
                logger.error(f"Not all expected processes of docker {docker} are running.\n"
                             f"Expected: {expected_processes[docker]}\nRunning: {running_processes}")
                success = False
        assert success, 'Not all expected processes in RUNNING status'

    @retry(Exception, tries=2, delay=30)
    def generate_techsupport(self, duration=60):
        """
        Generate sysdump for a given time frame in seconds
        :param duration: time frame in seconds
        :return: dump path
        """
        with allure.step('Generate Techsupport of last {} seconds'.format(duration)):
            output = self.engine.run_cmd('sudo generate_dump -s \"-{} seconds\"'.format(duration), validate=True)
            return output.splitlines()[-1]

    def do_installation(self, topology_obj, image_path, deploy_type, fw_pkg_path, platform_params):
        if deploy_type == 'onie':
            if 'simx' in platform_params.platform:
                in_onie = True
            else:
                with allure.step('Preparing switch for installation'):
                    logger.info("Begin: Preparing switch for installation ")
                    in_onie = self.prepare_for_installation(topology_obj)
                    logger.info("End: Preparing switch for installation ")
            self.deploy_onie(image_path, in_onie, fw_pkg_path, platform_params, topology_obj)

        if deploy_type == 'sonic':
            self.deploy_sonic(image_path)

        if deploy_type == 'bfb':
            change_to_one_port_hwsku = 'msn4' in platform_params.platform
            validate = "sn4280" not in platform_params.platform
            self.deploy_bfb(image_path, topology_obj,
                            change_to_one_port_hwsku=change_to_one_port_hwsku, validate=validate)

        if deploy_type == 'pxe':
            self.deploy_pxe(image_path, topology_obj, platform_params['hwsku'])

    def deploy_image(self, topology_obj, image_path, apply_base_config=False, setup_name=None,
                     platform_params=None, deploy_type='sonic', reboot_after_install=None, fw_pkg_path=None,
                     set_timezone='Israel', disable_ztp=False, configure_dns=False):

        if image_path.startswith('http'):
            image_path = '/auto/' + image_path.split('/auto/')[1]

        try:
            with allure.step("Trying to install sonic image"):
                self.do_installation(topology_obj, image_path, deploy_type, fw_pkg_path, platform_params)
        except OnieInstallationError:
            with allure.step("Caught exception OnieInstallationError during install. Perform reboot and trying again"):
                logger.error('Caught exception OnieInstallationError during install. Perform reboot and trying again')
                self.engine.disconnect()
                self.remote_reboot(topology_obj)
                logger.info('Sleeping %s seconds to handle ssh flapping' % InfraConst.SLEEP_AFTER_RRBOOT)
                time.sleep(InfraConst.SLEEP_AFTER_RRBOOT)
                self.do_installation(topology_obj, image_path, deploy_type, fw_pkg_path, platform_params)

        with allure.step('Verify dockers are up'):
            self.verify_dockers_are_up()

        # Break if it's installing the Bobcat DPUs
        if deploy_type == 'bfb' and 'sn4280' in platform_params.platform:
            return

        if reboot_after_install:
            with allure.step("Validate dockers are up, reboot if any docker is not up"):
                self.validate_dockers_are_up_reboot_if_fail()

        if set_timezone:
            with allure.step("Set dut NTP timezone to {} time.".format(set_timezone)):
                self.engine.disconnect()
                self.engine.run_cmd('sudo timedatectl set-timezone {}'.format(set_timezone), validate=True)

        with allure.step("Init telemetry keys"):
            self.init_telemetry_keys()

        self.engine.disconnect()

        if apply_base_config:
            self.update_platform_params(platform_params, setup_name)
            with allure.step("Apply basic config"):
                self.apply_basic_config(topology_obj, setup_name, platform_params, disable_ztp=disable_ztp,
                                        configure_dns=configure_dns)
        else:
            self.disable_ztp(disable_ztp)

        self.configure_dhclient_if_simx()

    def init_telemetry_keys(self):
        logger.info("Create telemetry directory")
        self.engine.run_cmd(f"sudo mkdir {SonicConst.TELEMETRY_PATH}")
        self.engine.run_cmd(f"sudo chmod 0755 {SonicConst.TELEMETRY_PATH}")
        logger.info("Generate server cert using openssl.")
        self.engine.run_cmd(f"sudo openssl req -x509 -sha256 -nodes -newkey rsa:2048 "
                            f"-keyout {SonicConst.TELEMETRY_SERVER_KEY} -subj '/CN=ndastreamingservertest' "
                            f"-out {SonicConst.TELEMETRY_SERVER_CER}")
        logger.info("Generate dsmsroot cert using openssl")
        self.engine.run_cmd(f"sudo openssl req -x509 -sha256 -nodes -newkey rsa:2048 "
                            f"-keyout {SonicConst.TELEMETRY_DSMSROOT_KEY} -subj '/CN=ndastreamingclienttest' "
                            f"-out {SonicConst.TELEMETRY_DSMSROOT_CER}")

    def deploy_sonic(self, image_path, is_skipping_migrating_package=False):
        tmp_target_path = '/tmp/sonic-mellanox.bin'
        delimiter = self.get_installer_delimiter()

        with allure.step('Deploying image via SONiC'):
            self.configure_dhclient_if_simx()
            with allure.step('Copying image to dut'):
                self.engine.copy_file(source_file=image_path, dest_file='sonic-mellanox.bin',
                                      file_system='/tmp/', overwrite_file=True, verify_file=False)

            with allure.step('Installing the image'):
                self.install_image(tmp_target_path, delimiter, is_skipping_migrating_package)

            with allure.step('Setting image as default'):
                image_binary = self.get_image_binary_version(tmp_target_path, delimiter)
                self.set_default_image(image_binary, delimiter)

        with allure.step('Rebooting the dut'):
            self.engine.reload(['sudo reboot'])

        with allure.step('Verifying installation'):
            with allure.step('Verifying dut booted with correct image'):
                # installer flavor might change after loading a different version
                delimiter = self.get_installer_delimiter()
                image_list = self.get_sonic_image_list(delimiter)
                assert 'Current: {}'.format(image_binary) in image_list

    def configure_dhclient_if_simx(self):
        if 'simx' in self.engine.run_cmd("hostname"):
            with allure.step('Configure dhclient on simx dut'):
                self.engine.run_cmd('sudo dhclient', validate=True)

    def deploy_bfb(self, image_path, topology_obj, change_to_one_port_hwsku=False, validate=True):
        rshim = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
            'Parent_device_NIC_name']
        hyper_name = 'hyper' if 'hyper' in topology_obj.players else 'hypervisor'
        hyper_engine = topology_obj.players[hyper_name]['engine']

        with allure.step('Check RSHIM service running(restart if required'):
            if not LinuxGeneralCli(hyper_engine).systemctl_is_service_active(service='rshim'):
                LinuxGeneralCli(hyper_engine).systemctl_restart(service='rshim')

        with allure.step('Installing image by "bfb-install" on server'):
            LinuxGeneralCli(hyper_engine).install_bfb_image(image_path=image_path, rshim_num=rshim)

        # Broken engine after install. Disconnect it. In next run_cmd, it will connect back
        self.engine.disconnect()

        if validate:
            with allure.step('Waiting for switch bring-up after reload'):
                logger.info('Waiting for switch bring-up after reload')
                check_port_status_till_alive(True, self.engine.ip, self.engine.ssh_port)

            if change_to_one_port_hwsku:
                with allure.step('Change hwsku to the one port hwsku(ends with C1)'):
                    config_db = self.get_config_db()
                    hwsku = config_db['DEVICE_METADATA']['localhost']['hwsku']
                    logger.info(f'Current hwsku: {hwsku}')
                    if not hwsku.endswith('-C1'):
                        hwsku = hwsku.rstrip("-C2")
                        hwsku += "-C1"
                        logger.info(f'Generate the configuration for one port hwsku: {hwsku}')
                        self.engine.run_cmd(
                            f'sudo sonic-cfggen -k {hwsku} --write-to-db', validate=True)
                        self.engine.run_cmd('sudo config save -y')
                        with allure.step('Reload config and wait for DPU bring-up'):
                            logger.info('Config reload')
                            self.engine.run_cmd('sudo config reload -yf')

    def deploy_pxe(self, image_path, topology_obj, hwsku):
        bf_cli_ssh_connect_bringup = 480
        if not self.is_bluefield(hwsku):
            raise Exception('The installation via PXE available only for Bluefield Devices')

        with allure.step('Installing image by PXE'):
            logger.info('Installing image by PXE')

        self.update_pxe_grub_config(image_path, topology_obj, hwsku)

        bmc_cli_obj = self.get_bf_bmc_cli_obj(topology_obj)
        with allure.step('Set next boot to PXE'):
            bmc_cli_obj.set_next_boot_pxe_bf()
        with allure.step('Reboot remotely the dut'):
            bmc_cli_obj.remote_reboot_bf()

        with allure.step(f'Wait {bf_cli_ssh_connect_bringup} seconds for downloading the image'):
            logger.info(f'Wait {bf_cli_ssh_connect_bringup} seconds for downloading the image')
            time.sleep(bf_cli_ssh_connect_bringup)

        with allure.step('Start to check if CLI connection is available'):
            logger.info('Start to check if CLI connection is available')
            retry_call(self.check_bf_cli_connection,
                       fargs=[],
                       tries=24,  # temporary workaround due to bad PXE performance, original value was 12
                       delay=60,
                       logger=logger)

    def check_bf_cli_connection(self):
        """
        This function checks the connection to switch via mgmt.
        During installation the Bluefield have flapped ping,
        so it can't be checked in regular way.

        :return: exception if connection not available
        """
        self.engine.disconnect()
        self.engine.run_cmd(DUMMY_COMMAND, validate=True)

    @staticmethod
    def update_pxe_grub_config(image_path, topology_obj, hwsku):
        """
        This function updating the grub cfg config on LAB-PXE server for Image and initramfs files for Bluefield
        device to required version.
        These files used for PXE boot.
        """
        image_path = os.path.realpath(image_path)  # in case provided image as symbolic link(for example the latest)

        pxe_dir_path = '/'.join(image_path.split('/')[:-2]) + '/Nvidia-bluefield/pxe'
        pxe_server_dir_path = '/sonic/sonic_dpu{}'.format(pxe_dir_path.split('/sonic/sonic_dpu')[1])

        dut_mgmt_mac_addr = \
            topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['mac_address']
        pxe_server_config_path = f'{BluefieldConstants.PXE_SERVER_CONFIGS_PATH}grub.cfg-bf-{dut_mgmt_mac_addr}'

        pxe_server_engine = LinuxSshEngine(ip=BluefieldConstants.PXE_SERVER,
                                           username=DefaultTestServerCred.DEFAULT_USERNAME,
                                           password=DefaultTestServerCred.DEFAULT_PASS)

        orig_grub_cfg_file = BluefieldConstants.GRUB_CFG_FILE_MAP[hwsku]
        image_str = '(tftp)/<update the location>/Image'
        initramfs_str = '(tftp)/<update the location>/initramfs'

        with open(os.path.join(pxe_dir_path, orig_grub_cfg_file)) as cfg_file_obj:
            pxe_server_engine.run_cmd(f'echo "" > {pxe_server_config_path}')
            for line in cfg_file_obj.readlines():
                if image_str in line:
                    line = line.replace(image_str, f'{pxe_server_dir_path}/Image')
                elif initramfs_str in line:
                    line = line.replace(initramfs_str, f'{pxe_server_dir_path}/initramfs')

                pxe_server_engine.run_cmd(f"echo '{line}' >> {pxe_server_config_path}")

    @staticmethod
    def get_bf_bmc_cli_obj(topology_obj):
        bmc_ip = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['BF Switch']['bmc']
        bmc_engine = LinuxSshEngine(ip=bmc_ip,
                                    username=BluefieldConstants.BMC_USER,
                                    password=BluefieldConstants.BMC_PASS)
        return LinuxGeneralCli(bmc_engine)

    def deploy_onie(self, image_path, in_onie, fw_pkg_path, platform_params, topology_obj):
        if not in_onie:
            onie_reboot_script_path = self.prepare_onie_reboot_script_on_dut()
            if self.required_onie_upgrade(fw_pkg_path, platform_params):
                self.reboot_by_onie_reboot_script(onie_reboot_script_path, 'update')
            else:
                self.reboot_by_onie_reboot_script(onie_reboot_script_path, 'install')

        if 'simx' in platform_params.platform:
            self.update_simx_platform_type(platform_params)
        else:
            SonicOnieCli(self.engine.ip, self.engine.ssh_port, fw_pkg_path, platform_params).update_onie()
            self.confirm_in_onie_install_mode(topology_obj)

        self.install_image_onie(self.engine, image_path, platform_params, topology_obj)

    def confirm_in_onie_install_mode(self, topology_obj):
        in_onie = self.prepare_for_installation(topology_obj)
        logger.info(f"Onie status:{in_onie}, after preparing installation")
        if not in_onie:
            onie_reboot_script_path = self.prepare_onie_reboot_script_on_dut()
            self.reboot_by_onie_reboot_script(onie_reboot_script_path, 'install')

    def update_simx_platform_type(self, platform_params):
        """
        Update SIMX platform type in ONIE
        :param platform_params: platform_params fixture
        """
        board_name = SonicSimxConstants.PLATFORM_TO_MACHINE_NAME_DICT[platform_params.platform]
        SonicOnieCliDevts(self.engine.ip, board_name, logger, self.engine.ssh_port).update_onie()

    def prepare_onie_reboot_script_on_dut(self):
        onie_reboot_script = 'onie_reboot.sh'
        onie_reboot_script_path = f'/tmp/{onie_reboot_script}'
        onie_reboot_script_local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     f'../../scripts/sonic_deploy/{onie_reboot_script}')
        self.engine.run_cmd('sudo rm -rf /tmp/*')
        self.engine.copy_file(source_file=onie_reboot_script_local_path, file_system='/tmp',
                              dest_file=onie_reboot_script)
        self.engine.run_cmd(f'chmod 777 {onie_reboot_script_path}', validate=True)
        return onie_reboot_script_path

    def required_onie_upgrade(self, fw_pkg_path, platform_params):
        platform_syseeprom_output = SonicChassisCli(self.engine).show_platform_syseeprom()
        latest_onie_version, _ = get_latest_onie_version(fw_pkg_path, platform_params)
        return latest_onie_version not in platform_syseeprom_output

    def reboot_by_onie_reboot_script(self, onie_reboot_script_path, mode):
        logger.info(f"Reboot to ONIE with boot-mode {mode}")
        with allure.step(f"Reboot to ONIE with boot-mode {mode}"):
            self.engine.reload([f'{onie_reboot_script_path} {mode}'], wait_after_ping=25, ssh_after_reload=False)

    @staticmethod
    def install_image_onie(engine, image_path, platform_params, topology_obj):
        sonic_cli_ssh_connect_timeout = 10
        dut_ip = engine.ip
        dut_ssh_port = engine.ssh_port

        with allure.step('Installing image by "onie-nos-install"'):
            SonicOnieCli(dut_ip, dut_ssh_port).install_image(image_path=image_path, platform_params=platform_params,
                                                             topology_obj=topology_obj)

        with allure.step('Waiting for switch shutdown after reload command'):
            logger.info('Waiting for switch shutdown after reload command')
            check_port_status_till_alive(False, dut_ip, dut_ssh_port)

        with allure.step('Waiting for switch bring-up after reload'):
            logger.info('Waiting for switch bring-up after reload')
            check_port_status_till_alive(True, dut_ip, dut_ssh_port)

        with allure.step('Waiting for CLI bring-up after reload'):
            logger.info('Waiting for CLI bring-up after reload')
            time.sleep(sonic_cli_ssh_connect_timeout)

    def check_dut_is_alive(self):
        ip = self.engine.ip
        port = self.engine.ssh_port
        dut_is_alive = True
        try:
            logger.info('Checking whether device is alive')
            check_port_status_till_alive(should_be_alive=True, destination_host=ip, destination_port=port, tries=2)
            logger.info('Device is alive')
        except Exception:
            logger.info('Device is not alive')
            dut_is_alive = False

        return dut_is_alive

    def remote_reboot(self, topology_obj, boot_into_onie=False):
        ip = self.engine.ip
        port = self.engine.ssh_port
        logger.info('Executing remote reboot')
        cmd = topology_obj.players[self.dut_alias]['attributes'].noga_query_data['attributes']['Specific'][
            'remote_reboot']
        _, _, rc = run_process_on_host(cmd)
        if rc == InfraConst.RC_SUCCESS:
            if boot_into_onie:
                self.boot_into_onie_by_serial_on_remote_reboot(topology_obj)
            check_port_status_till_alive(should_be_alive=True, destination_host=ip, destination_port=port)
        else:
            raise Exception('Remote reboot rc is other then 0')

    def boot_into_onie_by_serial_on_remote_reboot(self, topology_obj):
        serial_engine = SecureBootHelper.get_serial_engine_instance(topology_obj)
        serial_engine.create_serial_engine(login_to_switch=False)
        arrow_down_key = "\x1b[B"
        arrow_up_key = "\x1b[A"
        enter_key = '\r'

        logger.info("Wait for GNU GRUB  version")
        output, respond = serial_engine.run_cmd(
            '', ['GRUB loading.', 'GNU GRUB  version'], timeout=240, send_without_enter=True)
        logger.info(f"GNU GRUB  version is ready.\n output:{output} \n respond:{respond}")

        logger.info("Select ONIE by pressing arrow down")
        # press the arrow up several times to ensure the item is selected
        for i in range(3):
            logger.info("Sending one arrow down")
            serial_engine.run_cmd(arrow_down_key, expected_value='.*', send_without_enter=True)
            time.sleep(0.5)
        logger.info("Onie option selected")

        logger.info("Pressing Enter to enter ONIE grub menu")
        serial_engine.run_cmd(enter_key, expected_value='.*', timeout=30, send_without_enter=True)

        logger.info("Select 'ONIE: Install OS' by entering arrow up")
        # press the arrow up several times to ensure the item is selected
        for i in range(2):
            logger.info("Sending one arrow up")
            serial_engine.run_cmd(arrow_up_key, expected_value='.*', send_without_enter=True)
            time.sleep(0.5)

        logger.info("Pressing Enter to enter ONIE: Install OS")
        serial_engine.run_cmd('\r', expected_value='.*', timeout=30, send_without_enter=True)

    def prepare_for_installation(self, topology_obj):
        switch_in_onie = False
        if self.check_dut_is_alive():
            try:
                SonicOnieCli(self.engine.ip, self.engine.ssh_port).confirm_onie_boot_mode_install()
                switch_in_onie = True
            except Exception as err:
                logger.warning(f'DUT is not in ONIE. \n Got error: {err}')
                # it can cover the following scenarios
                # 1. user/password doesn't match the default one
                # 2. ping and ssh switch are ok, but cannot login into it
                if self.switch_dut_to_onie_by_remote_reboot(topology_obj):
                    switch_in_onie = True
        else:
            if self.switch_dut_to_onie_by_remote_reboot(topology_obj):
                switch_in_onie = True
            elif self.switch_dut_to_onie_by_serial_on_dut_stuck_on_selecting_os_page(topology_obj):
                switch_in_onie = True
            elif self.switch_dut_from_sonic_to_onie_by_serial_on_dut_is_not_alive(topology_obj):
                switch_in_onie = True
        return switch_in_onie

    def switch_dut_to_onie_due_to_unmatched_password(self):
        switch_in_onie = False
        with allure.step("Try other password because default password doesn't work"):
            try:
                # Checking if device is in sonic
                self.engine.run_cmd(DUMMY_COMMAND, validate=True)
            except netmiko.ssh_exception.NetmikoAuthenticationException:
                self.if_other_credentials_used_set_boot_order_onie()
                logger.info('Next boot set to onie succeed with new password')
                SonicOnieCli(self.engine.ip, self.engine.ssh_port).confirm_onie_boot_mode_install()
                switch_in_onie = True
            return switch_in_onie

    def switch_dut_to_onie_by_remote_reboot(self, topology_obj):
        with allure.step('Do remote reboot because dut is not alive'):
            try:
                logger.info("Do remote reboot ...")
                self.remote_reboot(topology_obj, boot_into_onie=True)
            except Exception as err:
                logger.info(f"remote reboot err:{err}")

        with allure.step('Check dut is in onie or not after remote reboot'):
            return self.check_dut_in_onie_install_status()

    def switch_dut_to_onie_by_serial_on_dut_stuck_on_selecting_os_page(self, topology_obj):
        """
        This function is to switch dut to onie by serial,
        when dut is stuck on the page of select os and losing ssh connection
        """
        with allure.step('Create serial engine without login to switch'):
            try:
                serial_engine = SecureBootHelper.get_serial_engine_instance(topology_obj)
                serial_engine.create_serial_engine(login_to_switch=False)
            except Exception as err:
                logger.error(f"Create serial engine error: {err}")
        with allure.step('switch dut to onie by serial'):
            try:
                time_out = 10
                wait_serial_take_effect = 2
                cmd_enter = "\n"
                cmd_press_esc = "\33"

                # before selecting onie, press esc and enter key to make sure the page is in the os selected page
                logger.info("Press esc ")
                serial_engine.run_cmd(cmd_press_esc, expected_value=" ", timeout=time_out)
                time.sleep(wait_serial_take_effect)
                logger.info("Press enter")
                serial_engine.run_cmd(cmd_enter, expected_value=" ", timeout=time_out)
                time.sleep(wait_serial_take_effect)

                logger.info("Select the last item: ONIE")
                cmd_last_one = "\03"
                serial_engine.run_cmd(cmd_last_one, expected_value="ONIE", timeout=time_out)
                time.sleep(wait_serial_take_effect)

                logger.info("Boot into ONIE by pressing enter")
                serial_engine.run_cmd(cmd_enter, expected_value=" ", timeout=time_out)
                time.sleep(wait_serial_take_effect)

                logger.info("Boot into ONIE install by pressing enter")
                serial_engine.run_cmd(cmd_enter, expected_value=" ", timeout=time_out)
                time.sleep(wait_serial_take_effect)
                logger.info("DUT is switched to onie by serial")

            except Exception as err:
                logger.error(f"Switching dut to onie by serial failed. {err}")

        with allure.step('Check dut is in onie or not after switching it from stuck page to onie by serial'):
            return self.check_dut_in_onie_install_status()

    def switch_dut_from_sonic_to_onie_by_serial_on_dut_is_not_alive(self, topology_obj):
        """
        This function is to switch dut from sonic into onie by serial, when dut is losing ssh connection
        """
        with allure.step('Create serial engine'):
            try:
                serial_engine = SecureBootHelper.get_serial_engine_instance(topology_obj)
                serial_engine.create_serial_engine()
            except Exception as err:
                logger.error(f"Create serial engine with login switch error: {err}")
        with allure.step('Switch dut from sonic to onie by serial'):
            try:
                time_out = 10
                logger.info("Set next_entry=ONIE in grub")
                cmd_set_next_entry = "sudo grub-editenv /host/grub/grubenv set next_entry=ONIE"
                serial_engine.run_cmd(cmd_set_next_entry, timeout=time_out)

                logger.info("Do reboot ")
                cmd_reboot = "sudo reboot"
                serial_engine.run_cmd(cmd_reboot, expected_value=" ", timeout=time_out)
                logger.info("DUT is switched to onie by serial")
            except Exception as err:
                logger.error(f"Switching dut to onie by serial failed. {err}")

        with allure.step('Check dut is in onie or not after switching it from sonic to onie by serial'):
            return self.check_dut_in_onie_install_status(tries=30)

    def check_dut_in_onie_install_status(self, tries=20):
        switch_in_onie = False
        with allure.step('Check dut is in onie or not '):
            try:
                logger.info('Checking whether device is alive')
                check_port_status_till_alive(should_be_alive=True, destination_host=self.engine.ip,
                                             destination_port=self.engine.ssh_port,
                                             tries=tries)
            except Exception as err:
                logger.error(f"Dut is not alive. {err}")
        with allure.step("Check dut is in onie install status"):
            try:
                logger.info('Checking dut is in onie install status')
                SonicOnieCli(self.engine.ip, self.engine.ssh_port).confirm_onie_boot_mode_install()
                switch_in_onie = True
            except Exception as err:
                logger.error(f"Dut is not in onie. {err}")

        logger.info(f"Dut onie status is {switch_in_onie}")
        return switch_in_onie

    def disable_ztp(self, disable_ztp=False):
        if disable_ztp:
            with allure.step('Disable ZTP'):
                retry_call(self.cli_obj.ztp.disable_ztp,
                           fargs=[],
                           tries=3,
                           delay=10,
                           logger=logger)
                self.save_configuration()

    def update_platform_params(self, platform_params, setup_name):
        if hasattr(self, 'cli_obj'):  # SONiC only
            current_platform_summary = self.cli_obj.chassis.parse_platform_summary()
            if platform_params["hwsku"] != current_platform_summary["HwSKU"] \
                    or platform_params["platform"] != current_platform_summary["Platform"] \
                    or self.is_performance_setup(setup_name):
                if self.is_performance_setup(setup_name):
                    # for performance setup the HwSKU not updated after install image
                    platform_params["hwsku"] = PerformanceSetupConstants.HWSKU
                else:
                    platform_params["hwsku"] = current_platform_summary["HwSKU"]
                platform_params["platform"] = current_platform_summary["Platform"]
                hostname = self.cli_obj.chassis.get_hostname()
                update_platform_info_files(hostname, current_platform_summary, update_inventory=True)

    def apply_basic_config(self, topology_obj, setup_name, platform_params, reload_before_qos=False,
                           disable_ztp=False, configure_dns=True):
        with allure.step("Upload port_config.ini and config_db.json with reboot of dut"):
            retry_call(self.apply_config_files,
                       fargs=[topology_obj, setup_name, platform_params],
                       tries=3,
                       delay=10,
                       logger=logger)

        self.disable_ztp(disable_ztp)

        with allure.step('Remove FRR configuration(which may contain default BGP config)'):
            self.cli_obj.frr.remove_frr_config_files()

        if reload_before_qos:
            with allure.step("Reload the dut"):
                self.reboot_reload_flow(r_type=SonicConst.CONFIG_RELOAD_CMD, topology_obj=topology_obj,
                                        reload_force=True)

        with allure.step("Apply qos and dynamic buffer config"):
            self.cli_obj.qos.reload_qos()
            self.verify_dockers_are_up(dockers_list=['swss'])
            if is_redmine_issue_active([3589124]):
                time.sleep(120)
            self.cli_obj.qos.stop_buffermgrd()
            self.cli_obj.qos.start_buffermgrd()

        with allure.step("Enable INFO logging on swss"):
            self.enable_info_logging_on_docker(docker_name='swss')

        if configure_dns:
            with allure.step('Apply DNS servers configuration'):
                self.cli_obj.ip.apply_dns_servers_into_resolv_conf(
                    is_air_setup=platform_params.setup_name.startswith('air'))

        self.cli_obj.general.save_configuration()

    def apply_config_files(self, topology_obj, setup_name, platform_params):
        platform = platform_params['platform']
        hwsku = platform_params['hwsku']
        shared_path = '{}{}'.format(InfraConst.MARS_TOPO_FOLDER_PATH, setup_name)

        if setup_name.startswith('air'):
            self.prepare_nvidia_air_basic_config_db_json(topology_obj, setup_name, hwsku, platform)
        else:
            # No need to modify port_config.ini for NvidiaAir setups - because ports split not supported yet
            self.upload_port_config_ini(platform, hwsku, shared_path)

        self.upload_config_db_file(topology_obj, setup_name, hwsku, platform, shared_path)

        with allure.step("Disable autoneg on SW control ports if SW control feature enabled"):
            if self.cli_obj.im.is_im_enabled():
                port_supporting_im = self.cli_obj.im.get_ports_supporting_im(
                    self.cli_obj.im.dut_ports_number_dict(topology_obj))
                if port_supporting_im:
                    with allure.step('Disable autoneg on ports supporting IM'):
                        self.cli_obj.im.disable_autoneg_on_ports_supporting_im(port_supporting_im)

        if is_redmine_issue_active([3858467]) and platform == 'x86_64-mlnx_msn4700-r0':
            self.reboot_reload_flow(r_type=SonicConst.CONFIG_RELOAD_CMD, topology_obj=topology_obj, reload_force=True)
        else:
            self.reboot_reload_flow(topology_obj=topology_obj)

    def upload_port_config_ini(self, platform, hwsku, shared_path):
        switch_config_ini_path = f'/usr/share/sonic/device/{platform}/{hwsku}'
        config_file_prefix = self.get_config_file_prefix(shared_path)
        source_file = os.path.join(shared_path, config_file_prefix + SonicConst.PORT_CONFIG_INI)
        logger.info(f'Copy file {source_file} to /tmp directory on a switch')
        self.engine.copy_file(source_file=source_file,
                              dest_file=SonicConst.PORT_CONFIG_INI, file_system='/tmp/',
                              overwrite_file=True, verify_file=False)
        self.engine.run_cmd(f'sudo mv /tmp/{SonicConst.PORT_CONFIG_INI} {switch_config_ini_path}')

    def get_config_file_prefix(self, str_with_setup_name):
        prefix = ''
        if self.is_performance_setup(str_with_setup_name):
            prefix = self.hostname() + '_'
        return prefix

    def upload_config_db_file(self, topology_obj, setup_name, hwsku, platform, shared_path):
        config_db_file = self.get_updated_config_db(topology_obj, setup_name, hwsku, platform)
        source_file = os.path.join(shared_path, config_db_file)
        logger.info(f'Copy file {source_file} to /tmp directory on a switch')
        self.engine.copy_file(source_file=source_file,
                              dest_file=SonicConst.CONFIG_DB_JSON, file_system='/tmp/',
                              overwrite_file=True, verify_file=False)
        self.engine.run_cmd(f'sudo mv /tmp/{SonicConst.CONFIG_DB_JSON} {SonicConst.CONFIG_DB_JSON_PATH}')

    def remove_minigraph_ipv6_mgmt_interface(self):
        logger.info("Remove IPv6 mgmt interface from minigraph.xml")
        V6HostIP_line_number = self.engine.run_cmd("awk '/V6HostIP/ {print NR}' /etc/sonic/minigraph.xml")
        if V6HostIP_line_number.isdecimal():
            V6HostIP_line_number = int(V6HostIP_line_number)
            start_line_number = V6HostIP_line_number - 1
            end_line_number = V6HostIP_line_number + 6
            self.engine.run_cmd(f"sudo sed -i '{start_line_number},{end_line_number}d' /etc/sonic/minigraph.xml")

    def remove_snmp_ipv6_addr(self):
        logger.info("Update SNMP config started")
        config_db = self.cli_obj.general.get_config_db()
        if 'SNMP_AGENT_ADDRESS_CONFIG' in config_db.keys():
            logger.info("SNMP_AGENT_ADDRESS_CONFIG in config_db.keys")
            snmp_config = config_db['SNMP_AGENT_ADDRESS_CONFIG']
            ipv6_add_to_remove = re.search(r"(\w{4}::.+)", ",".join(snmp_config.keys())).group(1)
            if ipv6_add_to_remove:
                snmp_config.pop(ipv6_add_to_remove)
                config_db['SNMP_AGENT_ADDRESS_CONFIG'] = snmp_config
                with open('/tmp/config_db.json', 'w') as f:
                    json.dump(config_db, f, indent=4)
                os.chmod('/tmp/config_db.json', 0o777)
                self.engine.copy_file(source_file='/tmp/config_db.json',
                                      dest_file="config_db.json", file_system='/tmp/',
                                      overwrite_file=True, verify_file=False)
                self.engine.run_cmd("sudo cp /tmp/config_db.json /etc/sonic/config_db.json")
                self.reload_configuration(force=True)
                self.verify_dockers_are_up()
                logger.info("Update SNMP config finished")

    def update_sai_xml_file(self, platform, hwsku, global_flag=False, local_flags=False):
        switch_sai_xml_path = f'/usr/share/sonic/device/{platform}/{hwsku}'
        default_sai_xml_file_name = 'sai.profile'

        logger.info('Get SAI init config file path')
        output = self.engine.run_cmd(
            f"sudo cat {switch_sai_xml_path}/{default_sai_xml_file_name} | grep \"SAI_INIT_CONFIG_FILE\"")

        logger.info(f'Get SAI init config file name {output}')
        # Match output of SAI_INIT_CONFIG_FILE=/usr/share/sonic/hwsku/sai_platform_name.xml
        actual_sai_xml_file_name = output.split("=")[1].split("/")[-1]

        logger.info(f'Get SAI actual config file name {actual_sai_xml_file_name}')
        actual_switch_sai_xml_path = switch_sai_xml_path + '/' + actual_sai_xml_file_name

        logger.info('Copy actual SAI config file to sonic-mgmt')
        self.engine.copy_file(source_file=f"{actual_switch_sai_xml_path}",
                              dest_file=f'/tmp/{actual_sai_xml_file_name}', file_system='/tmp/', direction='get')
        logger.info(f'Add appropriate flags to actual sai.xml {actual_switch_sai_xml_path}')
        self.modify_xml(f"/tmp/{actual_sai_xml_file_name}", global_flag=global_flag, local_flags=local_flags)

        logger.info('Copy modified file to DUT /tmp/ folder')
        self.engine.copy_file(source_file=f"/tmp/{actual_sai_xml_file_name}",
                              dest_file=actual_sai_xml_file_name, file_system='/tmp/',
                              overwrite_file=True, verify_file=False)

        logger.info(f'Move file {actual_sai_xml_file_name} from /tmp/ to {actual_switch_sai_xml_path}')
        self.engine.run_cmd(f'sudo mv /tmp/{actual_sai_xml_file_name} {actual_switch_sai_xml_path}')

    def modify_xml(self, filepath, global_flag=False, local_flags=False):
        doc = ET.parse(filepath)
        root_node = doc.getroot()
        child_node = root_node.find('platform_info')
        if global_flag:
            # Add global flag to child node
            logger.info('Add global flag to child node')
            global_flag = ET.Element("late-create-all-ports")
            global_flag.text = "1"
            child_node.append(global_flag)

        if local_flags:
            logger.info('Add local flag to child node')
            # Add local flag to all ports
            local_flag = ET.Element("late-create")
            local_flag.text = "true"
            for child in child_node:
                for element in child:
                    if element.tag == 'port-info':
                        element.append(local_flag)
        tree = ET.ElementTree(root_node)
        # ET.indent(tree, space="\t", level=0)
        tree.write(filepath, encoding="utf-8")

    def get_updated_config_db(self, topology_obj, setup_name, hwsku, platform):
        branch = get_sonic_branch(topology_obj, self.cli_obj.dut_alias)
        config_file_prefix = self.get_config_file_prefix(setup_name)
        config_db_file_name = f"{self.get_image_sonic_version()}_{config_file_prefix}config_db.json"
        if branch in ['202205', '202211', '202305']:
            base_config_db_json_file_name = SonicConst.CONFIG_DB_JSON
        else:
            base_config_db_json_file_name = SonicConst.CONFIG_DB_GNMI_JSON
        base_config_db_json_file_name = config_file_prefix + base_config_db_json_file_name
        base_config_db_json = self.get_config_db_json_obj(setup_name, base_config_db_json_file_name)
        self.create_extended_config_db_file(setup_name, base_config_db_json, file_name=config_db_file_name)
        self.update_config_db_metadata_router(setup_name, config_db_file_name)
        self.update_config_db_metadata_mgmt_port(setup_name, config_db_file_name)
        self.update_config_db_metadata_hwsku(setup_name, hwsku, config_db_file_name)
        self.update_config_db_features(setup_name, hwsku, platform, config_db_file_name)
        self.update_config_db_feature_config(setup_name, "database", "auto_restart", "always_enabled",
                                             config_db_file_name)
        default_mtu = "9100"
        self.update_config_db_port_mtu_config(setup_name, default_mtu, config_db_file_name)
        self.update_config_db_breakout_cfg(topology_obj, setup_name, hwsku, platform, config_db_file_name)
        # TODO: WA for the PR: https://github.com/sonic-net/sonic-buildimage/pull/16116,
        #  after the PR merged, it can be removed
        self.update_database_version(setup_name, config_db_file_name)
        if branch not in ['202205', '202211', '202305']:
            self.remove_syslog_telemetry_entry(setup_name, config_db_file_name)
        self.update_config_db_simx_setup_metadata_mac(setup_name, config_db_file_name)

        return config_db_file_name

    def update_config_db_simx_setup_metadata_mac(self, setup_name, config_db_json_file_name):
        expected_base_mac_file_path = f'/tmp/simx_base_mac_{self.engine.ip}'
        if os.path.exists(expected_base_mac_file_path):
            mac_address = os.popen(f"cat {expected_base_mac_file_path}").read()
            logger.info(f"Update the mac address for simx setup to: {mac_address}")
            config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
            config_db_json[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST][ConfigDbJsonConst.MAC] = \
                mac_address

            return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_features(self, setup_name, hwsku, platform, config_db_json_file_name):
        init_config_db_json = self.get_init_config_db_json_obj(hwsku, platform, setup_name)
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        image_supported_features = init_config_db_json[ConfigDbJsonConst.FEATURE]
        current_features = config_db_json[ConfigDbJsonConst.FEATURE]
        for feature, feature_properties in image_supported_features.items():
            if feature not in current_features:
                config_db_json[ConfigDbJsonConst.FEATURE][feature] = feature_properties
            has_timer_value = config_db_json[ConfigDbJsonConst.FEATURE][feature].pop("has_timer", None)
            if has_timer_value:
                config_db_json[ConfigDbJsonConst.FEATURE][feature]["delayed"] = has_timer_value
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_metadata_router(self, setup_name, config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        hwsku = config_db_json[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST][ConfigDbJsonConst.HWSKU]
        localhost_type = ConfigDbJsonConst.TOR_ROUTER
        if self.is_bluefield(hwsku):
            localhost_type = ConfigDbJsonConst.SONIC_HOST
        config_db_json[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST][ConfigDbJsonConst.TYPE] = \
            localhost_type
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_docker_routing_config_mode(self, topology_obj, mode='split',
                                                    remove_docker_routing_config_mode=False):
        config_db = self.get_config_db()
        config_db_localhost = config_db[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST]

        if remove_docker_routing_config_mode:
            config_db_localhost.pop(ConfigDbJsonConst.DOCKER_ROUTING_CONFIG_MODE, None)
        else:
            config_db_localhost.update({ConfigDbJsonConst.DOCKER_ROUTING_CONFIG_MODE: mode})

        save_config_db_json(self.engine, config_db)
        self.reboot_reload_flow(r_type=SonicConst.CONFIG_RELOAD_CMD, topology_obj=topology_obj, reload_force=True)

    def update_config_db_metadata_mgmt_port(self, setup_name, config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)

        config_db_json[ConfigDbJsonConst.MGMT_PORT] = json.loads(ConfigDbJsonConst.MGMT_PORT_VALUE)
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_metadata_hwsku(self, setup_name, hwsku, config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        config_db_json[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST][ConfigDbJsonConst.HWSKU] = \
            hwsku
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_hostname(self, setup_name, hostname, config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        config_db_json[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST][ConfigDbJsonConst.HOSTNAME] = \
            hostname
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_feature_config(self, setup_name, feature_name, feature_config_key, feature_config_value,
                                        config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        config_db_json[ConfigDbJsonConst.FEATURE][feature_name][feature_config_key] = feature_config_value
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_port_mtu_config(self, setup_name, mtu, config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        for k, _ in config_db_json[ConfigDbJsonConst.PORT].items():
            config_db_json[ConfigDbJsonConst.PORT][k]["mtu"] = mtu
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_database_version(self, setup_name, config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        cur_version = self.get_image_sonic_version()
        if 'VERSIONS' not in config_db_json.keys():
            config_db_json['VERSIONS'] = {}
        if 'DATABASE' not in config_db_json['VERSIONS'].keys():
            config_db_json['VERSIONS']['DATABASE'] = {}
        if "201911" in cur_version:
            config_db_json['VERSIONS']['DATABASE']["VERSION"] = "version_1_0_6"
        else:
            config_db_json['VERSIONS']['DATABASE']["VERSION"] = "version_2_0_0"
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def remove_syslog_telemetry_entry(self, setup_name, config_db_json_file_name):
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name=config_db_json_file_name)
        syslog_config_key = "SYSLOG_CONFIG_FEATURE"
        if syslog_config_key in config_db_json:
            if "telemetry" in config_db_json[syslog_config_key]:
                config_db_json[syslog_config_key].pop("telemetry")
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    def update_config_db_metadata_mgmt_ip(self, setup_name, ip, file_name=SonicConst.CONFIG_DB_JSON):
        def _get_subnet_mask(ip, interfaces_ips_output):
            for elem in interfaces_ips_output:
                if InfraConst.IP in elem:
                    if elem[InfraConst.IP] == ip:
                        return elem[InfraConst.MASK]

        def _get_default_gw():
            def _get_by_iproute():
                routes = self.cli_obj.route.show_ip_route()
                default_gw_obj = re.search(r'0\.0\.0\.0\/0 \[.*\] via (.*), eth0', routes)
                return default_gw_obj.group(1) if default_gw_obj else None

            def _get_by_arp():
                arp_table_dict = self.cli_obj.arp.show_arp_table()
                for arp_ip, arp_info in arp_table_dict.items():
                    if arp_info['Iface'] == 'eth0' and arp_info['MacAddress'] != '(incomplete)':
                        return arp_ip

            _default_gw = _get_by_iproute()
            if not _default_gw:
                _default_gw = _get_by_arp()
            return _default_gw

        config_db_json = self.get_config_db()
        mask = _get_subnet_mask(ip, self.cli_obj.ip.get_interface_ips('eth0'))
        default_gw = _get_default_gw()
        config_db_json[ConfigDbJsonConst.MGMT_INTERFACE] = \
            json.loads(ConfigDbJsonConst.MGMT_INTERFACE_VALUE % (ip, mask, default_gw))

        return self.create_extended_config_db_file(setup_name, config_db_json, file_name)

    @staticmethod
    def is_platform_supports_split_without_unmap(hwsku):
        platform_prefix_with_unmap = ["SN2410", "SN2700", "SN4600"]
        for platform_prefix in platform_prefix_with_unmap:
            if re.search(platform_prefix, hwsku):
                return False
        return True

    def update_config_db_breakout_cfg(self, topology_obj, setup_name, hwsku, platform, config_db_json_file_name):
        init_config_db_json = self.get_init_config_db_json_obj(hwsku, platform, setup_name)
        config_db_json = self.get_config_db_json_obj(setup_name, config_db_json_file_name)
        if init_config_db_json.get("BREAKOUT_CFG") and not self.is_bluefield(hwsku):
            config_db_json = self.update_breakout_cfg(topology_obj, init_config_db_json, config_db_json, hwsku)
        return self.create_extended_config_db_file(setup_name, config_db_json, file_name=config_db_json_file_name)

    @staticmethod
    def is_bluefield(hwsku):
        for bf_hwsku in BluefieldConstants.BLUEFIELD_HWSKUS_LIST:
            if bf_hwsku.lower() in hwsku.lower():
                return True
        return False

    @staticmethod
    def is_performance_setup(str_with_setup_name):
        return 'performance' in str_with_setup_name

    def is_default_hwsku(self, hwsku, setup_name):
        is_default_hwsku = True
        if self.is_performance_setup(setup_name) and hwsku == PerformanceSetupConstants.HWSKU:
            is_default_hwsku = False
        return is_default_hwsku

    @staticmethod
    def get_config_db_json_obj(setup_name, config_db_json_file_name=SonicConst.CONFIG_DB_JSON):
        config_db_path = str(os.path.join(InfraConst.MARS_TOPO_FOLDER_PATH, setup_name, config_db_json_file_name))
        with open(config_db_path) as config_db_json_file:
            config_db_json = json.load(config_db_json_file)
        return config_db_json

    def get_init_config_db_json_obj(self, hwsku, platform, setup_name):
        cmd = f"sonic-cfggen -k {hwsku} -H -j /etc/sonic/init_cfg.json --print-data"
        if not self.is_default_hwsku(hwsku, setup_name):
            switch_config_ini_path = f'/usr/share/sonic/device/{platform}/{hwsku}/{SonicConst.PORT_CONFIG_INI}'
            cmd = f"sonic-cfggen -k {hwsku} -H -j /etc/sonic/init_cfg.json -p {switch_config_ini_path} --print-data"
        init_config_db = self.engine.run_cmd(cmd, print_output=False)
        init_config_db_json = json.loads(init_config_db)
        return init_config_db_json

    def get_hwsku_json_as_dict(self, platform, hwsku):
        hwsku_path = f'/usr/share/sonic/device/{platform}/{hwsku}/hwsku.json'
        data = self.engine.run_cmd(f'cat {hwsku_path}')
        return json.loads(data)

    def update_breakout_cfg(self, topology_obj, init_config_db_json, config_db_json, hwsku):
        """
        This function updates the config_sb.json file with BREAKOUT_CFG section.
        In cases of systems where the consecutive port is unmapped after split of 4,
        the static split ports of 4, will not be include in the BREAKOUT_CFG.

        :param topology_obj: a topology object fixture
        :param init_config_db_json: a json object of the initial config_db.json file on the dut
        :param config_db_json: a json object of the config_db.json file on the dut
        :param hwsku:  hwsku of the dut  i.e, Mellanox-SN2700
        :return: the name of the updated config_db.json file with BREAKOUT_CFG section
        """
        breakout_cfg_dict = init_config_db_json.get("BREAKOUT_CFG")
        platform_json_obj = json_file_helper.get_platform_json(self.engine, self.cli_obj)
        parsed_platform_json_by_breakout_modes = self.parse_platform_json(topology_obj, platform_json_obj,
                                                                          parse_by_breakout_modes=True)
        split_ports_for_update = get_all_split_ports_parents(config_db_json, topology_obj)
        unsplit_ports_for_update = get_all_unsplit_ports(config_db_json, topology_obj)
        # TODO this is WA for virtual smartswitch, when last 4 ports connected to DPU and supports only 1x200G
        if hwsku == 'Mellanox-SN4700-O28':
            for i in range(1, 6):
                port = unsplit_ports_for_update[-i]
                parsed_platform_json_by_breakout_modes[port][1] = {'1x200G[100G,50G,40G,25G,10G,1G]'}
                config_db_json['PORT'][port]['speed'] = '200000'
                # TODO add condition when the name of virtual setup is know: "if not virtual_setup"
                # For CI/Build and regression on canonical setups. Last port connected to host with max 100G
                port = unsplit_ports_for_update[-1]
                parsed_platform_json_by_breakout_modes[port][1] = {'1x100G[50G,25G,10G,1G]'}
                config_db_json['PORT'][port]['speed'] = '100000'
        self.update_breakout_mode_for_split_ports(split_ports_for_update, hwsku, breakout_cfg_dict,
                                                  config_db_json, parsed_platform_json_by_breakout_modes)
        self.update_breakout_mode_for_unsplit_ports(unsplit_ports_for_update, breakout_cfg_dict,
                                                    config_db_json, parsed_platform_json_by_breakout_modes)
        port_info_dict = config_db_json.get(ConfigDbJsonConst.PORT, [])
        breakout_cfg_dict = {port: breakout_mode for port, breakout_mode in breakout_cfg_dict.items()
                             if port in port_info_dict}
        config_db_json["BREAKOUT_CFG"] = breakout_cfg_dict
        return config_db_json

    def is_supported_split_mode(self, hwsku, split_num):
        split_supported_without_unmap = self.is_platform_supports_split_without_unmap(hwsku) or split_num == 2
        platform_not_sn3800 = not re.search("SN3800", hwsku)
        split_supported_on_sn5 = True
        if re.search("SN5[46]00", hwsku) and split_num == 8:
            split_supported_on_sn5 = False
        return split_supported_without_unmap and platform_not_sn3800 and split_supported_on_sn5

    def update_breakout_mode_for_split_ports(self, split_ports_for_update, hwsku, breakout_cfg_dict,
                                             config_db_json, parsed_platform_json_by_breakout_modes):
        for port, split_num in split_ports_for_update:
            if self.is_supported_split_mode(hwsku, split_num):
                self.update_port_breakout_cfg_mode(breakout_cfg_dict, port, config_db_json, split_num,
                                                   parsed_platform_json_by_breakout_modes)

    def update_breakout_mode_for_unsplit_ports(self, unsplit_ports_for_update, breakout_cfg_dict,
                                               config_db_json, parsed_platform_json_by_breakout_modes):
        unsplit_ports_split_num = 1
        for port in unsplit_ports_for_update:
            self.update_port_breakout_cfg_mode(breakout_cfg_dict, port, config_db_json,
                                               unsplit_ports_split_num,
                                               parsed_platform_json_by_breakout_modes)

    @staticmethod
    def update_port_breakout_cfg_mode(breakout_cfg_dict, port, config_db_json,
                                      split_num, parsed_platform_json_by_breakout_modes):
        breakout_cfg_dict[port]["brkout_mode"] = get_port_current_breakout_mode(config_db_json, port, split_num,
                                                                                parsed_platform_json_by_breakout_modes)

    @staticmethod
    def create_extended_config_db_file(setup_name, config_db_json, file_name=SonicConst.EXTENDED_CONFIG_DB_PATH):
        new_config_db_json_path = str(os.path.join(InfraConst.MARS_TOPO_FOLDER_PATH,
                                                   setup_name,
                                                   file_name))
        if os.path.exists(new_config_db_json_path):
            os.remove(new_config_db_json_path)
        with open(new_config_db_json_path, 'w') as f:
            json.dump(config_db_json, f, indent=4)
            f.write('\n')
        os.chmod(new_config_db_json_path, 0o777)
        return file_name

    def update_dhclient_lease_time(self):
        dhclient_lease_time = 'send dhcp-lease-time 7200;'
        dhclient_conf_file = '/usr/share/sonic/templates/dhclient.conf.j2'
        update_dhclient_lease_time_cmd = f"""
        if grep -q dhcp-lease-time {dhclient_conf_file}; then
            sudo sed -i 's/^send dhcp-lease-time.*/{dhclient_lease_time}/g' {dhclient_conf_file}
        else
            sudo sed -i '/^send host-name = gethostname();/a {dhclient_lease_time}' {dhclient_conf_file}
        fi
        """
        self.engine.run_cmd(update_dhclient_lease_time_cmd, validate=True)

    def install_wjh(self, wjh_deb_url):
        wjh_package_local_name = '/home/admin/wjh.deb'
        self.engine.run_cmd('sudo curl {} -o {}'.format(wjh_deb_url, wjh_package_local_name))
        self.engine.run_cmd('sudo dpkg -i {}'.format(wjh_package_local_name), validate=True)
        logger.info('Sleep {} after what-just-happened installation'.format(InfraConst.SLEEP_AFTER_WJH_INSTALLATION))
        time.sleep(InfraConst.SLEEP_AFTER_WJH_INSTALLATION)
        self.set_feature_state('what-just-happened', 'enabled')
        self.save_configuration()
        self.engine.run_cmd('sudo rm -f {}'.format(wjh_package_local_name))
        retry_call(self._verify_dockers_are_up,
                   fargs=[[AppExtensionInstallationConstants.WJH_APP_NAME]],
                   tries=24,
                   delay=10,
                   logger=logger)

    def execute_command_in_docker(self, docker, command):
        return self.engine.run_cmd('docker exec -i {} {}'.format(docker, command))

    def copy_to_docker(self, docker, src_path_on_host, dst_path_in_docker):
        return self.engine.run_cmd('docker cp {} {}:{}'.format(src_path_on_host, docker, dst_path_in_docker))

    def copy_from_docker(self, docker, dst_path_on_host, src_path_in_docker):
        return self.engine.run_cmd('sudo docker cp {}:{} {}'.format(docker, src_path_in_docker, dst_path_on_host))

    def remove_from_docker(self, docker, src_path_in_docker):
        return self.engine.run_cmd('sudo docker exec {} rm -rf {}'.format(docker, src_path_in_docker))

    def get_warm_reboot_status(self):
        return self.engine.run_cmd('systemctl is-active warmboot-finalizer')

    def check_warm_reboot_status(self, expected_status):
        warm_reboot_status = self.get_warm_reboot_status()
        if expected_status not in warm_reboot_status:
            raise Exception('warm-reboot status "{}" not as expected "{}"'.format(warm_reboot_status, expected_status))

    def get_config_db(self):
        config_db_json = self.engine.run_cmd('cat {} ; echo'.format(SonicConst.CONFIG_DB_JSON_PATH), print_output=False)
        return json.loads(config_db_json)

    def get_config_db_from_running_config(self):
        config = self.engine.run_cmd('sudo show runningconfiguration all', print_output=False)
        return json.loads(config)

    def is_spc1(self, cli_object):
        """
        Function to check if the current DUT is SPC1
        :param cli_object: cli_object
        """
        platform = cli_object.chassis.get_platform()
        # if sn2 in platform, it's spc1. e.g. x86_64-mlnx_msn2700-r0
        return 'sn2' in platform

    def is_spc2(self, cli_object):
        """
        Function to check if the current DUT is SPC2
        :param cli_object: cli_object
        """
        platform = cli_object.chassis.get_platform()
        # if sn3 in platform, it's spc1. e.g. x86_64-mlnx_msn3800-r0
        return 'sn3' in platform

    @classmethod
    def is_simx_moose(cls, engine):

        if cls._is_simx_moose is None:
            platform = engine.run_cmd("show platform summary | grep Platform | awk '{print $2}'")
            cls._is_simx_moose = all(condition in platform for condition in ('sn5', 'simx'))
        return cls._is_simx_moose

    def show_version(self, validate=False):
        return self.engine.run_cmd('show version', validate=validate)

    def parse_platform_json(self, topology_obj, platform_json_obj, parse_by_breakout_modes=False):
        """
        parsing platform breakout options and config_db.json breakout configuration.
        :param topology_obj: topology object fixture
        :param platform_json_obj: a json object of platform.json file
        :param parse_by_breakout_modes: If true the function will return a dictionary with
        available breakout options by split number for all dut ports
        :return: a dictionary with available speeds option/ breakout options for each split number on all dut ports
        i.e, parse_by_breakout_modes = FALSE

           { 'Ethernet0' :{'1': [200G,100G,50G,40G,25G,10G,1G],
                           '2': [100G, 50G,40G,25G,10G,1G],
                           '4': [50G,40G,25G,10G,1G]},..}

        OR Iin case of: parse_by_breakout_modes = TRUE

           { 'Ethernet0' :    {1:{'1x100G[50G,40G,25G,10G]'},
                               2: {'2x50G[40G,25G,10G]'},
                               4: {'4x25G[10G]'},...}

        """
        ports_speeds_by_modes_info = {}
        breakout_options = SonicConst.BREAKOUT_MODES_REGEX
        if not platform_json_obj.get("interfaces"):
            ports_speeds_by_modes_info = self.generate_mock_ports_speeds(topology_obj, parse_by_breakout_modes)
        else:
            for port_name, port_dict in platform_json_obj["interfaces"].items():
                port_start_index = int(re.search(r'Ethernet(.*)', port_name).group(1))
                lanes = port_dict[SonicConstant.LANES].split(",")
                breakout_modes = re.findall(breakout_options, ",".join(list(port_dict[SonicConstant.BREAKOUT_MODES].
                                                                            keys())))
                lane_count = len(lanes)
                breakout_ports = ["Ethernet{}".format(port_start_index + i) for i in range(lane_count)]
                for port in breakout_ports:
                    if port in topology_obj.players_all_ports[self.dut_alias]:
                        if parse_by_breakout_modes:
                            ports_speeds_by_modes_info[port] = get_split_mode_supported_breakout_modes(breakout_modes)
                        else:
                            ports_speeds_by_modes_info[port] = get_split_mode_supported_speeds(breakout_modes)
        return ports_speeds_by_modes_info

    @staticmethod
    def generate_mock_ports_speeds(topology_obj, parse_by_breakout_modes=False):
        if parse_by_breakout_modes:
            raise AssertionError("This version doesn't support platform.json,\n"
                                 "there no mock option for interfaces breakout mode option")
        else:
            mock_ports_speeds_by_modes_info = {}
            port_list = get_dut_default_ports_list(topology_obj)
            for port in port_list:
                mock_ports_speeds_by_modes_info[port] = {
                    1: ['100G', '50G', '25G', '10G'],
                    2: ['50G', '25G', '10G'],
                    4: ['25G', '10G']
                }
            logger.debug("Mock ports speed option dictionary: {}".format(mock_ports_speeds_by_modes_info))
            return mock_ports_speeds_by_modes_info

    def show_warm_restart_state(self):
        """
        Show warm_restart_state
        Example:
            name             restore_count  state
            -------------  ---------------  ----------------------
            warm-shutdown                0  pre-shutdown-succeeded
            vlanmgrd                     4  reconciled
            cpu-report                   1  reconciled
            vrfmgrd                      4  reconciled
            syncd                        4
            neighsyncd                   4  reconciled
        return: warm_restart stat dict like below, or raise exception
            { "warm-shutdown": {"name":"warm-shutdown", "restore_count":"0", "state": "pre-shutdown-succeeded"},
              "vlanmgrd": {"name":"vlanmgrd", "restore_count":"4", "state": "reconciled"},
              "cpu-report": {"name":"cpu-report", "restore_count":"1", "state": "reconciled"},
              "vrfmgrd": {"name":"vrfmgrd", "restore_count":"4", "state": "reconciled"},
              "syncd": {"name":"syncd", "restore_count":"4", "state": ""},
              "neighsyncd", {"name":"neighsyncd", "restore_count":"4", "state": "reconciled"}
            }
        """
        warm_restart_state = self.engine.run_cmd("show warm_restart state")
        warm_restart_state_dict = generic_sonic_output_parser(warm_restart_state,
                                                              headers_ofset=0,
                                                              len_ofset=1,
                                                              data_ofset_from_start=2,
                                                              data_ofset_from_end=None,
                                                              column_ofset=2,
                                                              output_key='name')
        return warm_restart_state_dict

    def get_base_and_target_images(self):
        """
        This method getting base and target image from "sonic-installer list" output
        """
        installed_list_output = self.get_sonic_image_list()
        target_image = re.search(r'Current:\s(.*)', installed_list_output, re.IGNORECASE).group(1)
        try:
            available_images = re.search(r'Available:\s\n(.*)\n(.*)', installed_list_output, re.IGNORECASE)
            available_image_1 = available_images.group(1)
            available_image_2 = available_images.group(2)
            if target_image == available_image_1:
                base_image = available_image_2
            else:
                base_image = available_image_1
        except Exception:
            logger.warning('Only 1 installed image available')
            base_image = None

        return base_image, target_image

    def verify_installed_extensions_running(self):
        """
        Verify installed mellanox app_extension to image exist in docker ps output
        :return: None if successful, otherwise Exception
        """
        if self.cli_obj.app_ext.verify_version_support_app_ext():
            installed_mellanox_ext = get_installed_mellanox_extensions(self.cli_obj)
            if installed_mellanox_ext:
                retry_call(self._verify_dockers_are_up,
                           fargs=[installed_mellanox_ext],
                           tries=36,
                           delay=10,
                           logger=logger)

    def is_dummy_command_succeed(self):
        try:
            self.engine.run_cmd(DUMMY_COMMAND, validate=True)
            logger.info('login with credentials username: {} ,password:{} succeed!'.
                        format(self.engine.username, self.engine.password))
            return True
        except netmiko.ssh_exception.NetmikoAuthenticationException:
            logger.info('login with credentials username: {} ,password:{} did not succeed!'.
                        format(self.engine.username, self.engine.password))
            return False

    def if_other_credentials_used_set_boot_order_onie(self):
        engine = self.get_sonic_engine_try_different_passwords()
        if engine:
            with allure.step("Other credentials used then default"):
                logger.info('Other credentials used then default')
                with allure.step('Setting boot order to onie'):
                    self.set_next_boot_entry_to_onie()
                    self.engine = engine
                with allure.step('Rebooting the switch'):
                    engine.reload(['sudo reboot'], wait_after_ping=25, ssh_after_reload=False)

    def get_sonic_engine_try_different_passwords(self):
        for password in DefaultCredentialConstants.OTHER_SONIC_PASSWORD_LIST:
            engine = LinuxSshEngine(
                self.engine.ip, username=DefaultCredentialConstants.OTHER_SONIC_USER, password=password)
            if self.is_dummy_command_succeed():
                return engine

    def enable_info_logging_on_docker(self, docker_name):
        self.engine.run_cmd(f"{docker_name}loglevel -l INFO -a")

    def restart_service(self, service_name):
        self.engine.run_cmd(f'sudo service {service_name} restart')

    def prepare_nvidia_air_basic_config_db_json(self, topology_obj, setup_name, hwsku, platform):
        config_db_dict = self.get_init_config_db_json_obj(hwsku, platform, setup_name)
        dut_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        config_db_dict['DEVICE_METADATA']['localhost']['hostname'] = dut_name
        for interface in config_db_dict['PORT']:
            config_db_dict['PORT'][interface]['admin_status'] = 'up'
        ips_dict = get_dhcp_ips_dict(topology_obj)
        gw_ip = ips_dict[SonicHostsConstants.OOB_MGMT_SERVER]
        dut_ip = ips_dict[SonicHostsConstants.DUT]
        config_db_dict['MGMT_INTERFACE'] = {f'eth0|{dut_ip}/24': {'gwaddr': gw_ip}}
        config_db_path = os.path.join(InfraConst.MARS_TOPO_FOLDER_PATH, setup_name, SonicConst.CONFIG_DB_JSON)
        self.create_extended_config_db_file(setup_name, config_db_dict, config_db_path)

    def get_simx_version_and_chip_type(self):
        """
        This method is to get the simx version and chip type
        :return: version, chip_type
        """
        reg_simx_version = ".*Vendor specific: SimX version (?P<version>.*)"
        reg_simx_chip_type = ".*Vendor specific: SimX chip type: (?P<chip_type>.*)"

        simx_info = self.engine.run_cmd('sudo lspci -vvv | grep SimX')
        '''
        simx info like below:
        Product Name: SimX: Spectrum simulation
                        [V1] Vendor specific: SimX version 5.1.1057
                        [V2] Vendor specific: SimX chip type: Spectrum-3
        '''

        chip_type, version = '', ''

        for line in simx_info.split("\n"):
            match_version = re.match(reg_simx_version, line)
            if match_version:
                version = match_version.groupdict()["version"].strip()
            else:
                match_chip_type = re.match(reg_simx_chip_type, line)
                if match_chip_type:
                    chip_type = match_chip_type.groupdict()["chip_type"].strip()

        logger.info(f'Simx version:{version}, simx chip type:{chip_type}')
        return version, chip_type

    def get_sai_version(self):
        """
        This method is to get the sai version
        :return: sai_version
        """
        reg_sai_version = r".*mlnx.SAIBuild(?P<version>[\d.]+)\s+.*"

        sai_info = self.engine.run_cmd('docker exec syncd bash -c "dpkg -l | grep mlnx-sai"')
        '''
        sai info like below:
        ii  mlnx-sai     1.mlnx.SAIBuild2211.23.1.0     amd64        contains SAI implementation for Mellanox hardware
        '''
        sai_version = None
        sai_res = re.match(reg_sai_version, sai_info)
        if sai_res:
            sai_version = sai_res.groupdict()["version"].strip()

        logger.info(f'sai version:{sai_version}')
        return sai_version

    def get_bootctl_status(self):
        """
        This method is to get the output of bootctl command
        :return: bootctl output
        """
        return self.engine.run_cmd('bootctl', validate=True)

    def is_async_route_enabled(self, async_route_param):
        """
        Checks the status of async_route feature

        :param str async_route_param: async_route feature parameter from sai.profile, f.e. 'SAI_ASYNC_ROUTING_ENABLED=1'
        :return bool: True if feature is enabled, False otherwise
        """
        async_route_status = async_route_param.split('=')[-1]
        return async_route_status == '1'

    def enable_async_route_feature(self, platform, hwsku):
        """
        Checks if async route feature is enabled and enables it otherwise
        """
        switch_sai_xml_path = f'/usr/share/sonic/device/{platform}/{hwsku}'
        default_sai_xml_file_name = 'sai.profile'
        async_routing_enabled = 'SAI_ASYNC_ROUTING_ENABLED'

        logger.info('Get SAI init config file path')
        sai_profile_path = f'{switch_sai_xml_path}/{default_sai_xml_file_name}'
        async_route_param = self.engine.run_cmd(f'sudo cat {sai_profile_path} | grep {async_routing_enabled}')
        if async_route_param and not self.is_async_route_enabled(async_route_param):
            if self.is_async_route_enabled(async_route_param):
                logger.info('Async_route feature is already enabled')
            else:
                self.engine.run_cmd(f'sed -i "/{async_routing_enabled}/d" {sai_profile_path}')
                self.engine.run_cmd(f'echo "{async_routing_enabled}=1" >> {sai_profile_path}')


class SonicGeneralCli202012(SonicGeneralCliDefault):

    def __init__(self, engine, cli_obj, dut_alias):
        self.engine = engine
        self.cli_obj = cli_obj
        self.dut_alias = dut_alias

    def reload_flow(self, ports_list=None, topology_obj=None, reload_force=False):
        """
        Reloading switch and validate dockers and ports state
        :param ports_list: list of the ports to check status after reboot
        :param topology_obj: topology object
        :param reload_force: provide if want to do reload with -f flag(force)
        :return: None, raise error in case of unexpected result
        """
        if not (ports_list or topology_obj):
            raise Exception('ports_list or topology_obj must be passed to reload_flow method')
        if not ports_list:
            ports_list = topology_obj.players_all_ports[self.dut_alias]
        with allure.step('Reloading dut'):
            logger.info("Reloading dut")
            self.reload_configuration(reload_force)
            self.port_reload_reboot_checks(ports_list)

    def reload_configuration(self, force=False):
        if force:
            logger.warning('Force reload config not supported on branch 202012, using default cmd "config reload -y"')

        cmd = 'sudo config reload -y'
        self.engine.run_cmd(cmd, validate=True)
