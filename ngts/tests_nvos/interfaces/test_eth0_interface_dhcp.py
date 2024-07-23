import pytest
import time
from retry import retry

from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


@pytest.mark.ib
def test_interface_eth0_enable_disable(engines, topology_obj):
    """
    Connect via serial port, verify eth0 enable by default, can be disabled and enable it back

    flow:
    1. Verify eth0 is up and can ping
    2. Disable interface, check it’s down and not reachable
    3. Negative test it  with random value and verify error
    4. Unset it back and verify
    """

    mgmt_port = MgmtPort('eth0')
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


@pytest.mark.ib
@pytest.mark.simx
def test_interface_eth0_speed_duplex_autoneg(engines):
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

    mgmt_port = MgmtPort('eth0')
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

    with allure.step('Negative validation with auto neg, auto-neg must be on with default 1G speed'):
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
        list_supported_speeds = ["10M", "100M"]
        list_supported_duplex = ["full", "half"]
        for speed in list_supported_speeds:
            for duplex in list_supported_duplex:
                mgmt_port.interface.link.set(op_param_name='speed', op_param_value=speed, apply=True,
                                             ask_for_confirmation=True).verify_result()

                time.sleep(5)
                Port.wait_for_port_state(mgmt_port, "up")

                result = mgmt_port.interface.link.set(op_param_name='duplex', op_param_value=duplex,
                                                      apply=True, ask_for_confirmation=True)
                time.sleep(5)

                if not result:
                    SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                                    apply_config, engines.dut, True).verify_result()

                output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                    mgmt_port.interface.link.show()).get_returned_value()
                Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                                  field_name=IbInterfaceConsts.LINK_SPEED,
                                                                  expected_value=speed).verify_result()
                Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                                  field_name=IbInterfaceConsts.LINK_DUPLEX,
                                                                  expected_value=duplex).verify_result()

    with allure.step('Set autoneg to off'):
        mgmt_port.interface.link.set(op_param_name='auto-negotiate', op_param_value='off', apply=True,
                                     ask_for_confirmation=True).verify_result()
        time.sleep(5)

    with allure.step('Run show command on mgmt port and verify default values after unset'):
        mgmt_port.interface.link.unset(op_param='auto-negotiate', apply=True, ask_for_confirmation=True).verify_result()

        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            mgmt_port.interface.link.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_AUTO_NEGOTIATE,
                                                          expected_value="on")

        mgmt_port.interface.link.unset(op_param='duplex', apply=True, ask_for_confirmation=True).verify_result()

        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            mgmt_port.interface.link.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_DUPLEX,
                                                          expected_value="full")

        mgmt_port.interface.link.unset(op_param='speed', apply=True, ask_for_confirmation=True).verify_result()

        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            mgmt_port.interface.link.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_SPEED,
                                                          expected_value="1G")


@pytest.mark.ib
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

    mgmt_port = MgmtPort('eth0')
    with allure.step('Run show command on mgmt port and verify default values'):
        wait_for_mtu_changed(mgmt_port, 1500)

    with allure.step('Negative validation with not supported for eth mtu 256'):
        mgmt_port.interface.link.set(op_param_name='mtu', op_param_value='256').verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
    with allure.step('Negative validation with not supported for eth mtu 9218'):
        result_obj = mgmt_port.interface.link.set(op_param_name='mtu', op_param_value='9218', apply=False)
        assert not result_obj.result and "Valid range is" in result_obj.info, "Set of invalid mtu should fail"
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


@pytest.mark.ib
@pytest.mark.simx
def test_interface_eth0_description(engines):
    """
    Verify default description on mgmt interface, configure, check changes,

    flow:
    1. Check default values
    2. Configure possible description, and check changes
    3. Negative testing
    4. Unset description, check default value
    """
    mgmt_port = MgmtPort('eth0')
    with allure.step('Run show command on mgmt port and verify default description'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        assert IbInterfaceConsts.DESCRIPTION not in output_dictionary.keys(), \
            "Expected not to have description field after unset command, but we still have this field."

    with allure.step('Set description with spaces on mgmt port'):
        mgmt_port.interface.set(op_param_name='description', op_param_value='"eth0 description"',
                                apply=True).verify_result()
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.DESCRIPTION,
                                                          expected_value='eth0 description')

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


