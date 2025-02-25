import logging
import time
from contextlib import contextmanager

from retry import retry
from typing import Dict

from ngts.nvos_tools.infra import ExceptionTool
from ngts.nvos_tools.infra.FilesTool import EngineFile, TempFileOnEngine
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from retry.api import retry_call
import pytest
import random
import re
import math
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.Simulator import HWSimulator
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_constants.constants_nvos import SystemConsts, HealthConsts, NvosConst, PlatformConsts, FansConsts
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.nvos_tools.infra.DatabaseTool import DatabaseTool
from ngts.nvos_constants.constants_nvos import DatabaseConst

logger = logging.getLogger()


OK = HealthConsts.OK
NOT_OK = HealthConsts.NOT_OK
IGNORED = HealthConsts.IGNORED
USER_DEFINED_CHECKERS_KEY = 'user_defined_checkers'
DEVICES_TO_IGNORE_KEY = "devices_to_ignore"
SIMULATED_ISSUES = {"bad_device": "device is out of power"}


@pytest.fixture(scope='function')
def set_unset_ps_redundancy_grid():
    platform = Platform()
    with allure.step(f"Set platform ps-redundancy to {PlatformConsts.PS_REDUNDANCY_GRID}"):
        platform.ps_redundancy.set(PlatformConsts.PS_REDUNDANCY_POLICY, PlatformConsts.PS_REDUNDANCY_GRID, apply=True)
    yield
    with allure.step('Run unset platform ps-redundancy command and apply'):
        platform.ps_redundancy.unset(apply=True).verify_result()


@pytest.mark.system
@pytest.mark.health
def test_reboot_test():
    """
    Validate health after reboot :
    - status is OK
    - same health file as before the reboot
    - relevant reboot line appears in the health file
    - new summary line after the reboot in the health file
    """

    system = System()

    system.validate_health_status(OK)
    last_status_line = system.health.history.search_line(HealthConsts.SUMMARY_REGEX_OK)[-1]

    with allure.step('Reboot the system'):
        system.reboot.action_reboot()

    start_time = time.time()
    system.health.wait_until_health_status_change_after_reboot(OK)
    end_time = time.time()
    duration = end_time - start_time

    with allure.step("Took {} seconds until health status changed to OK after reboot".format(duration)):
        logger.info("Took {} seconds until health status changed to OK after reboot".format(duration))

    with allure.step("Validate it is the same health file"):
        logger.info("Validate it is the same health file")
        health_history_output = system.health.history.show()
        assert len(system.health.history.search_line(last_status_line, health_history_output)) == 1, "Health file has changed after reboot"

    with allure.step("Validate health history file indicates reboot occurred and print the status again"):
        logger.info("Validate health history file indicates reboot occurred and print the status again")
        system.health.history.validate_new_summary_line_in_history_file_after_boot(last_status_line)


@pytest.mark.system
@pytest.mark.health
def test_show_system_health(devices):
    """
    Validate all the show system health commands
        Test flow:
            1. validate nv show system health cmd
            2. validate nv show system cmd
            3. validate nv show fae health cmd
            4. validate nv show system health history cmd
            5. validate nv show system health history files cmd
            6. validate nv show system health history files <file> cmd
    """

    system = System()

    with allure.step("Validate \"nv show system health\" cmd"):
        logger.info("Validate \"nv show system health\" cmd")
        health_output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()
        ValidationTool.validate_all_values_exists_in_list([HealthConsts.STATUS, HealthConsts.STATUS_LED], health_output.keys()).verify_result()
        system.validate_health_status(HealthConsts.OK)
        verify_health_status_and_led(system, HealthConsts.OK)

    with allure.step("Validate health status with \"nv show system\" cmd"):
        logger.info("Validate health status with \"nv show system\" cmd")
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        ValidationTool.verify_field_exist_in_json_output(system_output, [SystemConsts.HEALTH_STATUS]).verify_result()
        verify_expected_health_status(system_output, SystemConsts.HEALTH_STATUS, OK)

    with allure.step("Validate \"nv show fae health\" cmd"):
        logger.info("Validate \"nv show fae health\" cmd")
        detail_health_output = OutputParsingTool.parse_json_str_to_dictionary(Fae().health.show()).get_returned_value()
        ValidationTool.validate_all_values_exists_in_list([HealthConsts.STATUS, HealthConsts.STATUS_LED, HealthConsts.MONITOR_LIST],
                                                          detail_health_output).verify_result()
        verify_expected_health_status(detail_health_output, HealthConsts.STATUS, OK)
        monitor_dict = sort_monitor_list(detail_health_output[HealthConsts.MONITOR_LIST])
        assert len(monitor_dict[NOT_OK]) == 0, "Expected not to have \"Not OK\" devices, cause the health status is OK,\n" \
                                               "but those devices are not OK : {}".format(monitor_dict[NOT_OK])
        ValidationTool.validate_all_values_exists_in_list(devices.dut.health_components,
                                                          detail_health_output[HealthConsts.MONITOR_LIST].keys()).verify_result()

    with allure.step("Validate \"nv show system health history\" cmd"):
        logger.info("Validate \"nv show system health history\" cmd")
        health_history_output = system.health.history.show()
        assert system.health.history.get_last_status_from_health_file(health_history_output) == OK, "Last status in the health report file is Not OK but expected to be OK"

    with allure.step("Validate \"nv show system health history files\" cmd"):
        logger.info("Validate \"nv show system health history files\" cmd")
        health_history_files = OutputParsingTool.parse_json_str_to_dictionary(system.health.history.files.show()).get_returned_value()
        files_amount = len(health_history_files)
        assert files_amount in [1, 2], "Unexpected amount of history files.\n Expected: 1 or 2 , but got {}".format(files_amount)
        assert HealthConsts.HEALTH_FIRST_FILE in health_history_files, "Expect to have {} as health file, but have those files {}"\
            .format(HealthConsts.HEALTH_FIRST_FILE, health_history_files)
        if files_amount == 2:
            assert HealthConsts.HEALTH_SECOND_FILE in health_history_files, "Expect to have {} as health file, but have those files {}" \
                .format(HealthConsts.HEALTH_SECOND_FILE, health_history_files)

        health_history_file_output = system.health.history.show_health_report_file(HealthConsts.HEALTH_FIRST_FILE)
        # first line in the health report output is the cmd itself, so we will compared just the file itself.
        assert health_history_file_output.split("\n", 2)[2] == health_history_output.split("\n", 2)[2], "The first health file does not show the same info as the default cmd"


