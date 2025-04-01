import time
import re

import allure
import pytest

from retry.api import retry_call
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.platform.Platform import Platform
from multiprocessing import Process

logger = logging.getLogger()


@pytest.mark.eth0
@pytest.mark.system
def test_interface_eth0_enable_disable(engines, topology_obj, serial_engine):
    """
    Connect via serial port, verify eth0 enable by default, can be disabled and enable it back

    flow:
    1. Verify eth0 is up and can ping
    2. Disable interface, check it’s down and not reachable
    3. Negative test it  with random value and verify error
    4. Unset it back and verify
    """

    try:
        mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
        mgmt_port = Port(mgmt_port_name)
        serial_engine = topology_obj.players['dut_serial']['engine']
        with allure.step('Run show command on mgmt port and verify that each field has an appropriate value'):
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                mgmt_port.interface.link.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_UP).verify_result()

        with allure.step('Negative validation'):
            mgmt_port.interface.link.state.set(op_param_name='invalid_value', apply=False).verify_result(False)

            logger.info('Check port status, should be up')
            check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                mgmt_port.interface.link.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_UP).verify_result()

        with allure.step('Set mgmt port down and check the state updated accordingly'):
            mgmt_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True,
                                               ask_for_confirmation=True, dut_engine=serial_engine).verify_result()

            logger.info('Check port status, should be down')
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                mgmt_port.interface.link.show(dut_engine=serial_engine)).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_DOWN).verify_result()
    finally:
        with allure.step('Unset mgmt port and make sure the port state is up and reachable'):
            mgmt_port.interface.link.state.unset(apply=True, ask_for_confirmation=True,
                                                 dut_engine=serial_engine).verify_result()
            logger.info('Check port status, should be up')
            check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)

            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                mgmt_port.interface.link.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_UP).verify_result()


@pytest.mark.cumulus
@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_interface_eth0_speed_duplex_autoneg(engines, devices, topology_obj):
    """
    Verify speed, duplex, autoneg configuration parameters can be changed

    flow:
    1. Check default values
    2. Try to set autoneg to off
    3. Negative testing for speed, duplex, autoneg
    4. Set duplex to half on default speed 1G
    5. Set speed to not default with supported duplex, verify changes via ping
    6. Set autoneg to on and validate changes
    7. Try to set all speeds from list supported with all supported duplex
    8. Unset speed, validate changes
    """

    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    with allure.step('Run show command on mgmt port and verify default values'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            mgmt_port.interface.link.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_SPEED,
                                                          expected_value="1G")

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_DUPLEX,
                                                          expected_value="full")

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_AUTO_NEGOTIATE,
                                                          expected_value="on")

    with allure.step(f'Negative validation with auto neg, {IbInterfaceConsts.LINK_AUTO_NEGOTIATE} must be on with default 1G speed'):
        mgmt_port.interface.link.set(op_param_name='auto_negotiate', op_param_value='off',
                                     apply=True).verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)

    with allure.step('Negative validation with invalid value for duplex'):
        mgmt_port.interface.link.set(op_param_name='duplex', op_param_value='a', apply=False).verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)

    with allure.step('Negative validation with invalid value speed'):
        mgmt_port.interface.link.set(op_param_name='speed', op_param_value='50F', apply=False).verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)

    '''with allure.step('Negative validation with half duplex and default speed 1G'):
        mgmt_port.interface.link.duplex.set(value='half', apply=True).verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)'''

    with allure.step('Set all supported speeds with all supported duplex'):
        list_supported_speeds = devices.dut.supported_eth0_speeds
        list_supported_duplex = devices.dut.supported_eth0_duplex
        for speed in list_supported_speeds:
            # Only allow full and half duplex if the speed is "10M" or "100M"
            if speed in ["10M", "100M"]:
                applicable_duplex = list_supported_duplex
            else:
                applicable_duplex = ["full"]  # For other speeds, only "full" duplex is applicable

            for duplex in applicable_duplex:
                mgmt_port.interface.link.set(op_param_name='speed', op_param_value=speed, apply=True,
                                             ask_for_confirmation=True).verify_result()
                result = mgmt_port.interface.link.set(op_param_name='duplex', op_param_value=duplex,
                                                      apply=True, ask_for_confirmation=True)
                check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
                check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
                Port.wait_for_port_state(mgmt_port, "up")

                if not result:
                    SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                                    apply_config, engines.dut, True).verify_result()

                wait_for_param_changed(mgmt_port, IbInterfaceConsts.LINK_SPEED, speed)
                wait_for_param_changed(mgmt_port, IbInterfaceConsts.LINK_DUPLEX, duplex)

    with allure.step('Set autoneg to off'):
        mgmt_port.interface.link.set(op_param_name=IbInterfaceConsts.LINK_AUTO_NEGOTIATE, op_param_value='off', apply=True,
                                     ask_for_confirmation=True).verify_result()
        check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        Port.wait_for_port_state(mgmt_port, "up")
        wait_for_param_changed(mgmt_port, IbInterfaceConsts.LINK_AUTO_NEGOTIATE, IbInterfaceConsts.LINK_AUTO_NEG_OFF)

    with allure.step('Run show command on mgmt port and verify default values after unset'):
        mgmt_port.interface.link.unset(op_param=IbInterfaceConsts.LINK_AUTO_NEGOTIATE, apply=True, ask_for_confirmation=True).verify_result()
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        Port.wait_for_port_state(mgmt_port, "up")

        wait_for_param_changed(mgmt_port, IbInterfaceConsts.LINK_AUTO_NEGOTIATE, IbInterfaceConsts.LINK_AUTO_NEG_ON)

        mgmt_port.interface.link.unset(op_param='duplex', apply=True, ask_for_confirmation=True).verify_result()

        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        wait_for_param_changed(mgmt_port, IbInterfaceConsts.LINK_DUPLEX, 'full')

        mgmt_port.interface.link.unset(op_param='speed', apply=True, ask_for_confirmation=True).verify_result()
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        wait_for_param_changed(mgmt_port, IbInterfaceConsts.LINK_SPEED, "1G")


