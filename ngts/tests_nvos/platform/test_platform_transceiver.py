import logging
import time

import pytest

from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts, IbInterfaceConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.LinuxCmdBuilderTool import LinuxCmdBuilderTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegisterTool import RegisterTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType

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
def test_transceiver_status_unplug(engines, devices, test_api, asic_conf_dict):
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
        module_under_test = _get_module_with_status(platform, PlatformConsts.INSERTED)
        ports = _get_ports_for_module(module_under_test)
        mst_dev_name = _get_mst_dev_name(engines, ports, asic_conf_dict)
        assert module_under_test, f"No module with state {desired_state} found"
        module_index = int(
            ''.join(c for c in module_under_test if c.isdigit())) - 1  # module start from 0, while sw from 1

    try:
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')
        _simulate_unplug_event(engines.dut, devices.dut, module_index, mst_dev_name)
        _verify_link_state_down(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Removed')

    finally:
        _simulate_plugin_event(engines.dut, devices.dut, module_index, mst_dev_name)
        _verify_link_state_up(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')


def _get_mst_dev_name(engines, ports, asic_conf_dict):
    assert ports, "No ports were found"
    with allure.step(f"Find correct mst_dev_name for port"):
        port_name = ports[0].name
        output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
            Fae(port_name=port_name).port.interface.show()).get_returned_value()
        asic_number = output_fae_port.get(IbInterfaceConsts.PRIMARY_ASIC, "0")
        assert asic_number is not None, "primary-asic is None"
        asic_dev_id_number = _get_asic_dev_id_number(asic_number)
        asic_mapping_number = asic_conf_dict[asic_dev_id_number]
        cmd = LinuxCmdBuilderTool("sudo mst status -v").grep("pciconf").grep(f"{asic_mapping_number}").awk_print("2").build()
        mst_dev_name = engines.dut.run_cmd(cmd)
        return mst_dev_name


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_status_with_reboot(engines, devices, test_api, asic_conf_dict):
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
        module_under_test = _get_module_with_status(platform, PlatformConsts.INSERTED)
        ports = _get_ports_for_module(module_under_test)
        mst_dev_name = _get_mst_dev_name(engines, ports, asic_conf_dict)
        assert module_under_test, f"No module with state {desired_state} found"
        module_index = int(
            ''.join(c for c in module_under_test if c.isdigit())) - 1  # module start from 0, while sw from 1

    try:
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')

        _simulate_unplug_event(engines.dut, devices.dut, module_index, mst_dev_name)
        _verify_link_state_down(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Removed')

        with allure.step("Reboot the system"):
            system.reboot.action_reboot(engine=engines.dut, device=devices.dut)

        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')

    finally:
        _simulate_plugin_event(engines.dut, devices.dut, module_index, mst_dev_name)
        _verify_link_state_up(ports)
        _verify_transceiver_status(platform, transceiver_id=module_under_test, expected_module_status='Inserted')


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
                                                          expected_value=expected_module_status) \
            .verify_result()

    with allure.step("Verify error status exists"):
        module_status = transceiver_output[PlatformConsts.TRANSCEIVER_STATUS].strip()
        error_status = transceiver_output[PlatformConsts.TRANSCEIVER_ERROR_STATUS].strip()
        assert error_status in MODULE_STATUS_DICT[
            module_status], f"module-error-status is in not allowed state: {error_status}"

    with allure.step(f"Check {PlatformConsts.TRANSCEIVER_ERROR_STATUS} has correct value {expected_error_status}"):
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=transceiver_output,
                                                          field_name=PlatformConsts.TRANSCEIVER_ERROR_STATUS,
                                                          expected_value=expected_error_status) \
            .verify_result()


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


def _simulate_plugin_event(engine, device, module_index, mst_dev_name):
    with allure.step(f"Simulate plugin event for module {module_index}"):
        admin_status = "1"  # The code to simulate plug event
        RegisterTool.update_pmaos_register(engine, device, mst_dev_name=mst_dev_name,
                                           admin_status=admin_status, module_index=module_index)
        time.sleep(40)


def _simulate_unplug_event(engine, device, module_index, mst_dev_name):
    with allure.step(f"Simulate unplug event for module {module_index}"):
        admin_status = "0xe"  # The code to simulate unplug event
        RegisterTool.update_pmaos_register(engine, device, mst_dev_name=mst_dev_name,
                                           admin_status=admin_status, module_index=module_index)
        time.sleep(2)


def _get_module_with_status(platform, status):
    with allure.step(f"Find {status} module"):
        transceivers_output = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show()).get_returned_value()
        for name, transceiver in transceivers_output.items():
            if "sw" in name and transceiver[PlatformConsts.TRANSCEIVER_STATUS] == status:
                return name
        assert False, f"No transceiver with status {status} found"


def _get_ports_for_module(module_name):
    with allure.step(f"Get ports for module {module_name}"):
        ports = Port.get_list_of_ports()
        ports_for_module = [port for port in ports if f"{module_name}p" in port.name]
        return ports_for_module


def _get_asic_dev_id_number(asic_number):
    return f"DEV_ID_ASIC_{asic_number}"
