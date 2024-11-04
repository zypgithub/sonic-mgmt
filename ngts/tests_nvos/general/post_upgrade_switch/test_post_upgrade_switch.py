import logging
from typing import Dict, Tuple

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.post_upgrade_switch.constants import UPGRADE_STATUS_FILE_PATH, UPGRADE_STATUS_FAIL_PREFIX, \
    InstallSteps
from ngts.tests_nvos.general.post_upgrade_switch.install_steps_timer import InstallStepsTimer
from ngts.tools.test_utils import allure_utils as allure


def test_post_upgrade_switch(engines):
    """
    This test is to perform checks after the Install step of regression, such that if the checks fail, do not fail
        the entire regression
    """
    with allure.step('make post install & upgrade checks'):
        with allure.independent_step('check upgrade with saved config status'):
            check_result_of_upgrade_with_save_config(engines.dut)
        with allure.independent_step('check upgrade with saved config status'):
            check_install_and_upgrade_steps_intervals()


def check_result_of_upgrade_with_save_config(dut_engine: LinuxSshEngine):
    out = dut_engine.run_cmd(f'cat {UPGRADE_STATUS_FILE_PATH}')
    assert UPGRADE_STATUS_FAIL_PREFIX not in out, f'upgrade with saved config failed\n{out}'


def check_install_and_upgrade_steps_intervals():
    """
    Verify if the intervals between specified steps are within the defined limits.
    Raises an AssertionError if any limit is exceeded.
    """
    InstallStepsTimer.print_saved_timestamps()

    # Constant dictionary for step limits
    intervals_limit: Dict[Tuple[str, str], float] = {
        (InstallSteps.ONIE_NOS_INSTALL, InstallSteps.SYSTEM_IS_READY_AFTER_MANUFACTURE): 10 * MINUTE,
        (InstallSteps.UPGRADE_CMD, InstallSteps.SHUT_DOWN): 10 * MINUTE,
        (InstallSteps.UPGRADE_CMD, InstallSteps.SYSTEM_IS_READY_AFTER_UPGRADE): 15 * MINUTE,
    }

    with allure.step('verify install/upgrade intervals against defined limits'):
        for (start_key, end_key), limit in intervals_limit.items():
            if InstallStepsTimer.get_timestamp(start_key) and InstallStepsTimer.get_timestamp(start_key):
                with allure.independent_step(f'verify that: from "{start_key}" to "{end_key}" <= {limit} seconds'):
                    interval = InstallStepsTimer.calculate_interval(start_key, end_key)
                    logging.info(f'actual interval: from "{start_key}" to "{end_key}" - {interval} seconds')
                    if interval is None:
                        raise AssertionError(f"Could not calculate interval between {start_key} and {end_key}")
                    assert interval <= limit, f"Time limit exceeded: {start_key} to {end_key} took {interval:.2f}s, limit is {limit}s"
                    logging.info(f"Verified: {start_key} to {end_key} took {interval:.2f}s (limit: {limit}s)")
