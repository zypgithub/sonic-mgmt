import pytest
import logging
import re
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

    def parse_speed(self, speed_str):
        """
        Parses a speed string into number and unit
        :param speed_str: string containing speed value (e.g., "10G", "1Gbps")
        :return: dictionary with 'number' and 'unit' keys, or None if parsing fails
        """
        match = re.match(r'(\d+)(G|GbE|Gbps|M|Mbps)?', str(speed_str))
        if not match:
            return None
        number, unit = match.groups()
        return {'number': number, 'unit': unit}

    def are_units_compatible(self, unit1, unit2):
        """
        Checks if two speed units are compatible with each other
        :param unit1: first speed unit (e.g., "G", "Gbps")
        :param unit2: second speed unit (e.g., "G", "Gbps")
        :return: True if units are compatible, False otherwise
        """
        if unit1 == unit2:
            return True

        valid_units = {
            "G": {"G", "GbE", "Gbps"},
            "M": {"M", "Mbps"}
        }
        for base_unit, aliases in valid_units.items():
            if unit1 in aliases and unit2 in aliases:
                return True

        return False

    def compare_speeds_by_units(self, speed_str1, speed_str2):
        """
        Compares two speed strings to verify:
          1. Both can be successfully parsed.
          2. Their units are compatible.
          3. Their numeric values match.
        :param speed_str1: The first speed string (e.g., "10G")
        :param speed_str2: The second speed string (e.g., "10Gbps")
        :return: True if the speeds are equivalent, otherwise False
        """
        speed1 = self.parse_speed(speed_str1)
        speed2 = self.parse_speed(speed_str2)

        if not speed1 or not speed2:
            return False

        if not self.are_units_compatible(speed1["unit"], speed2["unit"]):
            return False

        if speed1["number"] != speed2["number"]:
            return False

        return True

    def compare_fec_and_speed(self, expected_value, actual_conf_value):
        """
        Compares two values - can be either FEC status or speed data
        :param expected_value: string input of the expected fec status or expected speed data
        :param actual_conf_value: string input of the actual fec status or actual speed data
        :return: true if the fec status/speed data are equivalent
        """
        if expected_value == actual_conf_value:
            return True

        return self.compare_speeds_by_units(expected_value, actual_conf_value)

    def compare_actual_and_expected_fec_output(self, expected_conf, actual_conf):
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
                    assert self.compare_fec_and_speed(value, actual_conf_value), \
                        "Compared {} result failed: actual - {}, expected - {}".format(key, actual_conf_value, value)

    def configure_auto_fec(self, ports):
        for port in ports:
            self.cli_objects.dut.interface.configure_interface_fec(port, LinuxConsts.FEC_AUTO_MODE)
