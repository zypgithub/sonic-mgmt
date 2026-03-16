import random
import pytest
from typing import Tuple
import logging
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch, JulietNonScaleoutSwitch, RosalindSurrogateSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import PhyRecoveryConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tools.test_utils.allure_utils import step as allure_step
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.ngts_types import DevicesT, EnginesT
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.IbnetdiscoverTool import IbnetdiscoverTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


def show_interface_and_validate(engines, devices, ports_list, command=''):
    output_dictionary = OutputParsingTool.\
        parse_show_all_interfaces_output_to_dictionary(Port.show_interface(engines.dut, fae_param=command))\
        .get_returned_value()
    output_keys = list(output_dictionary.keys())
    ValidationTool.compare_values(output_keys.sort(), ports_list.sort()).verify_result()


def toggle_port_state(selected_port, port_state, test_name='', devices=None):
    selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
    with allure_step("Wait till port {} is {}".format(selected_port, port_state)):
        res_obj, duration = OperationTime.save_duration('port goes {}'.format(port_state), '', test_name,
                                                        selected_port.interface.wait_for_port_state, port_state,
                                                        sleep_time=0.2)
        res_obj.verify_result()
        operation = 'port goes {}'.format(port_state)
        OperationTime.verify_operation_time(duration, operation, devices).verify_result()


def validate_ports_state_and_speed(speed, expected_ports: list, prefix: str, state=NvosConsts.LINK_STATE_UP):
    port_requirements = PortRequirements()
    port_requirements.set_port_speed(speed)
    port_requirements.set_port_state(state)
    actual_ports = [port.name for port in Port.get_list_of_ports(port_requirements_object=port_requirements) if port.name.startswith(prefix)]

    ValidationTool.validate_subset_in_superset(expected_ports, actual_ports).verify_result()


def validate_mode_set(selected_port, mode: str, timeout: int = None):
    with allure.step(f"Validate mode {mode} is applied"):
        output = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.port.interface.link.phy_recovery.show()
        ).get_returned_value()
        mode = PhyRecoveryConsts.DISABLED if mode == PhyRecoveryConsts.FW_DEFAULT else mode
        ValidationTool.compare_values(output[PhyRecoveryConsts.SerdesEQ.MODE], mode).verify_result()
        if timeout:
            ValidationTool.compare_values(int(output[PhyRecoveryConsts.SerdesEQ.TIMEOUT]), timeout).verify_result()


def validate_default_config(selected_port):
    with allure_step("Check default config"):
        output_fae_port = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.port.interface.link.phy_recovery.show()).get_returned_value()
        filtered_out = {key: value for key, value in output_fae_port.items() if key in PhyRecoveryConsts.DEFAULT_PHY_RECOVERY_DICT}
        ValidationTool.compare_dictionaries(filtered_out, PhyRecoveryConsts.DEFAULT_PHY_RECOVERY_DICT).verify_result()


def select_random_nvl_port_name(devices, prefix=None):
    with allure.step(f"Select {devices.dut.nvl_port_type} port in up state"):
        port_names = [port.name for port in
                      RandomizationTool.select_random_ports(requested_ports_type=devices.dut.nvl_port_type,
                                                            num_of_ports_to_select=0).get_returned_value()]
        if prefix:
            with allure.step(f"filter by prefix: {prefix}"):
                port_names = [port for port in port_names if port.startswith(prefix)]

        return random.choice(port_names)


def skip_if_no_trunk_links(devices):
    if isinstance(devices.dut, JulietSwitch):
        has_any_connected_transceivers = bool(ClusterTools.get_all_interfaces_with_transceivers(devices))
        if isinstance(devices.dut, JulietNonScaleoutSwitch) or not has_any_connected_transceivers:
            pytest.skip("Skipping test - no connected trunk ports")


def skip_if_no_access_links(has_loopbox, standalone_system, is_simx):
    if not is_simx and not has_loopbox and standalone_system:
        pytest.skip("Skipping test - no connected access ports")


def reset_gpus_if_needed(setup_name):
    if setup_name in Configurations.non_standalone_systems:
        with allure.step(f"Reset the GPUs on non standalone_system: {setup_name}"):
            ClusterTools.reboot_compute_nodes_gpus(setup_name)


def is_qtm3_device(devices: DevicesT) -> bool:
    return isinstance(devices.dut, JulietSwitch) and devices.dut.asic_type in [NvosConst.QTM3, NvosConst.NVL5]


def is_qtm4_device(devices: DevicesT) -> bool:
    return isinstance(devices.dut, RosalindSurrogateSwitch) and devices.dut.asic_type in [NvosConst.QTM4, NvosConst.NVL6]


def is_nvl_device(devices: DevicesT) -> bool:
    return is_qtm3_device(devices) or is_qtm4_device(devices)


def get_linked_ports_pair(devices: DevicesT, engines: EnginesT) -> Tuple[str, str]:
    switches_list = IbnetdiscoverTool.run_ibnetdiscover(engines)
    with allure.step("Get a pair of linked port names"):
        random_switch = random.choice(switches_list)
        num_of_ports_in_switch = min(len(random_switch['ports']) - 1, 72)  # Last port is FNM port
        valid_access_ports = [p for p in random_switch['ports'] if 1 <= p['port_num'] <= num_of_ports_in_switch]
        assert valid_access_ports, f"No valid access ports (1-{num_of_ports_in_switch}) found in switch {random_switch['switch_guid']}"
        src_port = random.choice(valid_access_ports)
        remote_switch_guid = src_port['remote_switch_guid']
        remote_port_num = src_port['remote_port_num']

        remote_switch = next((switch for switch in switches_list if switch['switch_guid'] == remote_switch_guid), None)
        assert remote_switch is not None, f"Remote switch {remote_switch_guid} not found in {switches_list}"
        remote_port = next((port for port in remote_switch['ports'] if port['port_num'] == remote_port_num), None)
        assert remote_port is not None, f"Remote port {remote_port_num} not found in {remote_switch['ports']}"
        acp_port_src_name = f"acp{src_port['port_num'] + (num_of_ports_in_switch * (random_switch['order'] - 1))}"
        assert acp_port_src_name in devices.dut.nvl_access_ports_list, f"Source port {acp_port_src_name} not found in {devices.dut.nvl_access_ports_list}"
        acp_port_dst_name = f"acp{remote_port['port_num'] + (num_of_ports_in_switch * (remote_switch['order'] - 1))}"
        assert acp_port_dst_name in devices.dut.nvl_access_ports_list, f"Destination port {acp_port_dst_name} not found in {devices.dut.nvl_access_ports_list}"
        logger.info(f"Linked ports pair: {acp_port_src_name} <-> {acp_port_dst_name}")
        return (acp_port_src_name, acp_port_dst_name)
