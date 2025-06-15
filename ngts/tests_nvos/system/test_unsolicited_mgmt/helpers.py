import logging
import re
import time

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.DutUtilsTool import wait_for_specific_regex_in_logs
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli

link_logs = "eth0: link becomes ready"


def config_management_interface_verify_logs(engine, mgmt_interface, state, expected_logs):
    """

    :param engine:
    :param mgmt_interface:
    :param state:
    :param expected_logs:
    :return:
    """
    mgmt_port = Port(mgmt_interface)

    with allure.step(f"config {mgmt_interface} state to {state}"):
        mgmt_port.interface.link.state.set(state, apply=True, ask_for_confirmation=True).verify_result()

    time.sleep(20)
    with allure.step("check cable connection note in the logs"):
        logs_output = engine.run_cmd(f'tail -n 400 /var/log/syslog | grep "{expected_logs}"')
        assert logs_output, f"Error: Expected logs not found. {expected_logs}"


def replace_two_ip_addresses(engine):
    """

    :return:
    """
    eth0_port = Port('eth0')
    eth1_port = Port('eth1')

    with allure.step("replace eth0 ip with eth1 ip"):
        with allure.step("get current ip addresses for both mgmt ports"):
            eth0_gateway = next(iter(OutputParsingTool.parse_json_str_to_dictionary(eth0_port.interface.ip.gateway.show()).verify_result()))
            eth0_ip = next(iter(OutputParsingTool.parse_json_str_to_dictionary(eth0_port.interface.ip.address.show()).verify_result()))
            eth1_ip = next(iter(OutputParsingTool.parse_json_str_to_dictionary(eth1_port.interface.ip.address.show()).verify_result()))

        with allure.step("set and apply the replacement ips"):
            eth0_port.interface.ip.address.unset(op_param=eth0_ip)
            eth1_port.interface.ip.address.set(op_param_name=eth0_ip)
            eth1_port.interface.ip.address.unset(op_param=eth1_ip)
            eth0_port.interface.ip.address.set(op_param_name=eth1_ip)
            eth0_port.interface.ip.gateway.set(op_param_name=eth0_gateway)
            eth1_port.interface.ip.gateway.set(op_param_name=eth0_gateway)

            NvueGeneralCli.apply_config(engine, ask_for_confirmation=True)

        with allure.step("sleep 3 second"):
            time.sleep(3)

    return eth0_gateway, eth0_ip, eth1_ip


def swap_ips_and_verify_logs_and_packets(engine, expected_messages, is_enabled, hostname):
    """

    :return:
    """
    expected_packet_msg = f"ARP, Request who-has.*{hostname}.*\\(Broadcast\\).*"
    eth0_gateway, eth0_ip, eth1_ip = replace_two_ip_addresses(engine)

    expected_msg1 = expected_messages[0].format(eth1_ip.split('/')[0]) if is_enabled else expected_messages[0]
    expected_msg2 = expected_messages[1].format(eth0_ip.split('/')[0]) if is_enabled else expected_messages[1]

    try:
        with allure.step('Verify packets have {} been sent'.format('' if is_enabled else 'not')):
            with allure.independent_step('check tcpdump output'):
                output = engine.run_cmd('sudo timeout 30 tcpdump -i eth0 arp')
                matches = re.findall(expected_packet_msg, output)
                assert bool(matches) == is_enabled, f"Assertion failed for expected packet msg: ARP, Request who-has ... (Broadcast)\n, output: {output}\n, param: {is_enabled}"

            with allure.independent_step('check in logs'):
                logs_output = engine.run_cmd(f'tail -n 400 /var/log/syslog')
                assert expected_msg1 in logs_output, f"Error: the expected logs {expected_msg1} is missing"
                assert expected_msg2 in logs_output, f"Error: the expected logs {expected_msg2} is missing"

    finally:
        replace_two_ip_addresses(engine)
