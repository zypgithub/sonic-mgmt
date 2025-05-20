import logging
import pytest
import random

from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tools.test_utils import allure_utils as allure
import string
import time
import re
import socket
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_constants.constants_nvos import SyslogConsts, SyslogSeverityLevels, NvosConst
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SonicMgmtContainer import SonicMgmtContainer
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import SystemConsts

logger = logging.getLogger()
INCOMPLETE_COMMAND = "Incomplete Command"
ERROR = "Error"
INVALID_COMMAND = "Invalid Command"
IS_NOT_ONE_OF = "is not one of"
IS_NOT_AN_INTEGER = "is not an integer"
IS_NOT_OF_TYPE_INTEGER = "is not of type 'integer'"
IS_TOO_SHORT = "'' is too short"
INVALID_CONFIG = "Config invalid"


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_positive_minimal_flow_by_hostname(engines, test_api):
    """
    Will validate the minimal positive flow:
        set server and send UDP msg , verify the server get the msg and show commands

    Test flow:
    1. Configure remote syslog server by hostname
    2. Validate show commands
    3. Print msg that the server should catch, validate it gets the msg
    4. Print msg that the server should not catch, validate it does not get the msg
    5. Cleanup
    """
    TestToolkit.tested_api = test_api
    remote_server_engine = engines[NvosConst.SONIC_MGMT]
    remote_server_hostname = get_hostname_from_ip(remote_server_engine.ip)
    positive_minimal_flow(remote_server_engine, remote_server_hostname)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_positive_minimal_flow_by_ipv4(engines, test_api):
    """
    Will validate the minimal positive flow:
        set server and send UDP msg , verify the server get the msg and show commands

    Test flow:
    1. Configure remote syslog server by ipv4
    2. Validate show commands
    3. Print msg that the server should catch, validate it gets the msg
    4. Print msg that the server should not catch, validate it does not get the msg
    5. Cleanup
    """
    TestToolkit.tested_api = test_api
    remote_server_engine = engines[NvosConst.SONIC_MGMT]
    positive_minimal_flow(remote_server_engine, remote_server_engine.ip)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_positive_minimal_flow_by_ipv6(engines, test_api, sonic_mgmt_ipv6_addr):
    """
    Will validate the minimal positive flow:
        set server and send UDP msg , verify the server get the msg and show commands

    Test flow:
    1. Configure remote syslog server by ipv6
    2. Validate show commands
    3. Print msg that the server should catch, validate it gets the msg
    4. Print msg that the server should not catch, validate it does not get the msg
    5. Cleanup
    """
    if not IpTool.is_dhcp_client6_has_lease(engines.dut):
        pytest.skip("DUT DHCP client6 has no lease; cannot run this IPv6 test.")

    TestToolkit.tested_api = test_api
    positive_minimal_flow(engines[NvosConst.SONIC_MGMT], sonic_mgmt_ipv6_addr)


