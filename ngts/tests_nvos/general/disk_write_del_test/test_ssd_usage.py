import sys
import os
import time
import pytest
import allure
import logging
import json
import re
from infra.tools.sql.constants import SkynetGeneralConstants
from ngts.nvos_constants.constants_nvos import LogComponentsConsts
from ngts.nvos_tools.system.System import System

SSD_DIR = "/home/admin/ssd_check"
WRITTEN_MB_PATH = SSD_DIR + "/last_written_value.txt"
HOURS_IN_10_YEAR = 87600
TB_IN_MB = 1048576  # 1TB=1024GB=1024*1024 MB
logger = logging.getLogger()
ONE_DAY_IN_SEC = 86400


class MyLogger:
    def __init__(self, str_init=""):
        self.str = str_init

    def set_str(self, new_str):
        self.str = new_str


def do_ssd_endurance_test(dut_engine, min_gap, my_logger, release_mode=False):
    """
    Contains all logic for ssd endurance check
    :param dut_engine: engine of dut
    :param nos_name: the name of the operating system on which the tests runs on
    :param min_gap: The minimum amount of time in days allowed between 2 tests
    :param release_mode: Determines if the test is running in release mode or not.
    """
    try:
        skip_writing = False
        with allure.step("Detect SSD device and fetch device ID"):
            ssd_device_name = dut_engine.run_cmd("lsblk -o NAME,TYPE -p | grep disk").strip().split()[0]
            ssd_device_filter = "'Model Number'" if "nvme" in ssd_device_name else "'Device Model'"
            ssd_device_id = dut_engine.run_cmd(f"sudo smartctl -a {ssd_device_name} | grep {ssd_device_filter}", validate=True).strip().split()[-1]

        with allure.step("Fetch SSD TBW threshold for device"):
            ssd_threshold_tb = get_writing_threshold_for_device(ssd_device_id)
            ssd_threshold_mb = ssd_threshold_tb * TB_IN_MB

        with allure.step("Set DUT log level to default"):
            set_log_level_default(dut_engine)

        with allure.step("Read current and last written MB values from DUT"):
            logger.info("Calculate the current 'written mb' value on the DUT")
            if "nvme" in ssd_device_name:
                current_written_value = int(dut_engine.run_cmd(
                    "iostat -m | grep nvme | awk '{{print $7}}'", validate=True))
            else:
                current_written_value = int(dut_engine.run_cmd(
                    "iostat -m | grep sda | awk '{{print $7}}'", validate=True))
            last_written_value = get_last_written_value(dut_engine)
            logger.debug("Values for debug: last_written_value: %d, current_written_value: %d", last_written_value, current_written_value)

        with allure.step("Check time since last modification and validate test can run"):
            sec_from_last_modification = get_sec_from_last_modification(dut_engine)
            raw = dut_engine.run_cmd('echo $?', validate=True)
            rc = int(raw.strip().splitlines()[-1])
            if rc:
                raise RuntimeWarning("An error occurred after from a call to get_sec_from_last_modification()")
            logger.info("Checking if the current value is valid:"
                        " a reboot wasn't performed or %d days has passed from last writing", min_gap)
            validate_last_written_value(dut_engine, min_gap, sec_from_last_modification)
            logger.debug("Values for debug: sec from last modify: %d", sec_from_last_modification)

        with allure.step("Calculate SSD writing tempo and estimate 10 year write"):
            logger.info("Test starts: calculating the SSD writing tempo")
            mb_written_per_hour = calculate_ssd_writing(
                last_written_value, current_written_value, sec_from_last_modification)
            estimate_mb_write_for_10_years = mb_written_per_hour * HOURS_IN_10_YEAR
            logger.debug(
                "Values for debug: est_mb_for_10_years: %d, mb_written per hour: %d, hours in 10 years: %d, ssd thresh: %d",
                estimate_mb_write_for_10_years, mb_written_per_hour, HOURS_IN_10_YEAR, ssd_threshold_mb)

        with allure.step("Assert SSD write tempo is within threshold"):
            if estimate_mb_write_for_10_years > ssd_threshold_mb:
                logger.info("Test failed")
                to_logger(ssd_threshold_mb, estimate_mb_write_for_10_years, mb_written_per_hour, "Test failed", my_logger)
                raise AssertionError('FAILED: The writing tempo to ssd has exceeded the allowed threshold!')
            logger.info("Test passed!")
            to_logger(ssd_threshold_mb, estimate_mb_write_for_10_years, mb_written_per_hour, "Test passed", my_logger)

    except ValueError as err:
        skip_writing = True
        raise ValueError from err

    except AssertionError as err:
        raise AssertionError from err

    except RuntimeWarning as skip_phrase:
        str_skip = str(skip_phrase)
        if re.match("Not enough time", str_skip):
            skip_writing = True
        if not release_mode:
            pytest.skip(str_skip)
        raise RuntimeWarning from skip_phrase

    finally:
        with allure.step("Update current value on DUT (if needed)"):
            if not skip_writing:
                logger.info("Updating the current value to %s", current_written_value)
                update_current_value(dut_engine, current_written_value)
            else:
                logger.info("Update of current value is not needed, test finished")