@pytest.mark.system
@pytest.mark.health
def test_system_health_files(engines):
    """
    Will validate the health files requirements:
        -	Tech-support will contain health files
        -	Upload health files
        -	Delete health files
    """

    system_health_files_test(engines, check_rotation=False)


@pytest.mark.system
@pytest.mark.health
@pytest.mark.checklist
def test_system_health_files_with_rotation(engines):
    """
    Will validate the health files requirements:
        -	file will be rotated after 10 MB
        -	maximum 2 health files
        -	Tech-support will contain health files
        -	Upload health files
        -	Delete health files
    """

    system_health_files_test(engines, check_rotation=True)


@pytest.mark.system
@pytest.mark.health
def test_ignore_health_issue(engines, devices, loganalyzer):
    """
    Validate we can ignore all health issue and status will change to OK
    steps:
        1. Simulate PSU and FAN health issue
        2. Validate health status and report
        3. Ignore PSU issue and Validate
        4. Ignore FAN issue too and Validate health state change to OK
        5. Remove the ignore from FAN issue and Validate health state change to Not OK
        6. Remove the ignore from PSU issue too and Validate
        7. Fix PSU and FAN health issue
    """
    system = System()
    thermal_directory = devices.dut.fan_direction_dir
    validate_psu_redundancy(devices, Platform())
    health_config_file = EngineFile(engines.dut, get_system_health_monitoring_config_file_path())
    verify_health_before_test()

    try:
        with allure.step("Simulate PSU and FAN health issue"):
            psu_id, fan_id = simulate_fan_and_psu_health_issue(engines, devices)
            psu_display_name = "PSU{}".format(psu_id)
            psu_config_name = "PSU {}".format(psu_id)
            psu_fan_config_name = "psu{}_fan1".format(psu_id)
            fan_display_name = get_fan_display_name(fan_id)
            fan_config_name = "fan{}".format(fan_id)
            if loganalyzer:
                for hostname in loganalyzer.keys():
                    loganalyzer[hostname].ignore_regex.extend(
                        [f"\\.*Fan fault warning: {fan_config_name} is not working\\.*",
                         f"\\.*Fan removed warning: {psu_fan_config_name} was removed from the system, potential overheat hazard\\.*",
                         f"\\.*PSU absence warning: PSU {psu_id} is not present.\\.*",
                         f"\\.*Insufficient number of working fans warning\\.*",
                         ])

        with allure.step("Validate health status and report"):
            system.wait_until_health_status_change_to(NOT_OK)
            verify_health_status_and_led(system, NOT_OK)
            monitor_list = OutputParsingTool.parse_json_str_to_dictionary(Fae().health.show()).get_returned_value()[HealthConsts.MONITOR_LIST]
            verify_devices_health_status_in_monitor_list({psu_display_name: NOT_OK, fan_display_name: NOT_OK}, monitor_list)
            verify_devices_health_status_in_issues_list(system, [psu_display_name, fan_display_name])

        with allure.step("Ignore PSU issue and Validate"):
            initial_ignore_list = health_config_file.json_read()[DEVICES_TO_IGNORE_KEY]
            ignore_health_issue(initial_ignore_list + [psu_config_name, psu_fan_config_name], health_config_file,
                                ignore_psu_redundancy=True)
            system.wait_until_health_status_change_to(NOT_OK)
            verify_health_status_and_led(system, NOT_OK)
            monitor_list = OutputParsingTool.parse_json_str_to_dictionary(Fae().health.show()).get_returned_value()[
                HealthConsts.MONITOR_LIST]
            verify_devices_health_status_in_monitor_list({psu_display_name: IGNORED, fan_display_name: NOT_OK}, monitor_list)
            verify_devices_health_status_in_issues_list(system, [fan_display_name])

        with allure.step("Ignore FAN issue too and Validate health state change to OK"):
            ignore_health_issue(initial_ignore_list + [psu_config_name, psu_fan_config_name, fan_config_name],
                                health_config_file, ignore_psu_redundancy=True)
            system.wait_until_health_status_change_to(OK)
            verify_health_status_and_led(system, OK)
            monitor_list = OutputParsingTool.parse_json_str_to_dictionary(Fae().health.show()).get_returned_value()[
                HealthConsts.MONITOR_LIST]
            verify_devices_health_status_in_monitor_list({psu_display_name: IGNORED, fan_display_name: IGNORED}, monitor_list)
            verify_devices_health_status_in_issues_list(system, [])

        with allure.step("Remove the ignore from FAN issue and Validate health state change to Not OK"):
            ignore_health_issue(initial_ignore_list + [psu_config_name, psu_fan_config_name], health_config_file,
                                ignore_psu_redundancy=True)
            system.wait_until_health_status_change_to(NOT_OK)
            verify_health_status_and_led(system, NOT_OK)
            monitor_list = OutputParsingTool.parse_json_str_to_dictionary(Fae().health.show()).get_returned_value()[
                HealthConsts.MONITOR_LIST]
            verify_devices_health_status_in_monitor_list({psu_display_name: IGNORED, fan_display_name: NOT_OK}, monitor_list)
            verify_devices_health_status_in_issues_list(system, [fan_display_name])

        with allure.step("Remove the ignore from PSU issue too and Validate"):
            ignore_health_issue(initial_ignore_list, health_config_file, ignore_psu_redundancy=False)
            system.wait_until_health_status_change_to(NOT_OK)
            verify_health_status_and_led(system, NOT_OK)
            verify_devices_health_status_in_monitor_list({psu_display_name: NOT_OK, fan_display_name: NOT_OK})
            verify_devices_health_status_in_issues_list(system, [psu_display_name, fan_display_name])

    finally:

        with allure.step("Fix PSU and FAN health issue"):
            HWSimulator.simulate_fix_fan_fault(engines.dut, thermal_directory, fan_id)
            HWSimulator.simulate_fix_psu_fault(engines.dut, thermal_directory, psu_id)
            health_config_file.revert_to_original()
            system.wait_until_health_status_change_to(OK)
            verify_health_status_and_led(system, OK)