@pytest.mark.system
@pytest.mark.syslog
def test_rsyslog_multiple_servers_configuration(engines):
    """
    Validates the following:
    - Time to configure 1 and 10 servers should be similar (<< 1sec of difference)
    - No degradation in time to "nv show system syslog" when a lot servers are configured (10 for example)
    - Normal system resources utilization when a lot servers configured (10 for example)

    Test flow:
    1. configuring 1 single server and measuring its time.
    2. Measure "nv show system syslog" command time with 1 server configured.
    3. configuring 11 servers and measuring its time.
    4. Measure "nv show system syslog" command time with 11 servers configured.
    5. Verify all configured servers displayed in show command
    6. Validate system resources CPU utilization with 11 servers configured.
    7. Compare between server configuration times.
    8. Compare between "nv show system syslog" command times.
    9. Cleanup
    """
    system = System()
    server_name = 'server-0'

    try:
        with allure.step("Configure 1 remote syslog server {}".format(server_name)):
            logging.info("Configure 1 remote syslog server {}".format(server_name))
            start_time = time.time()
            system.syslog.servers.set_server(server_name, apply=True)
            end_time = time.time()
            config_single_duration = end_time - start_time

        with allure.step("Calculate a single server show time"):
            logging.info("Calculate a single server show time")
            start_time = time.time()
            system.syslog.servers.show()
            end_time = time.time()
            show_single_duration = end_time - start_time

        with allure.step("Configure 10 remote syslog servers"):
            logging.info("Configure 10 remote syslog servers")
            for x in range(1, SyslogConsts.MULTIPLE_SERVERS_NUMBER):
                server_name = 'server' + str(x)
                system.syslog.servers.set_server(server_name, apply=False)
            server_name = 'server-10'
            start_time = time.time()
            system.syslog.servers.set_server(server_name, apply=True)
            end_time = time.time()
            config_multiple_duration = end_time - start_time

        with allure.step("Calculate 10 server configuration time"):
            logging.info("Calculate 10 server configuration time")
            start_time = time.time()
            system.syslog.servers.show()
            end_time = time.time()
            show_multiple_duration = end_time - start_time

        with allure.step("Verify all configured servers displayed in show command"):
            logging.info("Verify all configured servers displayed in show command")
            server_list = OutputParsingTool.parse_json_str_to_dictionary(
                system.syslog.servers.show()).get_returned_value()
            server_len = len(server_list)
            assert server_len == (SyslogConsts.MULTIPLE_SERVERS_NUMBER + 1), \
                "Number of servers configured is different than expected"

        with allure.step("Validate system resources CPU utilization with 11 servers configured"):
            logging.info("Validate system resources CPU utilization with 11 servers configured")
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.show("cpu")).get_returned_value()
            cpu_utilization = output_dictionary[SystemConsts.CPU_TOTAL_UTILIZATION_KEY]
            assert cpu_utilization < SystemConsts.CPU_PERCENT_THRESH_MAX, \
                "CPU utilization: {actual}% is higher than the maximum limit of: {expected}%" \
                "".format(actual=cpu_utilization, expected=SystemConsts.CPU_PERCENT_THRESH_MAX)

        with allure.step("Verify configuration diff time"):
            logging.info("Verify configuration diff time")
            config_duration_diff = config_multiple_duration - config_single_duration
            assert config_duration_diff < SyslogConsts.CONFIG_TIME_DIFF_THRESHOLD, \
                "Configuration diff time: {actual} is higher than expected time: {expected}" \
                "".format(actual=config_duration_diff, expected=SyslogConsts.CONFIG_TIME_DIFF_THRESHOLD)

        with allure.step("Verify show diff time"):
            logging.info("Verify show diff time")
            show_duration_diff = show_multiple_duration - show_single_duration
            assert show_duration_diff < SyslogConsts.SHOW_TIME_DIFF_THRESHOLD, \
                "Show diff time: {actual} is higher than expected time: {expected}" \
                "".format(actual=show_duration_diff, expected=SyslogConsts.SHOW_TIME_DIFF_THRESHOLD)

    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.unset(apply=True)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_configurations(test_api):
    """
    will check rsyslog configurations

    Test flow:
    1. configure remote syslog servers : server_a, server_b
    2. validate show commands
    3. change global severity
    4. unset server_a
    5. validate show commands
    6. unset server
    7. validate show commands
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_a = 'server-a'
    server_b = 'server-b'

    with allure.step("Configure remote syslog servers"):
        logging.info("Configure remote syslog servers")
        system.syslog.servers.set_server(server_a, apply=True)
        system.syslog.servers.set_server(server_b, apply=True)

        system.syslog.selectors.set_selector(SyslogConsts.DEFAULT_SELECTOR_NAME, apply=True)
        system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_severity(
            SyslogSeverityLevels.ERROR, apply=True)
        system.syslog.servers.servers_dict[server_a].set_selector_priority(1, SyslogConsts.DEFAULT_SELECTOR_NAME,
                                                                           apply=True)
        system.syslog.servers.servers_dict[server_b].set_selector_priority(1, SyslogConsts.DEFAULT_SELECTOR_NAME,
                                                                           apply=True)

    try:
        with allure.step("Validate show commands"):
            logging.info("Validate show commands")
            expected_server_dictionary_a = create_remote_server_dictionary_with_selector(server_a, 1,
                                                                                         selector_id=SyslogConsts.DEFAULT_SELECTOR_NAME)
            expected_server_dictionary_b = create_remote_server_dictionary_with_selector(server_b, 1,
                                                                                         selector_id=SyslogConsts.DEFAULT_SELECTOR_NAME)
            expected_server_dictionary = {**expected_server_dictionary_a, **expected_server_dictionary_b}
            expected_syslog_dictionary = create_syslog_output_dictionary(
                server_dict={SyslogConsts.SERVER: expected_server_dictionary})
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            system.syslog.servers.verify_show_servers_list([server_a, server_b])
            system.syslog.servers.servers_dict[server_a].verify_show_server_output(expected_server_dictionary[server_a])

        with allure.step("unset server vrf and Validate"):
            logging.info("unset server vrf and Validate")
            system.syslog.servers.servers_dict[server_a].unset_vrf(apply=True)
            expected_syslog_dictionary[SyslogConsts.SERVER][server_a].update({SyslogConsts.VRF: SyslogConsts.DEFAULT_VRF})
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            system.syslog.servers.servers_dict[server_a].verify_show_server_output(expected_server_dictionary[server_a])

        severity_level = SyslogSeverityLevels.ERROR
        with allure.step("Unset {} and Validate".format(server_a)):
            logging.info("Unset {} and Validate".format(server_a))
            # system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].unset_severity(apply=True)
            system.syslog.servers.unset_server(server_a, apply=True)
            expected_syslog_dictionary[SyslogConsts.SERVER].pop(server_a)
            system.syslog.servers.verify_show_servers_list([server_b])
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            server_list = OutputParsingTool.parse_json_str_to_dictionary(
                system.syslog.servers.show()).get_returned_value()
            assert server_a not in server_list, "Did not expect to see {} in the list of servers".format(server_a)

        with allure.step("Unset server and Validate"):
            logging.info("Unset server and Validate")
            system.syslog.servers.unset_server(server_b, apply=True)
            expected_syslog_dictionary[SyslogConsts.SERVER].pop(server_b)
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            server_list = OutputParsingTool.parse_json_str_to_dictionary(
                system.syslog.servers.show()).get_returned_value()
            assert server_b not in server_list, "Did not expect to see {} in the list of servers".format(server_b)

        with allure.step("Configure remote syslog server and validate unset syslog"):
            logging.info("Configure remote syslog server and validate unset syslog")
            system.syslog.servers.set_server(server_a, apply=True)
            system.syslog.servers.servers_dict[server_a].set_selector_priority(1, SyslogConsts.DEFAULT_SELECTOR_NAME,
                                                                               apply=True)
            expected_server_dictionary = create_remote_server_dictionary_with_selector(server_a, 1,
                                                                                       selector_id=SyslogConsts.DEFAULT_SELECTOR_NAME)
            expected_syslog_dictionary.update({SyslogConsts.SERVER: expected_server_dictionary})
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            system.syslog.servers.verify_show_servers_list([server_a])
            system.syslog.unset(apply=True)
            expected_syslog_dictionary[SyslogConsts.SERVER].pop(server_a)
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            server_list = OutputParsingTool.parse_json_str_to_dictionary(
                system.syslog.servers.show()).get_returned_value()
            assert server_a not in server_list, "Did not expect to see {} in the list of servers".format(server_a)

    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.unset(apply=True)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_server_severity_levels(engines, loganalyzer, test_api):
    """
    Will validate all the severity options:  debug, info, notice, warning, error, critical, alert, emerg, none.
    Will configure the severity level, validate it in the show command and validate that the server catch the relevant
    messages only.

    Test flow:
    * Configure remote syslog server
    To each severity level:
         * Set severity level
         * Validate with show command
         * Print msg that the server should catch, validate
         * Print msg that the server should not catch, validate
    * Unset server severity
    * Cleanup
    """
    TestToolkit.tested_api = test_api
    remote_server_engine = engines[NvosConst.SONIC_MGMT]
    remote_server_ip = remote_server_engine.ip
    system = System()

    with allure.step("Configure remote syslog server {}".format(remote_server_ip)):
        logging.info("Configure remote syslog server {}".format(remote_server_ip))
        server = system.syslog.servers.set_server(remote_server_ip, apply=True)

    try:
        with allure.step("Configure selectors"):
            logging.info("Configure selectors")
            system.syslog.selectors.set_selector(SyslogConsts.DEFAULT_SELECTOR_NAME, apply=True)
            system.syslog.servers.servers_dict[remote_server_ip].set_selector_priority(1, SyslogConsts.DEFAULT_SELECTOR_NAME,
                                                                                       apply=True)
        with allure.step("Validate show commands"):
            logging.info("Validate show commands")
            expected_server_dictionary = create_remote_server_dictionary_with_selector(remote_server_ip, 1,
                                                                                       selector_id=SyslogConsts.DEFAULT_SELECTOR_NAME)
            expected_syslog_dictionary = create_syslog_output_dictionary(
                server_dict={SyslogConsts.SERVER: expected_server_dictionary})
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)

        with allure.step("Validate all severity levels"):
            logging.info("Validate all severity levels")
            for severity_level in SyslogSeverityLevels.SEVERITY_LEVEL_LIST:
                config_and_verify_severity(loganalyzer, system.syslog, server, remote_server_ip, remote_server_engine,
                                           severity_level,
                                           selector_id=SyslogConsts.DEFAULT_SELECTOR_NAME,
                                           global_severity_level=SyslogSeverityLevels.NOTICE)

            with allure.step("Validate none as severity level"):
                logging.info("Validate none as severity level")
                system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_severity(
                    SyslogSeverityLevels.NONE, apply=True)
                system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].verify_trap_severity_level(
                    SyslogConsts.DEFAULT_SELECTOR_NAME, SyslogSeverityLevels.NONE)
                random_msg = RandomizationTool.get_random_string(40, ascii_letters=string.ascii_letters + string.digits)
                send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_didnt_received=True)

    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.unset(apply=True)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_server_and_global_severity_levels(test_api):
    """
    Will validate all the severity options:  debug, info, notice, warning, error, critical, alert, emerg, none.
    Will configure the severity level, validate it in the show command and validate that the server catch the relevant
    messages only.

    Test flow:
    * Configure remote syslog server
    To each severity level:
         * Set severity level
         * Validate with show command
         * Print msg that the server should catch, validate
         * Print msg that the server should not catch, validate
    * Unset server trap
    * Cleanup
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_a_name = 'server_a'

    try:
        with allure.step("Configure remote syslog server and Validate"):
            logging.info("Configure remote syslog server and Validate")
            server_a = system.syslog.servers.set_server(server_a_name, apply=True)
            server_a.verify_trap_severity_level(None)

        with allure.step("Set global severity and Validate"):
            logging.info("Set global severity and Validate")
            system.syslog.set_trap(SyslogSeverityLevels.ERROR, apply=True)
            server_a.verify_trap_severity_level(None)

        with allure.step("Unset server severity and Validate nothing change"):
            logging.info("Unset server severity and Validate nothing change")
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].unset_severity(apply=True)
            server_a.verify_trap_severity_level(None, SyslogConsts.DEFAULT_SELECTOR_NAME)

        with allure.step("set server trap and Validate"):
            logging.info("set server trap and Validate")
            server_a.set_trap(SyslogSeverityLevels.DEBUG, apply=True)
            server_a.verify_trap_severity_level(SyslogSeverityLevels.SEVERITY_LEVEL_DICT[SyslogSeverityLevels.DEBUG])

        with allure.step("Unset server trap and Validate"):
            logging.info("Unset server trap and Validate")
            server_a.unset_trap(apply=True)
            server_a.verify_trap_severity_level(None)

        with allure.step("Unset global trap and Validate"):
            logging.info("Unset global trap and Validate")
            system.syslog.unset_trap(apply=True)
            server_a.verify_trap_severity_level(None)

        with allure.step("Validate unset global trap override server trap"):
            logging.info("Validate unset global trap override server trap")

            with allure.step("set global and server trap and Validate"):
                logging.info("set global and server trap and Validate")
                system.syslog.set_trap(SyslogSeverityLevels.ERROR, apply=True)
                server_a.set_trap(SyslogSeverityLevels.DEBUG, apply=True)
                server_a.verify_trap_severity_level(
                    SyslogSeverityLevels.SEVERITY_LEVEL_DICT[SyslogSeverityLevels.DEBUG])

            with allure.step("Unset global trap and Validate"):
                logging.info("Unset global trap and Validate")
                system.syslog.unset_trap(apply=True)
                server_a.verify_trap_severity_level(None)

        with allure.step("Validate set global trap override server trap"):
            logging.info("Validate global trap override server trap")

            with allure.step("set server trap and Validate"):
                logging.info("set server trap and Validate")
                server_a.set_trap(SyslogSeverityLevels.DEBUG, apply=True)
                system.syslog.verify_global_severity_level(
                    SyslogSeverityLevels.SEVERITY_LEVEL_DICT[SyslogSeverityLevels.NOTICE])
                server_a.verify_trap_severity_level(
                    SyslogSeverityLevels.SEVERITY_LEVEL_DICT[SyslogSeverityLevels.DEBUG])

            with allure.step("Set global trap and Validate"):
                logging.info("Set global trap and Validate")
                system.syslog.set_trap(SyslogSeverityLevels.ERROR, apply=True)
                system.syslog.verify_global_severity_level(
                    SyslogSeverityLevels.SEVERITY_LEVEL_DICT[SyslogSeverityLevels.ERROR])
                server_a.verify_trap_severity_level(None)

    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.unset(apply=True)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_port(engines, test_api):
    """
    Will check the syslog with non default port
    we will check it with 2 ports number, one in the system ports range (0-1023) and the other out of this range.
    steps:
    1. configure remote server syslog
    2. change rsyslog port on switch and remote server
    3. validate with show command
    4. send msg , validate remote server get the msg
    5. Change back rsyslog port to default port, just on switch
    6. send msg , validate remote server did not get the msg!
    7. Change back rsyslog port to default port on remote server
    8. send msg , validate remote server get the msg
    """
    TestToolkit.tested_api = test_api
    remote_server_engine = engines[NvosConst.SONIC_MGMT]
    remote_server_ip = remote_server_engine.ip
    system = System()
    tmp_port = 500  # in the system ports range

    with allure.step("Configure remote syslog server {}".format(remote_server_ip)):
        logging.info("Configure remote syslog server {}".format(remote_server_ip))
        system.syslog.servers.set_server(remote_server_ip, apply=True)

    try:
        with allure.step("Validate show commands and send msg"):
            logging.info("Validate show commands and send msg")
            expected_server_dictionary = create_remote_server_dictionary(remote_server_ip)
            system.syslog.servers.servers_dict[remote_server_ip].verify_show_server_output(
                expected_server_dictionary[remote_server_ip])
            random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
            send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_received=True)

        with allure.step("Change rsyslog port to non default port"):
            logging.info("Change rsyslog port to non default port")
            config_and_verify_rsyslog_port(system.syslog.servers.servers_dict[remote_server_ip], remote_server_engine,
                                           remote_server_ip, SyslogConsts.DEFAULT_PORT, tmp_port)
            config_and_verify_rsyslog_port(system.syslog.servers.servers_dict[remote_server_ip], remote_server_engine,
                                           remote_server_ip, tmp_port, 1500)
            tmp_port = 1500  # out of system port range

        with allure.step("Change back rsyslog port to default port, just on switch"):
            logging.info("Change back rsyslog port to default port, just on switch")
            system.syslog.servers.servers_dict[remote_server_ip].unset_port(apply=True)
            system.syslog.servers.servers_dict[remote_server_ip].verify_show_server_output(
                {SyslogConsts.PORT: str(SyslogConsts.DEFAULT_PORT)})
            random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
            send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_didnt_received=True)

        with allure.step("Change back rsyslog port to default port on remote server"):
            logging.info("Change back rsyslog port to default port on remote server")
            SonicMgmtContainer.change_rsyslog_port(remote_server_engine, tmp_port, SyslogConsts.DEFAULT_PORT, SyslogConsts.UDP,
                                                   restart_rsyslog=True)
            random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
            send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_received=True)

    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.unset(apply=True)
            SonicMgmtContainer.change_rsyslog_port(remote_server_engine, tmp_port, SyslogConsts.DEFAULT_PORT, SyslogConsts.UDP,
                                                   restart_rsyslog=True)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_protocol(engines, test_api):
    """
    Will check the syslog protocol options: TCP and UDP
    Steps:
        1. configure a remote syslog server
        2. config syslog protocol to udp
        3. validate with show commands
        4. send a msg and validate server received it
        5. config syslog protocol to tcp
        6. validate with show commands
        7. send a msg and validate server received it
        8. simulate a disconnection, by stop the rsyslog process
        9. send a msg and validate server did not receive it
        10. reconnect , restart the rsyslog process
        11. send a msg and validate server received it
    """
    TestToolkit.tested_api = test_api
    remote_server_engine = engines[NvosConst.SONIC_MGMT]
    remote_server_ip = remote_server_engine.ip
    system = System()

    with allure.step("Configure remote syslog server {}".format(remote_server_ip)):
        logging.info("Configure remote syslog server {}".format(remote_server_ip))
        system.syslog.servers.set_server(remote_server_ip, apply=True)

    try:
        with allure.step("Validate show commands"):
            expected_server_dictionary = create_remote_server_dictionary(remote_server_ip)
            system.syslog.servers.servers_dict[remote_server_ip].verify_show_server_output(
                expected_server_dictionary[remote_server_ip])

        config_and_verify_rsyslog_protocol(system.syslog.servers.servers_dict[remote_server_ip], remote_server_engine,
                                           remote_server_ip, SyslogConsts.UDP)
        config_and_verify_rsyslog_protocol(system.syslog.servers.servers_dict[remote_server_ip], remote_server_engine,
                                           remote_server_ip, SyslogConsts.TCP)

        with allure.step("Disconnect and Reconnect to server"):

            with allure.step("Simulate disconnection to the server"):
                remote_server_engine.run_cmd('sudo pkill rsyslogd')
                time.sleep(30)
                random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
                send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_didnt_received=True)

            with allure.step("Reconnect to the server"):
                SonicMgmtContainer.restart_rsyslog(remote_server_engine)
                time.sleep(30)
                random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
                send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_received=True)

            with allure.step("Unset syslog server protocol"):
                system.syslog.servers.servers_dict[remote_server_ip].unset_protocol(apply=True)
                system.syslog.servers.servers_dict[remote_server_ip].verify_show_server_output(
                    {SyslogConsts.PROTOCOL: SyslogConsts.UDP})

    finally:
        with allure.step("Cleanup syslog configurations"):
            system.syslog.unset(apply=True)
        SonicMgmtContainer.restart_rsyslog(remote_server_engine)
        time.sleep(10)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_filter(engines, test_api):
    """
    Will check the rsyslog filter options: exclude and include.
    Validate that the server will get only the relevant messages.
    Test flow:
    1. configure remote syslog server with exclude filter
    2. validate with show commands and send messages
    3. configure remote syslog server with include filter
    4. validate with show commands and send messages
    5. unset filter
    6. validate with show commands and send messages
    """
    TestToolkit.tested_api = test_api
    remote_server_engine = engines[NvosConst.SONIC_MGMT]
    remote_server_ip = remote_server_engine.ip
    system = System()

    try:
        with allure.step("Configure selector"):
            logging.info("Configure selector")
            system.syslog.selectors.set_selector(SyslogConsts.DEFAULT_SELECTOR_NAME, apply=True)

        with allure.step("Configure remote syslog server {} with exclude filter and validate".format(remote_server_ip)):
            logging.info("Configure remote syslog server {} with exclude filter and validate".format(remote_server_ip))
            system.syslog.servers.set_server(remote_server_ip, apply=True)
            system.syslog.servers.servers_dict[remote_server_ip].set_selector_priority(1, SyslogConsts.DEFAULT_SELECTOR_NAME,
                                                                                       apply=True)

            exclude_regex = "a+"
            include_regex = "b+"

            # First create and configure the filter with all settings
            selector = system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME]
            selector.set_filter("1", apply=False)
            selector.filter_dict["1"].set_action_filter(SyslogConsts.EXCLUDE, apply=False)
            selector.filter_dict["1"].set_match_filter(exclude_regex, apply=True)

            expected_server_dictionary = create_remote_server_dictionary_with_selector(remote_server_ip, 1,
                                                                                       selector_id=SyslogConsts.DEFAULT_SELECTOR_NAME)

            system.syslog.servers.servers_dict[remote_server_ip].verify_show_server_output(
                expected_server_dictionary[remote_server_ip])
        with allure.step("Validate show commands"):
            expected_selector_dictionary = {
                'facility': 'daemon',
                'filter': {
                    '1': {
                        'action': 'exclude',
                        'match': 'a+'
                    }
                },
                'rate-limit': None,
                'severity': 'notice'
            }
            logger.info("expected_selector_dictionary: {}".format(expected_selector_dictionary))
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].verify_filter_options(
                expected_selector_dictionary)
            with allure.step("Send message with the exclude filter regex,\n"
                             "expect message not to be received over the remote server"):
                logging.info("Send message with the exclude filter regex,\n"
                             "expect message not to be received over the remote server")
                random_msg = RandomizationTool.get_random_string(20, ascii_letters=string.digits)
                send_msg_to_server(exclude_regex + random_msg, remote_server_ip, remote_server_engine,
                                   verify_msg_didnt_received=True)

            with allure.step("Send message without the exclude filter regex but with lower severity level,\n"
                             "expect message not to be received over the remote server"):
                logging.info("Send message without the exclude filter regex but with lower severity level,\n"
                             "expect message not to be received over the remote server")
                random_msg = RandomizationTool.get_random_string(20, ascii_letters=string.digits)
                send_msg_to_server(random_msg, remote_server_ip, remote_server_engine,
                                   priority=SyslogSeverityLevels.DEBUG,
                                   verify_msg_didnt_received=True)

            with allure.step("Send message without the exclude filter regex,\n"
                             "expect message to be received over the remote server"):
                logging.info("Send message without the exclude filter regex,\n"
                             "expect message to be received over the remote server")
                random_msg = RandomizationTool.get_random_string(20, ascii_letters=string.digits)
                send_msg_to_server(include_regex + random_msg, remote_server_ip, remote_server_engine,
                                   verify_msg_received=True)

            with allure.step("Configure long regex for the exclude filter and validate"):
                logging.info("Configure long regex for the exclude filter and validate")
                long_exclude_regex = RandomizationTool.get_random_string(200,
                                                                         ascii_letters=string.digits + string.ascii_letters)
                selector = system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME]
                selector.filter_dict["1"].set_match_filter(long_exclude_regex, apply=True)
                expected_server_dictionary = create_remote_server_dictionary_with_selector(remote_server_ip, 1,
                                                                                           selector_id=SyslogConsts.DEFAULT_SELECTOR_NAME)
                system.syslog.servers.servers_dict[remote_server_ip].verify_show_server_output(
                    expected_server_dictionary[remote_server_ip])
                with allure.step("Validate show commands"):
                    expected_selector_dictionary.update(
                        {
                            SyslogConsts.FILTER: {
                                "1": {
                                    SyslogConsts.ACTION: SyslogConsts.EXCLUDE,
                                    SyslogConsts.MATCH: long_exclude_regex
                                }
                            }
                        }
                    )
                    logger.info("expected_selector_dictionary: {}".format(expected_selector_dictionary))
                    system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].verify_filter_options(
                        expected_selector_dictionary)
                # Ensure filter exists before unsetting
                # system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_filter("1", apply=True)
                # system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].unset_filter("1", apply=True)

        with allure.step("Configure remote syslog server {} with include filter and validate".format(remote_server_ip)):
            logging.info("Configure remote syslog server {} with include filter and validate".format(remote_server_ip))
            # system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_filter("1", apply=True)
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["1"].set_action_filter(
                SyslogConsts.INCLUDE, apply=False)
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["1"].set_match_filter(
                include_regex, apply=True)
            with allure.step("Validate show commands"):
                long_include_regex = RandomizationTool.get_random_string(200, ascii_letters=string.digits + string.ascii_letters)
                expected_selector_dictionary.update({SyslogConsts.FILTER: {"1": {SyslogConsts.ACTION: SyslogConsts.INCLUDE, SyslogConsts.MATCH: include_regex}}})
                logger.info("expected_selector_dictionary: {}".format(expected_selector_dictionary))
                system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].verify_filter_options(
                    expected_selector_dictionary)
            with allure.step("Send message without the include filter regex,\n"
                             "expect message not to be received over the remote server"):
                logging.info("Send message without the include filter regex,\n"
                             "expect message not to be received over the remote server")
                random_msg = RandomizationTool.get_random_string(20, ascii_letters=string.digits)
                send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_didnt_received=True)

            with allure.step("Send message with the include filter regex but with lower severity level,\n"
                             "expect message not to be received over the remote server"):
                logging.info("Send message with the include filter regex but with lower severity level,\n"
                             "expect message not to be received over the remote server")
                random_msg = RandomizationTool.get_random_string(20, ascii_letters=string.digits)
                send_msg_to_server(include_regex + random_msg, remote_server_ip, remote_server_engine,
                                   priority=SyslogSeverityLevels.DEBUG, verify_msg_didnt_received=True)

            with allure.step("Send message with the include filter regex,\n"
                             "expect message to be received over the remote server"):
                logging.info("Send message with the include filter regex,\n"
                             "expect message to be received over the remote server")
                random_msg = RandomizationTool.get_random_string(20, ascii_letters=string.digits)
                send_msg_to_server(long_exclude_regex + random_msg, remote_server_ip, remote_server_engine, priority=SyslogSeverityLevels.NOTICE,
                                   verify_msg_received=True)

            with allure.step("Configure long regex for the include filter and validate"):
                logging.info("Configure long regex for the include filter and validate")
                long_include_regex = RandomizationTool.get_random_string(200,
                                                                         ascii_letters=string.digits + string.ascii_letters)
                system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["1"].set_match_filter(
                    long_include_regex, apply=True)
                with allure.step("Validate show commands"):
                    expected_selector_dictionary.update({SyslogConsts.FILTER: {
                        "1": {SyslogConsts.ACTION: SyslogConsts.INCLUDE, SyslogConsts.MATCH: long_include_regex}
                    }})
                    logger.info("expected_selector_dictionary: {}".format(expected_selector_dictionary))
                    system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].verify_filter_options(
                        expected_selector_dictionary)
                with allure.step("Send message with the include filter regex,\n"
                                 "expect message to be received over the remote server"):
                    logging.info("Send message with the include filter regex,\n"
                                 "expect message to be received over the remote server")
                    send_msg_to_server(long_exclude_regex, remote_server_ip, remote_server_engine,
                                       verify_msg_received=True)

        with allure.step("Unset filter and validate"):
            logging.info("Unset filter and validate")
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].unset_filter("1", apply=True).verify_result()
            with allure.step("Validate show commands"):
                expected_selector_dictionary.update({SyslogConsts.FILTER: {}})
                logger.info("expected_selector_dictionary: {}".format(expected_selector_dictionary))
                system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].verify_filter_options(
                    expected_selector_dictionary)
            random_msg = RandomizationTool.get_random_string(20, ascii_letters=string.digits)
            send_msg_to_server(exclude_regex + random_msg, remote_server_ip, remote_server_engine,
                               verify_msg_received=True)

    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.unset(apply=True)