def to_logger(ssd_threshold_mb, estimate_mb_write_for_10_years, mb_written_per_hour, str_test_result, mylogger):

    output1 = "ssd_threshold_mb = " + str(ssd_threshold_mb)
    logger.info(output1)
    output2 = "estimate_mb_write_for_10_years = " + str(round(estimate_mb_write_for_10_years, 2))
    logger.info(output2)
    output3 = "mb_written_per_hour = " + str(round(mb_written_per_hour, 2))
    logger.info(output3)
    precent_calculate = (estimate_mb_write_for_10_years / ssd_threshold_mb) * 100
    output4 = "using rate: " + str(round(mb_written_per_hour)) + " for 10 years it use: " + str(round(precent_calculate, 2)) + "% of ssd_threshold_mb"
    logger.info(output4)
    mylogger.set_str(str_test_result + "\n" + output1 + "\n" + output2 + "\n" + output3 + "\n" + output4)


def set_log_to_all_component(log_level):
    list_with_all_components = LogComponentsConsts.COMPONENTS_LIST
    for component_name in list_with_all_components:
        system.log.component.component_id[component_name].level.set(log_level, apply=True).verify_result()


def set_log_level_default(dut_engine):
    """
    set the log level of the DUT to default to avoid extensive logs writing
    """
    system = System(None)
    list_with_all_components = LogComponentsConsts.COMPONENTS_LIST
    log_level = "notice"
    for component_name in list_with_all_components:
        if component_name == "symmetry-manager" or component_name == "nvue":
            log_level = "info"
        else:
            log_level = "notice"
        system.log.component.component_id[component_name].level.set(log_level, apply=True).verify_result()


def update_current_value(dut_engine, current_val):
    """
    Update the file on the DUT with the current Mb written value
    """
    dut_engine.run_cmd('mkdir -p {}'.format(SSD_DIR), validate=True)
    dut_engine.run_cmd("echo {} > {}".format(current_val, WRITTEN_MB_PATH), validate=True)


def get_sec_from_last_modification(dut_engine):
    """
    get from DUT how many seconds passed from last modification of the written mb file
    """
    return int((dut_engine.run_cmd(
        "stat -c \"%Y\" {} | xargs -I{{}} date +%s --date=\"now - {{}} seconds\"".format(WRITTEN_MB_PATH),
        validate=True)))


def get_last_written_value(dut_engine):
    """
    This method will return the "last written Mb" value from the switch, if exists.
    :param dut_engine: engines fixture
    """
    logger.info("Checking if a file with the latest value exists on DUT")
    dut_engine.run_cmd('ls {}'.format(WRITTEN_MB_PATH))
    raw = dut_engine.run_cmd('echo $?', validate=True)
    rc = int(raw.strip().splitlines()[-1])
    if rc:
        raise RuntimeWarning("The current value file does not exist, Writing the current value and exiting")
    written_mb_value = dut_engine.run_cmd('cat {}'.format(WRITTEN_MB_PATH), validate=True)
    if written_mb_value == "" or written_mb_value.isdigit() == False:
        raise ValueError('Written_mb_value is empty ,from get_last_written_value function ')
    logger.info("File exists, the last value written to the file is %s mb", written_mb_value)
    return int(written_mb_value)


