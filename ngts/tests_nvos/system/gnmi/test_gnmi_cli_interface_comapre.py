import pytest
import logging
import random

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts, IbInterfaceConsts
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tests_nvos.system.gnmi.helpers import verify_msg_not_in_out_or_err, parse_gnmi_output
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, GnmicErr, GnmiConstants
from ngts.constants.constants import GnmiConsts
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.gnmi
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_gnmi_cli_interface_compare(engines, devices, test_api):
    """
    Compare CLI and GNMI interface outputs.

    Test flow:
    1. Randomize two ports (one in up-state and the second in down-state)
    2. Subscribe GNMI client to port.
    3. Run 'nv show interface <port>', and get cli output.
    4. Compare CLI and GNMI outputs.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Select link-up port"):
        link_up_port_name = None
        result_obj = RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_UP,
                                                           num_of_ports_to_select=1)
        if not result_obj.result:
            logger.info(result_obj.info)
        else:
            link_up_port = result_obj.get_returned_value()[0]
            link_up_port_name = link_up_port.name

    with allure.step("Select link-down port"):
        link_down_port_name = None
        result_obj = RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_DOWN,
                                                           num_of_ports_to_select=1)
        if not result_obj.result:
            logger.info(result_obj.info)
        else:
            link_down_port = result_obj.get_returned_value()[0]
            link_down_port_name = link_down_port.name

    with allure.step("Get GNMI client"):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                            devices.dut.default_username, devices.dut.default_password,
                            verify_tools_installed=True)

    with allure.step("Start interface comparing"):
        for port in [link_up_port_name, link_down_port_name]:
            if port is not None:
                port_instance = Port(port)
                logger.info(f"Current port: {port}.")

                with allure.step("Start gnmi session (once) and get output"):
                    gnmi_out, gnmi_err = client.gnmic_subscribe_interface(mode=GnmiMode.ONCE, interface_name=port,
                                                                          skip_cert_verify=True, wait_till_done=True,
                                                                          interface_path='')
                    verify_msg_not_in_out_or_err(GnmicErr.AUTH_FAIL, gnmi_out, gnmi_err)
                    gnmi_output_as_dict = parse_gnmi_output(gnmi_out)

                with allure.step(f"Run 'nv show interface {port}' command and get CLI output"):
                    cli_output = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
                        port_instance.interface.show()).get_returned_value()

                with allure.step("Adjust CLI output to match GNMI output"):
                    adjusted_cli_output = adjust_cli_attributes_and_values(devices.dut.interface_attributes_mapping_dict,
                                                                           cli_output.get('link', {}))

                with allure.step("Compare GNMI-CLI relevant attributes"):
                    if len(adjusted_cli_output) == 0:
                        logger.info("No interface attributes to compare")
                    else:
                        for attribute, value in adjusted_cli_output.items():
                            with allure.independent_step(f"Testing {attribute}"):
                                assert attribute in gnmi_output_as_dict.keys(), f"Can't find {attribute} in GNMI output"
                                assert gnmi_output_as_dict[attribute] == value, f"Output mismatch. CLI={value}, GNMI={gnmi_output_as_dict[attribute]}"


def adjust_cli_attributes_and_values(attributes_mapping_dict, cli_output):
    """
    Adjust CLI attributes and values to match GNMI.
    (this is necessarily for the comparison process)
    """
    res = {}
    for attribute, value in cli_output.items():
        if isinstance(value, dict):
            for inner_attribute, inner_value in value.items():
                if inner_attribute in attributes_mapping_dict.keys():
                    res[attributes_mapping_dict[inner_attribute]] = adjust_cli_values(inner_attribute, inner_value)
        else:
            if attribute in attributes_mapping_dict.keys():
                res[attributes_mapping_dict[attribute]] = adjust_cli_values(attribute, value)
    return res


def adjust_speed(value):
    return 'SPEED_UNKNOWN' if value == '' else value.replace('G', '')


def adjust_supported_speeds(value):
    speeds_list = value.split(',')
    tmp_list = [IbInterfaceConsts.SPEED_LIST[speed].replace('G', '') for speed in speeds_list]
    return ','.join([str(int(x) * 1000) for x in tmp_list])


def adjust_auto_negotiate(value):
    return 'true' if value == 'on' else 'false'


def adjust_logical_state(value):
    return value.upper()


def adjust_physical_state(value):
    return 'LINK_UP' if value == IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP else value.upper()


# Mapping cli-attributes to their corresponding adjustment functions
attribute_adjustments = {
    IbInterfaceConsts.LINK_SPEED: adjust_speed,
    IbInterfaceConsts.LINK_IB_SPEED: adjust_speed,
    IbInterfaceConsts.LINK_SUPPORTED_SPEEDS: adjust_speed,
    IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS: adjust_supported_speeds,
    IbInterfaceConsts.LINK_AUTO_NEGOTIATE: adjust_auto_negotiate,
    IbInterfaceConsts.LINK_LOGICAL_PORT_STATE: adjust_logical_state,
    IbInterfaceConsts.DHCP_STATE: adjust_logical_state,
    IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE: adjust_physical_state,
}


def adjust_cli_values(attribute, value):
    adjustment_function = attribute_adjustments.get(attribute, None)
    if adjustment_function:
        return adjustment_function(value)
    return str(value) if not isinstance(value, str) else value
