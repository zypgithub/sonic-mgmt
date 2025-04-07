import logging
import re
from datetime import datetime, timedelta

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, ActionConsts, SystemConsts, PlatformConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import random_api
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.bmc
@pytest.mark.parametrize(['test_api', 'force_str'], [[ApiType.NVUE, ""],
                                                     [random_api(), "immediate"],
                                                     [random_api(), "force"],
                                                     [ApiType.NVUE, "force immediate"]  # todo openapi multiple flags
                                                     ])
def test_power_cycle_system(engines, devices, test_name, test_api, force_str):
    """Test for `nv action power-cycle system [force] [immediate]`. See documentation of _test functions below."""
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
    start_time = datetime.now()

    with allure.step("Run power-cycle command and measure duration"):
        system_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
        result_obj, duration = OperationTime.save_duration(ActionConsts.POWER_CYCLE, force_str, test_name,
                                                           do_power_cycle, force_str)
        result_obj.verify_result()
        logger.info(f"power-cycle took {duration} seconds")

    with allure.step("Assert that power-cycle happened"):
        bmc_uptime = get_bmc_uptime(engines.dut)
        assert bmc_uptime.seconds < (datetime.now() - start_time).total_seconds(), \
            f"Power-cycle did not actually happen: {bmc_uptime.seconds=}"

    with allure.step("Check reboot cause"):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show(SystemConsts.REBOOT_REASON)
                                                                ).get_returned_value()
        reboot_time = ClockTools.parse_datetime(output["gentime"])
        assert reboot_time >= system_time, \
            f"power-cycle command sent at {system_time.strftime('%H:%M:%S')} but 'show system reboot' shows {output}"
        if not is_redmine_issue_active([4247423])[0]:
            assert output["reason"] == 'Power Cycle'
            assert output["user"] == 'admin'

    with allure.step("Assert power-cycle duration was not too long"):
        OperationTime.verify_operation_time(duration, devices.dut.power_cycle_type).verify_result()


def _test_command_not_supported(engines, devices, test_name, test_api, force_str):
    """
    - `nv list-commands` doesn't show power-cycle
    - `nv action power-cycle system [force]` commands don't work
    """
    engine = engines.dut
    if test_api == ApiType.NVUE and not is_bug_active(4105725):
        with allure.independent_step("Verify command doesn't exist in command list"):
            output = NvueGeneralCli.search_in_list_commands(engine, ActionConsts.POWER_CYCLE)
            assert not output, "The following commands should not exist: " + output

    with allure.independent_step("Verify command doesn't work"):
        System().action(ActionConsts.POWER_CYCLE, param_name=force_str).verify_result(should_succeed=False)


def do_power_cycle(force_str: str) -> ResultObj:
    return System().action(ActionConsts.POWER_CYCLE, expect_reboot=True, param_name=force_str, output_format=None,
                           expected_output='System will power cycle in a few seconds')


def get_bmc_uptime(engine: LinuxSshEngine) -> timedelta:
    uptime_output = ssh_to_bmc("uptime", engine)
    uptime_match = re.search(r' up\s+([^,]+),', uptime_output)
    uptime_str, = uptime_match.groups()
    uptime = None
    for time_format in ["%H:%M", "%M min", "%S sec"]:
        try:
            uptime = datetime.strptime(uptime_str, time_format)
            break
        except ValueError:
            pass
    if uptime is None:
        raise Exception(uptime_str)
    return timedelta(hours=uptime.hour, minutes=uptime.minute, seconds=uptime.second)


def ssh_to_bmc(cmd: str, engine: LinuxSshEngine) -> str:
    """Runs cmd over ssh to the BMC and returns the output"""
    host = f"{PlatformConsts.BMC_LOGIN}@{PlatformConsts.BMC_INTERNAL_IP}"
    password_prompt = f"{host}'s password:"
    bmc_password = TpmTool(engine).get_bmc_admin_password_from_tpm()
    output = engine.run_cmd_set([f"ssh -o StrictHostKeyChecking=no {host} {cmd}", bmc_password],
                                patterns_list=[re.escape(password_prompt)])
    return output
