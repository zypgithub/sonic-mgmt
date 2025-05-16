import pytest
import logging
from retry.api import retry_call
from ngts.constants.constants import AutonegCommandConstants, SonicConst, LinuxConsts
from ngts.tests.nightly.conftest import compare_actual_and_expected
from ngts.tests.push_build_tests.L2.lldp.test_lldp import verify_lldp_neighbor_info_for_sonic_port
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

logger = logging.getLogger()


class TestAutoFecBase:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, engines, cli_objects, chip_type, fec_modes_speed_support,
              platform_params, dut_ports_interconnects, dut_ports_number_dict, is_simx):
        self.topology_obj = topology_obj
        self.engines = engines
        self.cli_objects = cli_objects
        self.fec_modes_speed_support = fec_modes_speed_support
        self.pci_conf = self.cli_objects.dut.chassis.get_pci_conf()
        self.dut_ports_interconnects = dut_ports_interconnects
        self.dut_ports_number_dict = dut_ports_number_dict
        self.is_simx = is_simx
        self.dut_mac = self.cli_objects.dut.mac.get_mac_address_for_interface("eth0")
        self.dut_hostname = self.cli_objects.dut.chassis.get_hostname()

    def auto_fec_checker(self, conf):
        """
        The function does as following:
         1) Verify the link is up
         2) Verify fec admin mode is auto
         3) Verify fec operational mode is a valid fec mode
        :param conf: a dictionary of the port auto negotiation configuration and expected outcome
        :return: raise a assertion error in case validation failed
        """
        with allure.step("Auto Fec checker"):
            logger.info(f'Verify Fec mode on ports: {list(conf.keys())}')
            ports_fec_status = self.cli_objects.dut.interface.parse_interfaces_fec_status()
            ports_status = self.cli_objects.dut.interface.parse_interfaces_status()
            for port in conf.keys():
                iface_oper = ports_status[port][AutonegCommandConstants.OPER]
                iface_fec_admin = ports_fec_status[port][AutonegCommandConstants.FEC_ADMIN]
                iface_fec_oper = ports_fec_status[port][AutonegCommandConstants.FEC_OPER]
                assert iface_oper == "up", f"{port} actual Oper state is {iface_oper}, expected is up"
                assert iface_fec_admin == SonicConst.FEC_AUTO_MODE, \
                    f"{port} FEC admin state is {iface_fec_admin}, expected is {SonicConst.FEC_AUTO_MODE}"
                assert iface_fec_oper in SonicConst.FEC_MODE_LIST, \
                    f"{port} actual FEC state is {iface_fec_oper}, " \
                    f"expected fec should be one of: {SonicConst.FEC_MODE_LIST}"

    def verify_fec_configuration(self, conf, lldp_checker=True):
        """
        :param conf: a dictionary of the port auto negotiation configuration and expected outcome
        :param lldp_checker: True if the fec validation should check lldp info for port,
        False when fec validation is done on dut-host ports
        :return: raise Assertion error in case the configuration doesn't match the actual state on the switch
        """
        with allure.step('Verify FEC configuration on ports: {}'.format(list(conf.keys()))):
            for port, port_conf_dict in conf.items():
                retry_call(self.verify_interfaces_status_cmd_output_for_port, fargs=[port, port_conf_dict],
                           tries=20, delay=10, logger=logger)
                if not self.is_simx:
                    retry_call(self.verify_mlxlink_fec_status_for_port, fargs=[port, port_conf_dict],
                               tries=8, delay=10, logger=logger)
                if lldp_checker:
                    retry_call(self.verify_interfaces_status_on_lldp_table, fargs=[port],
                               tries=4, delay=10, logger=logger)

    def verify_mlxlink_fec_status_for_port(self, port, port_conf_dict):
        port_number = self.dut_ports_number_dict[port]
        with allure.step('Verify FEC configuration on port: {} with mlxlink command'.format(port)):
            logger.info('Verify FEC configuration on port: {} with mlxlink command'.format(port))
            mlxlink_actual_conf = self.cli_objects.dut.interface.parse_port_mlxlink_status(self.pci_conf,
                                                                                           port_number,
                                                                                           port_name=port)
            self.compare_actual_and_expected_fec_output(expected_conf=port_conf_dict, actual_conf=mlxlink_actual_conf)

    def verify_interfaces_status_cmd_output_for_port(self, port, port_conf_dict):
        with allure.step('Verify FEC configuration on port: {} with show interfaces command'.format(port)):
            logger.info('Verify FEC configuration on port: {} with show interfaces command'.format(port))
            interface_status_actual_conf = self.cli_objects.dut.interface.parse_interfaces_fec_status()[port]
            self.compare_actual_and_expected_fec_output(expected_conf=port_conf_dict,
                                                        actual_conf=interface_status_actual_conf)

    def verify_interfaces_status_on_lldp_table(self, port):
        with allure.step(f'Verify LLDP neighbor info on port: {port} with show lldp neighbor command'):
            logger.info(f'Verify LLDP neighbor info on port: {port} with show lldp neighbor command')
            lldp_info = self.cli_objects.dut.lldp.parse_lldp_info_for_specific_interface(port)
            port_neighbor = self.dut_ports_interconnects[port]
            verify_lldp_neighbor_info_for_sonic_port(port, lldp_info, self.dut_hostname, self.dut_mac, port_neighbor)

    @staticmethod
    def compare_actual_and_expected_fec_output(expected_conf, actual_conf):
        """
        :param expected_conf:
        :param actual_conf:
        :return: raise assertion error in case expected and actual configuration don't match
        """
        with allure.step('Compare expected and actual fec configuration'):
            logger.debug("expected: {}".format(expected_conf))
            logger.debug("actual: {}".format(actual_conf))
            for key, value in expected_conf.items():
                if key in actual_conf.keys():
                    actual_conf_value = actual_conf[key]
                    compare_actual_and_expected(key, value, actual_conf_value)

    def configure_auto_fec(self, ports):
        for port in ports:
            self.cli_objects.dut.interface.configure_interface_fec(port, LinuxConsts.FEC_AUTO_MODE)
