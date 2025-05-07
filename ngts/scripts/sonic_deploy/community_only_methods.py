import logging
import random
import allure
import shlex
import subprocess

from ngts.scripts.reset_fanout.fanout_reset_factory_test import test_fanout_reset_factory
from ngts.constants.constants import MarsConstants

logger = logging.getLogger()


def deploy_fanout_config(onyx_image_url, ansible_path, host_name):
    """
    Method which deploy fanout switch config
    """
    logger.info("Performing reset_factory on fanout switch")
    with allure.step('Deploy fanout'):
        test_fanout_reset_factory(onyx_image_url=onyx_image_url)

        logger.info("Performing deploy fanout")
        pfcwd_dockers_url = '{}/auto/sw_system_project/sonic/docker/'.format(MarsConstants.HTTP_SERVER_NBU_NFS)
        with allure.step("Deploy fanout config"):
            cmd = "ansible-playbook -i lab fanout.yml -l {host_name} " \
                  "-e pfcwd_dockers_url={pfcwd_dockers_url} -vvv".format(host_name=_remove_mlnx_lab_suffix(host_name),
                                                                         pfcwd_dockers_url=pfcwd_dockers_url)
            logger.info("Running CMD: {}".format(cmd))
            return execute_script(cmd, ansible_path)


def get_generate_minigraph_cmd(setup_info, dut_name, sonic_topo, port_number):
    """
    Method which doing minigraph generation
    """
    testbed_file = ''
    if is_dualtor_topo(sonic_topo):
        dut_name = setup_info['setup_name']
        if is_dualtor_aa_topo(sonic_topo):
            testbed_file = '-t testbed.yaml'
    cmd = "./testbed-cli.sh {TESTBED_FILE} gen-mg {SWITCH}-{TOPO} lab vault".format(TESTBED_FILE=testbed_file,
                                                                                    SWITCH=dut_name, TOPO=sonic_topo)
    if port_number:
        cmd += " -e port_number={}".format(port_number)

    return cmd


def get_deploy_minigraph_cmd(deploy_dpu=False):
    """
    Method which returns the deploy minigraph command.
    For Bluefield devices used the method which generating and deploy the minigraph in one cmd with additional parameter
    """
    cmd = "ansible-playbook -i inventory --limit {SWITCH} deploy_minigraph.yml " \
          "-e dut_minigraph={SWITCH}.{TOPO}.xml -b -vvv"
    if deploy_dpu:
        cmd = "./testbed-cli.sh deploy-mg {SWITCH}-{TOPO} lab vault"
    return cmd


def generate_minigraph(ansible_path, setup_info, dut_name, sonic_topo, port_number):
    cmd = get_generate_minigraph_cmd(setup_info, dut_name, sonic_topo, port_number)
    with allure.step('Generate Minigraph'):
        logger.info("Running CMD: {}".format(cmd))
        logger.info("Generating minigraph")
        return execute_script(cmd, ansible_path)


def deploy_minigpraph(ansible_path, dut_name, sonic_topo, recover_by_reboot, topology_obj, cli_obj, deploy_dpu=False):
    """
    Method which doing minigraph deploy on DUT
    """
    with allure.step('Deploy Minigraph'):
        cmd_temp = get_deploy_minigraph_cmd(deploy_dpu)
        cmd = cmd_temp.format(SWITCH=dut_name, TOPO=sonic_topo)
        logger.info("Running CMD: {}".format(cmd))
        if recover_by_reboot:
            try:
                logger.info("Deploying minigraph")
                return execute_script(cmd, ansible_path)
            except Exception as err:
                logger.warning("Failed in Deploying minigraph. Got error: %s", err)
                logger.warning("Performing a reboot and retrying")
                cli_obj.reboot_reload_flow(topology_obj=topology_obj, ports_list=['Ethernet0'])
        logger.info("Deploying minigraph")
        return execute_script(cmd, ansible_path)


def config_y_cable_simulator(ansible_path, setup_name, sonic_topo):
    with allure.step('Config y-cable simulator for dualtor topology'):
        cmd = "./testbed-cli.sh -k ceos config-y-cable {SETUP}-{TOPO} lab vault".format(SETUP=setup_name, TOPO=sonic_topo)
        logger.info("Configuring y-cable simulator")
        logger.info("Running CMD: {}".format(cmd))
        return execute_script(cmd, ansible_path)


def add_host_for_y_cable_simulator(dut, setup_info):
    with allure.step('Add hypervisor to dut hosts file'):
        ip = setup_info['hypervisor']['hypervisor_ip']
        name = setup_info['hypervisor']['hypervisor_name']
        logger.info('Adding "{IP} {NAME}" to file /etc/hosts'.format(IP=ip, NAME=name))
        engine = dut['engine']
        try:
            engine.disconnect()
            engine.run_cmd('sudo chmod 777 /etc/hosts')
            engine.run_cmd('echo "{IP} {NAME}" >> /etc/hosts'.format(IP=ip, NAME=name))
        except Exception:
            logger.warning('Failed to add hypervisor to dut hosts file, please add it manually.')


def reboot_validation(ansible_path, reboot, dut_name, sonic_topo):
    """
    Method which doing reboot validation
    """
    if reboot == "random":
        reboot_type = random.choice(list(MarsConstants.REBOOT_TYPES.values()))
    else:
        reboot_type = MarsConstants.REBOOT_TYPES[reboot]

    with allure.step("Reboot validation (community setup)"):
        logger.info("Running reboot type: {}".format(reboot_type))
        cmd = "ansible-playbook test_sonic.yml -i inventory --limit {SWITCH} -e testbed_name={SWITCH}-{TOPO} " \
              "-e testbed_type={TOPO} -e testcase_name=reboot -e reboot_type={REBOOT_TYPE} " \
              "-vvv".format(SWITCH=dut_name, TOPO=sonic_topo, REBOOT_TYPE=reboot_type)
        exec_result = execute_script(cmd, ansible_path)
        if not exec_result and reboot != MarsConstants.REBOOT_TYPES["reboot"]:
            cmd = "ansible-playbook test_sonic.yml -i inventory --limit {SWITCH} -e testbed_name={SWITCH}-{TOPO} " \
                  "-e testbed_type={TOPO} -e testcase_name=reboot " \
                  "-e reboot_type={REBOOT_TYPE} -vvv".format(SWITCH=dut_name, TOPO=sonic_topo,
                                                             REBOOT_TYPE=MarsConstants.REBOOT_TYPES["reboot"])
            reboot_res = execute_script(cmd, ansible_path)
            logger.info("reboot type: {} result is {}"
                        .format(MarsConstants.REBOOT_TYPES["reboot"], reboot_res))


def _remove_mlnx_lab_suffix(hostname_string):
    """
    Returns switch hostname without mlnx lab prefix
    :param hostname_string: 'arc-switch1030.mtr.labs.mlnx'
    :return: arc-switch1030
    """
    host_name_index = 0
    return hostname_string.split('.')[host_name_index]


def execute_script(cmd, exec_path, validate=True, timeout=None):
    logger.info("Executing ansible script: {}".format(cmd))
    p = subprocess.Popen(shlex.split(cmd), cwd=exec_path)
    p.communicate(timeout=timeout)
    logger.info(p.stdout)
    if validate and p.returncode != 0:
        raise AssertionError('CMD: {} failed with RC: {}'.format(cmd, p.returncode))
    return p.returncode


def is_dualtor_topo(sonic_topo):
    return 'dualtor' in sonic_topo


def is_dualtor_aa_topo(sonic_topo):
    return 'dualtor-aa' in sonic_topo
