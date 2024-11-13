import pytest
import logging
import time
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure


logger = logging.getLogger()
QOS_COUNTER_CHECK_CMD = "redis-cli keys _BUFFER_* | grep -v 'empty array' | awk 'NF' | wc -l"
MAX_ATTEMPTS = 100


def check_qos_counter_status(engines):
    """
    Execute command "redis-cli keys _BUFFER_* | grep -v 'empty array' | awk 'NF' | wc -l" on the DUT.
    If the returned value is 0, the QOS counter is ready.
    If the value is not 0, it waits for 5 seconds and checks again until it reaches 100 attempts.
    If the counter is not ready after the maximum attempts, an exception is raised.
    """
    dut_engine = engines.dut
    max_attempts = MAX_ATTEMPTS
    attempts = 0
    logger.info("Starting to check if QOS counter is ready")

    while attempts < max_attempts:
        output = dut_engine.run_cmd(QOS_COUNTER_CHECK_CMD)
        logger.info(f"Check attempt {attempts + 1}: still has {output.strip()} QOS counter is not ready")

        if output.strip() == "0":
            logger.info("QOS counter is ready")
            return

        time.sleep(5)
        attempts += 1

    logger.error("QOS counter is not ready, exceeded maximum attempts")
    raise AssertionError("QOS counter is not ready")


@pytest.fixture(scope='module', autouse=True)
def check_qos_counter_ready(engines):
    """
    A fixture to check if the QOS counter is ready.
    """
    with allure.step('Check QOS counter status before test run'):
        check_qos_counter_status(engines)

    yield

    with allure.step('Check QOS counter status after test run'):
        check_qos_counter_status(engines)