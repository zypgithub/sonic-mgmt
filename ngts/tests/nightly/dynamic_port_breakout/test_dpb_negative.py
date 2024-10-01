import allure
import pytest
import random
import re
import copy
from retry.api import retry_call
from ngts.tests.nightly.dynamic_port_breakout.conftest import all_breakout_options, logger, is_splittable, \
    compare_actual_and_expected_speeds, get_mutual_breakout_modes, send_ping_and_verify_results, \
    set_dpb_conf, verify_ifaces_speed_and_status, verify_no_breakout
from ngts.tests.nightly.conftest import cleanup


class TestDPBNegative:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, engines,
              cli_objects, ports_breakout_modes,
              dut_ports_default_speeds_configuration, tested_modes_lb_conf, sw_control_ports):
        self.topology_obj = topology_obj
        self.dut_engine = engines.dut
        self.cli_object = cli_objects.dut
        self.ports_breakout_modes = ports_breakout_modes
        self.dut_ports_default_speeds_configuration = dut_ports_default_speeds_configuration
        self.tested_modes_lb_conf = tested_modes_lb_conf
        self.sw_control_ports = self.cli_object.im.sw_controlled_aoc_cables(sw_control_ports)

    @allure.title('Dynamic Port Breakout negative test: breakout on unbreakable port')
    def test_breakout_unbreakable_ports(self):
        """
        try break a unbreakable port and validate the breakout failed.
        :return:  raise assertion error if expected output is not matched
        """
        try:
            breakout_mode, lb = random.choice(list(self.tested_modes_lb_conf.items()))
            unsplittable_ports_list = self.get_unsplittable_ports_list(self.sw_control_ports)
            if len(unsplittable_ports_list) == 0:
                pytest.skip("Setup has no unsplittable ports to test breakout on - test is ignored")
            unsplittable_port = [random.choice(unsplittable_ports_list)]
            with allure.step(f'Verify breakout mode: {breakout_mode} on unsplittable port: {unsplittable_port} Fails'):
                self.verify_negative_breakout_configuration(unsplittable_port, breakout_mode)
        except Exception as e:
            raise e

    @allure.title('Dynamic Port Breakout negative test: unsupported breakout mode')
    def test_unsupported_breakout_mode(self, cleanup_list):
        """
        This test case will set unsupported breakout mode on a port,
        then will verify that wrong configuration is not applied,
        and check link-state (split port are up and there’s no traffic loss)
        :return: raise assertion error if expected output is not matched
        """
        try:
            breakout_mode, lb = random.choice(list(self.tested_modes_lb_conf.items()))
            mutual_breakout_modes = set(get_mutual_breakout_modes(self.ports_breakout_modes, lb))
            for port in lb:
                curr_breakout_mode = self.cli_object.interface.get_interface_current_breakout_mode(port)
                mutual_breakout_modes.add(curr_breakout_mode)
            unsupported_breakout_mode = random.choice(list(all_breakout_options.difference(mutual_breakout_modes)))
            with allure.step(f'Verify unsupported breakout mode {unsupported_breakout_mode} '
                             f'on ports {lb} fails as expected'):
                self.verify_negative_breakout_configuration(lb, unsupported_breakout_mode)
            send_ping_and_verify_results(self.topology_obj, self.dut_engine, cleanup_list, lb_list=[lb])
        except Exception as e:
            raise e

    @allure.title('Dynamic Port Breakout negative test: Wrong breakout removal from breakout port')
    def test_ports_breakout_after_wrong_removal(self, cleanup_list):
        """
        configure breakout on loopback than try to unbreak the loopback
        by configure unbreakout mode on the wrong ports.
        see if ports are still up after wrong removal tryout,
        then check that correct removal succeeded.
        :return: Raise assertion error if validation failed
        """
        breakout_mode, lb = random.choice(list(self.tested_modes_lb_conf.items()))
        unbreakout_port_mode = self.ports_breakout_modes[lb[0]]['default_breakout_mode']
        with allure.step(f'Configure breakout mode: {breakout_mode} on loopback: {lb}'):
            breakout_ports_conf = set_dpb_conf(self.dut_engine, self.cli_object,
                                               self.ports_breakout_modes,
                                               cleanup_list=cleanup_list,
                                               conf={breakout_mode: lb},
                                               original_speed_conf=self.dut_ports_default_speeds_configuration)
        ports_list_after_breakout = list(breakout_ports_conf.keys())

        with allure.step(f'Verify ports {ports_list_after_breakout} are up after breakout'):
            verify_ifaces_speed_and_status(self.cli_object, self.dut_engine, breakout_ports_conf)

        breakout_port_list = copy.deepcopy(ports_list_after_breakout)
        for port in lb:
            breakout_port_list.remove(port)
        breakout_port = random.choice(breakout_port_list)
        err_msg = rf"\[ERROR\] {breakout_port} interface is NOT present in BREAKOUT_CFG table of CONFIG DB"
        with allure.step(f'Verify unbreak out with mode {unbreakout_port_mode} '
                         f'on breakout port {breakout_port} failed as expected'):
            self.verify_breakout_on_port_failed(breakout_port, unbreakout_port_mode, err_msg)

        with allure.step(f'Verify ports {ports_list_after_breakout} are up after wrong breakout removal'):
            retry_call(self.cli_object.interface.check_ports_status,
                       fargs=[ports_list_after_breakout],
                       tries=2, delay=2, logger=logger)

        with allure.step(f'Remove breakout from ports: {lb} with mode {unbreakout_port_mode}'):
            cleanup(cleanup_list)

        with allure.step('Verify breakout ports were removed correctly'):
            verify_no_breakout(self.cli_object, breakout_ports_conf, tested_conf={breakout_mode: lb})

    def verify_negative_breakout_configuration(self, ports_list, breakout_mode):
        with allure.step(f'Get speed configuration of ports {ports_list} before breakout'):
            pre_breakout_speed_conf = self.cli_object.interface.get_interfaces_speed(ports_list)
        err_msg = r"\[ERROR\]\s+Target\s+mode\s+.*is\s+not\s+available\s+for\s+the\s+port\s+{}"
        with allure.step(f'Verify breakout mode {breakout_mode} on ports {ports_list} fails as expected'):
            for port in ports_list:
                self.verify_breakout_on_port_failed(port, breakout_mode, err_msg.format(port))
        with allure.step(f'Get speed configuration of ports {ports_list} after breakout'):
            post_breakout_speed_conf = self.cli_object.interface.get_interfaces_speed(ports_list)
        compare_actual_and_expected_speeds(pre_breakout_speed_conf, post_breakout_speed_conf)

    def get_unsplittable_ports_list(self, ports_to_exclude=None):
        """
        :param ports_to_exclude: list of ports to be excluded from dpb test case
        :return: a list of ports on dut which doesn't support any breakout mode
        """
        unsplittable_ports = []
        for port_alias, port_name in self.topology_obj.ports.items():
            if ports_to_exclude and port_name in ports_to_exclude:
                continue
            if port_alias.startswith("dut") and "splt" not in port_alias and \
                    not is_splittable(self.ports_breakout_modes, port_name):
                unsplittable_ports.append(port_name)
        return unsplittable_ports

    def verify_breakout_on_port_failed(self, port, breakout_mode, err_msg):
        """
        :param port: i.e, 'Ethernet8'
        :param breakout_mode: i.e., '4x50G[40G,25G,10G,1G]'
        :param err_msg: a regex expression
        :return: raise error if error message was not in output after breakout
        """
        with allure.step(f'Verify breakout mode {breakout_mode} on port {port} '
                         f'failed as expected with error message: {err_msg}'):
            output = self.cli_object.interface.configure_dpb_on_port(port, breakout_mode,
                                                                     expect_error=True, force=False)
            if not re.search(err_msg, output, re.IGNORECASE):
                raise AssertionError(f"Expected breakout mode {breakout_mode} on port {port} "
                                     f"to failed with error msg: {err_msg}, actual output: {output}")
