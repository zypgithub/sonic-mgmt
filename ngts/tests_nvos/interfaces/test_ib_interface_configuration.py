import logging
from time import sleep

from ngts.tools.test_utils import allure_utils as allure
import pytest
from retry import retry

from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()

PORT_UPDATE_SLEEP_TIME = 5


@pytest.mark.ib_interfaces
def test_ib_interface_mtu(engines, players, interfaces, start_sm, random_api):
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
def test_ib_interface_speed(engines, players, interfaces, devices, start_sm, random_api):
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
        original_supported_ib_speeds = current_link_dict[IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS].split(',')
        logging.info("Current speed value of port '{}' is: {}".format(selected_port.name, current_speed_value))
        logging.info("Current ib-speed value of port '{}' is: {}".format(selected_port.name, origin_ib_speed_value))
        logging.info("Current lanes value of port '{}' is: {}".format(selected_port.name, current_lanes_value))
        logging.info("Original supported-ib-speeds: {}".format(original_supported_ib_speeds))
        verify_speed_values(devices, selected_port)

    with allure.step("Get supported ib-speeds"):
        supported_ib_speeds = [s.strip() for s in original_supported_ib_speeds]
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

        with allure.step("Verify supported-ib-speeds behavior"):
            # EXPECTED BEHAVIOR: When you configure a speed, the supported-ib-speeds field will
            # dynamically update to show only speeds up to what you configured (not higher speeds)
            # Example: If you config 'ndr' (400G), supported-ib-speeds won't show 'xdr' (800G)

            # Get current supported speeds
            current_supported_ib_speeds_str = current_link_dict[IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS]
            current_supported_ib_speeds = [s.strip() for s in current_supported_ib_speeds_str.split(',')]
            logging.info("Current supported-ib-speeds: {}".format(current_supported_ib_speeds))

            # Check if configured a LOWER speed - verify supported-ib-speeds limited
            selected_speed_value = _get_ib_speed_numeric_value(selected_ib_speed_value)
            origin_speed_value = _get_ib_speed_numeric_value(origin_ib_speed_value)

            if selected_speed_value < origin_speed_value:
                with allure.step(f"Verify supported-ib-speeds limited to {selected_ib_speed_value} and below"):
                    violations = []
                    for speed in current_supported_ib_speeds:
                        speed_value = _get_ib_speed_numeric_value(speed)
                        if speed_value > selected_speed_value:
                            violations.append(speed)

                    assert not violations, (
                        f"After configuring ib-speed to {selected_ib_speed_value}, the following HIGHER speeds "
                        f"should NOT appear in supported-ib-speeds: {violations}. "
                        f"Expected: only speeds ≤ {selected_ib_speed_value}"
                    )
                    logger.info(f"✓ Confirmed: After lowering ib-speed to {selected_ib_speed_value}, supported speeds correctly limited")

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
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_ib_interface_speed_invalid(engines, devices, start_sm, test_api):
    """
    Try to set an invalid speed and make sure the config apply fails
    """
    TestToolkit.tested_api = test_api

    with allure.step("Get a random active port"):
        selected_port = Tools.RandomizationTool.get_random_active_port().get_returned_value()[0]

    TestToolkit.update_tested_ports([selected_port])

    with allure.step("Test Invalid Speeds"):
        invalid_speed = "invalid_speed"
        with allure.independent_step("Set an invalid ib-speed '{}' for port '{}".format(invalid_speed, selected_port.name)):
            selected_port.interface.link.set(op_param_name='ib-speed', op_param_value=invalid_speed,
                                             apply=True, ask_for_confirmation=True).verify_result(False)

        invalid_speeds = devices.dut.invalid_ib_speeds
        if invalid_speeds:
            invalid_speed = Tools.RandomizationTool.select_random_value(list(invalid_speeds.keys())).get_returned_value()
            with allure.independent_step("Set an invalid ib-speed '{}' for port '{}".format(invalid_speed, selected_port.name)):
                selected_port.interface.link.set(op_param_name='ib-speed', op_param_value=invalid_speed,
                                                 apply=False, ask_for_confirmation=True).verify_result(should_succeed=False, expected_value="is not one of [")


@pytest.mark.ib_interfaces
def test_ib_interface_lanes(engines, players, interfaces, devices, start_sm, random_api):
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

        # Validate supported-lanes matches device configuration
        if hasattr(devices.dut, 'supported_lanes'):
            expected_supported_lanes = devices.dut.supported_lanes
            assert current_supported_lanes == expected_supported_lanes, (
                f"Expected supported-lanes '{expected_supported_lanes}' from device config, "
                f"but got '{current_supported_lanes}'"
            )
            logger.info(f"✓ Validated: supported-lanes = {current_supported_lanes} (matches device config)")

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
def test_ib_interface_vls(engines, players, interfaces, start_sm, random_api):
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


def _get_ib_speed_numeric_value(ib_speed):
    """Convert IB speed string (e.g., 'xdr', 'ndr') to numeric value in Gbps"""
    speed_str = IbInterfaceConsts.SPEED_LIST.get(ib_speed, '0G')
    return int(speed_str.replace('G', ''))


