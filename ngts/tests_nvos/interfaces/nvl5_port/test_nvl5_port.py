import random
import time
from weakref import finalize

import pytest
import logging
from retry.api import retry_call

from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import ApiType, MultiPlanarConsts, NvosConst
from ngts.tests_nvos.interfaces.nvl5_port.helpers import validate_ports_state_and_speed, toggle_port_state, show_interface_and_validate, skip_if_no_trunk_links, skip_if_no_access_links
from ngts.nvos_tools.Devices.IbDevice import JulietNonScaleoutSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, GnmicErr
from ngts.tests_nvos.system.gnmi.helpers import verify_msg_not_in_out_or_err, verify_msg_in_out_or_err
from ngts.tools.test_utils.allure_utils import step as allure_step
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports, summarize_switch_ports
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


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

    TestToolkit.tested_api = 'NVUE'
    dut_device = devices.dut
    platform = Platform()
    present_transceivers = platform.transceiver.get_list_of_connected_transceivers()
    with allure_step("Select nvl5 port"):
        port_name = RandomizationTool.select_random_value(devices.dut.nvl_access_ports_list + devices.dut.nvl_trunk_ports_list).get_returned_value()
        selected_port = Port(port_name)
        selected_fae_port = Fae(port_name=port_name)
        fnm_port_name = RandomizationTool.select_random_value(devices.dut.nvl_fnm_ports).get_returned_value()
        fnm_fae_port_name = RandomizationTool.select_random_value(devices.dut.nvl_internal_fnm_ports).get_returned_value()
        fnm_port = Port(fnm_port_name)
        fnm_fae_port = Fae(port_name=fnm_fae_port_name)

    with allure_step("Validate show interface command with all nvl5 interfaces"):
        show_interface_and_validate(engines, devices, devices.dut.all_nvl_ports_list)

    with allure_step("Validate show fae interface command with all nvl5 interfaces"):
        show_interface_and_validate(engines, devices, devices.dut.all_fae_nvl_ports_list, 'fae')

    with allure_step("Validate all multi planar fields exist and port {} type nvl, port speed 400G"
                     .format(selected_port.name)):
        output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
            selected_fae_port.port.interface.show()).get_returned_value()
        fae_port_keys = list(output_fae_port.keys())
        ValidationTool.validate_all_values_exists_in_list(MultiPlanarConsts.MULTI_PLANAR_KEYS, fae_port_keys). \
            verify_result()
        ValidationTool.compare_values(output_fae_port['type'], devices.dut.nvl_port_type).verify_result()

    with allure_step('Check if device is not a JulietNonScaleoutSwitch Device'):
        if not isinstance(dut_device, JulietNonScaleoutSwitch):
            with allure_step("Verify switch port speed"):
                if devices.dut.nvl_trunk_ports_list != [] and present_transceivers != []:
                    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_UP, interface_type='sw').get_returned_value()
                    output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                        selected_port.interface.link.show()).get_returned_value()
                    assert output_dictionary[IbInterfaceConsts.LINK_SPEED] == dut_device.nvl_trunk_port_speed, \
                        f"port speed should be {dut_device.nvl_trunk_port_speed} instead of" \
                        f"{output_dictionary[IbInterfaceConsts.LINK_SPEED]}"

    with allure_step("Verify access ports speed"):
        if has_loopbox:
            selected_port = Tools.RandomizationTool.select_random_port(requested_ports_logical_state=NvosConsts.LINK_LOG_STATE_INITIALIZE, interface_type='acp').get_returned_value()
            output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()
            assert output_dictionary[IbInterfaceConsts.LINK_SPEED] == dut_device.access_port_speed, \
                f"port speed should be {dut_device.access_port_speed} instead of" \
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

        # ValidationTool.compare_values(output_fae_port['link']['speed'], devices.dut.nvl_trunk_port_speed).verify_result()
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
            if devices.dut.nvl_trunk_ports_list == [] and interface_type == 'sw':
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
def test_nvl5_port_configuration(engines, devices, random_api):
    """
    Validate configuration applied on interface

    Test flow:
    1. Set nvl5 interface description and validate
    2. Unset nvl5 interface and validate
    """

    TestToolkit.tested_api = 'NVUE'

    if is_bug_active(4502930) and TestToolkit.tested_api == ApiType.OPENAPI:
        logger.info("Bug 4502930 is open and API is OpenApi, replacing with NVUE")
        TestToolkit.tested_api = ApiType.NVUE

    try:
        with allure_step("Select nvl5 port"):
            port_name = RandomizationTool.select_random_value(devices.dut.nvl_access_ports_list + devices.dut.nvl_trunk_ports_list).get_returned_value()
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
        port_name = RandomizationTool.select_random_value(devices.dut.nvl_access_ports_list + devices.dut.nvl_trunk_ports_list).get_returned_value()
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
            selected_port.interface.link.set(op_param_name='speed', op_param_value='800G', apply=True,
                                             ask_for_confirmation=True).verify_result(False)
            selected_port.interface.link.set(op_param_name='speed', op_param_value='100G', apply=True,
                                             ask_for_confirmation=True).verify_result(False)
            selected_port.interface.link.set(op_param_name='speed', op_param_value='555G', apply=True,
                                             ask_for_confirmation=True).verify_result(False)
    finally:
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)


