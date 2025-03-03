import threading
import time
import allure
import logging
from pexpect.exceptions import EOF
import pytest

from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


def restart_getty_service(dut_engine):
    with allure.step('Restarting serial-getty@ttyS0.service'):
        dut_engine.run_cmd("sudo systemctl restart serial-getty@ttyS0.service")
        time.sleep(5)


def stress_getty(serial_engine, duration, stop_event):
    try:
        start_time = time.time()
        while not stop_event.is_set() and time.time() - start_time < duration:
            thread_name = threading.current_thread().name
            logger.info(f'[{thread_name}] Send CTRL+D (multiple times) to force new login for current connection')
            for _ in range(4):
                serial_engine.run_cmd('\x04', expected_value=" ")
            if stop_event.is_set():
                break
            logger.info(f'[{thread_name}] trying to get login regex')
            _, respond_index = serial_engine.run_cmd('\x04', DefaultConnectionValues.LOGIN_REGEX)
            time.sleep(0.1)
    except EOF as e:
        logger.error(f"[{threading.current_thread().name}] EOF error during stress test: {e}")
        stop_event.set()  # Signal other threads to stop
        raise e
    except Exception as e:
        logger.error(f"[{threading.current_thread().name}] Error during stress test: {e}")
        stop_event.set()  # Signal other threads to stop
        raise e


def monitor_service(dut_engine, duration, stop_event):
    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            result = dut_engine.run_cmd("systemctl status serial-getty@ttyS0.service")
            if "start-limit-hit" in result:
                stop_event.set()
                logger.error(f"[{threading.current_thread().name}] start-limit-hit detected!")
                restart_getty_service(dut_engine)
                break
            time.sleep(1)
    except Exception as e:
        logger.error(f"[{threading.current_thread().name}] Error during service monitoring: {e}")


@pytest.mark.system
def test_stress_serial_connection(engines, devices, topology_obj):
    DURATION = 10  # Duration for the stress test in seconds

    with allure.step('get serial engine'):
        serial_engine = ConnectionTool.create_serial_engine(topology_obj, enter_serial_context=True)

    stop_event = threading.Event()

    try:
        with allure.step('Start a thread to stress test the serial connection'):
            thread = threading.Thread(target=stress_getty, args=(serial_engine, DURATION, stop_event), name=f"StressThread")
            thread.start()

        with allure.step('Start a thread to monitor the service status'):
            monitor_thread = threading.Thread(target=monitor_service, args=(engines.dut, DURATION, stop_event), name="MonitorThread")
            monitor_thread.start()

        # Wait for the threads to complete
        thread.join()
        monitor_thread.join()

        with allure.step("Assert for 'start-limit-hit'"):
            assert not stop_event.is_set(), "serial-getty@ttyS0.service: Failed with result 'start-limit-hit'."

        logger.info("Stress test completed.")

    finally:
        status = engines.dut.run_cmd("systemctl status serial-getty@ttyS0.service")
        if not "active (running)" in status:
            restart_getty_service(engines.dut)
            status = engines.dut.run_cmd("systemctl status serial-getty@ttyS0.service")

        assert "active (running)" in status, "Failed to restart serial-getty@ttyS0 service."
