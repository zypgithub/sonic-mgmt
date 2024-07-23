import logging
import os
import signal
import time

import pytest

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import NvosConst, DatabaseConst
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.conftest import local_adminuser
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
            validate_show_gnmi(gnmi_server_obj, engines, gnmi_state=GnmiConsts.GNMI_STATE_ENABLED,
                               gnmi_is_running=GnmiConsts.GNMI_IS_NOT_RUNNING)
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

        if not is_redmine_issue_active([3727441]):
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
def test_gnmi_bad_flow(test_api, engines, devices):
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
    validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, engines.dut.ip)

    with allure.step("invalid command"):
        gnmi_server_obj.set(GnmiConsts.GNMI_STATE_FIELD, Tools.RandomizationTool.get_random_string(7), "Error")

    with allure.step("Subscribe to the gnmi server for data that is not supported"):
        if devices.dut.asic_type == NvosConst.QTM3:
            xpath = 'interfaces/interface[name=swA1p1]/state/counters/in-broadcast-pkts'
        else:
            xpath = 'interfaces/interface[name=sw1p1]/state/counters/in-broadcast-pkts'
        gnmi_stream_updates = run_gnmi_client_and_parse_output(engines, devices, xpath, engines.dut.ip)
        gnmi_stream_updates_value = list(gnmi_stream_updates.values())[0]
        assert gnmi_stream_updates_value == '0', f'{xpath} is unsupported field,' \
            f' so we expect to have 0, but got {gnmi_stream_updates_value}'

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
