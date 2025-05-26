import re

import concurrent.futures
import copy
import logging
import os
import shutil
import time
import json
import yaml
import sys

import allure
import pytest

from ngts.cli_wrappers.nvue.cumulus.cumulus_general_cli import CumulusGeneralCli
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.dvs.dvs_general_clis import DvsGeneralCli
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli
from ngts.constants.constants import PlayersAliases, SonicDeployConstants, MarsConstants, SerialLoggerConst, CliType
from ngts.cli_wrappers.sonic.sonic_general_clis import SonicGeneralCliDefault
from ngts.constants.constants import PlayersAliases, SerialLoggerConst, SSHConsts
from ngts.constants.performance_constants import PerfConsts, Cl_Consts
from ngts.helpers.general_helper import extract_host_details_from_topo_obj, get_cli_obj
from ngts.helpers.run_process_on_host import wait_until_background_procs_done
from ngts.nvos_tools.Devices.IbDevice import BlackMambaSwitch, CrocodileSwitch
from ngts.scripts.sonic_deploy.cumulus_only_methods import CumulusInstallationSteps
from ngts.scripts.sonic_deploy.dvs_only_methods import DvsInstallationSteps
from ngts.scripts.sonic_deploy.image_preparetion_methods import get_real_paths, prepare_images
from ngts.scripts.sonic_deploy.nvos_only_methods import NvosInstallationSteps
from ngts.scripts.sonic_deploy.sonic_only_methods import SonicInstallationSteps, is_community
from ngts.scripts.sonic_deploy.deploy_helper_methods import DeployMethods
from ngts.tools.infra import get_platform_info
from ngts.common.util import save_specified_installed_dpus, get_specified_installed_dpus_from_noga, \
    get_installed_dpu_info
from ngts.scripts.sonic_deploy.os_upgrade_flag import set_os_upgrade_flag

logger = logging.getLogger()

pytestmark = [
    pytest.mark.dependency(depends=["test_deploy_and_upgrade"])
]


