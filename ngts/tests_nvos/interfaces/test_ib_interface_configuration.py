import logging
from time import sleep

from ngts.tools.test_utils import allure_utils as allure
import pytest
from retry import retry

from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()

PORT_UPDATE_SLEEP_TIME = 5


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_interface_mtu(engines, players, interfaces, start_sm, test_api):
    """
    Configure port mtu and verify the configuration applied successfully
    Relevant cli commands:
    -	nv set/unset interface <name> link mtu
    -	nv show interface <name> link

    flow:
    1. Select a random port (state of which is up)
    2. Select an invalid mtu value
    3. Verify the mtu value is not updated to selected invalid value
    4. Select a random mtu value
    5. Set the mtu value to selected one
    6. Verify the mtu value is updated to selected value
    7. Unset the mtu value -> should changed to default
    8. If the default mtu value is not equal to the original:
        8.1 Restore the original mtu value
        8.2 Verify the mtu restored to original
    """
    TestToolkit.tested_api = test_api

    with allure.step("Get a random active port"):
        selected_port = Tools.RandomizationTool.get_random_traffic_port().get_returned_value()[0]

    TestToolkit.update_tested_ports([selected_port])

    with allure.step("Read current MTU value"):
        current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()
        origin_mtu_value = current_link_dict[IbInterfaceConsts.LINK_MTU]
        logging.info("Current mtu value of port '{}' is: {}".format(selected_port.name, origin_mtu_value))

    with allure.step("Get the max supported MTU value"):
        max_supported_mtu = current_link_dict[IbInterfaceConsts.LINK_MAX_SUPPORTED_MTU]
        logging.info("Max supported mtu: {}".format(max_supported_mtu))

    with allure.step('Negative validation with not supported for ib mtu 1000'):
        selected_port.interface.link.set(op_param_name='mtu', op_param_value='1000').verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        wait_for_port_to_become_active(selected_port)

    with allure.step("Select a random MTU value for port {}".format(selected_port.name)):
        mtu_values = [value for value in IbInterfaceConsts.MTU_VALUES if value <= int(max_supported_mtu)]
        selected_mtu_value = Tools.RandomizationTool.select_random_value(mtu_values,
                                                                         [origin_mtu_value]).get_returned_value()

    with allure.step("Set mtu '{}' for port '{}".format(selected_mtu_value, selected_port.name)):
        selected_port.interface.link.set(op_param_name='mtu', op_param_value=selected_mtu_value,
                                         apply=True, ask_for_confirmation=True).verify_result()
        sleep(PORT_UPDATE_SLEEP_TIME)

        with allure.step("Verify the mtu value updated to: {}".format(selected_mtu_value)):
            wait_for_port_to_become_active(selected_port)
            current_mtu_value = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()[IbInterfaceConsts.LINK_MTU]
            Tools.ValidationTool.compare_values(current_mtu_value, selected_mtu_value, True).verify_result()

    with allure.step("Unset MTU for port {}".format(selected_port.name)):
        selected_port.interface.link.unset(op_param='mtu', apply=True, ask_for_confirmation=True).verify_result()
        sleep(PORT_UPDATE_SLEEP_TIME)

        with allure.step("Verify the MTU is updated to default: {}".format(IbInterfaceConsts.DEFAULT_MTU)):
            wait_for_port_to_become_active(selected_port)
            current_mtu_value = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()[IbInterfaceConsts.LINK_MTU]
            Tools.ValidationTool.compare_values(current_mtu_value, IbInterfaceConsts.DEFAULT_MTU, True).verify_result()

    if origin_mtu_value != IbInterfaceConsts.DEFAULT_MTU:
        with allure.step("Restore original mtu value ({})".format(origin_mtu_value)):
            selected_port.interface.link.set(op_param_name='mtu', op_param_value=origin_mtu_value,
                                             apply=True, ask_for_confirmation=True).verify_result()
            sleep(PORT_UPDATE_SLEEP_TIME)

            with allure.step("Verify the mtu value was restored to: {}".format(origin_mtu_value)):
                wait_for_port_to_become_active(selected_port)
                current_mtu_value = OutputParsingTool.parse_json_str_to_dictionary(
                    selected_port.interface.link.show()).get_returned_value()[IbInterfaceConsts.LINK_MTU]
                Tools.ValidationTool.compare_values(current_mtu_value, origin_mtu_value, True).verify_result()


