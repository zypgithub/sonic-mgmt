import concurrent.futures
import copy
import logging
import os
import netmiko
import json
import re
import shutil
import time
from retry.api import retry_call
import yaml

import allure
import pytest
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from netmiko.ssh_exception import NetmikoAuthenticationException
from infra.tools.topology_tools.nogaq import upload_data_to_noga
from infra.tools.general_constants.constants import NogaConstants

from ngts.constants.constants import PlayersAliases, SonicDeployConstants, MarsConstants, SerialLoggerConst, CliType
from ngts.constants.constants import PlayersAliases, SerialLoggerConst, SSHConsts
from ngts.constants.performance_constants import PerfConsts, Cl_Consts
from ngts.scripts.sonic_deploy.image_preparetion_methods import get_real_paths, prepare_images
from ngts.helpers.general_helper import extract_host_details_from_topo_obj, get_cli_obj
from ngts.scripts.sonic_deploy.sonic_only_methods import is_community
from ngts.nvos_tools.Devices.IbDevice import BlackMambaSwitch, CrocodileSwitch
from ngts.cli_wrappers.nvue.cumulus.cumulus_general_cli import CumulusGeneralCli
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.dvs.dvs_general_clis import DvsGeneralCli
from ngts.cli_wrappers.sonic.sonic_general_clis import SonicGeneralCliDefault
from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon
from ngts.helpers.run_process_on_host import wait_until_background_procs_done
from ngts.common.util import save_specified_installed_dpus, get_installed_dpu_info

logger = logging.getLogger()


