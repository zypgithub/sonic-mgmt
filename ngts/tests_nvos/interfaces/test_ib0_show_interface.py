import pytest

from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.ib
@pytest.mark.nvos_ci
@pytest.mark.nvos_build
def test_ib0_show_interface(engines, random_api):
    """
    Run show interface ib0 command and verify the required fields are exist
    command: nv show interface ib0 link
    """
    ib0_port = Port('ib0')
    with allure.step('Run show command on ib0 port and verify that each field has an appropriate value'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            ib0_port.interface.show()).get_returned_value()

        validate_interface_fields(output_dictionary)


@pytest.mark.ib
def test_ib0_show_interface_link(engines, random_api):
    """
    Run show interface ib0 link command and verify the required fields are exist
    only show cmds
    command0: nv show interface ib0 link
    command1: nv show interface ib0 link state
    command2: nv show interface ib0 link stats
    """
    ib0_port = Port('ib0')

    with allure.step('Run show command on ib0 port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            ib0_port.interface.link.show()).get_returned_value()

        validate_link_fields(output_dictionary)


@pytest.mark.ib
def test_ib0_show_interface_stats(engines, random_api):
    """
    Run show interface command and verify the required fields exist
    Command: nv show interface <name> link stats
    """
    ib0_port = Port('ib0')

    with allure.step('Run show command on ib0 port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_stats_output_to_dictionary(
            ib0_port.interface.counters.show()).get_returned_value()

        validate_stats_fields(output_dictionary)


@pytest.mark.ib
def test_ib0_show_interface_ip(engines, random_api):
    """
    Run show interface command and verify the required fields exist
    Command: nv show interface <name> ip

    flow:
    1. Select ib0 port
    2. Run 'nv show interface ib0 ipv4' and 'nv show interface ib0 ipv6'
    3. Verify the required fields are presented in the output
    """
    ib0_port = Port('ib0')

    with allure.step('Run show command on ib0 port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        # Test both IPv4 and IPv6 interfaces
        output_dictionary_ipv4 = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            ib0_port.interface.ipv4.show()).get_returned_value()
        output_dictionary_ipv6 = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            ib0_port.interface.ipv6.show()).get_returned_value()

        validate_ip_fields(output_dictionary_ipv4)
        validate_ip_fields(output_dictionary_ipv6)


def validate_interface_fields(output_dictionary):
    with allure.step('Check that the following fields exist in the output: type, link, ipv4, ipv6, ifindex'):
        logging.info('Check that the following fields exist in the output: type, link, ipv4, ipv6, ifindex')
        field_to_check = [IbInterfaceConsts.TYPE,
                          IbInterfaceConsts.LINK,
                          IbInterfaceConsts.IFINDEX,
                          IbInterfaceConsts.IPV4,
                          IbInterfaceConsts.IPV6]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()


def validate_link_fields(output_dictionary):
    with allure.step('Check that all expected fields under link field exist in the output'):
        logging.info('Check that all expected fields under link field exist in the output')
        field_to_check = [IbInterfaceConsts.LINK_MTU,
                          IbInterfaceConsts.LINK_MAC,
                          IbInterfaceConsts.LINK_STATE]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()


def validate_stats_fields(output_dictionary):
    with allure.step('Check that all expected fields under link-stats field exist in the output'):
        logging.info('Check that all expected fields under link-stats field exist in the output')
        field_to_check = [IbInterfaceConsts.LINK_STATS_CARRIER_TRANSITION,
                          IbInterfaceConsts.LINK_STATS_IN_BYTES,
                          IbInterfaceConsts.LINK_STATS_IN_DROPS,
                          IbInterfaceConsts.LINK_STATS_IN_ERRORS,
                          IbInterfaceConsts.LINK_STATS_IN_PKTS,
                          IbInterfaceConsts.LINK_STATS_OUT_BYTES,
                          IbInterfaceConsts.LINK_STATS_OUT_DROPS,
                          IbInterfaceConsts.LINK_STATS_OUT_ERRORS,
                          IbInterfaceConsts.LINK_STATS_OUT_PKTS]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()


def validate_ip_fields(output_dictionary):
    with allure.step('Check that all expected fields under ip field exist in the output'):
        logging.info('Check that all expected fields under ip field exist in the output')
        field_to_check = [IbInterfaceConsts.IP_ADDRESS]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()
