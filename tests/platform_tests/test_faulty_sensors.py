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
STABILIZE_WAIT = 60


def _get_all_sensor_links(duthost):
    """Return dict of {link_path: original_target} for all symlinks under all sensor dirs."""
    # Build single command to find all symlinks and their targets
    # Output format: link_path -> target (one per line)
    find_cmds = []
    for sensor_dir in HW_MGMT_SENSOR_DIRS:
        # For each symlink, print "link_path|target"
        find_cmds.append(
            'find {} -maxdepth 1 -type l -exec sh -c \'echo "{{}}|$(readlink -f "{{}}")" \' \\;'.format(sensor_dir)
        )

    # Combine all find commands
    combined_cmd = " ; ".join(find_cmds)
    output = duthost.shell(combined_cmd, module_ignore_errors=True)["stdout_lines"]

    links = {}
    for line in output:
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            links[parts[0]] = parts[1]
    return links


def _restore_all_links(duthost, links):
    """Restore all symlinks to their original targets."""
    if not links:
        return

    # Build batch command: ln -sf target1 link1 ; ln -sf target2 link2 ; ...
    ln_cmds = []
    for link_path, target in links.items():
        ln_cmds.append("ln -sf '{}' '{}'".format(target, link_path))

    # Execute all ln commands in one SSH call
    batch_cmd = "sudo sh -c '{}'".format(" ; ".join(ln_cmds))
    duthost.shell(batch_cmd, module_ignore_errors=True)


def _verify_links_restored(duthost, original_links):
    """Verify each symlink points back to its original target."""
    if not original_links:
        return

    # Build command to read all link targets at once
    # Output: link_path|current_target
    link_paths = list(original_links.keys())
    readlink_cmd = " ; ".join(
        'echo "{}|$(readlink -f \'{}\')"'.format(lp, lp) for lp in link_paths
    )

    output = duthost.shell(readlink_cmd, module_ignore_errors=True)["stdout_lines"]

    # Parse output and build current state
    current_links = {}
    for line in output:
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            current_links[parts[0]] = parts[1]

    # Verify all links
    mismatches = []
    for link_path, expected_target in original_links.items():
        actual = current_links.get(link_path, "")
        if actual != expected_target:
            mismatches.append(
                "Link {} not restored: expected {}, got {}".format(
                    link_path, expected_target, actual))

    pytest_assert(not mismatches, "\n".join(mismatches))


@pytest.fixture(scope="module")
def check_platform_support(duthosts, enum_rand_one_per_hwsku_hostname):
    """
    Check if the platform supports faulty sensor tests.
    Skip if running on simx (no real hardware sensors) or non-Mellanox platforms.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]

    if "simx" in duthost.facts["platform"]:
        pytest.skip("Test not supported on simx platform - no real hardware sensors")

    if not mellanox_data.is_mellanox_device(duthost):
        pytest.skip("Only applicable to Mellanox platforms")

    return duthost


def test_remove_all_sensor_links(check_platform_support):
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
    duthost = check_platform_support

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


def test_relink_all_sensors_to_garbage_file(check_platform_support):
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
    duthost = check_platform_support

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
