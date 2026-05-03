import copy
import logging
import subprocess

try:
    from netmiko.ssh_exception import NetmikoAuthenticationException
except ImportError:
    from netmiko.exceptions import NetmikoAuthenticationException
from retry import retry

from devts.infra.tools.connection_tools.serial_engine_factory import SerialEngineFactory
from devts.infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tools.test_utils import allure_utils as allure
import threading

logger = logging.getLogger()


class ConnectionTool:
    @staticmethod
    def create_ssh_conn(ip, username, password, port=22, retry=True):
        """
        Create an SSH connection to the specified IP address.

        Args:
            ip (str): The IP address to connect to (IPv4 or IPv6)
            username (str): The username for the SSH connection
            password (str): The password for the SSH connection

        Returns:
            ResultObj: Object containing the connection result and SSH connection if successful
        """
        with allure.step('create ssh connection with the username {username}'.format(username=username)):
            result_obj = ResultObj(False, "Couldn't connect - ")

            try:
                ssh_conn = LinuxSshEngine(ip=ip, username=username, password=password, ssh_port=port, retry=retry)

                if ConnectionTool.is_connected(ssh_conn).verify_result():
                    result_obj.returned_value = ssh_conn
                    result_obj.result = True
                    result_obj.info = 'Created ssh connection successfully'
            except NetmikoAuthenticationException as ex:
                if not result_obj.returned_value:
                    result_obj.returned_value = str(ex)
                else:
                    result_obj.returned_value += ex
                return result_obj

            return result_obj

    @staticmethod
    def create_multiple_ssh_conns(ip: str, username: str, password: str, amount: int) -> list:
        """
        Create multiple SSH connections to the given IP address.

        Args:
            ip (str): The IP address to connect to (IPv4 or IPv6)
            username (str): The username for the SSH connections
            password (str): The password for the SSH connections
            amount (int): The number of SSH connections to create

        Returns:
            list: A list of SSH connections
        """
        with allure.step(f"Create {amount} SSH connection{'' if amount == 1 else 's'} as user {username}"):
            connections = []
            threads = []

            for _ in range(amount):
                thread = threading.Thread(target=lambda: connections.append(
                    ConnectionTool.create_ssh_conn(ip, username, password)))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            return connections

    @staticmethod
    def is_connected(engine, username_to_check=None):
        """
        for me: using  lslogins cmd parser -> running processes label value
        :param engine:
        :return:
        """
        if not username_to_check:
            username_to_check = engine.username

        with allure.step(f'check number of running processes for {username_to_check} on {engine.ip}'):
            running_processes = OutputParsingTool.parse_lslogins_cmd(engine.run_cmd('lslogins {username}'.format(
                username=username_to_check))).verify_result()[SystemConsts.PASSWORD_HARDENING_RUNNING_PROCESSES]

            return ResultObj(int(running_processes) > 0, "connected to {number}".format(number=running_processes), running_processes)

    @staticmethod
    def create_serial_engine(topology_obj, ip=None, username=None, password=None, enter_serial_context=False):
        """
        @summary: Create and return a serial engine. Dispatches via
                  :class:`SerialEngineFactory` (AIR → WSS engine,
                  NVUE → pexpect, else → Mellanox).
        """
        with allure.step("create serial engine"):
            att = topology_obj.players['dut_serial']['attributes'].noga_query_data['attributes']
            attributes = att
            if ip is not None:
                attributes = copy.deepcopy(att)
                attributes['Specific']['ip'] = ip
            serial_engine = SerialEngineFactory.create(
                attributes,
                login_username=username,
                login_password=password,
            )
            if enter_serial_context:
                serial_engine.create_serial_engine(False)
            return serial_engine

    @staticmethod
    def create_serial_connection(topology_obj, devices, ip=None, username=None, password=None, force_new_login=False):
        """
        @summary: Create serial pexpect engine and initiate connection (login)
        """
        device = devices.dut
        with allure.step("create serial connection"):
            username = username if username else device.default_username
            password = password if password else device.default_password

            try:
                logger.info('Try login with given credentials')
                serial_engine = ConnectionTool.create_serial_engine(topology_obj, ip, username, password)
                serial_engine.create_serial_engine(disconnect_existing_login=force_new_login)
            except Exception as e:
                logger.info('Could not login. Try login with default NVOS credentials')
                serial_engine = ConnectionTool.create_serial_engine(topology_obj, ip,
                                                                    username=device.default_username,
                                                                    password=device.default_password)
                serial_engine.create_serial_engine(disconnect_existing_login=force_new_login)
            return serial_engine

    @staticmethod
    def ping_device(server_ip, num_of_retries=30, delay_in_sec=15):
        @retry(Exception, tries=num_of_retries, delay=delay_in_sec)
        def _ping_device(server_ip):
            logger.info("Ping {}".format(server_ip))
            # Check if the address is IPv6
            is_ipv6 = ':' in server_ip
            cmd = "ping6 -c 3 {}".format(server_ip) if is_ipv6 else "ping -c 3 {}".format(server_ip)
            logger.info("Running cmd: {}".format(cmd))
            output = subprocess.check_output(cmd, shell=True, universal_newlines=True)
            logger.info("output: " + str(output))
            if " 0% packet loss" in str(output):
                logger.info("Reachable using ip address: " + server_ip)
                return True
            else:
                logger.error("ip address {} is unreachable".format(server_ip))
                raise Exception(f"ip address {server_ip} is unreachable")

        return _ping_device(server_ip)

    @staticmethod
    def disconnect_engine(engine, reason=""):
        with allure.step("Persist session history to disk"):
            engine.run_cmd("history -w")
        with allure.step(f"Terminate SSH session ({reason})"):
            engine.disconnect()
