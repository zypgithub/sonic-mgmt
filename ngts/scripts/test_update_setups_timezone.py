import logging
import pytest
import time
import allure
import multiprocessing
from ngts.tools.topology_tools.topology_by_setup import get_topology_by_setup_name_and_aliases

logger = logging.getLogger()


def update_ntp_for_single_setup(setup_name, results_queue):
    """
    Updates the local timezone and manually sets the system time to Israel (Asia/Jerusalem).
    :param setup_name (str): The name of the setup to be updated.
    :param results_queue (multiprocessing.Queue): A queue to store results for logging and processing.
    """
    try:
        topology_obj = get_topology_by_setup_name_and_aliases(setup_name, slow_cli=False)
        players_engines = []
        if 'dut' in topology_obj.players:
            players_engines.append((topology_obj.players['dut']['engine'], 'dut'))
        if 'hypervisor' in topology_obj.players:
            players_engines.append((topology_obj.players['hypervisor']['engine'], 'hypervisor'))
        if 'fanout' in topology_obj.players:
            players_engines.append((topology_obj.players['fanout']['engine'], 'fanout'))

        failed_devices = []
        success_devices = []

        for engine, device_name in players_engines:
            try:
                if set_timezone(engine):
                    success_devices.append(device_name)
                else:
                    failed_devices.append(device_name)
            except Exception as e:
                logger.error(f"Exception setting timezone on {device_name}: {e}")
                failed_devices.append(device_name)

        handle_results(setup_name, success_devices, failed_devices, results_queue)

    except Exception as err:
        results_queue.put((setup_name, f'Failed to update "{setup_name}" (partial/full). ERROR: {err}', False))


def set_timezone(engine):
    """
    Attempts to set the timezone on a given engine.
    :param engine: The engine object that allows running commands.
    :return bool: True if the timezone was set successfully, False otherwise.
    """

    def _get_timezone(engine):
        """ Fetches the current timezone from available sources. """
        commands = ['date', 'cat /etc/timezone', 'timedatectl', 'show clock']
        for cmd in commands:
            output = engine.run_cmd(cmd, validate=True)
            if output:
                return output.strip()
        return ""

    def _is_timezone_correct(output):
        """ Checks if the timezone is correctly set to Asia/Jerusalem. """
        return output and ('IST' in output or 'Asia/Jerusalem' in output)

    try:
        current_time_output = _get_timezone(engine)

        if _is_timezone_correct(current_time_output):
            return True

        engine.run_cmd('sudo ln -sf /usr/share/zoneinfo/Asia/Jerusalem /etc/localtime', validate=False)

        updated_time_output = _get_timezone(engine)

        return _is_timezone_correct(updated_time_output)

    except Exception:
        return False


def handle_results(setup_name, success_devices, failed_devices, results_queue):
    """
    Handles logging and queueing results after attempting to update timezone.
    :param setup_name (str): The name of the setup.
    :param success_devices (list): List of devices where timezone update was successful.
    :param failed_devices (list): List of devices where timezone update failed.
    :param results_queue (multiprocessing.Queue): Queue for storing results.
    """
    if len(failed_devices) == 0:
        result = f"Setup: {setup_name} : {success_devices}, Time & TimeZone updated to Asia/Jerusalem (Israel)."
        results_queue.put((setup_name + ": all devices", result, True))
    elif len(success_devices) == 0:
        results_queue.put((setup_name, f"Update process failed for setup {setup_name}.", False))
    else:
        success_result = f"Setup: {setup_name} : {success_devices}, TimeZone updated to Asia/Jerusalem (Israel)."
        failure_result = f"Setup: {setup_name} : {failed_devices}, TimeZone was not updated."
        results_queue.put((setup_name + ": success", success_result, True))
        results_queue.put((setup_name + ": failure", failure_result, False))


@pytest.mark.disable_loganalyzer
@allure.title('Updates the local timezone and manually sets the system time to Israel (Asia/Jerusalem)')
def test_update_ntp_server(setups_list):
    """
    Runs the NTP update process for multiple setups in parallel.
    :param setups_list : A fixture that returns the list of setup names that belongs to SONiC Canonical/Community.
    """
    start_time = time.time()
    processes = []
    results_queue = multiprocessing.Queue()
    failed_updates = []

    for setup_name in setups_list:
        with allure.step(f"Starting NTP update for setup: {setup_name}"):
            process = multiprocessing.Process(target=update_ntp_for_single_setup, args=(setup_name, results_queue))
            processes.append((setup_name, process))
            process.start()

    for setup_name, process in processes:
        with allure.step(f"Waiting for process to finish: {setup_name}"):
            process.join(timeout=60)

            if process.is_alive():
                process.terminate()
                process.join()
                results_queue.put((setup_name, "ERROR: Process timeout", False))

    while not results_queue.empty():
        setup_name, result, success = results_queue.get()
        with allure.step(f"Logging results for {setup_name}"):
            if success:
                logger.info(result)
            else:
                failed_updates.append(result)

    for failure in failed_updates:
        logger.error(failure)

    logger.info(f"Total test execution time: {time.time() - start_time:.2f} seconds")

    if failed_updates:
        logger.error("Some setups timezones were not fully updated")