class DeploymentContext:
    """
    Encapsulates all deployment parameters and derived values.

    This class replaces the complex parameter passing and initialization logic
    from the original test_deploy_and_upgrade function, providing a single
    source of truth for deployment configuration.
    """

    def __init__(self, topology_obj, is_simx, is_performance, base_version, base_version_dpu,
                 target_version, serve_files, sonic_topo, neighbor_type, deploy_only_target,
                 port_number, setup_name, platform_params, deploy_dpu, deploy_type,
                 apply_base_config, reboot_after_install, is_shutdown_bgp, fw_pkg_path,
                 recover_by_reboot, reboot, additional_apps, workspace_path, wjh_deb_url,
                 verify_secure_boot, chip_type, destination_hwsku, show_setup_versions,
                 serial_log_analyzers, fanout_target_version, request, is_air):
        """
        Initialize DeploymentContext with all parameters.

        This constructor replaces the initialization logic from lines 102-123
        of the original test_deploy_and_upgrade function.
        """
        # Store all input parameters
        self.topology_obj = topology_obj
        self.is_simx = is_simx
        self.is_performance = is_performance
        self.base_version = base_version
        self.base_version_dpu = base_version_dpu
        self.target_version = target_version
        self.serve_files = serve_files
        self.sonic_topo = sonic_topo
        self.neighbor_type = neighbor_type
        self.deploy_only_target = deploy_only_target
        self.port_number = port_number
        self.setup_name = setup_name
        self.platform_params = platform_params
        self.deploy_dpu = deploy_dpu
        self.deploy_type = deploy_type
        self.apply_base_config = apply_base_config
        self.reboot_after_install = reboot_after_install
        self.is_shutdown_bgp = is_shutdown_bgp
        self.fw_pkg_path = fw_pkg_path
        self.recover_by_reboot = recover_by_reboot
        self.reboot = reboot
        self.additional_apps = additional_apps
        self.workspace_path = workspace_path
        self.wjh_deb_url = wjh_deb_url
        self.verify_secure_boot = verify_secure_boot
        self.chip_type = chip_type
        self.destination_hwsku = destination_hwsku
        self.show_setup_versions = show_setup_versions
        self.serial_log_analyzers = serial_log_analyzers
        self.fanout_target_version = fanout_target_version
        self.request = request
        self.is_air = is_air

        # Initialize derived values (replaces lines 102-123 from original function)
        self._initialize()

    def _initialize(self):
        """
        Initialize derived values after the object is created.

        This method replaces the initialization logic from lines 102-123
        of the original test_deploy_and_upgrade function.
        """
        self._initialize_setup_info()
        self._initialize_hwsku()
        self._initialize_image_urls()
        self._validate_and_adjust_parameters()

    def _initialize_setup_info(self):
        """Initialize setup information from topology object."""
        with allure.step('preparations'):
            with allure.step('Initialize setup information'):
                logger.info("Deploy SONiC testing topology and upgrade switch")

            self.setup_info = DeployTopologyHelper.get_info_from_topology(self.topology_obj, self.workspace_path)
            self.setup_info['setup_name'] = self.setup_name

            # Create convenient attributes for commonly used data
            self.all_duts = self.setup_info['duts']
            self.primary_dut = self.setup_info['duts'][0]
            self.primary_cli_obj = self.setup_info['duts'][0]['cli_obj']
            self.all_cli_objs = [dut['cli_obj'] for dut in self.setup_info['duts']]

    def _initialize_hwsku(self):
        """Initialize hardware SKU configuration."""
        self.destination_hwsku = DeployTopologyHelper.get_hwsku(
            self.sonic_topo,
            self.destination_hwsku,
            self.setup_name
        )

    def _initialize_image_urls(self):
        """Prepare image versions and URLs."""
        with allure.step('prepare versions paths/urls'):

            # Get real paths for base and target versions
            cli_type = self.setup_info["duts"][0]["cli_type"]
            self.base_version, self.target_version = get_real_paths(
                self.base_version,
                self.target_version,
                cli_type
            )

            # Prepare images for installation
            self.image_urls = DeployImageHelper.prepare_images_to_install(
                self.base_version,
                self.target_version,
                self.serve_files,
                cli_type
            )

            # Get base and target version URLs
            self.base_version_url = DeployImageHelper.get_base_version_url(
                self.deploy_only_target,
                self.image_urls
            )

            self.target_version_url = (
                '' if not self.target_version
                else DeployImageHelper.get_target_version_url(self.image_urls)
            )

    def _validate_and_adjust_parameters(self):
        """Validate parameters and make necessary adjustments."""
        # Adjust apply_base_config for ptf-any topology
        if self.sonic_topo == 'ptf-any':
            self.apply_base_config = True

        # Validate and merge WJH and additional apps parameters
        if self.wjh_deb_url and self.additional_apps:
            raise Exception(
                'Arguments "wjh_deb_url" and "additional_apps" can not be used together'
            )

        if not self.additional_apps:
            self.additional_apps = self.wjh_deb_url

    @classmethod
    def from_function_params(cls, **kwargs):
        """
        Factory method to create DeploymentContext from function parameters.

        This method provides a clean way to create a DeploymentContext object
        from the original test_deploy_and_upgrade function parameters.

        Args:
            **kwargs: All the parameters from the original test_deploy_and_upgrade function

        Returns:
            DeploymentContext: Initialized deployment context
        """
        return cls(**kwargs)

    def get_dut_by_alias(self, dut_alias):
        """
        Get DUT information for a specific DUT alias.

        Args:
            dut_alias: Alias of the DUT (e.g., 'dut', 'dut-b', 'dut-c')

        Returns:
            Dict: DUT information dictionary

        Raises:
            ValueError: If DUT with specified alias is not found
        """
        for dut in self.all_duts:
            if dut['dut_alias'] == dut_alias:
                return dut
        raise ValueError(f"DUT with alias '{dut_alias}' not found")

    def get_cli_obj(self, dut):
        """
        Get CLI object from a DUT dictionary.

        Args:
            dut: DUT dictionary containing CLI object

        Returns:
            CLI object for the specified DUT
        """
        return dut['cli_obj']


