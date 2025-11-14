#!/usr/bin/env python
import allure
import logging

from retry.api import retry_call
from ngts.scripts.sonic_deploy.deploy_helper_methods import DeployTopologyHelper
from ngts.scripts.sonic_deploy.community_only_methods import config_y_cable_simulator, add_host_for_y_cable_simulator
from ngts.scripts.sonic_deploy.sonic_only_methods import SonicInstallationSteps, is_community


logger = logging.getLogger()


@allure.title('Deploy sonic image')
def test_deploy_sonic_image(topology_obj, setup_name, sonic_topo, platform_params, base_version, deploy_type,
                            apply_base_config, reboot_after_install, is_shutdown_bgp, fw_pkg_path, workspace_path,
                            post_installation_validation, chip_type, is_performance, is_air):
    """
    This script will deploy sonic image on the dut.
    :param topology_obj: topology object fixture
    :param setup_name: setup_name fixture
    :param platform_params: platform_params fixture
    :param base_version: path to sonic version to be installed
    :param deploy_type: deploy_type fixture
    :param apply_base_config: apply_base_config fixture
    :param reboot_after_install: reboot_after_install fixture
    :param is_shutdown_bgp: shutdown bgp flag, True or False
    :param fw_pkg_path: fw_pkg_path fixture
    :param is_performance: is_performance fixture, True in case when setup is performance
    :param is_air: is_air fixture
    :return: raise assertion error in case of script failure
    """
    setup_info = DeployTopologyHelper.get_info_from_topology(topology_obj, workspace_path)
    for dut in setup_info['duts']:
        try:
            # when bgp is up, dut can not access the external IP such as nbu-mtr-nfs.nvidia.com. So shutdown bgp
            if is_shutdown_bgp:
                dut['engine'].run_cmd('sudo config bgp shutdown all', validate=True)
                logger.info("Wait all bgp sessions are down")
                retry_call(check_bgp_is_shutdown,
                           fargs=[dut['engine']],
                           tries=6,
                           delay=10,
                           logger=logger)
            dut['cli_obj'].deploy_image(topology_obj, base_version, apply_base_config=apply_base_config,
                                        setup_name=setup_name, platform_params=platform_params,
                                        deploy_type=deploy_type, reboot_after_install=reboot_after_install,
                                        fw_pkg_path=fw_pkg_path, configure_dns=True)
        except Exception as err:
            raise AssertionError(err)
        finally:
            if is_shutdown_bgp:
                dut['engine'].run_cmd('sudo config bgp startup all', validate=True)
    if sonic_topo and is_community(sonic_topo) and post_installation_validation:
        for dut in setup_info['duts']:
            cli = dut['cli_obj']
            dut_alias = dut['dut_alias']
            cli.cli_obj.general.deploy_image_post_installtion(topology_obj, apply_base_config=False,
                                                              setup_name=setup_name,
                                                              platform_params=platform_params,
                                                              configure_dns=True,
                                                              setup_info=setup_info,
                                                              dut_alias=dut_alias)


def check_bgp_is_shutdown(dut_engine):
    assert dut_engine.run_cmd("show ip route bgp") == "" and dut_engine.run_cmd("show ipv6 route bgp") == "", \
        "Not all bgp sessions are down"
