import time

import pytest
import logging

from ngts.nvos_constants.constants_nvos import ApiType, MultiPlanarConsts, NvosConst
from ngts.nvos_tools.Devices.IbDevice import JulietNonScaleoutSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
# from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts [TBD]
from ngts.tools.test_utils.allure_utils import step as allure_step
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.platform.Platform import Platform

logger = logging.getLogger()


@pytest.mark.interface
@pytest.mark.multiplanar
@pytest.mark.simx
@pytest.mark.nvl_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_nvl5_interface_commands(engines, devices, test_api, has_loopbox):
    """
    validate all show fae interface nvl5 commands.

    Test flow:
    1. Validate show interface command with all nvl5 interfaces
    2. Validate show fae interface command with all nvl5 interfaces
    3. Validate all multi planar fields exist and port type nvl, port speed 400G
    4. Validate link diagnostics on access port
    5. Clear counters
    """

    TestToolkit.tested_api = test_api
    dut_device = devices.dut
    platform = Platform()
    present_transceivers = platform.transceiver.get_list_of_connected_transceivers()
    with allure_step("Select nvl5 port"):
        port_name = RandomizationTool.select_random_value(devices.dut.nvl5_access_ports_list + devices.dut.nvl5_trunk_ports_list).get_returned_value()
        selected_port = Port(port_name)
        selected_fae_port = Fae(port_name=port_name)
        fnm_port_name = RandomizationTool.select_random_value(devices.dut.nvl5_fnm_ports).get_returned_value()
        fnm_fae_port_name = RandomizationTool.select_random_value(devices.dut.nvl5_internal_fnm_ports).get_returned_value()
        fnm_port = Port(fnm_port_name)
        fnm_fae_port = Fae(port_name=fnm_fae_port_name)

    with allure_step("Validate show interface command with all nvl5 interfaces"):
        show_interface_and_validate(engines, devices, devices.dut.all_nvl5_ports_list)

    with allure_step("Validate show fae interface command with all nvl5 interfaces"):
        show_interface_and_validate(engines, devices, devices.dut.all_fae_nvl5_ports_list, 'fae')

    with allure_step("Validate all multi planar fields exist and port {} type nvl, port speed 400G"
                     .format(selected_port.name)):
        output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
            selected_fae_port.port.interface.show()).get_returned_value()
        fae_port_keys = list(output_fae_port.keys())
        ValidationTool.validate_all_values_exists_in_list(MultiPlanarConsts.MULTI_PLANAR_KEYS, fae_port_keys). \
            verify_result()
        ValidationTool.compare_values(output_fae_port['type'], devices.dut.nvl5_port_type).verify_result()

    with allure_step('Check if device is not a JulietNonScaleoutSwitch Device'):
        if not isinstance(dut_device, JulietNonScaleoutSwitch):
            with allure_step("Verify switch port speed"):
                if devices.dut.nvl5_trunk_ports_list != [] and present_transceivers != []:
                    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_UP, interface_type='sw').get_returned_value()
                    output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                        selected_port.interface.link.show()).get_returned_value()
                    assert output_dictionary[IbInterfaceConsts.LINK_SPEED] == dut_device.nvl5_port_speed, \
                        f"port speed should be {dut_device.nvl5_port_speed} instead of" \
                        f"{output_dictionary[IbInterfaceConsts.LINK_SPEED]}"

    with allure_step("Verify access ports speed"):
        if has_loopbox:
            selected_port = Tools.RandomizationTool.select_random_port(requested_ports_logical_state=NvosConsts.LINK_LOG_STATE_INITIALIZE, interface_type='acp').get_returned_value()
            output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()
            assert output_dictionary[IbInterfaceConsts.LINK_SPEED] == dut_device.nvl5_port_speed, \
                f"port speed should be {dut_device.nvl5_port_speed} instead of" \
                f"{output_dictionary[IbInterfaceConsts.LINK_SPEED]}"

    with allure_step("Verify fnm port speed"):
        if has_loopbox:
            output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                fnm_port.interface.link.show()).get_returned_value()
            assert output_dictionary[IbInterfaceConsts.LINK_SPEED] == dut_device.fnm_link_speed, \
                f"port speed should be {dut_device.fnm_link_speed} instead of" \
                f"{output_dictionary[IbInterfaceConsts.LINK_SPEED]}"

    with allure_step("Verify fae fnm port speed"):
        output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            fnm_fae_port.interface.link.show()).get_returned_value()
        assert output_dictionary[IbInterfaceConsts.LINK_SPEED] == dut_device.fnm_fae_link_speed, \
            f"port speed should be {dut_device.fnm_fae_link_speed} instead of" \
            f"{output_dictionary[IbInterfaceConsts.LINK_SPEED]}"

        # ValidationTool.compare_values(output_fae_port['link']['speed'], devices.dut.nvl5_port_speed).verify_result()
        # [TBD] will work only on real system,  when system arrived, bug 3730650

    # with allure_step("Validate link diagnostics on nvl5"):
    #     output_port = OutputParsingTool.parse_json_str_to_dictionary(
    #         selected_port.interface.link.diagnostics.show()).get_returned_value()
    #     ValidationTool.compare_values(output_port, {'0': {'status': 'No issue was observed'}}).verify_result()
    # [TBD] will work only on real system,  when system arrived, bug 3730650

    with allure_step("Validate all multi planar fields exist and port {} type fnm, port speed 400G"
                     .format(selected_port.name)):
        output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
            fnm_fae_port.port.interface.show()).get_returned_value()
        fae_port_keys = list(output_fae_port.keys())
        ValidationTool.validate_all_values_exists_in_list(MultiPlanarConsts.MULTI_PLANAR_KEYS, fae_port_keys). \
            verify_result()
        ValidationTool.compare_values(output_fae_port['type'], devices.dut.fnm_port_type).verify_result()

    with allure_step("Clear counters and validate"):
        selected_port.interface.action_clear_counter_for_all_interfaces(engines.dut).verify_result()