@pytest.mark.ib
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
    mgmt_port = MgmtPort('eth0')
    switch_ip = engines.dut.ip
    with allure.step('Run show command on mgmt port and verify default description'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            mgmt_port.interface.ip.show()).get_returned_value()

        validate_interface_ip_address(switch_ip, output_dictionary, True)

    with allure.step('Negative validation for eth0 ip'):
        res = mgmt_port.interface.ip.address.set(op_param_name='aa', apply=False, ask_for_confirmation=True)
        assert not res.result or "is not a" in res.returned_value, \
            "The operation succeeded while it is expected to fail"

    with allure.step('Disable dhcp, check mgmt port unreachable'):
        serial_engine.serial_engine.sendline("nv set interface eth0 ip dhcp-client state disabled")
        serial_engine.serial_engine.sendline("nv config apply")
        serial_engine.serial_engine.expect("Are you sure?", timeout=120)
        serial_engine.serial_engine.sendline("y")
        serial_engine.serial_engine.expect("applied", timeout=120)

        logger.info('Check port status, should be down')
        check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)

    with allure.step('Select random ipv4 and set it'):
        ip_address = Tools.IpTool.select_random_ipv4_address().verify_result()
        serial_engine.serial_engine.sendline("nv set interface eth0 ip address {}".format(ip_address))
        serial_engine.serial_engine.sendline("nv config apply")
        serial_engine.serial_engine.expect("Are you sure?", timeout=120)
        serial_engine.serial_engine.sendline("y")
        serial_engine.serial_engine.expect("applied", timeout=120)

        logger.info('Check port status, should be down')
        check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
        serial_engine.serial_engine.sendline("nv show interface eth0")
        serial_engine.serial_engine.expect(ip_address, timeout=120)

    with allure.step('Unset ipv4 and dhcp and check port reachable'):
        serial_engine.serial_engine.sendline("nv unset interface eth0")
        serial_engine.serial_engine.sendline("nv config apply")
        serial_engine.serial_engine.expect("Are you sure?", timeout=120)
        serial_engine.serial_engine.sendline("y")
        serial_engine.serial_engine.expect("applied", timeout=120)

        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        serial_engine.serial_engine.sendline("nv show interface eth0")
        serial_engine.serial_engine.expect(switch_ip, timeout=120)


@pytest.mark.ib
@pytest.mark.simx
def test_interface_eth0_show_dhcp(engines):
    """
    Verify all default fields in nv show interface eth0 ip ipv4 dhcp-client and ipv6 dhcp-client

    flow:
    1. Check all fields are exist in  in nv show interface eth0 ip ipv4 dhcp-client
    2. Check all fields exist in nv show interface eth0 ip ipv6 dhcp-client
    """
    mgmt_port = MgmtPort('eth0')
    with allure.step('Run show command on mgmt port and verify default description'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            mgmt_port.interface.ip.show()).get_returned_value()

        with allure.step("Validate all expected fields in show output"):
            Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, ["dhcp-client", "dhcp-client6"]) \
                .verify_result()
            logging.info("All expected fields were found")


