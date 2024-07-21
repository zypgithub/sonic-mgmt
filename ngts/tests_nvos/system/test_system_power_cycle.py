import logging
import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, ActionConsts, SystemConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.bmc
@pytest.mark.parametrize(['test_api', 'force_str'], [[ApiType.NVUE, ""], [ApiType.NVUE, "force"],
                                                     [ApiType.OPENAPI, "force"]])
def test_power_cycle_system(engines, devices, test_name, test_api, force_str):
    """Test for `nv action power-cycle system [force]`. See documentation of _test functions below."""
    TestToolkit.tested_api = test_api
    if ActionConsts.POWER_CYCLE in devices.dut.supported_commands:
        with allure.step("Test action power-cycle"):
            _test_command_supported(engines, devices, test_name, test_api, force_str)
    else:
        with allure.step("action power-cycle not supported. Test negative flow"):
            _test_command_not_supported(engines, devices, test_name, test_api, force_str)


def _test_command_supported(engines, devices, test_name, test_api, force_str):
    """
    - Make some config change (in order to verify it is removed after the reset)
    - nv action power-cycle system [force]
    - Verify the system reboots
    - Verify the reboot was complete in reasonable time
    - Verify the correct reboot-cause was provided
    - Verify the config-change from stage 1 was not saved
    """
    system = System()
    interface = MgmtPort("eth1")
    with allure.step("Make some config change"):
        obj, param, value = interface.interface, "description", '"NVOS TESTS"'
        original_value = OutputParsingTool.parse_json_str_to_dictionary(obj.show()).get_returned_value().get(param)
        obj.set(op_param_name=param, op_param_value=value, apply=True).verify_result(should_succeed=True)

    try:
        with allure.step("Run power-cycle command and measure duration"):
            result_obj, duration = OperationTime.save_duration(ActionConsts.POWER_CYCLE, force_str, test_name,
                                                               do_power_cycle, force_str)
            result_obj.verify_result()
            logger.error(duration)
            OperationTime.verify_operation_time(duration, ActionConsts.POWER_CYCLE).verify_result()

        with allure.step("Check reboot cause"):
            # todo: currently it shows reason unknown
            OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show(SystemConsts.REBOOT_REASON)).get_returned_value()
            OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show(SystemConsts.REBOOT_HISTORY)).get_returned_value()

        with allure.step("Assert config change was reverted"):
            current_param_value = OutputParsingTool.parse_json_str_to_dictionary(obj.show()).get_returned_value().get(param)
            assert current_param_value == original_value

    except Exception:
        obj.set(op_param_name=param, op_param_value=original_value, apply=True).verify_result(should_succeed=True)
        raise


def _test_command_not_supported(engines, devices, test_name, test_api, force_str):
    """
    - `nv list-commands` doesn't show power-cycle
    - `nv action power-cycle system [force]` commands don't work
    """
    engine = engines.dut
    if test_api == ApiType.NVUE:
        with allure.step("Verify command doesn't exist in command list"):
            output = NvueGeneralCli.search_in_list_commands(engine, ActionConsts.POWER_CYCLE)
            assert not output, "The following commands should not exist: " + output

    with allure.step("Verify command doesn't work"):
        do_power_cycle(force_str=force_str).verify_result(should_succeed=False)


def do_power_cycle(force_str: str) -> ResultObj:
    return System().action(ActionConsts.POWER_CYCLE, expect_reboot=True, param_name=force_str)