@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_format(engines, test_api):
    """
    Will validate all the format options:  standard, welf.
    Will configure the syslog format, validate it in the show command and in the syslog file.
    Test flow:
    1. configure remote syslog server
    2. validate with show commands
    3. send a msg and validate server received it and its not in welf format
    4. configure welf format
    5. validate with show command and on the remote syslog server
    6. configure welf firewall-nme
    7. validate with show command and on the remote syslog server
    8. unset welf firewall-nme
    9.  validate with show command and on the remote syslog server
    """
    TestToolkit.tested_api = test_api
    remote_server_engine = engines[NvosConst.SONIC_MGMT]
    remote_server_ip = remote_server_engine.ip
    system = System()

    try:
        with allure.step("Configure remote syslog server {} and validate".format(remote_server_ip)):
            logging.info("Configure remote syslog server {} and validate".format(remote_server_ip))
            system.syslog.servers.set_server(remote_server_ip, apply=True)
            expected_server_dictionary = create_remote_server_dictionary(remote_server_ip)
            expected_syslog_dictionary = create_syslog_output_dictionary(
                server_dict={SyslogConsts.SERVER: expected_server_dictionary})
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            system.syslog.verify_show_syslog_format_output({SyslogConsts.FORMAT: {SyslogConsts.STANDARD: {}}})
            send_random_msg_and_validate_format(remote_server_ip, remote_server_engine, expect_welf_format=False)

        with allure.step("Set welf format and validate"):
            logging.info("Set welf format and validate")
            system.syslog.format.set(SyslogConsts.WELF, apply=True).verify_result(False, expected_value=[f"firewall-name must be configured",
                                                                                                         f"firewall name must be configured"])

        with allure.step("Set firewall name and validate"):
            logging.info("Set firewall name and validate")
            firewall_name = RandomizationTool.get_random_string(6, ascii_letters=string.ascii_letters)
            system.syslog.format.welf.set_firewall_name(firewall_name, apply=True)
            system.syslog.verify_show_syslog_format_output({SyslogConsts.FORMAT: {SyslogConsts.WELF:
                                                                                  {SyslogConsts.FIREWAL_NAME:
                                                                                   firewall_name}}})
            send_random_msg_and_validate_format(remote_server_ip, remote_server_engine, expect_welf_format=True,
                                                firewall_name=firewall_name)

        with allure.step("Unset firewall name and validate"):
            logging.info("Unset firewall name and validate")
            system.syslog.format.welf.unset(apply=True)
            expected_syslog_dictionary[SyslogConsts.FORMAT] = {SyslogConsts.STANDARD: {}}
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            system.syslog.verify_show_syslog_format_output({SyslogConsts.FORMAT: {SyslogConsts.STANDARD: {}}})
            send_random_msg_and_validate_format(remote_server_ip, remote_server_engine, expect_welf_format=False)

    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.unset(apply=True)