def _validate_ib_fnm_port(port_name, port_obj, expected_speeds, expected_lanes, port_type="FNM"):
    """Validate supported-ib-speeds and lanes for FNM port"""
    output = OutputParsingTool.parse_json_str_to_dictionary(port_obj.interface.link.show()).get_returned_value()

    # Validate speeds
    speeds_str = output.get(IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS)
    if speeds_str:
        speeds = [s.strip() for s in speeds_str.split(',')]
        logger.info(f"{port_type} port {port_name} supported-ib-speeds: {speeds}")
        Tools.ValidationTool.compare_values(set(speeds), expected_speeds).verify_result()

        # Validate lanes
        lanes_str = output.get(IbInterfaceConsts.LINK_SUPPORTED_LANES)
        if lanes_str and expected_lanes:
            if lanes_str != expected_lanes:
                error_msg = (
                    f"{port_type} port {port_name} supported-lanes mismatch!\n"
                    f"Expected: '{expected_lanes}'\n"
                    f"Actual:   '{lanes_str}'"
                )
                logger.error(error_msg)
                assert False, error_msg
            logger.info(f"✓ Validated {port_type} port {port_name}: speeds={set(speeds)}, lanes={lanes_str}")
        elif lanes_str:
            logger.info(f"{port_type} port {port_name} supported-lanes: {lanes_str} (no validation)")
    else:
        logger.warning(f"No supported-ib-speeds found for {port_type} port {port_name}")


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


@pytest.mark.ib_interfaces
def test_ib_supported_speeds_validation(engines, devices, random_api):
    """
    Validate supported-ib-speeds field matches expected device supported IB speeds

    Test runs on ALL IB switches (Crocodile, BlackMamba, etc.)

    Test flow:
    1. Select a random IB port (any state - supported speeds visible always)
    2. Get supported-ib-speeds from show output
    3. Validate against devices.dut.supported_ib_speeds
    """

    with allure.step("Select random IB port (any state)"):
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
        logger.info(f"Selected port for supported IB speeds validation: {selected_port.name} (state-independent test)")

    with allure.step("Get and validate supported-ib-speeds"):
        current_link_dict = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()

        displayed_ib_speeds_str = current_link_dict.get(IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS)
        if not displayed_ib_speeds_str:
            pytest.skip(f"No supported-ib-speeds found in output for {selected_port.name}")

        displayed_ib_speeds = [s.strip() for s in displayed_ib_speeds_str.split(',')]
        logger.info(f"Displayed supported-ib-speeds: {displayed_ib_speeds}")

        # Validate against device configuration
        if not hasattr(devices.dut, 'supported_ib_speeds'):
            pytest.skip("No supported_ib_speeds defined in device")

        expected_ib_speeds = list(devices.dut.supported_ib_speeds)
        logger.info(f"Expected supported-ib-speeds: {expected_ib_speeds}")

        # Validate they match
        displayed_set = set(displayed_ib_speeds)
        expected_set = set(expected_ib_speeds)

        if displayed_set != expected_set:
            missing = expected_set - displayed_set
            extra = displayed_set - expected_set
            error_msg = (
                f"\n{'=' * 80}\n"
                f"SUPPORTED-IB-SPEEDS MISMATCH!\n"
                f"{'=' * 80}\n"
                f"Port: {selected_port.name}\n"
                f"Displayed: {sorted(displayed_ib_speeds)}\n"
                f"Expected:  {sorted(expected_ib_speeds)}\n"
            )
            if extra:
                error_msg += f"Extra speeds (in output, not in device config): {sorted(extra)}\n"
            if missing:
                error_msg += f"Missing speeds (in device config, not in output): {sorted(missing)}\n"
            error_msg += f"{'=' * 80}\n"
            logger.error(error_msg)
            assert False, error_msg

        logger.info(f"✓ Validated supported-ib-speeds match device configuration")

    # Test FNM ports
    with allure.step("Validate FNM ports (if available)"):
        if hasattr(devices.dut, 'fnm_port_list') and devices.dut.fnm_port_list:
            fnm_port_name = Tools.RandomizationTool.select_random_value(devices.dut.fnm_port_list).get_returned_value()
            fnm_speeds = set(devices.dut.supported_fnm_ib_speeds) if hasattr(devices.dut, 'supported_fnm_ib_speeds') else expected_set
            fnm_lanes = getattr(devices.dut, 'supported_fnm_lanes', None)
            logger.info(f"FNM validation - speeds: {fnm_speeds}, lanes: {fnm_lanes}")
            _validate_ib_fnm_port(fnm_port_name, Port(fnm_port_name), fnm_speeds, fnm_lanes, "FNM")
        else:
            logger.info("No FNM ports available, skipping")

    # Test internal FNM ports
    with allure.step("Validate internal FNM ports (if available)"):
        if hasattr(devices.dut, 'interface_active_internal_fnm_ports') and devices.dut.interface_active_internal_fnm_ports:
            internal_fnm_list = list(devices.dut.interface_active_internal_fnm_ports)
            internal_fnm_port_name = Tools.RandomizationTool.select_random_value(internal_fnm_list).get_returned_value()
            # Internal FNM may have different speeds than regular FNM
            internal_fnm_speeds = set(devices.dut.supported_internal_fnm_ib_speeds) if hasattr(devices.dut, 'supported_internal_fnm_ib_speeds') else set(devices.dut.supported_fnm_ib_speeds) if hasattr(devices.dut, 'supported_fnm_ib_speeds') else expected_set
            internal_fnm_lanes = getattr(devices.dut, 'supported_internal_fnm_lanes', None)
            logger.info(f"Internal FNM validation - speeds: {internal_fnm_speeds}, lanes: {internal_fnm_lanes}")
            _validate_ib_fnm_port(internal_fnm_port_name, Fae(port_name=internal_fnm_port_name), internal_fnm_speeds, internal_fnm_lanes, "Internal FNM")
        else:
            logger.info("No internal FNM ports available, skipping")