@pytest.mark.interface
@pytest.mark.nvl_ci
def test_toggle_interface_state(test_name, devices, has_loopbox):
    """
    Configure port interface state and verify the configuration applied successfully
    Relevant cli commands:
    -	nv set interface <name> link state up/down
    -	nv show interface <name>

    flow:
    1. Select a random port (state of which is up)
    2. Set selected port state to ‘down’
    3. Verify the configuration applied by running “show” command
    4. Set selected port state to ‘up’
    5. Wait until the port is up
    6. Verify the configuration applied by running “show” command
    """
    port_init_state_restored = True
    toggleable_interface = ['fnm', 'sw', 'acp'] if has_loopbox else ['sw']
    platform = Platform()
    present_transceivers = platform.transceiver.get_list_of_connected_transceivers()
    if not present_transceivers:
        toggleable_interface.remove('sw')
    try:
        for interface_type in toggleable_interface:
            if devices.dut.nvl5_trunk_ports_list == [] and interface_type == 'sw':
                continue
            port_type = 'fnm' if interface_type == 'fnm' else ''
            selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_UP, requested_ports_type=port_type, interface_type=interface_type).get_returned_value()
            TestToolkit.update_tested_ports([selected_port])
            toggle_port_state(selected_port, NvosConsts.LINK_STATE_DOWN, test_name)
            logger.info("Sleeping for 15 seconds till toggle is reflected")
            time.sleep(15)
            port_init_state_restored = False
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_DOWN).verify_result()

            toggle_port_state(selected_port, NvosConsts.LINK_STATE_UP, test_name)
            logger.info("Sleeping for 15 seconds till toggle is reflected")
            time.sleep(15)
            port_init_state_restored = True
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_UP).verify_result()
    finally:
        if not port_init_state_restored:
            toggle_port_state(selected_port, NvosConsts.LINK_STATE_UP, test_name)