@pytest.mark.system
@pytest.mark.health
def test_simulate_health_problem_with_hw_simulator(devices, engines, set_unset_ps_redundancy_grid):
    """
    Validate health monitoring.
    Health status should change to "Not OK" when we simulate a problem and return to "OK" if status fixed or ignored.
        Test flow:
            1. Simulate health problem with HW simulator
            2. validate health status changed to "Not OK"
            3. validate devices appear in the detailed health report as not OK
            5. validate status has changed in the log
            6. fix the health issue
            7. validate health status changed to "OK"
            8. validate devices appear in the detailed health report as OK
    """
    validate_psu_redundancy(devices, Platform())
    system = System()
    thermal_directory = devices.dut.fan_direction_dir
    system.log.rotate_logs()
    health_issue_dict = {}
    date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
    system.health.history.delete_history_file(HealthConsts.HEALTH_FIRST_FILE)
    time.sleep(1)
    verify_health_before_test()

    try:
        psu_id, fan_id = simulate_fan_and_psu_health_issue(engines, devices)
        psu_display_name = "PSU{}".format(psu_id)
        fan_display_name = get_fan_display_name(fan_id)
        health_issue_dict = {psu_display_name: ["missing or not available", "missing - Unpopulated PSU slot"],
                             fan_display_name: "not working"}
        logger.info("sleep 5 sec after simulating HW issue")
        time.sleep(5)
        validate_health_fix_or_issue(engines, system, health_issue_dict, date_time, False)

    finally:
        date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
        time.sleep(1)
        with allure.step("Cleanup - Fix the health issues"):
            HWSimulator.simulate_fix_fan_fault(engines.dut, thermal_directory, fan_id)
            HWSimulator.simulate_fix_psu_fault(engines.dut, thermal_directory, psu_id)
            validate_health_fix_or_issue(engines, system, health_issue_dict, date_time, True)


@pytest.mark.system
@pytest.mark.health
def test_simulate_fan_speed_fault(devices, engines, loganalyzer):
    """
    Validate health monitoring when having a fan speed fault.
        Test flow:
            1. Simulate fan speed fault
            2. validate health status changed to "Not OK"
            3. validate devices appear in the detailed health report as not OK
            5. validate status has changed in the log
            6. fix the health issue
            7. validate health status changed to "OK"
            8. validate devices appear in the detailed health report as OK
    """
    system = System()
    thermal_directory = devices.dut.fan_direction_dir
    speed_changed = False
    system.log.rotate_logs()
    date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
    system.health.history.delete_history_file(HealthConsts.HEALTH_FIRST_FILE)
    time.sleep(1)
    verify_health_before_test()
    fan_id = random.randrange(1, len(devices.dut.fan_list) + 1)
    logger.info("Chosen fan : {}  - {}".format(fan_id, get_fan_display_name(fan_id)))
    fan_display_name = get_fan_display_name(fan_id)
    health_issue_dict = {fan_display_name: [FansConsts.FAN_SPEED_OUT_OF_RANGE, FansConsts.FAN_NOT_WORKING]}
    real_speed = 0
    if loganalyzer:
        for hostname in loganalyzer.keys():
            loganalyzer[hostname].ignore_regex.extend([f"\\.*Fan low speed warning: fan{fan_id} current speed\\.*",
                                                       f"\\.*Fan fault warning: fan{fan_id} is not working\\.*",
                                                       f"\\.*Insufficient number of working fans warning\\.*"])

    try:
        real_speed = HWSimulator.simulate_fan_speed_fault(engines.dut, thermal_directory, fan_id, 1)
        speed_changed = True
        retry_validate_health_fix_or_issue(engines, system, health_issue_dict, date_time, False)

    finally:
        if speed_changed:
            with allure.step("Fix the health issues"):
                date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
                time.sleep(1)
                HWSimulator.simulate_fix_fan_speed_fault(engines.dut, thermal_directory, fan_id, real_speed)
                retry_validate_health_fix_or_issue(engines, system, health_issue_dict, date_time, True)