@pytest.mark.cumulus
@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_interface_eth0_mtu(engines, topology_obj):
    """
    Verify default mtu configuration(1500), check that we can configure possible values(1280-9216),
    negative check(1279, 9000), check changes, unset it to default

    flow:
    1. Check default values
    2. Negative testing
    3. Configure possible mtu
    4. Unset mtu, check default value
    """

    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    with allure.step('Run show command on mgmt port and verify default values'):
        wait_for_mtu_changed(mgmt_port, 1500)

    with allure.step('Negative validation with not supported for eth mtu 256'):
        mgmt_port.interface.link.set(op_param_name='mtu', op_param_value='256').verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
    with allure.step('Negative validation with not supported for eth mtu 9218'):
        result_obj = mgmt_port.interface.link.set(op_param_name='mtu', op_param_value='9218', apply=False)
        assert "Valid range for mtu is" in result_obj.get_info(False), "Set of invalid mtu should fail"
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        wait_for_mtu_changed(mgmt_port, 1500)
    with allure.step('Set validation with supported for eth mtu 9000'):
        mgmt_port.interface.link.set(op_param_name='mtu', op_param_value='9000',
                                     apply=True, ask_for_confirmation=True).verify_result()
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        wait_for_mtu_changed(mgmt_port, 9000)

    with allure.step('Unset mtu validation'):
        mgmt_port.interface.link.unset(op_param='mtu', apply=True, ask_for_confirmation=True).verify_result()
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        wait_for_mtu_changed(mgmt_port, 1500)


