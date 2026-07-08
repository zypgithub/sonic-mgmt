import logging

import pytest

from ngts.common.checkers import is_ver1_greater_or_equal_ver2
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

logger = logging.getLogger()

MIN_SDK_VERSION_FOR_DEBUG_STATE_FLAGS = "4.8.4000"


@pytest.fixture(scope='session')
def duthost(engines):
    return engines.dut


@pytest.fixture(scope='function')
def set_health_event_debug_state_flags(duthost, cli_objects):
    """
    Fixture to set health check debug state flags before test and restore after test.
    Only applies when SDK version is >= 4.8.4000.
    """
    sdk_version = cli_objects.dut.general.get_sdk_version()
    apply_debug_flags = is_ver1_greater_or_equal_ver2(
        sdk_version, MIN_SDK_VERSION_FOR_DEBUG_STATE_FLAGS
    )

    if apply_debug_flags:
        with allure.step('Enable health check debug state flags (Fatal-on-Warn)'):
            duthost.run_cmd(
                "sudo sh -c 'echo health_check set_debug_state_flags 1 1 > /proc/dbg_dump/dev_1/dbg_cmd'"
            )
            verify_debug_state_flags(duthost, enabled_flag='Fatal-on-Warn', disabled_flag='NONE')
    else:
        logger.info(
            "Skipping health check debug state flags setup - SDK version %s is below %s",
            sdk_version,
            MIN_SDK_VERSION_FOR_DEBUG_STATE_FLAGS,
        )

    yield

    if apply_debug_flags:
        with allure.step('Restore health check debug state flags'):
            duthost.run_cmd(
                "sudo sh -c 'echo health_check unset_debug_state_flags 1 1 > /proc/dbg_dump/dev_1/dbg_cmd'"
            )
            verify_debug_state_flags(duthost, enabled_flag='NONE', disabled_flag='Fatal-on-Warn')


def verify_debug_state_flags(dut_engine, enabled_flag, disabled_flag):
    output_lines = dut_engine.run_cmd('cat /proc/dbg_dump/dev_1/health_check_dump | grep flags')
    logger.info(f"Current debug state flags output: {output_lines}")

    assert f'Enabled flags' in output_lines and enabled_flag in output_lines
    assert f'Disabled flags' in output_lines and disabled_flag in output_lines