@pytest.mark.disable_loganalyzer
@pytest.mark.system
@pytest.mark.syslog
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rsyslog_bad_params(test_api):
    """
    Will check all the commands that get params, with bad params- empty or random
    """
    TestToolkit.tested_api = test_api
    system = System()
    rand_str = RandomizationTool.get_random_string(10)
    server_name = RandomizationTool.get_random_string(5)

    with allure.step("Global syslog commands"):
        logging.info("Global syslog commands")

        with allure.step("set selector"):
            system.syslog.selectors.set_selector(SyslogConsts.DEFAULT_SELECTOR_NAME, apply=True)

        with allure.independent_step("Configure and validate severity, should fail"):
            logging.info("Configure and validate severity, should fail")
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_severity(rand_str, expected_str=["Error", INCOMPLETE_COMMAND,
                                                                                                                            f"{IS_NOT_ONE_OF} ['debug', 'info', 'notice', 'warn', 'error', 'critical', 'alert', 'emergency']"], apply=True)
        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        # TODO change when bug 3390504 will be fixed
        with allure.independent_step("Configure and validate format, should fail"):
            logging.info("Configure and validate format, should fail")
            system.syslog.format.set(rand_str).verify_result(False,
                                                             expected_str=["Error", f"{IS_NOT_ONE_OF} ['welf', 'standard']",
                                                                           f"'{rand_str}' was unexpected: expected ['standard', 'welf']"], apply=True)
        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
    with allure.step("Specific syslog server commands"):
        logging.info("Specific syslog server commands")
        system.syslog.servers.set_server(server_name, apply=False)

        with allure.independent_step("Configure and validate port, should fail"):
            logging.info("Configure and validate port, should fail")
            system.syslog.servers.servers_dict[server_name].set_port("", expected_str=[
                INCOMPLETE_COMMAND,
                IS_NOT_OF_TYPE_INTEGER], apply=True)
            system.syslog.servers.servers_dict[server_name].set_port(rand_str, expected_str=[
                f"'{rand_str}' {IS_NOT_AN_INTEGER}",
                IS_NOT_OF_TYPE_INTEGER], apply=True)
        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        with allure.independent_step("Configure and validate protocol, should fail"):
            logging.info("Configure and validate protocol, should fail")
            system.syslog.servers.servers_dict[server_name].set_protocol("", expected_str=[
                INCOMPLETE_COMMAND,
                f"{IS_NOT_ONE_OF} ['{SyslogConsts.TCP}', '{SyslogConsts.UDP}', None]"], apply=True)
            if is_bug_active(4283380):
                system.syslog.servers.servers_dict[server_name].set_protocol(rand_str)
            else:
                system.syslog.servers.servers_dict[server_name].set_protocol(rand_str, expected_str=f"{IS_NOT_ONE_OF} ['{SyslogConsts.TCP}', '{SyslogConsts.UDP}']", apply=True)
        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        with allure.independent_step("Configure and validate vrf, should fail"):
            logging.info("Configure and validate vrf, should fail")
            system.syslog.servers.servers_dict[server_name].set_vrf("", expected_str=[
                INCOMPLETE_COMMAND,
                f"{IS_NOT_ONE_OF} ['{SyslogConsts.DEFAULT_VRF}', None, 'Error']"], apply=True)
            system.syslog.servers.servers_dict[server_name].set_vrf(rand_str, expected_str=[
                f"{IS_NOT_ONE_OF} ['{SyslogConsts.DEFAULT_VRF}']",
                "is too short"], apply=True)
        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        with allure.independent_step("Configure and validate filter, should fail"):
            logging.info("Configure and validate filter, should fail")
            # First set up a valid filter configuration
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_filter("2", apply=True).verify_result(False, expected_str=["Error", "match and action properties should be configured for the filter", "Config invalid"], apply=True)
            logging.info(f"Detaching any unapplied config")
            NvueGeneralCli.detach_config(TestToolkit.engines.dut)
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_filter("2", apply=False).verify_result()
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["1"].set_action_filter(
                SyslogConsts.INCLUDE, apply=False)
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["1"].set_match_filter(
                "test.*", apply=True)

            # Now try to set an invalid action filter
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].set_filter("2", apply=False).verify_result()
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["2"].set_action_filter(
                SyslogConsts.INCLUDE, apply=True, expected_str=["Error", "match and action properties should be configured for the filter", "Config invalid"])

        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        with allure.independent_step("Configure and validate filter include, should fail"):
            logging.info("Configure and validate filter include, should fail")
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["2"].set_action_filter(
                SyslogConsts.INCLUDE, apply=True, expected_str=["Error", "match and action properties should be configured for the filter", "Config invalid"])
        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        with allure.independent_step("Configure and validate filter exclude, should fail"):
            logging.info("Configure and validate filter exclude, should fail")
            system.syslog.selectors.selectors_dict[SyslogConsts.DEFAULT_SELECTOR_NAME].filter_dict["2"].set_action_filter(
                SyslogConsts.EXCLUDE, apply=True, expected_str=["Error", "match and action properties should be configured for the filter", "Config invalid"])

        logging.info(f"Detaching any unapplied config")
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
    with allure.step("Cleanup syslog configurations"):
        logging.info("Cleanup syslog configurations")
        system.syslog.unset(apply=True)