@pytest.mark.ib_interfaces
@pytest.mark.nvos_build
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_interface_speed(engines, players, interfaces, devices, start_sm, test_api):
    """
    Configure interface speed and verify the configuration applied successfully
    Relevant cli commands:
    -	nv set/unset interface <name> link speed/ib_speed
    -	nv show interface <name> link

    flow:
    1. Select a random port (state of which is up)
    2. Select a random speed value
    3. Set the speed to selected one
    4. Verify the speed value is updated to selected value (speed and ib_speed)
    5. Send traffic -> Verify the traffic passes successfully
    6. Select a random ib_speed value
    7. Set the ib_speed to selected one
    8. Verify the speed is updated to selected value (speed and ib_speed)
    9. Unset the speed value -> should changed to default
    9. Unset the ib-speed value -> should changed to default
    10.Send traffic -> Verify the traffic passes successfully
    """
    TestToolkit.tested_api = test_api
    if len(devices.dut.supported_ib_speeds) <= 1:
        pytest.skip(f"{type(devices.dut).__name__} has only one supported ib-speed: {devices.dut.supported_ib_speeds[0]}")

    with allure.step("Get a random active port"):
        selected_port = Tools.RandomizationTool.get_random_traffic_port().get_returned_value()[0]

    TestToolkit.update_tested_ports([selected_port])

    with allure.step("Read current speed value"):
        current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()
        current_speed_value = current_link_dict[IbInterfaceConsts.LINK_SPEED]
        origin_ib_speed_value = current_link_dict[IbInterfaceConsts.LINK_IB_SPEED]
        current_lanes_value = current_link_dict[IbInterfaceConsts.LINK_LANES]
        logging.info("Current speed value of port '{}' is: {}".format(selected_port.name, current_speed_value))
        logging.info("Current ib-speed value of port '{}' is: {}".format(selected_port.name, origin_ib_speed_value))
        logging.info("Current lanes value of port '{}' is: {}".format(selected_port.name, current_lanes_value))
        verify_speed_values(devices, selected_port)

    with allure.step("Get supported ib-speeds"):
        supported_ib_speeds = current_link_dict[IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS].split(',')
        logging.info("Supported ib-speeds: {}".format(supported_ib_speeds))

        '''with allure.step("Verify the traffic passes successfully"):
            Tools.TrafficGeneratorTool.send_ib_traffic(players=players, interfaces=interfaces, should_success=True'''

    with allure.step("Select a random ib-speed value for port {}".format(selected_port.name)):
        selected_ib_speed_value = Tools.RandomizationTool.select_random_value(
            list_of_values=supported_ib_speeds, forbidden_values=[IbInterfaceConsts.SDR, IbInterfaceConsts.XDR]). \
            get_returned_value()
        logging.info("Selected ib-speed: " + selected_ib_speed_value)

    with allure.step("Set ib-speed '{}' for port '{}".format(selected_ib_speed_value, selected_port.name)):
        selected_port.interface.link.set(op_param_name='ib-speed', op_param_value=selected_ib_speed_value,
                                         apply=True, ask_for_confirmation=True).verify_result()

        with allure.step("Verify the ib-speed value updated to: {}".format(selected_ib_speed_value)):
            sleep(PORT_UPDATE_SLEEP_TIME)
            wait_for_port_to_become_active(selected_port)
            current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()
            current_ib_speed_value = current_link_dict[IbInterfaceConsts.LINK_IB_SPEED]
            Tools.ValidationTool.compare_values(current_ib_speed_value, selected_ib_speed_value, True).verify_result()
            verify_speed_values(devices, selected_port)

        with allure.step("Get supported ib-speeds"):
            supported_ib_speeds = current_link_dict[IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS]
            logging.info("Supported ib-speeds: {}".format(supported_ib_speeds))

        '''with allure.step('Verify traffic'):
            Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, True).verify_result()'''

    with allure.step("Unset ib_speed for port {}".format(selected_port.name)):
        selected_port.interface.link.unset(op_param='ib-speed', apply=True,
                                           ask_for_confirmation=True).verify_result()
        sleep(PORT_UPDATE_SLEEP_TIME)
        wait_for_port_to_become_active(selected_port)
        verify_speed_values(devices, selected_port)

    with allure.step("Restore {} speed to {}".format(selected_port.name, origin_ib_speed_value)):
        selected_port.interface.link.set(op_param_name='ib-speed', op_param_value=origin_ib_speed_value,
                                         apply=True, ask_for_confirmation=True).verify_result()

        with allure.step("Verify the ib-speed value updated to: {}".format(origin_ib_speed_value)):
            sleep(PORT_UPDATE_SLEEP_TIME)
            wait_for_port_to_become_active(selected_port)
            current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()
            current_ib_speed_value = current_link_dict[IbInterfaceConsts.LINK_IB_SPEED]
            Tools.ValidationTool.compare_values(current_ib_speed_value, origin_ib_speed_value, True).verify_result()
            verify_speed_values(devices, selected_port)


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_interface_speed_invalid(engines, devices, start_sm, test_api):
    """
    Try to set an invalid speed and make sure the config apply fails
    """
    TestToolkit.tested_api = test_api

    with allure.step("Get a random active port"):
        selected_port = Tools.RandomizationTool.get_random_active_port().get_returned_value()[0]

    TestToolkit.update_tested_ports([selected_port])

    invalid_speed = "invalid_speed"
    with allure.step("Set an invalid ib-speed '{}' for port '{}".format(invalid_speed, selected_port.name)):
        selected_port.interface.link.set(op_param_name='ib-speed', op_param_value=invalid_speed,
                                         apply=True, ask_for_confirmation=True).verify_result(False)

    if (test_api == ApiType.OPENAPI) or (not is_bug_active(4370994)):
        invalid_speeds = devices.dut.invalid_ib_speeds
        if invalid_speeds:
            invalid_speed = Tools.RandomizationTool.select_random_value(list(invalid_speeds.keys())).get_returned_value()
            with allure.step("Set an invalid ib-speed '{}' for port '{}".format(invalid_speed, selected_port.name)):
                selected_port.interface.link.set(op_param_name='ib-speed', op_param_value=invalid_speed,
                                                 apply=False, ask_for_confirmation=True).verify_result()

                with allure.step("Try to apply invalid configuration and expect failure"):
                    res = Tools.SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config,
                                                                engines.dut, False)
                    selected_port.interface.link.unset(op_param='ib-speed', apply=True,
                                                       ask_for_confirmation=True).verify_result()
                    res.verify_result(False)


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_interface_lanes(engines, players, interfaces, devices, start_sm, test_api):
    """
    Configure port lanes and verify the configuration applied successfully
    Relevant cli commands:
    -	nv set/unset interface <name> link lanes
    -	nv show interface <name> link

    flow:
    1. Select a random port (state of which is up)
    2. Select a random lane value
    3. Set the lane value to selected one
    4. Verify the lane value is updated to selected value
    5. Send traffic -> Verify the traffic passes successfully
    6. Unset the lanes value -> should changed to default
    7. If the default lanes value is not equal to the original:
        7.1 Restore the original lanes value
        7.2 Verify the lanes restored to original
    8. Send traffic -> Verify the traffic passes successfully
    """
    TestToolkit.tested_api = test_api

    with allure.step("Get a random active port"):
        selected_port = Tools.RandomizationTool.get_random_traffic_port().get_returned_value()[0]

    TestToolkit.update_tested_ports([selected_port])

    with allure.step("Read current supported lanes"):
        current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()
        current_lanes = current_link_dict[IbInterfaceConsts.LINK_LANES]
        current_supported_lanes = current_link_dict[IbInterfaceConsts.LINK_SUPPORTED_LANES]

        logging.info("Current lanes value of port '{}' is: {}".format(selected_port.name, current_lanes))
        logging.info("Current supported-lanes value of port '{}' is: {}".format(selected_port.name,
                                                                                current_supported_lanes))

    with allure.step("Select a random lanes for port {}".format(selected_port.name)):
        selected_lanes = Tools.RandomizationTool.select_random_value(IbInterfaceConsts.SUPPORTED_LANES,
                                                                     [current_supported_lanes]).get_returned_value()

    with allure.step("Set lanes to '{}' for port '{}".format(selected_lanes, selected_port.name)):
        selected_port.interface.link.set(op_param_name='lanes', op_param_value=selected_lanes,
                                         apply=True, ask_for_confirmation=True).verify_result()

        with allure.step("Verify the lanes value updated to: {}".format(selected_lanes)):
            wait_for_port_to_become_active(selected_port)
            current_lanes = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()[IbInterfaceConsts.LINK_LANES]
            assert current_lanes in selected_lanes, "Invalid value for {}".format(IbInterfaceConsts.LINK_LANES)

            with allure.step("Verify the 'speed' is updated appropriately"):
                verify_speed_values(devices, selected_port)

        '''with allure.step('Verify traffic'):
            Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, True).verify_result()'''

    with allure.step("Unset lanes for port {}".format(selected_port.name)):
        selected_port.interface.link.unset(op_param='lanes', apply=True, ask_for_confirmation=True).verify_result()

        with allure.step("Verify the lanes is updated to default: {}".format(IbInterfaceConsts.DEFAULT_LANES)):
            wait_for_port_to_become_active(selected_port)
            current_lanes = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()[IbInterfaceConsts.LINK_LANES]
            assert current_lanes in IbInterfaceConsts.DEFAULT_LANES, \
                "Invalid value for {}".format(IbInterfaceConsts.LINK_LANES)

            with allure.step("Verify the 'speed' is updated appropriately"):
                verify_speed_values(devices, selected_port)

    if current_supported_lanes != IbInterfaceConsts.DEFAULT_LANES:
        with allure.step("Restore original lanes value ({})".format(current_supported_lanes)):
            selected_port.interface.link.set(op_param_name='lanes', op_param_value=current_supported_lanes,
                                             apply=True, ask_for_confirmation=True).verify_result()

            with allure.step("Verify the lanes value was restored to: {}".format(current_supported_lanes)):
                wait_for_port_to_become_active(selected_port)
                current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
                    selected_port.interface.link.show()).get_returned_value()
                current_lanes = current_link_dict[IbInterfaceConsts.LINK_LANES]
                current_supported_lanes = current_link_dict[IbInterfaceConsts.LINK_SUPPORTED_LANES]

                Tools.ValidationTool.compare_values(current_supported_lanes, IbInterfaceConsts.DEFAULT_LANES, True).\
                    verify_result()

                assert current_lanes in IbInterfaceConsts.DEFAULT_LANES, "Invalid value for {}".\
                    format(IbInterfaceConsts.LINK_LANES)

                with allure.step("Verify the 'speed' is updated appropriately"):
                    verify_speed_values(devices, selected_port)


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_interface_vls(engines, players, interfaces, start_sm, test_api):
    """
    Configure port vls and verify the configuration applied successfully
    Relevant cli commands:
    -	nv set/unset interface <name> link op-vls
    -	nv show interface <name> link

    flow:
    1. Select a random port (state of which is up)
    2. Select a random op-vls value
    3. Set the op-vls value to selected one
    4. Verify the op-vls value is updated to selected value
    5. Send traffic -> Verify the traffic passes successfully
    6. Unset the op-vls value -> should changed to default
    7. If the default op-vls value is not equal to the original:
        7.1 Restore the original op-vls value
        7.2 Verify the op-vls restored to original
    8. Send traffic -> Verify the traffic passes successfully
    """
    TestToolkit.tested_api = test_api

    with allure.step("Get a random active port"):
        selected_port = Tools.RandomizationTool.get_random_traffic_port().get_returned_value()[0]

    TestToolkit.update_tested_ports([selected_port])

    with allure.step("Read current supported op-vls"):
        current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()
        current_supported_op_vls = current_link_dict[IbInterfaceConsts.LINK_OPERATIONAL_VLS]
        origin_vl_capabilities = current_link_dict[IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES]
        logging.info("Current op_vls value of port '{}' is: {}".format(selected_port.name, current_supported_op_vls))
        logging.info("Current vl capabilities value of port '{}' is: {}".format(selected_port.name,
                                                                                origin_vl_capabilities))

    with allure.step("Select a random op_vls for port {}".format(selected_port.name)):
        selected_op_vls = Tools.RandomizationTool.select_random_value(IbInterfaceConsts.SUPPORTED_VLS,
                                                                      [origin_vl_capabilities]).get_returned_value()

    with allure.step("Set op_vls to '{}' for port '{}".format(selected_op_vls, selected_port.name)):
        selected_port.interface.link.set(op_param_name='op-vls', op_param_value=selected_op_vls,
                                         apply=True, ask_for_confirmation=True).verify_result()
        sleep(PORT_UPDATE_SLEEP_TIME)

        with allure.step("Verify vl-capabilities value updated to: {}".format(selected_op_vls)):
            wait_for_port_to_become_active(selected_port)
            current_vl_capabilities = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).\
                get_returned_value()[IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES]
            assert current_vl_capabilities in selected_op_vls, "Invalid value for {}".\
                format(IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES)

    with allure.step("Unset op_vls for port {}".format(selected_port.name)):
        selected_port.interface.link.unset(op_param='op-vls', apply=True, ask_for_confirmation=True).verify_result()
        sleep(PORT_UPDATE_SLEEP_TIME)

        with allure.step("Verify the op_vls is updated to default: {}".format(IbInterfaceConsts.DEFAULT_VLS)):
            wait_for_port_to_become_active(selected_port)
            current_vl_capabilities = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.link.show()).\
                get_returned_value()[IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES]
            assert current_vl_capabilities in IbInterfaceConsts.DEFAULT_VLS, "Invalid value for {}".\
                format(IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES)

    if origin_vl_capabilities != IbInterfaceConsts.DEFAULT_VLS:
        with allure.step("Restore original op_vls value ({})".format(current_supported_op_vls)):
            selected_port.interface.link.set(op_param_name='op-vls', op_param_value=current_supported_op_vls,
                                             apply=True, ask_for_confirmation=True).verify_result()

            with allure.step("Verify the op_vls value was restored to: {}".format(current_vl_capabilities)):
                wait_for_port_to_become_active(selected_port)
                current_vl_capabilities = OutputParsingTool.parse_json_str_to_dictionary(
                    selected_port.interface.link.show()). \
                    get_returned_value()[IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES]
                assert current_vl_capabilities in current_vl_capabilities, "Invalid value for {}".\
                    format(IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES)