def validate_last_written_value(dut_engine, min_gap, sec_from_last_modification):
    """
    This method will check if the switch was rebooted since the "last written value" was written to file
    or the gap between performing the tests is too low.
    """
    min_gap_in_sec = min_gap * 24 * 3600
    sec_from_uptime = int(float(dut_engine.run_cmd("sudo cat /proc/uptime | awk '{print $1}'")))
    if sec_from_uptime < sec_from_last_modification:
        raise RuntimeWarning("System has rebooted since last time ssd sampled, value is not valid")
    if sec_from_last_modification < min_gap_in_sec:
        remaining_hours_for_next_test = (min_gap_in_sec - sec_from_last_modification) / 3600
        raise RuntimeWarning("Not enough time has passed to calculate the SSD endurance. Please try again in {} hours"
                             .format(remaining_hours_for_next_test))


def calculate_ssd_writing(last_written_value, current_written_value, sec_from_last_modification):
    """
    Calculate SSD writing tempo per hour
    """
    total_written = current_written_value - last_written_value
    write_mb_per_hour = (total_written / sec_from_last_modification) * 3600
    return write_mb_per_hour


def get_writing_threshold_for_device(device_id):
    """
    Fetch the SSD TBW threshold from the json file
    """
    with open("ssd_threshold.json", "r") as json_file:
        th_dict = json.load(json_file)
        for json_device_id, ssd_th_value in th_dict.items():
            pattern = r'.*{}$'.format(json_device_id)
            if re.match(pattern, device_id):
                return ssd_th_value
    raise ValueError('The device {} was not found in the active SSD list'.format(device_id))


def test_calculate_ssd_writing(last, current, sec, expected):
    result = calculate_ssd_writing(last, current, sec)
    assert result == expected, f"Expected {expected}, got {result}"


def check_calculate():
    matrix = [
        [0, 100, 3600, 100],
        [500, 1500, 7200, 500],
        [1000, 2000, 3600, 1000],
    ]
    with allure.step("Calculate SSD writing for each parameter set"):
        for start, end, duration, workload in matrix:
            with allure.step(f"Params → start={start}, end={end}, duration={duration}, workload={workload}"):
                test_calculate_ssd_writing(start, end, duration, workload)


@allure.title("SSD Endurance Test Workflow")
def test_ssd_endurance(engines, str_gap_time_between_tests="30sec"):
    """
    Endurance test for SSD: runs calculation matrix, then the main endurance routine,
    handles intermittent RuntimeWarning, and finally resets log level.
    str_gap_time_between_tests can be for example: 30sec, 60sec, 10m, 15m, 1h, 2h, 12h, 24h  (m=minutes , h=hour)
    """
    min_gap_dict = {"30sec": 0.5 / (24 * 60), "60sec": 1 / (24 * 60), "10m": 10 / (24 * 60),
                    "15m": 15 / (24 * 60), "1h": 60 / (24 * 60), "2h": 120 / (24 * 60), "12h": 0.5, "24h": 1}
    min_gap = min_gap_dict[str_gap_time_between_tests]
    check_calculate()
    additional_delay = 300 * min_gap
    sleep_time = ONE_DAY_IN_SEC + additional_delay
    my_logger_results_of_test = MyLogger()
    with allure.step(f"Run SSD endurance on NOS=nvos , min_gap={min_gap} "):
        try:
            engines.dut.run_cmd(f"rm -f {WRITTEN_MB_PATH}", validate=True)
            do_ssd_endurance_test(engines.dut, min_gap, my_logger_results_of_test, True)
        except RuntimeWarning as err:
            with allure.step("Caught RuntimeWarning during first iteration ,now going to sleep"):
                allure.attach(str(err), name="RuntimeWarning message", attachment_type=allure.attachment_type.TEXT)
                engines.dut.disconnect()
                logger.info(f"TIME TO SLEEP {min_gap * 24} HOURS == {min_gap * 24 * 60} MINUTES ")
                time.sleep(min_gap * sleep_time)
                do_ssd_endurance_test(engines.dut, min_gap, my_logger_results_of_test)          # retry
        finally:
            with allure.step("Reset log level to default"):
                set_log_level_default(engines.dut)      # 3) Cleanup / reset log level
            logger.info(my_logger_results_of_test.str)
            allure.attach(my_logger_results_of_test.str, name="Test result", attachment_type=allure.attachment_type.TEXT)
