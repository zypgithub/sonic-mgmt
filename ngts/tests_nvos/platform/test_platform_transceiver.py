import logging
import random
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, NvosConst, PlatformConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.IbInterfaceTool import IbInterfaceTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tests_nvos.platform.constants import TransceiversConsts
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

MODULE_STATUS_DICT = {"Inserted": {"N/A", "Power budget exceeded", "Long range for non - Mellanox cable or module",
                                   "Bit I2C stuck", "Unsupported cable", "High temperature", "Enforce part number list",
                                   "Bad EEPROM", "Bad cable", "PMD type not enabled",
                                   "PCIE system power slot exceeded"},
                      "Removed": {"N/A"}}


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_status(engines, test_api):
    """
    The test will check default field and values for transceiver module_status and error.

    flow:
    1. Check module and error_status for plugged module
    2. Check module and error_status for unplugged module
    """
    TestToolkit.tested_api = test_api

    with allure.step("Create platform object"):
        platform = Platform()

    plugged_module = _get_module_with_status(platform, PlatformConsts.INSERTED)
    unplugged_module = _get_module_with_status(platform, PlatformConsts.REMOVED)
    up_ports = _get_ports_for_module(plugged_module)
    down_ports = _get_ports_for_module(unplugged_module)

    _verify_link_state_up(up_ports)
    _verify_transceiver_status(platform, transceiver_id=plugged_module, expected_module_status=PlatformConsts.INSERTED)

    _verify_transceiver_status(platform, transceiver_id=unplugged_module, expected_module_status=PlatformConsts.REMOVED)
    _verify_link_state_down(down_ports)


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_status_unplug(engines, devices, test_api):
    """
    The test will check if the module_status changes to Removed after simulating unplug event.

    flow:
    1. Verify module is plugged
    2. Unplug selected module
    3. Check module and error_status for unplugged module
    4. Plug module back
    """
    TestToolkit.tested_api = test_api

    platform = Platform()
    desired_state = NvosConsts.LINK_STATE_UP

    with allure.step(f"Get module with state {desired_state}"):
        module_under_test, ports, mst_dev_name, module_index = _get_module_with_desire_state(
            engines, devices, platform, desired_state)

    try:
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')
        IbInterfaceTool.simulate_unplug_module_event(engines.dut, devices.dut, module_index, mst_dev_name, 8)
        _verify_link_state_down(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Removed')

    finally:
        IbInterfaceTool.simulate_plugin_module_event(engines.dut, devices.dut, module_index, mst_dev_name, 50)
        _verify_link_state_up(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_status_with_reboot(engines, devices, test_api):
    """
    The test will check if the value of module_status is reset after reboot.

    flow:
    1. Verify module is plugged
    2. Unplug selected module
    3. Check module and error_status for unplugged module
    4. Reboot the system
    5. Verify module is plugged
    """
    TestToolkit.tested_api = test_api

    with allure.step("Create System and platform object"):
        platform = Platform()
        system = System()

    desired_state = NvosConsts.LINK_STATE_UP
    with allure.step(f"Get module with state {desired_state}"):
        module_under_test, ports, mst_dev_name, module_index = _get_module_with_desire_state(
            engines, devices, platform, desired_state)

    try:
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')

        IbInterfaceTool.simulate_unplug_module_event(engines.dut, devices.dut, module_index, mst_dev_name, 8)
        _verify_link_state_down(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Removed')

        sleep_time_seconds = 60
        with allure.step(f"Reboot the system and sleep {sleep_time_seconds} seconds"):
            system.reboot.action_reboot(engine=engines.dut, device=devices.dut)
            time.sleep(sleep_time_seconds)

        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')

    finally:
        IbInterfaceTool.simulate_plugin_module_event(engines.dut, devices.dut, module_index, mst_dev_name, 50)
        _verify_link_state_up(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_transceiver_general(engines, devices, nv_command, test_api):
    """
    The test verifies all expected modules (by device) exists in transceivers detail output.

    flow:
    1. Verify all expected modules exists in transceivers detail output
    Additional flow for Taipan:
    2. Verify all fields are as expected for els transceiver
    3. Verify all fields are as expected for oe transceiver
    4. Verify transceiver fault-condition, port-mapping and oe-mapping values for each els transceiver
    5. Verify transceiver status, fault-condition, port-mapping and els-mapping for each oe transceiver
    """
    TestToolkit.tested_api = test_api

    transceivers_list = devices.dut.transceiver_list

    with allure.step(f"Verify all expected modules exists in transceivers detail output"):
        transceivers_output = [name for name, transceiver in OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show('detail')).get_returned_value().items()]
        for transceiver in transceivers_list:
            assert transceiver in transceivers_output, f"{transceiver} is missing in transceivers output"

    # In case of Taipan system
    # --------------------------
    if devices.dut.switch_class == NvosConst.TAIPAN_SWITCH:
        els_list = [name for name in transceivers_list if TransceiversConsts.TRANSCEIVERS_ELS in name]
        oe_list = [name for name in transceivers_list if TransceiversConsts.TRANSCEIVERS_OE in name]

        with allure.independent_step(f"Verify transceiver co-optics-mapping output"):
            mapping_output = OutputParsingTool.parse_json_str_to_dictionary(
                nv_command.platform.transceiver.show('co-optics-mapping')).get_returned_value()
            for els in mapping_output.keys():
                assert mapping_output[els][PlatformConsts.TRANSCEIVER_OE_MAPPING] == \
                    TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING[els], \
                    (f"transceiver {els} oe-mapping is no as expected: "
                     f"{TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING[els]}")

                assert mapping_output[els][PlatformConsts.TRANSCEIVER_ELS_MAPPING] == \
                    TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[els], \
                    (f"transceiver {els} port-mapping is no as expected: "
                     f"{TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[els]}")

        with allure.independent_step(f"Verify all fields are as expected for els transceiver"):
            els_rand = random.choice(els_list)
            els_output = OutputParsingTool.parse_json_str_to_dictionary(
                nv_command.platform.transceiver.show(els_rand)).get_returned_value()
            assert els_output.keys() == TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_ELS], \
                (f"els transceiver fields is: {els_output.keys()}, while the expected fields are: "
                 f"{TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_ELS]}")

        with allure.independent_step(f"Verify all fields are as expected for oe transceiver"):
            oe_rand = random.choice(oe_list)
            oe_output = OutputParsingTool.parse_json_str_to_dictionary(
                nv_command.platform.transceiver.show(oe_rand)).get_returned_value()
            assert oe_output.keys() == TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_OE], \
                (f"oe transceiver fields is: {oe_output.keys()}, while the expected fields are: "
                 f"{TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_OE]}")

        with allure.independent_step(f"Verify transceiver fault-condition, "
                                     f"port-mapping and oe-mapping values for each els transceiver"):
            for els in els_list:
                els_output = OutputParsingTool.parse_json_str_to_dictionary(
                    nv_command.platform.transceiver.show(els)).get_returned_value()
                assert els_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].split() == \
                    TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[els], \
                    (f"Transceiver {els} port-mapping is {els_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING]}, "
                     f"instead of {TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[els]}")
                assert els_output[PlatformConsts.TRANSCEIVER_OE_MAPPING].split() == \
                    TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING[els], \
                    (f"Transceiver {els} oe-mapping is {els_output[PlatformConsts.TRANSCEIVER_OE_MAPPING]}, "
                     f"instead of {TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING[els]}")
                if els_output[PlatformConsts.TRANSCEIVER_STATUS] == PlatformConsts.INSERTED:
                    assert els_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION] == 'false', \
                        (f"Transceiver {els} fault-condition is "
                         f"{els_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION]}, instead of false")

        with allure.independent_step(f"Verify transceiver status, fault-condition, "
                                     f"port-mapping and els-mapping for each oe transceiver"):
            for oe in oe_list:
                oe_output = OutputParsingTool.parse_json_str_to_dictionary(
                    nv_command.platform.transceiver.show(oe)).get_returned_value()
                assert oe_output[PlatformConsts.TRANSCEIVER_STATUS] == PlatformConsts.INSERTED, \
                    (f"Transceiver {oe} status is {oe_output[PlatformConsts.TRANSCEIVER_STATUS]}, "
                     f"instead of {PlatformConsts.INSERTED}")
                assert oe_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION] == 'false', \
                    (f"Transceiver {oe} fault-condition is {oe_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION]}, "
                     f"instead of false")
                assert oe_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].split() == \
                    TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]], \
                    (f"Transceiver {oe} port-mapping is {oe_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING]}, "
                     f"instead of {TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]]}")
                assert oe in TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]], \
                    (f"Transceiver {oe} does not exist in {oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]} oe-mapping: "
                     f"{TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]]}")