@pytest.mark.system
@pytest.mark.health
def test_simulate_multi_fan_speed_fault(engines, devices, loganalyzer):
    """
    Validate health monitoring when having a fan speed fault.
        Test flow:
            1. Get the last system event ID to be used as marker
            2. Choose two fans to be used for testing
            3. Simulate fan speed fault for the chosen fans
            4. Validate fan speed fault system events for these fans
            5. Simulate fan speed fault fix for the chosen fans
            6. Validate fan speed fault system clear events for these fans
    """
    system = System()
    platform = Platform()
    thermal_directory = devices.dut.fan_direction_dir
    show_output = OutputParsingTool.parse_json_str_to_dictionary(platform.environment.fan.show()).verify_result()
    no_of_fans = 0
    for key in show_output:
        if re.search("^FAN.*", key):
            no_of_fans += 1
    fan_ids = random.sample([i for i in range(1, no_of_fans)], 2)
    logger.info("Chosen fans : {}".format(fan_ids))
    fan_info = dict()
    fan_fault_events = [FansConsts.FAN_SPEED_OUT_OF_RANGE, FansConsts.FAN_NOT_WORKING]

    if loganalyzer:
        for key, value in loganalyzer.items():
            for fan_id in fan_ids:
                value.ignore_regex.extend([f"\\.*Fan low speed warning: fan{fan_id} current speed\\.*",
                                           f"\\.*Fan fault warning: fan{fan_id} is not working\\.*",
                                           f"\\.*Insufficient number of working fans warning\\.*"])

    try:
        with allure.step("Get the latest event"):
            last_event = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.events.show_last().
                                                                              verify_result()).get_returned_value()
            latest_event_id = list(last_event)[0]

        with allure.step("Simulate fan speed fault for chosen fans:{}".format(fan_ids)):
            for fan_id in fan_ids:
                fan_display_name = get_fan_display_name(fan_id)
                real_speed = HWSimulator.simulate_fan_speed_fault(engines.dut, thermal_directory, 1, fan_id)
                fan_info[fan_id] = [fan_display_name, real_speed]
                time.sleep(2)

        with allure.step("Validate system event for fan speed fault for chosen fans:{}".format(fan_ids)):
            for fan_id in fan_ids:
                prefix = fan_info[fan_id][0] + " "
                events_to_search = [prefix + fan_fault_event for fan_fault_event in fan_fault_events]
                retry_call(validate_system_event, [system, latest_event_id, events_to_search],
                           exceptions=AssertionError, tries=12, delay=5)

        with allure.step("Simulate fix fan speed fault for chosen fans:{}".format(fan_ids)):
            for fan_id in fan_ids:
                HWSimulator.simulate_fix_fan_speed_fault(engines.dut, thermal_directory, fan_id, fan_info[fan_id][1])

        with allure.step("Validate system clear event for speed fault for chosen fans:{}".format(fan_ids)):
            for fan_id in fan_ids:
                prefix = "Cleared: " + fan_info[fan_id][0] + " "
                clear_events_to_search = [prefix + fan_fault_event for fan_fault_event in fan_fault_events]
                retry_call(validate_system_event, [system, latest_event_id, clear_events_to_search],
                           exceptions=AssertionError, tries=12, delay=5)
    finally:
        time.sleep(1)
        with allure.step("Fix the fan speed fault"):
            for fan_id in fan_ids:
                HWSimulator.simulate_fix_fan_speed_fault(engines.dut, thermal_directory, fan_ids[0], fan_info[fan_id][1])


@pytest.mark.system
@pytest.mark.health
def test_simulate_psu_multi_faults(engines, devices, loganalyzer):
    """
    Validate health monitoring when having a fan speed fault.
        Test flow:
            1. Get the last system event ID to be used as marker
            2. Choose one PSU to be used for testing
            3. Simulate PSU temperature out of range fault for the chosen PSU
            4. Validate PSU temperature fault system event for this PSU
            5. Simulate PSU absent for the chosen PSU
            6. Validate PSU absent fault system event for this PSU
            7. Get the last system event ID to be used as new marker
            8. Simulate PSU present for the chosen fans
            9. Validate PSU temperature fault system event again for this PSU
            10. Simulate PSU temperature in range for the chosen PSU
            11. Validate Cleared:PSU temperature fault system event for this PSU
    """
    system = System()
    platform = Platform()
    thermal_directory = devices.dut.fan_direction_dir
    show_output = OutputParsingTool.parse_json_str_to_dictionary(platform.environment.psu.show()).verify_result()
    no_of_psu = 0
    for key in show_output:
        if re.search("^PSU.*", key):
            no_of_psu += 1
    psu_id = random.randrange(1, no_of_psu + 1)
    logger.info("Chosen PSU : {}".format(psu_id))
    psu_display_name = "PSU{}".format(psu_id)
    psu_info = dict()
    psu_fault_events = ["temperature is too hot", "is missing - Unpopulated PSU slot"]
    temp_fault = False
    temp_fixed = False
    psu_status_fault = False
    psu_status_fixed = False

    if loganalyzer:
        for key, value in loganalyzer.items():
            value.ignore_regex.extend([f"\\.*PSU absence warning: PSU {psu_id} is not present.\\.*"])

    try:
        with allure.step("Get the latest event"):
            last_event = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.events.show_last().
                                                                              verify_result()).get_returned_value()
            latest_event_id = list(last_event)[0]

        with allure.step("Simulate PSU temperature fault for chosen PSU:{}".format(psu_id)):
            real_temp = HWSimulator.simulate_psu_temp_fault(engines.dut, thermal_directory, psu_id)
            psu_info[psu_id] = [psu_display_name, real_temp]
            temp_fault = True
            time.sleep(2)

        with allure.step("Validate system event for PSU temperature fault for chosen PSU:{}".format(psu_id)):
            event_to_search = psu_info[psu_id][0] + " " + psu_fault_events[0]
            retry_call(validate_system_event, [system, latest_event_id, [event_to_search]],
                       exceptions=AssertionError, tries=12, delay=5)

        with allure.step("Simulate PSU absent fault for chosen PSU:{}".format(psu_id)):
            HWSimulator.simulate_psu_fault(engines.dut, thermal_directory, psu_id)
            psu_status_fault = True
            time.sleep(2)

        with allure.step("Validate system event for PSU missing status for chosen PSU:{}".format(psu_id)):
            event_to_search = psu_info[psu_id][0] + " " + psu_fault_events[1]
            retry_call(validate_system_event, [system, latest_event_id, [event_to_search]],
                       exceptions=AssertionError, tries=12, delay=5)

        with allure.step("Get the latest event to be used as new marker"):
            last_event = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.events.show_last().
                                                                              verify_result()).get_returned_value()
            latest_event_id = list(last_event)[0]

        with allure.step("Simulate fix PSU absent for chosen PSU:{}".format(psu_id)):
            HWSimulator.simulate_fix_psu_fault(engines.dut, thermal_directory, psu_id)
            psu_status_fixed = True

        with allure.step("Validate system event for PSU temperature fault for chosen PSU:{}".format(psu_id)):
            event_to_search = psu_info[psu_id][0] + " " + psu_fault_events[0]
            retry_call(validate_system_event, [system, latest_event_id, [event_to_search]],
                       exceptions=AssertionError, tries=12, delay=5)

        with allure.step("Simulate PSU temperature fault fix for chosen PSU:{}".format(psu_id)):
            HWSimulator.simulate_psu_temp_fault(engines.dut, thermal_directory, psu_id, psu_info[psu_id][1])
            time.sleep(2)
            temp_fixed = True

        with allure.step("Validate clear system event for PSU temperature fault for chosen PSU:{}".format(psu_id)):
            event_to_search = "Cleared: " + psu_info[psu_id][0] + " " + psu_fault_events[0]
            retry_call(validate_system_event, [system, latest_event_id, [event_to_search]],
                       exceptions=AssertionError, tries=12, delay=5)

    finally:
        time.sleep(1)
        if temp_fault and not temp_fixed:
            with allure.step("Fix the PSU temperature fault for PSU:{}".format(psu_id)):
                HWSimulator.simulate_psu_temp_fault(engines.dut, thermal_directory, psu_id, psu_info[psu_id][1])

        if psu_status_fault and not psu_status_fixed:
            with allure.step("Fix PSU absent fault for chosen PSU:{}".format(psu_id)):
                HWSimulator.simulate_fix_psu_fault(engines.dut, thermal_directory, psu_id)