@pytest.mark.cumulus
@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_interface_eth0_description(engines, topology_obj):
    """
    Verify default description on mgmt interface, configure, check changes,

    flow:
    1. Check default values
    2. Configure possible description, and check changes
    3. Negative testing
    4. Unset description, check default value
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    with allure.step('Run show command on mgmt port and verify default description'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        assert IbInterfaceConsts.DESCRIPTION not in output_dictionary.keys(), \
            "Expected not to have description field after unset command, but we still have this field."

    with allure.step('Set description with spaces on mgmt port'):
        mgmt_port.interface.set(op_param_name='description', op_param_value='"{0} description"'.format(mgmt_port_name),
                                apply=True).verify_result()
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.DESCRIPTION,
                                                          expected_value='{0} description'.format(mgmt_port_name))

    with allure.step('Set possible description on mgmt port'):
        mgmt_port.interface.set(op_param_name='description', op_param_value='"nvosdescription"',
                                apply=True).verify_result()
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.DESCRIPTION,
                                                          expected_value='nvosdescription')

    with allure.step('Unset possible description on mgmt port'):
        mgmt_port.interface.unset(op_param='description', apply=True).verify_result()
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        assert IbInterfaceConsts.DESCRIPTION not in output_dictionary.keys(), \
            "Expected not to have description field after unset command, but we still have this field."


@pytest.mark.cumulus
@pytest.mark.eth0
@pytest.mark.system
def test_interface_eth0_ip_address(engines, topology_obj, serial_engine):
    """
    Verify can configure ipv address, switch ip updated by dhcp

    flow:
    1. Get ip/mask from switch, verify it’s reachable by ping
    2. Negative testing for ipv4 and prefix, instead of ip only “dhcp”
    3. Disable ipv4 dhcp, verify it’s disabled, we can’t ping
    4. Configure static ip for this switch, check it by show command, ping
    5. Unset ipv4, dhcp, validate in show command and ping
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    switch_ip = engines.dut.ip

    try:
        with allure.step('Run show command on mgmt port and verify default description'):
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
                mgmt_port.interface.ip.show()).get_returned_value()

            validate_interface_ip_address(switch_ip, output_dictionary, True)

        with allure.step('Negative validation for {0} ip'.format(mgmt_port_name)):
            res = mgmt_port.interface.ip.address.set(op_param_name='aa', apply=False, ask_for_confirmation=True)
            res.ignore_result()
            assert not res.result or "is not a" in res.returned_value, \
                "The operation succeeded while it is expected to fail"

        with allure.step('Disable dhcp, check mgmt port unreachable'):
            serial_engine.serial_engine.sendline("nv set interface {} ip dhcp-client state disabled".format(mgmt_port_name))
            serial_engine.serial_engine.sendline("nv config apply")
            serial_engine.serial_engine.expect("Are you sure?", timeout=120)
            serial_engine.serial_engine.sendline("y")
            serial_engine.serial_engine.expect("applied", timeout=120)

            logger.info('Check port status, should be down')
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)

        with allure.step('Select random ipv4 and set it'):
            ip_address = Tools.IpTool.select_random_ipv4_address().verify_result()
            serial_engine.serial_engine.sendline("nv set interface {0} ip address {1}".format(mgmt_port_name, ip_address))
            serial_engine.serial_engine.sendline("nv config apply")
            serial_engine.serial_engine.expect("Are you sure?", timeout=120)
            serial_engine.serial_engine.sendline("y")
            serial_engine.serial_engine.expect("applied", timeout=120)

            logger.info('Check port status, should be down')
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
            serial_engine.serial_engine.sendline("nv show interface {0}".format(mgmt_port_name))
            serial_engine.serial_engine.expect(ip_address, timeout=120)
    finally:
        with allure.step('Unset ipv4 and dhcp and check port reachable'):
            serial_engine.serial_engine.sendline("nv unset interface {0}".format(mgmt_port_name))
            serial_engine.serial_engine.sendline("nv config apply")
            serial_engine.serial_engine.expect("Are you sure?", timeout=120)
            serial_engine.serial_engine.sendline("y")
            serial_engine.serial_engine.expect("applied", timeout=120)

            logger.info('Check port status, should be up')
            check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
            serial_engine.serial_engine.sendline("nv show interface {0}".format(mgmt_port_name))
            serial_engine.serial_engine.expect(switch_ip, timeout=120)