def _verify_transceiver_status(platform, transceiver_id, expected_module_status='Inserted',
                               expected_error_status='N/A'):
    with allure.step("Check status and error-status exists in nv show platform transceiver"):
        transceiver_output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(transceiver_id)).get_returned_value()
        fields_to_check = [PlatformConsts.TRANSCEIVER_STATUS, PlatformConsts.TRANSCEIVER_ERROR_STATUS]
        Tools.ValidationTool.verify_field_exist_in_json_output(transceiver_output, fields_to_check). \
            verify_result()

    with allure.step(f"Check {PlatformConsts.TRANSCEIVER_STATUS} has correct value {expected_module_status}"):
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=transceiver_output,
                                                          field_name=PlatformConsts.TRANSCEIVER_STATUS,
                                                          expected_value=expected_module_status).verify_result()

    with allure.step("Verify error status exists"):
        module_status = transceiver_output[PlatformConsts.TRANSCEIVER_STATUS].strip()
        error_status = transceiver_output[PlatformConsts.TRANSCEIVER_ERROR_STATUS].strip()
        assert error_status in MODULE_STATUS_DICT[
            module_status], f"module-error-status is in not allowed state: {error_status}"

    with allure.step(f"Check {PlatformConsts.TRANSCEIVER_ERROR_STATUS} has correct value {expected_error_status}"):
        if not is_bug_active(4323183):
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=transceiver_output,
                                                              field_name=PlatformConsts.TRANSCEIVER_ERROR_STATUS,
                                                              expected_value=expected_error_status).verify_result()


