import concurrent.futures
import logging
import os
import netmiko
import json

import allure
import pytest
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from netmiko.ssh_exception import NetmikoAuthenticationException
from infra.tools.topology_tools.nogaq import upload_data_to_noga
from infra.tools.general_constants.constants import NogaConstants
from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon
from ngts.constants.constants import PlayersAliases, SonicDeployConstants, MarsConstants, SerialLoggerConst, CliType
from ngts.constants.constants import PlayersAliases, SerialLoggerConst, SSHConsts
from ngts.constants.performance_constants import PerfConsts

logger = logging.getLogger()


class DeployMethods:
    @staticmethod
    def get_current_os_engine(dut_ip):
        logger.info("Trying connect with SSH to switch")
        for nos_name, creds in SSHConsts.SSH_CREDS_DICT.items():
            engine = DeployMethods.attempt_connect_to_switch(dut_ip, nos_name, creds)
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
    def multi_nos_pre_installation_steps(duts, target_cli_type, chip_type):
        logger.info("Multi NOS pre installation steps")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for dut in duts:
                executor.submit(DeployMethods.do_multi_nos_pre_install, dut, target_cli_type, chip_type)

    @staticmethod
    def do_multi_nos_pre_install(dut, target_cli_type, chip_type):
        dut_ip = dut['dut_ip']
        current_os, engine = DeployMethods.get_current_os_engine(dut_ip)
        if engine:
            DeployMethods.validate_sudo_config(engine, current_os)
            GeneralCliCommon(engine).uninstall_os_flow(current_os, target_cli_type, chip_type)

    @staticmethod
    def validate_sudo_config(engine, current_os):
        if current_os == "Cumulus":
            cl_password = os.getenv("CUMULUS_SWITCH_PASSWORD")
            engine.run_cmd_set([
                "sudo sed -i --follow-symlinks 's/%sudo.*all=(all:all) all/%sudo all=(all:all) nopasswd: all/' /etc/sudoers",
                cl_password],
                patterns_list=["password for cumulus"])

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
            DeployMethods.multi_nos_install_traffic_generator(duts)

    @staticmethod
    def multi_nos_install_traffic_generator(duts):
        install_threads = []
        executor = concurrent.futures.ThreadPoolExecutor()
        for dut in duts:
            cli_obj = dut['cli_obj']
            with allure.step('Install traffic generator on switch: {}'.format(dut['dut_name'])):
                install_threads.append((f"Traffic Generator install on {dut['dut_name']}",
                                        executor.submit(cli_obj.install_traffic_generator)))
        DeployMethods.wait_until_deploy_background_process(install_threads)

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
