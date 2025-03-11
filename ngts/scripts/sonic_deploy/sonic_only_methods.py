import logging
import os
import requests
import json
import allure
import sys
from pathlib import Path

from ngts.helpers import json_file_helper
from ngts.scripts.sonic_deploy.image_preparetion_methods import is_url, get_sonic_branch
from ngts.constants.constants import MarsConstants, SonicDeployConstants, SonicConst
from ngts.scripts.sonic_deploy.community_only_methods import get_generate_minigraph_cmd, deploy_minigpraph, \
    reboot_validation, execute_script, is_bf_topo, is_dualtor_topo, is_dualtor_aa_topo, generate_minigraph, \
    config_y_cable_simulator, add_host_for_y_cable_simulator
from retry.api import retry_call
from ngts.helpers.run_process_on_host import run_background_process_on_host
from ngts.common.util import get_installed_dpu_info

logger = logging.getLogger()


class SonicInstallationSteps:

    @staticmethod
    def pre_installation_steps(
            sonic_topo, neighbor_type, base_version, target_version, setup_info, port_number, is_simx, threads_dict,
            destination_hwsku):
        """
        Pre-installation steps for SONIC
        :param sonic_topo: the topo for SONiC testing, for example: t0, t1, t1-lag, ptf32
        :param neighbor_type: neighbor_type fixture
        :param base_version: base version
        :param target_version: target version if provided
        :param setup_info: dictionary with setup info
        :param port_number: number of DUT ports
        :param is_simx: fixture, True if setup is SIMX, else False
        :param threads_dict: dict, contain threads which will run in background
        :param destination_hwsku: the destination hwsku value
        """
        setup_name = setup_info['setup_name']
        dut_name = setup_info['duts'][0]['dut_name']
        SonicInstallationSteps.verify_sonic_branch_supported(setup_info, base_version)
        if is_community(sonic_topo):
            ansible_path = setup_info['ansible_path']
            SonicInstallationSteps.override_hwsku_files(setup_info, destination_hwsku)
            # Get ptf docker tag
            ptf_tag = SonicInstallationSteps.get_ptf_tag_sonic(base_version, target_version)
            dut_names = []
            for dut in setup_info['duts']:
                dut_names.append(dut['dut_name'])
            with allure.step('Remove topologies'):
                cached_hwsku = get_cached_hwsku(dut_name)
                if cached_hwsku and cached_hwsku != destination_hwsku:
                    if "dual-tor" in setup_name:
                        SonicInstallationSteps.remove_topologies(ansible_path=ansible_path, dut_names=None,
                                                                 setup_name=setup_name, sonic_topo=sonic_topo)
                    logger.info(f"Copy the setup related file for the hwsku {cached_hwsku}")
                    SonicInstallationSteps.override_hwsku_files(setup_info, cached_hwsku)
                    SonicInstallationSteps.remove_topologies(ansible_path=ansible_path, dut_names=dut_names,
                                                             setup_name=None, sonic_topo=sonic_topo)
                else:
                    SonicInstallationSteps.remove_topologies(ansible_path=ansible_path,
                                                             dut_names=dut_names,
                                                             setup_name=setup_name,
                                                             sonic_topo=sonic_topo)
                if cached_hwsku and cached_hwsku != destination_hwsku:
                    SonicInstallationSteps.override_hwsku_files(setup_info, destination_hwsku)
            SonicInstallationSteps.start_community_background_threads(threads_dict, setup_name,
                                                                      dut_name, sonic_topo, neighbor_type,
                                                                      ptf_tag, port_number,
                                                                      ansible_path, setup_info, destination_hwsku)
            if is_dualtor_topo(sonic_topo) and "sonic-dual-tor-leopard" not in setup_name:
                generate_minigraph(ansible_path, setup_info, setup_info['setup_name'], sonic_topo, port_number)
        else:
            SonicInstallationSteps.start_canonical_background_threads(threads_dict, setup_name, dut_name, is_simx)

    @staticmethod
    def start_community_background_threads(threads_dict, setup_name, dut_name, sonic_topo, neighbor_type, ptf_tag,
                                           port_number, ansible_path, setup_info, hwsku):
        """
        Start background threads for community setup
        """
        if neighbor_type == 'vsonic':
            logger.info("Starting vsonic VMs")
            SonicInstallationSteps.start_vsonic_vms(ansible_path=ansible_path,
                                                    setup_name=setup_name,
                                                    dut_names=[dut_name],
                                                    sonic_topo=sonic_topo)
        add_topo_cmd = SonicInstallationSteps.get_add_topology_cmd(setup_name, dut_name, sonic_topo, neighbor_type,
                                                                   ptf_tag, hwsku)
        run_background_process_on_host(threads_dict, 'add_topology', add_topo_cmd, timeout=3600, exec_path=ansible_path)
        if (not is_bf_topo(sonic_topo) and not is_dualtor_topo(sonic_topo) and "mtvr-hippo-03" != dut_name and
                "mtvr-hippo-02" != dut_name and 'bobcat' not in dut_name and "r-moose-01" != dut_name and
                "mtvr-moose-04" != dut_name and "r-leopard-01" != dut_name and "r-leopard-58" != dut_name and
                'r-tigon-04' != dut_name and "mtvr-moose-13" != dut_name and "mtvr-moose-14" != dut_name and
                "mtvr-bison-02" != dut_name and "mtvr-gaur-03" != dut_name):
            gen_mg_cmd = get_generate_minigraph_cmd(setup_info, dut_name, sonic_topo, port_number)
            run_background_process_on_host(threads_dict, 'generate_minigraph', gen_mg_cmd, timeout=300,
                                           exec_path=ansible_path)

    @staticmethod
    def copy_csv_inventory_lab(setup_name, destination_hwsku):
        base_path = os.path.dirname(os.path.realpath(__file__))
        common_csv_file_path = os.path.join(base_path, "../../../ansible/files/")
        setup_csv_file_path = os.path.join(common_csv_file_path, f"hwsku_vars/{setup_name}/*.csv")
        setup_hwsku_csv_file_path = os.path.join(common_csv_file_path,
                                                 f"hwsku_vars/{setup_name}/{destination_hwsku}/*.csv")

        common_inventory_lab_path = os.path.join(base_path, "../../../ansible/")
        setup_hwsku_inventory_path = os.path.join(common_csv_file_path,
                                                  f"hwsku_vars/{setup_name}/{destination_hwsku}/inventory")
        setup_hwsku_lab_path = os.path.join(common_csv_file_path,
                                            f"hwsku_vars/{setup_name}/{destination_hwsku}/lab")

        logger.info(f"Common csv files path: {common_csv_file_path}")
        logger.info(f"Copy {setup_name} - {destination_hwsku} related csv files to override the common csv files")
        os.system(f"cp -f {setup_hwsku_csv_file_path} {common_csv_file_path}")
        os.system(f"cp -f {setup_csv_file_path} {common_csv_file_path}")

        logger.info(f"Common inventory and lab files path: {common_inventory_lab_path}")
        logger.info(f"Copy {setup_name} - {destination_hwsku} related inventory and lab files to override the "
                    f"common inventory and lab files")
        os.system(f"cp -f {setup_hwsku_inventory_path} {common_inventory_lab_path}")
        os.system(f"cp -f {setup_hwsku_lab_path} {common_inventory_lab_path}")

    @staticmethod
    def override_hwsku_files(setup_info, destination_hwsku):
        """
        Copy the csv/inventory/lab files under folder setup_name and folder hwsku to override the common files
        """
        setup_name = setup_info['setup_name']
        if 'dual-tor' in setup_name:
            SonicInstallationSteps.copy_csv_inventory_lab(setup_info['duts'][0]['dut_name'] + '_setup',
                                                          destination_hwsku)
        else:
            SonicInstallationSteps.copy_csv_inventory_lab(setup_name, destination_hwsku)

    @staticmethod
    def start_canonical_background_threads(threads_dict, setup_name, dut_name, is_simx):
        """
        Start background threads for canonical setup
        """
        python_bin_path = sys.executable

        if not is_simx:
            run_containers_cmd = SonicInstallationSteps.generate_run_containers_command(python_bin_path, setup_name)
            run_background_process_on_host(threads_dict, 'containers_bringup', run_containers_cmd, timeout=600)

        update_repo_cmd = SonicInstallationSteps.generate_update_sonic_mgmt_cmd(python_bin_path, dut_name)
        run_background_process_on_host(threads_dict, 'update_sonic_mgmt', update_repo_cmd)

    @staticmethod
    def generate_run_containers_command(python_bin_path, setup_name):
        """
        Generate command which can run containers_bringup.py script
        :param python_bin_path: path to python interpreter
        :param setup_name: name of setup
        :return: string, command which will contain containers_bringup.py script with arguments
        """
        devts_path = SonicInstallationSteps.get_devts_path()
        cmd = f'{python_bin_path} {devts_path}/scripts/docker/containers_bringup.py ' \
            f'--setup_name {setup_name} --sonic_setup'
        return cmd

    @staticmethod
    def generate_update_sonic_mgmt_cmd(python_bin_path, dut_name):
        """
        Generate command which can run update_sonic_mgmt.py script
        :param python_bin_path: path to python interpreter
        :param dut_name: name of DUT
        :return: string, command which will contain update_sonic_mgmt.py script with arguments
        """
        sonic_mgmt_path = os.path.abspath(__file__).split('/ngts/')[0]
        cmd = f'{python_bin_path} {sonic_mgmt_path}/sonic-tool/sonic_ngts/scripts/update_sonic_mgmt.py ' \
            f'--dut={dut_name} --mgmt_repo={sonic_mgmt_path}'
        return cmd

    @staticmethod
    def get_devts_path():
        """
        Get path to DevTS repository
        :return: string, path to DevTS repository
        """
        devts_path = None
        for path in sys.path:
            if path.endswith('devts'):
                devts_path = path
                break
        return devts_path

    @staticmethod
    def get_ptf_tag_sonic(base_version, target_version):
        """
        Getting ptf docker tag
        :param base_version: base version
        :param target_version: target version if provided
        :return: ptf_tag
        """
        with allure.step('Getting ptf docker tag'):
            if target_version:
                ptf_tag = SonicInstallationSteps.get_ptf_docker_tag(target_version)
            else:
                ptf_tag = SonicInstallationSteps.get_ptf_docker_tag(base_version)
        return ptf_tag

    @staticmethod
    def get_ptf_docker_tag(image_path):
        """
        Get PTF docker tag from SONiC image path
        :param image_path:
            example: /auto/sw_system_release/sonic/master.234-27a6641fb_Internal/Mellanox/sonic-mellanox.bin
        :return: ptf docker tag, example: '42007'
        """
        ptf_tag = '558858'
        try:
            if is_url(image_path):
                file_path_index = 3
                image_path = '/' + '/'.join(image_path.split('/')[file_path_index:])
            branch = get_sonic_branch(image_path)
            logger.info('SONiC branch is: {}'.format(branch))
            ptf_tag = MarsConstants.BRANCH_PTF_MAPPING.get(branch, '669063')
        except Exception as err:
            logger.error('Can not get SONiC branch and PTF tag from path: {}, using "latest". Error: {}'.format(
                image_path, err))

        return ptf_tag

    @staticmethod
    def stop_vsonic_vms(ansible_path, setup_name, dut_names, sonic_topo):
        """
        The method removes the topologies to get the clear environment.
        """
        for dut_name in dut_names:
            cmd = SonicInstallationSteps.get_stop_start_sonic_vms_cmd(setup_name, dut_name, sonic_topo, "stop",
                                                                      "sonic-vs.img")
            try:
                execute_script(cmd, ansible_path, validate=False, timeout=1200)
            except Exception as err:
                logger.warning(f'Failed to stop for dut {dut_name}. Got error: {err}')

    @staticmethod
    def start_vsonic_vms(ansible_path, setup_name, dut_names, sonic_topo):
        """
        The method removes the topologies to get the clear environment.
        """
        for dut_name in dut_names:
            cmd = SonicInstallationSteps.get_stop_start_sonic_vms_cmd(setup_name, dut_name, sonic_topo, "start",
                                                                      "sonic-vs.img")
            try:
                execute_script(cmd, ansible_path, validate=False, timeout=2400)
            except Exception as err:
                logger.warning(f'Failed to start SONiC VMs for dut {dut_name}. Got error: {err}')

    @staticmethod
    def remove_topologies(ansible_path, dut_names, setup_name, sonic_topo):
        """
        The method removes the topologies to get the clear environment.
        """
        def _remove_topologies(setup, topo_list):
            logger.info(
                f"Remove topologies: {topo_list}. This may increase a chance to deploy a new one successful")
            cached_vm_type = get_cached_vm_type(setup)

            for topo in topo_list:
                if cached_vm_type == 'vsonic':
                    logger.info("Stopping vsonic VMs")
                    SonicInstallationSteps.stop_vsonic_vms(ansible_path=ansible_path,
                                                           setup_name=setup_name,
                                                           dut_names=dut_names,
                                                           sonic_topo=topo)
                if is_dualtor_aa_topo(topo):
                    cmd = "./testbed-cli.sh -t testbed.yaml -k {NEIGHBOR_TYPE} remove-topo {SETUP}-{TOPO} vault".format(
                        SETUP=setup, TOPO=topo, NEIGHBOR_TYPE=cached_vm_type)
                else:
                    cmd = "./testbed-cli.sh -k {NEIGHBOR_TYPE} remove-topo {SETUP}-{TOPO} vault".format(
                        SETUP=setup, TOPO=topo, NEIGHBOR_TYPE=cached_vm_type)
                logger.info("Remove topo {}".format(topo))
                logger.info("Running CMD: {}".format(cmd))
                try:
                    execute_script(cmd, ansible_path, validate=True, timeout=600)
                except Exception as err:
                    logger.warning(f'Failed to remove topology. Got error: {err}')

        logger.info("Removing topologies to get the clear environment")
        with allure.step("Remove Topologies (community step)"):
            if setup_name and is_dualtor_topo(sonic_topo):
                topologies = SonicInstallationSteps.get_topologies_to_remove(sonic_topo, setup_name)
                _remove_topologies(setup_name, topologies)
            if dut_names:
                for dut_name in dut_names:
                    topologies = SonicInstallationSteps.get_topologies_to_remove(sonic_topo, dut_name)
                    _remove_topologies(dut_name, topologies)

    @staticmethod
    def get_topologies_to_remove(required_topology, dut_name):
        if is_bf_topo(required_topology):
            topos_to_remove = [required_topology]
        else:
            cached_topo = get_cached_topology(dut_name)
            if cached_topo:
                logger.info(f"Found cached topology: {cached_topo}, removing only this one")
                topos_to_remove = [cached_topo]
            else:
                if 'dual-tor' in dut_name:
                    topos_to_remove = MarsConstants.TOPO_ARRAY_DUALTOR
                else:
                    topos_to_remove = MarsConstants.TOPO_ARRAY
        return topos_to_remove

    @staticmethod
    def get_add_topology_cmd(setup_name, dut_name, sonic_topo, neighbor_type, ptf_tag, hwsku=None):
        testbed_file = ''
        if is_dualtor_topo(sonic_topo):
            dut_name = setup_name
            if is_dualtor_aa_topo(sonic_topo):
                testbed_file = '-t testbed.yaml'
        cmd = "./testbed-cli.sh {TESTBED_FILE} -k {NEIGHBOR_TYPE} -h {HWSKU} add-topo {SWITCH}-{TOPO} vault -e " \
              "ptf_imagetag={PTF_TAG} -vvvvv".format(TESTBED_FILE=testbed_file, SWITCH=dut_name,
                                                     TOPO=sonic_topo, PTF_TAG=ptf_tag, NEIGHBOR_TYPE=neighbor_type,
                                                     HWSKU=hwsku)
        return cmd

    @staticmethod
    def get_stop_start_sonic_vms_cmd(setup_name, dut_name, sonic_topo, action, sonic_file_name):
        testbed_file = ''
        if is_dualtor_topo(sonic_topo):
            dut_name = setup_name
            if is_dualtor_aa_topo(sonic_topo):
                testbed_file = '-t testbed.yaml'
        cmd = "./testbed-cli.sh {TESTBED_FILE} -k vsonic {ACTION}-topo-vms {SWITCH}-{TOPO} vault -e " \
              "{SONIC_FILE_NAME} -vvvvv".format(TESTBED_FILE=testbed_file, SWITCH=dut_name, TOPO=sonic_topo,
                                                ACTION=action, SONIC_FILE_NAME=sonic_file_name)
        return cmd

    @staticmethod
    def post_install_check(ansible_path, dut_name, sonic_topo):
        """
        Method which doing post install checks: check ports status, check dockers status, etc.
        """
        with allure.step("Post install check"):
            post_install_validation = "ansible-playbook -i inventory --limit {SWITCH} " \
                                      "post_upgrade_check.yml -e " \
                                      "topo={TOPO} -b -vvv".format(SWITCH=dut_name, TOPO=sonic_topo)
            logger.info("Performing post-install validation by running: {}".format(post_install_validation))
            return execute_script(cmd=post_install_validation, exec_path=ansible_path)

    @staticmethod
    def is_additional_apps_argument_is_deb_package(additional_apps_argument):
        is_deb_package = False
        path = additional_apps_argument
        try:
            if os.path.islink(additional_apps_argument):
                path = os.readlink(additional_apps_argument)
            if path.endswith('.deb'):
                is_deb_package = True
        except OSError:
            pass
        return is_deb_package

    @staticmethod
    def install_supported_app_extensions(ansible_path, setup_name, dut_name, app_extension_dict_path, sonic_topo):
        app_extension_path_str = ''
        if app_extension_dict_path:
            app_extension_path_str = '--app_extension_dict_path={}'.format(app_extension_dict_path)
        cmd = "{ngts_pytest} --setup_name={setup_name} --dut_name={dut_name} --rootdir={sonic_mgmt_dir}/ngts" \
              " -c {sonic_mgmt_dir}/ngts/pytest.ini --log-level=INFO" \
              " --clean-alluredir --alluredir=/tmp/allure-results --sonic-topo={sonic_topo}" \
              " --disable_loganalyzer {app_extension_path_str} " \
              " {sonic_mgmt_dir}/ngts/scripts/install_app_extension/install_app_extensions.py". \
            format(ngts_pytest=MarsConstants.NGTS_PATH_PYTEST, sonic_mgmt_dir=MarsConstants.SONIC_MGMT_DIR,
                   setup_name=setup_name, dut_name=dut_name, sonic_topo=sonic_topo,
                   app_extension_path_str=app_extension_path_str)
        logger.info("Running CMD: {}".format(cmd))
        execute_script(cmd, ansible_path)

    @staticmethod
    def check_bgp_is_shutdown(dut_engine):
        assert dut_engine.run_cmd("show ip route bgp") == "" and dut_engine.run_cmd("show ipv6 route bgp") == "", \
            "Not all bgp sessions are down"

    @staticmethod
    def is_additional_apps_argument_is_app_ext_dict(additional_apps_argument):
        is_app_ext_dict = False
        try:
            requests.get('{}/{}'.format(MarsConstants.HTTP_SERVER_NBU_NFS, additional_apps_argument)).json()
            is_app_ext_dict = True
        except json.decoder.JSONDecodeError:
            pass
        return is_app_ext_dict

    @staticmethod
    def copy_json_to_dut(json_content, filename, dest_path, dut_engine):
        with open(f'/tmp/{filename}', 'w') as f:
            json.dump(json_content, f, indent=4)
        os.chmod(f'/tmp/{filename}', 0o777)
        dut_engine.copy_file(source_file=f'/tmp/{filename}', dest_file=filename, file_system='/tmp/',
                             overwrite_file=True, verify_file=False)
        dut_engine.run_cmd(f'sudo cp /tmp/{filename} {dest_path}')

    @staticmethod
    def remove_redundant_service_port(dut_platform_path, hwsku, dut_engine, cli_obj):
        port_to_remove = 'Ethernet520'
        port_config_path = f'{dut_platform_path}/{hwsku}/port_config.ini'
        dut_engine.run_cmd(f'grep -v "{port_to_remove}" {port_config_path} > tmp_port_config')
        dut_engine.run_cmd(f'sudo mv tmp_port_config {port_config_path}')

        platform_json_path = f'{dut_platform_path}/platform.json'
        platform_json_obj = json_file_helper.get_platform_json(dut_engine, cli_obj)
        del platform_json_obj['interfaces'][port_to_remove]
        SonicInstallationSteps.copy_json_to_dut(platform_json_obj, 'platform.json', platform_json_path, dut_engine)

    @staticmethod
    def post_installation_steps(topology_obj, sonic_topo, recover_by_reboot, setup_name, platform_params,
                                apply_base_config, target_version, is_shutdown_bgp, reboot_after_install,
                                deploy_only_target, fw_pkg_path, reboot, additional_apps, setup_info, dut_alias,
                                is_performance, chip_type, deploy_dpu=False, xml_rpc=True):
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
        :param dut_alias: alias of dut
        :param is_performance: True in case when setup is performance
        :param chip_type: the type of chip
        :param deploy_dpu: deploy dpu flag
        """
        ansible_path = setup_info['ansible_path']
        cli = SonicInstallationSteps.get_dut_cli(setup_info)
        for dut in setup_info['duts']:
            cli = dut['cli_obj']
            dut_alias = dut['dut_alias']
            cli.cli_obj.general.update_platform_params(platform_params, setup_name)
            apply_base_config = False if is_performance else apply_base_config
            cli.cli_obj.general.deploy_image_post_installtion(topology_obj, apply_base_config=apply_base_config,
                                                              setup_name=setup_name,
                                                              platform_params=platform_params,
                                                              reboot_after_install=reboot_after_install,
                                                              configure_dns=True, disable_ztp=True,
                                                              setup_info=setup_info,
                                                              dut_alias=dut_alias)
        dut_name = setup_info['duts'][0]['dut_name']
        dut_platform_path = f'/usr/share/sonic/device/{platform_params["platform"]}'
        sonic_mgmt_hwsku_path = '/usr/share/sonic/device/x86_64-kvm_x86_64-r0'
        sonic_user = os.getenv("SONIC_SWITCH_USER")
        sonic_password = os.getenv("SONIC_SWITCH_PASSWORD")
        dut_engine = topology_obj.players['dut']['engine']
        logger.info(f'Current hwsku in the platform_params is: {platform_params["platform"]}')
        hwskus = []
        need_gen_mingraph = False
        if "mtvr-hippo-03" in setup_name or "mtvr-hippo-02" in setup_name:
            hwskus = [platform_params["hwsku"]]
            need_gen_mingraph = True
        if ("r-moose-01" in setup_name or "mtvr-moose-04" in setup_name or "mtvr-moose-13" in setup_name or
                "mtvr-moose-14" in setup_name):
            hwskus = ['Mellanox-SN5600-V256', 'Mellanox-SN5600-C256S1', 'Mellanox-SN5600-C224O8']
            need_gen_mingraph = True
        if "bobcat" in setup_name:
            hwskus = ['ACS-SN4280', 'Mellanox-SN4280-O28']
            need_gen_mingraph = True
        if "r-tigon-04" in setup_name:
            hwskus = ['Mellanox-SN4600C-D24C52']
            need_gen_mingraph = True
        if "r-leopard-01" in setup_name or "r-leopard-58" in setup_name:
            hwskus = ['Mellanox-SN4700-O32', 'Mellanox-SN4700-V64']
            need_gen_mingraph = True
        if "sonic-dual-tor-leopard" in setup_name:
            hwskus = ['Mellanox-SN4700-V64']
            need_gen_mingraph = True
        if "mtvr-bison-02" in setup_name or "mtvr-gaur-03" in setup_name:
            hwskus = ['Mellanox-SN5610N-C256S2', 'Mellanox-SN5610N-C224O8']
            need_gen_mingraph = True

        for hwsku in hwskus:
            if os.path.exists(f'{sonic_mgmt_hwsku_path}/{hwsku}'):
                logger.warning(f"The hwsku {hwsku} already exist in the sonic mgmt docker, no need to copy")
            elif "No such file or directory" in dut_engine.run_cmd(f"ls -l {dut_platform_path}/{hwsku}"):
                logger.warning(f"The hwsku {hwsku} not exist in the DUT, no need to copy")
            else:
                execute_script(f'sshpass -p "{sonic_password}" scp -o "StrictHostKeyChecking no"'
                               f' -r {sonic_user}@{dut_name}:{dut_platform_path}/{hwsku} '
                               f'{sonic_mgmt_hwsku_path}', ansible_path)

                logger.info(f"Copied the hwsku {hwsku} to sonic-mgmt")

        if "hippo" in setup_name:
            SonicInstallationSteps.remove_redundant_service_port(dut_platform_path, platform_params['hwsku'],
                                                                 dut_engine, cli.cli_obj)
            dut_engine.run_cmd(
                f"sudo sonic-cfggen --preset t1 -p -H "
                f"-k {platform_params['hwsku']} > {SonicConst.SONIC_CONFIG_FOLDER}{SonicConst.CONFIG_DB_JSON}")

        if ("r-moose-01" in setup_name or "mtvr-moose-14" in setup_name):
            v256 = "Mellanox-SN5600-V256"
            if os.path.exists(f'{sonic_mgmt_hwsku_path}/{v256}/port_config.ini'):
                execute_script(f'sed -i "s/200000/100000/g" {sonic_mgmt_hwsku_path}/{v256}/port_config.ini',
                               ansible_path)

            c256s1 = "Mellanox-SN5600-C256S1"
            if os.path.exists(f'{sonic_mgmt_hwsku_path}/{c256s1}/port_config.ini'):
                execute_script(f'sed -i "s/100000/50000/g" {sonic_mgmt_hwsku_path}/{c256s1}/port_config.ini',
                               ansible_path)

            c224o8 = "Mellanox-SN5600-C224O8"
            if os.path.exists(f'{sonic_mgmt_hwsku_path}/{c224o8}/port_config.ini'):
                execute_script(f'sed -i "s/100000/50000/g" {sonic_mgmt_hwsku_path}/{c224o8}/port_config.ini',
                               ansible_path)
                execute_script(f'sed -i "s/400000/100000/g" {sonic_mgmt_hwsku_path}/{c224o8}/port_config.ini',
                               ansible_path)
        if need_gen_mingraph:
            if "sonic-dual-tor-leopard" in setup_name:
                if not setup_info.get('setup_name', None):
                    setup_info['setup_name'] = setup_name
                generate_minigraph(ansible_path, setup_info, setup_name, sonic_topo, None)
            else:
                generate_minigraph(ansible_path, setup_info, dut_name, sonic_topo, None)

        cli.enable_async_route_feature(platform_params['platform'], platform_params['hwsku'])

        if not is_community(sonic_topo):
            # Enable Port Init Profile for Canonical setups
            logger.info("Prepare sai.xml files for Port Init feature testing")
            cli.update_sai_xml_file(platform_params['platform'], platform_params['hwsku'], global_flag=True,
                                    local_flags=False)

        # Community only steps
        if is_community(sonic_topo):
            if is_dualtor_topo(sonic_topo) and 'dualtor-aa' not in sonic_topo:
                config_y_cable_simulator(ansible_path=ansible_path, setup_name=setup_name, sonic_topo=sonic_topo)
                for dut in setup_info['duts']:
                    add_host_for_y_cable_simulator(dut, setup_info)
            for dut in setup_info['duts']:
                general_cli_obj = dut['cli_obj']
                deploy_minigpraph(ansible_path=ansible_path, dut_name=dut['dut_name'], sonic_topo=sonic_topo,
                                  recover_by_reboot=recover_by_reboot, topology_obj=topology_obj,
                                  cli_obj=general_cli_obj)
            with allure.step('Apply DNS servers configuration'):
                for dut in setup_info['duts']:
                    general_cli_obj = dut['cli_obj']
                    topology_obj.players[dut['dut_alias']]['engine'].disconnect()
                    general_cli_obj.cli_obj.ip.apply_dns_servers_into_resolv_conf(
                        is_air_setup=platform_params.setup_name.startswith('air'))
                    general_cli_obj.save_configuration()
            if deploy_dpu:
                with allure.step('Update the dash api in sonic-mgmt'):
                    retry_call(fetch_dash_api_package, tries=3, delay=10, logger=logger)
                    os.system("dpkg --install ./libdashapi_1.0.0_amd64.deb")

                if dut_engine.run_cmd("ls /etc/mlnx/ | grep dpu.conf", validate=False) != 'dpu.conf':
                    with allure.step('Startup dpu and save config'):
                        _, dpu_index_list, _ = get_installed_dpu_info(topology_obj)
                        general_cli_obj.startup_dpu(dpu_index_list)
                        general_cli_obj.save_configuration()

                with allure.step('Apply DPU IP assignment configuration'):
                    config_file_name = "dpu_basic_config.json"
                    dut_engine = topology_obj.players['dut']['engine']
                    config_path = \
                        os.path.join(MarsConstants.SONIC_MGMT_DIR,
                                     f"tests/smart_switch/{config_file_name}")
                    dut_engine.copy_file(source_file=config_path,
                                         dest_file=config_file_name, file_system='/tmp/',
                                         overwrite_file=True, verify_file=False)
                    dut_engine.run_cmd(
                        'sudo cp /etc/sonic/config_db.json /etc/sonic/config_db.backup.json')
                    dut_engine.run_cmd(
                        f'sudo sonic-cfggen -j /tmp/{config_file_name} --write-to-db', validate=True)
                    general_cli_obj.save_configuration()
                with allure.step('Apply NAT config to smartSwitch'):
                    enable_nat_from_dut_mgmt_to_dpu_mgmt_intf(dut_engine)

            for dut in setup_info['duts']:
                SonicInstallationSteps.post_install_check_sonic(sonic_topo=sonic_topo, dut_name=dut['dut_name'],
                                                                ansible_path=ansible_path)

        for dut in setup_info['duts']:
            SonicInstallationSteps.upgrade_switch(topology_obj=topology_obj, dut_name=dut['dut_name'],
                                                  setup_name=setup_name, platform_params=platform_params,
                                                  sonic_topo=sonic_topo, deploy_type='sonic',
                                                  apply_base_config=apply_base_config, target_version=target_version,
                                                  is_shutdown_bgp=is_shutdown_bgp, ansible_path=ansible_path,
                                                  reboot_after_install=reboot_after_install,
                                                  deploy_only_target=deploy_only_target, fw_pkg_path=fw_pkg_path,
                                                  cli=dut['cli_obj'], chip_type=chip_type)

        for dut in setup_info['duts']:
            SonicInstallationSteps.reboot_validation_sonic(dut_name=dut['dut_name'], sonic_topo=sonic_topo,
                                                           reboot=reboot, ansible_path=ansible_path)

        for dut in setup_info['duts']:
            if additional_apps:
                SonicInstallationSteps.install_app_extension_sonic(dut_name=dut['dut_name'], setup_name=setup_name,
                                                                   additional_apps=additional_apps,
                                                                   ansible_path=ansible_path,
                                                                   sonic_topo=sonic_topo)

        # This check is for swb respin r-anaconda-15, only the SONiC image with hw-management version
        # higher than 7.0020.3100 runs properly on this dut, stop the regression if the image is not suitable
        for dut in setup_info['duts']:
            if dut['dut_name'] == 'r-anaconda-15':
                SonicInstallationSteps.verify_hw_management_version(engine=topology_obj.players['dut']['engine'])

        for dut in setup_info['duts']:
            # Disconnect ssh connection, prevent "Socket is closed" in case when previous steps did reboot
            topology_obj.players[dut['dut_alias']]['engine'].disconnect()

        if not is_community(sonic_topo) and not is_performance:
            if xml_rpc:
                # deploy the xmlrpc, the traffic may loss right after the xml rpc server is started
                topology_obj.players['ha']['engine'].start_xml_rcp_server()
                topology_obj.players['hb']['engine'].start_xml_rcp_server()

            if deploy_dpu:
                with allure.step('Update the dash api in sonic-mgmt'):
                    retry_call(fetch_dash_api_package, tries=3, delay=10, logger=logger)
                    os.system("dpkg --install ./libdashapi_1.0.0_amd64.deb")
                with allure.step('Apply NAT config to smartSwitch'):
                    enable_nat_from_dut_mgmt_to_dpu_mgmt_intf(dut_engine)

            # Only check port status at canonical setup, there is an ansible counterpart for community setup
            for dut in setup_info['duts']:
                ports_list = topology_obj.players_all_ports[dut['dut_alias']]
                dut['cli_obj'].cli_obj.interface.check_link_state(ports_list)

    @staticmethod
    def get_dut_cli(setup_info):
        cli = None
        for dut in setup_info['duts']:
            if dut['dut_alias'] == 'dut':
                cli = dut['cli_obj']
                break
        return cli

    @staticmethod
    def deploy_image(cli, topology_obj, setup_name, platform_params, image_url, deploy_type,
                     apply_base_config, reboot_after_install,
                     is_shutdown_bgp, fw_pkg_path,
                     destination_hwsku=None,
                     setup_info=None, dut_alias=None, fanout_deploy_threads=None,
                     docker_list=None, fanout_target_version=None):
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
        :param cli : SONIC cli object
        :param destination_hwsku: the destination hwsku value
        :param setup_info: setup information
        :param dut_alias: dut alias, such as 'dut-b'
        :param fanout_deploy_threads: dict contains fanout deploy background threads
        :param docker_list : List of docker name to validate
        :param fanout_target_version :Path to target version of fanout.
        :return: raise assertion error in case of script failure
        """
        dut_engine = None
        try:
            # TODO: Temp workaround for overcoming ipv6 ssh issue
            os.system("sudo /bin/sh -c 'echo \"precedence ::ffff:0:0/96 100\" >> /etc/gai.conf'")
            # when bgp is up, dut can not access the external IP such as nbu-mtr-nfs.nvidia.com. So shutdown bgp
            # for sonic only (is_shutdown_bgp is False for NVOS)
            if is_shutdown_bgp:
                with allure.step('Shutdown bgp'):
                    dut_engine = cli.engine
                    dut_engine.run_cmd('sudo config bgp shutdown all', validate=True)
                    logger.info("Wait all bgp sessions are down")
                    retry_call(SonicInstallationSteps.check_bgp_is_shutdown,
                               fargs=[dut_engine],
                               tries=6,
                               delay=10,
                               logger=logger)

            with allure.step('Deploy sonic image on the dut'):
                disable_ztp = False
                if deploy_type == 'onie':
                    disable_ztp = True
                cli.deploy_image(topology_obj=topology_obj, image_path=image_url, apply_base_config=apply_base_config,
                                 setup_name=setup_name, platform_params=platform_params,
                                 deploy_type=deploy_type,
                                 reboot_after_install=reboot_after_install, fw_pkg_path=fw_pkg_path,
                                 disable_ztp=disable_ztp, configure_dns=True, destination_hwsku=destination_hwsku,
                                 setup_info=setup_info, dut_alias=dut_alias,
                                 deploy_fanout_threads=fanout_deploy_threads,
                                 docker_list=docker_list,
                                 fanout_target_version=fanout_target_version)

        except Exception as err:
            raise AssertionError(err)
        finally:
            # for sonic only (is_shutdown_bgp is False for NVOS)
            if is_shutdown_bgp and dut_engine:
                with allure.step('Startup bgp'):
                    dut_engine.run_cmd('sudo config bgp startup all', validate=True)

    @staticmethod
    def post_install_check_sonic(sonic_topo, dut_name, ansible_path):
        """
        Method which doing post install checks: check ports status, check dockers status, etc.
        :param sonic_topo: the topo for SONiC testing, for example: t0, t1, t1-lag, ptf32
        :param dut_name: dut name
        :param ansible_path: path to ansible directory
        """
        SonicInstallationSteps.post_install_check(ansible_path=ansible_path, dut_name=dut_name,
                                                  sonic_topo=sonic_topo)

    @staticmethod
    def upgrade_switch(topology_obj, dut_name, setup_name, platform_params, sonic_topo, deploy_type,
                       apply_base_config, target_version, is_shutdown_bgp, ansible_path,
                       reboot_after_install, deploy_only_target, fw_pkg_path, cli, chip_type, set_timezone='Israel'):
        """
        Upgrade switch to the target version
        :param topology_obj: topology object
        :param dut_name: dut name
        :param setup_name: setup name
        :param platform_params: platform params
        :param sonic_topo: the topo for SONiC testing, for example: t0, t1, t1-lag, ptf32
        :param deploy_type: deploy type - 'onie', 'sonic'
        :param apply_base_config: bool value
        :param target_version: path to target version
        :param is_shutdown_bgp: bool value
        :param ansible_path: path to ansible directory
        :param reboot_after_install: bool value
        :param deploy_only_target: bool value
        :param fw_pkg_path: path to FW pkg
        :param cli: cli - SonicCli / NvueCli
        :param chip_type: chip_type - chip generation installed at platform
        :param set_timezone: set timezone
        """
        if target_version and not deploy_only_target:
            with allure.step("Upgrade switch to the target version"):
                logger.info("Target version is defined, upgrade switch again to the target version.")
                SonicInstallationSteps.deploy_image(topology_obj=topology_obj, setup_name=setup_name,
                                                    image_url=target_version, platform_params=platform_params,
                                                    deploy_type=deploy_type,
                                                    apply_base_config=apply_base_config,
                                                    reboot_after_install=reboot_after_install,
                                                    is_shutdown_bgp=is_shutdown_bgp, fw_pkg_path=fw_pkg_path, cli=cli)

                if not is_community(sonic_topo):
                    cli.cli_obj.im.enable_im(topology_obj=topology_obj, platform_params=platform_params,
                                             chip_type=chip_type, enable_im=True)

            with allure.step("Set dut NTP timezone to {} time.".format(set_timezone)):
                cli.engine.disconnect()
                cli.engine.run_cmd('sudo timedatectl set-timezone {}'.format(set_timezone), validate=True)

            # There could be new running config generated by the new image
            with allure.step("Save new running config to config_db.json"):
                cli.cli_obj.qos.reload_qos()
                cli.cli_obj.general.verify_dockers_are_up()
                cli.cli_obj.general.enable_info_logging_on_docker(docker_name='swss')
                cli.cli_obj.general.save_configuration()

            with allure.step("Post installation check for community setup"):
                if is_community(sonic_topo):
                    SonicInstallationSteps.post_install_check(ansible_path=ansible_path, dut_name=dut_name,
                                                              sonic_topo=sonic_topo)
            cli.engine.run_cmd('sudo sonic-installer cleanup -y')

    @staticmethod
    def reboot_validation_sonic(dut_name, sonic_topo, reboot, ansible_path):
        """
        Reboot validation
        :param dut_name: dut name
        :param sonic_topo: the topo for SONiC testing, for example: t0, t1, t1-lag, ptf32
        :param reboot: whether reboot the switch after deploy. Default: 'no'
        :param ansible_path: path to ansible directory
        """
        if reboot and reboot != "no":
            reboot_validation(ansible_path=ansible_path, reboot=reboot, dut_name=dut_name, sonic_topo=sonic_topo)

    @staticmethod
    def install_app_extension_sonic(dut_name, setup_name, additional_apps, ansible_path, sonic_topo):
        """
        Install supported app extension
        :param dut_name: dut name
        :param setup_name: setup name
        :param additional_apps: additional apps
        :param ansible_path: path to ansible directory
        """
        app_extension_dict_path = additional_apps
        if app_extension_dict_path:
            with allure.step("Install supported app extension"):
                SonicInstallationSteps.install_supported_app_extensions(ansible_path=ansible_path,
                                                                        setup_name=setup_name,
                                                                        app_extension_dict_path=app_extension_dict_path,
                                                                        dut_name=dut_name,
                                                                        sonic_topo=sonic_topo)

    @staticmethod
    def verify_hw_management_version(engine):
        lowest_valid_version = '7.0020.3100'
        with allure.step('Getting the hw-management version from dut'):
            output = engine.run_cmd('dpkg -l | grep hw-management')

        with allure.step('Comparing the hw-management version with the lowest valid version'):
            version = output.split()[2]
            version = version.split('mlnx.')[-1]
            assert version >= lowest_valid_version, \
                'Current hw-management version {} is lower than the required version {}.'.format(
                    version, lowest_valid_version)

    @staticmethod
    def verify_sonic_branch_supported(setup_info, image_path):
        for dut in setup_info['duts']:
            if dut['dut_name'] in SonicDeployConstants.UN_SUPPORT_BRANCH_MAP:
                not_support_branch = SonicDeployConstants.UN_SUPPORT_BRANCH_MAP[dut['dut_name']]
                logger.info(f'The not supported branch for {dut["dut_name"]} are {not_support_branch}')
                with allure.step('Getting the image version'):
                    branch = get_sonic_branch(image_path)
                    logger.info('SONiC branch is: {}'.format(branch))
                assert branch not in not_support_branch, f"The setup dose not support to install image of {branch}"


