import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from netmiko import ConnectHandler
from paramiko.ssh_exception import AuthenticationException
from retry.api import retry_call, retry

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_constants.constants_nvos import SystemConsts, DatabaseConst, NvosConst
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.DatabaseTool import DatabaseTool
from ngts.tests_nvos.general.post_upgrade_switch.constants import InstallSteps
from ngts.tests_nvos.general.post_upgrade_switch.install_steps_timer import InstallStepsTimer
from ngts.tools.test_utils import allure_utils as allure
from .ResultObj import ResultObj, IssueType

logger = logging.getLogger()


@dataclass
class RebootParams:
    recovery_engine: Any = None
    topology_obj: Any = None
    wait_time_before_reboot: int = 120
    system_is_ready_timeout: int = None
    track_boot_intervals: bool = False
    should_wait_till_system_ready: bool = True


class DutUtilsTool:
    invalid_output_list = ['aborted', 'aborting', 'error']

    @staticmethod
    def reload(engine, device, command, confirm=False, reboot_params: Optional[RebootParams] = None):
        reboot_params = reboot_params or RebootParams()
        with allure.step(f'Run command "{command}" and wait for reboot to finish'):
            list_commands = [command, 'y'] if confirm else [command]
            output = device.reload_device(engine, list_commands)
            logger.info(output)

            output_lower = output.lower()
            if ('action succeeded' in output_lower) and ('reboot skipped' in output_lower):
                return ResultObj(result=True, info=output)

            error_list = ['aborted', 'aborting', 'error: action failed', 'command not found']
            for error in error_list:
                if error in output_lower:
                    return ResultObj(result=False, info=output)

            res_obj = DutUtilsTool.wait_on_system_reboot(engine, reboot_params, device,
                                                         verify_final_result=False, wait_for_nvos=True)
            if not reboot_params.should_wait_till_system_ready:
                time.sleep(40)
                return res_obj

        res_obj.returned_value = output
        return res_obj

    @staticmethod
    def check_ssh_for_authentication_error(engine, device):
        try:
            retry_call(engine.run_cmd, fargs=[''], tries=2, delay=3, logger=logger)
        except AuthenticationException as e:
            if engine.password == device.default_password:
                engine.password = NvosConst.OLD_PASS
            else:
                engine.password = device.default_password

    @staticmethod
    def run_cmd_and_reconnect(engine, command, find_prompt_tries=5, find_prompt_delay=2):
        """
            this tool will help u to run commands that disconnect the admin

        :param engine:
        :param command:
        :param find_prompt_tries:
        :param find_prompt_delay:
        :return:
        """
        with allure.step('Run {} and reconnect'.format(command)):
            engine.send_config_set(command, exit_config_mode=False, cmd_verify=False, enter_config_mode=False)
            engine.disconnect()
            retry_call(engine.run_cmd, fargs=[''], tries=find_prompt_tries, delay=find_prompt_delay, logger=logger)

            return ResultObj(result=True, info="Reconnected After Running {}".format(command))

    @staticmethod
    def wait_on_system_reboot(engine, reboot_params: Optional[RebootParams] = None, device=None, verify_final_result=True, wait_for_nvos=True):
        """
        Call this after an operation that should trigger a reboot. Will wait on the switch until it's functional.
        The RebootParams object can be used to control some parameters. If omitted, default values are used.
        """
        if not isinstance(reboot_params, RebootParams):
            reboot_params = RebootParams()
        with allure.step("Waiting for switch shutdown after reload command"):
            check_port_status_till_alive(
                False, engine.ip, engine.ssh_port,
                tries=reboot_params.wait_time_before_reboot / 2)  # divide by 2 because delay=2 seconds
            if reboot_params.track_boot_intervals:
                InstallStepsTimer.add_timestamp(InstallSteps.SHUT_DOWN)
            engine.disconnect()
            if not reboot_params.should_wait_till_system_ready:
                return ResultObj(result=True, info="system is not ready yet")

        with allure.step("Waiting for system to reboot and become available"):
            dut_engine: LinuxSshEngine = reboot_params.recovery_engine or engine
            with allure.step("Waiting for switch to be ready"):
                with allure.step('wait for switch reachable/ping'):
                    check_port_status_till_alive(True, dut_engine.ip, dut_engine.ssh_port)
                if wait_for_nvos and reboot_params.topology_obj:
                    with allure.step('wait for System is ready in serial'):
                        if reboot_params.system_is_ready_timeout:
                            DutUtilsTool.wait_for_system_ready_in_serial(reboot_params.topology_obj,
                                                                         wait_timeout=reboot_params.system_is_ready_timeout)
                        elif device:
                            DutUtilsTool.wait_for_system_ready_in_serial(reboot_params.topology_obj,
                                                                         wait_timeout=device.timeout_system_is_ready)
                        else:
                            DutUtilsTool.wait_for_system_ready_in_serial(reboot_params.topology_obj)
                        if reboot_params.track_boot_intervals:
                            InstallStepsTimer.add_timestamp(InstallSteps.SYSTEM_IS_READY_AFTER_UPGRADE)
                if not wait_for_nvos:
                    with allure.step('wait for ssh'):
                        dut_engine.run_cmd('echo "SSH OK"')
                    return ResultObj(result=True, info="rebooted, ssh up, but system is not ready yet")
                with allure.step('wait for os to be functional'):
                    if device:
                        result_obj = device.wait_for_os_to_become_functional(dut_engine)
                    else:
                        result_obj = DutUtilsTool.wait_for_nvos_to_become_functional(dut_engine)

                    if verify_final_result:
                        result_obj.verify_result()
                    return result_obj

    @staticmethod
    def wait_for_system_ready_in_serial(topology_obj, serial_engine: PexpectSerialEngine = None, wait_timeout=300):
        system_ready_pattern = 'System is ready'
        with allure.step('get serial engine'):
            serial_engine: PexpectSerialEngine = serial_engine or ConnectionTool.create_serial_engine(topology_obj, enter_serial_context=True)
        with allure.step(f'wait for "{system_ready_pattern}". timeout: {wait_timeout}'):
            serial_engine.run_cmd('', system_ready_pattern, timeout=wait_timeout, send_without_enter=True)

    @staticmethod
    def wait_for_nvos_to_become_functional(engine, find_prompt_tries=60, find_prompt_delay=10):
        with allure.step('wait until the system is ready - check SYSTEM_STATE table'):
            with allure.step('wait for the system table to exist'):
                wait_for_system_table_to_exist(engine)

            output = ''
            try:
                with allure.step('check system state in redis'):
                    output = DatabaseTool.sonic_db_cli_hgetall(engine=engine, asic="",
                                                               db_name=DatabaseConst.STATE_DB_NAME,
                                                               table_name='\"SYSTEM_READY|SYSTEM_STATE\"')
                    assert SystemConsts.STATUS_DOWN not in output and '(empty array)' not in output
            except AssertionError:
                if SystemConsts.STATUS_DOWN in output:
                    return ResultObj(result=False, info="THE SYSTEM IS NOT OK", issue_type=IssueType.PossibleBug)

                if '(empty array)' in output:
                    return ResultObj(result=False, info="SYSTEM_READY|SYSTEM_STATE TABLE IS MISSED",
                                     issue_type=IssueType.PossibleBug)

            with allure.step('wait until the CLI is up'):
                wait_until_cli_is_up(engine)

            try:
                with allure.step('Wait until systemctl status is "running"'):
                    wait_on_systemctl_initialization(engine)
            except BaseException as ex:
                logging.error("System is not ready according to systemctl status")
                engine.run_cmd("nv show system health")
                raise ex

            return ResultObj(result=True, info="System Is Ready", issue_type=IssueType.PossibleBug)

    @staticmethod
    def wait_for_cumulus_to_become_functional(engine, find_prompt_tries=60, find_prompt_delay=10):
        with allure.step('wait until the CLI is up'):
            wait_until_cli_is_up(engine)

        return ResultObj(result=True, info="System Is Ready", issue_type=IssueType.PossibleBug)

    @staticmethod
    def get_url(engine, command_opt='scp', file_full_path=''):
        if not engine or not engine.username:
            return ResultObj(result=False, info="No Engine")

        with allure.step('Trying to create url for {}'.format(engine.username)):

            with allure.step('check engine is reachable'):
                ssh_connection = ConnectionTool.create_ssh_conn(engine.ip, engine.username,
                                                                engine.password).verify_result()
                if not ssh_connection:
                    return ResultObj(result=False, info="{} is unreachable".format(engine.ip))

            with allure.step('generate url'):
                remote_url = '{}://{}:{}@{}{}'.format(command_opt, engine.username, engine.password, engine.ip,
                                                      file_full_path)

            return ResultObj(result=True, info=remote_url, returned_value=remote_url)

    @staticmethod
    def run_cmd_with_disconnect(engine, cmd, timeout=5):
        try:
            return engine.run_cmd(cmd, timeout=timeout)
        except socket.error as e:
            logging.info('Got "OSError: Socket is closed" - Current engine was also disconnected')
            engine.disconnect()
            return "Action succeeded"

    @staticmethod
    def get_engine_interface_name(engine, topology) -> str:
        dut_setup_specific_attributes: Dict[str, str] = \
            topology.players['dut']['attributes'].noga_query_data['attributes']['Specific']
        setup_mgmt_ips = [dut_setup_specific_attributes['ip_address'], dut_setup_specific_attributes['ip_address_2']]
        interface = ''
        for index, mgmt_ip in enumerate(setup_mgmt_ips):
            if mgmt_ip == engine.ip:
                interface = 'eth' + str(index)
        logger.info(f"engine interface name {interface}")
        return interface

    @staticmethod
    def get_prompt(engine: LinuxSshEngine) -> str:
        return engine.engine.send_command('', strip_prompt=False)

    @staticmethod
    def get_running_dockers(engine: LinuxSshEngine) -> List[str]:
        output = engine.run_cmd('docker ps --format \"table {{.Names}}\"', print_output=False)
        title, *dockers = output.splitlines()
        if title.strip().lower() != 'names':
            raise Exception("Got invalid response: " + output)
        return dockers

    @staticmethod
    def dut_psu_control(engines, topology_obj, skip_str='', psu_state='', dhcp_hostname='',):
        from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
        cli = NvueGeneralCli(engines.dut)
        with allure.step("Reboot {} the PSUs using reboot script".format(psu_state)):
            server_ip = cli.get_site_server_ip(topology_obj)
            ssh_conn = LinuxSshEngine(ip=server_ip, username=os.getenv("TEST_SERVER_USER"),
                                      password=os.getenv("TEST_SERVER_PASSWORD"))
            reboot_cmd = skip_str + '/.autodirect/mswg/utils/bin/rreboot ' + dhcp_hostname + ' ' + psu_state
            ssh_conn.run_cmd(reboot_cmd)


