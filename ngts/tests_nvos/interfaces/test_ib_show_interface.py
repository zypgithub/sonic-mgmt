import logging
from ngts.tools.test_utils import allure_utils as allure
import pytest

from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts, IbInterfaceConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_constants.constants_nvos import ApiType, NvosConst
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.ResultObj import ResultObj

logger = logging.getLogger()


@pytest.mark.ib_interfaces
@pytest.mark.nvos_ci
@pytest.mark.ib
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_show_interface(engines, devices, test_api):
    """
    Run show interface command and verify the required fields are exist
    command: nv show interface <name>

    flow:
    1. Select a random port (status of which is up)
    2. Run 'nv show interface <name>' on selected port
    3. Verify the required fields are presented in the output
    """
    TestToolkit.tested_api = test_api

    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()

    TestToolkit.update_tested_ports([selected_port])

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            selected_port.interface.show()).get_returned_value()
        validate_one_port_show_output(output_dictionary, devices.dut.switch_type.lower(), devices.dut.asic_type == NvosConst.QTM3)

    '''with allure.step(f'Check interface primary ASIC for port {selected_port.name}'):
        fae = Fae(port_name=selected_port.name)
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            fae.interface.show()).get_returned_value()
        assert IbInterfaceConsts.PRIMARY_ASIC in output_dictionary.keys(), \
            f"{IbInterfaceConsts.PRIMARY_ASIC} field not found for port {selected_port.name}"
        assert int(output_dictionary[IbInterfaceConsts.PRIMARY_ASIC]) in range(0, devices.dut.asic_amount), \
            f"IbInterfaceConsts.PRIMARY_ASIC should be in range of 0-{devices.dut.asic_amount}, " \
            f"but for port {selected_port.name} - " \
            f"{IbInterfaceConsts.PRIMARY_ASIC}={output_dictionary[IbInterfaceConsts.PRIMARY_ASIC]}"'''


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_show_interface_all_state_up(engines, devices, start_sm, test_api):
    """
    Run show interface command and verify the required fields are exist
    command: nv show interface

    flow:
    1. Run 'nv show interface'
    2. Select a random port from the output in 'up' state
    3. Verify the required fields are presented in the output
    4. Change the port state to 'down'
    5. Verify the port state as down
    6. Change the port state to 'up'
    7. Verify the port state as up

    """
    TestToolkit.tested_api = test_api

    output_dictionary = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
        Port.show_interface()).get_returned_value()

    result = Tools.RandomizationTool.select_random_port(requested_ports_state="up",
                                                        requested_ports_logical_state=NvosConsts.LINK_LOG_STATE_ACTIVE,
                                                        requested_ports_type=devices.dut.switch_type.lower())
    if not result.result:
        return

    selected_port = result.returned_value

    TestToolkit.update_tested_ports([selected_port])

    assert selected_port.name in output_dictionary.keys(), "selected port can't be found in the output"

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
        selected_port.interface.show()).get_returned_value()

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower())

    try:
        with allure.step('Set the state of selected port to "down"'):
            selected_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True,
                                                   ask_for_confirmation=True).verify_result()
            selected_port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_DOWN).verify_result()

            output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
                selected_port.interface.show()).get_returned_value()

            with allure.step('Run show command on selected port and verify that each field has an appropriate '
                             'value according to the state of the port'):
                validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower(), False)

            with allure.step('Set the state of selected port to "up"'):
                selected_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                                                       ask_for_confirmation=True).verify_result()
                selected_port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP,
                                                            logical_state='Active').verify_result()

            output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
                selected_port.interface.show()).get_returned_value()

            with allure.step('Run show command on selected port and verify that each field has an appropriate '
                             'value according to the state of the port'):
                validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower(), True)
    finally:
        with allure.step('Set the state of selected port to "up"'):
            selected_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                                                   ask_for_confirmation=True).verify_result()
            selected_port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP,
                                                        logical_state='Active').verify_result()


@pytest.mark.ib_interfaces
@pytest.mark.simx
@pytest.mark.nvos_chipsim_ci
def test_ib_show_interface_all_state_down(engines, devices):
    """
    Run show interface command and verify the required fields are exist
    command: nv show interface

    flow:
    1. Run 'nv show interface'
    2. Select a random port from the output in 'down' state
    3. Verify the required fields are presented in the output
    """
    output_dictionary = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
        Port.show_interface()).get_returned_value()

    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state="down",
                                                               requested_ports_logical_state=None,
                                                               requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()
    TestToolkit.update_tested_ports([selected_port])

    assert selected_port.name in output_dictionary.keys(), "selected port can't be found in the output"

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
        selected_port.interface.show()).get_returned_value()

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port, expecting Polling state since cable is not connected'):
        validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower(), False)
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary[IbInterfaceConsts.LINK],
                                                          field_name=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE,
                                                          expected_value=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING).verify_result()