@pytest.mark.dependency()
@pytest.mark.disable_loganalyzer
@allure.title('Deploy and upgrade image')
def test_deploy_and_upgrade(topology_obj, is_simx, is_performance, base_version, base_version_dpu, target_version,
                            serve_files, sonic_topo, neighbor_type, deploy_only_target, port_number, setup_name,
                            platform_params, deploy_dpu, deploy_type, apply_base_config, reboot_after_install,
                            is_shutdown_bgp, fw_pkg_path, recover_by_reboot, reboot, additional_apps, workspace_path,
                            wjh_deb_url, verify_secure_boot, chip_type, destination_hwsku, show_setup_versions,
                            serial_log_analyzers, fanout_target_version, request, is_air):
    """
        Deploy SONiC/NVOS testing topology and upgrade switch

        Flow:
            1. Get relevant setup info from topology object
            2. Prepare an image to be installed and get base version url
            3. Pre-installation steps
                If it's SONIC Community setup
                3.1. Get ptf docker tag
                3.2. Recover topology
            4. Deploy sonic/nvos image on the dut
            5. Post-installation steps
                For SONIC NOS only:
                5.1. Community only steps - Deploy fanout
                5.2. Post install check
                5.3. Upgrade switch to the target version
                5.4. Reboot validation
                5.5. Install WJH is requested
                5.6. Install supported app extension
                5.7. Port status validation

        :param topology_obj: topology object fixture.
        :param is_simx: is_simx fixture, True in case when setup is SIMX
        :param is_performance: is_performance fixture, True in case when setup is performance
        :param base_version: base_version fixture
        :param target_version: target_version fixture
        :param serve_files: serve_files fixture
        :param sonic_topo: sonic_topo fixture
        :param neighbor_type: neighbor_type fixture
        :param deploy_only_target: deploy_only_target fixture (True/False)
        :param port_number: port_number fixture
        :param setup_name: setup_name fixture
        :param platform_params: platform_params fixture
        :param deploy_type: deploy_type fixture
        :param apply_base_config: apply_base_config fixture
        :param reboot_after_install: reboot_after_install fixture
        :param is_shutdown_bgp: is_shutdown_bgp fixture
        :param fw_pkg_path: fw_pkg_path fixture
        :param recover_by_reboot: recover_by_reboot fixture
        :param reboot: reboot fixture
        :param additional_apps: additional_apps fixture
        :param workspace_path: workspace_path fixture
        :param wjh_deb_url: WJH deb URL
        :param verify_secure_boot: verify_secure_boot
        :param chip_type: chip_type fixture
        :raise AssertionError: in case of script failure.
    """
    try:
        with allure.step('preparations'):
            logger.info("Deploy SONiC testing topology and upgrade switch")

            setup_info = get_info_from_topology(topology_obj, workspace_path)
            setup_info['setup_name'] = setup_name
            destination_hwsku = get_hwsku(sonic_topo, destination_hwsku, setup_name)

            with allure.step('prepare versions paths/urls'):
                cli_type = setup_info["duts"][0]["cli_type"]
                base_version, target_version = get_real_paths(base_version, target_version, cli_type)
                image_urls = prepare_images_to_install(base_version, target_version, serve_files, cli_type)
                base_version_url = get_base_version_url(deploy_only_target, image_urls)
                target_version_url = '' if not target_version else get_target_version_url(image_urls)

            if sonic_topo == 'ptf-any':
                apply_base_config = True

            if wjh_deb_url and additional_apps:
                raise Exception('Arguments "wjh_deb_url" and "additional_apps" can not be used together')
            if not additional_apps:
                additional_apps = wjh_deb_url

        with allure.step('pre installation steps'):
            pre_install_threads = {}
            pre_installation_steps(
                sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number, is_simx,
                pre_install_threads, destination_hwsku, chip_type, request, is_performance)

        with allure.step('installation'):
            install_threads = []
            executor = concurrent.futures.ThreadPoolExecutor()
            use_GA_image = False
            for dut in setup_info['duts']:
                cli_obj = dut['cli_obj']
                related_base_version_url, related_target_version = get_related_image_to_switch(base_version_url,
                                                                                               target_version_url, dut, use_GA_image)
                if not cli_obj.is_dut_supports_image(related_base_version_url, dut['dut_name'], dut['cli_type']):
                    continue

                with allure.step('Install image on dut: {}'.format(dut['dut_name'])):
                    # Disconnect ssh connection, prevent "Socket is closed" in case when pre step took more than 15 min
                    topology_obj.players[dut['dut_alias']]['engine'].disconnect()
                    platform_params_copy = copy.deepcopy(platform_params)
                    install_threads.append((f"image install on {dut['dut_name']}",
                                            executor.submit(deploy_image, topology_obj=topology_obj,
                                                            setup_name=setup_name,
                                                            image_url=related_base_version_url,
                                                            platform_params=platform_params_copy,
                                                            deploy_type=deploy_type,
                                                            apply_base_config=apply_base_config,
                                                            reboot_after_install=reboot_after_install,
                                                            is_shutdown_bgp=is_shutdown_bgp, fw_pkg_path=fw_pkg_path,
                                                            cli_type=dut['cli_obj'],
                                                            target_image_url=related_target_version,
                                                            destination_hwsku=destination_hwsku, setup_info=setup_info,
                                                            dut_alias=dut['dut_alias'],
                                                            fanout_deploy_threads=pre_install_threads,
                                                            serial_log_analyzers=serial_log_analyzers,
                                                            dut_ip=dut['dut_ip'],
                                                            fanout_target_version=fanout_target_version)))
            DeployMethods.wait_until_deploy_background_process(install_threads, timeout=1500)

            if deploy_dpu:
                with allure.step(f'Start to install the bfb image on DPUs:{base_version_dpu}'):
                    bfb_install_dpu(topology_obj, setup_info, base_version_dpu)

        with allure.step('verify pre installation processes are done'):
            logger.info("Wait until pre-installation background process done")
            try:
                wait_until_background_procs_done(pre_install_threads)
            except AssertionError:
                # Give it another try if the background processes in the pre-installation steps fail
                pre_installation_steps(sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number,
                                       is_simx, pre_install_threads, destination_hwsku, chip_type, request)
                wait_until_background_procs_done(pre_install_threads)
            logger.info("Pre-installation background processes are done")

        with allure.step('post installation steps'):
            post_installation_steps(topology_obj=topology_obj, sonic_topo=sonic_topo,
                                    recover_by_reboot=recover_by_reboot, setup_name=setup_name,
                                    platform_params=platform_params, apply_base_config=apply_base_config,
                                    target_version=target_version, is_shutdown_bgp=True,
                                    reboot_after_install=reboot_after_install, deploy_only_target=deploy_only_target,
                                    fw_pkg_path=fw_pkg_path, reboot=reboot, additional_apps=additional_apps,
                                    setup_info=setup_info, dut_alias=dut['dut_alias'], workspace_path=workspace_path, is_performance=is_performance,
                                    chip_type=chip_type, base_version=base_version, deploy_dpu=deploy_dpu,
                                    verify_secure_boot=verify_secure_boot, serial_log_analyzers=serial_log_analyzers,
                                    request=request, is_air=is_air)

            # Remove .pytest_cache folder after deploy - otherwise  - cached info from old image will be used in skip tests
            cache_full_path = os.path.join(os.path.dirname(__file__), '../../.pytest_cache')
            shutil.rmtree(cache_full_path, ignore_errors=True)

        # set the OS upgrade flag
        if base_version and target_version and not deploy_only_target:
            if not set_os_upgrade_flag():
                logger.warning("Failed to set the OS upgrade flag")

    except Exception as err:
        raise AssertionError(err)

    finally:
        for analyzer in serial_log_analyzers.values():
            # if manufacture and upgrade stages are both present then we don't analyze the manufacture stage because
            # it runs an older OS version so we shouldn't debug it.
            if {SerialLoggerConst.MANUFACTURE_STAGE, SerialLoggerConst.UPGRADE_STAGE} <= set(analyzer.list_stages()):
                analyzer.ignore_stage(SerialLoggerConst.MANUFACTURE_STAGE)


