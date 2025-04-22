import ast
import logging
import os
import random
import re
import signal
import time
from multiprocessing import Process

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import NvosConst, DatabaseConst, ApiType, ActionConsts, SystemConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, MAX_GNMI_SUBSCRIBERS, GnmicErr
from ngts.tests_nvos.system.gnmi.helpers import gnmi_basic_flow, validate_gnmi_is_running_and_stream_updates, \
    validate_show_gnmi, validate_gnmi_server_in_health_issues, run_gnmi_client_in_the_background, \
    verify_description_value, run_gnmi_client_and_parse_output, validate_gnmi_enabled_and_running, \
    validate_memory_and_cpu_utilization, get_infiniband_name_from_port_name, get_port_oid_from_infiniband_port, \
    create_gnmi_infiniband_list, validate_redis_cli_and_gnmi_commands_results, create_interface_state_commands_list, \
    create_gnmi_counter_list, create_platform_general_commands_list, change_interface_description, \
    verify_msg_not_in_out_or_err, verify_msg_in_out_or_err

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_basic_flow_poll(engines, topology_obj):
    """
    Check gnmi basic flow: show command , disable and enable commands, validate stream updates to gnmi-client,
     with subscribe mode - poll.
        Test flow:
            1. validate gnmi-server is running
            2. validate health status is OK
            3. change port description
            5. validate gnmi-server stream updates
            6. Disable gnmi-server
            7. validate gnmi-server is not running
            8. validate health status is OK
            9. enable gnmi-server
            10. validate gnmi-server is running
            11. validate gnmi-server stream updates
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    gnmi_basic_flow(engines, mode=GnmiMode.POLL, mgmt_port_name=mgmt_port_name)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_basic_flow_once(engines, topology_obj):
    """
    Check gnmi basic flow: show command , disable and enable commands, validate stream updates to gnmi-client,
     with subscribe mode - once.
        Test flow:
            1. validate gnmi-server is running
            2. validate health status is OK
            3. change port description
            5. validate gnmi-server stream updates
            6. Disable gnmi-server
            7. validate gnmi-server is not running
            8. validate health status is OK
            9. enable gnmi-server
            10. validate gnmi-server is running
            11. validate gnmi-server stream updates
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    gnmi_basic_flow(engines, mode=GnmiMode.ONCE, mgmt_port_name=mgmt_port_name)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_gnmi_basic_flow_stream(test_api, engines, topology_obj):
    """
    Check gnmi basic flow: show command , disable and enable commands, validate stream updates to gnmi-client,
     with subscribe mode - stream.
        Test flow:
            1. validate gnmi-server is running
            2. validate health status is OK
            3. change port description
            5. validate gnmi-server stream updates
            6. Disable gnmi-server
            7. validate gnmi-server is not running
            8. validate health status is OK
            9. enable gnmi-server
            10. validate gnmi-server is running
            11. validate gnmi-server stream updates
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    TestToolkit.tested_api = test_api
    gnmi_basic_flow(engines, mode=GnmiMode.STREAM, mgmt_port_name=mgmt_port_name)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_simulate_gnmi_server_failure(test_api, engines):
    """
    In this test we will simulate a gnmi-server failure,
    by disabling the auto restart and stop the gnmi-server docker,
    will validate that its still enabled but not running, health status changes and reconnect after restart the docker.
        Test flow:
            1. validate gnmi-server is running
            2. validate health status is OK
            3. change port description
            5. validate gnmi-server stream updates
            6. simulate gnmi-server failure
            7. validate gnmi-server is not running but enabled
            8. validate health status is not OK
            9. fix gnmi-server failure
            10. validate gnmi-server is running
            11. validate gnmi-server stream updates
    """
    TestToolkit.tested_api = test_api
    system = System()
    gnmi_server_obj = system.gnmi_server
    validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, engines.dut.ip)

    try:
        with allure.step('Simulate gnmi server failure'):
            Tools.DatabaseTool.sonic_db_cli_hset(engines.dut, '', DatabaseConst.CONFIG_DB_NAME, "FEATURE|gnmi-server",
                                                 "auto_restart", "disabled")
            engines.dut.run_cmd("docker stop gnmi-server")
            validate_show_gnmi(gnmi_server_obj, engines, gnmi_state=GnmiConsts.GNMI_STATE_DISABLED)
            sleep_time_for_health_issue = 6
            logger.info(f"sleep {sleep_time_for_health_issue} seconds until the health output will be updated")
            time.sleep(sleep_time_for_health_issue)
            validate_gnmi_server_in_health_issues(system, expected_gnmi_health_issue=True)
            logger.info(f"{GnmiConsts.GNMI_DOCKER} appears in the health issues as we expect, "
                        f"after the gnmi-server failure")
    finally:
        with allure.step('re-enable gnmi server'):
            Tools.DatabaseTool.sonic_db_cli_hset(engines.dut, '', DatabaseConst.CONFIG_DB_NAME, "FEATURE|gnmi-server",
                                                 "auto_restart", "enabled")
            engines.dut.run_cmd("docker start gnmi-server")
            gnmi_server_obj.disable_gnmi_server()
            gnmi_server_obj.enable_gnmi_server()
            logger.info("sleep 90 sec until validate stream updates")
            time.sleep(90)
            validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, engines.dut.ip)


@pytest.mark.system
@pytest.mark.gnmi
def test_updates_on_gnmi_stream_mode(engines, devices):
    """
        Test flow:
            1. validate gnmi is running and send updates
            2. change port description
            3. wait until get port description update
    """
    system = System()
    gnmi_server_obj = system.gnmi_server
    validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, engines.dut.ip)

    with allure.step("Change port description and wait until gnmi-client gets description update"):
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value
        xpath = f'interfaces/interface[name={selected_port.name}]/state/description'

        with allure.step('Run gnmi client command in the background'):
            background_process = run_gnmi_client_in_the_background(engines.dut.ip, xpath, devices.dut)

        with allure.step('Set port description'):
            port_description = Tools.RandomizationTool.get_random_string(7)
            selected_port.interface.set(NvosConst.DESCRIPTION, port_description, apply=True).verify_result()
            selected_port.update_output_dictionary()
            verify_description_value(selected_port.show_output_dictionary, port_description)

        if not is_bug_active(3727441):
            with allure.step('Kill gnmi client command and verify updates'):
                logger.info(f"sleep {GnmiConsts.SLEEP_TIME_FOR_UPDATE} sec until verify gnmi updates")
                time.sleep(GnmiConsts.SLEEP_TIME_FOR_UPDATE)
                os.killpg(os.getpgid(background_process.pid), signal.SIGTERM)
            gnmi_client_output, error = background_process.communicate()
            assert port_description in str(
                gnmi_client_output), "we expect to see the new port description in the gnmi-client output but we didn't.\n" \
                                     f"port description: {port_description}\n" \
                                     f"but got: {str(gnmi_client_output)}"


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_gnmi_bad_flow(test_api, engines, devices, setup_name):
    """
    Check gnmi bad flow:
        Test flow:
            1. validate gnmi is running and send updates
            2. invalid command
            3. Subscribe to the gnmi server for data that is not supported
            5. Subscribe to the gnmi server with bad xpath
    """
    TestToolkit.tested_api = test_api
    system = System()
    gnmi_server_obj = system.gnmi_server
    xpath = f'interfaces/interface[name={devices.dut.default_port}]/state/counters/in-broadcast-pkts'
    validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, engines.dut.ip)

    with allure.step("invalid command"):
        gnmi_server_obj.set(GnmiConsts.GNMI_STATE_FIELD, Tools.RandomizationTool.get_random_string(7), "Error")

    with allure.step("Subscribe to the gnmi server for data that is not supported"):
        xpath = f'interfaces/interface[name={devices.dut.default_port}]/state/counters/in-broadcast-pkts'
        gnmi_stream_updates = run_gnmi_client_and_parse_output(engines, devices, xpath, engines.dut.ip)
        gnmi_stream_updates_value = list(gnmi_stream_updates.values())
        if devices.dut.switch_type == NvosConst.NVL_SWITCH_TYPE:
            assert not gnmi_stream_updates_value, f'{xpath} is unsupported field, so we expect to have none, but got {gnmi_stream_updates_value}'
        else:
            assert gnmi_stream_updates_value[0] == '0', f'{xpath} is unsupported field, so we expect to have 0, but got {gnmi_stream_updates_value}'

    with allure.step("Subscribe to the gnmi server with bad xpath"):
        xpath = f'/{Tools.RandomizationTool.get_random_string(5)}/{Tools.RandomizationTool.get_random_string(5)}'
        run_gnmi_client_and_parse_output(engines, devices, xpath, engines.dut.ip)  # just want to be sure no LA errors


@pytest.mark.system
@pytest.mark.gnmi
def test_simulate_gnmi_client_failure(engines, devices):
    """
    In this test we will simulate a gnmi-client failure by killing the gnmi-client process,
    will validate that it’s still enabled and running on the switch, health status doesn’t change
     and reconnect after restart the process.
        Test flow:
            1. validate gnmi-server is running
            2. validate health status is OK
            3. change port description
            5. validate gnmi-server stream updates
            6. simulate gnmi-client failure
            7. validate gnmi-server is running and enabled
            8. validate health status is  OK
    """
    system = System()
    gnmi_server_obj = system.gnmi_server
    validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, engines.dut.ip)

    with allure.step('Simulate gnmi client failure'):
        with allure.step('Run gnmi client command in the background and sleep 3 sec'):
            background_process = run_gnmi_client_in_the_background(engines.dut.ip, '/interfaces', devices.dut)
            time.sleep(3)
        with allure.step('Kill gnmi client command'):
            os.killpg(os.getpgid(background_process.pid), signal.SIGTERM)
        validate_gnmi_enabled_and_running(gnmi_server_obj, engines)
        validate_gnmi_server_in_health_issues(system, expected_gnmi_health_issue=False)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_performance(engines, devices):
    """
    Run 10 gnmi-client process to the same switch, validate stream updates and switch state.
        Test flow:
            1. create 10 gnmi_clients
            2. change port description
            3. validate gnmi-server stream updates
    """
    num_engines = 10
    gnmi_clients_without_updates = 0
    threads = []
    result = []
    port_description = Tools.RandomizationTool.get_random_string(7)
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value

    with allure.step(f"run {num_engines} gnmi_client sessions in the background"):
        for engine_id in range(num_engines):
            threads.append(run_gnmi_client_in_the_background(engines.dut.ip,
                                                             f"interfaces/interface[name={selected_port.name}]/state/description",
                                                             devices.dut))

    with allure.step("validate memory and CPU utilization"):
        validate_memory_and_cpu_utilization()

    with allure.step(f"change port description"):
        selected_port.interface.set(NvosConst.DESCRIPTION, port_description, apply=True).verify_result()
        selected_port.update_output_dictionary()
        verify_description_value(selected_port.show_output_dictionary, port_description)
        logger.info(f"sleep {GnmiConsts.SLEEP_TIME_FOR_UPDATE} sec until we start validate the gnmi stream")
        time.sleep(GnmiConsts.SLEEP_TIME_FOR_UPDATE)

    with allure.step(f"stop the gnmi_client sessions and validate updates"):
        for thread in threads:
            os.killpg(os.getpgid(thread.pid), signal.SIGTERM)
            output, error = thread.communicate()
            result.append(output)
            if port_description not in str(output):
                gnmi_clients_without_updates += 1
        assert gnmi_clients_without_updates == 0, f"{gnmi_clients_without_updates} gnmi clients didn't get updates..{output}"


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_mapping_table(engines, devices):
    """
    test will validate all the mapping tables between the redis DB data and the gnmic output
    """
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value
    port_name = selected_port.name
    infiniband_name = get_infiniband_name_from_port_name(engines.dut, port_name)
    port_oid = get_port_oid_from_infiniband_port(engines.dut, infiniband_name)
    with allure.step("Validate infiniband table mapping"):
        gnmi_list = create_gnmi_infiniband_list(port_name, port_oid, infiniband_name)
        validate_redis_cli_and_gnmi_commands_results(engines, devices, gnmi_list)
    with allure.step("Validate interface state table mapping"):
        gnmi_list = create_interface_state_commands_list(port_name, infiniband_name)
        validate_redis_cli_and_gnmi_commands_results(engines, devices, gnmi_list)
    with allure.step("Validate counter table mapping"):
        gnmi_list = create_gnmi_counter_list(port_name, port_oid)
        validate_redis_cli_and_gnmi_commands_results(engines, devices, gnmi_list)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_platform_general_components(engines, devices):
    with allure.step("Create gnmi disk info mapping"):
        gnmi_list = create_platform_general_commands_list()
    with allure.step("Validate disk and ram fields"):
        validate_redis_cli_and_gnmi_commands_results(engines, devices, gnmi_list, allowed_range_in_bytes=20)


# -------------- NEW -------------- #

@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_max_subscribers(engines, local_adminuser):
    """
    verify that max number of subscribers cannot be exceeded

    1. subscribe MAX gnmi clients
    2. change port description - expect all get updates
    3. subscribe another client
    4. change port description
    5. verify last user fails and don't receive update
    """
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value
    client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, local_adminuser.username,
                        local_adminuser.password)
    with allure.step(f'subscribe {MAX_GNMI_SUBSCRIBERS} clients'):
        for i in range(MAX_GNMI_SUBSCRIBERS):
            with allure.step(f'subscribe client #{i}'):
                client.gnmic_subscribe_interface_and_keep_session_alive(GnmiMode.STREAM, selected_port.name,
                                                                        skip_cert_verify=True)
                time.sleep(1)
    with allure.step('subscribe another client'):
        last_process = client.gnmic_subscribe_interface_and_keep_session_alive(GnmiMode.STREAM, selected_port.name,
                                                                               skip_cert_verify=True)
    with allure.step('change port description'):
        new_description = change_interface_description(selected_port)
    with allure.step('verify last user fails and do not receive update'):
        out, err = client.close_session_and_get_out_and_err(last_process)
        verify_msg_in_out_or_err(GnmicErr.NO_SUBSCRIBER_SLOT_AVAILABLE, out, err)
        verify_msg_not_in_out_or_err(new_description, out, err)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_events_overload(engines, devices):
    """
    Run 10 gnmi-client process to the same switch, validate CPU state when events stream updates reaches maximum
        Test flow:
            1. Check CPU, Memory and mpstat
            2. Create 10 gnmi_clients
            3. Set events table size to maximum ie 10000
            4. Clear system events
            5. Start monitoring CPU usage against maximum allowed for the whole time at every 10 seconds
            6. Create 50 events to simulate stream update for these events
            7. Repeat tep 5 till total number of events reached 5000
            8. Kill all gnmi_clients created in step 1
            9. Unset events table size to default it to 1000
            10. Clear system events
            11. Check CPU, Memory and mpstat
    """
    pattern = "(\\d{2}:\\d{2}:\\d{2} (?:AM|PM) ) (.{3})(.*)(\\d{2}\\.\\d{2})"
    regex = re.compile(pattern)
    system = System()
    client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, devices.dut.default_username,
                        devices.dut.default_password)

    try:
        with allure.step("Check CPU, Memory and mpstat at the beginning"):
            validate_memory_and_cpu_utilization()
            mpstat_output = engines.dut.run_cmd('mpstat -P ALL')
            logger.info("At the beginning - Utilization: {}".format(parse_mpstat_output(regex, mpstat_output)))
            logger.info(mpstat_output)

        with allure.step(f'subscribe {MAX_GNMI_SUBSCRIBERS} clients'):
            for i in range(MAX_GNMI_SUBSCRIBERS):
                with allure.step(f'Subscribe client #{i}'):
                    client.gnmic_subscribe_system_events(mode=GnmiMode.STREAM, skip_cert_verify=True,
                                                         keep_session_alive=True)
                    _, _, client_proc = client.gnmic_subscribe_system_events(mode=GnmiMode.STREAM,
                                                                             skip_cert_verify=True,
                                                                             keep_session_alive=True)

                with allure.step("Monitor the events received by client no {}".format(i)):
                    subscriber_monitor_process = Process(target=check_subscriber_output_in_parallel,
                                                         args=(i, client_proc,))
                    subscriber_monitor_process.start()

        with allure.step('Set system events table-size to maximum ie {}'.format(SystemConsts.EVENTS_TABLE_SIZE_MAX)):
            system.events.set(op_param_name='table-size', op_param_value=SystemConsts.EVENTS_TABLE_SIZE_MAX,
                              apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Clear system events'):
            system.events.action(ActionConsts.CLEAR).verify_result()

        with allure.step("Create a separate process to monitor CPU & Memory utilization"):
            cpu_mem_monitor_process = Process(target=check_memory_and_cpu_in_parallel, args=(regex, engines.dut,))
            cpu_mem_monitor_process.start()

        with allure.step("Stream events update {} at a time till no of events reaches {}".
                         format(GnmiConsts.STREAM_PERFORMANCE_EVENTS_BATCH_SIZE,
                                GnmiConsts.STREAM_PERFORMANCE_EVENTS_MAX_SIZE)):
            no_of_events = 0
            # 100 iterations of 2 seconds each ie total of 200 seconds
            while no_of_events < GnmiConsts.STREAM_PERFORMANCE_EVENTS_MAX_SIZE:
                no_of_events += GnmiConsts.STREAM_PERFORMANCE_EVENTS_BATCH_SIZE
                cmd_to_simulate_events = 'docker exec eventd events_publish_test.py -c ' + \
                                         str(GnmiConsts.STREAM_PERFORMANCE_EVENTS_BATCH_SIZE)
                cmd_output = engines.dut.run_cmd(cmd_to_simulate_events)
                assert cmd_output == '', 'Error simulating events : {}\n{}'.\
                    format(cmd_output, cmd_to_simulate_events)
                logger.info("Simulated {} no of events".format(no_of_events))
                time.sleep(GnmiConsts.STREAM_EVENTS_INTERVAL)

        with allure.step("Wait for a minute for the events to be streamed over GNMI"):
            time.sleep(60)

    finally:
        with allure.step('Unset system events table-size to make it default'):
            system.events.unset(apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Clear system events'):
            system.events.action(ActionConsts.CLEAR)

        with allure.step("Check CPU, Memory and mpstat at the end"):
            validate_memory_and_cpu_utilization()
            mpstat_output = engines.dut.run_cmd('mpstat -P ALL')
            logger.info("At the End - Utilization: {}".format(parse_mpstat_output(regex, mpstat_output)))


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_gnmi_extend_telemetry(test_api, engines, devices):
    """
    Check gnmi extend telemetry flow:
        Test flow:
            1. Get system version from nvue
            2. Subscribe to the gnmi server and check system version
            3. Get all firmware components from nv fae show platform firmware command"
            4. Get all components with sonic-cli and check it have information, compare with fw output
            5. Subscribe to gnmi and compare all components with fw output
    """
    TestToolkit.tested_api = test_api
    system = System()
    fae = Fae()

    with allure.step("Get system version from nvue"):
        system_version = system.version.get_nvos_image_version()

    with allure.step("Subscribe to the gnmi server and check system version"):
        gnmi_stream_updates = run_gnmi_client_and_parse_output(engines, devices, devices.dut.version_xpath,
                                                               engines.dut.ip)
        gnmi_stream_updates_value = list(gnmi_stream_updates.values())[0]
        assert system_version == gnmi_stream_updates_value, f"'{system_version}' not exist in {gnmi_stream_updates_value}"

    with allure.step("Get all firmware components from nv fae show platform firmware command"):
        firmware_show = OutputParsingTool.parse_json_str_to_dictionary(
            fae.platform.firmware.show()).get_returned_value()

    with (allure.step("Get all components with sonic-cli and check it have information, compare with fw output")):
        component_keys = Tools.DatabaseTool.sonic_db_cli_get_keys(engine=engines.dut, asic="",
                                                                  db_name=DatabaseConst.STATE_DB_NAME,
                                                                  grep_str=GnmiConsts.SYSTEM_COMPONENTS).splitlines()
        for component in component_keys:
            component_output = Tools.DatabaseTool.sonic_db_cli_hgetall(engine=engines.dut, asic="",
                                                                       db_name=DatabaseConst.STATE_DB_NAME,
                                                                       table_name=f'\"{component}\"')
            output = ast.literal_eval(component_output)

            assert GnmiConsts.FW_VERSION in output and output[GnmiConsts.FW_VERSION], f"fw_version is missing or empty for {component}"
            assert GnmiConsts.PART_NUMBER in output and output[GnmiConsts.PART_NUMBER], f"part_number is missing or empty {component}"
            assert GnmiConsts.DESCRIPTION in output and output[GnmiConsts.DESCRIPTION], f"description is missing or empty {component}"

            if GnmiConsts.ONIE_COMPONENT in component:
                continue
            assert any(firmware_component.get('actual-firmware') == output['fw_version'] for firmware_component in
                       firmware_show.values()), f"Value '{output['fw_version']}' not found in {firmware_show}"

    with allure.step("Subscribe to gnmi and compare all components with fw output"):
        for path in devices.dut.components_gnmi_xpath:
            gnmi_stream_updates = run_gnmi_client_and_parse_output(engines, devices, path, engines.dut.ip)
            gnmi_stream_updates_value = list(gnmi_stream_updates.values())[0]
            assert any(component.get('actual-firmware') == gnmi_stream_updates_value for component in firmware_show.values()), f"Value '{gnmi_stream_updates_value}' not found in any 'actual-firmware' field"


def check_subscriber_output_in_parallel(client_no, client_proc):
    out, _ = client_proc.communicate()
    out = out.decode('utf-8')
    log_str = "Test event with index "
    no_of_logs = out.count(log_str)
    logger.info("No of test events streamed for Client #{}:{}".format(client_no, no_of_logs))
    assert no_of_logs >= GnmiConsts.STREAM_PERFORMANCE_EVENTS_MAX_SIZE, \
        "No of events streamed to client #{} is {} instead of {}".format(client_no, no_of_logs,
                                                                         GnmiConsts.STREAM_PERFORMANCE_EVENTS_MAX_SIZE)


def check_memory_and_cpu_in_parallel(regex, engine):
    try:
        no_of_iterations = 0
        # Monitor the usage till streaming is happening over GNMI ie 200 seconds
        total_iterations = GnmiConsts.STREAM_PERFORMANCE_TOTAL_DURATION / GnmiConsts.CPU_USAGE_MONITOR_INTERVAL

        while no_of_iterations < total_iterations:
            no_of_iterations += 1
            # validate_memory_and_cpu_utilization()
            mpstat_output = engine.run_cmd('mpstat -P ALL')
            logger.info("Iteration_{} Utilization: {}".format(no_of_iterations,
                                                              parse_mpstat_output(regex, mpstat_output)))
            # Monitor usage every 10 seconds
            random_interval = random.randint(3, 10)
            time.sleep(random_interval)

    except AssertionError:
        assert False, "CPU utilization exceeds max limit allowed"

    finally:
        with allure.step("CPU utilization monitoring completed"):
            logger.info("CPU utilization monitoring completed")


def parse_mpstat_output(regex, mpstat_output):
    matches = regex.findall(mpstat_output)
    cpu_utilization_dict = {}

    try:
        for match in matches:
            assert len(match) == 4, "mpstat parsing issue, we expect to match 4 groups"
            data = match[1].strip()
            busy_cpu_percent = round(100 - (float(match[3])), 2)
            cpu_name = 'CPU_all' if data.startswith('a') else "CPU" + data
            cpu_utilization_dict[cpu_name] = busy_cpu_percent

    finally:
        return cpu_utilization_dict