class DeployImageHelper:
    """Handle all image-related operations"""

    @staticmethod
    def get_related_image_urls(base_version_url, target_version_url, dut, use_ga_image=False):
        """
        Get the appropriate image URLs for a specific DUT.

        Args:
            base_version_url: Base version URL
            target_version_url: Target version URL
            dut: DUT information dictionary
            use_ga_image: Whether to use GA image for traffic generators

        Returns:
            Tuple of (base_version_url, target_version_url)
        """
        return DeployImageHelper.get_related_image_to_switch(
            base_version_url,
            target_version_url,
            dut,
            use_ga_image
        )

    @staticmethod
    def get_related_image_to_switch(base_version, target_version, dut, use_GA_image):
        """production devices support only prod versions of ONIE and SONiC"""
        if dut['dut_alias'] == "dut":
            base_version, target_version = DeployImageHelper.get_image_for_dut(base_version, target_version, dut)
        elif dut['dut_alias'] in PerfConsts.TG_ALIAS_LIST:
            base_version, target_version = DeployMultiNosHelper.get_image_for_traffic_generators(base_version, target_version, dut, use_GA_image)
        return base_version, target_version

    @staticmethod
    def get_image_for_dut(base_version, target_version, dut):
        if dut['cli_type'] == CliType.NVUE:
            if target_version.startswith('http'):
                target_version = '/auto/' + target_version.split('/auto/')[1]
        return base_version, target_version

    @staticmethod
    def prepare_images_to_install(base_version, target_version, serve_files, cli_type):
        """
        Prepare images to be installed
        :param base_version: base version argument
        :param target_version: target version argument
        :param serve_files: serve files
        :param cli_type: cli_type of the system
        :return:
        """
        with allure.step('Prepare images and get base version url'):
            return prepare_images(base_version, target_version, serve_files, cli_type)

    @staticmethod
    def get_base_version_url(deploy_only_target, image_urls):
        """Get base version url"""
        with allure.step('Get base version url'):
            base_version_url = image_urls["base_version"]
            if deploy_only_target:
                if image_urls["target_version"]:
                    base_version_url = image_urls["target_version"]
                else:
                    raise Exception(
                        'Argument "target_version" must be provided when "deploy_only_target" flag is set to "yes".'
                        ' Please provide a target version.')
        return base_version_url

    @staticmethod
    def get_target_version_url(image_urls):
        """Get target version url"""
        with allure.step('Get target version url'):
            return DeployImageHelper.get_base_version_url(True, image_urls)

    @staticmethod
    def cleanup_reboot_cause_history(topology_obj, setup_info):
        """
        Clean reboot-cause history after SONiC upgrade to resolve timezone conflicts.
        This function removes old reboot-cause history files that may have inconsistent
        timezone formats between different SONiC versions (e.g., 202411 IDT vs 202505 UTC).

        :param topology_obj: topology object containing device connections
        :param setup_info: setup information containing DUT details
        """
        logger.info("Starting reboot-cause history cleanup after SONiC upgrade")

        for dut in setup_info['duts']:
            dut_name = dut['dut_name']
            dut_alias = dut['dut_alias']
            try:
                logger.info(f"Cleaning reboot-cause history on DUT: {dut_name}")
                engine = topology_obj.players[dut_alias]['engine']
                # Commands to clean up reboot-cause history
                cleanup_commands = [
                    # Backup existing history (optional - for safety)
                    'sudo mkdir -p /host/reboot-cause/backup',
                    'sudo cp -r /host/reboot-cause/history/* /host/reboot-cause/backup/ 2>/dev/null || true',
                    # Remove all old reboot-cause history files
                    'sudo rm -f /host/reboot-cause/history/reboot-cause-*.json',
                    # Restart the process-reboot-cause service to reset state
                    'sudo systemctl restart process-reboot-cause.service || true',
                    # Verify cleanup
                    'ls -la /host/reboot-cause/history/ || true'
                ]
                for cmd in cleanup_commands:
                    try:
                        result = engine.run_cmd(cmd)
                        logger.debug(f"Command '{cmd}' executed on {dut_name}: {result}")
                    except Exception as e:
                        logger.warning(f"Non-critical error executing '{cmd}' on {dut_name}: {e}")
                logger.info(f"Reboot-cause history cleanup completed for DUT: {dut_name}")
            except Exception as e:
                logger.error(f"Failed to clean reboot-cause history on DUT {dut_name}: {e}")
                # Don't fail the entire upgrade process for history cleanup issues
                continue
        logger.info("Reboot-cause history cleanup completed for all DUTs")


