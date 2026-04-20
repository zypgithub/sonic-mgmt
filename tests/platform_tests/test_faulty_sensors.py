"""
Tests for sensor fault robustness.

Validates that the system remains stable when all sensor
sysfs symlinks are removed or replaced with garbage data.
Covers thermal, power, and alarm directories under hw-management.
"""

import logging
import time

import pytest

from tests.common.helpers.assertions import pytest_assert
from tests.common import mellanox_data
from tests.common.utilities import wait_until

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer,
]

HW_MGMT_SENSOR_DIRS = [
    "/var/run/hw-management/thermal/",
    "/var/run/hw-management/power/",
    "/var/run/hw-management/alarm/",
]
GARBAGE_FILE = "/tmp/garbage_2m"
STABILIZE_WAIT = 30


def _get_all_sensor_links(duthost):
    """Return dict of {link_path: original_target} for all symlinks under all sensor dirs."""
    links = {}
    for sensor_dir in HW_MGMT_SENSOR_DIRS:
        output = duthost.shell(
            "find {} -maxdepth 1 -type l".format(sensor_dir),
            module_ignore_errors=True)["stdout_lines"]
        for link_path in output:
            link_path = link_path.strip()
            if not link_path:
                continue
            target = duthost.shell(
                "readlink -f {}".format(link_path),
                module_ignore_errors=True)["stdout"].strip()
            if target:
                links[link_path] = target
    return links


def _restore_all_links(duthost, links):
    """Restore all symlinks to their original targets."""
    for link_path, target in links.items():
        duthost.shell(
            "sudo ln -f -s {} {}".format(target, link_path),
            module_ignore_errors=True)


def _verify_links_restored(duthost, original_links):
    """Verify each symlink points back to its original target."""
    for link_path, expected_target in original_links.items():
        actual = duthost.shell(
            "readlink -f {}".format(link_path),
            module_ignore_errors=True)["stdout"].strip()
        pytest_assert(
            actual == expected_target,
            "Link {} not restored: expected {}, got {}".format(
                link_path, expected_target, actual))


def test_remove_all_sensor_links(duthosts, enum_rand_one_per_hwsku_hostname):
    """
    Remove all sensor symlinks and verify system stability.

    Test flow:
        1. Collect all symlinks and their original targets from
           thermal, power, and alarm directories
        2. Remove every symlink
        3. Wait for daemon polling cycle
        4. Verify all critical services are still running
        5. Restore all symlinks and verify recovery
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]

    if not mellanox_data.is_mellanox_device(duthost):
        pytest.skip("Only applicable to Mellanox platforms")

    original_links = _get_all_sensor_links(duthost)
    pytest_assert(len(original_links) > 0, "No sensor symlinks found")
    logger.info("Found %d sensor symlinks across %d directories",
                len(original_links), len(HW_MGMT_SENSOR_DIRS))

    try:
        for link_path in original_links:
            duthost.shell("sudo unlink {}".format(link_path),
                          module_ignore_errors=True)
        logger.info("Removed all %d sensor symlinks", len(original_links))

        time.sleep(STABILIZE_WAIT)

        pytest_assert(
            wait_until(120, 10, 0, duthost.critical_services_fully_started),
            "Critical services not fully started after removing all sensor links")
        logger.info("System stable after removing all sensor links")

    finally:
        logger.info("Restoring all sensor symlinks")
        _restore_all_links(duthost, original_links)
        time.sleep(STABILIZE_WAIT)
        _verify_links_restored(duthost, original_links)
        logger.info("All symlinks restored successfully")

        pytest_assert(
            wait_until(120, 10, 0, duthost.critical_services_fully_started),
            "Critical services not fully started after restoring sensor links")


def test_relink_all_sensors_to_garbage_file(duthosts, enum_rand_one_per_hwsku_hostname):
    """
    Relink all sensor symlinks to a 2MB garbage file and verify
    system stability.

    Test flow:
        1. Create a 2MB file filled with random data
        2. Collect all symlinks and their original targets from
           thermal, power, and alarm directories
        3. Repoint every symlink to the garbage file
        4. Wait for daemon polling cycle
        5. Verify all critical services are still running
        6. Restore all symlinks, remove garbage file, verify recovery
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]

    if not mellanox_data.is_mellanox_device(duthost):
        pytest.skip("Only applicable to Mellanox platforms")

    duthost.shell("dd if=/dev/urandom of={} bs=1M count=2".format(GARBAGE_FILE))
    logger.info("Created 2MB garbage file at %s", GARBAGE_FILE)

    original_links = _get_all_sensor_links(duthost)
    pytest_assert(len(original_links) > 0, "No sensor symlinks found")
    logger.info("Found %d sensor symlinks across %d directories",
                len(original_links), len(HW_MGMT_SENSOR_DIRS))

    try:
        for link_path in original_links:
            duthost.shell("sudo ln -sf {} {}".format(GARBAGE_FILE, link_path),
                          module_ignore_errors=True)
        logger.info("Relinked all %d sensor symlinks to %s",
                    len(original_links), GARBAGE_FILE)

        time.sleep(STABILIZE_WAIT)

        pytest_assert(
            wait_until(120, 10, 0, duthost.critical_services_fully_started),
            "Critical services not fully started after relinking to garbage file")
        logger.info("System stable after relinking all sensor files to garbage")

    finally:
        logger.info("Restoring all sensor symlinks")
        _restore_all_links(duthost, original_links)
        duthost.shell("rm -f {}".format(GARBAGE_FILE), module_ignore_errors=True)
        time.sleep(STABILIZE_WAIT)
        _verify_links_restored(duthost, original_links)
        logger.info("All symlinks restored successfully")

        pytest_assert(
            wait_until(120, 10, 0, duthost.critical_services_fully_started),
            "Critical services not fully started after restoring sensor links")
