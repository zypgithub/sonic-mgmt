import logging
from time import sleep

from ngts.nvos_constants.constants_nvos import HealthConsts, ApiType, SystemConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.DutUtilsTool import wait_for_specific_regex_in_logs
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.platform.test_platform_firmware import test_show_platform_firmware
from ngts.tests_nvos.platform.test_platform_inventory import InventoryBmcTest
from ngts.tests_nvos.system.test_system_health import verify_health_status_and_led
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot

logger = logging.getLogger()


BMC_ON_LOG_LINE = r"BMC status changed from .* to Ok"
LOG_DELAY = 150
CPU_MAX_UTILIZATION = 20.0
BMC_LOG_LINES_MAX = 30


def test_recover_from_bmc_reset(engines, devices, topology_obj):
    system = System()
    platform = Platform()
    engine = engines.dut
    test_api = ApiType.NVUE
    output_format = 'auto'

    with allure.step("Assert BMC status is ok before starting test"):
        assert_bmc_status_ok(engines, devices)

    with allure.step("Assert health ok before starting test"):
        verify_health_status_and_led(system, HealthConsts.OK)

    with allure.step("Reset BMC"):
        BmcTool.reset(engine)

    try:
        with allure.step("Wait for log line indicating BMC is back on"):
            wait_for_specific_regex_in_logs(engine, BMC_ON_LOG_LINE, LOG_DELAY)
            logger.info("waiting 60 seconds...")
            sleep(60)

        with allure.step("Assert BMC status is ok"):
            assert_bmc_status_ok(engines, devices)

    except Exception:
        with allure.step("BMC failed to reset or to recover. Fixing by remote-reboot."):
            recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)
        raise

    with allure.step("Check general system status"):
        with allure.independent_step("Assert health ok"):
            verify_health_status_and_led(system, HealthConsts.OK)

        with allure.independent_step("Assert show-firmware command is not broken"):
            firmware_output = platform.firmware.show("BMC")
            assert "actual-firmware" in firmware_output
            # test_show_platform_firmware(engines, devices, test_api, output_format)

        with allure.independent_step("Assert CPU usage"):
            cpu_output = OutputParsingTool.parse_json_str_to_dictionary(system.show("cpu")).get_returned_value()
            cpu_utilization = cpu_output[SystemConsts.CPU_UTILIZATION_KEY]
            assert cpu_utilization <= CPU_MAX_UTILIZATION

        with allure.independent_step("Assert logs aren't flooded with BMC error messages"):
            bmc_log_lines = system.log.show(op_param=" | grep -ie bmc").splitlines()
            assert len(bmc_log_lines) < BMC_LOG_LINES_MAX


def assert_bmc_status_ok(engines, devices):
    InventoryBmcTest.test_show_item(engines, devices, ApiType.NVUE)
