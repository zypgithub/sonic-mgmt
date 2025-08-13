import pytest
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType

logger = logging.getLogger()


@pytest.mark.check_log_size
@pytest.mark.check_disk_usage
@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv4_address(engines):
    _ib0_interface_ip_address(False)


@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv6_address(engines):
    _ib0_interface_ip_address(True)


def _ib0_interface_ip_address(is_ipv6):
    ib0_port = Port('ib0')
    if is_ipv6:
        ip_address = Tools.IpTool.select_random_ipv6_address().verify_result()
    else:
        ip_address = Tools.IpTool.select_random_ipv4_address().verify_result()
    ib0_port.interface.ip.address.set(op_param_name=ip_address, apply=True, ask_for_confirmation=True).verify_result()

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
        ib0_port.interface.ip.show()).get_returned_value()

    validate_interface_ip_address(ip_address, output_dictionary)

    ib0_port.interface.ip.address.unset(apply=True).verify_result()

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
        ib0_port.interface.ip.show()).get_returned_value()

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


# ------------ Open API tests -----------------

@pytest.mark.openapi
@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv6_address_openapi(engines):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_ib0_interface_ipv6_address(engines)


@pytest.mark.openapi
@pytest.mark.ib
@pytest.mark.simx
def test_ib0_interface_ipv4_address_openapi(engines):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_ib0_interface_ipv4_address(engines)