def verify_welf_format(line_to_check, firewall_name=".*", expect_welf_format=True):
    welf_format_regex = "id=firewall time=\".*\" fw=\"{}\" pri=\\d msg=\".*\"".format(firewall_name)
    result = re.findall(welf_format_regex, line_to_check)
    with allure.step("Verify msg format"):
        logging.info("Verify msg format")
        logger.info("This line : \n {}\n is {} in welf format".format(line_to_check, "" if result else "not"))
        logger.info("result : {}".format(result))
        if expect_welf_format:
            assert result, "Expect the line to be in welf format, but it was not"
        else:
            assert not result, "Expect the line not to be in welf format, but it was"


def send_random_msg_and_validate_format(remote_server_ip, remote_server_engine, expect_welf_format, firewall_name=".*"):
    random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
    output = send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_received=True)
    verify_welf_format(output, expect_welf_format=expect_welf_format, firewall_name=firewall_name)


def config_and_verify_rsyslog_protocol(server, remote_server_engine, remote_server_ip, protocol):
    with allure.step("Change rsyslog protocol to {}".format(protocol)):
        logging.info("Change rsyslog protocol to {}".format(protocol))
        server.set_protocol(protocol, apply=True)
        server.verify_show_server_output({SyslogConsts.PROTOCOL: protocol})
        random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
        send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_received=True)