def ping_device(ip_add):
    try:
        return _ping_device(ip_add)
    except BaseException as ex:
        logging.error(str(ex))
        logging.info(f"ip address {ip_add} is unreachable")
        return False


@retry(Exception, tries=5, delay=10)
def _ping_device(ip_add):
    with allure.step(f"Ping device ip {ip_add}"):
        cmd = f"ping -c 3 {ip_add}"
        logging.info(f"Running cmd: {cmd}")
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
        output, error = process.communicate()
        logging.info("output: " + str(output))
        logging.info("error: " + str(error))
        if " 0% packet loss" in str(output):
            logging.info("Reachable using ip address: " + ip_add)
            return True
        else:
            logging.error("Unreachable using ip address: " + ip_add)
            logging.info(f"ip address {ip_add} is unreachable")
            raise Exception(f"ip address {ip_add} is unreachable")


@retry(Exception, tries=80, delay=15)
def wait_for_system_table_to_exist(engine):
    output = DatabaseTool.sonic_db_cli_hgetall(engine=engine, asic="", db_name=DatabaseConst.STATE_DB_NAME,
                                               table_name='\"SYSTEM_READY|SYSTEM_STATE\"')
    if '(empty array)' in output:
        logger.info('Waiting to SYSTEM_STATUS table to be available')
        raise Exception("System is not ready yet")
    return True


@retry(Exception, tries=80, delay=15)
def wait_until_cli_is_up(engine):
    logger.info('Checking the status of nvued')
    output = DutUtilsTool.run_cmd_with_disconnect(engine, 'nv show system')
    if 'CLI is unavailable' in output:
        raise Exception("Waiting for NVUE to become functional")


@retry(Exception, tries=15, delay=10)
def wait_on_systemctl_initialization(engine):
    output = DutUtilsTool.run_cmd_with_disconnect(engine, "sudo systemctl is-system-running")
    if "running" not in output:
        raise Exception("Waiting for systemctl to finish initializing")


def wait_for_specific_regex_in_logs(engine, regex, timeout=70):
    """

    :param engine:
    :param regex:
    :param timeout
    :return:
    """
    device = {'device_type': engine.device_type, 'host': engine.ip, 'username': engine.username,
              'password': engine.password, 'timeout': timeout}
    with allure.step(f"wait for {timeout} seconds to see '{regex}' in logs"):
        connection = ConnectHandler(**device)
        connection.send_command('nv show system log file follow', expect_string=regex)
        return
