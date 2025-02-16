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
    def create_listener(host, port):
        host.run_cmd(f"ib_send_lat -F -n 5 -s 512 -i 1 -d {port}")

    @staticmethod
    def send_ib_traffic(players, interfaces, should_success):
        """
        Send ib traffic
        :param interfaces: interfaces fixture
        :param players: players fixture
        :param should_success: True of False
        """
        with allure.step("Generate ib traffic"):
            validation_obj = TrafficGeneratorTool._create_validation_obj(
                interfaces=interfaces,
                traffic_type=InternalNvosConsts.IB_TRAFFIC_LAT_TYPE,
                expected_results=IBTrafficConst.SUCCESS if should_success else IBTrafficConst.FAILURE)

            with allure.step("Send ib traffic"):
                try:
                    logger.info("Sending ib traffic")
                    IBTrafficChecker(players, validation_obj).run_validation()
                    return ResultObj(True, "IB traffic validation ended successfully")
                except BaseException as ex:
                    return ResultObj(False, "IB traffic validation failed - check log for more info.")

    @staticmethod
    def send_ipoib_traffic(players, interfaces, should_success):
        """
        Send IPoIB traffic
        :param interfaces: interfaces fixture
        :param players: players fixture
        :param should_success: True of False
        """
        with allure.step("Generate IPoIB traffic"):
            validation_obj = TrafficGeneratorTool._create_validation_obj(
                interfaces=interfaces,
                traffic_type=InternalNvosConsts.IB_TRAFFIC_IPOIB_TYPE,
                expected_results=IBTrafficConst.SUCCESS if should_success else IBTrafficConst.FAILURE)

            with allure.step("Send IPoIB traffic"):
                try:
                    logger.info("Sending IPoIB traffic")
                    IPoIBTrafficChecker(players, validation_obj).run_validation()
                    return ResultObj(True, "IPoIB traffic validation ended successfully")
                except BaseException as ex:
                    return ResultObj(False, "IPoIB traffic validation failed - " + str(ex))

    @staticmethod
    def _create_validation_obj(interfaces, traffic_type, expected_results):
        with allure.step("Creating validation object in order to generate traffic"):
            logger.info("Creating validation object")
            validation_obj = {'type': traffic_type,
                              'sender': 'ha',
                              'sender_interface': interfaces.ha_dut_1,
                              'receiver': 'hb',
                              'receiver_interface': interfaces.hb_dut_1,
                              'expected_traffic_result': expected_results
                              }
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

    @staticmethod
    def start_ping_multiple_ips(host, ip_list):
        with allure.step('Start pinging multiple ip addresses'):
            for ip in ip_list:
                host.run_cmd(f'ping {ip} &')

    @staticmethod
    def stop_ping_multiple_ips(host):
        with allure.step('Stop pinging jobs and verify no packet loss'):
            running_jobs = host.run_cmd('jobs -l').split('[')
            ping_outputs = []

            for job in running_jobs:
                if "Running" in job:
                    job_id = job.split(' ')[1]
                    output = host.run_cmd(f'kill -SIGINT {job_id}')
                    time.sleep(5)
                    ping_outputs.append(output)

            assert len(ping_outputs) > 0, 'No running jobs found'

        return ping_outputs

    @staticmethod
    def start_traffic_between_2_hosts(host_a, host_b, traffic_duration, server_output, client_output):
        with allure.step('start send traffic from Host A to Host B'):
            ha_device = host_a.run_cmd(IbConsts.IB_DEV_2_NET_DEV).split()[0]
            hb_device = host_b.run_cmd(IbConsts.IB_DEV_2_NET_DEV).split()[0]
            host_a.run_cmd(IbConsts.IB_SEND_LAT_SERVER.format(traffic_duration=traffic_duration, ib_device=ha_device,
                                                              server_output=server_output))
            host_b.run_cmd(IbConsts.IB_SEND_LAT_CLIENT.format(traffic_duration=traffic_duration, server_ip=host_a.ip,
                                                              ib_device=hb_device, client_output=client_output))
        # return traffic start time
        start_time = time.time()
        logger.info(f"start traffic time: {start_time}")
        return start_time

    @staticmethod
    def stop_traffic_between_2_hosts(host_a, host_b, traffic_start_time, traffic_timeout, server_file, client_file):
        with allure.step('Verify traffic results from Host A to Host B'):
            job_server = host_a.run_cmd(IbConsts.GET_JOB_IB)
            job_client = host_b.run_cmd(IbConsts.GET_JOB_IB)
            assert job_server and job_client, (f"Traffic client and/or traffic server not exist. "
                                               f"job client: {job_client}, job server: {job_server}")
            with allure.step('Wait for traffic send completion'):
                while True:
                    job_server = host_a.run_cmd(IbConsts.GET_JOB_IB)
                    job_client = host_b.run_cmd(IbConsts.GET_JOB_IB)
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

    @staticmethod
    def start_ibping_between_2_hosts(host_a, host_b):
        with allure.step('start ibping from Host A to Host B'):
            host_a_lid = host_a.run_cmd(IbConsts.BASE_LID).split()[-1]
            host_a.run_cmd('ibping -S &')
            host_b.run_cmd(f'ibping -L {host_a_lid} &')

    @staticmethod
    def stop_ibping_between_2_hosts(host_a, host_b):
        with allure.step('Stop pinging from Host A to Host B and verify results'):
            job_server = host_a.run_cmd('jobs -l').split(' ')[1]
            job_sender = host_b.run_cmd('jobs -l').split(' ')[1]

            ping_output = host_b.run_cmd(f'kill -SIGINT {job_sender}')
            num_of_packets = ping_output.split(" ")[0]
            host_a.run_cmd(f'kill -SIGINT {job_server}')
            assert "0% packet loss" in ping_output, f'{ping_output}'

        return num_of_packets