@pytest.mark.interface
@pytest.mark.multiplanar
def test_interface_xdr_slow_speed_access_ports(engines, devices, random_api, setup_name, standalone_system, has_loopbox):
    skip_if_no_access_links(has_loopbox, standalone_system)
    acp_ports_range = f'acp1-{str(len(devices.dut.nvl5_access_ports_list))}'
    _set_unset_interface_xdr_slow_speed(engines, devices, random_api, setup_name,
                                        standalone_system, acp_ports_range, prefix='acp')


@pytest.mark.interface
@pytest.mark.multiplanar
def test_interface_xdr_slow_speed_trunk_ports(engines, devices, random_api, setup_name, standalone_system):
    skip_if_no_trunk_links(devices)
    summarized_switch_ports = summarize_switch_ports(devices.dut.nvl5_trunk_ports_list)
    _set_unset_interface_xdr_slow_speed(engines, devices, random_api, setup_name,
                                        standalone_system, summarized_switch_ports, prefix='sw')


def _set_unset_interface_xdr_slow_speed(engines, devices, test_api, setup_name, standalone_system,
                                        group_all_ports: str, prefix: str):
    """
    Configure xdr slow speed on all trunk / access ports
    Relevant CLI commands:
    - nv set interface <interface-id> link speed 200G/400G
    - nv unset interface <interface-id> link speed
    - nv show interface <interface-id> link

    Flow:
    1. Select all up ports for validation
    2. Set all ports speed to 200G.
    3. Verify the value using the "show" command.
    4. Unset all ports speed.
    5. Verify the default value (400G) is restored.
    """
    TestToolkit.tested_api = test_api
    with allure.step(f"Select {devices.dut.nvl_port_type} ports"):
        port_names = [port.name for port in RandomizationTool.select_random_ports(requested_ports_type=devices.dut.nvl_port_type, num_of_ports_to_select=0).get_returned_value() if port.name.startswith(prefix)]
        up_ports = [Port(port_name) for port_name in port_names]
        selected_port = random.choice(up_ports)

    with allure.step('set up streamed gnmi session - subscribe client to port speed'):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, devices.dut.default_username,
                            devices.dut.default_password, verify_tools_installed=True)
        session = client.gnmic_subscribe_interface_speed_and_keep_session_alive(GnmiMode.STREAM, selected_port.name,
                                                                                skip_cert_verify=True)

    with allure.step(f"Create instance for all ports"):
        all_ports = Port(group_all_ports)

    speed = IbInterfaceConsts.XDR_SLOW_SPEED
    try:
        with allure.step(f"Test speed {speed}"):
            all_ports.interface.link.set(op_param_name=IbInterfaceConsts.LINK_SPEED, op_param_value=speed, apply=True,
                                         ask_for_confirmation=True).verify_result()
            if not standalone_system:
                with allure.step(f"Reset the GPUs on non standalone_system: {setup_name}"):
                    ClusterTools.reboot_compute_nodes_gpus(setup_name)

            with allure.step(f"Validate xdr slow speed on ports"):
                retry_call(validate_ports_state_and_speed, [speed, port_names, prefix], exceptions=AssertionError, tries=6,
                           delay=30)
                time.sleep(30)  # GNMI 30 seconds pulling interval

    # Unset port speed and verify default (400G) is restored
    finally:
        with allure.step(f"Test unset xdr slow speed"):
            all_ports.interface.link.unset(op_param=IbInterfaceConsts.LINK_SPEED, apply=True, ask_for_confirmation=True).verify_result()
            if not standalone_system:
                with allure.step(f"Reset the GPUs on non standalone_system: {setup_name}"):
                    ClusterTools.reboot_compute_nodes_gpus(setup_name)

            with allure.step(f"Validate unset xdr slow speed on ports"):
                retry_call(validate_ports_state_and_speed, [devices.dut.nvl_trunk_port_speed, port_names, prefix], exceptions=AssertionError, tries=6,
                           delay=30)

        with allure.step('verify that client received the xdr speed in the existing streaming session'):
            out, err = client.close_session_and_get_out_and_err(session)
            verify_msg_not_in_out_or_err(GnmicErr.AUTH_FAIL, out, err)
            with allure.independent_step(f'check that "{IbInterfaceConsts.XDR_SLOW_SPEED}" was streamed'):
                verify_msg_in_out_or_err('200', out)