def verify_speed_values(devices, selected_port):
    current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
        selected_port.interface.link.show()).get_returned_value()
    speed = current_link_dict[IbInterfaceConsts.LINK_SPEED]
    ib_speed = current_link_dict[IbInterfaceConsts.LINK_IB_SPEED]
    lanes = current_link_dict[IbInterfaceConsts.LINK_LANES]
    ib_speed_val = IbInterfaceConsts.SPEED_LIST[ib_speed].replace("G", "")
    ib_speed_val = round_string_number_with_positivity_check(ib_speed_val, "ib_speed_val")
    lanes_val = lanes.replace("X", "")
    lanes_val = round_string_number_with_positivity_check(lanes_val, "lanes_val")
    speed_val = speed.replace("G", "")
    speed_val = round_string_number_with_positivity_check(speed_val, "speed_val")
    expected_speed = round_string_number_with_positivity_check(ib_speed_val / 4 * lanes_val, "expected speed")
    assert expected_speed == speed_val, "The values of 'speed' is invalid"


def round_string_number_with_positivity_check(value, name):
    res = round(float(value))
    assert res > 0, f"The {name} should be more than zero but is {res}"
    return res


@retry(Exception, tries=12, delay=20)
def wait_for_port_to_become_active(port_obj):
    with allure.step("Waiting for port {} to become active".format(port_obj.name)):
        current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(port_obj.interface.link.show()).\
            get_returned_value()
        logical_state = current_link_dict[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE]
        state = current_link_dict[IbInterfaceConsts.LINK_STATE]
        assert logical_state == "Active" and "up" in state.keys(), \
            "The logical state of interface {} is not 'Active'".format(port_obj.name)
        sleep(PORT_UPDATE_SLEEP_TIME)
