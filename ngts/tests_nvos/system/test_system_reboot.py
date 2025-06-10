import logging
import time

import pytest

from retry import retry
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, RebootConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool, RebootParams, ping_device
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.tools.test_utils import allure_utils as allure
from retry.api import retry_call
from infra.tools.redmine.redmine_api import is_redmine_issue_active

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.nvos_build
def test_reboot_command(engines, devices, test_name):
    """
    Test flow:
        1. run nv action reboot system
    """
    system = System(None)
    expected_reason, expected_user = RebootConsts.REBOOT_REASON_MAP[RebootConsts.COLD]

    with allure.step('Clear system events to remove older reboot system events'):
        system.events.action(ActionConsts.CLEAR)

    with allure.step('Run nv action reboot system'):
        result_obj, duration = OperationTime.save_duration('reboot', '', test_name, system.reboot.action_reboot)
        OperationTime.verify_operation_time(duration, devices.dut.reboot_type).verify_result()

    with allure.step("Check system reboot output"):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show()).get_returned_value()
        assert "reason" in output.keys(), "'reason' not in the output"
        assert "history" in output.keys(), "'history' not in the output"

        with allure.step("Check system reboot reason output"):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.reason.show()).get_returned_value()
            ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output, ["gentime", "reason", "user"]).verify_result()

        with allure.step("Check system reboot history output"):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.history.show()).get_returned_value()
            if output and len(output.keys()) > 0:
                ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output[list(output.keys())[0]],
                                                                                  ["gentime", "reason", "user"]).verify_result()

        with allure.step("Check reboot cause"):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.reason.show()).get_returned_value()
            assert 'reboot' in output["reason"], "reboot not found in show reboot output"
            assert 'admin' in output["user"], f"reboot user is not 'admin' as expected (actual - {output['user']})"

    validate_reboot_reason_and_user(system, expected_reason, expected_user)


@pytest.mark.system
def test_reboot_command_force(engines, devices, test_name, random_api):
    """
    Test flow:
        1. run nv action reboot system force
    """
    TestToolkit.tested_api = random_api
    system = System(None)
    with allure.step('Run nv action reboot system mode force'):
        result_obj, duration = OperationTime.save_duration('reboot', '', test_name,
                                                           system.reboot.action_reboot, params='force')
        OperationTime.verify_operation_time(duration, devices.dut.reboot_type).verify_result()


@pytest.mark.system
def test_reboot_command_bad_flow(engines, devices):
    """
    Test flow:
        1. run nv action reboot system --type fast
        2. expected message: not supported for IB
        3. run nv action reboot system --type warm
        4. expected message: not supported for IB
    """
    system = System()
    substring = 'Error: Invalid parameter'
    invalid_command = 'Error: Invalid Command:'
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

    with allure.step("test non-existing mode"):
        output = engines.dut.run_cmd('nv action reboot system mode non existing mode')
        ValidationTool.verify_expected_output(output, invalid_command, True)

        with allure.step("test pruned warm mode"):
            output = engines.dut.run_cmd('nv action reboot system mode warm')
            ValidationTool.verify_expected_output(output, invalid_command, True)

    if RebootConsts.POWER_CYCLE not in devices.dut.supported_commands:
        with (allure.step("action power-cycle not supported. Test negative flow")):
            output = engines.dut.run_cmd('nv action reboot system mode power-cycle')
            ValidationTool.verify_expected_output(output, RebootConsts.POWER_CYCLE_NOT_SUPPORTED_ERR_MSG, True)