class DeployTopologyHelper:
    """Handle topology and setup information"""

    @staticmethod
    def get_info_from_topology(topology_obj, workspace_path):
        """
        Creates a class which contains setup info
        :param topology_obj: topology object
        :param workspace_path: workspace_path argument
        :return: SetupInfo object
        """
        ansible_path = os.path.join(workspace_path, "sonic-mgmt/ansible/")
        setup_info = {'ansible_path': ansible_path, 'duts': [], 'fanouts': []}

        with allure.step("Create setup_info object"):
            for host in topology_obj.players:
                if host in PlayersAliases.duts_list:
                    cli_type, dut_alias, dut_ip, dut_name, engine, switch_type = extract_host_details_from_topo_obj(
                        topology_obj, host)
                    cli_obj = get_cli_obj(topology_obj, cli_type, switch_type, engine, host, dut_alias)
                    dut_info = {'dut_name': dut_name, 'cli_type': cli_type, 'engine': engine, 'cli_obj': cli_obj,
                                'dut_alias': dut_alias, 'switch_type': switch_type, 'dut_ip': dut_ip, 'cli': topology_obj.players[dut_alias]['cli']}
                    if dut_info['dut_alias'] == "dut":
                        setup_info['duts'].insert(0, dut_info)
                    else:
                        if 'dpu' not in dut_info['dut_alias']:
                            setup_info['duts'].append(dut_info)
                elif host == 'hypervisor':
                    hypervisor_name = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Common']['Name']
                    hypervisor_ip = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific']['ip']
                    hypervisor_info = {'hypervisor_name': hypervisor_name, 'hypervisor_ip': hypervisor_ip}
                    setup_info['hypervisor'] = hypervisor_info

        return setup_info

    @staticmethod
    def get_hwsku(sonic_topo, dest_hwsku, setup_name):
        if is_community(sonic_topo):
            base_path = os.path.dirname(os.path.realpath(__file__))
            default_hwsku_file_path = os.path.join(base_path, f"../../../{SonicDeployConstants.DEFAULT_HWSKU_FILE_PATH}")
            logger.info(f"Reading {SonicDeployConstants.DEFAULT_HWSKU_FILE_PATH}")
            with open(default_hwsku_file_path, 'r') as hwsku_json:
                hwsku_data = json.load(hwsku_json)
            if dest_hwsku:
                if dest_hwsku in hwsku_data[setup_name]['support_hwsku']:
                    return dest_hwsku
                else:
                    raise Exception(f"Un supported hwsku provided: {dest_hwsku}, "
                                    f"the supported hwsku: {hwsku_data[setup_name]['support_hwsku']}")

            else:
                logger.warning(f"No hwsku assigned, will use the default value: "
                               f"{hwsku_data[setup_name]['default_hwsku']}")
                return hwsku_data[setup_name]['default_hwsku']

    @staticmethod
    def filter_testbed_yaml_file(setup_info):
        """
        Remove from testbed.yaml file all configurations, which not relevant to setup.
        This action will save us ~1.5 minutes of runtime in the first test,
         where need to get basic_facts in the first time.
        :param setup_info: setup_info dictionary
        """

        duts = []
        for dut in setup_info['duts']:
            duts.append(dut['dut_name'])
        testbed_yaml_file_path = os.path.join(os.path.dirname(__file__), "../../../ansible/testbed.yaml")
        testbed_yaml_backup_file_path = os.path.join(os.path.dirname(__file__), "../../../ansible/testbed.yaml.backup")
        # backup of original file
        shutil.copyfile(testbed_yaml_file_path, testbed_yaml_backup_file_path)
        # get current testbed.yaml data
        with open(testbed_yaml_file_path, 'r') as f:
            data = yaml.safe_load(f)
        # entry should include at least one on switch name
        filtered_data = []
        for entry in data:
            for device in entry['dut']:
                if device in duts:
                    filtered_data.append(entry)
                    break
        # store filtered data
        with open(testbed_yaml_file_path, 'w') as out_file:
            yaml.dump(filtered_data, out_file, default_flow_style=False)


