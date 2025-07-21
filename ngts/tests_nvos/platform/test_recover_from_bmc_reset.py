import logging
from datetime import datetime
from time import sleep
import pytest

from ngts.nvos_constants.constants_nvos import SystemConsts, PlatformConsts, FansConsts, HealthConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.DeviceLogTool import grep_log_lines_after_datetime
from ngts.nvos_tools.infra.DutUtilsTool import wait_for_specific_regex_in_logs
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.nvos_tools.Devices.IbDevice import JulietNonScaleoutSwitchGB300

logger = logging.getLogger()


BMC_ON_LOG_LINE = r"BMC status changed from .* to Ok"
LOG_DELAY = 150
CPU_MAX_UTILIZATION = 26.0
BMC_LOG_LINES_MAX = 30


@pytest.mark.disable_loganalyzer
def test_recover_from_bmc_reset(engines, devices, topology_obj, loganalyzer):
    if is_bug_active(4359149) and isinstance(devices.dut, JulietNonScaleoutSwitchGB300):
        pytest.skip("Skipping test because we have a bug in bmc reset factory for gb300.")
    system = System()
    platform = Platform()
    engine = engines.dut

    with allure.step("Add health.err to loganalyzer ignore list"):
        for log_analyzer_instance in (loganalyzer or {}).values():
            log_analyzer_instance.ignore_regex.append('health.err')

    with allure.step("Assert BMC status is ok before starting test"):
        initial_bmc_status = OutputParsingTool.parse_json_str_to_dictionary(
            platform.inventory.show('BMC')).get_returned_value()
        assert initial_bmc_status[PlatformConsts.INV_STATE] == FansConsts.STATE_OK

    with allure.step("Get health issues before starting test"):
        initial_health_issues = OutputParsingTool.parse_json_str_to_dictionary(
            system.health.show()).get_returned_value()[HealthConsts.ISSUES].keys()

    with allure.step("Reset BMC"):
        start_time = datetime.now()
        BmcTool.reset(engine)

    try:
        with allure.step("Wait for log line indicating BMC is back on"):
            wait_for_specific_regex_in_logs(engine, BMC_ON_LOG_LINE, LOG_DELAY)
            logger.info("waiting 2:30 minutes for system to recover...")
            sleep(150)

        with allure.step("Validating BMC reachability"):
            try:
                BmcTool.get_bmc_ip_addresses(engines, topology_obj)
            except Exception:
                raise Exception("Unable to reach BMC")

        with allure.step("Assert BMC status is ok"):
            final_bmc_status = OutputParsingTool.parse_json_str_to_dictionary(
                platform.inventory.show('BMC')).get_returned_value()
            assert final_bmc_status == initial_bmc_status

        with allure.step("Check general system status"):
            with allure.independent_step("Assert logs aren't flooded with BMC error messages"):
                bmc_log_lines = grep_log_lines_after_datetime(engine, 'bmc', start_time)
                assert len(bmc_log_lines) < BMC_LOG_LINES_MAX, (
                    f'BMC reset causes log flooding: logs contain {len(bmc_log_lines)} lines regarding BMC, more '
                    f'than the threshold of {BMC_LOG_LINES_MAX}:\n\n' +
                    '\n'.join(bmc_log_lines)
                )

            with allure.independent_step("Assert health ok"):
                final_health_issues = OutputParsingTool.parse_json_str_to_dictionary(
                    system.health.show()).get_returned_value()[HealthConsts.ISSUES].keys()
                assert set(final_health_issues) <= set(initial_health_issues)

            with allure.independent_step("Assert show-firmware command is not broken"):
                firmware_output = platform.firmware.show("BMC")
                assert "actual-firmware" in firmware_output
                # test_show_platform_firmware(engines, devices, test_api, output_format)

            with allure.independent_step("Assert CPU usage"):
                cpu_output = OutputParsingTool.parse_json_str_to_dictionary(system.show("cpu")).get_returned_value()
                cpu_utilization = cpu_output[SystemConsts.CPU_TOTAL_UTILIZATION_KEY]
                assert cpu_utilization <= CPU_MAX_UTILIZATION

    except Exception:
        with allure.step("Failed to recover from BMC reset. Fixing device by remote-reboot."):
            recover_dut_with_remote_reboot(topology_obj, engines)
        raise
