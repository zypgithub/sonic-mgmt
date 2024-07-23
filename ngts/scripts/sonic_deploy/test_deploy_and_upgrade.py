import concurrent.futures
import copy
import logging
import os
import shutil
import time

import allure
import pytest

from ngts.cli_wrappers.nvue.cumulus.cumulus_general_cli import CumulusGeneralCli
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli
from ngts.constants.constants import PlayersAliases, MarsConstants
from ngts.helpers.run_process_on_host import wait_until_background_procs_done
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
from ngts.nvos_tools.Devices.IbDevice import BlackMambaSwitch, CrocodileSwitch
from ngts.scripts.sonic_deploy.cumulus_only_methods import CumulusInstallationSteps
from ngts.scripts.sonic_deploy.image_preparetion_methods import get_real_paths, prepare_images
from ngts.scripts.sonic_deploy.nvos_only_methods import NvosInstallationSteps
from ngts.scripts.sonic_deploy.sonic_only_methods import SonicInstallationSteps
from ngts.tools.infra import get_platform_info

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
@allure.title('Deploy and upgrade image')
def test_deploy_and_upgrade(topology_obj, is_simx, is_performance, base_version, base_version_dpu, target_version, serve_files,
                            sonic_topo, neighbor_type, deploy_only_target, port_number, setup_name, platform_params, deploy_dpu,
                            deploy_type, apply_base_config, reboot_after_install, is_shutdown_bgp,
                            fw_pkg_path, recover_by_reboot, reboot, additional_apps, workspace_path, wjh_deb_url,
                            verify_secure_boot, chip_type):
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
        logger.info("Deploy SONiC testing topology and upgrade switch")

        setup_info = get_info_from_topology(topology_obj, workspace_path)
        setup_info['setup_name'] = setup_name

        base_version, target_version = get_real_paths(base_version, target_version)
        image_urls = prepare_images_to_install(base_version, target_version, serve_files)
        base_version_url = get_base_version_url(deploy_only_target, image_urls)
        target_version_url = '' if not target_version else get_target_version_url(image_urls)

        if sonic_topo == 'ptf-any':
            apply_base_config = True

        if wjh_deb_url and additional_apps:
            raise Exception('Arguments "wjh_deb_url" and "additional_apps" can not be used together')
        if not additional_apps:
            additional_apps = wjh_deb_url

        switch_or_standalone_dpu_duts = []
        smart_switch_dpu_duts = []
        for dut in setup_info['duts']:
            if 'dut-dpu' not in dut['dut_alias']:
                switch_or_standalone_dpu_duts.append(dut)
            elif base_version_dpu:
                smart_switch_dpu_duts.append(dut)
        # Remove the smart switch DPUs from the setup_info for we do not want to run the pre and post steps on them
        setup_info['duts'] = switch_or_standalone_dpu_duts

        pre_install_threads = {}
        pre_installation_steps(
            sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number, is_simx,
            pre_install_threads)
        install_threads = []
        install_dpu_threads = []
        executor = concurrent.futures.ThreadPoolExecutor()
        player_dut = topology_obj.players['dut']
        for dut in switch_or_standalone_dpu_duts:
            if not is_dut_supports_image(base_version_url, dut['dut_name']):
                continue
            with allure.step('Install image on dut: {}'.format(dut['dut_name'])):
                # Disconnect ssh connection, prevent "Socket is closed" in case when pre step took more than 15 min
                topology_obj.players[dut['dut_alias']]['engine'].disconnect()
                platform_params_copy = copy.deepcopy(platform_params)
                install_threads.append((dut['dut_name'],
                                        executor.submit(deploy_image, topology_obj=topology_obj, setup_name=setup_name,
                                                        image_url=base_version_url, platform_params=platform_params_copy,
                                                        deploy_type=deploy_type, apply_base_config=apply_base_config,
                                                        reboot_after_install=reboot_after_install,
                                                        is_shutdown_bgp=is_shutdown_bgp, fw_pkg_path=fw_pkg_path,
                                                        cli_type=dut['cli_obj'], target_image_url=target_version_url)))
        wait_until_deploy_background_process(install_threads, timeout=1500)

        if "bobcat" in setup_name and base_version_dpu:
            with allure.step('Copying image to switch dut'):
                dpu_image_url = MarsConstants.HTTP_SERVER_NBU_NFS + base_version_dpu
                dest_file = "/tmp/" + base_version_dpu.split('/')[-1]
                topology_obj.players['dut']['engine'].run_cmd(
                    f"sudo curl {dpu_image_url} --output {dest_file}")
            base_version_dpu = dest_file

        for dut in smart_switch_dpu_duts:
            with allure.step('Install image on DPU: {}'.format(dut['dut_name'])):
                # Disconnect ssh connection, prevent "Socket is closed" in case when pre step took more than 15 min
                topology_obj.players[dut['dut_alias']]['engine'].disconnect()
                # Deepcopy with the dut cli object sometimes fails due to
                # "TypeError: cannot pickle '_thread.lock' object",
                # don't copy it since it will be replaced eventually
                topology_obj.players['dut'] = None
                topology_obj_dpu = copy.deepcopy(topology_obj)
                topology_obj.players['dut'] = player_dut
                platform_params_dpu = copy.copy(platform_params)
                topology_obj_dpu.players['dut'] = topology_obj_dpu.players[dut['dut_alias']]
                if "bobcat" in setup_name:
                    topology_obj_dpu.players['hyper'] = topology_obj.players['dut']
                topology_obj_dpu.players['hyper']['engine'].disconnect()
                platform_params_dpu['hwsku'] = get_platform_info(topology_obj_dpu)['hwsku']
                logger.info(f"Starting to install image on DPU {dut['dut_name']}")
                deploy_image(topology_obj=topology_obj_dpu, setup_name=setup_name,
                             image_url=base_version_dpu, platform_params=platform_params,
                             deploy_type='bfb', apply_base_config=False,
                             reboot_after_install=reboot_after_install,
                             is_shutdown_bgp=is_shutdown_bgp, fw_pkg_path='',
                             cli_type=dut['cli_obj'], target_image_url='')

        logger.info("Wait until pre-installation background process done")
        try:
            wait_until_background_procs_done(pre_install_threads)
        except AssertionError:
            # Give it another try if the background processes in the pre-installation steps fail
            pre_installation_steps(sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number,
                                   is_simx, pre_install_threads)
            wait_until_background_procs_done(pre_install_threads)
        logger.info("Pre-installation background processes are done")

        post_installation_steps(topology_obj=topology_obj, sonic_topo=sonic_topo,
                                recover_by_reboot=recover_by_reboot, setup_name=setup_name,
                                platform_params=platform_params, apply_base_config=apply_base_config,
                                target_version=target_version, is_shutdown_bgp=True,
                                reboot_after_install=reboot_after_install, deploy_only_target=deploy_only_target,
                                fw_pkg_path=fw_pkg_path, reboot=reboot, additional_apps=additional_apps,
                                setup_info=setup_info, workspace_path=workspace_path, is_performance=is_performance,
                                chip_type=chip_type, base_version=base_version, deploy_dpu=deploy_dpu,
                                verify_secure_boot=verify_secure_boot)

        # Remove .pytest_cache folder after deploy - otherwise  - cached info from old image will be used in skip tests
        cache_full_path = os.path.join(os.path.dirname(__file__), '../../.pytest_cache')
        shutil.rmtree(cache_full_path, ignore_errors=True)

    except Exception as err:
        raise AssertionError(err)