@pytest.mark.system
@pytest.mark.health
def test_simulate_health_problem_with_user_config_file(devices, engines):
    """
    Validate health monitoring.
    Health status should change to "Not OK" when we simulate a problem and return to "OK" if status fixed or ignored.
        Test flow:
            1. Simulate health problem with user config file
            2. validate health status changed to "Not OK"
            3. validate new devices appear in the detailed cmd
            5. validate status has changed in the log
            6. fix the health issue
            7. validate health status changed to "Not OK"
            8. validate new devices removed from the detailed cmd
    """

    system = System()
    system.log.rotate_logs()
    date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
    system.health.history.delete_history_file(HealthConsts.HEALTH_FIRST_FILE)
    time.sleep(1)
    system.validate_health_status(OK)

    with allure.step("Simulate health issue"):
        with simulate_health_issue_using_config_file(engines.dut):
            validate_health_issues_exist(system, SIMULATED_ISSUES)
            validate_health_fix_or_issue(system, SIMULATED_ISSUES, date_time, False)
            date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())

    time.sleep(1)
    validate_health_fix_or_issue(system, SIMULATED_ISSUES, date_time, True)


@pytest.mark.system
@pytest.mark.health
def test_simulate_health_problem_with_docker_stop(devices, engines):
    """
    Validate health monitoring.
    Health status should change to "Not OK" when we simulate a problem and return to "OK" if status fixed or ignored.
        Test flow:
            1. Simulate health problem with user config file
            2. stop docker auto restart
            3. validate health status changed to "Not OK"
            4. validate new devices appear in the detailed cmd
            5. validate status has changed in the log
            6. fix the health issue
            7. validate health status changed to "Not OK"
            8. validate new devices removed from the detailed cmd
    """

    system = System()
    system.log.rotate_logs()
    date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
    system.health.history.delete_history_file(HealthConsts.HEALTH_FIRST_FILE)
    time.sleep(1)
    system.validate_health_status(OK)
    docker_to_stop = "gnmi-server"
    docker_not_running_log_str = "Container '" + docker_to_stop + "' is not running"

    try:
        with allure.step("stop {} docker auto restart".format(docker_to_stop)):
            DatabaseTool.sonic_db_cli_hset(engine=engines.dut, asic="", db_name=DatabaseConst.CONFIG_DB_NAME,
                                           db_config="FEATURE|{}".format(docker_to_stop),
                                           param=NvosConst.DOCKER_AUTO_RESTART,
                                           value=NvosConst.DOCKER_STATUS_DISABLED)
            # DatabaseTool.redis_cli_hset(engines.dut, DatabaseConst.CONFIG_DB_NAME, "FEATURE|{}".format(docker_to_stop), NvosConst.DOCKER_AUTO_RESTART, NvosConst.DOCKER_STATUS_DISABLED)

        with allure.step("Get the latest event"):
            last_event = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.events.show_last().
                                                                              verify_result()).get_returned_value()
            latest_event_id = list(last_event)[0]

        with allure.step("stop {} docker".format(docker_to_stop)):
            time.sleep(3)
            output = engines.dut.run_cmd("docker stop {}".format(docker_to_stop))
            assert docker_to_stop in output, "Failed to stop docker"

        with allure.step("Validate docker not running in health issues"):
            health_issue_dict = {docker_to_stop: f"Container '{docker_to_stop}' is not running"}
            validate_health_fix_or_issue(engines, system, health_issue_dict, date_time, False, False)

        with allure.step("validate docker not running event in system events"):
            retry_call(validate_system_event, [system, latest_event_id, [docker_not_running_log_str]],
                       exceptions=AssertionError, tries=12, delay=5)

    finally:
        date_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
        time.sleep(1)
        with allure.step("Fix the health issue "):
            with allure.step("restart docker"):
                output = engines.dut.run_cmd("docker start {}".format(docker_to_stop))
                with allure.step("restart docker auto start"):
                    DatabaseTool.sonic_db_cli_hset(engine=engines.dut, asic="", db_name=DatabaseConst.CONFIG_DB_NAME,
                                                   db_config="FEATURE|{}".format(docker_to_stop),
                                                   param=NvosConst.DOCKER_AUTO_RESTART,
                                                   value=NvosConst.DOCKER_STATUS_ENABLED)
                    # DatabaseTool.redis_cli_hset(engines.dut, 4, "FEATURE|{}".format(docker_to_stop), NvosConst.DOCKER_AUTO_RESTART, NvosConst.DOCKER_STATUS_ENABLED)
                assert docker_to_stop in output, "Failed to start docker"
            validate_docker_is_up(engines.dut, docker_to_stop)
            time.sleep(10)
            validate_health_fix_or_issue(engines, system, health_issue_dict, date_time, True)

        with allure.step("validate docker not running clear event in system events"):
            clear_docker_not_running_log_str = "Cleared: {}".format(docker_not_running_log_str)
            retry_call(validate_system_event, [system, latest_event_id, [clear_docker_not_running_log_str]],
                       exceptions=AssertionError, tries=12, delay=5)


def validate_system_event(system, latest_event_id, events_to_search):
    events = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.events.show("last")). \
        get_returned_value()
    newer_events = [events[event]['text'] for event in list(events) if event > latest_event_id]
    assert bool(set(events_to_search) & set(newer_events)), "None of events:{} found in events".format(events_to_search)


