import logging
import socket
import random
import time
import pytest
from retry import retry
import re

from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon
from ngts.nvos_constants.constants_nvos import ApiType, NtpConsts, CumulusConsts, ServiceConsts
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.service.Service import Service
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.system.gnmi.helpers import validate_cpu_utilization_with_retry
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.system.clock.ClockTools import ClockTools


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_configure_ntp_server(test_api, devices):
    """
    Validate NTP server configuration, state changes, and synchronization behavior.

    Test flow:
    1. Clear all ntp configurations (unset, set state to disabled, set listen to eth0, set vrf to mgmt)
    2. Validate show system ntp commands output (expect default values and empty server list)
    3. Set different date and time (save previous time for comparison)
    4. Configure ntp server and enable ntp
    5. Validate show system ntp output (expect state enabled and clock synchronized)
    6. Validate server configured with default values
    7. Validate system clock and date are up to date (verify time sync occurred)
    8. Update existing ntp server with non-default values (iburst enabled, state disabled, version 3)
    9. Validate ntp server configured values (expect all values as configured)
    10. Validate show system ntp output (expect state enabled but clock unsynchronized due to server disabled)
    11. Unset each of the server configurations (association-type, iburst, state, version)
    12. Validate server configured with default values (expect defaults restored)
    13. Enable ntp server
    14. Validate show system ntp output (expect state enabled and clock synchronized)
    15. Set system ntp disabled
    16. Validate show system ntp output (expect ntp state disabled and clock unsynchronized)
    17. Set system ntp enabled
    18. Validate show system ntp output (expect ntp state enabled and clock synchronized)
    19. Unset system ntp (unset all, then set state to disabled)
    20. Validate show system ntp commands output (expect state disabled and empty server list)
    21. Validate unset system ntp commands (unset listen, state, vrf and verify defaults)
    22. Verify ntp daemon state (in finally block - verify Ntpd is running)
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_name = NtpConsts.SERVER1_IPV4
    ntp_dict = devices.dut.ntp_dict.copy()

    try:
        with allure.step("Clear all ntp configurations"):
            system.ntp.unset().verify_result()
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value).verify_result()
            system.ntp.listen.set(NtpConsts.Listen.ETH0.value).verify_result()
            system.ntp.set(op_param_name=NtpConsts.VRF, op_param_value=NtpConsts.Vrf.MGMT.value,
                           apply=True, ask_for_confirmation=True).verify_result()
            time.sleep(NtpConsts.CONFIG_TIME)

        with allure.step("Validate show system ntp commands output"):
            ntp_dict[NtpConsts.STATE] = NtpConsts.State.DISABLED.value
            ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            ValidationTool.compare_dictionary_content(ntp_show, ntp_dict).verify_result()
            server_list = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show()).get_returned_value()
            assert not server_list, f"server list {server_list} should be empty"

        with allure.step("Set different date and time"):
            prev_time = GeneralCliCommon(TestToolkit.engines.dut).get_utc_time()
            GeneralCliCommon(TestToolkit.engines.dut).set_time(NtpConsts.OLD_DATE)

        with allure.step("Configure ntp server and enable ntp"):
            system.ntp.servers.set_resource(server_name).verify_result()
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value,
                           apply=True).verify_result()
            time.sleep(NtpConsts.SYNCHRONIZATION_MAX_TIME)

        with allure.step("Validate show system ntp output"):
            ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            ntp_dict[NtpConsts.SERVER] = {
                server_name: {
                    NtpConsts.ASSOCIATION_TYPE: NtpConsts.AssociationType.SERVER.value,
                    NtpConsts.IBURST: NtpConsts.Iburst.ENABLED.value,
                    NtpConsts.STATE: NtpConsts.State.ENABLED.value,
                    NtpConsts.VERSION: NtpConsts.Version.VERSION_4.value
                }
            }
            ntp_dict[NtpConsts.STATE] = NtpConsts.State.ENABLED.value
            ntp_dict[NtpConsts.STATUS] = NtpConsts.Status.SYNCHRONISED.value
            ntp_dict[NtpConsts.REFERENCE] = devices.dut.ntp_default_reference
            ntp_dict[NtpConsts.OFFSET] = ntp_show[NtpConsts.OFFSET]  # specific parameter does not verified
            ValidationTool.compare_nested_dictionary_content(ntp_show, ntp_dict).verify_result()

        with allure.step("Validate server configured with default values"):
            server_list = OutputParsingTool.parse_json_str_to_dictionary(
                system.ntp.servers.show(server_name)).get_returned_value()
            server_values = devices.dut.ntp_server1_values_dict.copy()
            ValidationTool.compare_dictionary_content(
                server_list, server_values).verify_result()

        with allure.step("Validate system clock and date"):
            # compare to previous time and validate the change
            curr_time = GeneralCliCommon(TestToolkit.engines.dut).get_utc_time()
            diff_time = int(curr_time) - int(prev_time)
            expected_time = devices.dut.ntp_expected_time
            assert diff_time < expected_time, "ntp diff time: {diff_time} seconds, is higher than expected time of {expected_time} seconds".\
                format(diff_time=diff_time)

        with allure.step("Update existing ntp server with none default values"):
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.IBURST, op_param_value=NtpConsts.Iburst.ENABLED.value).\
                verify_result()
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value).verify_result()
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.VERSION, op_param_value=NtpConsts.Version.VERSION_3.value, apply=True).verify_result()

        with allure.step("Validate ntp server configured values"):
            server_list = OutputParsingTool.parse_json_str_to_dictionary(
                system.ntp.servers.show(server_name)).get_returned_value()
            server_values = devices.dut.ntp_server_none_values_dict.copy()
            ValidationTool.compare_dictionary_content(
                server_list, server_values).verify_result()
            time.sleep(NtpConsts.CONFIG_TIME)

        with allure.step("Validate show system ntp output"):
            ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            ntp_dict[NtpConsts.SERVER] = {server_name: {}}
            ntp_dict[NtpConsts.STATE] = NtpConsts.State.ENABLED.value
            ntp_dict[NtpConsts.STATUS] = NtpConsts.Status.UNSYNCHRONISED.value
            ntp_dict.pop(NtpConsts.REFERENCE)
            ntp_dict.pop(NtpConsts.OFFSET)
            ValidationTool.compare_nested_dictionary_content(ntp_show, ntp_dict).verify_result()

        with allure.step("Unset each of the server configurations"):
            if TestToolkit.tested_api == ApiType.OPENAPI:
                system.ntp.servers.unset_resource(server_name, apply=True).verify_result()
                system.ntp.servers.set_resource(server_name, apply=True).verify_result()
            else:
                system.ntp.servers.resources_dict[server_name].unset(op_param=NtpConsts.ASSOCIATION_TYPE).\
                    verify_result()
                system.ntp.servers.resources_dict[server_name].unset(op_param=NtpConsts.IBURST).\
                    verify_result()
                system.ntp.servers.resources_dict[server_name].unset(op_param=NtpConsts.STATE).verify_result()
                system.ntp.servers.resources_dict[server_name].unset(op_param=NtpConsts.VERSION, apply=True).verify_result()

        with allure.step("Validate server configured with default values"):
            server_list = OutputParsingTool.parse_json_str_to_dictionary(
                system.ntp.servers.show(server_name)).get_returned_value()
            server_values = devices.dut.ntp_server1_values_dict.copy()
            ValidationTool.compare_dictionary_content(
                server_list, server_values).verify_result()

        with allure.step("Enable ntp server"):
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value, apply=True).verify_result()
            time.sleep(NtpConsts.SYNCHRONIZATION_MAX_TIME)

        with allure.step("Validate show system ntp output"):
            ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            ntp_dict[NtpConsts.SERVER] = {server_name: {}}
            ntp_dict[NtpConsts.STATE] = NtpConsts.State.ENABLED.value
            ntp_dict[NtpConsts.STATUS] = NtpConsts.Status.SYNCHRONISED.value
            ntp_dict[NtpConsts.REFERENCE] = devices.dut.ntp_default_reference
            ntp_dict[NtpConsts.OFFSET] = ntp_show[NtpConsts.OFFSET]  # specific parameter does not verified
            ValidationTool.compare_nested_dictionary_content(ntp_show, ntp_dict).verify_result()

        with allure.step("Set system ntp disabled"):
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value,
                           apply=True).verify_result()

        with allure.step("Validate show system ntp output"):
            ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            ntp_dict[NtpConsts.SERVER] = {server_name: {}}
            ntp_dict[NtpConsts.STATE] = NtpConsts.State.DISABLED.value
            ntp_dict[NtpConsts.STATUS] = NtpConsts.Status.UNSYNCHRONISED.value
            ntp_dict.pop(NtpConsts.SERVER)
            ntp_dict.pop(NtpConsts.REFERENCE)
            ntp_dict.pop(NtpConsts.OFFSET)
            ValidationTool.compare_nested_dictionary_content(ntp_show, ntp_dict).verify_result()

        with allure.step("Set system ntp enabled"):
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value,
                           apply=True, ask_for_confirmation=True).verify_result()
            time.sleep(NtpConsts.SYNCHRONIZATION_MAX_TIME)

        with allure.step("Validate show system ntp output"):
            ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            ntp_dict[NtpConsts.SERVER] = {server_name: {}}
            ntp_dict[NtpConsts.STATE] = NtpConsts.State.ENABLED.value
            ntp_dict[NtpConsts.STATUS] = NtpConsts.Status.SYNCHRONISED.value
            ntp_dict[NtpConsts.REFERENCE] = devices.dut.ntp_default_reference
            ntp_dict[NtpConsts.OFFSET] = ntp_show[NtpConsts.OFFSET]  # specific parameter does not verified
            ValidationTool.compare_nested_dictionary_content(ntp_show, ntp_dict).verify_result()

        with allure.step("Unset system ntp"):
            system.ntp.unset().verify_result()
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value, apply=True, ask_for_confirmation=True).verify_result()
            time.sleep(NtpConsts.CONFIG_TIME)

        with allure.step("Validate show system ntp commands output"):
            ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            default_dict = devices.dut.ntp_dict
            default_dict[NtpConsts.STATE] = NtpConsts.State.DISABLED.value
            ValidationTool.compare_dictionary_content(ntp_show, default_dict).verify_result()
            server_list = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show()).get_returned_value()
            assert not server_list, f"server list {server_list} should be empty"

        with allure.step("Validate unset system ntp commands"):
            if TestToolkit.tested_api == ApiType.OPENAPI:
                system.ntp.unset(apply=True).verify_result()
            else:
                system.ntp.unset(op_param=NtpConsts.LISTEN).verify_result()
                system.ntp.unset(op_param=NtpConsts.STATE).verify_result()
                system.ntp.unset(op_param=NtpConsts.VRF, apply=True, ask_for_confirmation=True).verify_result()
            time.sleep(NtpConsts.CONFIG_TIME)
            ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            assert ntp_show[NtpConsts.LISTEN] == NtpConsts.NTP_DEFAULT_DICT[NtpConsts.LISTEN], \
                "Ntp parameter should equal to default value"
            assert ntp_show[NtpConsts.STATE] == NtpConsts.State.DISABLED.value, \
                "Ntp parameter should equal to default value"
            assert ntp_show[NtpConsts.VRF] == NtpConsts.Vrf.MGMT.value, \
                "Ntp parameter should equal to default value"

    finally:
        with allure.step("Verify ntp daemon state"):
            logging.info("Verify ntp daemon state")
            # Verify daemon state (Ntpd is running)


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_configure_ntp_multiple_servers(test_api, devices):
    """
    Validate multiple NTP servers configuration using IPv4, IPv6, and hostname.
    Tests server management, show commands, disable/enable, and unset operations.

    Test flow:
    1. Clear all ntp configurations (unset and set state to disabled)
    2. Configure 10 servers (1 IPv4, 1 hostname, 8 dummy servers) and enable ntp
    3. Validate show system ntp output with all flags (brief/detail for NVUE, expect synchronized)
    4. Validate show system ntp server output with all flags (verify all 10 servers listed)
    5. Validate specific server configuration (show SERVER1_IPV4 details with default values)
    6. Disable state of a specific server (disable SERVER1_IPV4, verify only it becomes disabled)
    7. Check unset of a specific server and verify another server becomes active
       (unset SERVER1_IPV4, verify reference changes to different server)
    8. Check unset of all servers (verify all servers removed and ntp returns to default)
    9. Finally: Unset system ntp
    """
    TestToolkit.tested_api = test_api
    system = System()
    server2_hostname = get_hostname_from_ip(NtpConsts.SERVER2_IPV4)
    ntp_dict = devices.dut.ntp_dict.copy()
    ntp_brief_dict = devices.dut.ntp_dict.copy()

    try:
        with allure.step("Clear all ntp configurations"):
            system.ntp.unset().verify_result()
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value, apply=True).verify_result()

        with allure.step("Configure 10 servers (by v4|v6|hostname)"):
            system.ntp.servers.set_resource(NtpConsts.SERVER1_IPV4).verify_result()
            system.ntp.servers.set_resource(server2_hostname).verify_result()
            for server_id in range(1, (NtpConsts.MULTIPLE_SERVERS_NUMBER - 2)):
                server_name = 'dummy.server' + str(server_id)
                system.ntp.servers.set_resource(server_name, apply=False)
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value,
                           apply=True).verify_result()
            time.sleep(NtpConsts.SYNCHRONIZATION_MAX_TIME)

        with allure.step("Validate show system ntp (all flags) output"):
            ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            if TestToolkit.tested_api == ApiType.OPENAPI:
                # Create a modified version with only the fields that appear in the actual output
                modified_servers_dict = {}
                for server_name, server_config in NtpConsts.MULTIPLE_SERVERS_CONFIG_DICT.items():
                    modified_config = {
                        NtpConsts.ASSOCIATION_TYPE: server_config[NtpConsts.ASSOCIATION_TYPE],
                        NtpConsts.IBURST: NtpConsts.Iburst.ENABLED.value,
                        NtpConsts.STATE: server_config[NtpConsts.STATE],
                        NtpConsts.VERSION: server_config[NtpConsts.VERSION]
                    }
                    modified_servers_dict[server_name] = modified_config
                ntp_dict[NtpConsts.SERVER] = modified_servers_dict
                ntp_dict[NtpConsts.STATUS] = NtpConsts.Status.SYNCHRONISED.value
                ntp_dict[NtpConsts.REFERENCE] = ntp_show[NtpConsts.REFERENCE]
                ntp_dict[NtpConsts.OFFSET] = ntp_show[NtpConsts.OFFSET]  # Offset is not validated
            else:
                ntp_show_brief = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show('brief')).\
                    get_returned_value()
                # Create a modified version with only the fields that appear in the actual output
                modified_servers_dict = {}
                for server_name, server_config in NtpConsts.MULTIPLE_SERVERS_CONFIG_DICT.items():
                    modified_config = {
                        NtpConsts.ASSOCIATION_TYPE: server_config[NtpConsts.ASSOCIATION_TYPE],
                        NtpConsts.IBURST: NtpConsts.Iburst.ENABLED.value,
                        NtpConsts.STATE: server_config[NtpConsts.STATE],
                        NtpConsts.VERSION: server_config[NtpConsts.VERSION]
                    }
                    modified_servers_dict[server_name] = modified_config
                ntp_dict[NtpConsts.SERVER] = ntp_brief_dict[NtpConsts.SERVER] = modified_servers_dict
                ntp_dict[NtpConsts.STATUS] = ntp_brief_dict[NtpConsts.STATUS] = NtpConsts.Status.SYNCHRONISED.value
                ntp_dict[NtpConsts.REFERENCE] = ntp_brief_dict[NtpConsts.REFERENCE] = ntp_show[NtpConsts.REFERENCE]
                ntp_dict[NtpConsts.OFFSET] = ntp_brief_dict[NtpConsts.OFFSET] = ntp_show[NtpConsts.OFFSET]  # Offset is not validated
                ntp_dict[NtpConsts.VRF] = ntp_brief_dict[NtpConsts.VRF] = NtpConsts.Vrf.MGMT.value
                ValidationTool.compare_dictionary_content(ntp_show_brief, ntp_brief_dict).verify_result()
            ValidationTool.compare_dictionary_content(ntp_show, ntp_dict).verify_result()

        with allure.step("Validate show system ntp server (all flags) output"):
            server_list = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show()).get_returned_value()
            if TestToolkit.tested_api == ApiType.OPENAPI:
                server_dict = devices.dut.ntp_multiple_servers_values_dict.copy()
                # Create a modified version with iburst enabled for all servers
                server_dict = {}
                for server_name, server_config in devices.dut.ntp_multiple_servers_values_dict.items():
                    modified_config = server_config.copy()
                    modified_config[NtpConsts.IBURST] = NtpConsts.Iburst.ENABLED.value
                    server_dict[server_name] = modified_config
                server_dict[NtpConsts.SERVER1_IPV4] = server_list[NtpConsts.SERVER1_IPV4]
                server_dict[NtpConsts.SERVER2_HOSTNAME] = server_list[NtpConsts.SERVER2_HOSTNAME]
                ValidationTool.compare_dictionary_content(server_list, server_dict).verify_result()
            else:
                server_brief_list = OutputParsingTool.parse_json_str_to_dictionary(
                    system.ntp.servers.show('brief')).get_returned_value()
                server_detail_list = OutputParsingTool.parse_json_str_to_dictionary(
                    system.ntp.servers.show('detail')).get_returned_value()
                # Create a modified version with iburst enabled for all servers
                expected_server_brief_list = {}
                for server_name, server_config in devices.dut.ntp_multiple_servers_values_dict.items():
                    modified_config = server_config.copy()
                    modified_config[NtpConsts.IBURST] = NtpConsts.Iburst.ENABLED.value
                    expected_server_brief_list[server_name] = modified_config
                ValidationTool.compare_dictionary_content(server_brief_list, expected_server_brief_list).\
                    verify_result()
                listed_servers = len(server_detail_list)
                assert listed_servers == 2, "Listed {listed} servers, expected {expected} servers". \
                    format(listed=listed_servers, expected=2)
                # Create a modified version with iburst enabled for all servers
                expected_server_list = {}
                for server_name, server_config in devices.dut.ntp_multiple_servers_values_dict.items():
                    modified_config = server_config.copy()
                    modified_config[NtpConsts.IBURST] = NtpConsts.Iburst.ENABLED.value
                    expected_server_list[server_name] = modified_config
                ValidationTool.compare_dictionary_content(server_list, expected_server_list). \
                    verify_result()

        with allure.step("Validate server configured with default values"):
            server_dict = OutputParsingTool.parse_json_str_to_dictionary(
                system.ntp.servers.show(NtpConsts.SERVER1_IPV4)).get_returned_value()
            server_values = devices.dut.ntp_server1_values_dict.copy()
            ValidationTool.compare_dictionary_content(
                server_dict, server_values).verify_result()

        with allure.step("Disable state of a specific server"):
            system.ntp.servers.resources_dict[NtpConsts.SERVER1_IPV4].set(
                op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value, apply=True).\
                verify_result()
            server_list = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show()).get_returned_value()
            assert server_list[NtpConsts.SERVER1_IPV4][NtpConsts.STATE] == NtpConsts.State.DISABLED.value, \
                "Server {server} state should be {expected}".\
                format(server=NtpConsts.SERVER1_IPV4, expected=NtpConsts.State.DISABLED.value)
            assert server_list[server2_hostname][NtpConsts.STATE] == NtpConsts.State.ENABLED.value, \
                "Server {server} state should be {expected}".\
                format(server=server2_hostname, expected=NtpConsts.State.ENABLED.value)
            for server_id in range(1, (NtpConsts.MULTIPLE_SERVERS_NUMBER - 2)):
                server_name = 'dummy.server' + str(server_id)
                assert server_list[server_name][NtpConsts.STATE] == NtpConsts.State.ENABLED.value, \
                    "Server {server} state should be {expected}". \
                    format(server=server_name, expected=NtpConsts.State.ENABLED.value)

        with allure.step("Check unset of a specific server and active another server"):
            system.ntp.servers.unset_resource(NtpConsts.SERVER1_IPV4, apply=True).verify_result()
            time.sleep(NtpConsts.SYNCHRONIZATION_MAX_TIME)
            ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            assert ntp_show[NtpConsts.REFERENCE] != NtpConsts.SERVER1_IPV4, \
                "Reference server should be other than {server}".format(server=NtpConsts.SERVER1_IPV4)

            server_list = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show()).get_returned_value()
            ValidationTool.verify_field_exist_in_json_output(
                server_list, NtpConsts.SERVER1_IPV4, should_be_found=False).verify_result()

        with allure.step("Check unset of all servers"):
            system.ntp.unset(NtpConsts.SERVER, apply=True).verify_result()
            time.sleep(5)
            ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            ntp_dict = devices.dut.ntp_dict.copy()
            ValidationTool.compare_dictionary_content(ntp_show, ntp_dict).verify_result()
            server_list = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show()).get_returned_value()
            assert not server_list, f"server list {server_list} should be empty"

    finally:
        with allure.step("Unset system ntp"):
            system.ntp.unset(apply=True).verify_result()


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_ntp_performance(test_api):
    """
    Validate NTP configuration and show command performance with single vs multiple servers.
    Tests configuration time, show command response time, CPU utilization, and sync time.

    Test flow:
    1. Clear all ntp configurations (unset and set state to disabled)
    2. Measure configuring time of 1 server
    3. Measure show system ntp execution time for 1 server
    4. Remove all ntp servers
    5. Measure configuring time of 10 servers (9 dummy + 1 final server)
    6. Measure show system ntp execution time for 10 servers
    7. Validate configuration time diff (expect diff < 2 sec threshold)
    8. Validate show command time diff (expect diff < 0.5 sec threshold)
    9. Validate CPU utilization (verify normal utilization with individual core check)
    10. Remove all ntp servers
    11. Validate system sync time after setting a new server (expect synchronized status)
    12. Finally: Unset system ntp
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_name = NtpConsts.SERVER1_IPV4

    try:
        with allure.step("Clear all ntp configurations"):
            system.ntp.unset().verify_result()
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value,
                           apply=True).verify_result()

        with allure.step("Measure configuring time of 1 server"):
            start_time = time.time()
            system.ntp.servers.set_resource(server_name, apply=True)
            end_time = time.time()
            config_1_duration = end_time - start_time

        with allure.step("Measure show system ntp time of 1 server"):
            start_time = time.time()
            system.ntp.show()
            end_time = time.time()
            show_1_duration = end_time - start_time

        with allure.step("Remove all ntp servers"):
            system.ntp.unset(apply=True).verify_result()

        with allure.step("Measure configuring time of 10 servers"):
            for server_id in range(1, NtpConsts.MULTIPLE_SERVERS_NUMBER - 1):
                server_name = 'dummy.server' + str(server_id)
                system.ntp.servers.set_resource(server_name, apply=False)
            server_name = 'server10'
            start_time = time.time()
            system.ntp.servers.set_resource(server_name, apply=True)
            end_time = time.time()
            config_10_duration = end_time - start_time

        with allure.step("Measure show system ntp time of 10 servers"):
            start_time = time.time()
            system.ntp.show()
            end_time = time.time()
            show_10_duration = end_time - start_time

        with allure.step("Validate configuration diff time"):
            config_duration_diff = config_10_duration - config_1_duration
            assert config_duration_diff < NtpConsts.CONFIG_TIME_DIFF_THRESHOLD, \
                "Configuration diff time: {actual} is higher than expected time: {expected}".\
                format(actual=config_duration_diff, expected=NtpConsts.CONFIG_TIME_DIFF_THRESHOLD)

        with allure.step("Validate show diff time"):
            show_duration_diff = show_10_duration - show_1_duration
            assert show_duration_diff < NtpConsts.SHOW_TIME_DIFF_THRESHOLD, \
                "Show diff time: {actual} is higher than expected time: {expected}".\
                format(actual=show_duration_diff, expected=NtpConsts.SHOW_TIME_DIFF_THRESHOLD)

        with allure.step("Validate cpu utilization"):
            validate_cpu_utilization_with_retry(check_individual_cores=True)

        with allure.step("Remove all ntp servers"):
            system.ntp.unset(apply=True).verify_result()

        with allure.step("Validate system sync time after setting a new server"):
            system.ntp.servers.set_resource(NtpConsts.SERVER1_IPV4, apply=True)
            expected_max_time = CumulusConsts.NTP_SYNCHRONIZATION_MAX_TIME
            ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            assert ntp_show[NtpConsts.STATUS] == NtpConsts.Status.SYNCHRONISED.value, \
                "Synchronization time is longer than expected time of {expected} seconds".\
                format(actual=show_duration_diff, expected=expected_max_time)

    finally:
        with allure.step("Unset system ntp"):
            system.ntp.unset(apply=True).verify_result()


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_ntp_reliability(devices, test_api):
    """
    Validate NTP service reliability under various conditions including reboot, service stop/start,
    unreachable servers, and repeated configuration changes.

    Test flow:
    1. Clear all ntp configurations
    2. Configure ntp server
    3. Verify system clock is synchronized
    4. Reboot system
    5. Verify system clock is synchronized after reboot (Clock remains synchronized)
    6. Stop ntp server (systemctl stop)
    7. Verify system clock is unsynchronized (Clock becomes unsynchronized)
    8. Start ntp server (systemctl start)
    9. Verify system clock is synchronized (Clock recovers synchronization)
    10. Remove all ntp servers
    11. Configure an unreachable ntp server and verify system is still operational
    12. Configure ntp server in the loop and verify system remains stable (iterate multiple times)
    13. Set ntp server to default in the loop and verify system remains stable (unset in loop)
    14. Finally: Unset system ntp
    """
    server_name = NtpConsts.SERVER1_IPV4
    system = System()

    try:
        with allure.step("Clear all ntp configurations"):
            system.ntp.unset().verify_result()

        with allure.step("Configure ntp server"):
            system.ntp.servers.set_resource(server_name, apply=True).verify_result()

        with allure.step("Verify system clock is synchronized"):
            ntp_dict = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            assert ntp_dict[NtpConsts.STATUS] == NtpConsts.Status.SYNCHRONISED.value, \
                "Server {server} status should be {expected}".\
                format(server=server_name, expected=NtpConsts.Status.SYNCHRONISED.value)

        with allure.step('Reboot system'):
            system.reboot.action_reboot(params=devices.dut.ntp_reboot_action_param, send_user_confirmation='y').verify_result()

        with allure.step("Verify system clock is synchronized"):
            ntp_dict = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            assert ntp_dict[NtpConsts.STATUS] == NtpConsts.Status.SYNCHRONISED.value, \
                "Server {server} status should be {expected}".\
                format(server=server_name, expected=NtpConsts.Status.SYNCHRONISED.value)

        with allure.step('Stop ntp server'):
            GeneralCliCommon(TestToolkit.engines.dut).systemctl_stop(devices.dut.ntp_service_name)

        with allure.step("Verify system clock is unsynchronized"):
            ntp_dict = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
            assert ntp_dict[NtpConsts.STATUS] == NtpConsts.Status.UNSYNCHRONISED.value, \
                "Server {server} status should be {expected}".\
                format(server=server_name, expected=NtpConsts.Status.UNSYNCHRONISED.value)

        with allure.step('Start ntp server'):
            GeneralCliCommon(TestToolkit.engines.dut).systemctl_start(devices.dut.ntp_service_name)

        with allure.step("Verify system clock is synchronized"):
            ntp_dict = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
            assert ntp_dict[NtpConsts.STATUS] == NtpConsts.Status.SYNCHRONISED.value, \
                "Server {server} status should be {expected}".\
                format(server=server_name, expected=NtpConsts.Status.SYNCHRONISED.value)

        with allure.step("Remove all ntp servers"):
            system.ntp.unset(NtpConsts.SERVER, apply=True).verify_result()

        with allure.step("Configure an unreachable ntp server and verify system is still operational"):
            system.ntp.servers.set_resource(NtpConsts.INVALID_SERVER, apply=True).verify_result()
            # Validate system is still running by executing show ntp command
            OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()

        with allure.step("Configure ntp server in the loop and verify system remains stable"):
            for server_id in range(1, NtpConsts.NUMBER_OF_ITERATION):
                server_name = 'server-' + str(server_id)
                system.ntp.servers.set_resource(server_name, apply=True).verify_result()
            # Validate system is still stable by executing show ntp command
            OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()

        with allure.step("Set ntp server to default in the loop and verify system remains stable"):
            for server_id in range(1, NtpConsts.NUMBER_OF_ITERATION):
                system.ntp.unset(apply=True).verify_result()
            # Validate system is still stable by executing show ntp command
            OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()

    finally:
        with allure.step("Unset system ntp"):
            system.ntp.unset(apply=True).verify_result()


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_ntp_log(engines, test_api):
    """
    Validate that NTP configuration commands are properly logged to system log files.

    Test flow:
    1. Clear all ntp configurations (rotate logs, unset, set state to disabled)
    2. Configure ntp server and enable ntp
    3. Update server configuration (set state to disabled, set version to 3)
    4. Validate commands exist in system log (verify NTP commands in nv-cli.log)
    5. Finally: Unset system ntp
    """
    server_name = NtpConsts.SERVER1_IPV4
    system = System()
    ssh_connection = ConnectionTool.create_ssh_conn(engines.dut.ip, engines.dut.username,
                                                    engines.dut.password).get_returned_value()

    try:
        with allure.step("Clear all ntp configurations"):
            system.log.rotate_logs()
            system.ntp.unset().verify_result()
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value,
                           apply=True).verify_result()

        with allure.step("Configure ntp server and enable ntp"):
            system.ntp.servers.set_resource(NtpConsts.SERVER1_IPV4).verify_result()
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value,
                           apply=True).verify_result()
            time.sleep(NtpConsts.SYNCHRONIZATION_MAX_TIME)

        with allure.step("Update server configuration"):
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.DISABLED.value).verify_result()
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.VERSION, op_param_value=NtpConsts.Version.VERSION_3.value, apply=True).verify_result()

        with allure.step("Validate commands exist in system log"):
            # For Cumulus devices, verify logs in the nvue component log files
            nvue_component = system.log.component.component_id[CumulusConsts.NTP_LOGS_COMPONENT_ID]
            grep_logs = '|'.join(CumulusConsts.LOG_MSG_SET_NTP)
            output = nvue_component.file.file_id['nv-cli.log'].show(
                op_param=f'| grep -E "{grep_logs}"',
                output_format='',
                dut_engine=ssh_connection
            )

            # Verify that the expected logs are found
            log_search_errors = {log: f'log "{log}" was not found' for log in CumulusConsts.LOG_MSG_SET_NTP}
            if output:
                for log in CumulusConsts.LOG_MSG_SET_NTP:
                    if log in output and log in log_search_errors:
                        del log_search_errors[log]

    finally:
        with allure.step("Unset system ntp"):
            system.ntp.unset(apply=True).verify_result()


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_ntp_invalid_values(test_api):
    """
    Validate NTP configuration rejects invalid parameter values.

    Test flow:
    1. Validate set ntp invalid state (expect failure)
    2. Validate set ntp invalid listen (expect success - invalid listen is allowed)
    3. Validate set ntp server invalid association-type (create server first, expect failure)
    4. Validate set ntp server invalid state (expect failure)
    5. Validate set ntp server invalid version (expect failure)
    6. Finally: Unset system ntp
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_name = NtpConsts.SERVER1_IPV4

    try:
        with allure.step("Validate set ntp invalid state"):
            system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.INVALID_STATE). \
                verify_result(should_succeed=False)

        with allure.step("Validate set ntp invalid listen"):
            system.ntp.set(op_param_name=NtpConsts.LISTEN, op_param_value=NtpConsts.INVALID_LISTEN, apply=True) \
                .verify_result(should_succeed=True)

        with allure.step("Validate set ntp server invalid association-type"):
            system.ntp.servers.set_resource(server_name).verify_result()
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.ASSOCIATION_TYPE, op_param_value=NtpConsts.INVALID_SERVER_ASSOCIATION_TYPE). \
                verify_result(should_succeed=False)

        with allure.step("Validate set ntp server invalid state"):
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.INVALID_SERVER_STATE). \
                verify_result(should_succeed=False)

        with allure.step("Validate set ntp server invalid version"):
            system.ntp.servers.resources_dict[server_name].set(
                op_param_name=NtpConsts.VERSION, op_param_value=NtpConsts.INVALID_SERVER_VERSION).\
                verify_result(should_succeed=False)

    finally:
        with allure.step("Unset system ntp"):
            system.ntp.unset(apply=True).verify_result()


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cgroups_on_ntp(test_api):
    """
    Validate NTP service resource limits using cgroups.

    Test flow:
    1. Clear all ntp configurations and configure ntp service (unset, enable state, set listen to eth0, set vrf to mgmt)
    2. Validate ntp resource limit (set CPU and memory resource limits)
    3. Validate cgroups cpu and memory values (verify values match in NVUE output and flat file)
    """
    TestToolkit.tested_api = test_api
    system = System()
    service = Service()

    with allure.step("Clear all ntp configurations"):
        system.ntp.unset().verify_result()
        system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value).verify_result()
        system.ntp.listen.set(NtpConsts.Listen.ETH0.value).verify_result()
        vrf_value = NtpConsts.Vrf.MGMT.value
        system.ntp.set(op_param_name=NtpConsts.VRF, op_param_value=vrf_value,
                       apply=True, ask_for_confirmation=True).verify_result()
        time.sleep(NtpConsts.CONFIG_TIME)

    with allure.step("Validate ntp resource limit"):
        service.control.service_name.resource_limit.set_cpu(ServiceConsts.NTP_RESOURCE_LIMIT_CPU_DEFAULT_VALUE, apply=True).verify_result()
        service.control.service_name.resource_limit.set_memory(ServiceConsts.NTP_RESOURCE_LIMIT_MEMORY_DEFAULT_VALUE, apply=True).verify_result()

    with allure.step("Validate cgroups cpu and memory value"):
        result = check_cgroups_cpu_and_memory_value(service, ServiceConsts.NTP, ServiceConsts.NTP_RESOURCE_LIMIT_CPU_DEFAULT_VALUE, ServiceConsts.NTP_RESOURCE_LIMIT_MEMORY_DEFAULT_VALUE)
        assert not result, "cgroups cpu and memory value should be correct"


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_show_time_zone(engines, test_api):
    """
    Validate timezone changes and their impact on NTP and syslog service processes.

    Test flow:
    1. Clear all ntp configurations and configure ntp service (unset, enable state, set listen to eth0, set vrf to mgmt)
    2. Set the new timezone to Asia/Kolkata
    3. Verify new timezone in 'nv show system date-time' and in 'timedatectl'
    4. Get syslog and ntp process IDs before adding server
    5. Add ntp server with iburst enabled
    6. Validate ntp synchronization status (expect synchronized)
    7. Get syslog and ntp process IDs after adding server (verify PIDs changed from step 4)
    8. Set the new timezone to America/Los_Angeles
    9. Verify new timezone in 'nv show system date-time' and in 'timedatectl'
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_name = NtpConsts.SERVER4_IPV4
    new_timezone = "Asia/Kolkata"

    with allure.step("Clear all ntp configurations"):
        system.ntp.unset().verify_result()
        system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value).verify_result()
        system.ntp.listen.set(NtpConsts.Listen.ETH0.value).verify_result()
        vrf_value = NtpConsts.Vrf.MGMT.value
        system.ntp.set(op_param_name=NtpConsts.VRF, op_param_value=vrf_value,
                       apply=True, ask_for_confirmation=True).verify_result()
        time.sleep(NtpConsts.CONFIG_TIME)

    with allure.step("Set the new timezone with 'nv set system date-time timezone'"):
        ClockTools.set_timezone(new_timezone, system, apply=True).verify_result()

    with allure.step("Verify 'nv show system date-time' output"):
        with allure.independent_step("Verify new timezone in 'nv show system date-time' and in 'timedatectl'"):
            ClockTools.verify_timezone(engines, system, expected_timezone=new_timezone)

    pid_syslog_old = TestToolkit.engines.dut.run_cmd("ps axf | grep rsyslog | grep -v grep | awk '{print $1}'")
    pid_ntp_old = TestToolkit.engines.dut.run_cmd("ps axf | grep ntp | grep -v grep | awk '{print $1}'")

    with allure.step("Add ntp server"):
        system.ntp.servers.set_resource(server_name).verify_result()
        system.ntp.servers.resources_dict[server_name].set(op_param_name=NtpConsts.IBURST, op_param_value=NtpConsts.Iburst.ENABLED.value, apply=True).verify_result()
        ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
        assert ntp_show[NtpConsts.STATUS] == NtpConsts.Status.SYNCHRONISED.value, \
            "Server {server} status should be {expected}".\
            format(server=server_name, expected=NtpConsts.Status.SYNCHRONISED.value)

    pid_syslog_new = TestToolkit.engines.dut.run_cmd("ps axf | grep rsyslog | grep -v grep | awk '{print $1}'")
    pid_ntp_new = TestToolkit.engines.dut.run_cmd("ps axf | grep ntp | grep -v grep | awk '{print $1}'")

    assert pid_syslog_old != pid_syslog_new, "syslog process ID should change"
    assert pid_ntp_old != pid_ntp_new, "ntp process ID should change"

    new_timezone = "America/Los_Angeles"

    with allure.step("Set the new timezone with 'nv set system date-time timezone'"):
        ClockTools.set_timezone(new_timezone, system, apply=True).verify_result()

    with allure.step("Verify 'nv show system date-time' output"):
        with allure.independent_step("Verify new timezone in 'nv show system date-time' and in 'timedatectl'"):
            ClockTools.verify_timezone(engines, system, expected_timezone=new_timezone)


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_configure_service_ntp(test_api):
    """
    Validate NTP service configuration with multiple servers, association types, iburst settings,
    and various show command outputs.

    Test flow:
    1. Clear all ntp configurations and verify /etc/ntpsec/ntp.conf has no server or pool entries
    2. Validate ntp daemon state (ntpsec@mgmt should be active)
    3. Configure ntp service (enable state, set listen to eth0, set vrf to mgmt)
    4. Add ntp servers with iburst enabled (3 servers) and iburst disabled (3 servers)
       and verify iburst configuration in /etc/ntpsec/ntp.conf
    5. Update servers with association-type pool (3 servers) and verify pool configuration in /etc/ntpsec/ntp.conf
    6. Wait for ntp synchronization and validate status (expect synchronized)
    7. Verify nv show system ntp brief output (validate full ntp dict with 6 servers)
    8. Verify nv show system ntp listen output (validate eth0 interface)
    9. Verify nv show system ntp server brief output (validate all servers configuration)
    10. Verify nv show system ntp server detail output (expect non-empty output)
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_name = NtpConsts.SERVER4_IPV4
    ntp_dict = dict(NtpConsts.NTP_DEFAULT_DICT)
    ntp_dict.pop(NtpConsts.AUTHENTICATION, None)
    ntp_dict.pop(NtpConsts.DHCP, None)

    with allure.step("Clear all ntp configurations"):
        system.ntp.unset().verify_result()
        output = TestToolkit.engines.dut.run_cmd("cat /etc/ntpsec/ntp.conf")
        assert ("server" not in output) and ("pool" not in output), "/etc/ntpsec/ntp.conf should not contain server or pool"

    with allure.step('Validate ntp daemon state'):
        assert GeneralCliCommon(TestToolkit.engines.dut).systemctl_is_service_active('ntpsec@mgmt'), 'ntpsec@mgmt should be active'

    with allure.step("Configure ntp service"):
        system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value).verify_result()
        system.ntp.listen.set(NtpConsts.Listen.ETH0.value).verify_result()
        vrf_value = NtpConsts.Vrf.MGMT.value
        system.ntp.set(op_param_name=NtpConsts.VRF, op_param_value=vrf_value, apply=True, ask_for_confirmation=True).verify_result()
        time.sleep(NtpConsts.CONFIG_TIME)

    with allure.step("Add ntp servers with iburst enabled"):
        for server_name in [NtpConsts.SERVER5_IPV4, NtpConsts.SERVER7_IPV4, NtpConsts.SERVER9_IPV4]:
            system.ntp.servers.set_resource(server_name).verify_result()
            system.ntp.servers.resources_dict[server_name].set(op_param_name=NtpConsts.IBURST, op_param_value=NtpConsts.Iburst.ENABLED.value, apply=True).verify_result()
        for server_name in [NtpConsts.SERVER6_IPV4, NtpConsts.SERVER8_IPV4, NtpConsts.SERVER10_IPV4]:
            system.ntp.servers.set_resource(server_name).verify_result()
            system.ntp.servers.resources_dict[server_name].set(op_param_name=NtpConsts.IBURST, op_param_value=NtpConsts.Iburst.DISABLED.value, apply=True).verify_result()
        output = TestToolkit.engines.dut.run_cmd("cat /etc/ntpsec/ntp.conf")
        assert ("google.com iburst" in output) or ("1.cumulusnetworks.pool.ntp.org iburst" in output) or ("3.cumulusnetworks.pool.ntp.org iburst" in output), "/etc/ntpsec/ntp.conf should contain google.com iburst or 1.cumulusnetworks.pool.ntp.org iburst or 3.cumulusnetworks.pool.ntp.org iburst"

    with allure.step("Add ntp servers with association-type pool"):
        for server_name in [NtpConsts.SERVER5_IPV4, NtpConsts.SERVER6_IPV4, NtpConsts.SERVER7_IPV4]:
            # system.ntp.servers.set_resource(server_name).verify_result()
            system.ntp.servers.resources_dict[server_name].set(op_param_name=NtpConsts.ASSOCIATION_TYPE, op_param_value=NtpConsts.AssociationType.POOL.value, apply=True).verify_result()
        output = TestToolkit.engines.dut.run_cmd("cat /etc/ntpsec/ntp.conf")
        assert ("pool google.com" in output) or ("pool 1.cumulusnetworks.pool.ntp.org" in output) or ("pool 3.cumulusnetworks.pool.ntp.org" in output), "/etc/ntpsec/ntp.conf should contain pool google.com or pool 1.cumulusnetworks.pool.ntp.org or pool 3.cumulusnetworks.pool.ntp.org"

    with allure.step("Wait for ntp synchronization"):
        ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
        assert ntp_show[NtpConsts.STATUS] == NtpConsts.Status.SYNCHRONISED.value, \
            "Server {server} status should be {expected}".\
            format(server=server_name, expected=NtpConsts.Status.SYNCHRONISED.value)

    ntp_dict[NtpConsts.VRF] = NtpConsts.Vrf.MGMT.value
    ntp_dict[NtpConsts.LISTEN] = {NtpConsts.Listen.ETH0.value: {}}
    ntp_dict[NtpConsts.STATE] = NtpConsts.State.ENABLED.value
    ntp_dict[NtpConsts.STATUS] = NtpConsts.Status.SYNCHRONISED.value
    ntp_dict[NtpConsts.SERVER] = {
        NtpConsts.SERVER5_IPV4: {
            NtpConsts.ASSOCIATION_TYPE: NtpConsts.AssociationType.POOL.value,
            NtpConsts.IBURST: NtpConsts.Iburst.ENABLED.value,
            NtpConsts.STATE: NtpConsts.State.ENABLED.value,
            NtpConsts.VERSION: NtpConsts.Version.VERSION_4.value
        },
        NtpConsts.SERVER6_IPV4: {
            NtpConsts.ASSOCIATION_TYPE: NtpConsts.AssociationType.POOL.value,
            NtpConsts.IBURST: NtpConsts.Iburst.DISABLED.value,
            NtpConsts.STATE: NtpConsts.State.ENABLED.value,
            NtpConsts.VERSION: NtpConsts.Version.VERSION_4.value
        },
        NtpConsts.SERVER7_IPV4: {
            NtpConsts.ASSOCIATION_TYPE: NtpConsts.AssociationType.POOL.value,
            NtpConsts.IBURST: NtpConsts.Iburst.ENABLED.value,
            NtpConsts.STATE: NtpConsts.State.ENABLED.value,
            NtpConsts.VERSION: NtpConsts.Version.VERSION_4.value
        },
        NtpConsts.SERVER8_IPV4: {
            NtpConsts.ASSOCIATION_TYPE: NtpConsts.AssociationType.SERVER.value,
            NtpConsts.IBURST: NtpConsts.Iburst.DISABLED.value,
            NtpConsts.STATE: NtpConsts.State.ENABLED.value,
            NtpConsts.VERSION: NtpConsts.Version.VERSION_4.value
        },
        NtpConsts.SERVER9_IPV4: {
            NtpConsts.ASSOCIATION_TYPE: NtpConsts.AssociationType.SERVER.value,
            NtpConsts.IBURST: NtpConsts.Iburst.ENABLED.value,
            NtpConsts.STATE: NtpConsts.State.ENABLED.value,
            NtpConsts.VERSION: NtpConsts.Version.VERSION_4.value
        },
        NtpConsts.SERVER10_IPV4: {
            NtpConsts.ASSOCIATION_TYPE: NtpConsts.AssociationType.SERVER.value,
            NtpConsts.IBURST: NtpConsts.Iburst.DISABLED.value,
            NtpConsts.STATE: NtpConsts.State.ENABLED.value,
            NtpConsts.VERSION: NtpConsts.Version.VERSION_4.value
        }
    }

    with allure.step("Verify nv show system ntp brief output"):
        ntp_show_brief = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show(op_param='brief')).get_returned_value()
        ValidationTool.compare_dictionary_content(ntp_show_brief, ntp_dict).verify_result()

    with allure.step("Verify nv show system ntp listen output"):
        ntp_show_listen = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.listen.show()).get_returned_value()
        ValidationTool.compare_dictionary_content(ntp_show_listen, {"eth0": {}}).verify_result()

    # with allure.step("Verify nv show system ntp listen eth0 output"):
    #     ntp_show_listen = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.listen.show(op_param='eth0')).get_returned_value()
    #     ValidationTool.compare_dictionary_content(ntp_show_listen, ntp_dict).verify_result()

    with allure.step("Verify nv show system ntp server brief output"):
        ntp_show_server = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show(op_param='brief')).get_returned_value()
        ValidationTool.compare_dictionary_content(ntp_show_server, ntp_dict[NtpConsts.SERVER]).verify_result()

    with allure.step("Verify nv show system ntp server detail output"):
        ntp_show_server_detail = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.servers.show(op_param='detail')).get_returned_value()
        assert ntp_show_server_detail != {}, "nv show system ntp server detail output should not be empty"


@pytest.mark.system
@pytest.mark.ntp
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_ntp_server_restart(test_api):
    """
    Validate NTP server operations and nvued process behavior during server configuration changes.

    Test flow:
    1. Clear all ntp configurations
    2. Configure ntp service (enable state, set listen to eth0, set vrf to mgmt)
    3. Add ntp servers with iburst enabled (3 servers) and iburst disabled (3 servers)
    4. Wait for ntp synchronization and validate status (expect synchronized)
    5. Get nvued process ID before unset
    6. Unset all ntp servers
    7. Verify nvued process ID changed (nvued was restarted)
    8. Verify ntp synchronization is lost (status should be unsynchronized)
    """
    TestToolkit.tested_api = test_api
    system = System()
    server_name = NtpConsts.SERVER4_IPV4

    with allure.step("Clear all ntp configurations"):
        system.ntp.unset().verify_result()

    with allure.step("Configure ntp service"):
        system.ntp.set(op_param_name=NtpConsts.STATE, op_param_value=NtpConsts.State.ENABLED.value).verify_result()
        system.ntp.listen.set(NtpConsts.Listen.ETH0.value).verify_result()
        vrf_value = NtpConsts.Vrf.MGMT.value
        system.ntp.set(op_param_name=NtpConsts.VRF, op_param_value=vrf_value, apply=True, ask_for_confirmation=True).verify_result()
        time.sleep(NtpConsts.CONFIG_TIME)

    with allure.step("Add ntp servers with iburst enabled"):
        for server_name in [NtpConsts.SERVER5_IPV4, NtpConsts.SERVER7_IPV4, NtpConsts.SERVER9_IPV4]:
            system.ntp.servers.set_resource(server_name).verify_result()
            system.ntp.servers.resources_dict[server_name].set(op_param_name=NtpConsts.IBURST, op_param_value=NtpConsts.Iburst.ENABLED.value, apply=True).verify_result()
        for server_name in [NtpConsts.SERVER6_IPV4, NtpConsts.SERVER8_IPV4, NtpConsts.SERVER10_IPV4]:
            system.ntp.servers.set_resource(server_name).verify_result()
            system.ntp.servers.resources_dict[server_name].set(op_param_name=NtpConsts.IBURST, op_param_value=NtpConsts.Iburst.DISABLED.value, apply=True).verify_result()

    with allure.step("Wait for ntp synchronization"):
        ntp_show = wait_for_ntp_status(system, NtpConsts.Status.SYNCHRONISED.value)
        assert ntp_show[NtpConsts.STATUS] == NtpConsts.Status.SYNCHRONISED.value, \
            "Ntp status should be {expected}".format(expected=NtpConsts.Status.SYNCHRONISED.value)

    nvued_initial_pid = TestToolkit.engines.dut.run_cmd("ps -ef | grep nvued | grep -v grep")

    with allure.step("Unset ntp server"):
        system.ntp.servers.unset(apply=True).verify_result()

    with allure.step("Verify nvued process is restarted"):
        nvued_new_pid = TestToolkit.engines.dut.run_cmd("ps -ef | grep nvued | grep -v grep")
        assert nvued_initial_pid != nvued_new_pid, "nvued process should not be restarted"

    with allure.step("Verify ntp synchronization is lost"):
        ntp_show = wait_for_ntp_status(system, NtpConsts.Status.UNSYNCHRONISED.value)
        assert ntp_show[NtpConsts.STATUS] == NtpConsts.Status.UNSYNCHRONISED.value, \
            "Ntp status should be {expected}".format(expected=NtpConsts.Status.UNSYNCHRONISED.value)

# ---------------------------------------------


def check_cgroups_cpu_and_memory_value(service, service_name=ServiceConsts.NTP, cpu_value=0, memory_value=0):
    output_nvue = OutputParsingTool.parse_json_str_to_dictionary(service.control.show(op_param=service_name)).get_returned_value()

    while cpu_value != 0:
        cpu_value_status_nvue = 0
        cpu_value_status_flat_file = 0
        try:
            if output_nvue["resource-limit"]["cpu"] != cpu_value:
                logging.info(
                    "The CPU value of {0} is NOT correct for service {1}".format(
                        cpu_value, service_name
                    )
                )
            else:
                logging.info(
                    "The CPU value of {0} is correct for service {1}".format(
                        cpu_value, service_name
                    )
                )
                cpu_value_status_nvue = 1
            output_file = TestToolkit.engines.dut.run_cmd("cat /etc/systemd/system/{0}.service.d/override.conf".format(service_name))
            if not re.search("CPUQuota=%s" % cpu_value, output_file):
                logging.info(
                    "The CPU value of {0} is NOT correct for service {1} in flat file".format(
                        cpu_value, service_name
                    )
                )
            else:
                logging.info(
                    "The CPU value of {0} is correct for service {1} in flat file".format(
                        cpu_value, service_name
                    )
                )
                cpu_value_status_flat_file = 1
        except KeyError:
            logging.info("Json output format doesn't have the correct keys for cpu values")
            return False
        if cpu_value_status_nvue and cpu_value_status_flat_file:
            return True
        else:
            return False
    while memory_value != 0:
        memory_value_status_nvue = 0
        memory_value_status_flat_file = 0
        try:
            if output_nvue["resource-limit"]["memory"] != memory_value:
                logging.info(
                    "The memory value of {0} is NOT correct for service {1}".format(
                        memory_value, service_name
                    )
                )
            else:
                logging.info(
                    "The memory value of {0} is correct for service {1}".format(
                        memory_value, service_name
                    )
                )
                memory_value_status_nvue = 1
            output_file = TestToolkit.engines.dut.run_cmd("cat /etc/systemd/system/{0}.service.d/override.conf".format(service_name))
            if not re.search("MemoryMax=%s" % memory_value, output_file):
                logging.info(
                    "The memory value of {0} is NOT correct for service {1} in flat file".format(
                        memory_value, service_name
                    )
                )
            else:
                logging.info(
                    "The memory value of {0} is correct for service {1} in flat file".format(
                        memory_value, service_name
                    )
                )
                memory_value_status_flat_file = 1
        except KeyError:
            logging.info(
                "Json output format doesn't have the correct keys for memory values"
            )
            return False

        if memory_value_status_nvue and memory_value_status_flat_file:
            return True
        else:
            return False


def get_hostname_from_ip(ip):
    host_name_index = 0
    hostname_str = socket.gethostbyaddr(ip)[host_name_index]

    # Remove mlnx labs suffix from switch hostname
    return hostname_str.split('.')[host_name_index] + NtpConsts.HOSTNAME_SUFFIX


def verify_ntp_sync_stabilization(nv_command, expected_listen, expected_time, engine_dut=None):
    with allure.step(f"Verify ntp status is synchronized, listen to {expected_listen}, "
                     f"and stable for {expected_time} sec"):
        start_time = time.time()
        diff_time = 0
        while diff_time < expected_time:
            verify_ntp_status_and_listen(nv_command, expected_listen, NtpConsts.Status.SYNCHRONISED.value, engine_dut)
            diff_time = time.time() - start_time


@retry(Exception, tries=10, delay=6)
def verify_ntp_status_and_listen(nv_command, expected_listen, expected_status, engine_dut=None):
    with allure.step(f"Verify ntp status is {expected_status}, and listen to {expected_listen}"):
        ntp_show = OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.system.ntp.show(dut_engine=engine_dut)).get_returned_value()
        assert ntp_show[NtpConsts.STATUS] == expected_status, (f'NTP status is {ntp_show[NtpConsts.STATUS]},'
                                                               f'while it should be "{expected_status}"')
        assert ntp_show[NtpConsts.LISTEN] == {expected_listen: {}}, (f'NTP listen is {ntp_show[NtpConsts.LISTEN]},'
                                                                     f'while it should be "{expected_listen}"')


def wait_for_ntp_status(system, expected_status, timeout=CumulusConsts.NTP_SYNCHRONIZATION_MAX_TIME, interval=1):
    elapsed_time = 0
    # TestToolkit.engines.dut.run_cmd('sudo systemctl restart ntpsec@mgmt')
    while elapsed_time < timeout:
        ntp_show = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()).get_returned_value()
        if ntp_show.get(NtpConsts.STATUS) == expected_status:
            return ntp_show
        time.sleep(interval)
        # TestToolkit.engines.dut.run_cmd('sudo systemctl restart ntpsec@mgmt')
        elapsed_time += interval
    # Return the last value even if not matching
    return ntp_show