def pre_installation_steps(sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number, is_simx,
                           threads_dict, destination_hwsku, chip_type, request, is_performance):
    """
    Pre-installation steps
    :param sonic_topo: sonic_topo fixture
    :param neighbor_type: neighbor_type fixture
    :param base_version: base_version fixture
    :param target_version: target version argument
    :param setup_info: dictionary with setup info
    :param port_number: number of DUT ports
    :param is_simx: is_simx fixture, True in case when setup is SIMX
    :param threads_dict: dict, contain threads which will run in background
    :param destination_hwsku: the destination hwsku value
    :param request: request plugin
    :param is_performance: is_performance fixture, True in case when setup is performance
    """
    cli_type = setup_info['duts'][0]['cli_obj']
    if isinstance(cli_type, CumulusGeneralCli):
        CumulusInstallationSteps.pre_installation_steps(setup_info, base_version, target_version)
    elif isinstance(cli_type, NvueGeneralCli):
        NvosInstallationSteps.pre_installation_steps(setup_info, base_version, target_version)
    elif isinstance(cli_type, DvsGeneralCli):
        DvsInstallationSteps.pre_installation_steps(setup_info)
    elif isinstance(cli_type, SonicGeneralCliDefault):
        SonicInstallationSteps.pre_installation_steps(sonic_topo, neighbor_type, base_version, target_version,
                                                      setup_info, port_number, is_simx,
                                                      threads_dict, destination_hwsku, is_performance)
    else:
        raise AssertionError(f"CLI type {cli_type} is not supported")

    replace_nos = request.config.getoption('--target_cli_type')
    if replace_nos:
        dut_list = setup_info['duts']
        DeployMethods.multi_nos_pre_installation_steps(dut_list, replace_nos, chip_type)


