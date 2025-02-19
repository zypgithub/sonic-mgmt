import logging
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.tools.test_utils import allure_utils as allure
from retry.api import retry_call


@pytest.mark.system
@pytest.mark.nvos_build
def test_reboot_command(engines, devices, test_name):
    """
    Test flow:
        1. run nv action reboot system
    """
    system = System(None)
    expected_reboot_reason = SystemConsts.REBOOT_REASON_REBOOT

    with allure.step('Run nv action reboot system'):
        result_obj, duration = OperationTime.save_duration('reboot', '', test_name, system.reboot.action_reboot)
        OperationTime.verify_operation_time(duration, devices.dut.reboot_type).verify_result()

    with allure.step("Check system reboot output"):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show()).get_returned_value()
        assert "reason" in output.keys(), "'reason' not in the output"
        assert "history" in output.keys(), "'history' not in the output"

        with allure.step("Check system reboot reason output"):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show("reason")).get_returned_value()
            ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output, ["gentime", "reason", "user"]).verify_result()

        with allure.step("Check system reboot history output"):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show("history")).get_returned_value()
            if output and len(output.keys()) > 0:
                ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output[list(output.keys())[0]],
                                                                                  ["gentime", "reason", "user"]).verify_result()

        with allure.step("Check reboot cause"):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show(SystemConsts.REBOOT_REASON)
                                                                    ).get_returned_value()
            assert output["reason"] == 'reboot'
            assert output["user"] == 'admin'

    with allure.step("Check reboot reason event in system events"):
        reboot_reason = OutputParsingTool.get_reboot_reason_system_events(system)
        assert expected_reboot_reason in reboot_reason, 'Reboot reason is {} instead of {}'.\
            format(reboot_reason, expected_reboot_reason)


@pytest.mark.system
def test_reboot_command_immediate(engines, devices, test_name):
    """
    Test flow:
        1. run nv action reboot system mode immediate
    """
    system = System(None)
    with allure.step('Run nv action reboot system mode immediate'):
        result_obj, duration = OperationTime.save_duration('reboot', 'immediate', test_name,
                                                           system.reboot.action_reboot, params='immediate')
        OperationTime.verify_operation_time(duration, devices.dut.reboot_type).verify_result()


@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_reboot_command_force(engines, devices, test_name, test_api):
    """
    Test flow:
        1. run nv action reboot system mode force
    """
    TestToolkit.tested_api = test_api
    system = System(None)
    with allure.step('Run nv action reboot system mode force'):
        result_obj, duration = OperationTime.save_duration('reboot', 'force', test_name,
                                                           system.reboot.action_reboot, params='force')
        OperationTime.verify_operation_time(duration, devices.dut.reboot_type).verify_result()


@pytest.mark.system
def test_reboot_command_type(engines):
    """
    Test flow:
        1. run nv action reboot system --type fast
        2. expected message: not supported for IB
        3. run nv action reboot system --type warm
        4. expected message: not supported for IB
    """
    substring = 'Error: Invalid parameter'
    err_message = 'Reboot types should not be supported in NVOS'

    with allure.step('Run nv action reboot system type fast'):
        list_commands = ['nv action reboot system type fast', 'y']
        output = engines.dut.send_config_set(list_commands, exit_config_mode=False, cmd_verify=False,
                                             enter_config_mode=False)
        ValidationTool.verify_substring_in_output(output, substring, err_message, True)

    with allure.step('Run nv action reboot system type warm'):
        list_commands = ['nv action reboot system type warm', 'y']
        output = engines.dut.send_config_set(list_commands, exit_config_mode=False, cmd_verify=False,
                                             enter_config_mode=False)
        ValidationTool.verify_substring_in_output(output, substring, err_message, True)


@pytest.mark.system
def test_reboot_halt(engines, devices, test_name, topology_obj):
    """
    Test flow:
        1. run remote reboot script to turn off PSU and turn on the PSU
        2. Validate reboot reason in system events
    """
    system = System()
    expected_reboot_reason = SystemConsts.REBOOT_REASON_POWER_LOSS
    dhcp_hostname = ''

    with allure.step("Get name from NOGA"):
        noga_query_data = topology_obj.players['dut']['attributes'].noga_query_data['attributes']
        dhcp_hostname = noga_query_data['Common']['Name'] or noga_query_data['Specific']['dhcp_hostname']

    with allure.step('Run nv action reboot system'):
        OperationTime.save_duration('reboot halt', '', test_name, system.reboot.action_reboot, params='halt',
                                    should_wait_till_system_ready=False)
        # Wait for system to halt
        time.sleep(10)

    with allure.step('Power the system back on via PSU'):
        DutUtilsTool.dut_psu_control(engines, topology_obj, dhcp_hostname=dhcp_hostname)

    with allure.step('Wait for the system to be ready'):
        res_obj = DutUtilsTool.wait_on_system_reboot(engines.dut, device=devices.dut, verify_final_result=False)
        assert res_obj.result, 'System did not come back up'

    with allure.step("Check reboot reason event in system events"):
        # Wait for newer system events to be generated
        time.sleep(60)
        reboot_reason = OutputParsingTool.get_reboot_reason_system_events(system)
        assert expected_reboot_reason in reboot_reason, 'Reboot reason is {} instead of {}'.\
            format(reboot_reason, expected_reboot_reason)


@pytest.mark.system
def test_reboot_via_psu_off(engines, devices, topology_obj):
    """
    Test flow:
        1. run remote reboot script to turn off PSU and turn on the PSU
        2. Validate reboot reason in system events
    """
    system = System()
    expected_reboot_reason = SystemConsts.REBOOT_REASON_POWER_LOSS
    dhcp_hostname = ''

    with allure.step("Get name from NOGA"):
        noga_query_data = topology_obj.players['dut']['attributes'].noga_query_data['attributes']
        dhcp_hostname = noga_query_data['Common']['Name'] or noga_query_data['Specific']['dhcp_hostname']

    with allure.step("Reboot the system using PSU off-on"):
        DutUtilsTool.dut_psu_control(engines, topology_obj, dhcp_hostname=dhcp_hostname)

    res_obj = DutUtilsTool.wait_on_system_reboot(engines.dut, device=devices.dut, verify_final_result=False)
    assert res_obj.result, 'System reboot failed'

    with allure.step("Check reboot reason event in system events"):
        reboot_reason = OutputParsingTool.get_reboot_reason_system_events(system)
        retry_call(_help_validate_reboot_reason, [expected_reboot_reason, reboot_reason], exceptions=AssertionError,
                   tries=6, delay=10)


def _help_validate_reboot_reason(expected_reboot_reason, reboot_reason):
    assert expected_reboot_reason in reboot_reason, 'Reboot reason is {} instead of {}'.\
        format(reboot_reason, expected_reboot_reason)
