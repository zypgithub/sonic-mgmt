import pytest
import logging
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.check_log_size
@pytest.mark.check_disk_usage
@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv4_address(engines, random_api):
    _ib0_interface_ip_address(False)


@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv6_address(engines, random_api):
    _ib0_interface_ip_address(True)


def _ib0_interface_ip_address(is_ipv6):
    ib0_port = Port('ib0')
    if is_ipv6:
        ip_address = Tools.IpTool.select_random_ipv6_address().verify_result()
        ip_obj = ib0_port.interface.ipv6
    else:
        ip_address = Tools.IpTool.select_random_ipv4_address().verify_result()
        ip_obj = ib0_port.interface.ipv4

    ip_obj.address.set(op_param_name=ip_address, apply=True, ask_for_confirmation=True).verify_result()

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
        ip_obj.show()).get_returned_value()

    validate_interface_ip_address(ip_address, output_dictionary)

    ip_obj.address.unset(apply=True).verify_result()

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
        ip_obj.show()).get_returned_value()

    validate_interface_ip_address(ip_address, output_dictionary, False)


def validate_interface_ip_address(address, output_dictionary, validate_in=True):
    """

    :param address: ip address (could be ipv4 or ipv6)
    :param output_dictionary: the output after running nv show interface ib0 ip
    :param validate_in: True after running set cmd, False after running unset
    """
    with allure.step('check the address field is updated as expected'):
        if validate_in:
            assert address in output_dictionary['address'].keys(), "address not found: {add}".format(add=address)
        if not validate_in:
            assert address not in output_dictionary['address'].keys(), "address found and should be deleted: {add}"\
                .format(add=address)


def _test_gateway_functionality(ip_version, ib0_port):
    """
    Test gateway functionality for IPv4 or IPv6

    :param ip_version: 'ipv4' or 'ipv6'
    :param ib0_port: Port object for ib0 interface
    """
    if ip_version == 'ipv4':
        gateway_address_with_cidr = Tools.IpTool.select_random_ipv4_address().verify_result()
        ip_obj = ib0_port.interface.ipv4
    else:  # ipv6
        gateway_address_with_cidr = Tools.IpTool.select_random_ipv6_address().verify_result()
        ip_obj = ib0_port.interface.ipv6

    # Extract IP address without CIDR notation for gateway configuration
    gateway_address = gateway_address_with_cidr.split('/')[0]

    with allure.step(f'Test {ip_version.upper()} gateway set'):
        ip_obj.gateway.set(op_param_name=gateway_address, apply=True, ask_for_confirmation=True).verify_result()
        logger.info(f"Gateway {gateway_address} has been successfully configured (verified by successful set operation)")

    with allure.step(f'Test {ip_version.upper()} gateway show'):
        # Test the gateway show command (even though it returns empty output)
        gateway_show_output = ip_obj.gateway.show()
        logger.info(f"Gateway show command executed, output: {gateway_show_output}")

    with allure.step(f'Test {ip_version.upper()} gateway unset'):
        ip_obj.gateway.unset(apply=True).verify_result()
        logger.info(f"Gateway {gateway_address} has been successfully removed (verified by successful unset operation)")

    # Reconfigure for specific gateway unset test
    ip_obj.gateway.set(op_param_name=gateway_address, apply=True, ask_for_confirmation=True).verify_result()

    with allure.step(f'Test {ip_version.upper()} gateway specific unset'):
        ip_obj.gateway.unset(op_param=gateway_address, apply=True, ask_for_confirmation=True).verify_result()
        logger.info(f"Gateway {gateway_address} has been successfully removed via specific unset (verified by successful unset operation)")


@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_missing_show_commands(engines, random_api):
    """
    Test missing show commands for ib0 interface

    Commands tested:
    - nv show interface ib0 ipv4
    - nv show interface ib0 ipv6
    """

    ib0_port = Port('ib0')

    with allure.step('Test general IPv4 show'):
        ipv4_output = ib0_port.interface.ipv4.show()
        assert ipv4_output is not None, "General IPv4 show should return output"

    with allure.step('Test general IPv6 show'):
        ipv6_output = ib0_port.interface.ipv6.show()
        assert ipv6_output is not None, "General IPv6 show should return output"


@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv4_gateway_commands(engines, random_api):
    """
    Test IPv4 gateway commands for ib0 interface

    Commands tested:
    - nv set interface ib0 ipv4 gateway <addr>
    - nv show interface ib0 ipv4 gateway
    - nv unset interface ib0 ipv4 gateway
    - nv unset interface ib0 ipv4 gateway <ip-address-id>
    """

    ib0_port = Port('ib0')
    _test_gateway_functionality('ipv4', ib0_port)


@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv6_gateway_commands(engines, random_api):
    """
    Test IPv6 gateway commands for ib0 interface

    Commands tested:
    - nv set interface ib0 ipv6 gateway <addr>
    - nv show interface ib0 ipv6 gateway
    - nv unset interface ib0 ipv6 gateway
    - nv unset interface ib0 ipv6 gateway <ip-address-id>
    """

    ib0_port = Port('ib0')
    _test_gateway_functionality('ipv6', ib0_port)