@pytest.mark.ib_interfaces
@pytest.mark.nvos_ci
@pytest.mark.ib
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_show_interface_name_link(engines, devices, test_api):
    """
    Run show interface command and verify the required fields exist
    Command: nv show interface <name> link

    flow:
    1. Select a random port (status of which is up)
    2. Run 'nv show interface <name> link' on selected port
    3. Verify the required fields are presented in the output
    4. Verify state based on logical & physical state
    """
    TestToolkit.tested_api = test_api

    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()

    TestToolkit.update_tested_ports([selected_port])

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()

        validate_link_fields(output_dictionary, devices.dut.switch_type.lower())
        verify_expected_link_state(output_dictionary)


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_show_interface_name_stats(engines, devices, test_api):
    """
    Run show interface command and verify the required fields exist
    Command: nv show interface <name> link stats

    flow:
    1. Select a random port (status of which is up)
    2. Run 'nv show interface <name> link stats' on selected port
    3. Verify the required fields are presented in the output
    """
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()

    TestToolkit.update_tested_ports([selected_port])

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_stats_output_to_dictionary(
            selected_port.interface.link.stats.show()).get_returned_value()

        validate_stats_fields(output_dictionary, devices.dut.asic_type == NvosConst.QTM3)


@pytest.mark.ib_interfaces
@pytest.mark.ib
def test_show_interface_filter(engines):
    """
    Run show interface command with filter flag and verify the required fields are exist
    command: nv show interface -- filter "<filter>=<value>"

    flow:
    1. Run show interface without filter
    2. Select filter type and value from existing output
    3. Create expected dictionary according to the selected filter
    4. Run show interface with the selected filter
    5. Compare between filtered output dictionary to expected dictionary (at least one should be found)
    6. Run show interface with an empty filter (returns all data)
    7. Compare between filtered output dictionary to the full dictionary
    8. Run show interface with existing filter but value not exist
    9. Run show interface with a filter that does not exist
    """
    interface = Interface(parent_obj=None)

    with allure.step('Run show interface without filter'):
        output_dict = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.show()).get_returned_value()

    with allure.step('Select filter type and value from existing output'):
        random_key = RandomizationTool.select_random_value(list(output_dict.keys())).get_returned_value()
        filter_name = RandomizationTool.select_random_value(list(output_dict[random_key].keys())).get_returned_value()
        value = output_dict[random_key][filter_name]

    with allure.step('Create expected dictionary according to the selected filter'):
        filtered_expected = {}
        for key in output_dict.keys():
            if filter_name in output_dict[key].keys():
                if value == output_dict[key][filter_name]:
                    filtered_expected.update({key: output_dict[key]})

    with allure.step('Run show interface with the selected filter'):
        output_dict_filtered = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.show(f'--filter "{filter_name}={value}"')).get_returned_value()

    with allure.step('Compare between filtered output dictionary to expected dictionary'
                     '(at least one should be found)'):
        ValidationTool.compare_nested_dictionary_content(output_dict_filtered, filtered_expected).verify_result()

    with allure.step('Run show interface with an empty filter (returns all data)'):
        output_dict_filtered = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.show('--filter ""')).get_returned_value()

    with allure.step('Run show interface without filter'):
        output_dict = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.show()).get_returned_value()

    with allure.step('Compare between filtered output dictionary to the full dictionary'):
        ValidationTool.compare_nested_dictionary_content(output_dict_filtered, output_dict).verify_result()

    with allure.step('Run show interface with existing filter but value not exist'):
        value = 'value_not_exists'
        output_dict_filtered = interface.show(f'--filter "{filter_name}={value}"', output_format='auto')
        assert output_dict_filtered == 'No Data'

    with allure.step('Run show interface with a filter that does not exist'):
        filter_name = 'filter_not_exist'
        output_dict_filtered = interface.show(f'--filter "{filter_name}={value}"',
                                              output_format='auto', should_succeed=False)
        assert 'Error: No match found for filter depth of 4.' in output_dict_filtered


def validate_interface_fields(output_dictionary):
    with allure.step('Check that the following fields exist in the output: type, link'):
        logging.info('Check that the following fields exist in the output: type, link')
        field_to_check = [IbInterfaceConsts.TYPE, IbInterfaceConsts.LINK]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()


