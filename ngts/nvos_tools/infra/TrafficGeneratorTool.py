import logging
import subprocess
import threading
from ngts.nvos_constants.constants_nvos import NvosConst, SystemConsts
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
            ha = players['ha']['engine']
            hb = players['hb']['engine']

            output = ha.run_cmd("ibdev2netdev")
            assert output, f"failed to get port name for {ha.ip}"
            ha_port = output.split()[0]

            output = hb.run_cmd("ibdev2netdev")
            assert output, f"failed to get port name for {hb.ip}"
            hb_port = output.split()[0]

            with allure.step(f"Set {hb.ip} as a listener"):
                t1 = threading.Thread(target=TrafficGeneratorTool.create_listener, args=(hb, hb_port,))
                t1.start()

            with allure.step(f"Send ib traffic from {ha.ip}"):
                output = ha.run_cmd(f"ib_send_lat -F -n 5 -s 512 -i 1 {hb.ip} -d {ha_port}")

            with allure.step("Verify traffic sent successfully"):
                if "Completion with error" in output:
                    return ResultObj(False, f"Failed to send traffic: \n {output}")
                else:
                    return ResultObj(True)

        """with allure.step("Generate ib traffic"):
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
                    return ResultObj(False, "IB traffic validation failed - check log for more info.")"""

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