def post_installation_steps(topology_obj, sonic_topo, recover_by_reboot, deploy_dpu,
                            setup_name, platform_params, apply_base_config, target_version,
                            is_shutdown_bgp, reboot_after_install, deploy_only_target, fw_pkg_path, reboot,
                            additional_apps, setup_info, dut_alias, workspace_path, is_performance, chip_type,
                            serial_log_analyzers, request, is_air, base_version='', verify_secure_boot=True):
    """
    Post-installation steps
    :param topology_obj: topology object
    :param sonic_topo: sonic_topo fixture
    :param recover_by_reboot: bool value
    :param setup_name: setup_name from NOGA
    :param platform_params: platform_params
    :param apply_base_config: apply_base_config
    :param target_version: target_version
    :param is_shutdown_bgp: bool value
    :param reboot_after_install:  bool value
    :param deploy_only_target:  bool value
    :param fw_pkg_path: path to FW pkg
    :param reboot: reboot fixture
    :param additional_apps: additional_apps fixture
    :param setup_info: dictionary with setup info
    :param workspace_path: workspace_path fixture
    :param is_performance: is_performance fixture, True in case when setup is performance
    :param chip_type: chip_type fixture
    :param base_version: base_version fixture
    :param verify_secure_boot: verify_secure_boot flag
    :param serial_log_analyzers: serial_log_analyzers fixture
    :param request: request plugin
    :param is_air: is_air fixture
    """
    dut_cli_obj = setup_info['duts'][0]['cli_obj']
    if isinstance(dut_cli_obj, CumulusGeneralCli):
        CumulusInstallationSteps.post_installation_steps(setup_info, is_performance)
    elif isinstance(dut_cli_obj, NvueGeneralCli):
        NvosInstallationSteps.post_installation_steps(topology_obj, workspace_path, setup_info,
                                                      serial_log_analyzers[dut_cli_obj.engine.ip],
                                                      request.config.rootdir, base_version,
                                                      target_version, verify_secure_boot)

    elif isinstance(dut_cli_obj, DvsGeneralCli):
        DvsInstallationSteps.post_installation_steps(setup_info['duts'], target_version)

    elif isinstance(dut_cli_obj, SonicGeneralCliDefault):
        SonicInstallationSteps.post_installation_steps(topology_obj, sonic_topo, recover_by_reboot, setup_name,
                                                       platform_params, apply_base_config, target_version,
                                                       is_shutdown_bgp, reboot_after_install, deploy_only_target,
                                                       fw_pkg_path, reboot, additional_apps, setup_info, dut_alias,
                                                       is_performance, chip_type, deploy_dpu, is_air)
    else:
        raise AssertionError(f"CLI type {dut_cli_obj} is not supported")

    replace_nos = request.config.getoption('--target_cli_type')
    if replace_nos:
        DeployMethods.multi_nos_post_installation_steps(setup_info['duts'], replace_nos, is_performance)

    filter_testbed_yaml_file(setup_info)


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


def get_related_image_to_switch(base_version, target_version, dut, use_GA_image):
    # production devices support only prod versions of ONIE and SONiC
    if dut['dut_alias'] == "dut":
        base_version, target_version = get_image_for_dut(base_version, target_version, dut)
    elif dut['dut_alias'] in PerfConsts.TG_ALIAS_LIST:
        base_version, target_version = get_image_for_traffic_generators(base_version, target_version, dut, use_GA_image)
    return base_version, target_version


