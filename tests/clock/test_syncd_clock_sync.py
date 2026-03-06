import logging
import re
import datetime as dt

import pytest

from tests.common.mellanox_data import is_mellanox_device
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
    pytest.mark.skip_check_dut_health,
    pytest.mark.clock
]

PTP_CLOCK_SYNC_MARGIN = 2
CMD_LIST_PTP_DEVICES = "ls /dev/ptp[0-9]* 2>/dev/null"
PHC_CLOCK_TIME_PATTERN = r'clock time is (\d+\.\d+)'
ASIC_PTP_CLOCK_NAMES = [
    'sx_ptp',      # Mellanox/NVIDIA Spectrum ASIC
]


def get_asic_ptp_device(duthost):
    """
    Get ASIC PTP clock device inside syncd container.

    Returns:
        str: ASIC PTP device path (e.g., '/dev/ptp1') if found, None otherwise
    """
    ptp_list_cmd = f"docker exec syncd {CMD_LIST_PTP_DEVICES}"
    ptp_result = duthost.shell(ptp_list_cmd, module_ignore_errors=True)

    if ptp_result['rc'] != 0 or not ptp_result['stdout'].strip():
        logging.info('No PTP devices found in syncd container')
        if is_mellanox_device(duthost):
            pytest.fail('No PTP devices found in syncd container on Mellanox device')
        return None

    ptp_devices = ptp_result['stdout'].strip().split()
    logging.info(f'Found PTP devices: {ptp_devices}')

    for ptp_dev in ptp_devices:
        dev_num = ptp_dev.split('ptp')[-1]
        clock_name_cmd = f"cat /sys/class/ptp/ptp{dev_num}/clock_name"
        clock_name_result = duthost.shell(clock_name_cmd, module_ignore_errors=True)

        if clock_name_result['rc'] != 0:
            logging.warning(f'Failed to get clock_name for {ptp_dev}')
            continue

        clock_name = clock_name_result['stdout'].strip()
        logging.info(f'PTP device {ptp_dev} clock_name: {clock_name}')

        if clock_name in ASIC_PTP_CLOCK_NAMES:
            logging.info(f'Found ASIC PTP clock: {ptp_dev} (clock_name: {clock_name})')
            return ptp_dev

    logging.info('No ASIC PTP clock found in syncd container')
    if is_mellanox_device(duthost):
        pytest.fail('No ASIC PTP clock found in syncd container on Mellanox device')
    return None


def get_ptp_clock_time(duthost, ptp_dev):
    """
    Get PTP clock time using phc_ctl command inside syncd container.

    Returns:
        tuple: (ptp_time, cmd_duration) if successful, (None, None) otherwise.
               cmd_duration is the command execution time in seconds.
    """
    phc_ctl_cmd = f"docker exec syncd phc_ctl {ptp_dev} get"
    phc_result = duthost.shell(phc_ctl_cmd, module_ignore_errors=True)

    if phc_result['rc'] != 0:
        logging.error(f'Failed to get clock time for {ptp_dev}: {phc_result["stderr"]}')
        return None, None

    phc_output = phc_result['stdout'].strip()
    logging.info(f'phc_ctl output: {phc_output}')

    match = re.search(PHC_CLOCK_TIME_PATTERN, phc_output)
    if not match:
        logging.error(f'Could not parse clock time from output: {phc_output}')
        return None, None

    ptp_time = float(match.group(1))

    delta_time = dt.datetime.strptime(phc_result['delta'], '%H:%M:%S.%f')
    cmd_duration = delta_time.hour * 3600 + delta_time.minute * 60 + delta_time.second + delta_time.microsecond / 1e6
    logging.info(f'Command execution time: {cmd_duration:.6f}s')

    return ptp_time, cmd_duration


def test_syncd_ptp_clock_sync(duthosts, rand_one_dut_hostname):
    """
    @summary:
        Test that ASIC PTP clock inside syncd container is synchronized with the system clock.

        Steps:
        1. Check if phc_ctl is available in syncd container
        2. Find ASIC PTP clock inside syncd container
        3. Skip test if no ASIC PTP clock found
        4. Get ASIC PTP clock time using phc_ctl
        5. Verify the time difference with system clock is within acceptable margin
    """
    duthost = duthosts[rand_one_dut_hostname]

    with allure.step('Check if phc_ctl is available in syncd container'):
        phc_ctl_check = duthost.shell("docker exec syncd which phc_ctl", module_ignore_errors=True)
        if phc_ctl_check['rc'] != 0:
            pytest.skip("phc_ctl not available in syncd container (linuxptp not installed)")

    with allure.step('Get ASIC PTP clock inside syncd container'):
        asic_ptp_dev = get_asic_ptp_device(duthost)
        if asic_ptp_dev is None:
            pytest.skip("No ASIC PTP clock found in syncd container")

    with allure.step('Get ASIC PTP clock time'):
        ptp_time, cmd_duration = get_ptp_clock_time(duthost, asic_ptp_dev)
        if ptp_time is None:
            pytest.fail(f'Failed to get PTP clock time for {asic_ptp_dev}')

    with allure.step('Compare ASIC PTP clock with system clock'):
        system_time = float(duthost.shell("date +%s.%N")['stdout'].strip())

        time_diff = abs(ptp_time - system_time)
        effective_margin = PTP_CLOCK_SYNC_MARGIN + cmd_duration

        logging.info(f'ASIC PTP time: {ptp_time} ({dt.datetime.fromtimestamp(ptp_time)})')
        logging.info(f'System time: {system_time} ({dt.datetime.fromtimestamp(system_time)})')
        logging.info(f'Time difference: {time_diff:.3f}s')
        logging.info(f'Effective margin (base {PTP_CLOCK_SYNC_MARGIN}s + '
                     f'cmd_duration {cmd_duration:.3f}s): {effective_margin:.3f}s')

        assert time_diff <= effective_margin, \
            f'ASIC PTP clock is not synchronized with system clock. ' \
            f'Diff: {time_diff:.3f}s (max allowed: {effective_margin:.3f}s)'

        logging.info('ASIC PTP clock is synchronized with system clock (diff: {:.3f}s)'.format(time_diff))
