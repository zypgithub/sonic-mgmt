import concurrent.futures
import logging
import random
import re
import threading
import time

import pytest

from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@pytest.mark.check_disk_usage(expectedKbWritten=60000)
@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.ssh_config
@pytest.mark.system
def test_parallel_cli_commands(engines, devices):
    """
    Test flow:
        1. get max sessions value save as <max_sessions>
        2. Run mpstat -p ALL and save result as <memory_mpstat_output_before_testing>
        3. create <max_sessions> - 3 sessions
        4. Run mpstat -p ALL and save result as <memory_mpstat_output_after_connections>
        5. create 5 commands lists. save as cmds_list1, cmds_list2, cmds_list3, cmds_list4, cmds_list5
        6. run all sessions in parallel s.t. each session will select randomly one ofe the 5 lists and save all memory and CPU outputs
        7. verify that memory and CPU outputs fall within the expected intervals

    """
    system = System()
    with allure.step('Show ssh and verify default values'):
        ssh_output = OutputParsingTool.parse_json_str_to_dictionary(system.ssh_server.show()).get_returned_value()
        max_sessions = ssh_output[SystemConsts.SSH_CONFIG_MAX_SESSIONS] - 20
        sessions = []

    with allure.step('save memory and cpu before testing'):
        memory_mpstat_output_before_testing = run_memory_mpstat_commands(engines.dut)

    with allure.step(f'Create {max_sessions} sessions'):
        start_time = time.time()
        for conn_no in range(max_sessions):
            logger.info("Creating connection number: {}".format(conn_no + 1))
            connection = ConnectionTool.create_ssh_conn(engines.dut.ip, engines.dut.username,
                                                        engines.dut.password).get_returned_value()
            sessions.append(connection)

    with allure.step(f"verify {max_sessions} ssh-connections making time"):
        expected_time = 7.00
        time_per_connection = (time.time() - start_time) / max_sessions
        assert time_per_connection < expected_time, f"Despite the expected time per SSH connection being {expected_time} seconds, the actual time per connection is {time_per_connection}."

    with allure.step(f'save memory and cpu after {max_sessions} connections'):
        memory_mpstat_output_after_connections = run_memory_mpstat_commands(engines.dut)

    with allure.step('Create 5 lists of commands'):
        cmds_list1 = ['nv show system -o json']
        cmds_list2 = ["nv set system message pre-login 'test'", "nv config apply", "nv show system message -o json"]
        cmds_list3 = ['nv show interface -o json']
        cmds_list4 = ['nv show platform firmware -o json']
        cmds_list5 = ['nv show interface -o json']
        command_lists = [cmds_list1, cmds_list2, cmds_list3, cmds_list4, cmds_list5]
        keep_running_event = threading.Event()
        keep_running_event.set()

    try:
        with allure.step("Run all session in parallel"):
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_sessions) as executor:
                futures = []
                future_mem_cpu = executor.submit(memory_cpu_run, sessions[-1], keep_running_event)
                futures.append(future_mem_cpu)
                for i in range(max_sessions - 1):
                    future = executor.submit(run_session, sessions[i], command_lists, keep_running_event)
                    futures.append(future)

                with allure.step("run all threads for 2 minutes"):
                    time.sleep(120)
                    keep_running_event.clear()

                memory_mpstat_output_during_testing = future_mem_cpu.result()

    finally:
        with allure.step(f'save memory and cpu after closing {max_sessions} connections'):
            for connection in sessions:
                connection.disconnect()

            memory_mpstat_output_after_testing = run_memory_mpstat_commands(engines.dut)

        with allure.step("verify memory and cpu while running test"):
            validate_memory_and_cpu(memory_mpstat_output_before_testing, memory_mpstat_output_after_connections,
                                    memory_mpstat_output_during_testing, memory_mpstat_output_after_testing)


def run_session(session, commands_list, keep_running_event):
    """

    :param keep_running_event:
    :param session:
    :param commands_list:
    :return:
    """
    commands = random.choice(commands_list)
    with allure.step(f"This session will execute the following list of commands: {commands}."):
        while keep_running_event.is_set():
            for cmd in commands:
                session.run_cmd(cmd)
                time.sleep(7)


def memory_cpu_run(session, keep_running_event):
    """

    :return:
    """
    memory_cpu_outputs = []
    while keep_running_event.is_set():
        logger.info(" checking memory and cpu ")
        memory_cpu_outputs.append(run_memory_mpstat_commands(session))

    return memory_cpu_outputs


def parssing_memory_and_mpstat(memory, mp_stat):
    """

    :param memory:
    :param mp_stat:
    :return:
    """
    with allure.step("Parse memory and mpstat outputs"):
        result_dict = {"memory_utilization": round(memory[SystemConsts.MEMORY_PHYSICAL_KEY][SystemConsts.CPU_UTILIZATION_KEY] / 100, 2)}
        pattern = "(\\d{2}:\\d{2}:\\d{2} (?:AM|PM) ) (.{3})(.*)(\\d{2}\\.\\d{2})"
        regex = re.compile(pattern)
        matches = regex.findall(mp_stat)

        for match in matches:
            assert len(match) == 4, "mpstat parsing issue, we expect to match 4 groups"
            data = match[1].strip()

            busy_cpu_percent = round(1 - (float(match[3]) / 100), 2)
            key = 'CPU_all' if data.startswith('a') else "CPU" + data
            result_dict[key] = busy_cpu_percent

        return result_dict


def run_memory_mpstat_commands(engine):
    """

    :param engine:
    :return:
    """
    with allure.step("Run memory and mpstat commands"):
        memory_output = OutputParsingTool.parse_json_str_to_dictionary(
            engine.run_cmd('nv show system memory -o json')).verify_result()
        mpstat_output = engine.run_cmd('mpstat -P ALL')
        return parssing_memory_and_mpstat(memory_output, mpstat_output)


def validate_memory_and_cpu(before_testing, after_connections, during_testing={}, after_testing={}):
    """

    :param before_testing:
    :param after_connections:
    :param during_testing:
    :param after_testing:
    :return:
    """

    with allure.step("printing outputs"):
        logger.info(f"the memory and cpu before testing: \n {before_testing} \n")
        logger.info(f"the memory and cpu after connections: \n {after_connections} \n")
        logger.info(f"the memory and cpu during testing: \n {during_testing} \n")
        logger.info(f"the memory and cpu after testing: \n {after_testing} \n")

    with allure.step("validate memory and cpu after connections"):
        for key, value in after_connections.items():
            assert after_connections[key] - before_testing[key] < 0.1, f"unexpected change in {key} detected: initial output was {before_testing}, revised output after connections: {after_connections}"

    with allure.step("validate memory and cpu during testing"):
        for step in during_testing:
            for key, value in step.items():
                assert step[key] - before_testing[key] < 0.3, f"unexpected change in {key} detected: initial output was {before_testing}, revised output after connections: {step}"

    with allure.step("validate memory and cpu after testing"):
        for key, value in after_connections.items():
            assert after_testing[key] - before_testing[key] < 0.07, f"unexpected change in {key} detected: initial output was {before_testing}, revised output after connections: {after_testing}"