@retry(Exception, tries=5, delay=2)
def validate_docker_is_up(engine, docker):
    assert docker in engine.run_cmd("docker ps")


def validate_psu_redundancy(devices, platform):
    valid_psus = platform.environment.get_available_psus()
    if len(valid_psus) == len(devices.dut.psu_list) / 2:
        pytest.skip(f"DUT has {len(valid_psus)} valid PSUs, we cant simulate psu fault due to ps-redundancy")


def verify_health_status_and_led(system, expected_status, output=None):
    if not output:
        output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()
    system.validate_health_status(expected_status)
    verify_expected_health_status(output, HealthConsts.STATUS, expected_status)
    expected_led = HealthConsts.LED_OK_STATUS if expected_status == HealthConsts.OK else HealthConsts.LED_NOT_OK_STATUS
    verify_expected_health_status(output, HealthConsts.STATUS_LED, expected_led)


def verify_health_before_test():
    try:
        verify_health_status_and_led(System(), OK)
    except AssertionError as e:
        raise Exception("Cannot run test because device health is not OK.\n" + ExceptionTool.format_traceback())


def verify_devices_health_status_in_monitor_list(device_status_dict, monitor_list=None):
    """
    verify device status in the health detail output
    :param device_status_dict: dictionary with devices and their status, example: {PSU1: OK , PSU2: Not OK, FAN1/1: Ignored}
    """
    monitor_dict = sort_monitor_list(monitor_list)
    for device_name, status in device_status_dict.items():
        if status == HealthConsts.IGNORED and monitor_list:
            assert device_name not in list(monitor_list.keys()), \
                f"{device_name} should be ignored , so should not appear in the monitor list"
        else:
            assert device_name in monitor_dict[status]


def verify_devices_health_status_in_issues_list(system, devices_list):
    """
    verify device status in the health show output, under the section "issues"
    :param devices_list: list of devices with issues, example: [PSU1, PSU2, FAN1/1]
    """
    issues_dict = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()[HealthConsts.ISSUES]
    assert set(devices_list) <= set(list(issues_dict.keys()))


def get_system_health_monitoring_config_file_path():
    with allure.step("Get path of system_health_monitoring_config.json"):
        output = OutputParsingTool.parse_json_str_to_dictionary(System().show()).get_returned_value()
        platform_name = output[SystemConsts.PLATFORM]
        ret = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(platform_name)
        logger.info(ret)
        return ret


def simulate_fan_and_psu_health_issue(engines, devices):
    thermal_directory = devices.dut.fan_direction_dir
    with allure.step("simulate_fan_and_psu_health_issue"):
        psu_id = int(random.choice(Platform().environment.get_available_psus()).replace('PSU', ''))
        fan_id = random.randrange(1, len(devices.dut.fan_list) + 1)
        logger.info("Chosen PSU : {}\n Chosen fan : {}  - {}".format(psu_id, fan_id, get_fan_display_name(fan_id)))
        HWSimulator.simulate_fan_fault(engines.dut, thermal_directory, fan_id)
        HWSimulator.simulate_psu_fault(engines.dut, thermal_directory, psu_id)
        return psu_id, fan_id


def get_fan_display_name(fan_id):
    section = 1 if fan_id % 2 == 1 else 2
    num = math.floor(fan_id / 2) + fan_id % 2
    return "FAN{}/{}".format(num, section)


def ignore_health_issue(components_list_to_ignore, health_config_file: EngineFile, ignore_psu_redundancy=None):
    health_config_dict = health_config_file.json_read()
    health_config_dict[DEVICES_TO_IGNORE_KEY] = components_list_to_ignore
    health_config_dict["supports_ps_redundancy"] = not ignore_psu_redundancy
    health_config_file.json_overwrite(health_config_dict)


def verify_issues_in_health_output(health_issues, expected_issues, is_fae_output):
    key = 'message' if is_fae_output else 'issue'
    issues_matched = False
    for component, issues in expected_issues.items():
        for issue in issues:
            if issue in health_issues[component][key]:
                issues_matched = True

    assert issues_matched, (f'Expected {component} health issue to be one of: {issues}, '
                            f'but got "{health_issues[component][key]}"')