def is_community(sonic_topo):
    if sonic_topo:
        return sonic_topo != 'ptf-any'


def get_cached_topology(dut_name):
    cached_topo = None
    cached_topo_path = f"{MarsConstants.SONIC_MARS_BASE_PATH}/cached_deployed_topologies/"
    setup_cached_topo_file = Path(f"{cached_topo_path}/{dut_name}")
    if setup_cached_topo_file.is_file():
        cached_topo_vm = setup_cached_topo_file.read_text().strip()
        if ',' in cached_topo_vm:
            cached_topo = cached_topo_vm.split(',')[0].strip()
        else:
            cached_topo = cached_topo_vm
        if cached_topo not in MarsConstants.TOPO_ARRAY:
            logger.info(f"There is a garbage in the cache file, {cached_topo} is not in {MarsConstants.TOPO_ARRAY}"
                        " removing all topologies")
            cached_topo = None
    return cached_topo


def get_cached_vm_type(dut_name):
    cached_vm_type = 'ceos'
    cached_topo_vm_type_path = f"{MarsConstants.SONIC_MARS_BASE_PATH}/cached_deployed_topologies/"
    setup_cached_topo_file = Path(f"{cached_topo_vm_type_path}/{dut_name}")
    if setup_cached_topo_file.is_file():
        topo_vm_type = setup_cached_topo_file.read_text().strip()
        if ',' in topo_vm_type:
            cached_vm_type = topo_vm_type.split(',')[1].strip()
    return cached_vm_type