def config_and_verify_rsyslog_port(server, remote_server_engine, remote_server_ip, old_port, new_port):
    with allure.step("Change rsyslog port to {}".format(new_port)):
        logging.info("Change rsyslog port to {}".format(new_port))
        server.set_port(new_port, apply=True)
        server.verify_show_server_output({SyslogConsts.PORT: str(new_port)})
        try:
            SonicMgmtContainer.change_rsyslog_port(remote_server_engine, old_port, new_port, SyslogConsts.UDP,
                                                   restart_rsyslog=True)
            random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
            send_msg_to_server(random_msg, remote_server_ip, remote_server_engine, verify_msg_received=True)
        except Exception as err:
            SonicMgmtContainer.change_rsyslog_port(remote_server_engine, old_port, new_port, SyslogConsts.UDP,
                                                   restart_rsyslog=True)
            raise err


def config_and_verify_severity(loganalyzer, syslog, server, server_name, server_engine, severity_level,
                               selector_id=None,
                               global_severity_level=SyslogSeverityLevels.NOTICE):
    with allure.step("Configure and verify severity level: {}".format(severity_level)):
        logging.info("Validate severity level: {}".format(severity_level))
        syslog.selectors.selectors_dict[selector_id].set_severity(severity_level, apply=True)
        syslog.selectors.selectors_dict[selector_id].verify_trap_severity_level(selector_id, severity_level)

        random_msg = RandomizationTool.get_random_string(40, ascii_letters=string.ascii_letters + string.digits)
        add_msg_to_ignore_loganalyzer_regex(loganalyzer, random_msg)
        severity_level_index = SyslogSeverityLevels.SEVERITY_LEVEL_LIST.index(severity_level)
        send_msg_to_server(random_msg, server_name, server_engine, priority=severity_level,
                           verify_msg_received=True,
                           verify_msg_didnt_received=False)

        if severity_level_index + 1 < len(SyslogSeverityLevels.SEVERITY_LEVEL_LIST):
            random_msg = RandomizationTool.get_random_string(40, ascii_letters=string.ascii_letters + string.digits)
            add_msg_to_ignore_loganalyzer_regex(loganalyzer, random_msg)
            rand_recieved_level = random.choice(SyslogSeverityLevels.SEVERITY_LEVEL_LIST[severity_level_index + 1:])
            send_msg_to_server(random_msg, server_name, server_engine, priority=rand_recieved_level,
                               verify_msg_received=True,
                               verify_msg_didnt_received=False)
        if severity_level_index > 0:
            rand_not_recieved_level = random.choice(SyslogSeverityLevels.SEVERITY_LEVEL_LIST[:severity_level_index])
            random_msg = RandomizationTool.get_random_string(35, ascii_letters=string.ascii_letters + string.digits)
            add_msg_to_ignore_loganalyzer_regex(loganalyzer, random_msg)
            send_msg_to_server(random_msg, server_name, server_engine, priority=rand_not_recieved_level,
                               verify_msg_received=False,
                               verify_msg_didnt_received=True)