@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_interface_eth0_show_dhcp(engines, topology_obj):
    """
    Verify all default fields in nv show interface eth0 ip ipv4 dhcp-client and ipv6 dhcp-client

    flow:
    1. Check all fields are exist in nv show interface eth0 ip ipv4 dhcp-client
    2. Check all fields exist in nv show interface eth0 ip ipv6 dhcp-client
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    with allure.step('Run show command on mgmt port and verify default description'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            mgmt_port.interface.ip.show()).get_returned_value()

        with allure.step("Validate all expected fields in show output"):
            Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, ["dhcp-client", "dhcp-client6"]) \
                .verify_result()
            logging.info("All expected fields were found")


@pytest.mark.cumulus
@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_interface_eth0_dhcp_hostname(engines, topology_obj, serial_engine):
    """
    Verify switch receive hostname by dhcp

    flow:
    1. Check hostname received by dhcp, validate it’s same in show system and iblinkinfo command, field lease yes
    2. Disable dhcp, unset hostname, verify it’s nvos, is running no, no lease field
    3. Disable dhcp set-hostname, verify changed for ipv4 and ipv6 dhcp
    4. Enable dhcp, check we didn’t receive hostname
    5. Unset set-hostname and check we received hostname as we have on start of the test, configuration for ipv4 and ipv6 dhcp same, can ping
    """
    expect_timeout = 30
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    system = System()

    try:
        with allure.step('Run show ip dhcp command and check default values and dhcp hostname'):
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
                mgmt_port.interface.ip.dhcp_client.show()).get_returned_value()

            noga_query_data = topology_obj.players['dut']['attributes'].noga_query_data['attributes']

            system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()

            dhcp_hostname = noga_query_data['Specific']['dhcp_hostname']
            dhcp_hostname = dhcp_hostname if dhcp_hostname else noga_query_data['Common']['Name']
            assert dhcp_hostname, "No dhcp_hostname received from noga"

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name='has-lease',
                                                              expected_value='yes').verify_result()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name='is-running',
                                                              expected_value='yes').verify_result()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name='set-hostname',
                                                              expected_value='enabled').verify_result()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name='state',
                                                              expected_value='enabled').verify_result()

            assert dhcp_hostname in system_output['hostname'], "hostname wasn't changed"

        with allure.step('Disable dhcp and unset hostname, check port down and not reachable'):
            serial_engine.serial_engine.sendline("nv set interface {} ip dhcp-client state disabled".format(mgmt_port_name))
            serial_engine.serial_engine.sendline("nv config apply")
            serial_engine.serial_engine.expect("Are you sure?", timeout=expect_timeout)
            serial_engine.serial_engine.sendline("y")
            serial_engine.serial_engine.expect("applied", timeout=expect_timeout)

            logger.info('Check port status, should be down')
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)

            serial_engine.serial_engine.sendline("nv show interface {} ip dhcp-client".format(mgmt_port_name))
            serial_engine.serial_engine.expect("state         disabled", timeout=expect_timeout)

        with allure.step('Disable dhcp set-hostname, check port down and not reachable'):
            serial_engine.serial_engine.sendline("nv set interface {} ip dhcp-client set-hostname disabled".format(mgmt_port_name))
            serial_engine.serial_engine.sendline("nv config apply")
            serial_engine.serial_engine.expect("Are you sure?", timeout=expect_timeout)
            serial_engine.serial_engine.sendline("y")
            serial_engine.serial_engine.expect("applied", timeout=expect_timeout)

            logger.info('Check port status, should be down')
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
            serial_engine.serial_engine.sendline("nv show interface {} ip dhcp-client".format(mgmt_port_name))
            serial_engine.serial_engine.expect("state         disabled", timeout=expect_timeout)
            serial_engine.serial_engine.sendline("nv show interface {} ip dhcp-client6".format(mgmt_port_name))
            serial_engine.serial_engine.expect("state         disabled", timeout=expect_timeout)

        with allure.step('Set hostname and enable dhcp, check hostname not changed, check port up'):
            serial_engine.serial_engine.sendline("nv set system hostname {}".format(SystemConsts.HOSTNAME))
            serial_engine.serial_engine.sendline("nv config apply")
            serial_engine.serial_engine.expect("Are you sure?", timeout=expect_timeout)
            serial_engine.serial_engine.sendline("y")
            serial_engine.serial_engine.expect("applied", timeout=expect_timeout)
            logger.info('Check port status, should be down')
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
            serial_engine.serial_engine.sendline("nv set interface {} ip dhcp-client state enabled".format(mgmt_port_name))
            serial_engine.serial_engine.sendline("nv config apply")
            serial_engine.serial_engine.expect("Are you sure?", timeout=expect_timeout)
            serial_engine.serial_engine.sendline("y")
            serial_engine.serial_engine.expect("applied", timeout=expect_timeout)

            logger.info('Check port status, should be up')
            check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)

            dhcp_output = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
                mgmt_port.interface.ip.dhcp_client.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=dhcp_output, field_name='state',
                                                              expected_value='enabled').verify_result()
    finally:
        with allure.step('Unset dhcp, , check port up'):
            mgmt_port.interface.ip.dhcp_client.unset(apply=True, ask_for_confirmation=True).verify_result()
            logger.info('Check port status, should be up')
            check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)

            dhcp_output = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
                mgmt_port.interface.ip.dhcp_client.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=dhcp_output,
                                                              field_name='state',
                                                              expected_value='enabled').verify_result()
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=dhcp_output,
                                                              field_name='set-hostname',
                                                              expected_value='enabled').verify_result()

        with allure.step('Check hostname received by dhcp'):
            system.unset(op_param=SystemConsts.HOSTNAME, apply=True, ask_for_confirmation=True, dut_engine=serial_engine)
            wait_for_hostname_changed(system, dhcp_hostname)


@pytest.mark.cumulus
@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_mgmt_interface_default(engines, topology_obj):
    """
    Verify default fields, stats, logs

    flow:
    1. Check default fields
    2. Check mgmt port ip is reachable
    3. Check logs
    4. Check stats
    """
    system = System(None)
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)

    with allure.step('Run show command on mgmt port and verify default values'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        field_to_check = [IbInterfaceConsts.TYPE, IbInterfaceConsts.LINK,
                          IbInterfaceConsts.IFINDEX, IbInterfaceConsts.IP]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()

    with allure.step('Verify mgmt interface is reachable'):
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)

    with allure.step('Check logs for mgmt interface exist'):
        show_output_lines = system.log.file.show(op_param=" | grep '" + mgmt_port_name + "'", output_format="").splitlines()
        assert len(show_output_lines) > 0, "Mgmt port {} not found in system log".format(mgmt_port_name)

    with allure.step('Check stats'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_stats_output_to_dictionary(
            mgmt_port.interface.link.stats.show()).get_returned_value()
        field_to_check = [IbInterfaceConsts.LINK_STATS_CARRIER_TRANSITION, IbInterfaceConsts.LINK_STATS_IN_BYTES,
                          IbInterfaceConsts.LINK_STATS_IN_DROPS, IbInterfaceConsts.LINK_STATS_IN_ERRORS,
                          IbInterfaceConsts.LINK_STATS_IN_PKTS, IbInterfaceConsts.LINK_STATS_OUT_BYTES,
                          IbInterfaceConsts.LINK_STATS_OUT_DROPS, IbInterfaceConsts.LINK_STATS_OUT_ERRORS,
                          IbInterfaceConsts.LINK_STATS_OUT_PKTS]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()


@pytest.mark.cumulus
@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_mgmt_interface_dhcpv6_ztp(engines, topology_obj):
    """
    Test to verify ztp dhcpv6 vendor class bug https://redmine.mellanox.com/issues/3963391

    flow:
    1. Run tcpdump and catch 5 packets dhcpv6 ztp vendor class
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)

    with allure.step('Run tcpdump and catch dhcpv6 ztp vendor class'):
        tcpdump_output = Tools.IpTool.run_tcpdump(engines.dut, mgmt_port_name,
                                                  filter='port 546 or port 547 -e -c 5 -n -vv')
        match = re.search(r"(\d+) packets received by filter", tcpdump_output)
        packets_received = int(match.group(1))
        assert packets_received >= 5, f"Only {packets_received} packets received, less than 5"


