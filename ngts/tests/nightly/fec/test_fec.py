import pytest
import logging
import random
import re
from retry import retry
from retry.api import retry_call

from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.tests.nightly.conftest import reboot_reload_random, cleanup, save_configuration
from ngts.constants.constants import AutonegCommandConstants, SonicConst, \
    LinuxConsts, FecConstants
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.tests.nightly.fec.conftest import get_tested_lb_dict_tested_ports
from ngts.helpers.interface_helpers import get_lb_mutual_speed, speed_string_to_int_in_mb
from ngts.tests.nightly.auto_negotition.auto_fec_common import TestAutoFecBase
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

logger = logging.getLogger()


class TestFec(TestAutoFecBase):

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, interfaces, engines, cli_objects,
              tested_lb_dict, tested_lb_dict_for_bug_2705016_flow, pci_conf,
              fec_capability_for_dut_ports, dut_ports_number_dict,
              split_mode_supported_speeds, tested_dut_to_host_conn, fec_modes_speed_support,
              dut_ports_default_speeds_configuration, dut_ports_default_mlxlink_configuration, chip_type,
              platform_params, dut_ports_interconnects, host_speed_type_support, is_simx, ports_support_autoneg,
              mlxlink_supported_speeds):
        self.topology_obj = topology_obj
        self.chip_type = chip_type
        self.platform_params = platform_params
        self.dut_ports_interconnects = dut_ports_interconnects
        self.interfaces = interfaces
        self.engines = engines
        self.is_simx = is_simx
        self.cli_objects = cli_objects
        self.dut_mac = self.cli_objects.dut.mac.get_mac_address_for_interface("eth0")
        self.dut_hostname = self.cli_objects.dut.chassis.get_hostname()
        self.tested_lb_dict = tested_lb_dict
        self.tested_lb_dict_for_bug_2705016_flow = tested_lb_dict_for_bug_2705016_flow
        self.tested_dut_to_host_conn = tested_dut_to_host_conn
        self.pci_conf = pci_conf
        self.fec_capability_for_dut_ports = fec_capability_for_dut_ports
        self.dut_ports_number_dict = dut_ports_number_dict
        self.split_mode_supported_speeds = split_mode_supported_speeds
        self.fec_modes_speed_support = fec_modes_speed_support
        self.host_speed_type_support = host_speed_type_support
        self.ports_support_autoneg = ports_support_autoneg
        # For Cleanup
        self.dut_ports_basic_speeds_configuration = dut_ports_default_speeds_configuration
        self.dut_ports_basic_mlxlink_configuration = dut_ports_default_mlxlink_configuration
        self.mlxlink_supported_speeds = mlxlink_supported_speeds

    @pytest.mark.reboot_reload
    def test_fec_capabilities_loopback_ports(self, cleanup_list, sw_control_ports):
        with allure.step("Configure and verify FEC with all speed options on dut loopbacks"):
            logger.info("Configure and verify FEC with all speed options on dut loopbacks")
            dut_lb_conf = self.check_all_speeds_with_fec(self.tested_lb_dict, cleanup_list)

        tested_ports = list(dut_lb_conf.keys())
        if sw_control_ports and is_redmine_issue_active([3886748]):
            tested_ports = [port for port in tested_ports if port not in sw_control_ports]

        reboot_reload_random(self.topology_obj, self.engines.dut, self.cli_objects.dut,
                             tested_ports, cleanup_list, simx=self.is_simx)

        with allure.step("Verify FEC on dut loopbacks"):
            self.verify_fec_configuration(dut_lb_conf)

        with allure.step("Cleaning FEC configuration and verify port state was restored"):
            logger.info("Cleanup Configuration")
            cleanup(cleanup_list)
            self.update_conf(dut_lb_conf)

        with allure.step("Verify FEC on dut loopbacks"):
            logger.info("Verify FEC on dut loopbacks returned to default configuration")
            self.verify_fec_configuration(dut_lb_conf)
        self.pop_autoneg_enabled_from_cleanup_list(tested_ports, cleanup_list)

    @pytest.mark.reboot_reload
    def test_fec_capabilities_hosts_ports(self, cleanup_list, sw_control_ports):

        with allure.step("Configure IP on dut - host connectivities for traffic validation"):
            logger.info("Configure IP on dut - host connectivities for traffic validation")
            ip_conf = self.set_peer_port_ip_conf(cleanup_list)

        with allure.step("Configure and verify FEC with all speed options on dut - host ports"):
            logger.info("Configure and verify FEC with all speed options on dut - host ports")
            dut_host_conf = self.check_all_speeds_with_fec_on_host_ports(ip_conf, cleanup_list)

        tested_ports = list(dut_host_conf.keys())
        if sw_control_ports and is_redmine_issue_active([3886748]):
            tested_ports = [port for port in tested_ports if port not in sw_control_ports]

        reboot_reload_random(self.topology_obj, self.engines.dut, self.cli_objects.dut, tested_ports,
                             cleanup_list, simx=self.is_simx)

        with allure.step("Verify FEC on dut - host connectivities"):
            logger.info("Verify FEC on dut - host connectivities")
            self.verify_fec_configuration(dut_host_conf, lldp_checker=False)
            if not self.is_simx:
                logger.info("Verify FEC on host - dut connectivities")
                self.verify_fec_configuration_on_host(dut_host_conf, tested_ports)

        with allure.step("Verify traffic on dut - host connectivities"):
            self.validate_traffic(ip_conf)

        with allure.step("Cleaning FEC configuration and verify port state was restored"):
            logger.info("Cleanup Configuration")
            cleanup(cleanup_list)
            self.update_conf(dut_host_conf)

        for dut_host_port in dut_host_conf.keys():
            with allure.step(f"Configure AUTONEG mode: enabled on dut host port: {dut_host_port}"):
                self.cli_objects.dut.interface.config_auto_negotiation_mode(dut_host_port, mode="enabled")

        with allure.step("Verify FEC on dut - host connectivities"):
            logger.info("Verify FEC on dut - host connectivities returned to default configuration")
            self.verify_fec_configuration(dut_host_conf, lldp_checker=False)
            if not self.is_simx:
                logger.info("Verify FEC on host - dut connectivities returned to default configuration")
                self.verify_fec_configuration_on_host(dut_host_conf, tested_ports)

    def test_negative_fec(self, cleanup_list):
        split_mode = 1
        conf = {}
        dut_host_port = self.interfaces.dut_hb_2
        host_dut_port = self.interfaces.hb_dut_2
        port_supported_fec_modes = self.get_fec_capability_for_negative_test(dut_host_port)
        mode_to_configure_on_host = random.choice(port_supported_fec_modes)
        modes_to_configure_on_dut = set(port_supported_fec_modes)
        modes_to_configure_on_dut.remove(mode_to_configure_on_host)

        self.configure_fec_mode_on_host_port(mode_to_configure_on_host,
                                             self.cli_objects.hb,
                                             self.engines.hb,
                                             host_dut_port,
                                             cleanup_list)

        for fec_mode in modes_to_configure_on_dut:
            with allure.step("Configure mismatched FEC mode: {} on dut port: {}".format(fec_mode, dut_host_port)):
                self.configure_fec_on_dut_host_port(conf, fec_mode, split_mode,
                                                    dut_host_port, host_dut_port, cleanup_list, disable_autoneg=False)
                conf[dut_host_port][AutonegCommandConstants.OPER] = "down"

            with allure.step("Verify link is down with mismatched FEC modes"):
                retry_call(self.verify_interfaces_status_cmd_output_for_port, fargs=[dut_host_port,
                                                                                     conf[dut_host_port]],
                           tries=3, delay=5, logger=logger)

        with allure.step("Configure matched FEC mode: {} on dut port: {}".format(mode_to_configure_on_host,
                                                                                 dut_host_port)):
            self.configure_fec_on_dut_host_port(conf, mode_to_configure_on_host,
                                                split_mode, dut_host_port, host_dut_port,
                                                cleanup_list)

        with allure.step(f"Configure AUTONEG mode: enabled on dut host port: {dut_host_port}"):
            self.cli_objects.dut.interface.config_auto_negotiation_mode(dut_host_port, mode="enabled")

        with allure.step("Verify FEC on dut - host connectivity is UP after correct FEC configuration"):
            self.verify_fec_configuration(conf, lldp_checker=False)
            retry_call(self.verify_fec_configuration_on_host_port,
                       fargs=[conf[dut_host_port], self.cli_objects.hb, host_dut_port],
                       tries=6, delay=10, logger=logger)

    def test_fec_bug_2705016(self, cli_objects, cleanup_list, sw_control_ports):
        reboot_type = 'warm-reboot'
        tested_ports = get_tested_lb_dict_tested_ports(self.tested_lb_dict_for_bug_2705016_flow)
        ports_for_toggle_flow, ports_for_disable_enable_flow = \
            self.get_ports_for_test_flow(self.tested_lb_dict_for_bug_2705016_flow)
        if sw_control_ports and is_redmine_issue_active([3886748]):
            tested_ports = [port for port in tested_ports if port not in sw_control_ports]
            ports_for_toggle_flow = [port for port in ports_for_toggle_flow if port not in sw_control_ports]
            ports_for_disable_enable_flow = [port for port in ports_for_disable_enable_flow if port not in
                                             sw_control_ports]
        logger.info("Ports to be disabled before warm-reboot and then enabled: {}"
                    .format(ports_for_disable_enable_flow))
        logger.info("Ports to be toggled after warm-reboot: {}"
                    .format(ports_for_toggle_flow))

        with allure.step("Configure FEC mode on ports: {}".format(tested_ports)):
            conf = self.configure_fec(self.tested_lb_dict_for_bug_2705016_flow,
                                      cleanup_list)

        self.verify_fec_configuration(conf)

        with allure.step("Disable ports: {}".format(ports_for_disable_enable_flow)):
            self.disable_ports(ports_for_disable_enable_flow, cleanup_list)

        with allure.step("Save configuration and warm reboot"):
            save_configuration(self.engines.dut, self.cli_objects.dut, cleanup_list)
            self.cli_objects.dut.general.safe_reboot_flow(topology_obj=self.topology_obj, reboot_type=reboot_type)
            cli_objects.dut.general.verify_dockers_are_up(SonicConst.DOCKERS_LIST)

        with allure.step("Toggle ports: {}".format(ports_for_toggle_flow)):
            self.toggle_ports(ports_for_toggle_flow, cleanup_list)

        with allure.step("Enable ports: {}".format(ports_for_disable_enable_flow)):
            self.enable_ports(ports_for_disable_enable_flow)

        with allure.step("Verify ports: {} are up".format(tested_ports)):
            cli_objects.dut.interface.check_link_state(tested_ports)

        self.verify_fec_configuration(conf)
        self.pop_autoneg_enabled_from_cleanup_list(tested_ports, cleanup_list)

    @staticmethod
    def get_ports_for_test_flow(tested_lb_dict_for_bug_2705016_flow):
        ports_for_toggle_flow, ports_for_disable_enable_flow = [], []
        for split_mode, fec_mode_tested_lb_dict in tested_lb_dict_for_bug_2705016_flow.items():
            for fec_mode, lb_list in fec_mode_tested_lb_dict.items():
                if len(lb_list) == 1:
                    random_list = random.choice([ports_for_toggle_flow, ports_for_disable_enable_flow])
                    random_list += lb_list[0]
                else:
                    ports_for_toggle_flow += lb_list[0]
                    ports_for_disable_enable_flow += lb_list[1]
        return ports_for_toggle_flow, ports_for_disable_enable_flow

    def toggle_ports(self, ports, cleanup_list):
        logger.info("Toggle ports: {}".format(ports))
        for port in ports:
            self.toggle_port(port, cleanup_list)

    def disable_ports(self, ports, cleanup_list):
        logger.info("Disable ports: {}".format(ports))
        for port in ports:
            cleanup_list.append((self.cli_objects.dut.interface.enable_interface, (port,)))
            self.cli_objects.dut.interface.disable_interface(port,)

    def enable_ports(self, ports):
        logger.info("Enable ports: {}".format(ports))
        for port in ports:
            self.cli_objects.dut.interface.enable_interface(port)

    def toggle_port(self, port, cleanup_list):
        logger.info("Toggle port: {}".format(port))
        cleanup_list.append((self.cli_objects.dut.interface.enable_interface, (port,)))
        self.cli_objects.dut.interface.disable_interface(port)
        self.cli_objects.dut.interface.enable_interface(port)

    def set_peer_port_ip_conf(self, cleanup_list):
        """
        set ips on the dut and host ports
        :param cleanup_list:  a list of cleanup functions that should be called in the end of the test
        :return: None
        """
        ip_conf = {}
        ip_template = '{ip_prefix}.{ip_prefix}.{ip_prefix}.{ip_index}'
        ip_index = 1
        ip_prefix = 20
        for fec_mode, tested_dut_host_conn_dict in self.tested_dut_to_host_conn.items():
            ip_config_dict = dict()
            dst_ip = ip_template.format(ip_prefix=ip_prefix, ip_index=ip_index)
            ip_config_dict['dut'] = [{'iface': tested_dut_host_conn_dict["dut_port"],
                                      'ips': [(dst_ip, '24')]}]
            ip_index += 1
            ip_config_dict[tested_dut_host_conn_dict['host']] = [{'iface': tested_dut_host_conn_dict["host_port"],
                                                                  'ips': [(ip_template.format(ip_prefix=ip_prefix,
                                                                                              ip_index=ip_index),
                                                                           '24')]}]
            ip_index += 1
            ip_prefix += 10
            ip_conf[tested_dut_host_conn_dict["dut_port"]] = {
                "sender": tested_dut_host_conn_dict['host'],
                "src": tested_dut_host_conn_dict["host_port"],
                "dst": tested_dut_host_conn_dict["dut_port"],
                "dst_ip": dst_ip
            }
            cleanup_list.append((IpConfigTemplate.cleanup, (self.topology_obj, ip_config_dict,)))
            IpConfigTemplate.configuration(self.topology_obj, ip_config_dict)
        return ip_conf

    def configure_fec(self, tested_lb_dict, cleanup_list):
        conf = {}
        for split_mode, fec_mode_tested_lb_dict in tested_lb_dict.items():
            for fec_mode, lb_list in fec_mode_tested_lb_dict.items():
                for lb in lb_list:
                    speed, interface_type = self.get_lb_config_for_fec_mode(lb, fec_mode, split_mode)
                    if speed:
                        for port in lb:
                            self.update_port_fec_conf_dict(conf, port, speed, fec_mode, interface_type, cleanup_list)
                    else:
                        logger.warning(f"Could not find supported interface type with FEC mode: {fec_mode} with "
                                       f"split_mode: {split_mode} on loopback: {lb}. "
                                       f"Skipping fec configuration on that lb")
        return conf

    def check_all_speeds_with_fec(self, tested_lb_dict, cleanup_list):
        conf = {}
        for split_mode, fec_mode_tested_lb_dict in tested_lb_dict.items():
            for fec_mode, lb_list in fec_mode_tested_lb_dict.items():
                dut_lb_conf = {}
                lb = lb_list.pop()
                speed_options = self.get_lb_speeds_option_for_fec_mode(lb, split_mode,
                                                                       fec_mode, self.fec_modes_speed_support)
                random.shuffle(speed_options)
                for speed in speed_options:
                    with allure.step(f"Configure FEC mode: {fec_mode} with speed: {speed} on loopback: {lb}"):
                        supported_interface_types = self.get_lb_interface_types_for_speed(lb, fec_mode, split_mode,
                                                                                          speed)
                        if supported_interface_types:
                            interface_type = random.choice(supported_interface_types)
                            self.configure_fec_speed_on_ports(dut_lb_conf, lb, speed, fec_mode,
                                                              interface_type, cleanup_list)
                        else:
                            logger.warning(f"Could not find supported interface type with FEC mode: {fec_mode} with "
                                           f"speed: {speed} on loopback: {lb}. Skipping validation of that speed")
                            continue
                    with allure.step(f"Verify FEC mode: {fec_mode} with speed: {speed} on loopback: {lb}"):
                        self.verify_fec_configuration(dut_lb_conf)
                conf.update(dut_lb_conf)
                self.set_cleanup_of_latest_config(lb, cleanup_list)
        return conf

    def configure_fec_speed_on_ports(self, dut_lb_conf, ports, speed, fec_mode, interface_type, cleanup_list):
        for port in ports:
            self.update_port_fec_conf_dict(dut_lb_conf, port, speed,
                                           fec_mode, interface_type,
                                           cleanup_list, set_cleanup=False)

    def set_cleanup_of_latest_config(self, lb, cleanup_list):
        for port in lb:
            self.set_speed_fec_cleanup(port, cleanup_list)

    def get_lb_speed_conf_for_fec_mode(self, lb, split_mode, fec_mode, fec_modes_speed_support):
        mutual_speeds_option = self.get_lb_speeds_option_for_fec_mode(lb, split_mode, fec_mode, fec_modes_speed_support)
        speed = random.choice(mutual_speeds_option)
        return speed

    def get_lb_speeds_option_for_fec_mode(self, lb, split_mode, fec_mode, fec_modes_speed_support):
        lb_mutual_speeds = set(get_lb_mutual_speed(lb, split_mode, self.split_mode_supported_speeds))
        lb_cable_supported_speeds = self.get_lb_cable_mutual_speeds(lb)
        fec_mode_supported_speeds = set(fec_modes_speed_support[fec_mode][split_mode].keys())
        mutual_speeds_option = list(lb_mutual_speeds & lb_cable_supported_speeds & fec_mode_supported_speeds)
        return mutual_speeds_option

    def configure_fec_on_dut_host_ports(self, cleanup_list):
        conf = {}
        split_mode = 1
        for fec_mode, tested_dut_host_conn_dict in self.tested_dut_to_host_conn.items():
            dut_host_port = tested_dut_host_conn_dict["dut_port"]
            host_dut_port = tested_dut_host_conn_dict["host_port"]
            self.configure_fec_on_dut_host_port(conf, fec_mode, split_mode, dut_host_port, host_dut_port, cleanup_list)
        return conf

    def check_all_speeds_with_fec_on_host_ports(self, ip_conf, cleanup_list):
        conf = {}
        split_mode = 1
        for fec_mode, tested_dut_host_conn_dict in self.tested_dut_to_host_conn.items():
            dut_host_port = tested_dut_host_conn_dict["dut_port"]
            host_dut_port = tested_dut_host_conn_dict["host_port"]
            dut_host_conf = {}
            speed_options = self.get_dut_host_port_speeds_option_for_fec_mode(fec_mode, split_mode,
                                                                              dut_host_port, host_dut_port)
            random.shuffle(speed_options)
            for speed in speed_options:
                mutual_types = self.get_mutual_types(fec_mode, split_mode, speed, host_dut_port)
                if mutual_types:
                    interface_type = random.choice(mutual_types)
                    self.configure_and_verify_fec_speed_on_hosts_ports(tested_dut_host_conn_dict, dut_host_conf,
                                                                       ip_conf, interface_type, speed,
                                                                       fec_mode, cleanup_list)
                else:
                    logger.info(f"No mutual type on dut and host for {fec_mode} with speed: {speed},"
                                f" on dut host port: {dut_host_port}")
            self.set_cleanup_of_latest_config([dut_host_port], cleanup_list)
            conf.update(dut_host_conf)
        return conf

    def get_mutual_types(self, fec_mode, split_mode, speed, host_dut_port):
        dut_types = self.fec_modes_speed_support[fec_mode][split_mode][speed]
        host_types = self.host_speed_type_support[host_dut_port][speed]
        mutual_types = list(set(host_types) & set(dut_types))
        return mutual_types

    def configure_and_verify_fec_speed_on_hosts_ports(self, tested_dut_host_conn_dict, dut_host_conf, ip_conf,
                                                      interface_type, speed, fec_mode, cleanup_list):
        dut_host_port = tested_dut_host_conn_dict["dut_port"]
        host_dut_port = tested_dut_host_conn_dict["host_port"]
        cli_object = tested_dut_host_conn_dict["cli"]
        with allure.step(f"Configure FEC mode: {fec_mode} with speed: {speed} on dut host port: {dut_host_port}"):
            logger.info(f"Configure FEC mode: {fec_mode} with speed: {speed} on dut host port: {dut_host_port}")
            self.configure_fec_speed_on_ports(dut_host_conf, [dut_host_port], speed, fec_mode,
                                              interface_type, cleanup_list)
        with allure.step(f"Configure AUTONEG mode: enabled on dut host port: {dut_host_port}"):
            self.cli_objects.dut.interface.config_auto_negotiation_mode(dut_host_port, mode="enabled")
        with allure.step(f"Verify FEC mode: {fec_mode} with speed: {speed} on dut host port: {dut_host_port}"):
            logger.info(f"Verify FEC mode: {fec_mode} with speed: {speed} on dut host port: {dut_host_port}")
            self.verify_fec_configuration(dut_host_conf, lldp_checker=False)
        if not self.is_simx:
            with allure.step(f"Verify FEC mode: {fec_mode} with speed: {speed} on host dut port: {host_dut_port}"):
                logger.info(f"Verify FEC mode: {fec_mode} with speed: {speed} on host dut port: {host_dut_port}")
                self.verify_fec_configuration_on_host_port(dut_host_conf[dut_host_port], cli_object, host_dut_port)
        with allure.step("Verify traffic on dut - host connectivity"):
            traffic_validation = ip_conf[dut_host_port]
            retry_call(
                self.validate_traffic_on_dut_host_ports,
                fargs=[traffic_validation],
                tries=3,
                delay=5,
                logger=logger,
            )

    def get_dut_host_port_speeds_option_for_fec_mode(self, fec_mode, split_mode, dut_host_port, host_dut_port):
        fec_mode_supported_speeds = set(self.fec_modes_speed_support[fec_mode][split_mode].keys())
        ports_supported_speeds = get_lb_mutual_speed([dut_host_port, host_dut_port], split_mode,
                                                     self.split_mode_supported_speeds)
        if self.is_simx:
            ports_supported_speeds = list(self.split_mode_supported_speeds[dut_host_port][split_mode])
        mutual_speeds_option = list(fec_mode_supported_speeds.intersection(ports_supported_speeds))
        return mutual_speeds_option

    def configure_fec_on_dut_host_port(self, conf, fec_mode, split_mode, dut_host_port, host_dut_port, cleanup_list,
                                       disable_autoneg=True):
        mutual_speeds_option = self.get_dut_host_port_speeds_option_for_fec_mode(fec_mode, split_mode,
                                                                                 dut_host_port, host_dut_port)
        speed = random.choice(mutual_speeds_option)
        interface_type = random.choice(self.fec_modes_speed_support[fec_mode][split_mode][speed])
        self.update_port_fec_conf_dict(conf, dut_host_port, speed, fec_mode, interface_type, cleanup_list,
                                       disable_autoneg=disable_autoneg)

    def configure_fec_mode_on_host(self, cleanup_list):
        for fec_mode, tested_dut_host_conn_dict in self.tested_dut_to_host_conn.items():
            self.configure_fec_mode_on_host_port(fec_mode,
                                                 cli_object=tested_dut_host_conn_dict["cli"],
                                                 engine=tested_dut_host_conn_dict["engine"],
                                                 interface=tested_dut_host_conn_dict["host_port"],
                                                 cleanup_list=cleanup_list)

    @staticmethod
    def configure_fec_mode_on_host_port(fec_mode, cli_object, engine, interface, cleanup_list):
        logger.info("Configure FEC mode: {} on host port: {} on host: {}".format(fec_mode,
                                                                                 interface,
                                                                                 engine.ip))
        with allure.step("Configure FEC mode: {} on host port: {} on host: {}".format(fec_mode,
                                                                                      interface,
                                                                                      engine.ip)):
            cleanup_list.append((cli_object.interface.configure_interface_fec, (interface,
                                                                                LinuxConsts.FEC_AUTO_MODE)))
            cli_object.interface.configure_interface_fec(interface, fec_option=fec_mode)

    def verify_fec_configuration_on_host(self, conf, tested_ports):
        for fec_mode, tested_dut_host_conn_dict in self.tested_dut_to_host_conn.items():
            cli_object = tested_dut_host_conn_dict["cli"]
            interface = tested_dut_host_conn_dict["host_port"]
            if interface not in tested_ports:
                logger.info(f"Skip SW control port {interface}")
            else:
                dut_port = tested_dut_host_conn_dict["dut_port"]
                expected_conf = conf[dut_port]
                self.verify_fec_configuration_on_host_port(expected_conf, cli_object, interface)

    @retry(Exception, tries=6, delay=10)
    def verify_fec_configuration_on_host_port(self, expected_conf, cli_object, interface):
        actual_speed = cli_object.interface.parse_show_interface_ethtool_status(interface)["speed"]
        actual_fec_mode = cli_object.interface.parse_interface_fec(interface)[LinuxConsts.ACTIVE_FEC]
        actual_host_port_conf = {
            AutonegCommandConstants.SPEED: actual_speed,
            AutonegCommandConstants.FEC: actual_fec_mode
        }
        self.compare_actual_and_expected_fec_output(expected_conf=expected_conf, actual_conf=actual_host_port_conf)

    def validate_traffic(self, ip_conf):
        """
        send ping between dut and host and validate the results
        :param ip_conf: ip_conf
        :return: raise assertion errors in case of validation errors
        """
        for dut_host_port, traffic_validation in ip_conf.items():
            self.validate_traffic_on_dut_host_ports(traffic_validation)

    def validate_traffic_on_dut_host_ports(self, traffic_validation):
        with allure.step('send ping from {} to {}'.format(traffic_validation["src"],
                                                          traffic_validation["dst"])):
            validation = {'sender': traffic_validation["sender"],
                          'args': {'interface': traffic_validation["src"],
                                   'count': 3,
                                   'dst': traffic_validation["dst_ip"]}}
            ping = PingChecker(self.topology_obj.players, validation)
            logger.info('Sending 3 untagged packets from {} to {}'.format(traffic_validation["src"],
                                                                          traffic_validation["dst"]))
            ping.run_validation()

    def update_port_fec_conf_dict(self, conf, port, speed, tested_fec_mode,
                                  interface_type, cleanup_list, set_cleanup=True, disable_autoneg=True):
        interface_width = self.get_interface_width(interface_type)
        if set_cleanup:
            self.set_speed_fec_cleanup(port, cleanup_list)

        self.cli_objects.dut.interface.disable_interface(port)
        if disable_autoneg:
            self.cli_objects.dut.interface.config_auto_negotiation_mode(port, "disabled")

        self.cli_objects.dut.interface.config_interface_type(port, 'none')
        self.cli_objects.dut.interface.set_interface_speed(port, speed)
        self.cli_objects.dut.interface.config_advertised_speeds(port, speed_string_to_int_in_mb(speed))
        if not self.is_copper_cable(port):
            interface_type.replace(FecConstants.COPPER_TYPE_PREFIX, FecConstants.OPTIC_TYPE_PREFIX)
        self.cli_objects.dut.interface.config_interface_type(port, interface_type)
        self.cli_objects.dut.interface.config_advertised_interface_types(port, interface_type)
        self.cli_objects.dut.interface.configure_interface_fec(port, tested_fec_mode)
        if self.port_requires_autoneg_config(port, speed, interface_width):
            self.cli_objects.dut.interface.config_auto_negotiation_mode(port, "enabled")
        self.cli_objects.dut.interface.enable_interface(port)

        conf[port] = {AutonegCommandConstants.SPEED: speed,
                      AutonegCommandConstants.ADV_SPEED: speed,
                      AutonegCommandConstants.ADV_TYPES: interface_type,
                      AutonegCommandConstants.FEC: tested_fec_mode,
                      AutonegCommandConstants.WIDTH: self.get_interface_width(interface_type),
                      AutonegCommandConstants.ADMIN: 'up',
                      AutonegCommandConstants.OPER: 'up'
                      }

    @staticmethod
    def get_interface_width(interface_type):
        """
        :param interface_type: a interface type string 'CR'
        :return: int width  value, i.e, '1'
        more examples,
        'CR' -> 1
        'CR2' -> 2
        'CR4' -> 4
        """
        match = re.search(r"\w+(\d+)", interface_type)
        if match:
            width = match.group(1)
            return int(width)
        else:
            return 1

    @staticmethod
    def is_port_pam4(n_active_lanes, speed):
        return (speed_string_to_int_in_mb(speed) / n_active_lanes) >= AutonegCommandConstants.PAM4_MIN_LANE_SPEED_MB

    def set_speed_fec_cleanup(self, port, cleanup_list):
        cleanup_list.append((self.cli_objects.dut.interface.disable_interface, (port,)))
        base_speed = self.dut_ports_basic_speeds_configuration[port]
        base_fec = self.dut_ports_basic_mlxlink_configuration[port][AutonegCommandConstants.FEC]
        base_interface_type = self.dut_ports_basic_mlxlink_configuration[port][AutonegCommandConstants.TYPE]
        if not self.is_copper_cable(port):
            base_interface_type.replace(FecConstants.COPPER_TYPE_PREFIX, FecConstants.OPTIC_TYPE_PREFIX)
        cleanup_list.append((self.cli_objects.dut.interface.config_auto_negotiation_mode, (port, "disabled")))
        cleanup_list.append((self.cli_objects.dut.interface.config_interface_type, (port,
                                                                                    'none')))
        cleanup_list.append((self.cli_objects.dut.interface.set_interface_speed, (port, base_speed)))
        cleanup_list.append((self.cli_objects.dut.interface.config_interface_type, (port,
                                                                                    base_interface_type)))
        cleanup_list.append(
            (self.cli_objects.dut.interface.config_advertised_speeds, (port, speed_string_to_int_in_mb(base_speed))))
        cleanup_list.append(
            (self.cli_objects.dut.interface.config_advertised_interface_types, (port, base_interface_type)))

        cleanup_list.append((self.cli_objects.dut.interface.configure_interface_fec, (port, base_fec)))

        if self.port_requires_autoneg_config(port, base_speed, self.get_interface_width(base_interface_type)):
            cleanup_list.append((self.cli_objects.dut.interface.config_auto_negotiation_mode, (port, "enabled")))
        cleanup_list.append((self.cli_objects.dut.interface.enable_interface, (port,)))

    def update_conf(self, conf):
        for port, port_conf in conf.items():
            base_speed = self.dut_ports_basic_speeds_configuration[port]
            base_fec = self.dut_ports_basic_mlxlink_configuration[port][AutonegCommandConstants.FEC]
            base_width = \
                self.get_interface_width(self.dut_ports_basic_mlxlink_configuration[port][AutonegCommandConstants.TYPE])
            conf[port][AutonegCommandConstants.SPEED] = base_speed
            conf[port][AutonegCommandConstants.FEC] = base_fec
            conf[port][AutonegCommandConstants.WIDTH] = base_width

    def get_fec_capability_for_negative_test(self, dut_host_port):
        """
        auto fec cannot be tested in the negative test because the test
        checks that incompatible fec result in port down and auto fec mode will
        result in mutual fec configuration.
        :param dut_host_port: i.e, dut_host_port = 'Ethernet28'
        :return: fec capabilities on port without auto
        """
        port_supported_fec_modes = self.fec_capability_for_dut_ports[dut_host_port]
        if 'auto' in port_supported_fec_modes:
            port_supported_fec_modes.remove('auto')
        return port_supported_fec_modes

    def port_requires_autoneg_config(self, port, speed, interface_width):
        """
        The function returns whether the port should have autoneg enabled before configuring fec.
        It returns true if the port supports autoneg and is pam4.
        :param port: A dut port, i.e. 'Ethernet28'
        :param speed: The speed to be configured on the port (used to check if the port is pam4).
        :param interface_width: The interface width to be configured on the port (used to check if the port is pam4).
        :return: A boolean stating whether the port should have autoneg enabled before configuring fec
        """
        return port in self.ports_support_autoneg and self.is_port_pam4(interface_width, speed)

    def pop_autoneg_enabled_from_cleanup_list(self, tested_ports, cleanup_list):
        """
        As part of the test cleanup, we want to set the fec configurations of dac and pam4 ports. To do that,
        autoneg must be enabled. In order to return autoneg to its original state, we call this function to remove
        enable autoneg commands from the cleanup list that will be executed at the end of the test.
        :param tested_ports: ports that were used during the test
        :param cleanup_list: cleanup_list containing commands that will eb executed at the end of the test
        """
        logger.info("Deleting enable autoneg commands from fec cleanup, so ports have autoneg disabled at the end of "
                    "the test")
        for port in tested_ports:
            cleanup_autoneg_enabled_entry = (
                self.cli_objects.dut.interface.config_auto_negotiation_mode, (port, "enabled"))
            if cleanup_autoneg_enabled_entry in cleanup_list:
                cleanup_list.remove(cleanup_autoneg_enabled_entry)

    def get_lb_interface_types_for_speed(self, lb, fec_mode, split_mode, speed):
        lb_supported_interface_types = set(self.fec_modes_speed_support[fec_mode][split_mode][speed])
        for port in lb:
            lb_supported_interface_types.intersection_update(self.mlxlink_supported_speeds[port][speed])
        return list(lb_supported_interface_types)

    def get_lb_config_for_fec_mode(self, lb, fec_mode, split_mode):
        """
        The function returns a tuple (speed, interface type) that is supported on both lb ports, in this fec and split
        modes
        :return: A tuple (speed, interface type) that is supported on both lb ports, in this fec and split modes,
        if no such tuple is found, it returns None, None
        """

        mutual_speed_options = self.get_lb_speeds_option_for_fec_mode(lb, split_mode, fec_mode,
                                                                      self.fec_modes_speed_support)
        random.shuffle(mutual_speed_options)
        for speed in mutual_speed_options:
            interface_types_for_speed = self.get_lb_interface_types_for_speed(lb, fec_mode, split_mode, speed)
            if interface_types_for_speed:
                return speed, random.choice(interface_types_for_speed)
        return None, None

    def get_lb_cable_mutual_speeds(self, lb):
        first_port_speeds = set(self.mlxlink_supported_speeds[lb[0]].keys())
        second_port_speeds = set(self.mlxlink_supported_speeds[lb[1]].keys())
        return first_port_speeds.intersection(second_port_speeds)

    def is_copper_cable(self, port):
        """
        The function determines whether the port is using a copper (dac) cable
        :return: A boolean stating if the port uses a copper (dac) cable or not
        """
        return self.is_simx or port in self.ports_support_autoneg
