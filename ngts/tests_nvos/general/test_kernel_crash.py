
import pytest
import logging
import random
import time
import re
from datetime import datetime
from ngts.constants.constants import BugHandlerConst
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_constants.constants_nvos import OperationTimeConsts, NvosConst
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
@pytest.mark.timeout(10 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_kernel_crash(engines, devices, topology_obj, test_api):
    """
        @summary: Test simulates kernal crash and verifies behavior
        Test flow:
        1. Simulate kernel crash
        2. Wait until system is ready
        3. Sleep until tech-support file is generated
        4. Verify in logs that kernel crash was detected and tech-support file was generated
        5. Get generated tech-support and verify it's birth-time was in the last 6 mins
        6. Get kdump files in tech-support
        7. Verify expected kdump files in tech-support
    """
    TestToolkit.tested_api = test_api
    system = System()
    with allure.step("Simulate kernel crash"):
        start_time = datetime.strptime(ClockTools.get_local_time_from_show_system_date_time_output(system.datetime.show()),
                                       BugHandlerConst.TIMESTAMP_FORMATS[4])
        serial_engine: PexpectSerialEngine = ConnectionTool.create_serial_connection(topology_obj, devices)
        serial_engine.run_cmd("echo 1 | sudo tee /proc/sys/kernel/sysrq")
        serial_engine.run_cmd("echo c | sudo tee /proc/sysrq-trigger")
    with allure.step("Wait for system is ready in serial"):
        DutUtilsTool.wait_on_system_reboot(engines.dut)
        time.sleep(10)
    with allure.step("Verify in logs that kernel crash was detected and tech-support file will be generated"):
        log_message_list = [r"Kernel crashes detected",
                            r"System is ready to respond, will take tech support file.",
                            r"Generating system tech-support file, it might take a few minutes..."]
        system.log.verify_expected_logs_by_time(log_message_list, engines.dut, only_latest_log=False,
                                                start_time=start_time)
    with allure.step("Sleep until tech-support file in generated"):
        tech_support_generation_time = getattr(devices.dut, "generate_tech_support", False)
        if tech_support_generation_time:
            time.sleep(OperationTimeConsts.THRESHOLDS[tech_support_generation_time] + 0.25 * MINUTE)
        else:
            time.sleep(OperationTimeConsts.THRESHOLDS['generate tech-support'] + 0.25 * MINUTE)
    with allure.step("Verify in logs that tech-support file generation is done"):
        log_message_list = [r"Generated tech-support"]
        system.log.verify_expected_logs_by_time(log_message_list, engines.dut, only_latest_log=False,
                                                start_time=start_time)
    with allure.step("Get generated tech-support and verify it was generated in the last 6 mins"):
        output_list = list(Tools.OutputParsingTool.parse_show_files_to_dict(
            system.techsupport.show()).get_returned_value().values())
        techsupport_file_path = output_list[0]
        techsupport_file_name = techsupport_file_path.split('/')[-1]
        system.techsupport.check_techsupport_file_age(engines.dut, system, techsupport_file_path, max_age_hours=0.1)
    with allure.step("Get expected kdump files names"):
        kdump_files_names_templates = ["dmesg.{}.gz", "kdump.{}", "kdump_lock.gz"]
        expected_patterns_list = []
        for template in kdump_files_names_templates:
            if '{}' in template:
                pattern = re.escape(template).replace(r'\{\}', NvosConst.TIMESTAMP_REGEX)
            else:
                pattern = re.escape(template)
            expected_patterns_list.append(re.compile(f"^{pattern}$"))
    with allure.step("Validate each expected file name and size"):
        system.techsupport.extract_techsupport_files(engines.dut, techsupport_file_name)
        techsupport_files_dict = system.techsupport.get_techsupport_files_names(engines.dut,
                                                                                {"kdump": expected_patterns_list})
        with allure.independent_step("Validate files names"):
            verify_techsupport_files_names(techsupport_files_dict["kdump"], expected_patterns_list)
        with allure.independent_step("Validate files sizes"):
            verify_techsupport_files_sizes(engines.dut, techsupport_file_name)


def verify_techsupport_files_names(techsupport_files_list, expected_patterns_list):
    files_search_errors = {}
    for expected_file_pattern in expected_patterns_list:
        if not any(expected_file_pattern.match(file) for file in techsupport_files_list):
            files_search_errors[expected_file_pattern] = f'file "{expected_file_pattern}" was not found'
    err = ',\n'.join(list(files_search_errors.values()))
    assert not files_search_errors, f"The following files weren't found:\n{err}"


def verify_techsupport_files_sizes(engine, techsupport_file_name):
    system = System()
    files_list = system.techsupport.get_techsupport_empty_files(engine, techsupport_file_name, "kdump")
    assert len(files_list) == 0, f"the next files are unexpectedly empty {files_list}"
