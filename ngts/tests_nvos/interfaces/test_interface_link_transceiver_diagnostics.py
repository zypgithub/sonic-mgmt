import pytest

from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.platform.Platform import Platform
from infra.tools.redmine.redmine_api import is_redmine_issue_active

logger = logging.getLogger()

list_with_status_codes = [{'1024': {'status': 'Cable is unplugged'}}, {'1': {'status': 'Closed by command'}},
                          {'0': {'status': 'No issue was observed'}}, {'2': {'status': 'Negotiation failure'}},
                          {'15': {'status': 'Bad signal integrity'}}, {'59': {'status': 'Other issues'}},
                          {'57': {'status': 'signal not detected'}}]


@pytest.mark.ib
def test_interface_transceiver_diagnostics_basic(engines, devices):
    """
    The test will check default field and values for transceiver diagnostic.

    flow:
    1. Run diagnostics for optical cable and verify fields in output
    2. Run diagnostics for link which doesn't exist and verify output
    3. Run diagnostics for link which is not DDMI and verify output
    4. Run diagnostics for not exist port/eth0/ib0/lo, wrong channel name
    5. Run diagnostics with channel-id for link and verify output
    """
    with allure.step("Create System object"):
        platform = Platform()

    with allure.step("Run diagnostics for optical cable and verify fields in output"):
        list_of_transceivers = list(platform.transceiver.get_dict_of_transceivers(cable_type=PlatformConsts.TRANSCEIVER_CABLE_OPTICAL_MODULE))
        optical_transceiver_name = Tools.RandomizationTool.select_random_value(list_of_transceivers).get_returned_value()
        optical_output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(optical_transceiver_name)).get_returned_value()
        yaml_output = platform.transceiver.show(optical_transceiver_name, output_format=OutputFormat.yaml)
        fields_to_check = ["supported-cable-length", "cable-type", "channel", "diagnostics-status", "identifier",
                           "temperature", "vendor-date-code", "vendor-name", "vendor-pn", "vendor-rev", "vendor-sn",
                           "voltage"]
        for field in fields_to_check:
            assert field in yaml_output, '{0} not exist in yaml output'.format(field)
        Tools.ValidationTool.verify_field_exist_in_json_output(optical_output_dictionary, fields_to_check).\
            verify_result()

    with allure.step("Run diagnostics for link which doesn't exist and verify output"):
        list_of_transceivers = list(platform.transceiver.get_dict_of_transceivers(cable_type=None))
        transceiver_name = Tools.RandomizationTool.select_random_value(list_of_transceivers).get_returned_value()
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(transceiver_name)).get_returned_value()
        fields_to_check = ["diagnostics-status"]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, fields_to_check).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=PlatformConsts.
                                                          HARDWARE_TRANCEIVER_DIAGNOSTIC_STATUS,
                                                          expected_value=PlatformConsts.HARDWARE_TRANCEIVER_NOT_EXIST)\
            .verify_result()

    with allure.step("Run diagnostics for link which is not DDMI and verify output"):
        list_of_transceivers = list(platform.transceiver.get_dict_of_transceivers(cable_type=PlatformConsts.TRANSCEIVER_CABLE_COPPER_CABLE))
        transceiver_name = Tools.RandomizationTool.select_random_value(list_of_transceivers).get_returned_value()
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(transceiver_name)).get_returned_value()
        fields_to_check = ["cable-length", "cable-type", "diagnostics-status", "identifier",
                           "vendor-date-code", "vendor-name", "vendor-pn", "vendor-rev", "vendor-sn"]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, fields_to_check).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=PlatformConsts.
                                                          HARDWARE_TRANCEIVER_DIAGNOSTIC_STATUS,
                                                          expected_value=PlatformConsts.HARDWARE_TRANCEIVER_NOT_DDMI)\
            .verify_result()

    with allure.step('Run diagnostics for not exist port/eth0/ib0/lo, wrong channel name'):
        for port in devices.dut.network_ports:
            output_dictionary = platform.transceiver.show(op_param=port, should_succeed=False)
            assert 'The requested item does not exist.' in output_dictionary, f"Negative command {port} port accepted"
        output_dictionary = platform.transceiver.show(op_param='aa', should_succeed=False)
        assert 'The requested item does not exist.' in output_dictionary, "Negative command aa port accepted"
        output_dictionary = platform.transceiver.show(op_param=f'{optical_transceiver_name} channel aa', should_succeed=False)
        assert 'The requested item does not exist.' in output_dictionary, "Negative command accepted"

    with allure.step("Run diagnostics with channel-id for link and verify output"):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(f'{optical_transceiver_name} channel channel-1')).get_returned_value()
        assert output_dictionary['rx-power'] != '-inf mW', "RX power value not as expected"
        assert output_dictionary['tx-bias-current'] != '-inf mW', "TX bias power value not as expected"
        assert output_dictionary['tx-power'] != '-inf mW', "TX power value not as expected"
        fields_to_check = ["rx-power", "tx-power", "tx-bias-current"]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, fields_to_check).verify_result()