def get_cached_hwsku(dut_name):
    cached_hwsku = None
    cached_topo_vm_type_path = f"{MarsConstants.SONIC_MARS_BASE_PATH}/cached_deployed_topologies/"
    setup_cached_topo_file = Path(f"{cached_topo_vm_type_path}/{dut_name}")
    if setup_cached_topo_file.is_file():
        topo_vm_type = setup_cached_topo_file.read_text().strip()
        if ',' in topo_vm_type:
            cached_vars = topo_vm_type.split(',')
            if len(cached_vars) >= 3:
                cached_hwsku = cached_vars[2].strip()
    return cached_hwsku


def enable_nat_from_dut_mgmt_to_dpu_mgmt_intf(engine):
    enable_nat_cmds = [
        "sudo su",
        "sudo sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/g' /etc/sysctl.conf",
        "sudo echo net.ipv4.conf.eth0.forwarding=1 >> /etc/sysctl.conf",
        "sudo sysctl -p",
        "sudo iptables -t nat -A POSTROUTING -s 169.254.200.0/24 -o eth0 -j MASQUERADE",
        "sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 5021 -j DNAT --to-destination 169.254.200.1:22",
        "sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 5022 -j DNAT --to-destination 169.254.200.2:22",
        "sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 5023 -j DNAT --to-destination 169.254.200.3:22",
        "sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 5024 -j DNAT --to-destination 169.254.200.4:22",
        "sudo iptables -t nat -L",
        "sudo iptables-save > /etc/iptables/rules.v4",
        "exit"
    ]
    engine.run_cmd_set(enable_nat_cmds)


def fetch_dash_api_package():
    rc = os.system("wget 'https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=master&"
                   "definitionId=1055&artifactName=sonic-buildimage.amd64.ubuntu20_04&"
                   "target=libdashapi_1.0.0_amd64.deb' -O libdashapi_1.0.0_amd64.deb")
    assert rc == 0, "Failed to fetch the dash api package"