@pytest.mark.system
@pytest.mark.parametrize('mode', RebootConsts.DEFAULT_MODES)
def test_reboot_mode(engines, devices, topology_obj, mode, random_api, test_name):
    if mode == RebootConsts.POWER_CYCLE and mode not in devices.dut.supported_commands:
        pytest.skip(f"{mode} not supported")
    system = System()
    TestToolkit.tested_api = ApiType.NVUE

    try:
        with allure.step('Clear system events to remove older reboot system events'):
            system.events.action(ActionConsts.CLEAR)

        result_obj = _reboot_system_by_mode(engines, devices, test_name, topology_obj, mode)
        result_obj.verify_result()
        expected_reason, expected_user = RebootConsts.REBOOT_REASON_MAP[mode]

        validate_reboot_reason_and_user(system, expected_reason, expected_user)

        with allure.step("Verify reboot time is within expected range"):
            OperationTime.verify_operation_time(result_obj.duration, devices.dut.reboot_type).verify_result()

    finally:
        if not ping_device(engines.dut.ip):
            logger.info("system is off and will now remote reboot the switch")
            NvueGeneralCli(TestToolkit.engines.dut).remote_reboot_nvue(topology_obj)


@pytest.mark.system
def test_reboot_via_psu_off(engines, devices, topology_obj):
    """
    Test flow:
        1. run remote reboot script to turn off PSU and turn on the PSU
        2. Validate reboot reason in system events
    """
    system = System()
    expected_reason, expected_user = RebootConsts.REBOOT_REASON_MAP[RebootConsts.PSU_OFF]

    with allure.step('Clear system events to remove older reboot system events'):
        system.events.action(ActionConsts.CLEAR)

    with allure.step("Get name from NOGA"):
        noga_query_data = topology_obj.players['dut']['attributes'].noga_query_data['attributes']
        dhcp_hostname = noga_query_data['Common']['Name'] or noga_query_data['Specific']['dhcp_hostname']

    with allure.step("Reboot the system using PSU off-on"):
        DutUtilsTool.dut_psu_control(engines, topology_obj, dhcp_hostname=dhcp_hostname)

    res_obj = DutUtilsTool.wait_on_system_reboot(engines.dut, device=devices.dut, verify_final_result=False)
    assert res_obj.result, 'System reboot failed'

    validate_reboot_reason_and_user(system, expected_reason, expected_user)


@retry(Exception, tries=6, delay=10)
def validate_reboot_reason_and_user(system, expected_reason: str, expected_user: str):
    with allure.step("Check reboot reason event in system events"):
        reboot_reason, reboot_user = OutputParsingTool.get_reboot_reason_and_user_from_system_events(system)

        with allure.independent_step("Validate reboot reason"):
            assert expected_reason in reboot_reason, \
                f"Reboot reason is '{reboot_reason}' instead of expected '{expected_reason}'"

        with allure.independent_step("Validate reboot user"):
            assert expected_user in reboot_user, \
                f"Reboot user is '{reboot_user}' instead of expected '{expected_user}'"


def _reboot_system_by_mode(engines, devices, test_name, topology_obj, mode):
    system = System()
    dhcp_hostname = ''

    if mode == RebootConsts.HALT:
        noga_data = topology_obj.players['dut']['attributes'].noga_query_data['attributes']
        dhcp_hostname = noga_data['Common']['Name'] or noga_data['Specific']['dhcp_hostname']

    # Run reboot
    with allure.step(f"Rebooting system with mode: {mode}"):
        reboot_params = RebootParams()
        reboot_params.should_wait_till_system_ready = mode != RebootConsts.HALT
        reboot_result_obj, _ = OperationTime.save_duration(f"reboot {mode}", '', test_name,
                                                           system.action_reboot,
                                                           flags=mode,
                                                           reboot_params=reboot_params)
        time.sleep(10)

    # PSU recovery for halt
    if mode == RebootConsts.HALT:
        with allure.step("Power the system back on via PSU"):
            DutUtilsTool.dut_psu_control(engines, topology_obj, dhcp_hostname=dhcp_hostname)

        with allure.step("Wait for system to be ready"):
            result_obj = DutUtilsTool.wait_on_system_reboot(engines.dut, device=devices.dut, verify_final_result=False)
            assert result_obj.result, f"System did not come back after reboot mode {mode}"

    return reboot_result_obj


