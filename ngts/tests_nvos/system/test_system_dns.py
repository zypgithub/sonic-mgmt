import logging
from ngts.tools.test_utils import allure_utils as allure
import pytest
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime

logger = logging.getLogger()

BASE_IMAGE_VERSION_TO_INSTALL = "nvos-amd64-{pre_release_name}.bin"
BASE_IMAGE_VERSION_TO_INSTALL_PATH = "/auto/sw_system_release/nos/nvos/{pre_release_name}/amd64/{base_image}"


def clear_system_dns(system, engines):
    """
    Method to unset the system dns configurations
    :param system:  System object
    :param engines: Engines object
    """
    with allure.step('Run unset system DNS server and apply config'):
        system.dns.unset(SystemConsts.DNS_SERVER, apply=True, dut_engine=engines.dut).verify_result()


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_system_dns_server(engines, test_api):
    """
    Run set system dns server command and verify in show command
        1. Run ‘nv set system dns server <ip> and verify command is completed successfully
        2. Check ‘nv show system dns server’ ond validate DNS server <ip> in output
        3. Check ‘nv show system dns server <ip>’ and validate <ip> DNS server information in output

    """
    TestToolkit.tested_api = test_api
    dns_server_id = SystemConsts.DNS_SERVER_IDS["ipv4"]
    system = System()
    if test_api == ApiType.OPENAPI:
        dns_server_id_param_value = {dns_server_id: {}}
    else:
        dns_server_id_param_value = dns_server_id
    try:
        with allure.step('Run set system dns server <server-id>command and apply config'):
            system.dns.set(SystemConsts.DNS_SERVER, dns_server_id_param_value, apply=True, dut_engine=engines.dut)

        with allure.step('Verify DNS server in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id in dns_output, "The configured DNS server is not present in show system dns"

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.parametrize('dns_server_id', SystemConsts.DNS_SERVER_LIST)
def test_set_system_dns_functionality(engines, test_api, release_name, dns_server_id):
    """
    Run set system dns server command and verify in show command
        1. Attempt a file fetch from a build server and verify it is successful
        2. Verify contents of resolv.conf file that it does not have <ip> listed as DNS server
        3. Run ‘nv set system dns server <ip> and verify command is completed successfully
        4. Verify contents of resolv.conf file that it have <ip> listed as DNS server
        5. Attempt a file fetch from a build server and verify it is not successful

    """
    TestToolkit.tested_api = test_api
    release_name = "25.01.4000"
    system = System()
    if test_api == ApiType.OPENAPI:
        dns_server_id_param_value = {dns_server_id: {}}
    else:
        dns_server_id_param_value = dns_server_id
    try:
        verify_dns_in_resolv_file(engines, [dns_server_id], is_present=False)

        with allure.step(f"Update path with provided release name: {release_name}"):
            global BASE_IMAGE_VERSION_TO_INSTALL
            BASE_IMAGE_VERSION_TO_INSTALL = BASE_IMAGE_VERSION_TO_INSTALL.format(pre_release_name=release_name)
            logger.info(f"base image name: {BASE_IMAGE_VERSION_TO_INSTALL}")

            global BASE_IMAGE_VERSION_TO_INSTALL_PATH
            BASE_IMAGE_VERSION_TO_INSTALL_PATH = BASE_IMAGE_VERSION_TO_INSTALL_PATH.format(
                pre_release_name=release_name,
                base_image=BASE_IMAGE_VERSION_TO_INSTALL)

        with allure.step("Fetch the image"):
            scp_path = 'scp://{}:{}@{}'.format("root", "3tango", "fit-build-240")

            with allure.step("Fetch an image {}".format(scp_path + BASE_IMAGE_VERSION_TO_INSTALL_PATH)):
                system.image.action_fetch(scp_path + BASE_IMAGE_VERSION_TO_INSTALL_PATH)

        with allure.step('Run set system dns server <server-id>command and apply config'):
            system.dns.set(SystemConsts.DNS_SERVER, dns_server_id_param_value,
                           apply=True, dut_engine=engines.dut).verify_result()

        verify_dns_in_resolv_file(engines, [dns_server_id])

        with allure.step("Attempt fetching the image which should fail"):
            scp_path = 'scp://{}:{}@{}'.format("root", "3tango", "fit-build-240")
            with allure.step("Fetch an image {}".format(scp_path + BASE_IMAGE_VERSION_TO_INSTALL_PATH)):
                system.image.action_fetch(scp_path + BASE_IMAGE_VERSION_TO_INSTALL_PATH,
                                          expected_str="Failed to create file")

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_unset_system_dns_server(engines):
    """
    Run set system dns server command and verify in show command
        1. Run ‘nv set system dns server <dns_server_id_ipv4> and verify command is completed successfully
        2. Run ‘nv set system dns server <dns_server_id_ipv6> and verify command is completed successfully
        3. Check ‘nv show system dns server’ ond validate DNS server ips ipv4 and ipv6 in output
        4. Verify contents of resolv.conf file that it has <ips> ipv4 and ipv6 listed as DNS servers
        5. Run ‘nv unset system dns server' and verify command is completed successfully
        6. Check ‘nv show system dns server’ ond validate DNS server ipv6 and ipv4 are not in output
        7. Verify contents of resolv.conf file that it does not have ipv6 and ipv4 listed as DNS servers

    """
    dns_server_id_ipv4 = SystemConsts.DNS_SERVER_IDS["ipv4"]
    dns_server_id_ipv6 = SystemConsts.DNS_SERVER_IDS["ipv6"]
    system = System()

    try:
        with allure.step('Run set system dns server <server-id> ipv4 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{dns_server_id_ipv4}"',
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server <server-id> ipv6 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{dns_server_id_ipv6}"',
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify DNS server ipv4 and ipv6  in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 in dns_output, "The configured DNS server ipv4 is not present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"

        verify_dns_in_resolv_file(engines, [dns_server_id_ipv4, dns_server_id_ipv6])

        with allure.step('Run unset system dns server command and apply config'):
            system.dns.unset(SystemConsts.DNS_SERVER, apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify DNS server ipv4 and ipv6 are not present in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 not in dns_output, "The configured DNS server ipv4 is present in show system dns"
            assert dns_server_id_ipv6 not in dns_output, "The configured DNS server ipv6 is present in show system dns"

        verify_dns_in_resolv_file(engines, [dns_server_id_ipv4, dns_server_id_ipv6], is_present=False)

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_unset_system_dns_server_ip(engines):
    """
    Run set system dns server command and verify in show command
        1. Run ‘nv set system dns server <dns_server_id_ipv4> and verify command is completed successfully
        2. Run ‘nv set system dns server <dns_server_id_ipv6> and verify command is completed successfully
        3. Check ‘nv show system dns server’ ond validate DNS server ips ipv4 and ipv6 in output
        4. Verify contents of resolv.conf file that it has <ips> ipv4 and ipv6 listed as DNS servers
        5. Run ‘nv unset system dns server <dns_server_id_ipv4> and verify command is completed successfully
        6. Check ‘nv show system dns server’ ond validate DNS server ipv6 in output but no ipv4
        7. Verify contents of resolv.conf file that it has ipv6 but no ipv4 listed as DNS servers

    """
    dns_server_id_ipv4 = SystemConsts.DNS_SERVER_IDS["ipv4"]
    dns_server_id_ipv6 = SystemConsts.DNS_SERVER_IDS["ipv6"]
    system = System()

    try:
        with allure.step('Run set system dns server <server-id> ipv4 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{dns_server_id_ipv4}"',
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server <server-id> ipv6 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{dns_server_id_ipv6}"',
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify DNS server ipv4 and ipv6  in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 in dns_output, "The configured DNS server ipv4 is not present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"

        verify_dns_in_resolv_file(engines, [dns_server_id_ipv4, dns_server_id_ipv6])

        with allure.step('Run unset system dns server <server-id> ipv4 command and apply config'):
            arg = SystemConsts.DNS_SERVER + " " + dns_server_id_ipv4
            system.dns.unset(arg, apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify DNS server ipv4 is not present and ipv6 is, in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 not in dns_output, "The configured DNS server ipv4 is present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"

        with allure.step('Verify in resolv.conf file that it is updated with ipv6 but not ipv4'):
            verify_dns_in_resolv_file(engines, [dns_server_id_ipv6])
            verify_dns_in_resolv_file(engines, [dns_server_id_ipv4], is_present=False)

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_set_system_invalid_dns_server(engines):
    """
    Run set system dns server command and verify in show command
        1. Run ‘nv unset system dns server <ip> and verify command is not completed successfully

    """
    system = System()
    invalid_ip = "420.420.42.42"
    invalid_ip_format = "1.1.1"
    invalid_ip_multicast = "255.255.255.255"
    invalid_ip_localhost = "127.0.0.1"

    try:
        with allure.step('Run set system dns server invalid_ip command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{invalid_ip}"',
                           apply=True, dut_engine=engines.dut).verify_result(should_succeed=False)

        with allure.step('Run set system dns server invalid_ip_format command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{invalid_ip_format}"',
                           apply=True, dut_engine=engines.dut).verify_result(should_succeed=False)

        with allure.step('Run set system dns server invalid_ip_multicast command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{invalid_ip_multicast}"',
                           apply=True, dut_engine=engines.dut).verify_result(should_succeed=False)

        with allure.step('Run set system dns server invalid_ip_multicast command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=f'"{invalid_ip_localhost}"',
                           apply=True, dut_engine=engines.dut).verify_result(should_succeed=False)

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_system_dns_server_max(engines):
    """
    Run set system dns server command and verify in show command
        1. Run ‘nv set system dns server <dns_server_id_ipv4> and verify command is completed successfully
        2. Run ‘nv set system dns server <dns_server_id_ipv6> and verify command is completed successfully
        3. Run ‘nv set system dns server '1.1.1.1' and verify command is completed successfully
        4. Check ‘nv show system dns server’ ond validate all configured DNS servers in output
        5. Run ‘nv set system dns server '2.2.2.2' and verify it shows error that max DNS server config is reached
        6. Run ‘nv unset system dns server 1.1.1.1' and verify command is completed successfully
        7. Run ‘nv set system dns server '2.2.2.2' and verify command is completed successfully
        8. Check ‘nv show system dns server’ ond validate all configured DNS servers in output

    """
    dns_server_id_ipv4 = SystemConsts.DNS_SERVER_IDS["ipv4"]
    dns_server_id_ipv6 = SystemConsts.DNS_SERVER_IDS["ipv6"]
    system = System()

    try:
        with allure.step('Run set system dns server <server-id> ipv4 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id_ipv4,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server <server-id> ipv6 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id_ipv6,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server 1.1.1.1 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value="1.1.1.1",
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify all configured DNS servers in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 in dns_output, "The configured DNS server ipv4 is not present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"
            assert "1.1.1.1" in dns_output, "The configured DNS server ipv6 is not present in show system dns"

        with allure.step('Run set system dns server 2.2.2.2 command and verify it throws max error'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value="2.2.2.2",
                           apply=True, dut_engine=engines.dut).verify_result(should_succeed=False)

        with allure.step('Run unset system dns server 1.1.1.1 command and apply config'):
            system.dns.unset(SystemConsts.DNS_SERVER + " " + "1.1.1.1",
                             apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server 2.2.2.2 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value="2.2.2.2",
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify all configured DNS servers are present in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 in dns_output, "The configured DNS server ipv4 is not present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"
            assert "2.2.2.2" in dns_output, "The configured DNS server ipv6 is not present in show system dns"

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_system_dns_server_max_single_apply(engines):
    """
    Run set system dns server command and verify in show command
        1. Run ‘nv set system dns server <dns_server_id_ipv4> and verify command is completed successfully
        2. Run ‘nv set system dns server <dns_server_id_ipv6> and verify command is completed successfully
        3. Check ‘nv show system dns server’ ond validate all configured DNS servers in output
        4. Run ‘nv set system dns server '1.1.1.1'
        5. Run ‘nv set system dns server '2.2.2.2'
        6. Apply config and verify it shows error that max DNS server config is reached
        7. Check ‘nv show system dns server’ ond validate output still shows first two configured IPs

    """
    dns_server_id_ipv4 = SystemConsts.DNS_SERVER_IDS["ipv4"]
    dns_server_id_ipv6 = SystemConsts.DNS_SERVER_IDS["ipv6"]
    system = System()

    try:
        with allure.step('Run set system dns server <server-id> ipv4 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id_ipv4,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server <server-id> ipv6 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id_ipv6,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify all configured DNS servers in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 in dns_output, "The configured DNS server ipv4 is not present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"

        with allure.step('Run set system dns server 1.1.1.1 command'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value="1.1.1.1",
                           apply=False, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server 2.2.2.2 command and verify it shows error that max DNS'
                         'server config is reached'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value="2.2.2.2",
                           apply=True, dut_engine=engines.dut).verify_result(should_succeed=False)

        with allure.step('Verify only the first two configured DNS servers in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 in dns_output, "The configured DNS server ipv4 is not present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_system_dns_server_max_set_unset_single_apply(engines):
    """
    Run set system dns server command and verify in show command
        1. Run ‘nv set system dns server <dns_server_id_ipv4> and verify command is completed successfully
        2. Run ‘nv set system dns server <dns_server_id_ipv6> and verify command is completed successfully
        4. Run ‘nv set system dns server '1.1.1.1' (don't apply config)
        5. Run ‘nv set system dns server '2.2.2.2' (don't apply config)
        5. Run 'nv unset system dns server <dns_server_id_ipv4>
        6. Apply config and verify it does not shows any error that max DNS server config is reached
        7. Check ‘nv show system dns server’ ond validate output still shows all three configured IPs

    """
    dns_server_id_ipv4 = SystemConsts.DNS_SERVER_IDS["ipv4"]
    dns_server_id_ipv6 = SystemConsts.DNS_SERVER_IDS["ipv6"]
    system = System()

    try:
        with allure.step('Run set system dns server <server-id> ipv4 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id_ipv4,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server <server-id> ipv6 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id_ipv6,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify all configured DNS servers in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv4 in dns_output, "The configured DNS server ipv4 is not present in show system dns"
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"

        with allure.step('Run set system dns server 1.1.1.1 command'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value="1.1.1.1",
                           apply=False, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server 2.2.2.2 command'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value="2.2.2.2",
                           apply=False, dut_engine=engines.dut).verify_result()

        with allure.step('Run unset system dns server dns_server_id_ipv4 command and apply config'):
            system.dns.unset(SystemConsts.DNS_SERVER + " " + dns_server_id_ipv4,
                             apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify the configured DNS servers are in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)).\
                get_returned_value()
            assert dns_server_id_ipv6 in dns_output, "The configured DNS server ipv6 is not present in show system dns"
            assert "1.1.1.1" in dns_output, "The configured DNS server 1.1.1.1 is not present in show system dns"
            assert "2.2.2.2" in dns_output, "The configured DNS server ipv6 is not present in show system dns"

    finally:
        clear_system_dns(system, engines)


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_factory_reset_for_static_system_dns(engines, devices, handle_la_marker_in_manufacture):
    """
    Run factory reset system command and verify the system DNS fields are removed from show system dns
        Test flow:
        1. Run ‘nv set system dns server <ip> and verify command is completed successfully
        2. Check ‘nv show system dns server’ ond validate DNS server <ip> in output
        3. Run system factory reset
        4. Run 'nv show system' and verify system dns server fields is removed
    """
    system = System()
    dns_server_id = SystemConsts.DNS_SERVER_IDS["ipv4"]

    try:
        with allure.step('Validate system dns is default (Null)'):
            system_dns_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.dns.show(SystemConsts.DNS_SERVER)).get_returned_value()
            assert system_dns_output == {}, \
                "System contact in system show is {} instead of Null".format(system_dns_output)

        with allure.step('Run set system dns server <server-id> command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify DNS server in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)). \
                get_returned_value()
            assert dns_server_id in dns_output, "The configured DNS server {} is not present in show system dns".\
                format(dns_server_id)

        with allure.step("Run reset factory with keep basic param"):
            res_obj = system.factory_default.action_reset(param="keep basic", operation=devices.dut.reset_factory)
            res_obj.verify_result()

        with allure.step('Validate system dns is back to default (Null)'):
            system_dns_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.dns.show(SystemConsts.DNS_SERVER)).get_returned_value()
            assert system_dns_output == {}, \
                "System DNS in system show is {} instead of Null".format(system_dns_output)

    finally:
        clear_system_dns(system, engines)

        with allure.step("Verify operation time"):
            OperationTime.verify_operation_time(res_obj.duration, devices.dut.reset_factory).verify_result()


@pytest.mark.dns
@pytest.mark.system
@pytest.mark.simx
def test_factory_reset_with_config_save_for_static_system_dns(engines, devices, handle_la_marker_in_manufacture):
    """
    Run factory reset system command and verify the system DNS fields are removed from show system dns
        Test flow:
        1. Run ‘nv set system dns server <ip> and verify command is completed successfully
        2. Check ‘nv show system dns server’ ond validate DNS server <ip> in output
        3. Save config
        4. Run system factory reset
        5. Run 'nv show system' and verify system dns server fields is configured
        6. Run 'nv show config -o commands' and verify system dns commands are shown
    """
    system = System()
    dns_server_id = SystemConsts.DNS_SERVER_IDS["ipv4"]

    try:
        with allure.step('Validate system dns is default (Null)'):
            system_dns_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.dns.show(SystemConsts.DNS_SERVER)).get_returned_value()
            assert system_dns_output == {}, \
                "System contact in system show is {} instead of Null".format(system_dns_output)

        with allure.step('Run set system dns server <server-id> command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=dns_server_id,
                           apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify DNS server in show system dns server output'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)). \
                get_returned_value()
            assert dns_server_id in dns_output, "The configured DNS server {} is not present in show system dns".\
                format(dns_server_id)

        with allure.step('Save config'):
            TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

        with allure.step("Run reset factory with keep basic param"):
            res_obj = system.factory_default.action_reset(param="keep basic", operation=devices.dut.reset_factory)
            res_obj.verify_result()

        with allure.step('Validate system dns config is retained'):
            dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)). \
                get_returned_value()
            assert dns_server_id in dns_output, "The configured DNS server {} is not retained in show system dns".\
                format(dns_server_id)

    finally:
        clear_system_dns(system, engines)

        with allure.step("Verify operation time"):
            OperationTime.verify_operation_time(res_obj.duration, devices.dut.reset_factory).verify_result()


def verify_dns_in_resolv_file(engines, dns_server_id_list, is_present=True):
    is_present_str = ""
    if not is_present:
        is_present_str = "not"
    for dns_server_id in dns_server_id_list:
        with allure.step('Verify in resolv.conf file that it does {} have DNS server {}'.format(is_present_str,
                                                                                                dns_server_id)):
            cmd = 'cat /etc/resolv.conf'
            resolve_file_output = engines.dut.run_cmd(cmd)
            if is_present:
                assert dns_server_id in resolve_file_output, 'DNS {} is not present in resolv.conf'
            else:
                assert dns_server_id not in resolve_file_output, 'DNS {} is present in resolv.conf'.\
                    format(dns_server_id)