class DeployConnectionHelper:
    """Handle SSH connections and OS detection"""

    @staticmethod
    def get_current_os_engine(dut_ip):
        logger.info("Trying connect with SSH to switch")
        for nos_name, creds in SSHConsts.SSH_CREDS_DICT.items():
            engine = DeployConnectionHelper.attempt_connect_to_switch(dut_ip, nos_name, creds)
            if engine:
                logger.info("Current OS is {}".format(nos_name))
                return nos_name, engine
        logger.error("SSH connection to Cumulus, SONiC, and DVS has failed, check switch")
        return None, None

    @staticmethod
    def attempt_connect_to_switch(ip, nos_name, creds_dict):
        try:
            username = creds_dict.get('username')
            password = creds_dict.get('password')
            engine = LinuxSshEngine(ip, username=username, password=password)
            engine.run_cmd("echo $?")
        except NetmikoAuthenticationException:
            logger.error(f"Login to with {nos_name} credentials has failed")
            return None

        return engine

    @staticmethod
    def handle_serial_log_analyzers(serial_log_analyzers):
        """
        Handle serial log analyzers - ignore manufacture stage if both manufacture and upgrade stages are present

        Args:
            serial_log_analyzers: Dictionary of serial log analyzers
        """
        for analyzer in serial_log_analyzers.values():
            # if manufacture and upgrade stages are both present then we don't analyze the manufacture stage because
            # it runs an older OS version so we shouldn't debug it.
            if {SerialLoggerConst.MANUFACTURE_STAGE, SerialLoggerConst.UPGRADE_STAGE} <= set(analyzer.list_stages()):
                analyzer.ignore_stage(SerialLoggerConst.MANUFACTURE_STAGE)