@pytest.mark.ib
def test_interface_link_diagnostics_basic(engines, devices):
    """
    The test will check default field and values for link diagnostic.

    flow:
    1. Check all fields exist in output command
    2. Validate code to message
    3. Run link diagnostics for port in up state
    4. Run link diagnostics for unplugged port
    5. Run link diagnostics for not exist port/eth0/ib0/lo
    """
    selected_down_ports = Tools.RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_DOWN,
                                                                      requested_ports_type=devices.dut.switch_type.lower(),
                                                                      num_of_ports_to_select=0).get_returned_value()
    selected_up_ports = Tools.RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_UP,
                                                                    requested_ports_type=devices.dut.switch_type.lower(),
                                                                    num_of_ports_to_select=0).get_returned_value()
    selected_fnm_ports = Tools.RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_UP,
                                                                     requested_ports_type=IbInterfaceConsts.FNM_PORT_TYPE,
                                                                     num_of_ports_to_select=0).get_returned_value()

    all_switch_ports = selected_up_ports + selected_down_ports
    count_of_all_ports = len(all_switch_ports)
    with allure.step('Run nv show interface --view link-diagnostics to check fields, codes'):
        any_port = selected_up_ports[0]
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            any_port.show_interface(port_names='--view link-diagnostics')).get_returned_value()
        assert count_of_all_ports == len(output_dictionary), 'Not fully interface list in --view link-diagnostics'
        field_to_check = ['link', 'diagnostics', 'status']
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()

        with allure.step('Validate code to message'):
            for port in all_switch_ports:
                diagnostics_per_port = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
                    port.interface.link.diagnostics.show()).get_returned_value()
                output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
                    any_port.show_interface(port_names='--view link-diagnostics')).get_returned_value()
                status_dict = output_dictionary[port.name]['link']['diagnostics']
                logging.info("Check each port status in all ports status")
                logging.info("Status dict {0} for port {1}".format(status_dict, port.name))
                assert status_dict in list_with_status_codes, "Code doesn't exist in status code list"
                if diagnostics_per_port != status_dict:
                    raise BaseException("Transceiver diagnostic for all ports not equal {0} to "
                                        "transceiver diagnostic per port {1}".format(status_dict, diagnostics_per_port))

    with allure.step('Run nv show interface for port in up state'):
        up_port_output = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            any_port.interface.link.diagnostics.show()).get_returned_value()
        assert up_port_output == IbInterfaceConsts.LINK_DIAGNOSTICS_WITHOUT_ISSUE_PORT, "Status code isn't 0"

    with allure.step('Run nv show interface for unplugged port'):
        for port in selected_down_ports:
            if port.name == 'sw32p1' or port.name == 'swA32p1':
                unplugged_port_output = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
                    port.interface.link.diagnostics.show()).get_returned_value()
                assert unplugged_port_output == IbInterfaceConsts.LINK_DIAGNOSTICS_UNPLUGGED_PORT, \
                    "Status code isn't 1024"

    if not is_redmine_issue_active(3556295):
        with allure.step('Run nv show interface for not exist port/eth0/ib0/lo'):
            output_dictionary = any_port.show_interface(port_names='aa link diagnostics')
            assert "Valid interface types are swp, eth, loopback, ipoib, fnm." in output_dictionary, \
                "Can run command for aa transceiver"
            output_dictionary = any_port.show_interface(port_names='eth0 link diagnostics')
            assert output_dictionary == "Error: 'diagnostics' is not one of ['brief', 'state', 'counters']", \
                "Can run command for eth0 transceiver"
            output_dictionary = any_port.show_interface(port_names='ib0 link diagnostics')
            assert output_dictionary == "Error: 'diagnostics' is not one of ['brief', 'state', 'counters']", \
                "Can run command for ib0 transceiver"
            output_dictionary = any_port.show_interface(port_names='lo link diagnostics')
            assert output_dictionary == "Error: 'diagnostics' is not one of ['brief', 'state', 'counters']", \
                "Can run command for lo transceiver"


@pytest.mark.ib
def test_interface_link_diagnostics_functional(engines, start_sm, devices):
    """
    The test will check functionality of link diagnostics in different scenarios.

    flow:
    1. Get connected to each other ports
    2. Shutdown first one, check code and status for both of them, unset interface
    3. Get redis alias for port
    4. Rewrite transceiver opcode for port to negative value, check output, should be empty
    5. Rewrite transceiver opcode for port to 0, check output, system should return correct code and status
    """
    selected_up_ports = Tools.RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_UP,
                                                                    requested_ports_type=devices.dut.switch_type.lower(),
                                                                    num_of_ports_to_select=0).get_returned_value()
    with allure.step('Get ports connected to each others'):
        # Need to provide some good way to find loopback ports. Is it ibnetdiscover?
        check_list = ['sw15p1', 'sw16p1', 'swA15p1', 'swA16p1']
        ports_connected = [port for port in selected_up_ports if port.name in check_list]
        assert ports_connected, 'Connected in loopback ports not found'

    with allure.step('Check default code and status, should be the same'):
        first_port_status = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            ports_connected[0].interface.link.diagnostics.show()).get_returned_value()
        second_port_status = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            ports_connected[-1].interface.link.diagnostics.show()).get_returned_value()
        assert first_port_status == second_port_status, "Status code isn't 1"

    with allure.step('Shutdown first port and check code and status on both'):
        ports_connected[0].interface.link.state.set(NvosConsts.LINK_STATE_DOWN, apply=True,
                                                    ask_for_confirmation=True).verify_result()

        _wait_until_status_changed(ports_connected[0], IbInterfaceConsts.LINK_DIAGNOSTICS_CLOSED_BY_COMMAND_PORT)
        _wait_until_status_changed(ports_connected[1], IbInterfaceConsts.LINK_DIAGNOSTICS_SIGNAL_NOT_DETECTED)
        ports_connected[0].interface.link.state.set(NvosConsts.LINK_STATE_UP, apply=True,
                                                    ask_for_confirmation=True).verify_result()


@retry(Exception, tries=15, delay=1)
def _wait_until_status_changed(port, status):
    port_status = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(port.interface.
                                                                                              link.diagnostics.show()).\
        get_returned_value()
    assert port_status == status, "Status code isn't {}".format(status)
