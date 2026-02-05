import os
import shutil

import allure
import pytest

from ngts.scripts.sonic_deploy.image_preparetion_methods import get_real_paths
from ngts.scripts.sonic_deploy.sonic_only_methods import SonicInstallationSteps, update_hosts_file
from ngts.scripts.sonic_deploy.deploy_helper_methods import DeployTopologyHelper
from ngts.cli_wrappers.sonic.sonic_general_clis import SonicGeneralCliDefault
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tools.test_utils.nvos_config_utils import set_base_configurations
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.scripts.sonic_deploy.sonic_only_methods import is_community
from ngts.helpers.run_process_on_host import wait_until_background_procs_done
from ngts.scripts.sonic_deploy.simx_community_helper import prepare_air_community_directory


@pytest.mark.disable_loganalyzer
@allure.title('Deploy and upgrade image - Air')
def test_deploy_and_upgrade_air(topology_obj, target_version, sonic_topo, deploy_only_target, setup_name, base_version,
                                platform_params, reboot_after_install, fw_pkg_path, recover_by_reboot, reboot, port_number,
                                additional_apps, workspace_path, chip_type, custom_config_db_air_path, destination_hwsku,
                                deploy_sequential):
    try:
        with allure.step('Collecting setup info'):
            setup_info = DeployTopologyHelper.get_info_from_topology(topology_obj, workspace_path)
            setup_info['setup_name'] = setup_name
            dut = setup_info['duts'][0]
        cli_obj = setup_info['duts'][0]['cli_obj']
        dut_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        update_hosts_file(dut_ip=dut['engine'].ip, dut_name=dut_name, sonic_topo=sonic_topo, setup_name=setup_name)
        if isinstance(cli_obj, SonicGeneralCliDefault) and is_community(sonic_topo):
            prepare_air_community_directory(setup_name=setup_name, topology=topology_obj, hwsku=destination_hwsku, platform_params=platform_params)
            threads_dict = {}
            sonic_cli = SonicGeneralCliDefault(engine=dut['engine'], cli_obj=cli_obj, dut_alias=dut['dut_alias'])
            with allure.step('Pre installation steps'):
                SonicInstallationSteps.pre_installation_steps(sonic_topo, neighbor_type='ceos',
                                                              base_version=base_version, target_version=None, setup_info=setup_info, port_number=port_number, is_simx=True,
                                                              threads_dict=threads_dict, destination_hwsku=destination_hwsku, is_performance=False, is_air=True,
                                                              deploy_sequential=deploy_sequential)
            sonic_cli.deploy_fanout(topology_obj, destination_hwsku, platform_params, setup_info, dut['dut_alias'], threads_dict)
            wait_until_background_procs_done(threads_dict)

        with allure.step('Post installation steps'):
            if isinstance(cli_obj, NvueGeneralCli):
                DutUtilsTool.wait_for_nvos_to_become_functional(dut['engine'])
                set_base_configurations(dut_engine=dut['engine'], apply=True)
            elif isinstance(cli_obj, SonicGeneralCliDefault):
                apply_base_config = True if sonic_topo == 'ptf-any' else False
                SonicInstallationSteps.post_installation_steps(topology_obj=topology_obj, sonic_topo=sonic_topo,
                                                               recover_by_reboot=recover_by_reboot, setup_name=setup_name,
                                                               platform_params=platform_params, apply_base_config=apply_base_config,
                                                               target_version=target_version, is_shutdown_bgp=True,
                                                               reboot_after_install=reboot_after_install,
                                                               deploy_only_target=deploy_only_target,
                                                               fw_pkg_path=fw_pkg_path, reboot=reboot,
                                                               additional_apps=additional_apps, setup_info=setup_info,
                                                               dut_alias=dut['dut_alias'], is_performance=False,
                                                               chip_type=chip_type, deploy_dpu=False, is_air=True,
                                                               custom_config_db_air_path=custom_config_db_air_path)

            # Remove .pytest_cache folder after deploy - otherwise  - cached info from old image will be used in skip tests
            cache_full_path = os.path.join(os.path.dirname(__file__), '../../.pytest_cache')
            shutil.rmtree(cache_full_path, ignore_errors=True)
    except Exception as err:
        raise AssertionError(err)
