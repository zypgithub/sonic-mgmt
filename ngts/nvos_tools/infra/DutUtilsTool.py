import logging
import socket
import subprocess
import time
from typing import Dict
from typing import List

from netmiko import ConnectHandler
from paramiko.ssh_exception import AuthenticationException
from retry.api import retry_call, retry

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_constants.constants_nvos import SystemConsts, DatabaseConst, NvosConst
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.DatabaseTool import DatabaseTool
from ngts.tools.test_utils import allure_utils as allure
from .ResultObj import ResultObj, IssueType

logger = logging.getLogger()


class DutUtilsTool:

    @staticmethod
    def reload(engine, device, command, find_prompt_tries=80, find_prompt_delay=2, should_wait_till_system_ready=True,
               confirm=False, recovery_engine=None):
        """

        :param should_wait_till_system_ready: if True then we will wait till the system is ready, if false then we only will wait till we can re-connect to the system
        :param engine:
        :param device:
        :param command:
        :param find_prompt_tries:
        :param find_prompt_delay:
        :param confirm:
        :param recovery_engine: recover with other engine (optional)
        :return:
        """
        with allure.step('Reload the system with {} command, and wait till system is ready'.format(command)):
            list_commands = [command, 'y'] if confirm else [command]
            output = device.reload_device(engine, list_commands)
            logger.info(output)

            if 'aborted' in output.lower() or 'aborting' in output.lower():
                return ResultObj(result=False, info=output)

            res_obj = DutUtilsTool.wait_on_system_reboot(engine, recovery_engine, None, should_wait_till_system_ready,
                                                         device, False)
            if not should_wait_till_system_ready:
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
            engine.send_config_set(command, exit_config_mode=False, cmd_verify=False)
            engine.disconnect()
            retry_call(engine.run_cmd, fargs=[''], tries=find_prompt_tries, delay=find_prompt_delay, logger=logger)

            return ResultObj(result=True, info="Reconnected After Running {}".format(command))

    @staticmethod
    def wait_on_system_reboot(engine, recovery_engine=None, wait_time_before_reboot=120, wait_till_system_ready=True,
                              device=None, verify_final_result=True, wait_for_nvos=True):
        """
        Call this after an operation that should trigger a reboot. Will wait on the switch until it's functional.
        :param wait_time_before_reboot: How many seconds to wait for the switch to go down. If this time elapsed and
            the ports are still alive, we assume the switch did not start reboot at all and raise AssertionError.
        """
        with allure.step("Waiting for switch shutdown after reload command"):
            if wait_time_before_reboot is not None:
                check_port_status_till_alive(False, engine.ip, engine.ssh_port,
                                             tries=wait_time_before_reboot / 2)  # divide by 2 because 2 delay=2 seconds
            else:
                check_port_status_till_alive(False, engine.ip, engine.ssh_port)
            engine.disconnect()
            if not wait_till_system_ready:
                return ResultObj(result=True, info="system is not ready yet")

        with allure.step("Waiting for system to reboot and become available"):
            dut_engine: LinuxSshEngine = recovery_engine or engine
            with allure.step("Waiting for switch to be ready"):
                with allure.step('wait for switch reachable/ping'):
                    check_port_status_till_alive(True, dut_engine.ip, dut_engine.ssh_port)
                with allure.step('wait for ssh'):
                    dut_engine.run_cmd('echo "SSH OK"')
                if not wait_for_nvos:
                    return ResultObj(result=True, info="rebooted, ssh up, but system is not ready yet")
                with allure.step('wait for os to be functional'):
                    if device:
                        result_obj = device.wait_for_os_to_become_functional(dut_engine)
                    else:
                        result_obj = DutUtilsTool.wait_for_nvos_to_become_functional(dut_engine)
                    if verify_final_result:
                        result_obj.verify_result()
                    else:
                        return result_obj

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

            with allure.step('Wait until systemctl status is "running"'):
                wait_on_systemctl_initialization(engine)

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
    output = engine.run_cmd('nv show system')
    logger.info(output)
    if 'CLI is unavailable' in output:
        raise Exception("Waiting for NVUE to become functional")


@retry(Exception, tries=15, delay=10)
def wait_on_systemctl_initialization(engine):
    output = engine.run_cmd("sudo systemctl is-system-running")
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
        connection.send_command('nv show system log follow', expect_string=regex)
        return
