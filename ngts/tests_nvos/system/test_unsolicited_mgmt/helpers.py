import logging
import time
import re

from devts.infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine


from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)
link_logs = "eth0: link becomes ready"


def config_management_interface_verify_logs(engine: ProxySshEngine, mgmt_interface: str, state: str, expected_logs: str):
    """

    :param engine:
    :param mgmt_interface:
    :param state:
    :param expected_logs:
    :return:
    """
    mgmt_port = Port(mgmt_interface)

    with allure.step(f"config {mgmt_interface} state to {state}"):
        mgmt_port.interface.link.state.set(state, apply=True, ask_for_confirmation=True, dut_engine=engine).verify_result()

    time.sleep(20)
    with allure.step("check cable connection note in the logs"):
        logs_output = engine.run_cmd(f'tail -n 400 /var/log/syslog | grep "{expected_logs}"')
        assert logs_output, f"Error: Expected logs not found. {expected_logs}"


def replace_two_ip_addresses(engine: ProxySshEngine):
    """

    :return:
    """
    eth0_port = Port('eth0')
    eth1_port = Port('eth1')

    with allure.step("replace eth0 ip with eth1 ip"):
        with allure.step("get current ip addresses for both mgmt ports"):
            eth0_gateway = next(iter(
                OutputParsingTool.parse_json_str_to_dictionary(eth0_port.interface.ipv4.gateway.show()).verify_result()
            ))
            eth0_ip = next(iter(OutputParsingTool.parse_json_str_to_dictionary(eth0_port.interface.ipv4.address.show()).verify_result()))
            eth1_ip = next(iter(OutputParsingTool.parse_json_str_to_dictionary(eth1_port.interface.ipv4.address.show()).verify_result()))

        with allure.step("set and apply the replacement ips"):
            eth0_port.interface.ipv4.address.unset(op_param=eth0_ip)
            eth1_port.interface.ipv4.address.set(op_param_name=eth0_ip)
            eth1_port.interface.ipv4.address.unset(op_param=eth1_ip)
            eth0_port.interface.ipv4.address.set(op_param_name=eth1_ip)
            eth0_port.interface.ipv4.gateway.set(op_param_name=eth0_gateway)
            eth1_port.interface.ipv4.gateway.set(op_param_name=eth0_gateway)

            NvueGeneralCli.apply_config(engine, ask_for_confirmation=True)

    return eth0_gateway, eth0_ip, eth1_ip


def swap_ips_and_verify_logs_and_packets(engine: ProxySshEngine, expected_messages: list[str], is_enabled: bool, hostname: str):
    """

    :return:
    """
    _, eth0_ip, eth1_ip = replace_two_ip_addresses(engine)
    expected_eth0_ip = eth1_ip.split('/')[0]
    expected_packet_msg = r"ARP, Request who-has.*(%s|%s).*\((Broadcast|ff:ff:ff:ff:ff:ff)\).*" % (
        re.escape(expected_eth0_ip),
        re.escape(hostname),
    )

    expected_msg1 = expected_messages[0].format(eth1_ip.split('/')[0]) if is_enabled else expected_messages[0]
    expected_msg2 = expected_messages[1].format(eth0_ip.split('/')[0]) if is_enabled else expected_messages[1]

    try:
        with allure.step('Verify packets have {} been sent'.format('' if is_enabled else 'not')):
            with allure.independent_step('check tcpdump output'):
                # Increase the timeout here if needed, up to 90 seconds
                output: str = engine.run_cmd('sudo timeout 70 tcpdump -n -i eth0 arp')
                found_expected = bool(re.findall(expected_packet_msg, output))
                assert found_expected == is_enabled, (
                    f"Assertion failed: expected match={is_enabled}, msg: {expected_packet_msg}\n, output: {output}"
                )

            with allure.independent_step('check in logs'):
                logs_output = engine.run_cmd('tail -n 400 /var/log/syslog')
                assert expected_msg1 in logs_output, f"Error: the expected logs {expected_msg1} is missing"
                assert expected_msg2 in logs_output, f"Error: the expected logs {expected_msg2} is missing"

    finally:
        replace_two_ip_addresses(engine)