def validate_health_fix_or_issue(engines, system, health_issue_dict, search_since_datetime, is_fix, expected_in_monitor_list=True):
    """
    validate health issue or fix with show commands
        - validate with system show cmd the health status
        - validate with health detailed report
        - validate with health history file the status and the issues
        - validate system log indicates that health status has changed
    """
    status = OK if is_fix else NOT_OK
    regex = HealthConsts.HEALTH_FIX_REGEX if is_fix else HealthConsts.HEALTH_ISSUE_REGEX
    # normalize health_issue_dict values to be sets of strings
    health_issue_dict = {k: ({v} if isinstance(v, str) else set(v)) for k, v in health_issue_dict.items()}

    with allure.step("Validate health issues {}".format("fix" if is_fix else "")):
        system.wait_until_health_status_change_to(status)

        with allure.independent_step("Validate health output issues"):
            health_output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()
            verify_health_status_and_led(system, status, health_output)
            health_issues = health_output[HealthConsts.ISSUES]
            if is_fix:
                assert not (health_issue_dict.keys() & health_issues.keys()), (
                    f"Expected none of these health issues: {list(health_issue_dict.keys())}\n"
                    f"But got the following issues: {list(health_issues.keys())}"
                )
            else:
                assert health_issue_dict.keys() <= health_issues.keys(), (
                    f"The following health issues are expected but missing: {health_issue_dict.keys() - health_issues.keys()}"
                )
                verify_issues_in_health_output(health_issues, health_issue_dict, is_fae_output=False)

        if expected_in_monitor_list:
            with allure.independent_step("Validate detailed health report"):
                detail_health_output = OutputParsingTool.parse_json_str_to_dictionary(
                    Fae().health.show()).get_returned_value()
                verify_expected_health_status(detail_health_output, HealthConsts.STATUS, status)
                monitor_dict = sort_monitor_list(detail_health_output[HealthConsts.MONITOR_LIST])
                for component, issues in health_issue_dict.items():
                    if is_fix:
                        assert component not in monitor_dict[NOT_OK]
                    else:
                        assert component in monitor_dict[NOT_OK]
                        verify_issues_in_health_output(detail_health_output[HealthConsts.MONITOR_LIST],
                                                       health_issue_dict, is_fae_output=True)

        with allure.independent_step("Validate health history file"):
            # health_history_output = system.health.history.files.show("health_history | tail -1")
            health_history_output = engines.dut.run_cmd('nv show system health history files health_history | grep ""')
            assert system.health.history.get_last_status_from_health_file(
                health_history_output) == status, "Last status in the health report file is not {}, as we expect".format(status)
            assert len(TestToolkit.search_line_after_a_specific_date_time(
                HealthConsts.ADD_STATUS_TO_SUMMARY_REGEX + status, health_history_output,
                search_since_datetime)) > 0, "Didn't find health status in history file since time : {},\n" \
                                             "history:\n {}".format(search_since_datetime, health_history_output)
            for component, issues in health_issue_dict.items():
                issues_regex = "[" + "|".join(issues) + "]"
                assert len(TestToolkit.search_line_after_a_specific_date_time(
                    regex.format(time_regex=NvosConst.DATE_TIME_REGEX, component=component, issue=issues_regex),
                    health_history_output, search_since_datetime)) > 0

        with allure.independent_step("Validate health status change appears in system log"):
            exp_status = "Health status is {arg}ok".format(arg="" if is_fix else "not ")
            exp_summary = "HEALTH_SUMMARY_{arg}OK".format(arg="" if is_fix else "NOT_")
            log_output = system.log.file.show_log(param='| grep healthd', expected_str=exp_status)
            HealthConsts.SYSTEM_LOG_HEALTH_REGEX.format(status)
            regex_to_search = NvosConst.DATE_TIME_REGEX + HealthConsts.SYSTEM_LOG_HEALTH_STATUS_REGEX.format(
                exp_status, exp_summary)
            assert len(TestToolkit.search_line_after_a_specific_date_time(regex_to_search,
                                                                          log_output, search_since_datetime)) > 0, \
                "Didn't find health status line in the system log since specific time :{}\nSystem Log:\n {}".format(
                    search_since_datetime, log_output)


@retry(Exception, tries=6, delay=10)
def retry_validate_health_fix_or_issue(engines, system, health_issue_dict, search_since_datetime, is_fix, expected_in_monitor_list=True):
    validate_health_fix_or_issue(engines, system, health_issue_dict, search_since_datetime, is_fix, expected_in_monitor_list)


def system_health_files_test(engines, check_rotation=False):
    """
    Will validate the health files requirements:
    steps:
        1. validate health status is OK
        2. simulate health issue
        3. validate health status is not OK
        4. do file rotation (if flag is true)
        5. Validate health files in tech support file
        6. upload health files
        7. delete health files
    """

    system = System()
    system.validate_health_status(OK)

    try:
        with simulate_health_issue_using_config_file(engines.dut):
            validate_health_issues_exist(system, SIMULATED_ISSUES)

            if check_rotation:
                with allure.step("First file rotation"):
                    logger.info("First file rotation")
                    cause_health_file_rotation_and_validate(engines.dut, system)

                with allure.step("Second file rotation"):
                    logger.info("Second file rotation")
                    cause_health_file_rotation_and_validate(engines.dut, system)

            health_files = list(OutputParsingTool.parse_json_str_to_dictionary(system.health.history.files.show()).get_returned_value().keys())

            with allure.step("Validate health files in tech support file"):
                logger.info("Validate health files in tech support file")
                validate_health_files_exist_in_techsupport(system, engines.dut, health_files)

            with allure.step("Upload health files"):
                logger.info("Upload health files")
                validate_upload_health_files(engines, system, health_files)

            with allure.step("Delete health files"):
                logger.info("Delete health files")
                validate_delete_health_files(system, health_files)

    finally:
        system.wait_until_health_status_change_to(OK)


def validate_delete_health_files(system, health_files=[HealthConsts.HEALTH_FIRST_FILE, HealthConsts.HEALTH_SECOND_FILE]):
    """
    delete health files and validate new health file was crated with health summary status
    """
    last_status_line = system.health.history.search_line(HealthConsts.ADD_STATUS_TO_SUMMARY_REGEX + OK)[-1]
    system.health.history.delete_history_files(health_files)
    time.sleep(5)
    with allure.step("Validate new file was created"):
        logger.info("Validate new file was created")
        assert len(system.health.history.search_line(last_status_line)) == 0, "Health file has not changed"

    with allure.step("Validate health status exist in the history file"):
        logger.info("Validate health status exist in the history file")
        health_history_output = system.health.history.show()
        assert system.health.history.get_last_status_from_health_file(health_history_output) == NOT_OK
        assert "health_history file deleted, creating new file" in health_history_output

    validate_health_files_amount(1)


def validate_upload_health_files(engines, system, health_files=[HealthConsts.HEALTH_FIRST_FILE, HealthConsts.HEALTH_SECOND_FILE]):
    """
    validate upload health files with scp and sftp
    """
    upload_protocols = ['scp', 'sftp']
    player = engines['sonic_mgmt']
    file_to_upload = random.choice(health_files)

    with allure.step(
            "Upload health file to player {} with the next protocols : {}".format(player.ip, upload_protocols)):
        logging.info("Upload health file to player {} with the next protocols : {}".format(player.ip, upload_protocols))

        for protocol in upload_protocols:
            with allure.step("Upload health file to player with {} protocol".format(protocol)):
                logging.info("Upload health file to player with {} protocol".format(protocol))
                upload_path = '{}://{}:{}@{}/tmp/{}'.format(protocol, player.username, player.password, player.ip,
                                                            file_to_upload)
                system.health.history.upload_history_files(file_to_upload, upload_path)

            with allure.step("Validate file was uploaded to player and delete it"):
                logging.info("Validate file was uploaded to player and delete it")
                assert player.run_cmd(
                    cmd='ls /tmp/ | grep {}'.format(file_to_upload)), "Did not find the file with ls cmd"
                player.run_cmd(cmd='rm -f /tmp/{}'.format(file_to_upload))
    with allure.step("Validate health files still exist"):
        logger.info("Validate health files still exist")
        validate_health_files_amount(len(health_files))


