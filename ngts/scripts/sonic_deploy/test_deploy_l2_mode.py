#!/usr/bin/env python
import allure
from ngts.scripts.test_rpc_check_and_set_topology import run_testbed_cli_script
from ngts.scripts.sonic_deploy.test_deploy_and_upgrade import get_info_from_topology


@allure.title('Deploy L2 mode')
def test_deploy_l2_mode(cli_objects, topology_obj, workspace_path):
    """
    This test will deploy l2 mode on the dut
    """
    dut_name = cli_objects.dut.chassis.get_hostname()
    setup_info = get_info_from_topology(topology_obj, workspace_path)
    ansible_cmd = f"ansible-playbook -i lab testbed_set_l2_mode.yml --vault-password-file=vault -l {dut_name} -vvv"

    with allure.step("Deploy L2 mode"):
        run_testbed_cli_script(ansible_cmd, setup_info['ansible_path'])

    # TODO: The workaround to shutdown DPU ports
    # TODO: it should be removed after issue https://github.com/sonic-net/sonic-buildimage/issues/20937 fixed
    with allure.step("Shutdown DPU ports if needed"):
        hostname = cli_objects.dut.general.hostname()
        if "bobcat" in hostname:
            dpu_port_list = ['Ethernet224', 'Ethernet232', 'Ethernet240', 'Ethernet248']
            for port in dpu_port_list:
                cli_objects.dut.interface.disable_interface(port)
            cli_objects.dut.interface.check_link_state(dpu_port_list, expected_status="down")
            cli_objects.dut.general.save_configuration()


@allure.title('Restore default mode')
def test_restore_default_mode(cli_objects, sonic_topo, topology_obj, workspace_path):
    """
    This test will restore the default mode
    """
    dut_name = cli_objects.dut.chassis.get_hostname()
    setup_info = get_info_from_topology(topology_obj, workspace_path)
    ansible_cmd = f"./testbed-cli.sh deploy-mg {dut_name}-{sonic_topo} lab vault -vvv"

    with allure.step("Deploy minigraph"):
        run_testbed_cli_script(ansible_cmd, setup_info['ansible_path'])