def pre_installation_steps(sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number, is_simx,
                           threads_dict):
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
    """
    cli_type = setup_info['duts'][0]['cli_obj']
    if isinstance(cli_type, CumulusGeneralCli):
        CumulusInstallationSteps.pre_installation_steps(setup_info, base_version, target_version)
    elif isinstance(cli_type, NvueGeneralCli):
        NvosInstallationSteps.pre_installation_steps(setup_info, base_version, target_version)
    else:
        SonicInstallationSteps.pre_installation_steps(sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number,
                                                      is_simx, threads_dict)


def post_installation_steps(topology_obj, sonic_topo, recover_by_reboot, deploy_dpu,
                            setup_name, platform_params, apply_base_config, target_version,
                            is_shutdown_bgp, reboot_after_install, deploy_only_target, fw_pkg_path, reboot,
                            additional_apps, setup_info, workspace_path, is_performance, chip_type, base_version='',
                            verify_secure_boot=True):
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
    """
    dut_cli_obj = setup_info['duts'][0]['cli_obj']
    if isinstance(dut_cli_obj, CumulusGeneralCli):
        CumulusInstallationSteps.post_installation_steps()
    elif isinstance(dut_cli_obj, NvueGeneralCli):
        NvosInstallationSteps.post_installation_steps(topology_obj, workspace_path, setup_info, base_version,
                                                      target_version, verify_secure_boot)
    else:
        SonicInstallationSteps.post_installation_steps(topology_obj, sonic_topo, recover_by_reboot, setup_name,
                                                       platform_params, apply_base_config, target_version,
                                                       is_shutdown_bgp, reboot_after_install, deploy_only_target,
                                                       fw_pkg_path, reboot, additional_apps, setup_info, is_performance,
                                                       chip_type, deploy_dpu)