def add_msg_to_ignore_loganalyzer_regex(loganalyzer, random_msg):
    if loganalyzer:
        for hostname in loganalyzer.keys():
            loganalyzer[hostname].ignore_regex.extend([f".*{random_msg}.*"])


def send_msg_to_server(msg, server_name, server_engine, protocol=None, priority=None, port=None, program=None, facility=None,
                       verify_msg_received=False,
                       verify_msg_didnt_received=False):
    with allure.step("Send msg to server {}".format(server_name)):
        logging.info("Send msg to server {}".format(server_name))

        protocol_flag = f' --{protocol}' if protocol else ''  # must be tcp or udp
        severity = SyslogSeverityLevels.SEVERITY_LEVEL_DICT[priority] if priority else SyslogSeverityLevels.NOTICE
        priority_flag = f' --priority {facility}.{severity}' if facility else f' --priority {SyslogConsts.DAEMON}.{severity}'
        port_flag = f' --port {port}' if port else ''
        program_flag = f' --tag {program}' if program else ''
        extra_flags = protocol_flag + priority_flag + port_flag + program_flag
        logger_cmd = f'logger {extra_flags} "{msg}"'
        TestToolkit.engines.dut.run_cmd(logger_cmd)
        TestToolkit.engines.dut.run_cmd('tail -10 /var/log/syslog')
        output = ''

        if verify_msg_received:
            with allure.step("Verify server {} received the msg".format(server_name)):
                logging.info("Verify server {} received the msg".format(server_name))
                output = verify_msg_in_syslog_file(server_engine, msg, should_find=True)
        elif verify_msg_didnt_received:
            with allure.step("Verify server {} did not receive the msg".format(server_name)):
                logging.info("Verify server {} did not receive the msg".format(server_name))
                verify_msg_in_syslog_file(server_engine, msg, should_find=False)
        return output


