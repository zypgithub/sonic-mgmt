import pytest
import time
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType

logger = logging.getLogger()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_dhcp_default_values(engines, topology_obj):
    """
        Verify default values for dhcp-client and dhcp-client6.

        flow:
        1. Run nv show interface ib0 ip dhcp-client
        2. verify the set-hostname is enabled, state is disabled, is-running is no and has-lease is no.
        2. Run nv show interface ib0 ip dhcp-client6
        3. verify the set-hostname is enabled, state is disabled, is-running is no and has-lease is no.
        """

    ipoib_port = Port('ib0')
    with allure.step('verify the default values for ib0 ip dhcp-client and dhcp-client6'):
        expected_keys = [IbInterfaceConsts.DHCP_SET_HOSTNAME, 'state', 'has-lease', 'is-running']
        default_values = ['enabled', 'disabled', 'no', 'no']
        dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
            ipoib_port.interface.ip.dhcp_client.show()).verify_result()
        dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
            ipoib_port.interface.ip.dhcp_client6.show()).verify_result()

        with allure.step('verify the default values for ib0 ip dhcp-client'):
            Tools.ValidationTool.validate_fields_values_in_output(
                expected_keys, default_values, dhcp_client_dict).verify_result()

        with allure.step('verify the default values for ib0 ip dhcp-client6'):
            Tools.ValidationTool.validate_fields_values_in_output(
                expected_keys, default_values, dhcp_client6_dict).verify_result()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_dhcp_set_hostname(engines, topology_obj):
    """
        check that we can configure the set-hostname value

        flow:
        1. Run nv set interface ib0 ip dhcp-client set-hostname disable
        2. verify the dhcp-client set-hostname is disabled
        3. verify the dhcp-client6 set-hostname is disabled
        4. Run nv unset interface ib0 ip dhcp-client set-hostname
        5. verify the dhcp-client set-hostname is enabled
        6. verify the dhcp-client6 set-hostname is enabled
        7. Run nv set interface ib0 ip dhcp-client6 set-hostname disable
        8. verify the dhcp-client6 set-hostname is enabled
        """

    ipoib_port = Port('ib0')
    with allure.step('check that we can configure the set-hostname value for dhcp-client'):
        with allure.step('config the set-hostname value to disabled'):
            ipoib_port.interface.ip.dhcp_client.set(op_param_name='set-hostname', op_param_value='disabled',
                                                    apply=True, ask_for_confirmation=True).verify_result()
            time.sleep(10)

        with allure.step('verify the dhcp-client after the change'):
            dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ip.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'disabled').verify_result()

        with allure.step('verify the dhcp-client6 set-hostname after the change'):
            dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ip.dhcp_client6.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client6_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'enabled').verify_result()

        with allure.step('check that we can unset the configuration'):
            ipoib_port.interface.ip.dhcp_client.unset(apply=True, ask_for_confirmation=True)
            dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ip.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'enabled').verify_result()

        with allure.step('verify the dhcp-client6 after unset'):
            dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ip.dhcp_client6.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client6_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'enabled').verify_result()

    with allure.step('check that we can configure the set-hostname value for dhcp-client6'):
        with allure.step('config the set-hostname value to disabled'):
            ipoib_port.interface.ip.dhcp_client6.set(op_param_name=IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                     op_param_value='disabled',
                                                     apply=True, ask_for_confirmation=True).verify_result()

        with allure.step('verify the value after the change'):
            dhcp_client6_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ip.dhcp_client6.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(dhcp_client6_dict, IbInterfaceConsts.DHCP_SET_HOSTNAME,
                                                              'disabled').verify_result()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_set_dhcp_state(engines, topology_obj):
    """
        check that we can configure the set-hostname value

        flow:
        1. Run nv set interface ib0 ip dhcp-client state enabled
        2. verify the dhcp-client state is enabled
        3. Run nv unset interface ib0 ip dhcp-client state
        4. verify the dhcp-client set-hostname is disabled
        """

    ipoib_port = Port('ib0')
    new_value = 'enabled'
    with allure.step('check that we can configure the state value for dhcp-client'):
        with allure.step('config the state value to disabled'):
            ipoib_port.interface.ip.dhcp_client.set(op_param_name='state', op_param_value=new_value,
                                                    apply=True, ask_for_confirmation=True).verify_result()

        with allure.step('verify the dhcp-client state after the change'):
            dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ip.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(
                dhcp_client_dict, IbInterfaceConsts.DHCP_STATE, new_value).verify_result()

        with allure.step('check that we can unset the configuration'):
            ipoib_port.interface.ip.dhcp_client.unset(apply=True, ask_for_confirmation=True)
            dhcp_client_dict = OutputParsingTool.parse_json_str_to_dictionary(
                ipoib_port.interface.ip.dhcp_client.show()).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(
                dhcp_client_dict, IbInterfaceConsts.DHCP_STATE,
                IbInterfaceConsts.IB0_DHCP_STATE_DEFAULT_VALUE).verify_result()


# ------------ Open API tests -----------------

@pytest.mark.openapi
@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_dhcp_default_values_openapi(engines, topology_obj):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_interface_ib0_dhcp_default_values(engines, topology_obj)


@pytest.mark.openapi
@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_dhcp_set_hostname_openapi(engines, topology_obj):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_interface_ib0_dhcp_set_hostname(engines, topology_obj)


@pytest.mark.openapi
@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_set_dhcp_state_openapi(engines, topology_obj):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_interface_ib0_set_dhcp_state(engines, topology_obj)