@pytest.mark.platform
def test_lspci_width(engines, devices):
    """
    The purpose of this function is to check if 2 parameters (LnkSta, LnkCap) are valid.
    """
    with allure.step("Running lspci command to find Infiniband controllers"):
        lines_devices = engines.dut.run_cmd("sudo lspci | grep 'Infiniband controller: Mellanox Technologies Device'")
        actual_devices = lines_devices.split("\n")

    with allure.step("Validating the number of detected devices"):
        assert len(actual_devices) == devices.dut.asic_amount, \
            f"Actual number of devices: {len(actual_devices)}, Expected: {devices.dut.asic_amount}"

    for device in actual_devices:
        device_num_str = device.split(" ")[0]

        with allure.step(f"Fetching LnkCap for device {device_num_str}"):
            bash_cmd_cap = f"sudo lspci -vv -s {device_num_str} | grep LnkCap:"
            line_cap = engines.dut.run_cmd(bash_cmd_cap)
            cap_arr = line_cap.split(' ')

        with allure.step(f"Fetching LnkSta for device {device_num_str}"):
            bash_cmd_sta = f"sudo lspci -vv -s {device_num_str} | grep LnkSta:"
            line_sta = engines.dut.run_cmd(bash_cmd_sta)
            sta_arr = line_sta.split(' ')

        with allure.step(f"Validating LnkCap and LnkSta for device {device_num_str}"):
            validate_lspci_status(engines, cap_arr, sta_arr, line_sta, line_cap)


def validate_lspci_status(engines, cap_arr, sta_arr, line_sta, line_cap):
    with allure.step("Checking if cap_arr and sta_arr are non-empty"):
        assert sta_arr, f"sta_arr is empty: {sta_arr}"
        assert cap_arr, f"cap_arr is empty: {cap_arr}"

    with allure.step("Validating speed in LnkCap and LnkSta"):
        number_gts_sta = get_number_gts(sta_arr, "")
        number_gts_cap = get_number_gts(cap_arr, "")
        assert number_gts_sta, f"The string number_gts_sta is empty: {cap_arr}"
        assert number_gts_cap, f"The string number_gts_cap is empty: {sta_arr}"
        assert number_gts_cap in number_gts_sta, \
            f"Speed NUMBER GT/s mismatch: LnkCap={number_gts_cap}, LnkSta={number_gts_sta}"

    with allure.step("Validating Width values in LnkCap and LnkSta"):
        x_number_cap = get_x_number(cap_arr, "")
        assert x_number_cap, f"Width x<Number> not found in line_cap: {line_cap}, cap_arr: {cap_arr}"
        x_number_sta = get_x_number(sta_arr, "")
        assert x_number_sta, "Width x<Number> not found in LnkSta"
        assert x_number_cap == x_number_sta, \
            f"Width mismatch: LnkCap={x_number_cap}, LnkSta={x_number_sta}"

    with allure.step("Checking the number of 'ok' occurrences in LnkSta"):
        ok_count = get_ok_count(sta_arr)
        assert ok_count == 2, f"Unexpected 'ok' count in LnkSta: {line_sta}, found: {ok_count}"


def get_ok_count(sta_arr):
    """
    Return the number of times "ok" appears in LnkSta.
    """
    with allure.step("Counting 'ok' occurrences in sta_arr"):
        ok_count = sum(1 for word in sta_arr if "ok" in word)
        return ok_count


def get_number_gts(arr, number_gts):
    """
    Return GT/s number.
    """
    with allure.step("Extracting GT/s value from array"):
        for word in arr:
            if "GT/s" in word:
                number_gts = word[:-1] if word.endswith(',') else word
                return number_gts


def get_x_number(arr, x_number):
    """
    Return x number.
    """
    with allure.step("Extracting Width x<number> from array"):
        for i in range(len(arr)):
            if "Width" in arr[i]:
                x_number = arr[i + 1]
                x_number = x_number[:-1] if x_number.endswith(',') else x_number
                return x_number
