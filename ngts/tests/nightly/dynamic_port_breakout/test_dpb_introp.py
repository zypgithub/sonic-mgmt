import allure
import pytest
import random
import re
from retry.api import retry_call
from ngts.cli_util.cli_constants import SonicConstant
from ngts.tests.nightly.conftest import save_configuration_and_reboot, cleanup
from ngts.tests.nightly.dynamic_port_breakout.conftest import get_ports_list_from_loopback_tuple_list, \
    verify_no_breakout, set_dpb_conf, verify_ifaces_speed_and_status, \
    send_ping_and_verify_results, build_remove_dpb_conf
from ngts.helpers.dependencies_helpers import DependenciesBase


class TestDPBInterop(DependenciesBase):

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, engines,
              cli_objects, ports_breakout_modes,
              dut_ports_default_speeds_configuration, tested_modes_lb_conf):
        self.topology_obj = topology_obj
        self.dut_engine = engines.dut
        self.cli_object = cli_objects.dut
        self.ports_breakout_modes = ports_breakout_modes
        self.dut_ports_default_speeds_configuration = dut_ports_default_speeds_configuration
        self.tested_modes_lb_conf = tested_modes_lb_conf

    @pytest.mark.reboot_reload
    @allure.title('Dynamic Port Breakout with Dependencies')
    def test_dpb_configuration_interop(self, cleanup_list,
                                       dependency_list=["portchannel", "vlan", "ip"],
                                       reboot_type=None):
        """
        self.tested_modes_lb_conf = a dictionary of the tested configuration,
        i.e breakout mode and ports list which breakout mode will be applied on
        {'2x50G[40G,25G,10G,1G]': ('Ethernet212', 'Ethernet216'), '4x25G[10G,1G]': ('Ethernet228', 'Ethernet232')}

        This test case will set dependency configuration on a port,
        then will try to break out the port with/without force,
        then check link-state and dependencies on the split port
        :param dependency_list: list of features that will be configured before port breakout
        :return: raise assertion error if expected output is not matched
        """
        try:
            ports_list = get_ports_list_from_loopback_tuple_list(self.tested_modes_lb_conf.values())
            if not ports_list:
                pytest.skip(f'Skip TC as ports selected fot testing are SW control')
            ports_dependencies = self.set_dependencies(dependency_list, ports_list, cleanup_list)
            self.verify_breakout_without_force()
            breakout_ports_conf = self.verify_breakout_with_force(cleanup_list, dependency_list, ports_dependencies)
            reboot_type = random.choice(
                list(SonicConstant.REBOOT_TYPES.values())) if reboot_type is None else reboot_type
            self.reboot_and_check_functionality(cleanup_list, reboot_type, breakout_ports_conf)
            with allure.step(f'Cleanup breakout configuration from all ports'):
                cleanup(cleanup_list)
            with allure.step(f'Verify interfaces {ports_list} are in up state after breakout is removed'):
                retry_call(self.cli_object.interface.check_ports_status,
                           fargs=[ports_list],
                           tries=3, delay=10)
        except Exception as e:
            raise e

    def verify_breakout_without_force(self):
        """
        verify that breakout without force is failing as expected
        because of dependencies on ports
        :return: None, raise assertion error in case of failure
        """
        breakout_ports_conf = {}
        for breakout_mode, lb in self.tested_modes_lb_conf.items():
            for port in lb:
                output = self.verify_breakout_failed_due_dependency(breakout_mode, port)
                breakout_ports_conf.update(self.cli_object.interface.parse_added_breakout_ports(output))
        verify_no_breakout(self.cli_object, breakout_ports_conf, tested_conf=self.tested_modes_lb_conf)

    def verify_breakout_failed_due_dependency(self, breakout_mode, port):
        """
        Configure breakout_mode on port without force and verify that the breakout failed due the dependencies.
        :param breakout_mode: i.e. "4x25G[10G]"
        :param port: i.e. 'Ethernet212'
        :return: DPB command output, raise assertion error in case command didn't fail due the dependencies.
        """
        with allure.step(f'Configure breakout without force on port: {port}'):
            output = self.cli_object.interface.configure_dpb_on_port(port, breakout_mode,
                                                                     expect_error=True, force=False)
        self.verify_dependencies_in_output(output)
        return output

    @staticmethod
    def verify_dependencies_in_output(breakout_output):
        """
        verify that the breakout failed due the dependencies.
        :param breakout_output: the output from the breakout configuration command
        :return: None, raise assertion error in case of failure
        """
        # TODO: the spelling of "Dependencies" in the cli output is incorrect, there is a bug 3438231 for it
        #  to avoid loosing coverage, change the spelling back to the wrong one
        #  revert this change after the bug  is fixed
        err_msg = r"Depend.*\s+Exist\.\s+No\s+further\s+action\s+will\s+be\s+taken"
        with allure.step(f'Configure breakout without force fail with error: {err_msg}'):
            if not re.search(err_msg, breakout_output, re.IGNORECASE):
                raise AssertionError(f"Error message: {err_msg} was not found in breakout output")

    def verify_breakout_with_force(self, cleanup_list, dependency_list, ports_dependencies):
        """
        configure breakout mode with force and verify breakout is
        successful and dependencies were removed from ports.
        :param cleanup_list: a list of function to be called to cleanup test configuration
        :param dependency_list:  a list of features i.e. ['vlan', 'portchannel']
        :param ports_dependencies:  a dictionary with the ports configured dependencies information
        for example,
        {'Ethernet212': {'vlan': 'Vlan3730', 'portchannel': 'PortChannel0001'},
        'Ethernet216': {'vlan': 'Vlan3730', 'portchannel': 'PortChannel0002'},...}
        :return: a dictionary with the port configuration after breakout
        {'Ethernet216': '25G',
        'Ethernet217': '25G',...}
        """
        ports_w_dependencies_list = list(ports_dependencies.keys())
        with allure.step(f'Configure breakout with force on ports: {ports_w_dependencies_list}'):
            breakout_ports_conf = set_dpb_conf(self.dut_engine, self.cli_object,
                                               self.ports_breakout_modes, cleanup_list=cleanup_list,
                                               conf=self.tested_modes_lb_conf,
                                               original_speed_conf=self.dut_ports_default_speeds_configuration,
                                               force=True)
        verify_ifaces_speed_and_status(self.cli_object, self.dut_engine, breakout_ports_conf)
        self.verify_no_dependencies_on_ports(dependency_list, ports_dependencies)
        return breakout_ports_conf

    def reboot_and_check_functionality(self, cleanup_list, reboot_type, breakout_ports_conf):
        """
        :param cleanup_list: a list of function to be called to cleanup test configuration
        :param reboot_type: i.e reboot/warm-reboot/fast-reboot
        :param breakout_ports_conf: a dictionary with the port configuration after breakout
        {'Ethernet216': '25G',
        'Ethernet217': '25G',...}
        :return: raise assertion error in case validation failed after reboot
        """
        interfaces_list = list(breakout_ports_conf.keys())
        save_configuration_and_reboot(self.topology_obj, self.dut_engine, self.cli_object,
                                      interfaces_list, cleanup_list, reboot_type)
        send_ping_and_verify_results(self.topology_obj, self.dut_engine, cleanup_list,
                                     self.tested_modes_lb_conf.values())

    @allure.title('Dynamic Port remove breakout from breakout ports with dependencies')
    def test_remove_dpb_configuration_interop(self, cleanup_list, dependency_list=["portchannel", "vlan", "ip"]):
        """
        This test case will set dependency configuration on a split port,
        then will try to unsplit the port with/without force,
        then check link-state and dependencies on the port.
        :param dependency_list: list of features that will be configured before port breakout removal
        :return: raise assertion error if expected output is not matched
        """
        try:
            with allure.step(f'Configure breakout mode on ports: {self.tested_modes_lb_conf}'):
                breakout_ports_conf = set_dpb_conf(self.dut_engine, self.cli_object,
                                                   self.ports_breakout_modes,
                                                   cleanup_list=cleanup_list, conf=self.tested_modes_lb_conf,
                                                   original_speed_conf=self.dut_ports_default_speeds_configuration)
            ports_list = list(breakout_ports_conf.keys())
            if not ports_list:
                pytest.skip(f'Skip TC as ports selected fot testing are SW control')
            with allure.step(f'set dependencies on breakout ports: {ports_list}'):
                ports_dependencies = self.set_dependencies(dependency_list, ports_list, cleanup_list)
            self.verify_remove_breakout_without_force()
            self.verify_remove_breakout_with_force(cleanup_list, dependency_list,
                                                   ports_dependencies, breakout_ports_conf)

        except Exception as e:
            raise e

    def verify_remove_breakout_without_force(self):
        """
        verify remove breakout without force failed when port has dependencies configuration on it
        :return: raise assertion error in case validation failed
        """
        for breakout_mode, lb in self.tested_modes_lb_conf.items():
            for port in lb:
                self.verify_remove_breakout_failed_due_dependency(port)

    def verify_remove_breakout_failed_due_dependency(self, port):
        """
        configure un breakout mode and verify that it failed due to configured dependencies on port
        :param port: i.e, 'Ethernet212'
        :return: raise assertion error in case validation failed
        """
        breakout_ports_conf = {}
        default_breakout_mode = self.ports_breakout_modes[port]['default_breakout_mode']
        with allure.step(f'Verify remove breakout without force failed due dependencies configuration on port: {port}'):
            output = self.cli_object.interface.configure_dpb_on_port(port, default_breakout_mode,
                                                                     expect_error=True, force=False)
            breakout_ports_conf.update(self.cli_object.interface.parse_added_breakout_ports(output))
        self.verify_dependencies_in_output(output)
        breakout_ports = breakout_ports_conf.keys()
        self.verify_remove_breakout_failed(breakout_ports)

    def verify_remove_breakout_failed(self, breakout_ports):
        """
        check that port is still in breakout mode and all it's breakout ports in state up
        :param breakout_ports: a list of breakout ports
        :return: raise assertion error in case validation failed
        """
        with allure.step(f'Verify remove breakout without force failed and breakout ports: {breakout_ports} are up'):
            self.cli_object.interface.check_ports_status(breakout_ports, expected_status='up')

    def verify_remove_breakout_with_force(self, cleanup_list, dependency_list, ports_dependencies, breakout_ports_conf):
        """
        remove breakout configuration with force and validate all dependencies were removed from port
        :param cleanup_list: a list of function to be called to cleanup test configuration
        :param dependency_list: list of features that will be configured before port breakout removal
        :param ports_dependencies: a dictionary with the ports configured dependencies information
         i.e {'Ethernet212': {'vlan': 'Vlan3730', 'portchannel': 'PortChannel0001', 'ip': 10.10.10.1}, ...}
        :param breakout_ports_conf: a dictionary with the port configuration after breakout
        {'Ethernet216': '25G',
        'Ethernet217': '25G',..}
        :return: raise assertion error in case validation failed
        """
        remove_breakout_ports_conf = build_remove_dpb_conf(self.tested_modes_lb_conf, self.ports_breakout_modes)
        unbreakout_ports_conf = {}
        with allure.step('Configure remove breakout with force from ports'):
            for port_remove_breakout_ports_conf in remove_breakout_ports_conf:
                unbreakout_ports_conf.update(
                    set_dpb_conf(self.dut_engine, self.cli_object,
                                 self.ports_breakout_modes,
                                 cleanup_list=cleanup_list,
                                 conf=port_remove_breakout_ports_conf,
                                 original_speed_conf=self.dut_ports_default_speeds_configuration,
                                 force=True))
        with allure.step('Verify remove breakout succeeded and breakout ports no longer exist'):
            verify_no_breakout(self.cli_object, breakout_ports_conf, tested_conf=self.tested_modes_lb_conf)
        verify_ifaces_speed_and_status(self.cli_object, self.dut_engine, unbreakout_ports_conf)
        self.verify_no_dependencies_on_ports(dependency_list, ports_dependencies)
        send_ping_and_verify_results(self.topology_obj, self.dut_engine, cleanup_list,
                                     self.tested_modes_lb_conf.values())
        return breakout_ports_conf