@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_mgmt_interface_dhcp_option_60(engines, topology_obj):
    """
    Test to verify availability of option 60(Vendor class) in dhcp

    flow:
    1. Start a subprocess to start monitoring tcpdump to validate option 60
    2. Renew DHCP so that packet transfers starts happening
    """

    platform = Platform()
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    output = OutputParsingTool.parse_json_str_to_dictionary(platform.show()).get_returned_value()
    product_name = output['product-name']
    hostname = engines.dut.run_cmd("hostname")
    regex = r"Hostname.*{}.*Vendor-Class.*{}".format(hostname, product_name)

    try:
        with allure.step("Create a separate process to run tcpdump and validate option 60 in packets"):
            tcpdump_process = Process(target=run_tcpdump_validate_option_60,
                                      args=(engines.dut, mgmt_port_name, regex))
            tcpdump_process.start()

        with allure.step("Renew DHCP to initiate packet transfers"):
            mgmt_port.interface.ip.dhcp_client.action('renew')

    finally:
        with allure.step("Combine with tcpdump process to finish gracefully"):
            tcpdump_process.join()
            assert tcpdump_process.exitcode == 0, "Vendor-Class Identifier (Option 60) not found in dhcp packets"


@pytest.mark.eth0
@pytest.mark.system
@pytest.mark.simx
def test_mgmt_interface_dhcp_option_60_conf_file(engines):
    """
    Test to verify availability of option 60(Vendor class identifier) in dhcp

    flow:
    1. Check vendor class identifier (DHCP option 60) is present in dh client conf file
    """

    with allure.step('Open dh client conf file and validate option 60'):
        dh_client_conf = engines.dut.run_cmd("cat " + SystemConsts.DH_CLIENT_CONF_FILE)
        assert "vendor-class-identifier" in dh_client_conf, "Vendor class identifier not present in dh client conf file"