class DeployMultiNosHelper:
    """Handle multi-NOS operations and NOGA updates"""

    @staticmethod
    def get_image_for_traffic_generators(base_version, target_version, dut, use_GA_image):
        if dut['cli_type'] == CliType.SONIC:
            base_version = PerfConsts.SONIC_GA_IMAGE if use_GA_image else base_version
        elif dut['cli_type'] == CliType.NVUE:
            target_version = Cl_Consts.CL_GA_IMAGE if use_GA_image else target_version
        return base_version, target_version

    @staticmethod
    def validate_sudo_config(engine, current_os):
        if current_os == "Cumulus":
            cl_password = os.getenv("CUMULUS_SWITCH_PASSWORD")
            engine.run_cmd_set([
                "sudo sed -i --follow-symlinks 's/%sudo.*all=(all:all) all/%sudo all=(all:all) nopasswd: all/' /etc/sudoers",
                cl_password],
                patterns_list=["password for cumulus"])

    @staticmethod
    def multi_nos_pre_installation_steps(duts, target_cli_type, chip_type):
        logger.info("Multi NOS pre installation steps")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for dut in duts:
                executor.submit(DeployMultiNosHelper.do_multi_nos_pre_install, dut, target_cli_type, chip_type)

    @staticmethod
    def do_multi_nos_pre_install(dut, target_cli_type, chip_type):
        dut_ip = dut['dut_ip']
        current_os, engine = DeployConnectionHelper.get_current_os_engine(dut_ip)
        if engine:
            DeployMultiNosHelper.validate_sudo_config(engine, current_os)
            GeneralCliCommon(engine).uninstall_os_flow(current_os, target_cli_type, chip_type)

    @staticmethod
    def multi_nos_post_installation_steps(duts, target_cli_type, is_performance):
        for dut in duts:
            data_query = json.loads('{ "update": { "CLI_TYPE": "' + target_cli_type +
                                    '", "TYPE": "' + CliType.NOS_TO_TYPE_DICT[target_cli_type] +
                                    '"}, "filter": { "name": "' + dut['dut_name'] + '" }, "params": { "login_user": "' +
                                    NogaConstants.NOGA_USER +
                                    '", "api_key":"' + NogaConstants.NOGA_API_KEY + '" } }')
            logger.info(f"Set cli type of {dut['dut_name']} to {target_cli_type} and switch type to "
                        f"{CliType.NOS_TO_TYPE_DICT[target_cli_type]}")
            upload_data_to_noga(data_query)
        if is_performance:
            DeployMultiNosHelper.multi_nos_install_traffic_generator(duts)

    @staticmethod
    def multi_nos_install_traffic_generator(duts):
        install_threads = []
        executor = concurrent.futures.ThreadPoolExecutor()
        for dut in duts:
            cli_obj = dut['cli_obj']
            with allure.step('Install traffic generator on switch: {}'.format(dut['dut_name'])):
                install_threads.append((f"Traffic Generator install on {dut['dut_name']}",
                                        executor.submit(cli_obj.install_traffic_generator)))
        DeployOrchestrator.wait_until_deploy_background_process(install_threads)


