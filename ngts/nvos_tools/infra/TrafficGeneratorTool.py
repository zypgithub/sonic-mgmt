import logging
import subprocess
import time

from ngts.nvos_constants.constants_nvos import IbConsts, NvosConst, SystemConsts
from ngts.nvos_tools.hypervisor.VerifyServerFunctionality import verify_server_is_functional
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import InternalNvosConsts
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.tools.test_utils import allure_utils as allure
from infra.tools.validations.traffic_validations.ip_over_ib_traffic.ip_over_ib_traffic_runner import IPoIBTrafficChecker
from infra.tools.validations.traffic_validations.ib_traffic.ib_traffic_checker import IBTrafficChecker
from infra.tools.validations.traffic_validations.ib_traffic.ib_traffic_const import IBTrafficConst

logger = logging.getLogger()


class TrafficGeneratorTool:
    @staticmethod
    def send_ib_traffic(players, interfaces, setup_name, should_success, reverse_direction=False):
        """
        Send ib traffic
        :param interfaces: interfaces fixture
        :param players: players fixture
        :param setup_name: setup_name
        :param should_success: True of False
        :param reverse_direction: True to send from hb to ha
        """
        flags = '--no_ddp' if 'xdr_ndr' in setup_name else ''
        with allure.step("Generate ib traffic"):
            validation_obj = TrafficGeneratorTool._create_validation_obj(
                interfaces=interfaces,
                traffic_type=InternalNvosConsts.IB_TRAFFIC_LAT_TYPE,
                flags=flags,
                reverse_direction=reverse_direction,
                expected_results=IBTrafficConst.SUCCESS if should_success else IBTrafficConst.FAILURE)

            with allure.step("Send ib traffic"):
                try:
                    logger.info("Sending ib traffic")
                    IBTrafficChecker(players, validation_obj).run_validation()
                    return ResultObj(True, "IB traffic validation ended successfully")
                except BaseException as ex:
                    return ResultObj(False, "IB traffic validation failed - check log for more info.")

    @staticmethod
    def send_ipoib_traffic(players, interfaces, should_success, reverse_direction=False):
        """
        Send IPoIB traffic
        :param interfaces: interfaces fixture
        :param players: players fixture
        :param should_success: True of False
        :param reverse_direction: True to send from hb to ha
        """
        with allure.step("Generate IPoIB traffic"):
            validation_obj = TrafficGeneratorTool._create_validation_obj(
                interfaces=interfaces,
                traffic_type=InternalNvosConsts.IB_TRAFFIC_IPOIB_TYPE,
                reverse_direction=reverse_direction,
                expected_results=IBTrafficConst.SUCCESS if should_success else IBTrafficConst.FAILURE)

            with allure.step("Send IPoIB traffic"):
                try:
                    logger.info("Sending IPoIB traffic")
                    IPoIBTrafficChecker(players, validation_obj).run_validation()
                    return ResultObj(True, "IPoIB traffic validation ended successfully")
                except BaseException as ex:
                    return ResultObj(False, "IPoIB traffic validation failed - " + str(ex))

    @staticmethod
    def _create_validation_obj(interfaces, traffic_type, expected_results, flags='', reverse_direction=False):
        with allure.step("Creating validation object in order to generate traffic"):
            logger.info("Creating validation object")
            validation_obj = {'type': traffic_type,
                              'expected_traffic_result': expected_results,
                              IBTrafficConst.FLAGS: flags,
                              }
            if reverse_direction:
                validation_obj.update({
                    'sender': 'hb',
                    'sender_interface': interfaces.hb_dut_1,
                    'receiver': 'ha',
                    'receiver_interface': interfaces.ha_dut_1,
                })
            else:
                validation_obj.update({
                    'sender': 'ha',
                    'sender_interface': interfaces.ha_dut_1,
                    'receiver': 'hb',
                    'receiver_interface': interfaces.hb_dut_1,
                })
            if traffic_type == InternalNvosConsts.IB_TRAFFIC_IPOIB_TYPE:
                validation_obj['ping_args'] = {'count': 5}

            return validation_obj

    @staticmethod
    def bring_up_traffic_containers(engines, setup_name):
        """
        Bring up traffic containers in case are in down state.
        """
        if hasattr(engines, 'ha') and hasattr(engines, 'hb'):
            with allure.step("Verify traffic server is up"):
                ha_name = engines[NvosConst.HOST_HA_ATTR].noga_query_data['attributes']['Common']['Name']
                server_name = ha_name[:-len(ha_name.split('-')[-1]) - 1]
                verify_server_is_functional(server_name, NvosConst.ROOT_USER, NvosConst.ROOT_PASSWORD)
            with allure.step("Check if traffic containers are already up"):
                try:
                    ConnectionTool.ping_device(engines[NvosConst.HOST_HA].ip, num_of_retries=1)
                    ConnectionTool.ping_device(engines[NvosConst.HOST_HB].ip, num_of_retries=1)
                except BaseException:
                    with allure.step("Run reboot on bring-up containers"):
                        cmd = SystemConsts.CONTAINER_BU_TEMPLATE.format(
                            python_path=SystemConsts.PYTHON_PATH, container_bu_script=SystemConsts.CONTAINER_BU_SCRIPT,
                            setup_name=setup_name)
                        logging.info(f"cmd: {cmd}")
                        subprocess.run(cmd, shell=True, check=True, timeout=240)

            with allure.step("Verify openSM is running"):
                OpenSmTool.start_open_sm(engines)
        else:
            logger.info(f'Could not bring-up traffic containers, {NvosConst.HOST_HA} and {NvosConst.HOST_HB} '
                        f'were not found in engines')

    def start_ping_multiple_ips(self, host, ip_list):
        with allure.step("Stop any ping if it is already running on host"):
            self.stop_command_run_on_host(host, 'ping')

        with allure.step('Start pinging multiple ip addresses'):
            for ip in ip_list:
                host.run_cmd(f"nohup ping {ip} > {ip}_ping_output.txt 2>&1 & echo $!")

    def stop_ping_multiple_ips(self, host, ip_list):
        with allure.step('Stop pinging jobs and verify no packet loss'):
            self.stop_command_run_on_host(host, 'ping')

        with allure.step('Get pings info'):
            ping_outputs = []
            for ip in ip_list:
                ping_outputs.append(host.run_cmd(f'grep "% packet loss" {ip}_ping_output.txt'))
                host.run_cmd(f'rm -f {ip}_ping_output.txt')

        return ping_outputs

    @staticmethod
    def start_traffic_between_2_hosts(host_a, host_b, traffic_duration, server_output, client_output):
        with allure.step('start send traffic from Host A to Host B'):
            # Get device info from host_a and verify interface is Up
            ha_output = host_a.run_cmd(IbConsts.IB_DEV_2_NET_DEV)
            ha_device = ha_output.split()[0]
            assert '(Up)' in ha_output, (f"Host A interface is not Up. "
                                         f"ibdev2netdev output: {ha_output}")

            # Get device info from host_b and verify interface is Up
            hb_output = host_b.run_cmd(IbConsts.IB_DEV_2_NET_DEV)
            hb_device = hb_output.split()[0]
            assert '(Up)' in hb_output, (f"Host B interface is not Up. "
                                         f"ibdev2netdev output: {hb_output}")

            logger.info(f"Host A device: {ha_device} is Up")
            logger.info(f"Host B device: {hb_device} is Up")

            host_a.run_cmd(IbConsts.IB_SEND_LAT_SERVER.format(traffic_duration=traffic_duration, ib_device=ha_device,
                                                              server_output=server_output))
            host_b.run_cmd(IbConsts.IB_SEND_LAT_CLIENT.format(traffic_duration=traffic_duration, server_ip=host_a.ip,
                                                              ib_device=hb_device, client_output=client_output))
        # return traffic start time
        start_time = time.time()
        logger.info(f"start traffic time: {start_time}")
        return start_time

    def stop_traffic_between_2_hosts(self, host_a, host_b, traffic_start_time, traffic_timeout, server_file, client_file):
        with allure.step('Verify traffic results from Host A to Host B'):
            job_server = self.check_command_id_on_host(host_a, 'ib_send_lat')
            job_client = self.check_command_id_on_host(host_b, 'ib_send_lat')
            assert job_server and job_client, (f"Traffic client and/or traffic server do not exist. "
                                               f"job client: {job_client}, job server: {job_server}\n,"
                                               f"traffic time: {time.time() - traffic_start_time}, "
                                               f"traffic timeout: {traffic_timeout}")
            with allure.step('Wait for traffic send completion'):
                while True:
                    job_server = self.check_command_id_on_host(host_a, 'ib_send_lat')
                    job_client = self.check_command_id_on_host(host_b, 'ib_send_lat')
                    time_diff = time.time() - traffic_start_time
                    if not (job_server or job_client):
                        logger.info(f"Traffic is done, diff time: {time_diff}")
                        break
                    assert time_diff < traffic_timeout, \
                        (f"Traffic reached timeout ({traffic_timeout} sec) before it was done. "
                         f"job_server: {job_server}, job_client: {job_client}, time_diff: {time_diff}")

            with allure.step('Get traffic client and server results'):
                server_output = host_a.run_cmd('cat ' + server_file)
                client_output = host_b.run_cmd('cat ' + client_file)
                logger.info(f"server_output: {server_output}")
                logger.info(f"client_output: {client_output}")

            with allure.step('Delete output files'):
                host_a.run_cmd('rm -f ' + server_file)
                host_b.run_cmd('rm -f ' + client_file)

            with allure.step('Verify traffic results'):
                assert client_output and ('error' not in client_output) and ('loss' not in client_output), \
                    f'client output failed: {client_output}'
                assert server_output and ('error' not in server_output) and ('loss' not in server_output), \
                    f'server output failed: {server_output}'

            with allure.step('Compare number of iterations transmitted'):
                client_iterations = client_output.split("\n")[-2].split()[1]
                server_iterations = server_output.split("\n")[-2].split()[1]
                assert client_iterations == server_iterations, (f"Number os iterations send: {client_iterations}, "
                                                                f"Number of iterations received: {server_iterations}")
        return server_iterations

    def start_ibping_between_2_hosts(self, host_a, host_b, server_file, client_file):
        with allure.step("Stop ibping if it is already running - on both hosts"):
            hosts = [host_a, host_b]
            for host in hosts:
                self.stop_command_run_on_host(host, 'ibping')

        with allure.step('start ibping from Host A to Host B'):
            host_a_lid = host_a.run_cmd(IbConsts.BASE_LID).split()[-1]
            host_a.run_cmd(f"nohup ibping -S > {server_file} 2>&1 & echo $!")
            host_b.run_cmd(f"nohup ibping -L {host_a_lid} > {client_file} 2>&1 & echo $!")

    def stop_ibping_between_2_hosts(self, host_a, host_b, server_file, client_file):
        with allure.step('Stop pinging from Host A to Host B and verify results'):
            with allure.step(f"Stop ibping running on client"):
                self.stop_command_run_on_host(host_b, 'ibping', True)

            with allure.step(f"Stop ibping running on server"):
                self.stop_command_run_on_host(host_a, 'ibping', True)

            with allure.step(f"Verify the traffic has no packet loss"):
                cmd = f'grep "% packet loss" {client_file}'
                ping_output = host_b.run_cmd(cmd)

                # clear log files
                host_a.run_cmd(f'rm -f {server_file}')
                host_b.run_cmd(f'rm -f {client_file}')

                if ping_output:
                    assert "0% packet loss" in ping_output, f'{ping_output}'
                    num_of_packets = ping_output.split(" ")[0]
                else:
                    assert False, "Traffic information is missing"

            return num_of_packets

    @staticmethod
    def stop_command_run_on_host(host, command, check_one=False):
        with allure.step(f"Check if {command} is already running on host"):
            output = host.run_cmd(f"ps aux | grep {command}")
            lines = [line for line in output.split('\n') if 'grep' not in line]
            if check_one:
                assert len(lines) == 1, f"There is more than 1 {command} job on client side {len(lines)}"
            if lines:
                with allure.step(f"Stop ibping on {host}"):
                    process_ids = [line.split()[1] for line in lines]
                    cmd = "sudo kill -SIGINT"
                    for process_id in process_ids:
                        cmd += f" {process_id}"
                    host.run_cmd(cmd)

    @staticmethod
    def check_command_id_on_host(host, command):
        with allure.step(f"Check if {command} is already running on host"):
            output = host.run_cmd(f"ps aux | grep {command}")
            lines = [line for line in output.split('\n') if 'grep' not in line]
            assert len(lines) <= 1, f"It should be up to 1 {command} job on client side, but found {len(lines)} jobs"
            if lines:
                return lines[0].split()[1]
            else:
                return ''
