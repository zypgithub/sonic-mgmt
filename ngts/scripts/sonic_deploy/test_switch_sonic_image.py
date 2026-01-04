#!/usr/bin/env python
import allure
import logging

from ngts.scripts.sonic_deploy.deploy_helper_methods import DeployTopologyHelper
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive


logger = logging.getLogger()


@allure.title('Switch sonic image')
def test_switch_sonic_image(topology_obj, setup_name, workspace_path):
    """
    This script will switch sonic image on the dut(s).
    Supports single DUT and dual-tor topologies.
    :param topology_obj: topology object fixture
    :param setup_name: setup_name fixture
    :param workspace_path: workspace_path fixture
    :return: raise assertion error in case of script failure
    """
    try:
        setup_info = DeployTopologyHelper.get_info_from_topology(topology_obj, workspace_path)
        current_image_dict = {}

        for dut in setup_info['duts']:
            dut_engine = dut['engine']
            cli_obj = dut['cli_obj']
            dut_name = dut.get('dut_name', dut.get('dut_alias', 'unknown'))

            logger.info(f"Switching image on DUT: {dut_name}")

            with allure.step(f"Switch image on {dut_name}"):
                target_image, _ = cli_obj.get_base_and_target_images()
                current_image_dict[dut_name] = target_image

                with allure.step(f"Set {target_image} as default image on {dut_name}"):
                    delimiter = cli_obj.get_installer_delimiter()
                    cli_obj.set_default_image(target_image, delimiter)

                with allure.step(f'Rebooting {dut_name}'):
                    dut_engine.run_cmd('sudo reboot')

                with allure.step("Waiting for switch shutdown after reload command"):
                    check_port_status_till_alive(False, dut_engine.ip, dut_engine.ssh_port)
                    dut_engine.disconnect()

        for dut in setup_info['duts']:
            dut_engine = dut['engine']
            cli_obj = dut['cli_obj']
            dut_name = dut.get('dut_name', dut.get('dut_alias', 'unknown'))

            with allure.step("Waiting for switch to be ready"):
                check_port_status_till_alive(True, dut_engine.ip, dut_engine.ssh_port)

            with allure.step(f'Verifying {dut_name} booted with correct image'):
                delimiter = cli_obj.get_installer_delimiter()
                image_list = cli_obj.get_sonic_image_list(delimiter)
                assert f'Current: {current_image_dict[dut_name]}' in image_list, \
                    f'Current: {current_image_dict[dut_name]} not in {image_list} for {dut_name}'

            with allure.step(f"Verify basic container is up on {dut_name}"):
                cli_obj.verify_dockers_are_up()

            logger.info(f"Successfully switched image on {dut_name}")

    except Exception as err:
        raise AssertionError(err)