@pytest.mark.ib
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
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = MgmtPort(mgmt_port_name)
    system = System()
    with allure.step('Run show ip dhcp command and check default values and dhcp hostname'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            mgmt_port.interface.ip.dhcp_client.show()).get_returned_value()

        dhcp_hostname = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
            'dhcp_hostname']
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()

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
        serial_engine.serial_engine.expect("Are you sure?", timeout=20)
        serial_engine.serial_engine.sendline("y")
        serial_engine.serial_engine.expect("applied", timeout=20)

        logger.info('Check port status, should be down')
        check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)

        serial_engine.serial_engine.sendline("nv show interface {} ip dhcp-client".format(mgmt_port_name))
        serial_engine.serial_engine.expect("state         disabled", timeout=20)

    with allure.step('Disable dhcp set-hostname, check port down and not reachable'):
        serial_engine.serial_engine.sendline("nv set interface {} ip dhcp-client set-hostname disabled".format(mgmt_port_name))
        serial_engine.serial_engine.sendline("nv config apply")
        serial_engine.serial_engine.expect("Are you sure?", timeout=20)
        serial_engine.serial_engine.sendline("y")
        serial_engine.serial_engine.expect("applied", timeout=20)

        logger.info('Check port status, should be down')
        check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
        serial_engine.serial_engine.sendline("nv show interface {} ip dhcp-client".format(mgmt_port_name))
        serial_engine.serial_engine.expect("state         disabled", timeout=20)
        serial_engine.serial_engine.sendline("nv show interface {} ip dhcp-client6".format(mgmt_port_name))
        serial_engine.serial_engine.expect("state         disabled", timeout=20)

    with allure.step('Set hostname and enable dhcp, check hostname not changed, check port up'):
        serial_engine.serial_engine.sendline("nv set system hostname {}".format(SystemConsts.HOSTNAME))
        serial_engine.serial_engine.sendline("nv config apply")
        serial_engine.serial_engine.expect("Are you sure?", timeout=20)
        serial_engine.serial_engine.sendline("y")
        serial_engine.serial_engine.expect("applied", timeout=20)
        logger.info('Check port status, should be down')
        check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)
        serial_engine.serial_engine.sendline("nv set interface {} ip dhcp-client state enabled".format(mgmt_port_name))
        serial_engine.serial_engine.sendline("nv config apply")
        serial_engine.serial_engine.expect("Are you sure?", timeout=20)
        serial_engine.serial_engine.sendline("y")
        serial_engine.serial_engine.expect("applied", timeout=20)

        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)

        dhcp_output = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            mgmt_port.interface.ip.dhcp_client.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=dhcp_output, field_name='state',
                                                          expected_value='enabled').verify_result()

        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        Tools.ValidationTool.verify_field_value_in_output(system_output, SystemConsts.HOSTNAME,
                                                          'hostname').verify_result()

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
        system.unset(op_param=SystemConsts.HOSTNAME, apply=True, ask_for_confirmation=True)
        wait_for_hostname_changed(system, dhcp_hostname)


@pytest.mark.ib
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
    mgmt_port = MgmtPort(mgmt_port_name)

    with allure.step('Run show command on mgmt port and verify default values'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        field_to_check = [IbInterfaceConsts.TYPE, IbInterfaceConsts.LINK,
                          IbInterfaceConsts.IFINDEX, IbInterfaceConsts.IP]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()

    with allure.step('Verify mgmt interface is reachable'):
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)

    with allure.step('Check logs for mgmt interface exist'):
        show_output = system.log.show_log(exit_cmd='q')
        ValidationTool.verify_expected_output(show_output, mgmt_port_name).verify_result()

    with allure.step('Check stats'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_stats_output_to_dictionary(
            mgmt_port.interface.link.stats.show()).get_returned_value()
        field_to_check = [IbInterfaceConsts.LINK_STATS_CARRIER_TRANSITION, IbInterfaceConsts.LINK_STATS_IN_BYTES,
                          IbInterfaceConsts.LINK_STATS_IN_DROPS, IbInterfaceConsts.LINK_STATS_IN_ERRORS,
                          IbInterfaceConsts.LINK_STATS_IN_PKTS, IbInterfaceConsts.LINK_STATS_OUT_BYTES,
                          IbInterfaceConsts.LINK_STATS_OUT_DROPS, IbInterfaceConsts.LINK_STATS_OUT_ERRORS,
                          IbInterfaceConsts.LINK_STATS_OUT_PKTS]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()


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


@retry(Exception, tries=4, delay=2)
def wait_for_hostname_changed(system, dhcp_hostname):
    with allure.step("Waiting for system hostname changed to {}".format(dhcp_hostname)):
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        assert dhcp_hostname in system_output['hostname'], "hostname wasn't changed"