def get_image_for_dut(base_version, target_version, dut):
    if dut['cli_type'] == CliType.SONIC:
        if dut['dut_name'] == 'mtvr-hippo-05':
            base_version = base_version.replace('/dev/', '/prod/')
            if base_version.startswith('http'):
                base_version = '/auto/' + base_version.split('/auto/')[1]
            assert os.path.exists(base_version), (f"The required prod image path"
                                                  f" doesn't exists. {base_version}")
    elif dut['cli_type'] == CliType.NVUE:
        if target_version.startswith('http'):
            target_version = '/auto/' + target_version.split('/auto/')[1]
    return base_version, target_version


def get_image_for_traffic_generators(base_version, target_version, dut, use_GA_image):
    if dut['cli_type'] == CliType.SONIC:
        base_version = PerfConsts.SONIC_GA_IMAGE if use_GA_image else base_version
    elif dut['cli_type'] == CliType.NVUE:
        target_version = Cl_Consts.CL_GA_IMAGE if use_GA_image else target_version
    return base_version, target_version


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


def prepare_images_to_install(base_version, target_version, serve_files, cli_type):
    """
    Prepare images to be installed
    :param base_version: base version argument
    :param target_version: target version argument
    :param serve_files: serve files
    :param cli_type: cli_type of the system
    :return:
    '"""
    with allure.step('Prepare images and get base version url'):
        return prepare_images(base_version, target_version, serve_files, cli_type)


def get_base_version_url(deploy_only_target, image_urls):
    """
    Get base version url
    :return:
    """
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


def get_target_version_url(image_urls):
    """
    Get target version url
    :return:
    """
    with allure.step('Get target version url'):
        return get_base_version_url(True, image_urls)


def deploy_image(topology_obj, setup_name, platform_params, image_url, deploy_type,
                 apply_base_config, reboot_after_install, is_shutdown_bgp, fw_pkg_path, cli_type, target_image_url='',
                 destination_hwsku=None, setup_info=None, dut_alias=None, fanout_deploy_threads=None,
                 serial_log_analyzers=None, dut_ip='',
                 fanout_target_version=None):
    """
    This method will deploy sonic image on the dut.
    :param topology_obj: topology object
    :param setup_name: setup_name from NOGA
    :param platform_params: platform_params
    :param image_url: path to sonic version to be installed
    :param deploy_type: deploy_type
    :param apply_base_config: apply_base_config
    :param reboot_after_install: reboot_after_install
    :param is_shutdown_bgp: shutdown bgp flag, True or False
    :param fw_pkg_path: fw_pkg_path
    :param cli_type: NVUE or SONIC cli object
    :param destination_hwsku: the destination hwsku value
    :param setup_info: setup information
    :param dut_alias: dut alias, such as 'dut-b'
    :param fanout_deploy_threads: dict, contain threads which will run in background
    :param fanout_target_version: Path to fanout image. Only for SONiC.
    :return: raise assertion error in case of script failure
    """
    if isinstance(cli_type, NvueGeneralCli):
        base_image_url = image_url
        if type(cli_type.device) not in [BlackMambaSwitch, CrocodileSwitch]:
            # if base version specified, installing version with prev default password - adjust engine
            if base_image_url and not isinstance(cli_type, CumulusGeneralCli):
                cli_type.engine.password = cli_type.device.get_default_password_by_version(base_image_url)
        with serial_log_analyzers[dut_ip].stage(SerialLoggerConst.MANUFACTURE_STAGE):
            NvosInstallationSteps.deploy_image(cli_type, topology_obj, setup_name, platform_params, base_image_url,
                                               deploy_type, apply_base_config, reboot_after_install, fw_pkg_path,
                                               target_image_url, dut_alias)
    elif isinstance(cli_type, SonicGeneralCliDefault):
        SonicInstallationSteps.deploy_image(cli=cli_type,
                                            topology_obj=topology_obj,
                                            setup_name=setup_name,
                                            platform_params=platform_params,
                                            image_url=image_url,
                                            deploy_type=deploy_type,
                                            apply_base_config=apply_base_config,
                                            reboot_after_install=reboot_after_install,
                                            is_shutdown_bgp=is_shutdown_bgp,
                                            fw_pkg_path=fw_pkg_path,
                                            destination_hwsku=destination_hwsku,
                                            setup_info=setup_info,
                                            dut_alias=dut_alias,
                                            fanout_deploy_threads=fanout_deploy_threads,
                                            fanout_target_version=fanout_target_version)

    elif isinstance(cli_type, DvsGeneralCli):
        cli_type.deploy_image(PerfConsts.DVS_GA_IMAGE, topology_obj, dut_alias)
    time.sleep(30)


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