def validate_health_files_exist_in_techsupport(system, engine, health_files=[HealthConsts.HEALTH_FIRST_FILE, HealthConsts.HEALTH_SECOND_FILE]):
    """
    generate techsupport and validate we have the health files in the log dir
    """
    try:
        system.techsupport.action_generate()
        system.techsupport.extract_techsupport_files(engine)
        techsupport_files_list = system.techsupport.get_techsupport_files_list(engine, 'log')
        for health_file in health_files:
            assert "{}.gz".format(health_file) in techsupport_files_list, \
                "Expect to have {} file, in the tech support log files {}".format(HealthConsts.HEALTH_FIRST_FILE, techsupport_files_list)

    finally:
        system.techsupport.cleanup(engine)
        if system.techsupport.file_name:
            system.techsupport.action_delete(system.techsupport.file_name)


def validate_health_issues_exist(system, issues: Dict[str, str]):
    with allure.step("Validate health status has change and add the info of the new devices"):
        logger.info("Validate health status has change and add the info of the new devices")
        system.wait_until_health_status_change_to(NOT_OK)
        health_output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()
        verify_expected_health_status(health_output, HealthConsts.STATUS, NOT_OK)
        detail_health_output = OutputParsingTool.parse_json_str_to_dictionary(
            Fae().health.show()).get_returned_value()
        verify_expected_health_status(detail_health_output, HealthConsts.STATUS, NOT_OK)
        for device, issue in issues.items():
            assert device in health_output[HealthConsts.ISSUES].keys()
            assert issue in health_output[HealthConsts.ISSUES][device].values()
            assert device in detail_health_output[HealthConsts.MONITOR_LIST].keys()
            assert issue in detail_health_output[HealthConsts.MONITOR_LIST][device].values()


def cause_health_file_rotation_and_validate(engine, system):
    last_status_line = system.health.history.search_line(HealthConsts.ADD_STATUS_TO_SUMMARY_REGEX + OK)[-1]
    with allure.step("create text file in size of 10 MB and replace it with the health file"):
        logger.info("create text file in size of 10 MB and replace it with the health file")
        engine.run_cmd("dd if=/dev/urandom bs=1M count=10 | base64 > file.txt")
        engine.run_cmd("sudo cp file.txt /var/log/health_history")

    with allure.step("Wait until file rotation"):
        logger.info("Wait until file rotation")
        system.health.history.wait_until_health_history_file_rotation(engine)

    with allure.step("Validate we have 2 health files"):
        logger.info("Validate we have 2 health files")
        wait_until_expected_health_files_amount(2)

    with allure.step("Validate new file was created"):
        logger.info("Validate new file was created")
        lines = system.health.history.search_line(last_status_line)
        assert len(lines) == 0, "Health file has not changed"

    with allure.step("Validate health status exist in the history file"):
        logger.info("Validate health status exist in the history file")
        health_history_output = system.health.history.show()
        assert system.health.history.get_last_status_from_health_file(health_history_output) == NOT_OK


def sort_monitor_list(monitor_list=None):
    """
    get the monitor list from the "nv show fae health command,
    return a dictionary with all the optional status as keys: [OK, Not OK , Ignored]
    if the status of a device is not one of [OK, Not OK , Ignored], we will consider it as NOT OK.
    :param monitor_list:
    :return:
    """
    if not monitor_list:
        monitor_list = OutputParsingTool.parse_json_str_to_dictionary(Fae().health.show()).get_returned_value()[HealthConsts.MONITOR_LIST]
    status_options = [OK, NOT_OK, IGNORED]
    monitor_dict = {status_key: [] for status_key in status_options}
    for key, value in monitor_list.items():
        status = value[HealthConsts.STATUS]
        assert status in status_options, "{} is not expected status. Expect to be one of them {}".format(status, status_options)
        monitor_dict[status].append(key)
    return monitor_dict


def verify_expected_health_status(health_output_dict, health_status_field, expected_status):
    """
    verify the expected health status
    :param health_output_dict: dictionary of health status. for example from "nv show system health" cmd.
    :param health_status_field: the health status field name. example : "Status"
    :param expected_status: the expected health status. example "Not OK"
    """
    assert expected_status == health_output_dict[health_status_field], \
        "Unexpected health status. \n Expected: {}, but got :{}".format(expected_status, health_output_dict[health_status_field])


@retry(Exception, tries=12, delay=30)
def wait_until_expected_health_files_amount(num_of_expected_files, actual_health_files=None):
    validate_health_files_amount(num_of_expected_files, actual_health_files)


def validate_health_files_amount(num_of_expected_files, actual_health_files=None):
    if not actual_health_files:
        actual_health_files = OutputParsingTool.parse_json_str_to_dictionary(System().health.history.files.show()).get_returned_value()
    assert num_of_expected_files == len(actual_health_files), \
        "Unexpected num of health files.\n Expected: {}, actual files: {}".format(num_of_expected_files, actual_health_files)


@contextmanager
def simulate_health_issue_using_config_file(engine):
    """
    Creates a simple script and configures the switch (using the health-config file) to use it as an extra
    health-checker. This will cause the switch to report the health issues configured in SIMULATED_ISSUES.
    When the context exits the script is deleted and the configuration restored so the health issues are gone.
    """
    with TempFileOnEngine(engine, 'py') as checker_file:
        checker_file.write('print("MyCategory")')
        for device, issue in SIMULATED_ISSUES.items():
            checker_file.write(f'print("{device}:{issue}")')

        with EngineFile(engine, get_system_health_monitoring_config_file_path()) as config_file:
            with allure.step("Update monitoring config file with my_checker file"):
                config_dict = config_file.json_read()
                config_dict[USER_DEFINED_CHECKERS_KEY].append(f'python {checker_file.path}')
                config_file.json_overwrite(config_dict)

            yield
