"""
Internal test to verify fan speed reduction feature on SN4280 platform.
This is a small hw-mgmt feature, test will not be upstreamed to community.
"""
import logging
import random
import re
import pytest
import time

from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until

pytestmark = [
    pytest.mark.asic('mellanox'),
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer
]

logger = logging.getLogger(__name__)

# Constants
HW_MGMT_FAN_STATUS_PATH = "/var/run/hw-management/thermal/{}_status"
FAN_NUMBER = 4
SHOW_PLATFORM_FAN_UPDATE_INTERVAL = 65  # 60 seconds with 5 seconds buffer


@pytest.fixture(scope="module", autouse=True)
def skip_platform_not_supported(duthost):
    if '4280' not in duthost.facts.get('platform', ''):
        pytest.skip("Test only applicable for SN4280 platform.")


@pytest.fixture(scope="function")
def random_selected_fan():
    """
    Fixture to select a random fan for testing.
    """
    yield f"fan{random.randint(1, FAN_NUMBER)}"


@pytest.fixture(scope="function")
def recover_fan(duthost, random_selected_fan):
    """
    Fixture to recover the fan in teardown on test failures.
    """
    fan_status_file = HW_MGMT_FAN_STATUS_PATH.format(random_selected_fan)
    original_symlink_target = duthost.shell(f"readlink -f {fan_status_file}")["stdout"]

    yield original_symlink_target

    if duthost.shell(f"readlink -f {fan_status_file}")["stdout"] != original_symlink_target:
        recover_fan_symlink(duthost, random_selected_fan, original_symlink_target)
        logger.info("Check all fans are present and OK")
        pytest_assert(
            wait_until(SHOW_PLATFORM_FAN_UPDATE_INTERVAL, 5, 0,
                       check_fans_present, duthost, present=True),
            "Not all fans are present after recovery"
        )
        check_all_fan_status_ok(duthost)


def get_fan_info(duthost):
    """
    Get fan status from "show platform fan" command.
    PSU fans are excluded.
    """
    fan_info = duthost.show_and_parse('show plat fan | egrep "rawer|--"')
    return fan_info


def simulate_fan_removal(duthost, fan_name):
    """
    Simulate fan removal by manipulating hw-mgmt sysfs file.
    """
    fan_status_file = HW_MGMT_FAN_STATUS_PATH.format(fan_name)
    duthost.shell(f"sudo rm -rf {fan_status_file}")
    duthost.shell(f"sudo bash -c 'echo 0 > {fan_status_file}'")


def recover_fan_symlink(duthost, random_selected_fan, original_symlink_target):
    """
    Recover the fan by restoring the original symlink.
    """
    logger.info(f"Recovering fan {random_selected_fan} by restoring symlink")
    fan_status_file = HW_MGMT_FAN_STATUS_PATH.format(random_selected_fan)
    duthost.shell(f"sudo rm -rf {fan_status_file}")
    duthost.shell(f"sudo ln -s {original_symlink_target} {fan_status_file}")


def check_fans_present(duthost, fan_name_list=None, present=True):
    """
    Check if one or more fans are present or not present in "show platform fan" output.
    """
    if not fan_name_list:
        fan_name_list = [f"fan{i}" for i in range(1, FAN_NUMBER + 1)]
    fan_info = get_fan_info(duthost)
    failures = []
    fans_found = []
    for fan in fan_info:
        name = fan["fan"]
        if name in fan_name_list:
            fans_found.append(name)
            fan_presence = fan["presence"] == "Present"
            if fan_presence is not present:
                failures.append(name)
    assert len(fans_found) == len(fan_name_list), f"Some fans in {fan_name_list} are not found on the dut."
    if failures:
        return False
    else:
        return True


def check_remaining_fans_speed_reduced(duthost, removed_fan_name):
    """
    Check that all remaining (present) fans have speed less than 100%.
    """
    fan_info = get_fan_info(duthost)
    for fan in fan_info:
        name = fan["fan"]
        if name == removed_fan_name:
            continue
        speed = int(re.match(r"(\d+)%", fan["speed"]).group(1))
        pytest_assert(speed < 100, f"Fan {name} has speed 100%, expected less than 100%")


def get_and_check_fan_directions(duthost):
    """
    Get direction of all fans.
    All fans should run in the same direction.
    """
    direction = None
    fan_info = get_fan_info(duthost)
    for fan in fan_info:
        pytest_assert(fan["direction"] in ["exhaust", "intake"], f"Unexpected fan direction: {fan['direction']}")
        if direction and direction != fan['direction']:
            pytest_assert(False, "Not all fans are running in the same direction.")
        direction = fan['direction']
    return direction


def check_all_fan_status_ok(duthost):
    """
    Check that all fans are OK.
    """
    fan_info = get_fan_info(duthost)
    pytest_assert(len(fan_info) == FAN_NUMBER, f"Expected 4 fans, found: {len(fan_info)}")
    pytest_assert(all(fan_status["status"] == "OK" for fan_status in fan_info), "Some fans are not OK")


def test_reduce_fan_speed_sn4280(duthost, random_selected_fan, recover_fan):
    """
    Test to verify fan speed reduction feature on SN4280 platform.
    This test validates that when a fan is removed, the remaining active fans reduce their speed
    below 100% to lower internal pressure and prevent a newly inserted fan from spinning in
    the wrong direction.
    """
    logger.info("Checking initial fan status and directions")
    check_all_fan_status_ok(duthost)
    initial_direction = get_and_check_fan_directions(duthost)
    logger.info(f"Initial fan directions: {initial_direction}")

    logger.info(f"Selected a random fan to simulate removal: {random_selected_fan}")
    simulate_fan_removal(duthost, random_selected_fan)

    logger.info("Waiting for fan status update, fan status should be not present")
    pytest_assert(
        wait_until(SHOW_PLATFORM_FAN_UPDATE_INTERVAL, 5, 0,
                   check_fans_present, duthost, [random_selected_fan], False),
        f"Fan {random_selected_fan} is still showing as present after simulated removal"
    )

    logger.info("Checking remaining fans speed is less than 100%")
    check_remaining_fans_speed_reduced(duthost, random_selected_fan)
    logger.info(f"Wait {SHOW_PLATFORM_FAN_UPDATE_INTERVAL} seconds and check again")
    time.sleep(SHOW_PLATFORM_FAN_UPDATE_INTERVAL)
    check_remaining_fans_speed_reduced(duthost, random_selected_fan)

    logger.info(f"Recovering fan {random_selected_fan}")
    recover_fan_symlink(duthost, random_selected_fan, recover_fan)
    pytest_assert(
        wait_until(SHOW_PLATFORM_FAN_UPDATE_INTERVAL, 5, 0,
                   check_fans_present, duthost, present=True),
        "Not all fans are present"
    )
    check_all_fan_status_ok(duthost)

    # Verify fan directions have not changed
    final_directions = get_and_check_fan_directions(duthost)
    logger.info(f"Validate final fan directions: {final_directions}")
    pytest_assert(final_directions == initial_direction,
                  "Fan directions changed after fan removal and recovery")