def _verify_transceiver_fields(platform, transceiver_id, expected_module_status='Inserted',
                               expected_error_status='N/A'):
    with allure.step("Check all fields in nv show platform transceiver <transceiver>"):
        transceiver_output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(transceiver_id)).get_returned_value()
        fields_to_check = [PlatformConsts.TRANSCEIVER_STATUS, PlatformConsts.TRANSCEIVER_ERROR_STATUS]
        Tools.ValidationTool.verify_field_exist_in_json_output(transceiver_output, fields_to_check). \
            verify_result()

    with allure.step(f"Check {PlatformConsts.TRANSCEIVER_STATUS} has correct value {expected_module_status}"):
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=transceiver_output,
                                                          field_name=PlatformConsts.TRANSCEIVER_STATUS,
                                                          expected_value=expected_module_status).verify_result()

    with allure.step("Verify error status exists"):
        module_status = transceiver_output[PlatformConsts.TRANSCEIVER_STATUS].strip()
        error_status = transceiver_output[PlatformConsts.TRANSCEIVER_ERROR_STATUS].strip()
        assert error_status in MODULE_STATUS_DICT[
            module_status], f"module-error-status is in not allowed state: {error_status}"

    with allure.step(f"Check {PlatformConsts.TRANSCEIVER_ERROR_STATUS} has correct value {expected_error_status}"):
        if not is_bug_active(4323183):
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=transceiver_output,
                                                              field_name=PlatformConsts.TRANSCEIVER_ERROR_STATUS,
                                                              expected_value=expected_error_status).verify_result()