class DeployOrchestrator:
    """Coordinate deployment operations and thread management"""

    def __init__(self, context):
        self.context = context
        self.pre_install_threads = {}
        self.install_threads = []

    @staticmethod
    def wait_until_deploy_background_process(install_threads, timeout=1200):
        for task_name, task in install_threads:
            with allure.step(f'Wait until {task_name} background process done'):
                try:
                    task.result(timeout=timeout)
                    logger.info(f"{task_name} finished successfully")
                except concurrent.futures.TimeoutError:
                    logger.error(f"{task_name} failed to complete in {timeout}s.")
                    raise

    def execute_pre_installation_steps(self):
        cli_obj = self.context.primary_cli_obj

        cli_obj.pre_installation_steps(self.context, self.pre_install_threads)

        replace_nos = self.context.request.config.getoption('--target_cli_type')
        if replace_nos:
            DeployMultiNosHelper.multi_nos_pre_installation_steps(self.context.all_duts, replace_nos, self.context.chip_type)

        return self.pre_install_threads

    def execute_installation(self):
        """Execute installation phase for all DUTs"""

        executor = concurrent.futures.ThreadPoolExecutor()
        use_GA_image = False

        for dut in self.context.all_duts:
            cli_obj = self.context.get_cli_obj(dut)
            related_base_version_url, related_target_version = DeployImageHelper.get_related_image_urls(
                self.context.base_version_url, self.context.target_version_url, dut, use_GA_image)

            if not cli_obj.is_dut_supports_image(related_base_version_url, dut['dut_name'], dut['cli_type']):
                continue

            with allure.step('Install image on dut: {}'.format(dut['dut_name'])):
                # Disconnect ssh connection
                self.context.topology_obj.players[dut['dut_alias']]['engine'].disconnect()
                platform_params_copy = copy.deepcopy(self.context.platform_params)

                self.install_threads.append((f"image install on {dut['dut_name']}",
                                             executor.submit(self.deploy_image,
                                                             topology_obj=self.context.topology_obj,
                                                             setup_name=self.context.setup_name,
                                                             image_url=related_base_version_url,
                                                             platform_params=platform_params_copy,
                                                             deploy_type=self.context.deploy_type,
                                                             apply_base_config=self.context.apply_base_config,
                                                             reboot_after_install=self.context.reboot_after_install,
                                                             is_shutdown_bgp=self.context.is_shutdown_bgp,
                                                             fw_pkg_path=self.context.fw_pkg_path,
                                                             cli_type=dut['cli_obj'],
                                                             target_image_url=related_target_version,
                                                             destination_hwsku=self.context.destination_hwsku,
                                                             setup_info=self.context.setup_info,
                                                             dut_alias=dut['dut_alias'],
                                                             fanout_deploy_threads=self.pre_install_threads,
                                                             serial_log_analyzers=self.context.serial_log_analyzers,
                                                             dut_ip=dut['dut_ip'],
                                                             fanout_target_version=self.context.fanout_target_version)))

        return self.install_threads

    def deploy_image(self, topology_obj, setup_name, platform_params, image_url, deploy_type,
                     apply_base_config, reboot_after_install, is_shutdown_bgp, fw_pkg_path, cli_type, target_image_url='',
                     destination_hwsku=None, setup_info=None, dut_alias=None, fanout_deploy_threads=None,
                     serial_log_analyzers=None, dut_ip='', fanout_target_version=None):
        cli_type.deploy_image_steps(
            topology_obj=topology_obj,
            setup_name=setup_name,
            platform_params=platform_params,
            image_url=image_url,
            deploy_type=deploy_type,
            apply_base_config=apply_base_config,
            reboot_after_install=reboot_after_install,
            is_shutdown_bgp=is_shutdown_bgp,
            fw_pkg_path=fw_pkg_path,
            target_image_url=target_image_url,
            destination_hwsku=destination_hwsku,
            setup_info=setup_info,
            dut_alias=dut_alias,
            fanout_deploy_threads=fanout_deploy_threads,
            serial_log_analyzers=serial_log_analyzers,
            dut_ip=dut_ip,
            fanout_target_version=fanout_target_version
        )
        time.sleep(30)

    def execute_post_installation_steps(self):
        cli_obj = self.context.primary_cli_obj

        cli_obj.post_installation_steps(self.context, DeployImageHelper)

        replace_nos = self.context.request.config.getoption('--target_cli_type')
        if replace_nos:
            DeployMultiNosHelper.multi_nos_post_installation_steps(self.context.setup_info['duts'], replace_nos, self.context.is_performance)

        DeployTopologyHelper.filter_testbed_yaml_file(self.context.setup_info)

    def execute_full_deployment(self):
        """
        Execute the complete deployment flow

        Returns:
            dict: Results containing thread information and status
        """
        results = {}

        # Phase 1: Pre-installation
        with allure.step('pre installation steps'):
            results['pre_install_threads'] = self.execute_pre_installation_steps()

        # Phase 2: Installation
        with allure.step('installation'):
            results['install_threads'] = self.execute_installation()
            self.wait_until_deploy_background_process(results['install_threads'], timeout=1500)

            # DPU installation if needed
            if self.context.deploy_dpu:
                with allure.step(f'Start to install the bfb image on DPUs:{self.context.base_version_dpu}'):
                    install_threads = []
                    executor = concurrent.futures.ThreadPoolExecutor()
                    for dut in self.context.setup_info['duts']:
                        install_threads.append((f"DPU image install on {dut['dut_name']}",
                                               executor.submit(DeployDpuHelper.bfb_install_dpu,
                                                               self.context.topology_obj,
                                                               self.context.base_version_dpu,
                                                               dut['dut_alias'], dut['dut_name'], dut['cli_obj'])))
                    DeployOrchestrator.wait_until_deploy_background_process(install_threads, timeout=2000)

        # Phase 3: Verify pre-installation processes
        with allure.step('verify pre installation processes are done'):
            self._verify_pre_installation_processes(results['pre_install_threads'])

        # Phase 4: Post-installation
        with allure.step('post installation steps'):
            self.execute_post_installation_steps()

            # Cleanup
            cache_full_path = os.path.join(os.path.dirname(__file__), '../../.pytest_cache')
            shutil.rmtree(cache_full_path, ignore_errors=True)

        return results

    def _verify_pre_installation_processes(self, pre_install_threads):
        """Verify pre-installation background processes are complete"""

        logger.info("Wait until pre-installation background process done")
        try:
            wait_until_background_procs_done(pre_install_threads)
        except AssertionError:
            # Give it another try if the background processes fail
            self.execute_pre_installation_steps()
            wait_until_background_procs_done(pre_install_threads)
        logger.info("Pre-installation background processes are done")


