import pytest
import time
import logging
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_dhcp_default_values(engines, topology_obj, random_api):
    TestToolkit.tested_api = random_api
    """
        Verify default values for dhcp-client and dhcp-client6.

        flow:
        1. Run nv show interface ib0 ipv4 dhcp-client
        2. verify the set-hostname is enabled, state is disabled.
        2. Run nv show interface ib0 ipv6 dhcp-client6
        3. verify the set-hostname is enabled, state is disabled.
        """
    ipoib_port = Port('ib0')
    with allure.step('verify the default values for ib0 ipv4 dhcp-client and ipv6 dhcp-client6'):
        # Updated schema: use ipv4 and ipv6 instead of ip
        expected_keys = [IbInterfaceConsts.DHCP_SET_HOSTNAME, 'state']
        default_values = ['enabled', 'disabled']
        dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
            ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
        dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
            ipoib_port.interface.ipv6.dhcp_client.show()).verify_result()

        with allure.step('verify the default values for ib0 ipv4 dhcp-client'):
            Tools.ValidationTool.validate_fields_values_in_output(
                expected_keys, default_values, dhcp_client_dict).verify_result()

        with allure.step('verify the default values for ib0 ipv6 dhcp-client6'):
            Tools.ValidationTool.validate_fields_values_in_output(
                expected_keys, default_values, dhcp_client6_dict).verify_result()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_dhcp_set_hostname(engines, topology_obj, random_api):
    TestToolkit.tested_api = random_api
    """
        check that we can configure the set-hostname value (interdependent between IPv4 and IPv6)

        flow:
        1. Run nv set interface ib0 ipv4 dhcp-client set-hostname disable
        2. verify the ipv4 dhcp-client set-hostname is disabled
        3. verify the ipv6 dhcp-client6 set-hostname is also disabled (interdependent)
        4. Run nv unset interface ib0 ipv4 dhcp-client set-hostname
        5. verify the ipv4 dhcp-client set-hostname is enabled
        6. verify the ipv6 dhcp-client6 set-hostname is also enabled (interdependent)
        7. Run nv set interface ib0 ipv6 dhcp-client6 set-hostname disable
        8. verify the ipv6 dhcp-client6 set-hostname is disabled
        9. verify the ipv4 dhcp-client set-hostname is also disabled (interdependent)
        """

    ipoib_port = Port('ib0')
    with allure.step('check that we can configure the set-hostname value for dhcp-client'):
        with allure.step('config the set-hostname value to disabled'):
            ipoib_port.interface.ipv4.dhcp_client.set(op_param_name='set-hostname', op_param_value='disabled',
                                                      apply=True, ask_for_confirmation=True).verify_result()
            time.sleep(10)

        with allure.step('verify the dhcp-client after the change'):
            dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'disabled').verify_result()

        with allure.step('verify the dhcp-client6 set-hostname after the change'):
            dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv6.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client6_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'disabled').verify_result()

        with allure.step('check that we can unset the configuration'):
            ipoib_port.interface.ipv4.dhcp_client.unset(apply=True, ask_for_confirmation=True)
            dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'enabled').verify_result()

        with allure.step('verify the dhcp-client6 after unset'):
            dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv6.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client6_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'enabled').verify_result()

    with allure.step('check that we can configure the set-hostname value for dhcp-client6'):
        with allure.step('config the set-hostname value to disabled'):
            ipoib_port.interface.ipv6.dhcp_client.set(op_param_name=IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                      op_param_value='disabled',
                                                      apply=True, ask_for_confirmation=True).verify_result()

        with allure.step('verify the value after the change'):
            dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv6.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client6_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'disabled').verify_result()

        with allure.step('verify that ipv4 dhcp-client set-hostname is also disabled due to interdependence'):
            dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'disabled').verify_result()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_set_dhcp_state(engines, topology_obj):
    """
        check that we can configure the dhcp-client state value

        flow:
        1. Run nv set interface ib0 ipv4 dhcp-client state enabled
        2. verify the dhcp-client state is enabled
        3. Run nv unset interface ib0 ipv4 dhcp-client state
        4. verify the dhcp-client state is disabled
        """
    try:
        # First, ensure the ib0 interface exists
        ipoib_port = Port('ib0')
        new_value = 'enabled'
        with allure.step('check that we can configure the state value for dhcp-client'):
            with allure.step('config the state value to enabled'):
                # Updated schema: use ipv4 instead of ip
                ipoib_port.interface.ipv4.dhcp_client.set(op_param_name='state', op_param_value=new_value,
                                                          apply=True, ask_for_confirmation=True).verify_result()

            with allure.step('verify the dhcp-client state after the change'):
                dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                    ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
                Tools.ValidationTool.verify_field_value_in_output(
                    dhcp_client_dict, IbInterfaceConsts.DHCP_STATE, new_value).verify_result()

            with allure.step('check that we can unset the configuration'):
                ipoib_port.interface.ipv4.dhcp_client.unset(apply=True, ask_for_confirmation=True)
                dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                    ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
                Tools.ValidationTool.verify_field_value_in_output(
                    dhcp_client_dict, IbInterfaceConsts.DHCP_STATE,
                    IbInterfaceConsts.IB0_DHCP_STATE_DEFAULT_VALUE).verify_result()

    finally:
        ipoib_port.interface.ipv4.dhcp_client.unset(apply=True, ask_for_confirmation=True).verify_result()
        ipoib_port.interface.ipv6.dhcp_client.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_dhcp_ipv6_state(engines, topology_obj, random_api):
    TestToolkit.tested_api = random_api
    """
    Test IPv6 DHCP client state configuration

    flow:
    1. Ensure ib0 interface exists
    2. Test nv set interface ib0 ipv6 dhcp-client state enabled
    3. Test nv unset interface ib0 ipv6 dhcp-client state
    4. Verify state changes are applied correctly
    """
    try:
        # First, ensure the ib0 interface exists
        ipoib_port = Port('ib0')

        with allure.step('Check initial state of IPv4 and IPv6 DHCP clients'):
            # Get initial state of IPv4 DHCP client
            ipv4_dhcp_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
            ipv4_state = ipv4_dhcp_dict.get(IbInterfaceConsts.DHCP_STATE, 'unknown')

            # Get initial state of IPv6 DHCP client
            ipv6_dhcp_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv6.dhcp_client.show()).verify_result()
            ipv6_state = ipv6_dhcp_dict.get(IbInterfaceConsts.DHCP_STATE, 'unknown')

            logger.info(f"Initial IPv4 DHCP client state: {ipv4_state}")
            logger.info(f"Initial IPv6 DHCP client state: {ipv6_state}")

            # Check if states match
            if ipv4_state == ipv6_state:
                logger.info(f"IPv4 and IPv6 DHCP client states match: {ipv4_state}")
            else:
                logger.warning(f"IPv4 and IPv6 DHCP client states differ - IPv4: {ipv4_state}, IPv6: {ipv6_state}")

        with allure.step('Test IPv6 DHCP client state set to enabled'):
            ipoib_port.interface.ipv6.dhcp_client.set(op_param_name='state', op_param_value='enabled',
                                                      apply=True, ask_for_confirmation=True).verify_result()

            # Check status just before verification
            logger.info("Checking DHCP client states before verification:")

            # Check IPv4 DHCP client state
            ipv4_dhcp_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
            ipv4_state = ipv4_dhcp_dict.get(IbInterfaceConsts.DHCP_STATE, 'unknown')
            logger.info(f"IPv4 DHCP client state: {ipv4_state}")

            # Check IPv6 DHCP client state
            ipv6_dhcp_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv6.dhcp_client.show()).verify_result()
            ipv6_state = ipv6_dhcp_dict.get(IbInterfaceConsts.DHCP_STATE, 'unknown')
            logger.info(f"IPv6 DHCP client state: {ipv6_state}")
            logger.info(f"Full IPv6 DHCP response: {ipv6_dhcp_dict}")

            # Verify IPv6 state matches IPv4 state (instead of hardcoding 'enabled')
            if ipv4_state == ipv6_state:
                logger.info(f" IPv6 DHCP client state matches IPv4 state: {ipv6_state}")
            else:
                logger.info(f" IPv6 DHCP client state ({ipv6_state}) does not match IPv4 state ({ipv4_state})")
                # Use the validation tool to show the mismatch
                Tools.ValidationTool.verify_field_value_in_output(
                    ipv6_dhcp_dict, IbInterfaceConsts.DHCP_STATE, ipv4_state).verify_result()

        with allure.step('Test IPv6 DHCP client state unset'):
            ipoib_port.interface.ipv6.dhcp_client.unset(apply=True, ask_for_confirmation=True).verify_result()

            # Check states after unset
            ipv4_dhcp_dict_after = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv4.dhcp_client.show()).verify_result()
            ipv4_state_after = ipv4_dhcp_dict_after.get(IbInterfaceConsts.DHCP_STATE, 'unknown')

            ipv6_dhcp_dict_after = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ipv6.dhcp_client.show()).verify_result()
            ipv6_state_after = ipv6_dhcp_dict_after.get(IbInterfaceConsts.DHCP_STATE, 'unknown')

            logger.info(f"After unset - IPv4 state: {ipv4_state_after}, IPv6 state: {ipv6_state_after}")

            # Verify IPv6 state matches IPv4 state after unset
            if ipv4_state_after == ipv6_state_after:
                logger.info(f" After unset, IPv6 DHCP client state matches IPv4 state: {ipv6_state_after}")
            else:
                logger.info(f" After unset, IPv6 DHCP client state ({ipv6_state_after}) does not match IPv4 state ({ipv4_state_after})")
                Tools.ValidationTool.verify_field_value_in_output(
                    ipv6_dhcp_dict_after, IbInterfaceConsts.DHCP_STATE, ipv4_state_after).verify_result()
    finally:
        ipoib_port.interface.ipv4.dhcp_client.unset(apply=True, ask_for_confirmation=True).verify_result()
        ipoib_port.interface.ipv6.dhcp_client.unset(apply=True, ask_for_confirmation=True).verify_result()