def _verify_link_state_up(up_ports):
    link_states = [
        OutputParsingTool.parse_json_str_to_dictionary(port.interface.link.state.show()).get_returned_value()
        for port in up_ports
    ]
    port_names = [port.name for port in up_ports]
    with allure.step(f"Verify link for any of the {port_names} is {NvosConsts.LINK_STATE_UP}"):
        for link_state in link_states:
            if not link_state:
                assert False, "Link state is empty should be up or down"
            # At least one of the ports should be up for inserted transceiver.
            if NvosConsts.LINK_STATE_UP in link_state:
                return
        assert False, f"None of the ports are {NvosConsts.LINK_STATE_UP}"


def _verify_link_state_down(down_ports):
    link_states = [
        OutputParsingTool.parse_json_str_to_dictionary(port.interface.link.state.show()).get_returned_value()
        for port in down_ports
    ]
    port_names = [port.name for port in down_ports]
    with allure.step(f"Verify all {port_names} are down"):
        for link_state in link_states:
            if not link_state:
                assert False, "Link state is empty should be up or down"
            if NvosConsts.LINK_STATE_DOWN not in link_state:
                assert False, "The link state is up for removed transceiver"


def _get_module_with_status(platform, status):
    with allure.step(f"Find {status} module"):
        detail = ""
        if TestToolkit.tested_api == ApiType.NVUE:
            detail = "detail"
        transceivers = [name for name, transceiver in
                        OutputParsingTool.parse_json_str_to_dictionary(
                            platform.transceiver.show(detail)).get_returned_value().items() if
                        ((TransceiversConsts.TRANSCEIVERS_SW in name) or (TransceiversConsts.TRANSCEIVERS_ELS in name)) and
                        transceiver[PlatformConsts.TRANSCEIVER_STATUS] == status]
        if not transceivers:
            pytest.skip(f"No {status} transceivers found for setup")
        return random.choice(transceivers)


def _get_ports_for_module(module_name):
    with allure.step(f"Get ports for module {module_name}"):
        ports = Port.get_list_of_ports()
        if TransceiversConsts.TRANSCEIVERS_ELS in module_name:
            platform = Platform()
            port_mapping = OutputParsingTool.parse_json_str_to_dictionary(
                platform.transceiver.show(module_name)).get_returned_value()['port-mapping'].keys()
            ports_for_module = [port for port in ports if port.name in port_mapping]
        else:
            ports_for_module = [port for port in ports if f"{module_name}p" in port.name]
        return ports_for_module


def _count_module_index(module_name, device):
    module_index = int(''.join(c for c in module_name if c.isdigit()))
    if TransceiversConsts.TRANSCEIVERS_ELS in module_name:
        module_index += 71  # [els1,...,els18] -> [module_index 72,...,module_index 89]
    else:
        module_index -= 1
        if device.module_offset:
            offset = device.module_offset
            module_index %= offset
    return module_index


def _get_module_with_desire_state(engines, devices, platform, desired_state):
    with allure.step(f"Get module with state {desired_state}"):
        module_under_test = _get_module_with_status(platform, PlatformConsts.INSERTED)
        assert module_under_test, f"No module with state {desired_state} found"
        ports = _get_ports_for_module(module_under_test)
        assert ports, "Should be at least one port for module"
        mst_dev_name = IbInterfaceTool.get_mst_dev_name(engine=engines.dut, module_name=module_under_test,
                                                        port_name=ports[0].name)
        module_index = _count_module_index(module_under_test, devices.dut)

    return module_under_test, ports, mst_dev_name, module_index