def get_cli_obj(topology_obj, cli_type, switch_type, engine, host, dut_alias):
    if cli_type == NvosConst.NVUE_CLI:
        device_name = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific'].\
            get('switch_type', '')
        device = DeviceFactory.create_device(device_name)
        if switch_type == NvosConst.CUMULUS_SWITCH:
            cli_obj = CumulusGeneralCli(engine, device)
        else:
            cli_obj = NvueGeneralCli(engine, device)
    else:
        cli_obj = SonicCli(topology_obj, dut_alias=dut_alias).general

    return cli_obj


def is_dut_supports_image(base_version_url, dut_name):
    image_supports = True
    # device mtvr-moose-01 is production and supports only prod versions of ONIE and SONiC
    if dut_name == 'mtvr-moose-01' and "prod" not in base_version_url:
        image_supports = False
    # when executed deploy of production image, skip the flow on not production devices
    if dut_name != 'mtvr-moose-01' and 'prod' in base_version_url:
        image_supports = False
    return image_supports


def wait_until_deploy_background_process(install_threads, timeout=1200):
    for dut_name, task in install_threads:
        with allure.step(f'Wait until {dut_name} installation background process done'):
            try:
                task.result(timeout=timeout)
                logger.info(f"Image is successfully installed on {dut_name}")
            except TimeoutError:
                logger.error(f"The installation on {dut_name} failed to complete in {timeout}s.")


def get_info_from_topology(topology_obj, workspace_path, include_smartswitch_dpu=True):
    """
    Creates a class which contains setup info
    :param topology_obj: topology object
    :param workspace_path: workspace_path argument
    :param include_smartswitch_dpu: controls whether collect the entries of SmartSwitch DPUs
    :return: SetupInfo object
    """
    ansible_path = os.path.join(workspace_path, "sonic-mgmt/ansible/")
    setup_info = {'ansible_path': ansible_path, 'duts': []}

    with allure.step("Create setup_info object"):
        for host in topology_obj.players:
            if host in PlayersAliases.duts_list:
                dut_name = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Common']['Name']
                dut_alias = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Common']['Description']
                cli_type = topology_obj[0][host]['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE']
                switch_type = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific'].get('TYPE', '')
                dut_ip = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific'].get('ip address', '')
                engine = topology_obj.players[host]['engine']
                cli_obj = get_cli_obj(topology_obj, cli_type, switch_type, engine, host, dut_alias)
                dut_info = {'dut_name': dut_name, 'cli_type': cli_type, 'engine': engine, 'cli_obj': cli_obj,
                            'dut_alias': dut_alias, 'switch_type': switch_type, 'dut_ip': dut_ip}
                if 'dut-dpu' in dut_alias and not include_smartswitch_dpu:
                    continue
                setup_info['duts'].append(dut_info)
            elif host == 'hypervisor':
                hypervisor_name = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Common']['Name']
                hypervisor_ip = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific']['ip']
                hypervisor_info = {'hypervisor_name': hypervisor_name, 'hypervisor_ip': hypervisor_ip}
                setup_info['hypervisor'] = hypervisor_info

    return setup_info


def prepare_images_to_install(base_version, target_version, serve_files):
    """
    Prepare images to be installed
    :param base_version: base version argument
    :param target_version: target version argument
    :param serve_files: serve files
    :return:
    '"""
    with allure.step('Prepare images and get base version url'):
        return prepare_images(base_version, target_version, serve_files)


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
                 apply_base_config, reboot_after_install, is_shutdown_bgp, fw_pkg_path, cli_type, target_image_url=''):
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
    :return: raise assertion error in case of script failure
    """

    if isinstance(cli_type, NvueGeneralCli):
        base_image_url = image_url
        if type(cli_type.device) not in [BlackMambaSwitch, CrocodileSwitch]:
            # if base version specified, installing version with prev default password - adjust engine
            if base_image_url and not isinstance(cli_type, CumulusGeneralCli):
                cli_type.engine.password = cli_type.device.get_default_password_by_version(base_image_url)
        NvosInstallationSteps.deploy_image(cli_type, topology_obj, setup_name, platform_params, base_image_url, deploy_type,
                                           apply_base_config, reboot_after_install, fw_pkg_path, target_image_url)
    else:
        SonicInstallationSteps.deploy_image(cli_type, topology_obj, setup_name, platform_params, image_url,
                                            deploy_type, apply_base_config, reboot_after_install, is_shutdown_bgp,
                                            fw_pkg_path)
    time.sleep(30)