def bfb_install_dpu(topology_obj, setup_info, base_version_dpu):
    cli_obj = setup_info['duts'][0]['cli_obj']

    rshim_value, dpu_index_list, installed_dpus = get_installed_dpu_info(topology_obj)

    with allure.step("Disable dark mode"):
        disable_dark_mode(topology_obj, cli_obj, dpu_index_list)

    with allure.step('Copying image to switch dut'):
        dpu_image_url = MarsConstants.HTTP_SERVER_NBU_NFS + base_version_dpu
        dest_file = "/tmp/" + base_version_dpu.split('/')[-1]
        topology_obj.players['dut']['engine'].run_cmd(
            f"sudo curl {dpu_image_url} --output {dest_file}")

    with allure.step('Install BFB image on all DPUs'):
        # Disconnect ssh connection, prevent "Socket is closed" in case when pre step took more than 15 min
        output = topology_obj.players['dut']['engine'].run_cmd(
            f"sudo sonic-bfb-installer.sh -r {rshim_value} -b {dest_file} -v")
        failures = []
        for index in dpu_index_list:
            pattern = f"{index}.*Installation Successful"
            if not re.search(pattern, output):
                failures.append(index)
        if failures:
            assert False, f"Failed to install bfb image on DPU: {failures}."

        if installed_dpus:
            save_specified_installed_dpus(installed_dpus)


def disable_dark_mode(topology_obj, cli_obj, dpu_index_list):
    if topology_obj.players['dut']['engine'].run_cmd("ls /etc/mlnx/ | grep dpu.conf", validate=False) == 'dpu.conf':
        if "DARK_MODE=true" in topology_obj.players['dut']['engine'].run_cmd("cat /etc/mlnx/dpu.conf"):
            with allure.step('Disable dark mode and power cycle'):
                topology_obj.players['dut']['engine'].run_cmd(
                    'sudo sh -c "sed -i \'s/DARK_MODE=true/DARK_MODE=false/\' /etc/mlnx/dpu.conf"')
                time.sleep(60)
                cli_obj.remote_reboot(topology_obj)
                cli_obj.verify_dockers_are_up()
                dpu_ready = topology_obj.players['dut']['engine'].run_cmd(
                    "dpuctl dpu-status | awk '{print $2}'")
                assert "False" not in dpu_ready, "Not all DPUs are ready."
    else:
        with allure.step('Disable dark mode by config chassis modules startup DPU'):
            cli_obj.verify_dpus_down(dpu_index_list)
            cli_obj.startup_dpu(dpu_index_list)
            cli_obj.verify_dpus_up(dpu_index_list)
            cli_obj.save_configuration()


if 'base-version=/auto/sw_system_release/sonic' in ' '.join(sys.argv) and 'target_cli_type' not in ' '.join(sys.argv):
    from ngts.tests.nightly.sanity_checker.test_sanity_checker import platform_json_data, is_in_deploy_image_flow, \
        clear_file_inlcude_failed_sanity_check_case, test_device_asic_check, \
        test_cable_connection_for_canonical_check, test_more_then_2_fan_status_wrong_check, test_psu_status_check, \
        test_fan_status_check, test_cpld_version_check, test_core_dump_file_in_var_core_check