@pytest.mark.interface
@pytest.mark.multiplanar
@pytest.mark.simx
@pytest.mark.nvl_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_nvl5_port_configuration(engines, devices, test_api):
    """
    Validate configuration applied on interface

    Test flow:
    1. Set nvl5 interface description and validate
    2. Unset nvl5 interface and validate
    """

    TestToolkit.tested_api = test_api

    try:
        with allure_step("Select nvl5 port"):
            port_name = RandomizationTool.select_random_value(devices.dut.nvl5_access_ports_list + devices.dut.nvl5_trunk_ports_list).get_returned_value()
            selected_port = Port(port_name)

        with allure_step("Set nvl5 {} port description and validate".format(selected_port.name)):
            selected_port.interface.set(NvosConst.DESCRIPTION, 'aaa', apply=True).verify_result()
            access_port_output = OutputParsingTool.parse_json_str_to_dictionary(
                selected_port.interface.show()).get_returned_value()
            ValidationTool.compare_values(access_port_output['description'], 'aaa').verify_result()

    finally:
        with allure_step("Unset configuration"):
            selected_port.interface.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.interface
@pytest.mark.multiplanar
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_nvl5_negative(engines, devices, test_api):
    """
    Validate negative testing on nvl5 port

    Test flow:
    1. Validate negative split on access nvl5 port
    2. Validate negative testing nvl5 port lanes
    3. Validate negative testing nvl5 port speed
    """

    TestToolkit.tested_api = test_api

    with allure_step("Select nvl5 port"):
        port_name = RandomizationTool.select_random_value(devices.dut.nvl5_access_ports_list + devices.dut.nvl5_trunk_ports_list).get_returned_value()
        selected_port = Port(port_name)

    try:
        if not is_bug_active(4209873):
            with allure_step("Negative testing with split nvl5 {} port".format(selected_port.name)):
                selected_port.interface.link.set(op_param_name='breakout', op_param_value='2x-ndr', apply=True,
                                                 ask_for_confirmation=True).verify_result(False)
                selected_port.interface.link.set(op_param_name='breakout', op_param_value='2x-hdr', apply=True,
                                                 ask_for_confirmation=True).verify_result(False)
                NvueGeneralCli.detach_config(TestToolkit.engines.dut)

        with allure_step("Negative testing with configure nvl5 port params"):
            selected_port.interface.link.set(op_param_name='op-vls', op_param_value='1X', apply=True,
                                             ask_for_confirmation=True).verify_result(False)
            selected_port.interface.link.set(op_param_name='op-vls', op_param_value='4X', apply=True,
                                             ask_for_confirmation=True).verify_result(False)
            selected_port.interface.link.set(op_param_name='speed', op_param_value='xdr', apply=True,
                                             ask_for_confirmation=True).verify_result(False)
            selected_port.interface.link.set(op_param_name='speed', op_param_value='ndr', apply=True,
                                             ask_for_confirmation=True).verify_result(False)
    finally:
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)


def show_interface_and_validate(engines, devices, ports_list, command=''):
    output_dictionary = OutputParsingTool.\
        parse_show_all_interfaces_output_to_dictionary(Port.show_interface(engines.dut, fae_param=command))\
        .get_returned_value()
    output_keys = list(output_dictionary.keys())
    ValidationTool.compare_values(output_keys.sort(), ports_list.sort()).verify_result()


def toggle_port_state(selected_port, port_state, test_name=''):
    selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
    with allure_step("Wait till port {} is {}".format(selected_port, port_state)):
        res_obj, duration = OperationTime.save_duration('port goes {}'.format(port_state), '', test_name,
                                                        selected_port.interface.wait_for_port_state, port_state,
                                                        sleep_time=0.2)
        res_obj.verify_result()
        OperationTime.verify_operation_time(duration, 'port goes {}'.format(port_state)).verify_result()
