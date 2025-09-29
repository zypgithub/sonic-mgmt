from time import sleep

from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tools.test_utils.allure_utils import step as allure_step
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.HostMethods import HostMethods
from ngts.nvos_tools.infra.Fae import Fae


logger = logging.getLogger()


def test_interface_ipoib_mapping_basic_functionality(engines, devices, start_sm):
    """
    Validate IPoIB interface on multi asic systems
        Test flow:
            1. validate nv show fae ipoib-mapping command and validate fields
            2. validate number swid, ib0, asic related to system
            3. validate params applied to ib0 interface
            4. validate logs for params ib0
            5. validate unset
    """
    fae = Fae()
    system = System()
    ib0_port = Port('ib0')
    system.log.rotate_logs()

    with allure_step("Run run nv show fae ipoib-mapping command and validate fields"):
        mapping_output = OutputParsingTool.parse_json_str_to_dictionary(fae.ipoibmapping.show()).get_returned_value()

        with allure_step("Validate all expected fields in show output"):
            ValidationTool.verify_field_exist_in_json_output(mapping_output,
                                                             ["asic", "swid"]).verify_result()
            logging.info("All expected fields were found")

    with allure_step("Check number of swids, ib interfaces and asic related to the system"):
        device = devices.dut
        primary_ib_interface = device.primary_ipoib_interface
        # primary_asic = device.PRIMARY_ASIC
        # primary_swid = device.PRIMARY_SWID
        values_to_check = [ImageConsts.SWID, ImageConsts.ASIC]
        ValidationTool.verify_field_value_exist_in_output_dict(mapping_output, primary_ib_interface).verify_result()
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(mapping_output[primary_ib_interface],
                                                                          values_to_check).verify_result()

    with allure_step("Set parameters to ib0 interface related to the system"):
        ib0_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                                          ask_for_confirmation=True).verify_result()

        ip_address = Tools.IpTool.select_random_ipv4_address().verify_result()
        ib0_port.interface.ipv4.address.set(op_param_name=ip_address, apply=True,
                                            ask_for_confirmation=True).verify_result()

        ip_output = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            ib0_port.interface.ipv4.show()).get_returned_value()

        ib0_output = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            ib0_port.interface.link.show()).get_returned_value()

        ValidationTool.verify_field_value_in_output(output_dictionary=ib0_output,
                                                    field_name=IbInterfaceConsts.LINK_STATE,
                                                    expected_value=NvosConsts.LINK_STATE_UP).verify_result()

        validate_interface_ip_address(ip_address, ip_output)

        with allure_step("Validate params applied to primary/secondary ib interface"):
            primary_ib_interface_output = engines.dut.run_cmd("ip addr show {}".format(device.primary_ipoib_interface))
            if device.multi_asic_system:
                secondary_ib_interface_output = engines.dut.run_cmd("ip addr show {}".format(
                    device.primary_ipoib_interface))
                assert "UP" in secondary_ib_interface_output, "port not in up state"
                assert ip_address in primary_ib_interface_output, "address not found on primary ib interface"
                assert ip_address not in secondary_ib_interface_output, "address found on secondary ib interface"
            else:
                assert ip_address in primary_ib_interface_output, "address not found on primary ib interface"

        with allure_step("Check logs exist for ib0 commands"):

            with allure_step("Run nv show system log command follow to view system logs"):
                show_output = system.log.file.show_log(param="| grep 'IB_INTERFACE_TABLE'")

            with allure_step('Verify updated “system/image” in the logs as expected'):
                ValidationTool.verify_expected_output(show_output, "IB_INTERFACE_TABLE").verify_result()

    with allure_step("Unset ib0 interface"):
        ib0_port.interface.ipv4.address.unset(apply=True).verify_result()

        output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            ib0_port.interface.ipv4.show()).get_returned_value()

        validate_interface_ip_address(ip_address, output_dictionary, False)

        primary_ib_interface_output = engines.dut.run_cmd("ip addr show {}".format(device.primary_ipoib_interface))
        assert ip_address not in primary_ib_interface_output, "address found on primary ib interface"


def test_interface_ipoib_ping_functionality(engines, devices, start_sm, players, interfaces):
    """
    Validate traffic over ipoib interface
        Test flow:
            1. set ip address on switch and host
            2. send ping, validate
            3. unset ip address
    """
    ib0_port = Port('ib0')
    # fae = Fae()

    with allure_step("Set ip on switch ipoib interface and host ib interface connected to switch"):
        ib0_port.interface.ipv4.address.set(op_param_name='1.1.1.1/24', apply=True).verify_result()
        Port.wait_for_port_state(ib0_port, "up")
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_pluggable_output_to_dictionary(
            ib0_port.interface.ipv4.show()).get_returned_value()
        validate_interface_ip_address('1.1.1.1/24', output_dictionary)

        HostMethods.host_ip_address_set(engines.ha, '1.1.1.2/24', interfaces.ha_dut_1)
        sleep(5)
        ping_output = HostMethods.host_ping(engines.ha, '1.1.1.1', interfaces.ha_dut_1)
        assert '5 packets transmitted, 5 received' in ping_output, 'ping is not working'

        with allure_step("Unset ip address"):
            HostMethods.host_ip_address_unset(engines.ha, '1.1.1.2/24', interfaces.ha_dut_1)
            ib0_port.interface.ipv4.address.unset(apply=True).verify_result()


def validate_interface_ip_address(address, output_dictionary, validate_in=True):
    """
    :param address: ip address (could be ipv4 or ipv6)
    :param output_dictionary: the output after running nv show interface ib0 ip
    :param validate_in: True after running set cmd, False after running unset
    """
    with allure_step('check the address field is updated as expected'):
        if validate_in:
            assert address in output_dictionary['address'].keys(), "address not found: {add}".format(add=address)
        if not validate_in:
            assert address not in output_dictionary['address'].keys(), "address found and should be deleted: {add}"\
                .format(add=address)