def validate_link_fields(output_dictionary, switch_type, port_up=True):
    with allure.step('Check that all expected fields under link field exist in the output'):
        logging.info('Check that all expected fields under link field exist in the output')
        field_to_check = [IbInterfaceConsts.LINK_STATE,
                          # IbInterfaceConsts.LINK_IB_SUBNET,
                          IbInterfaceConsts.LINK_SUPPORTED_LANES,
                          IbInterfaceConsts.LINK_MAX_SUPPORTED_MTU,
                          # IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS,
                          # IbInterfaceConsts.LINK_SUPPORTED_SPEEDS,
                          IbInterfaceConsts.LINK_LOGICAL_PORT_STATE,
                          IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE,
                          IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES,
                          IbInterfaceConsts.LINK_CONNECTION_MODE]
        if switch_type == "ib":
            field_to_check.insert(1, IbInterfaceConsts.LINK_IB_SUBNET)  # Insert at the desired position

        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()

        field_to_check = [IbInterfaceConsts.LINK_MTU,
                          # IbInterfaceConsts.LINK_SPEED,
                          # IbInterfaceConsts.LINK_IB_SPEED,
                          IbInterfaceConsts.LINK_OPERATIONAL_VLS]
        if switch_type == "ib":
            field_to_check.insert(2, IbInterfaceConsts.LINK_IB_SUBNET)  # Insert at the desired position

        if output_dictionary[IbInterfaceConsts.LINK_CONNECTION_MODE] == IbInterfaceConsts.XDR and \
           output_dictionary[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE] == IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE:
            field_to_check.insert(1, IbInterfaceConsts.LINK_SPEED)

        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary,
                                                               field_to_check, port_up).verify_result()
        # Will be changed
        field_to_check = [IbInterfaceConsts.LINK_LANES]
        res = Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check, port_up)
        logging.warning(res.info)


def validate_stats_fields(output_dictionary, is_qtm3_device=False):
    with allure.step('Check that all expected fields under link-stats field exist in the output'):
        logging.info('Check that all expected fields under link-stats field exist in the output')
        fields_to_check = [IbInterfaceConsts.LINK_STATS_IN_BYTES,
                           IbInterfaceConsts.LINK_STATS_IN_DROPS,
                           IbInterfaceConsts.LINK_STATS_IN_ERRORS,
                           IbInterfaceConsts.LINK_STATS_IN_SYMBOL_ERRORS,
                           IbInterfaceConsts.LINK_STATS_IN_PKTS,
                           IbInterfaceConsts.LINK_STATS_OUT_BYTES,
                           IbInterfaceConsts.LINK_STATS_OUT_DROPS,
                           IbInterfaceConsts.LINK_STATS_OUT_ERRORS,
                           IbInterfaceConsts.LINK_STATS_OUT_PKTS,
                           IbInterfaceConsts.LINK_STATS_OUT_WAIT]
        if is_qtm3_device:
            logging.info('Add expected fields for Quantum3 device')
            fields_to_check.extend(IbInterfaceConsts.LINK_STATS_QNT3)
            verify_non_negative_counters({IbInterfaceConsts.LINK_STATS_RCV_ICRC_ERRORS: output_dictionary[IbInterfaceConsts.LINK_STATS_RCV_ICRC_ERRORS],
                                         IbInterfaceConsts.LINK_STATS_TX_PARITY_ERRORS: output_dictionary[IbInterfaceConsts.LINK_STATS_TX_PARITY_ERRORS]})
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, fields_to_check).verify_result()


def validate_one_port_show_output(output_dictionary, switch_type, is_qtm3_device=False):
    validate_interface_fields(output_dictionary)

    validate_link_fields(output_dictionary[IbInterfaceConsts.LINK], switch_type)

    validate_stats_fields(output_dictionary[IbInterfaceConsts.LINK][IbInterfaceConsts.LINK_STATS], is_qtm3_device)


def validate_one_port_in_show_all_ports(output_dictionary, switch_type, port_up=True):
    field_to_check = [IbInterfaceConsts.TYPE, IbInterfaceConsts.LINK]
    Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()

    validate_link_fields(output_dictionary[IbInterfaceConsts.LINK], switch_type, port_up)


def verify_expected_link_state(output_dictionary):
    link_physical_port_state = output_dictionary[IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE]
    link_logical_port_state = output_dictionary[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE]
    if link_physical_port_state in \
            [IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING,
             IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_DISABLED]:

        Tools.ValidationTool.validate_fields_values_in_output(
            output_dict=output_dictionary,
            expected_fields=[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE, IbInterfaceConsts.LINK_STATE],
            expected_values=[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_DOWN, NvosConsts.LINK_STATE_DOWN]) \
            .verify_result()

    elif link_physical_port_state == IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP:

        Tools.ValidationTool.verify_field_value_in_output(
            output_dictionary=output_dictionary,
            field_name=IbInterfaceConsts.LINK_STATE,
            expected_value=NvosConsts.LINK_STATE_UP).verify_result()

        assert link_logical_port_state in [IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE,
                                           IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_INITIALIZE], \
            "Link logical port state {} isn't as we expected".format(link_logical_port_state)

    else:
        raise Exception("Link physical port state {} isn't as we expected".format(link_physical_port_state))


def verify_non_negative_counters(link_stats_dict):
    for field, counter in link_stats_dict.items():
        assert counter >= 0, f"counter isn't as we expected.\n we got: {field}={counter}"