class DeployDpuHelper:
    """Handle DPU-specific deployment operations"""

    @staticmethod
    def bfb_install_dpu(topology_obj, base_version_dpu, dut_alias, dut_name, cli_obj):

        rshim_value, dpu_index_list, installed_dpus = get_installed_dpu_info(topology_obj, dut_alias, dut_name)

        with allure.step(f"Disable dark mode on {dut_name} {dut_alias}"):
            DeployDpuHelper.disable_dark_mode(topology_obj, cli_obj, dpu_index_list, dut_alias)

        with allure.step('Copying image to switch dut'):
            dpu_image_url = MarsConstants.HTTP_SERVER_NBU_NFS + base_version_dpu
            dest_file = "/tmp/" + base_version_dpu.split('/')[-1]
            retry_call(lambda: topology_obj.players[dut_alias]['engine'].run_cmd(
                f"sudo curl -C - --retry 5 {dpu_image_url} --output {dest_file}", validate=True, retry_run=True),
                tries=5, delay=2)

        with allure.step('Install BFB image on all DPUs'):
            # Disconnect ssh connection, prevent "Socket is closed" in case when pre step took more than 15 min
            output = topology_obj.players[dut_alias]['engine'].run_cmd(
                f"sudo sonic-bfb-installer.sh -r {rshim_value} -b {dest_file} -v")
            failures = []
            for index in dpu_index_list:
                pattern = f"{index}.*Installation Successful"
                if not re.search(pattern, output):
                    failures.append(index)
            if failures:
                assert False, f"Failed to install bfb image on DPU: {failures}."

            if installed_dpus:
                save_specified_installed_dpus(installed_dpus, dut_alias, dut_name)

    @staticmethod
    def disable_dark_mode(topology_obj, cli_obj, dpu_index_list, dut_alias):
        if topology_obj.players[dut_alias]['engine'].run_cmd("ls /etc/mlnx/ | grep dpu.conf", validate=False) == 'dpu.conf':
            if "DARK_MODE=true" in topology_obj.players[dut_alias]['engine'].run_cmd("cat /etc/mlnx/dpu.conf"):
                with allure.step('Disable dark mode and power cycle'):
                    topology_obj.players[dut_alias]['engine'].run_cmd(
                        'sudo sh -c "sed -i \'s/DARK_MODE=true/DARK_MODE=false/\' /etc/mlnx/dpu.conf"')
                    time.sleep(60)
                    cli_obj.remote_reboot(topology_obj)
                    cli_obj.verify_dockers_are_up()
                    dpu_ready = topology_obj.players[dut_alias]['engine'].run_cmd(
                        "dpuctl dpu-status | awk '{print $2}'")
                    assert "False" not in dpu_ready, "Not all DPUs are ready."
        else:
            with allure.step('Disable dark mode by config chassis modules startup DPU'):
                cli_obj.verify_dpus_down(dpu_index_list)
                cli_obj.startup_dpu(dpu_index_list)
                try:
                    cli_obj.verify_dpus_up(dpu_index_list)
                except AssertionError:
                    logger.warning("Failed to verify DPUs are up, checking if they can receive the new image")
                    cli_obj.verify_dpu_boot_progress(dpu_index_list, bad_states={0, 15})
                cli_obj.save_configuration()