def verify_msg_in_syslog_file(engine, msg_to_find, syslog_file='/var/log/syslog', should_find=True):
    cmd = f'cat {syslog_file}|grep {msg_to_find}'
    output = engine.run_cmd(cmd)
    msg_in_file = msg_to_find in output
    logging.info(f"msg_in_file: {msg_in_file}")
    logging.info(f"output: {output}")

    if msg_in_file and not should_find:
        raise Exception("Found the message, but expected not to find it")
    elif not msg_in_file and should_find:
        raise Exception("Didn't find the message, but expected to find it")

    logging.info("{} find the msg as expected".format('' if should_find else 'Did not'))
    return output


def create_syslog_output_dictionary(format=SyslogConsts.STANDARD, format_dict={}, trap=SyslogSeverityLevels.NOTICE,
                                    server_dict=None):
    dictionary = {
        SyslogConsts.FORMAT: {format: format_dict},
        # SyslogConsts.TRAP: trap
    }
    if server_dict:
        dictionary.update(server_dict)
    return dictionary


def create_remote_server_dictionary(server_name, port=SyslogConsts.DEFAULT_PORT, protocol=SyslogConsts.UDP, vrf=SyslogConsts.DEFAULT_VRF):
    dictionary = {
        server_name: {
            SyslogConsts.PORT: str(port),
            SyslogConsts.PROTOCOL: protocol,
            SyslogConsts.VRF: vrf,
            SyslogConsts.SELECTOR: {},
        }
    }
    return dictionary


def create_remote_server_dictionary_with_selector(server_name, priority, port=SyslogConsts.DEFAULT_PORT, protocol=SyslogConsts.UDP,
                                                  vrf=SyslogConsts.DEFAULT_VRF, selector_id=None):
    dictionary = {
        server_name: {
            SyslogConsts.PORT: str(port),
            SyslogConsts.PROTOCOL: protocol,
            SyslogConsts.VRF: vrf,
            SyslogConsts.SELECTOR: {str(priority): {SyslogConsts.SELECTOR_ID: selector_id}},
        }
    }
    return dictionary


def create_selector_dictionary(selector_id, options=None, program=SyslogConsts.DEFAULT_PROGRAM, facility=SyslogConsts.DAEMON, severity=SyslogSeverityLevels.NOTICE, rate_limit=None, filter_action=SyslogConsts.EXCLUDE, filter_match='a+'):
    selector = {selector_id: {
        SyslogConsts.FACILITY: facility,
        SyslogConsts.PROGRAM_NAME: program,
        SyslogConsts.FILTER: {},
        SyslogConsts.RATE_LIMIT: rate_limit,
        SyslogConsts.SEVERITY: severity
    }}
    if options and SyslogConsts.FILTER in options:
        selector[selector_id][SyslogConsts.FILTER] = options[SyslogConsts.FILTER]
    else:
        selector[selector_id][SyslogConsts.FILTER] = {'1': {SyslogConsts.ACTION: filter_action, SyslogConsts.MATCH: filter_match}}

    if options:
        for key, value in options.items():
            if key == SyslogConsts.SEVERITY:
                selector[selector_id][SyslogConsts.SEVERITY] = value
            elif key == SyslogConsts.PROGRAM_NAME:
                selector[selector_id][SyslogConsts.PROGRAM_NAME] = value
            elif key == SyslogConsts.FACILITY:
                selector[selector_id][SyslogConsts.FACILITY] = value
            elif key == SyslogConsts.RATE_LIMIT:
                if isinstance(value, dict):
                    selector[selector_id][SyslogConsts.RATE_LIMIT] = {}
                    if SyslogConsts.INTERVAL in value:
                        selector[selector_id][SyslogConsts.RATE_LIMIT][SyslogConsts.INTERVAL] = value[SyslogConsts.INTERVAL]
                    if SyslogConsts.BURST in value:
                        selector[selector_id][SyslogConsts.RATE_LIMIT][SyslogConsts.BURST] = value[SyslogConsts.BURST]

    logger.info("selector: {}".format(selector))
    return selector[selector_id]


def positive_minimal_flow(remote_server_engine, remote_server):
    system = System()

    with allure.step("Configure remote syslog server: {}".format(remote_server)):
        logging.info("Configure remote syslog server: {}".format(remote_server))
        system.syslog.servers.set_server(remote_server, apply=True)

    try:
        random_msg = RandomizationTool.get_random_string(30, ascii_letters=string.ascii_letters + string.digits)
        with allure.step("Validate show commands"):
            logging.info("Validate show commands")
            expected_server_dictionary = create_remote_server_dictionary(remote_server)
            expected_syslog_dictionary = create_syslog_output_dictionary(
                server_dict={SyslogConsts.SERVER: expected_server_dictionary})
            system.syslog.verify_show_syslog_output(expected_syslog_dictionary)
            system.syslog.servers.verify_show_servers_list([remote_server])
            system.syslog.servers.servers_dict[remote_server].verify_show_server_output(
                expected_server_dictionary[remote_server])

        send_msg_to_server(random_msg, remote_server, remote_server_engine, verify_msg_received=True)
    finally:
        with allure.step("Cleanup syslog configurations"):
            logging.info("Cleanup syslog configurations")
            system.syslog.servers.unset(apply=True)


def get_hostname_from_ip(ip):
    host_name_index = 0
    hostname_str = socket.gethostbyaddr(ip)[host_name_index]
    return remove_mlnx_lab_suffix(hostname_str)


def remove_mlnx_lab_suffix(hostname_string):
    """
    Returns switch hostname without mlnx lab prefix
    :param hostname_string: 'arc-switch1030.mtr.labs.mlnx'
    :return: arc-switch1030
    """
    host_name_index = 0
    return hostname_string.split('.')[host_name_index]