def run_tcpdump_validate_option_60(dut, mgmt_port_name, regex):
    with allure.step('Run tcpdump and validate option 60'):
        retry_call(validate_dhcp_option_60_tcpdump, [dut, mgmt_port_name, regex],
                   exceptions=AssertionError, tries=5, delay=0)


def validate_dhcp_option_60_tcpdump(dut, mgmt_port_name, regex):
    tcpdump_output = Tools.IpTool.run_tcpdump(dut, mgmt_port_name, filter='port 67 or port 68 -c 10 -n -vv')
    # split packets
    tcp_dumps = tcpdump_output.split("Client-Ethernet-Address")
    for tcpdump in tcp_dumps:
        if re.search(regex, tcpdump, re.DOTALL):
            return
    assert False, "Vendor-Class Identifier (Option 60) not found in dhcp packets"


def validate_interface_ip_address(address, output_dictionary, validate_in=True):
    """

    :param address: ip address (could be ipv4 or ipv6)
    :param output_dictionary: the output after running nv show interface ib0 ip
    :param validate_in: True after running set cmd, False after running unset
    """
    with allure.step('check the address field is updated as expected'):
        output_dictionary = str(output_dictionary['address'].keys())
        if validate_in:
            assert address in output_dictionary, "address not found: {add}".format(add=address)
        if not validate_in:
            assert address not in output_dictionary, "address found and should be deleted: {add}".format(add=address)


@retry(Exception, tries=10, delay=2)
def wait_for_mtu_changed(port_obj, mtu_to_verify):
    with allure.step("Waiting for mgmt port mtu changed to {}".format(mtu_to_verify)):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            port_obj.interface.link.show()).get_returned_value()
        current_mtu = output_dictionary[IbInterfaceConsts.LINK_MTU]
        assert current_mtu == mtu_to_verify, "Current mtu {} is not as expected {}".format(current_mtu, mtu_to_verify)


@retry(Exception, tries=15, delay=2)
def wait_for_hostname_changed(system, dhcp_hostname):
    with (allure.step("Waiting for system hostname changed to {}".format(dhcp_hostname))):
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        assert dhcp_hostname in system_output[SystemConsts.HOSTNAME], "hostname wasn't changed"


@retry(Exception, tries=25, delay=2)
def wait_for_param_changed(port_obj, param, param_to_verify):
    with allure.step(f"Waiting for {param} changed to {param_to_verify}"):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            port_obj.interface.link.show()).get_returned_value()
        current_param = output_dictionary[f'{param}']
        assert current_param == param_to_verify, f"Current {current_param} is not as expected {param_to_verify}"
