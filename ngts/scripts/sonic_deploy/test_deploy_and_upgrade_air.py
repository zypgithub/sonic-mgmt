import os
import shutil

import allure
import pytest

from ngts.scripts.sonic_deploy.image_preparetion_methods import get_real_paths
from ngts.scripts.sonic_deploy.sonic_only_methods import SonicInstallationSteps
from ngts.scripts.sonic_deploy.test_deploy_and_upgrade import get_info_from_topology
from ngts.cli_wrappers.sonic.sonic_general_clis import SonicGeneralCliDefault
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tools.test_utils.nvos_config_utils import set_base_configurations
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool


@pytest.mark.disable_loganalyzer
@allure.title('Deploy and upgrade image - Air')
def test_deploy_and_upgrade_air(topology_obj, target_version, sonic_topo, deploy_only_target, setup_name,
                                platform_params, reboot_after_install, fw_pkg_path, recover_by_reboot, reboot,
                                additional_apps, workspace_path, chip_type, use_custom_config_db_air):
    try:
        with allure.step('Collecting setup info'):
            setup_info = get_info_from_topology(topology_obj, workspace_path)
            setup_info['setup_name'] = setup_name
            dut = setup_info['duts'][0]

            with allure.step('prepare versions paths/urls'):
                cli_type = setup_info["duts"][0]["cli_type"]
                _, target_version = get_real_paths(None, target_version, cli_type)

        with allure.step('Post installation steps'):
            cli_obj = setup_info['duts'][0]['cli_obj']
            if isinstance(cli_obj, NvueGeneralCli):
                DutUtilsTool.wait_for_nvos_to_become_functional(dut['engine'])
                set_base_configurations(dut_engine=dut['engine'], apply=True)
            elif isinstance(cli_obj, SonicGeneralCliDefault):
                SonicInstallationSteps.post_installation_steps(topology_obj=topology_obj, sonic_topo=sonic_topo,
                                                               recover_by_reboot=recover_by_reboot, setup_name=setup_name,
                                                               platform_params=platform_params, apply_base_config=True,
                                                               target_version=target_version, is_shutdown_bgp=True,
                                                               reboot_after_install=reboot_after_install,
                                                               deploy_only_target=deploy_only_target,
                                                               fw_pkg_path=fw_pkg_path, reboot=reboot,
                                                               additional_apps=additional_apps, setup_info=setup_info,
                                                               dut_alias=dut['dut_alias'], is_performance=False,
                                                               chip_type=chip_type, deploy_dpu=False, is_air=True,
                                                               use_custom_config_db_air=use_custom_config_db_air)

            # Remove .pytest_cache folder after deploy - otherwise  - cached info from old image will be used in skip tests
            cache_full_path = os.path.join(os.path.dirname(__file__), '../../.pytest_cache')
            shutil.rmtree(cache_full_path, ignore_errors=True)
    except Exception as err:
        raise AssertionError(err)
