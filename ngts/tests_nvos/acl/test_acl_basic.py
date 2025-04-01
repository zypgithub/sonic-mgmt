import logging
import pytest
from retry import retry

from retry.api import retry_call
import random
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType, AclConsts, OutputFormat, IpConsts
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from scapy.layers.inet import IP, TCP, ICMP
from scapy.layers.inet6 import IPv6, ICMPv6EchoRequest
from scapy.all import *
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from multiprocessing import Process

logger = logging.getLogger()

SLEEP_TIME = 15
IPV6_ADDR = "2001:db8:abcd:0012:0000:0000:0000:00ef"
RULE_CONFIG_FUNCTION = {
    AclConsts.ACTION: lambda rule_id_obj, param: rule_id_obj.action.set(param),
    AclConsts.ACTION_LOG_PREFIX: lambda rule_id_obj, param: rule_id_obj.action.log.set_log_prefix(param),
    AclConsts.REMARK: lambda rule_id_obj, param: rule_id_obj.set_remark(param),

    AclConsts.TCP_SOURCE_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.source_port.set(param),
    AclConsts.UDP_SOURCE_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.udp.source_port.set(param),
    AclConsts.TCP_DEST_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.dest_port.set(param),
    AclConsts.UDP_DEST_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.udp.dest_port.set(param),
    AclConsts.FRAGMENT: lambda rule_id_obj, param: rule_id_obj.match.ip.set_fragment(),
    AclConsts.ECN_FLAGS: lambda rule_id_obj, param: rule_id_obj.match.ip.ecn.flags.set(param),
    AclConsts.ECN_IP_ECT: lambda rule_id_obj, param: rule_id_obj.match.ip.ecn.set_ecn_ip_ect(param),
    AclConsts.TCP_FLAGS: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.flags.set(param),
    AclConsts.TCP_MASK: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.mask.set(param),
    AclConsts.TCP_STATE: lambda rule_id_obj, param: rule_id_obj.match.ip.state.set(param),
    AclConsts.MSS: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.set_mss(param),
    AclConsts.ALL_MSS_EXCEPT: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.set_all_mss_except(param),
    AclConsts.SOURCE_IP: lambda rule_id_obj, param: rule_id_obj.match.ip.set_source_ip(param),
    AclConsts.DEST_IP: lambda rule_id_obj, param: rule_id_obj.match.ip.set_dest_ip(param),
    AclConsts.ICMP_TYPE: lambda rule_id_obj, param: rule_id_obj.match.ip.set_icmp_type(param),
    AclConsts.ICMPV6_TYPE: lambda rule_id_obj, param: rule_id_obj.match.ip.set_icmpv6_type(param),
    AclConsts.IP_PROTOCOL: lambda rule_id_obj, param: rule_id_obj.match.ip.set_protocol(param),
    AclConsts.RECENT_LIST_NAME: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.set_name(param),
    AclConsts.RECENT_LIST_UPDATE: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.see_interval(param),
    AclConsts.RECENT_LIST_HIT: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.set_hit_count(param),
    AclConsts.RECENT_LIST_ACTION: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.set_action(param),
    AclConsts.DSCP_SET_ACTION: lambda rule_id_obj, param: rule_id_obj.action.dscp.set(param),
    AclConsts.HASHLIMIT_NAME: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_name(param),
    AclConsts.HASHLIMIT_RATE: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_rate_limit(param),
    AclConsts.HASHLIMIT_BURST: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_burst(param),
    AclConsts.HASHLIMIT_MODE: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_mode(param),
    AclConsts.HASHLIMIT_EXPIRE: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_expire(param),
    AclConsts.HASHLIMIT_DEST_MASK: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_destination_mask(param),
    AclConsts.HASHLIMIT_SRC_MASK: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_source_mask(param),

    AclConsts.SOURCE_MAC: None,
    AclConsts.SOURCE_MAC_MASK: None,
    AclConsts.DEST_MAC: None,
    AclConsts.DEST_MAC_MASK: None,
    AclConsts.MAC_PROTOCOL: None
}


def test_can_ping_from_eth1(engines, devices):
    """
    This test is a workaround for the issue that some switches fail to ping the sonic_mgmt ip through eth1.
    It should run before all other ACL tests because some of them depend on using eth1.
    The test attempts to ping. On failure it runs a shell command that fixes the issue, allowing future tests to run
    smoothly, but this test will still fail to let us know the issue still exists.
    """
    if 'eth1' not in devices.dut.mgmt_ports:
        pytest.skip("Device does not have eth1 mgmt-port")

    try:
        ping_from_switch(engines.dut, engines.sonic_mgmt.ip, "eth1").verify_result()
        logger.info("Successfully pinged sonic-mgmt through eth1")
    except Exception:
        logger.error(f"Could not ping sonic-mgmt through eth1. Fixing...")
        gateway = Port("eth0").interface.ip.gateway.show(output_format=OutputFormat.auto).splitlines()[-1].strip()
        devices.dut.run_cmd(f"sudo ip route add {engines.sonic_mgmt.ip} via {gateway} dev eth1")
        raise


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_acls(engines, test_api):
    TestToolkit.tested_api = test_api

    with allure.step("Show ACL and verify the output"):
        acl = Acl()
        acls = OutputParsingTool.parse_show_output_to_dict(acl.show()).get_returned_value()
        assert acls and len(acls.keys()) > 1, "No ACLs were found"

        with allure.step("Verify all default ACL are found"):
            ValidationTool.verify_field_exist_in_json_output(acls, AclConsts.DEFAULT_ACLS).verify_result()

        with allure.step("Verify expected ACL fields"):
            ValidationTool.verify_field_exist_in_json_output(acls[AclConsts.DEFAULT_ACLS[0]],
                                                             [AclConsts.RULE, AclConsts.TYPE])


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_rules_order(devices, engines, test_api, topology_obj):
    """
    Validate acl rules order by priority of rules order.
    the first rule that match the packet should apply even if the next rule also match but the action is different.
    steps:
    1. config an ACL with 2 rules
    2. send packet
    3. validate that the action we do on the packet is as the first rule.
    """
    TestToolkit.tested_api = test_api
    with allure.step("Define ACL with 2 rules"):

        with allure.step("Define ACL"):
            acl = Acl()
            acl_id = "AA_TEST_ACL1"
            acl.set(acl_id).verify_result()
            acl_id_obj = acl.acl_id[acl_id]
            acl_id_obj.set(AclConsts.TYPE, 'ipv4').verify_result()
            expected_acl_dict = {acl_id: {AclConsts.RULE: {}, AclConsts.TYPE: 'ipv4'}}

        with allure.step("Config 2 rules"):
            rule_dict = {AclConsts.ACTION: AclConsts.DENY, AclConsts.SOURCE_IP: 'ANY', AclConsts.IP_PROTOCOL: 'icmp',
                         AclConsts.ICMP_TYPE: 'echo-request'}
            rule_id_1 = '1'
            config_rule(engines.dut, acl_id_obj, rule_id_1, rule_dict)
            rule_id_2 = '2'
            rule_dict[AclConsts.ACTION] = AclConsts.PERMIT
            config_rule(engines.dut, acl_id_obj, rule_id_2, rule_dict)

            expected_acl_dict[acl_id][AclConsts.RULE].update({
                rule_id_1: {
                    AclConsts.ACTION: {AclConsts.DENY: {}},
                    AclConsts.MATCH: {
                        AclConsts.IP: {
                            AclConsts.SOURCE_IP: 'ANY',
                            AclConsts.PROTOCOL: 'icmp',
                            AclConsts.ICMP_TYPE: 'echo-request'
                        },
                    }
                }
            })

            expected_acl_dict[acl_id][AclConsts.RULE].update({
                rule_id_2: {
                    AclConsts.ACTION: {AclConsts.PERMIT: {}},
                    AclConsts.MATCH: {
                        AclConsts.IP: {
                            AclConsts.SOURCE_IP: 'ANY',
                            AclConsts.PROTOCOL: 'icmp',
                            AclConsts.ICMP_TYPE: 'echo-request'
                        },
                    }
                }
            })

        with allure.step("Validate configuration with show commands"):
            acl_id_output = acl_id_obj.parse_show()
            ValidationTool.compare_dictionaries(expected_acl_dict[acl_id], acl_id_output).verify_result()

    with allure.step("Attach ACL to mgmt interface"):
        mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
        mgmt_port = Port(mgmt_port_name)
        mgmt_port.interface.acl.set(acl_id).verify_result()
        mgmt_port.interface.acl.acl_id[acl_id].inbound.set(AclConsts.CONTROL_PLANE, apply=True)
        sleep()

        with allure.step("Validate configuration with show commands"):
            interface_acl_output = mgmt_port.interface.acl.acl_id[acl_id].parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE].keys() == interface_acl_output[AclConsts.STATISTICS].keys(), \
                f'Got unexpected mgmt interface acl output after mgmt configuration\n' \
                f'expected: {expected_acl_dict[acl_id][AclConsts.RULE].keys()}\n' \
                f'but got: {interface_acl_output[AclConsts.STATISTICS].keys()}'

    with allure.step("Validate rule order"):
        rule_packets_before = get_rule_packets(mgmt_port, acl_id)
        ping_packet = ping_from_sonic_mgmt(engines.dut.ip)
        rule_packets_after = get_rule_packets(mgmt_port, acl_id)
        assert rule_packets_after[rule_id_1] > rule_packets_before[rule_id_1], \
            f'we expect to see increase in rule id {rule_id_1} counter - cause the first rule should be applied'
        assert rule_packets_after[rule_id_2] == rule_packets_before[rule_id_2], \
            f'we expect to see that the counter of rule id {rule_id_2} will not change - cause the first rule should be applied and not the second'

    with allure.step("Remove the first rule"):
        acl_id_obj.rule.rule_id[rule_id_1].unset(apply=True)
        expected_acl_dict[acl_id][AclConsts.RULE].pop(rule_id_1)
        sleep()
        acl_id_output = acl_id_obj.parse_show()
        assert expected_acl_dict[acl_id] == acl_id_output, f'Got unexpected acl output after removing 1 rule\n' \
            f'expected: {expected_acl_dict[acl_id]}\nbut got: {acl_id_output}'
        interface_acl_output = mgmt_port.interface.acl.acl_id[acl_id].parse_show()
        assert expected_acl_dict[acl_id][AclConsts.RULE].keys() == interface_acl_output[AclConsts.STATISTICS].keys(), \
            f'Got unexpected mgmt interface acl output after removing 1 rule\n' \
            f'expected: {expected_acl_dict[acl_id][AclConsts.RULE].keys()}\n' \
            f'but got: {interface_acl_output[AclConsts.STATISTICS].keys()}'

    with allure.step("Validate rule order"):
        rule_packets_before = get_rule_packets(mgmt_port, acl_id)
        ping_from_sonic_mgmt(ping_packet)
        rule_packets_after = get_rule_packets(mgmt_port, acl_id)
        assert rule_packets_after[rule_id_2] > rule_packets_before[rule_id_2], \
            f'we expect to see that the counter of rule id {rule_id_2} will not change - cause the first rule should be applied and not the second'


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_order(engines, test_api, topology_obj):
    """
    Validate ACLs rules order by priority of ACL order.
    the first rule in the first acl that match the packet should applied.
    steps:
    1. config 2 ACLs with a rule
    2. send packet
    3. validate that the action we do on the packet is as the first ACL rule.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Define ACLs with rule"):
        acl_type = 'ipv4'
        mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
        mgmt_port = Port(mgmt_port_name)
        sonic_mgmt_ip = engines.sonic_mgmt.ip
        rule_id = '1'
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.DENY, AclConsts.SOURCE_IP: sonic_mgmt_ip,
                                   AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'}

        acl_id_1 = "AA_TEST_ACL_1"
        acl_id_1_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id_1, acl_type, rule_id,
                                                                  rule_configuration_dict, mgmt_port, AclConsts.INBOUND, AclConsts.CONTROL_PLANE)

        acl_id_2 = "AA_TEST_ACL_2"
        sonic_mgmt_prefix_or_netmask = sonic_mgmt_ip + random.choice(['/255.255.255.0', '/32'])
        rule_conf_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.SOURCE_IP: sonic_mgmt_prefix_or_netmask,
                          AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'}
        acl_id_2_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id_2, acl_type, rule_id, rule_conf_dict,
                                                                  mgmt_port, AclConsts.INBOUND, AclConsts.CONTROL_PLANE)

    with allure.step("Validate configuration with show commands"):
        interface_acl_1_output = mgmt_port.interface.acl.acl_id[acl_id_1].parse_show()
        interface_acl_2_output = mgmt_port.interface.acl.acl_id[acl_id_2].parse_show()
        assert interface_acl_1_output[AclConsts.STATISTICS].keys() == interface_acl_2_output[AclConsts.STATISTICS].keys(), \
            f'Got unexpected mgmt interface acl output after mgmt configuration'

    with allure.step("Validate ACL rule order"):
        rule_packets_1_before = get_rule_packets(mgmt_port, acl_id_1)
        rule_packets_2_before = get_rule_packets(mgmt_port, acl_id_2)
        ping_packet = ping_from_sonic_mgmt(dst=engines.dut.ip, src=sonic_mgmt_ip)
        rule_packets_1_after = get_rule_packets(mgmt_port, acl_id_1)
        rule_packets_2_after = get_rule_packets(mgmt_port, acl_id_2)
        assert rule_packets_1_after[rule_id] > rule_packets_1_before[rule_id], \
            f'we expect to see increase in acl {acl_id_1} rule id {rule_id} counter - cause the first acl should be applied'
        assert rule_packets_2_after[rule_id] == rule_packets_2_before[rule_id], \
            f'we expect to see that the counter of acl {acl_id_2} rule id {rule_id} will not change - cause the first acl should be applied and not the second'

    with allure.step("Remove the first rule"):
        mgmt_port.interface.acl.unset(acl_id_1).verify_result()
        acl_id_1_obj.unset(apply=True)
        acl_output = Acl().parse_show()
        assert acl_id_1 not in acl_output.keys(), 'Got unexpected acl output after acl removal'
        interface_acl_output = mgmt_port.interface.acl.parse_show()
        assert acl_id_1 not in interface_acl_output.keys(), 'Got unexpected mgmt interface acl output after acl removal'

    with allure.step("Validate new ACL rule order"):
        rule_packets_before = get_rule_packets(mgmt_port, acl_id_2)
        send(ping_packet)
        rule_packets_after = get_rule_packets(mgmt_port, acl_id_2)
        assert rule_packets_after[rule_id] > rule_packets_before[rule_id], \
            f'we expect to see increase in acl {acl_id_2} rule id {rule_id} counter - cause the first acl has removed'


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_ipv6(engines, test_api, topology_obj, sonic_mgmt_ipv6_addr):
    """
    Validate ACLs rules over ipv6.
    steps:
    1. config ACL with a rule
    2. send packet
    3. validate counters increase
    """
    TestToolkit.tested_api = test_api
    if not IpTool.is_dhcp_client6_has_lease(engines.dut):
        pytest.skip("DUT DHCP client6 has no lease; cannot run this IPv6 test.")

    with allure.step("Define ACLs with rule"):
        acl_type = 'ipv6'
        mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
        mgmt_port = Port(mgmt_port_name)
        ipv6_prefix_or_netmask = sonic_mgmt_ipv6_addr + '/64'
        rule_id = '1'
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.DENY, AclConsts.SOURCE_IP: sonic_mgmt_ipv6_addr}

        acl_id_1 = "AA_TEST_ACL_IPV6"
        acl_id_1_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id_1, acl_type, rule_id,
                                                                  rule_configuration_dict, mgmt_port, AclConsts.INBOUND, AclConsts.CONTROL_PLANE)

        switch_ipv6_addr = mgmt_port.interface.get_ipv6_address()

    with allure.step("Validate ACL counters"):
        time.sleep(5)
        rule_packets_1_before = get_rule_packets(mgmt_port, acl_id_1)
        with allure.step("Ping"):
            ping_packet = IPv6(dst=switch_ipv6_addr, src=sonic_mgmt_ipv6_addr) / ICMPv6EchoRequest()
            send(ping_packet)
        rule_packets_1_after = get_rule_packets(mgmt_port, acl_id_1)
        assert rule_packets_1_after[rule_id] > rule_packets_1_before[rule_id], \
            f'we expect to see increase in acl {acl_id_1} rule id {rule_id} counter'

    with allure.step("Change the rule- use ipv6 prefix"):
        config_rule(engines.dut, acl_id_1_obj, rule_id,
                    {AclConsts.ACTION: AclConsts.DENY, AclConsts.SOURCE_IP: ipv6_prefix_or_netmask})
        time.sleep(5)
        rule_packets_1_before = get_rule_packets(mgmt_port, acl_id_1)
        ping_packet = IPv6(dst=switch_ipv6_addr, src=sonic_mgmt_ipv6_addr) / ICMPv6EchoRequest()
        send(ping_packet)
        rule_packets_1_after = get_rule_packets(mgmt_port, acl_id_1)
        assert rule_packets_1_after[rule_id] > rule_packets_1_before[rule_id], \
            f'we expect to see increase in acl {acl_id_1} rule id {rule_id} counter'


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_loopback(engines, test_api):
    """
    Validate ACLs rules can't be defined for the loopback connection
    steps:
    1. config ACL with a rule
    2. try to apply, and fail
    """
    TestToolkit.tested_api = test_api

    with allure.step("Define ACLs with rule"):
        acl_type = 'ipv4'
        mgmt_port = Port('lo')
        sonic_mgmt_ip = engines.sonic_mgmt.ip
        rule_id = '1'
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT}

        acl_id_1 = "AA_TEST_ACL_LOOPBACK"
        acl_id_1_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id_1, acl_type, rule_id,
                                                                  rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                  AclConsts.CONTROL_PLANE, should_succeed=False)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_acl_commands(devices, engines, test_api, topology_obj):
    """
    Validate acl show commands.
    steps:
    1. config an ACL with rules
    2. validate show commands
    """
    TestToolkit.tested_api = test_api
    with allure.step("Define ACL with rules"):

        with allure.step("Define ACL"):
            acl = Acl()
            acl_id = "AA_TEST_ACL1"
            acl.set(acl_id).verify_result()
            acl_id_obj = acl.acl_id[acl_id]
            acl_id_obj.set(AclConsts.TYPE, 'ipv4').verify_result()
            expected_acl_dict = {acl_id: {AclConsts.RULE: {}, AclConsts.TYPE: 'ipv4'}}

        with allure.step("Config 3 rules"):
            rule_id_1 = '1'
            config_rule(engines.dut, acl_id_obj, rule_id_1, {AclConsts.ACTION: AclConsts.DENY, AclConsts.REMARK: "description", AclConsts.SOURCE_IP: 'ANY',
                                                             AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'})
            expected_acl_dict[acl_id][AclConsts.RULE].update({
                rule_id_1: {
                    AclConsts.ACTION: {AclConsts.DENY: {}},
                    AclConsts.REMARK: "description",
                    AclConsts.MATCH: {
                        AclConsts.IP: {
                            AclConsts.SOURCE_IP: 'ANY',
                            AclConsts.PROTOCOL: 'icmp',
                            AclConsts.ICMP_TYPE: 'echo-request',
                        },
                    },
                }
            })
            rule_id_2 = '2'
            config_rule(engines.dut, acl_id_obj, rule_id_2, {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.IP_PROTOCOL: 'tcp',
                                                             AclConsts.TCP_DEST_PORT: 'snmp', AclConsts.ECN_FLAGS: 'tcp-ece', AclConsts.ECN_IP_ECT: 2})
            expected_acl_dict[acl_id][AclConsts.RULE].update({
                rule_id_2: {
                    AclConsts.ACTION: {AclConsts.PERMIT: {}},
                    AclConsts.MATCH: {
                        AclConsts.IP: {
                            AclConsts.PROTOCOL: 'tcp',
                            'tcp': {
                                'dest-port': {
                                    'snmp': {},
                                },
                            },
                            'ecn': {
                                AclConsts.FLAGS: {
                                    'tcp-ece': {},
                                },
                                AclConsts.IP_ECT: 2,
                            },
                        },
                    },
                }
            })
            rule_id_3 = '3'
            config_rule(engines.dut, acl_id_obj, rule_id_3,
                        {AclConsts.ACTION: AclConsts.LOG, AclConsts.IP_PROTOCOL: 'tcp', AclConsts.TCP_FLAGS: 'syn', AclConsts.TCP_MASK: 'syn'})
            expected_acl_dict[acl_id][AclConsts.RULE].update({
                rule_id_3: {
                    AclConsts.ACTION: {AclConsts.LOG: {}},
                    AclConsts.MATCH: {
                        AclConsts.IP: {
                            AclConsts.PROTOCOL: 'tcp',
                            'tcp': {
                                AclConsts.FLAGS: {
                                    'syn': {},
                                },
                                AclConsts.MASK: {
                                    'syn': {},
                                },
                            },
                        },
                    },
                }
            })

        with allure.step("Validate configuration with show commands"):
            rule_id_1_obj = acl_id_obj.rule.rule_id[rule_id_1]
            acl_id_output = acl_id_obj.parse_show()
            ValidationTool.compare_dictionaries(expected_acl_dict[acl_id], acl_id_output).verify_result()

            rule_output = acl_id_obj.rule.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE] == rule_output

            rule_id_1_output = rule_id_1_obj.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_1] == rule_id_1_output

            action_show = rule_id_1_obj.action.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_1][AclConsts.ACTION] == action_show  # bug 3659032

            match_show = rule_id_1_obj.match.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_1][AclConsts.MATCH] == match_show

            match_ip_show = rule_id_1_obj.match.ip.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_1][AclConsts.MATCH][AclConsts.IP] == match_ip_show

            dest_port_show = acl_id_obj.rule.rule_id[rule_id_2].match.ip.tcp.dest_port.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_2][AclConsts.MATCH][AclConsts.IP]['tcp']['dest-port'] == dest_port_show

            tcp_show = acl_id_obj.rule.rule_id[rule_id_3].match.ip.tcp.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_3][AclConsts.MATCH][AclConsts.IP]['tcp'] == tcp_show

            tcp_flags_show = acl_id_obj.rule.rule_id[rule_id_3].match.ip.tcp.flags.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_3][AclConsts.MATCH][AclConsts.IP]['tcp'][AclConsts.FLAGS] == tcp_flags_show

            tcp_mask_show = acl_id_obj.rule.rule_id[rule_id_3].match.ip.tcp.mask.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_3][AclConsts.MATCH][AclConsts.IP]['tcp'][AclConsts.MASK] == tcp_mask_show

            ecn_show = acl_id_obj.rule.rule_id[rule_id_2].match.ip.ecn.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_2][AclConsts.MATCH][AclConsts.IP]['ecn'] == ecn_show

            ecn_flags_show = acl_id_obj.rule.rule_id[rule_id_2].match.ip.ecn.flags.parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE][rule_id_2][AclConsts.MATCH][AclConsts.IP]['ecn'][AclConsts.FLAGS] == ecn_flags_show

    with allure.step("Define ACL to mgmt interface"):
        mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
        mgmt_port = Port(mgmt_port_name)
        mgmt_port.interface.acl.set(acl_id).verify_result()
        mgmt_port.interface.acl.acl_id[acl_id].inbound.set(AclConsts.CONTROL_PLANE, apply=True).verify_result()
        wait_till_acl_applied(mgmt_port, acl_id)

        with allure.step("Validate configuration with show commands"):
            interface_acls_output = mgmt_port.interface.acl.parse_show()
            assert acl_id_output[AclConsts.RULE].keys() == interface_acls_output[acl_id][AclConsts.STATISTICS].keys()

            interface_acl_output = mgmt_port.interface.acl.acl_id[acl_id].parse_show()
            assert rule_output.keys() == interface_acl_output[AclConsts.STATISTICS].keys()

            statistics_output = mgmt_port.interface.acl.acl_id[acl_id].statistics.parse_show()
            assert rule_output.keys() == statistics_output.keys()

            rule_statistics_output = mgmt_port.interface.acl.acl_id[acl_id].statistics.parse_show(rule_id_1)
            assert statistics_output[rule_id_1].keys() == rule_statistics_output.keys()

            inbound_output = mgmt_port.interface.acl.acl_id[acl_id].inbound.parse_show(AclConsts.CONTROL_PLANE)
            assert rule_output.keys() == inbound_output[AclConsts.STATISTICS].keys()


@retry(Exception, tries=5, delay=3)
def wait_till_acl_applied(mgmt_port, acl_id):
    interface_acls_output = mgmt_port.interface.acl.parse_show()
    assert acl_id in interface_acls_output.keys(), f"{acl_id} not found"


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_inbound_outbound_counters(engines, test_api, topology_obj):
    """
    Validate inbound outbound counters.
    rule match ip dest-ip - should increase outbound counters only
    rule match ip source-ip - should increase inbound counters only
    steps:
    1. config inbound and outbound ACLs with match dest-ip rule
    2. validate outbound counters increased only
    3. config inbound and outbound ACLs with match source-ip rule
    4. validate inbound counters increased only
    5. unset source-ip rule from inbound acl
    6. validate outbound counters are still 0
    """
    TestToolkit.tested_api = test_api
    with allure.step("Choosing randomly whether or not to use control-plane parameter"):
        control_plane = random.choice([AclConsts.CONTROL_PLANE, ""])
        allure.orig_allure.attach(f"{control_plane=}", "control_plane_value", allure.orig_allure.attachment_type.TEXT)

    with allure.step("Config inbound and outbound ACLs with match dest-ip rule"):
        acl_type = 'ipv4'
        mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
        mgmt_port = Port(mgmt_port_name)
        sonic_mgmt_ip = engines.sonic_mgmt.ip
        logger.info(f"{mgmt_port_name=}, {sonic_mgmt_ip=}, {control_plane=}")

        rule_id_match_dest_ip = '1'
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.DEST_IP: sonic_mgmt_ip,
                                   AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'}

        acl_id_inbound_match_dest_ip = "AA_TEST_A_ACL_INBOUND_MATCH_DEST_IP"
        acl_obj_inbound_match_dest_ip = config_acl_with_rule_attached_to_interface(engines.dut, acl_id_inbound_match_dest_ip,
                                                                                   acl_type, rule_id_match_dest_ip,
                                                                                   rule_configuration_dict, mgmt_port,
                                                                                   AclConsts.INBOUND, control_plane)

        acl_id_outbound_match_dest_ip = "AA_TEST_B_ACL_OUTBOUND_MATCH_DEST_IP"
        acl_obj_outbound_match_dest_ip = config_acl_with_rule_attached_to_interface(engines.dut, acl_id_outbound_match_dest_ip,
                                                                                    acl_type, rule_id_match_dest_ip,
                                                                                    rule_configuration_dict, mgmt_port,
                                                                                    AclConsts.OUTBOUND, control_plane)

    with allure.step("Validate outbound counters increased only"):
        sleep()
        rule_packets_1_before = get_rule_packets(mgmt_port, acl_id_inbound_match_dest_ip, rule_id_match_dest_ip, rule_direction=AclConsts.INBOUND)
        rule_packets_2_before = get_rule_packets(mgmt_port, acl_id_outbound_match_dest_ip, rule_id_match_dest_ip, rule_direction=AclConsts.OUTBOUND)
        ping_from_switch(engines.dut, sonic_mgmt_ip, mgmt_port_name).verify_result()
        rule_packets_1_after = get_rule_packets(mgmt_port, acl_id_inbound_match_dest_ip, rule_id_match_dest_ip, rule_direction=AclConsts.INBOUND)
        rule_packets_2_after = get_rule_packets(mgmt_port, acl_id_outbound_match_dest_ip, rule_id_match_dest_ip, rule_direction=AclConsts.OUTBOUND)
        assert rule_packets_1_after[rule_id_match_dest_ip] == rule_packets_1_before[rule_id_match_dest_ip], \
            f'The inbound counters of acl {acl_id_inbound_match_dest_ip} rule id {rule_id_match_dest_ip} should be the same cause the rule is matching' \
            f' packets with specific dest ip but it attached to the inbound control plan and not to the outbound.'
        assert rule_packets_2_after[rule_id_match_dest_ip] > rule_packets_2_before[rule_id_match_dest_ip], \
            f'we expect to see increase in acl {acl_id_outbound_match_dest_ip} rule id {rule_id_match_dest_ip} counter after the ping'

    with allure.step("Config inbound and outbound ACLs with match source-ip rule"):
        rule_id_match_src_ip = '2'
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.SOURCE_IP: sonic_mgmt_ip,
                                   AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'}
        config_rule(engines.dut, acl_obj_inbound_match_dest_ip, rule_id_match_src_ip, rule_configuration_dict)
        config_rule(engines.dut, acl_obj_outbound_match_dest_ip, rule_id_match_src_ip, rule_configuration_dict)

    with allure.step("Validate inbound counters increased only"):
        rule_packets_1_before = get_rule_packets(mgmt_port, acl_id_inbound_match_dest_ip, rule_id_match_src_ip,
                                                 rule_direction=AclConsts.INBOUND)
        rule_packets_2_before = get_rule_packets(mgmt_port, acl_id_outbound_match_dest_ip, rule_id_match_src_ip,
                                                 rule_direction=AclConsts.OUTBOUND)
        ping_from_sonic_mgmt(dst=engines.dut.ip, src=sonic_mgmt_ip)
        rule_packets_1_after = get_rule_packets(mgmt_port, acl_id_inbound_match_dest_ip, rule_id_match_src_ip,
                                                rule_direction=AclConsts.INBOUND)
        rule_packets_2_after = get_rule_packets(mgmt_port, acl_id_outbound_match_dest_ip, rule_id_match_src_ip,
                                                rule_direction=AclConsts.OUTBOUND)
        assert rule_packets_1_after[rule_id_match_src_ip] > rule_packets_1_before[rule_id_match_src_ip], \
            f'we expect to see increase in acl {acl_id_inbound_match_dest_ip} rule id {rule_id_match_src_ip} counter after the ping'
        assert rule_packets_2_after[rule_id_match_src_ip] == rule_packets_2_before[rule_id_match_src_ip], \
            f'The outbound counters of acl {acl_id_outbound_match_dest_ip} rule id {rule_id_match_src_ip} should be the same cause the rule is matching' \
            f' packets with specific dest ip but it attached to the inbound control plan and not to the outbound.'
        assert rule_packets_2_after[rule_id_match_src_ip] == 0

    with allure.step("Unset source-ip rule from inbound acl"):
        acl_obj_inbound_match_dest_ip.rule.rule_id[rule_id_match_src_ip].unset(apply=True)
        sleep()

    with allure.step("Validate outbound counters are still 0"):
        ping_from_sonic_mgmt(dst=engines.dut.ip, src=sonic_mgmt_ip)
        rule_packets_2_after = get_rule_packets(mgmt_port, acl_id_outbound_match_dest_ip, rule_id_match_src_ip,
                                                rule_direction=AclConsts.OUTBOUND)
        assert rule_packets_2_after[rule_id_match_src_ip] == 0, \
            f'we expect to see increase in acl {acl_id_outbound_match_dest_ip} rule id {rule_id_match_src_ip} counter after the ping'


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_dest_ip(engines, test_api, topology_obj, sonic_mgmt_ipv6_addr):
    """
    Validate ACL match dest-ip rules.
    steps:
    For each ip-string in the list:
        - Define ACL rule for ip, with the lowest rule-ID so it has the highest priority
        - Attach rule to the interface
        - Send packet over interface
        - Assert the rule statistics have increased
    """
    TestToolkit.tested_api = test_api
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    with allure.step("ACL type ipv4 test"):
        ipv4_addr = engines.sonic_mgmt.ip
        dest_ip_list = [ipv4_addr, ipv4_addr + '/32', ipv4_addr + '/255.255.255.0']
        dest_ip_test(engines, mgmt_port, 'ipv4', "AA_TEST_ACL_IPV4", dest_ip_list, ipv4_addr)

    if IpTool.is_dhcp_client6_has_lease(engines.dut):
        with allure.step("ACL type ipv6 test"):
            dest_ip_list = [sonic_mgmt_ipv6_addr, sonic_mgmt_ipv6_addr + '/64']
            dest_ip_test(engines, mgmt_port, 'ipv6', "AA_TEST_ACL_IPV6", dest_ip_list, sonic_mgmt_ipv6_addr)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_source_port(engines, test_api, topology_obj):
    """
    Validate ACL match source port rules.
    steps:
    1. config ACL with a match source port rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    src_port_list = ['ANY', 'ssh', 1244]
    match_ip_port_test(engines, mgmt_port, 'ipv4', 'AA_TEST_ACL_SOURCE_PORT', src_port_list, engines.dut.ip, AclConsts.TCP_SOURCE_PORT, engines.sonic_mgmt)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_dest_port(engines, test_api, topology_obj):
    """
    Validate ACL match dest port rules.
    steps:
    1. config ACL with a match dest port rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_port_list = ['ANY', 'ssh', 1244]
    match_ip_port_test(engines, mgmt_port, 'ipv4', 'AA_TEST_ACL_DEST_PORT', dest_port_list, engines.sonic_mgmt.ip, AclConsts.TCP_DEST_PORT, engines.dut)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_protocol(engines, test_api, topology_obj):
    """
    Validate ACL match protocol rules.
    steps:
    1. config ACL with a match protocol rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_PROTOCOL"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    protocol_packet_dict = {'tcp': f"IP(dst=\"{dest_addr}\") / TCP()",
                            'udp': f"IP(dst=\"{dest_addr}\") / UDP()",
                            'icmp': f"IP(dst=\"{dest_addr}\") / ICMP()"}
    rule_id = str(len(protocol_packet_dict))
    acl_obj = None

    with allure.step("Testing protocols"):
        for protocol, packet in protocol_packet_dict.items():
            with allure.independent_step(f"{protocol=}"):
                rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.IP_PROTOCOL: protocol}
                acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                                     rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                     AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
                time.sleep(5)
                validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                                packet=packet)
                rule_id = str(int(rule_id) - 1)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_fragment(engines, test_api, topology_obj):
    """
    Validate ACL match fragment rules.
    steps:
    1. config ACL with a match fragment rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_FRAGMENT"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    packet = f"IP(dst=\"{dest_addr}\") /  ICMP() / (\"X\" * (8000))"
    rule_id = '3'
    rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.IP_PROTOCOL: 'icmp', AclConsts.FRAGMENT: AclConsts.FRAGMENT}
    config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id, rule_configuration_dict, mgmt_port,
                                               AclConsts.INBOUND, control_plane='')
    validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr, packet=packet)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_tcp_flag_mask(engines, test_api, topology_obj):
    """
    Validate ACL match tcp flag and mask rules.
    steps:
    1. config ACL with tcp flag and mask rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_TCP_FLAG_MASK"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    flag_packet_dict = {'ack': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"A\")",
                        'fin': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"F\")",
                        'psh': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"P\")",
                        'rst': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"R\")",
                        'syn': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"S\")",
                        'urg': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"U\")",
                        'all': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"SAFRUP\")",
                        'none': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"\")"}

    rule_id = str(len(flag_packet_dict) * 2)
    acl_obj = None

    for flag, packet in flag_packet_dict.items():
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.IP_PROTOCOL: 'tcp',
                                   AclConsts.TCP_FLAGS: flag, AclConsts.TCP_MASK: flag}
        acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                             rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                             AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
        validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                        packet=packet)
        rule_id = str(int(rule_id) - 1)
        if flag not in ['all', 'none']:
            rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.IP_PROTOCOL: 'tcp',
                                       AclConsts.TCP_FLAGS: flag, AclConsts.TCP_MASK: 'all'}
            acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                                 rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                 AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
            validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id,
                                            dest_addr, packet=packet)
            rule_id = str(int(rule_id) - 1)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_ip_state(engines, test_api, topology_obj):
    """
    Validate ACL match ip state rules.
    steps:
    1. config ACL with a match ip state rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_IP_STATE"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    state_packet_dict = {'new': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"S\")",
                         'invalid': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"R\")",
                         'established': f"IP(dst=\"{dest_addr}\") / ICMP()"}
    # 'related': f"IP(dst=\"{dest_addr}\") / ICMP(type=3)"}
    rule_id = str(len(state_packet_dict))
    acl_obj = None

    for state, packet in state_packet_dict.items():
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.TCP_STATE: state, AclConsts.IP_PROTOCOL: 'tcp'}
        acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                             rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                             AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
        validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                        packet=packet)
        rule_id = str(int(rule_id) - 1)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_icmp_type(engines, test_api, topology_obj):
    """
    Validate ACL match icmp_type rules.
    steps:
    1. config ACL with a match icmp_type rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_ICMP_TYPE"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    rand_num_type = random.randint(0, 255)
    state_packet_dict = {'echo-reply': f"IP(dst=\"{dest_addr}\") / ICMP(type=\"echo-reply\")",
                         'echo-request': f"IP(dst=\"{dest_addr}\") / ICMP(type=\"echo-request\")",
                         'time-exceeded': f"IP(dst=\"{dest_addr}\") / ICMP(type=\"time-exceeded\")",
                         'destination-unreachable': f"IP(dst=\"{dest_addr}\") / ICMP(type=3)",
                         'port-unreachable': f"IP(dst=\"{dest_addr}\") / ICMP(type=3, code=3)",
                         rand_num_type: f"IP(dst=\"{dest_addr}\") / ICMP(type={rand_num_type})"}
    rule_id = str(len(state_packet_dict))
    acl_obj = None

    for icmp_type, packet in state_packet_dict.items():
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.ICMP_TYPE: icmp_type, AclConsts.IP_PROTOCOL: 'icmp'}
        acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                             rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                             AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
        validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                        packet=packet)
        rule_id = str(int(rule_id) - 1)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_icmpv6_type(engines, test_api, topology_obj):
    """
    Validate ACL match icmpv6_type rules.
    steps:
    1. config ACL with a match icmpv6_type rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_ICMPV6_TYPE"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    icmpv6_type_packet_dict = {'router-solicitation': f"IP(dst=\"{dest_addr}\") / ICMPv6ND_RS()",
                               'router-advertisement': f"IP(dst=\"{dest_addr}\") / ICMPv6ND_RA()"}
    # 'neighbor-solicitation': f"IP(dst=\"{dest_addr}\") / ICMPv6ND_NS()",
    # 'neighbor-advertisement': f"IP(dst=\"{dest_addr}\") / ICMPv6ND_NA()"}
    rule_id = str(len(icmpv6_type_packet_dict))
    acl_obj = None

    for icmpv6_type, packet in icmpv6_type_packet_dict.items():
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.ICMPV6_TYPE: icmpv6_type, AclConsts.IP_PROTOCOL: 'icmpv6'}
        acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv6', rule_id,
                                                             rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                             AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
        validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                        packet=packet)
        rule_id = str(int(rule_id) - 1)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_mss(engines, test_api, topology_obj):
    """
    Validate ACL match ip mss rules.
    steps:
    1. config ACL with a match ip mss rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_MSS"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    rand_mss = str(random.randint(1500, 2500))
    packet = f"IP(dst=\"{dest_addr}\") / TCP(options=[('MSS', {rand_mss})])"
    rule_id = str(random.randint(2, 10))

    with allure.step("mss rules"):
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.MSS: rand_mss, AclConsts.IP_PROTOCOL: 'tcp'}
        acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                             rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                             AclConsts.CONTROL_PLANE)
        validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                        packet=packet)

    with allure.step("all-mss-except rules"):
        rule_id = str(int(rule_id) - 1)
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.ALL_MSS_EXCEPT: rand_mss, AclConsts.IP_PROTOCOL: 'tcp'}
        config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id, rule_configuration_dict,
                                                   mgmt_port, AclConsts.INBOUND, AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
        validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                        packet=packet)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_match_ecn(engines, test_api, topology_obj):
    """
    Validate ACL match ecn rules.
    steps:
    1. config ACL with a match ecn rule
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_ECN"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    ecn_flags_dict = {'tcp-cwr': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"C\")",
                      'tcp-ece': f"IP(dst=\"{dest_addr}\") / TCP(flags=\"E\")"}
    ecn_ip_ect_dict = {0: f"IP(dst=\"{dest_addr}\", tos=0) / TCP(dport=80)",
                       1: f"IP(dst=\"{dest_addr}\", tos=1) / TCP(dport=80)",
                       2: f"IP(dst=\"{dest_addr}\", tos=2) / TCP(dport=80)"}
    # 3: f"IP(dst=\"{dest_addr}\", tos=3) / TCP(dport=80)"}
    rule_id = str(len(ecn_flags_dict) + len(ecn_ip_ect_dict))
    acl_obj = None

    with allure.step("ecn flags rules"):
        for ecn_flag, packet in ecn_flags_dict.items():
            rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.ECN_FLAGS: ecn_flag, AclConsts.IP_PROTOCOL: 'tcp'}
            acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                                 rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                 AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
            validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                            packet=packet)
            rule_id = str(int(rule_id) - 1)

    with allure.step("ecn ip-ect rules"):
        for ip_ect, packet in ecn_ip_ect_dict.items():
            rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.ECN_IP_ECT: ip_ect, AclConsts.IP_PROTOCOL: 'tcp'}
            acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id,
                                                                 rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                 AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
            validate_counters_after_traffic(engines.sonic_mgmt, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr,
                                            packet=packet)
            rule_id = str(int(rule_id) - 1)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_hashlimit(engines, test_api, topology_obj):
    """
    Validate ACL match hashlimit rules.
    steps:
    1. config ACL with 2 rule hashlimit rules
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_HASH_LIMIT"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.sonic_mgmt.ip
    rule_id = '1'
    rand_burst = random.randint(1, 10)

    with allure.step("configurations"):
        rule_1_configuration_dict = {AclConsts.ACTION: AclConsts.DENY, AclConsts.DEST_IP: dest_addr,
                                     AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request',
                                     AclConsts.HASHLIMIT_NAME: 'one_per_min', AclConsts.HASHLIMIT_RATE: '1/min',
                                     AclConsts.HASHLIMIT_BURST: rand_burst, AclConsts.HASHLIMIT_MODE: 'src-ip',
                                     AclConsts.HASHLIMIT_EXPIRE: 50000}
        config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', rule_id, rule_1_configuration_dict,
                                                   mgmt_port, AclConsts.OUTBOUND)

    with allure.step(f"Validate counters increased"):
        rule_packets_before = get_rule_packets(mgmt_port, acl_id, rule_id, rule_direction=AclConsts.OUTBOUND)
        packets_amount = 3 * rand_burst
        ping_from_switch(engines.dut, dest_addr, mgmt_port_name, count=packets_amount, optional_params="-i 0.2").verify_result()
        time.sleep(5)
        rule_packets_after = get_rule_packets(mgmt_port, acl_id, rule_id, rule_direction=AclConsts.OUTBOUND)
        assert int(rule_packets_after[rule_id]) - int(rule_packets_before[rule_id]) >= (packets_amount - rand_burst - 1), \
            "expect to see difference in the counters after the ping"


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_recent_list(engines, test_api, topology_obj):
    """
    Validate ACL match recent-list rules.
    steps:
    1. config ACL with 2 recent-list rules
    2. send packet
    3. validate counter increased
    """
    TestToolkit.tested_api = test_api
    acl_id = "AA_TEST_ACL_RECENT_LIST"
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    dest_addr = engines.dut.ip
    src_ip = engines.sonic_mgmt.ip
    set_rule_id = '1'
    update_rule_id = '2'
    recent_list_name = 'ip_list'
    update_interval = random.randint(5, 10)
    hit_count = random.randint(3, 10)

    with allure.step("configurations"):
        rule_1_configuration_dict = {AclConsts.SOURCE_IP: src_ip, AclConsts.RECENT_LIST_NAME: recent_list_name,
                                     AclConsts.RECENT_LIST_ACTION: 'set', AclConsts.IP_PROTOCOL: 'icmp',
                                     AclConsts.ICMP_TYPE: 'echo-request'}
        acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, 'ipv4', set_rule_id, rule_1_configuration_dict,
                                                             mgmt_port, AclConsts.INBOUND)
        rule_2_configuration_dict = {AclConsts.ACTION: AclConsts.DENY, AclConsts.SOURCE_IP: src_ip,
                                     AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request',
                                     AclConsts.RECENT_LIST_NAME: recent_list_name, AclConsts.RECENT_LIST_ACTION: 'update',
                                     AclConsts.RECENT_LIST_UPDATE: update_interval, AclConsts.RECENT_LIST_HIT: hit_count}
        config_rule(engines.dut, acl_obj, update_rule_id, rule_2_configuration_dict)

    with allure.step("Validate the second rule will not match cause it will be less packets than the hit-count"):
        amount_of_packet = hit_count - 2
        engines.sonic_mgmt.run_cmd_set(['ping {} -c {} -i 0.1'.format(dest_addr, amount_of_packet), "\x03"])
        rule_packets_after = get_rule_packets(mgmt_port, acl_id)
        assert amount_of_packet == int(rule_packets_after[set_rule_id])
        assert 0 == int(rule_packets_after[update_rule_id])

        with allure.step(f"wait {update_interval} sec as the update interval value"):
            time.sleep(update_interval)

    with allure.step("Validate the second rule will match cause it will be the same amount of packets as the hit-count"):
        amount_of_packet1 = 2 * hit_count + 2
        engines.sonic_mgmt.run_cmd_set(['ping {} -c {} -i 0.1'.format(dest_addr, amount_of_packet1), "\x03"])
        rule_packets_after = get_rule_packets(mgmt_port, acl_id)
        assert amount_of_packet + amount_of_packet1 == int(rule_packets_after[set_rule_id]), "expect to see all the sent packets in the counters of the set rule after ping"
        assert hit_count <= int(rule_packets_after[update_rule_id]), f"expect to see just {hit_count} packets in the counters of the update rule after ping"

    with allure.step("unset the second rule and validate packets received since it should delete the ip from the list"):
        acl_obj.rule.rule_id[update_rule_id].unset(apply=True)
        time.sleep(5)
        amount_of_packet = hit_count
        output = engines.sonic_mgmt.run_cmd_set(['ping {} -c {} -i 0.1'.format(dest_addr, amount_of_packet), "\x03"])
        rule_packets_after3 = get_rule_packets(mgmt_port, acl_id)
        assert 4 * hit_count == int(rule_packets_after3[set_rule_id]), "expect to see all the sent packets in the counters of the set rule after ping"
        assert '0% packet loss' in output, "expect ping to pass after removing the update rule"

# ------------------- default rules -------------------


@pytest.mark.acl
def test_adding_new_rule(engines, topology_obj, apply_default_config):
    """
    Adding new rule that will be the opposite of a default rule and validate that the first rule will catch the packet.
    -	Add it before the default rules (by acl name) : validate new rule catch the packet and see counter increase
    -	Unset to the rule
    -	Add it before the default rules (by acl name): validate that the default rule catch the packet and not the new rule
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    default_chosen_acl = 'ACL_MGMT_INBOUND_CP_DEFAULT'
    default_chosen_rule = '130'
    new_acl = 'AA_TEST_ADD_NEW_RULE'
    new_rule = '1'
    acl_type = 'ipv4'

    with allure.step("Sanity check - send packet and validate default rule counters"):
        rule_packets_1_before = get_rule_packets(mgmt_port, default_chosen_acl, default_chosen_rule)
        packet = f"IP(dst=\"{engines.dut.ip}\") / UDP(dport=161)"
        scapy_send_packet(engines.sonic_mgmt, packet)
        rule_packets_1_after = get_rule_packets(mgmt_port, default_chosen_acl, default_chosen_rule)
        assert rule_packets_1_after[default_chosen_rule] > rule_packets_1_before[default_chosen_rule], \
            f'expect to see increase in acl {default_chosen_acl} rule id {default_chosen_rule} counter after sending relevant packet'

    try:
        with allure.step("Add new rule that will be before the default rules"):
            rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.IP_PROTOCOL: 'udp'}
            new_acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, new_acl, acl_type, new_rule,
                                                                     rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                     AclConsts.CONTROL_PLANE)
            with allure.step("Validate new rule with show command"):
                rule_output = new_acl_obj.rule.parse_show(new_rule)
                assert rule_output[AclConsts.MATCH][AclConsts.IP][AclConsts.PROTOCOL] == 'udp'

        with allure.step("Validate ACL counters"):
            new_rule_packets_before = get_rule_packets(mgmt_port, new_acl, new_rule)
            default_rule_packets_before = get_rule_packets(mgmt_port, default_chosen_acl, default_chosen_rule)
            scapy_send_packet(engines.sonic_mgmt, packet)
            default_rule_packets_after = get_rule_packets(mgmt_port, default_chosen_acl, default_chosen_rule)
            new_rule_packets_after = get_rule_packets(mgmt_port, new_acl, new_rule)
            assert new_rule_packets_after[new_rule] > new_rule_packets_before[new_rule], \
                f'we expect to see increase in acl {new_acl} rule id {new_rule} counter - cause the first acl should be applied'
            assert default_rule_packets_after[default_chosen_rule] == default_rule_packets_before[default_chosen_rule], \
                f'counters of acl {default_chosen_acl} rule id {default_chosen_rule} expected not to change'

        with allure.step("unset new rule and add new rule to be after the default rules"):
            new_acl_obj.unset()
            mgmt_port.interface.acl.unset(new_acl, apply=True)
            new_acl_obj.show(should_succeed=False)
            new_acl = 'ZZ_TEST_ADD_NEW_RULE'
            new_acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, new_acl, acl_type, new_rule,
                                                                     rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                     AclConsts.CONTROL_PLANE)
            with allure.step("Validate new rule with show command"):
                rule_output = new_acl_obj.rule.parse_show(new_rule)
                assert rule_output[AclConsts.MATCH][AclConsts.IP][AclConsts.PROTOCOL] == 'udp'

        with allure.step("Validate ACL counters"):
            new_rule_packets_before = get_rule_packets(mgmt_port, new_acl, new_rule)
            default_rule_packets_before = get_rule_packets(mgmt_port, default_chosen_acl, default_chosen_rule)
            scapy_send_packet(engines.sonic_mgmt, packet)
            default_rule_packets_after = get_rule_packets(mgmt_port, default_chosen_acl, default_chosen_rule)
            new_rule_packets_after = get_rule_packets(mgmt_port, new_acl, new_rule)
            assert default_rule_packets_after[default_chosen_rule] > default_rule_packets_before[default_chosen_rule], \
                f'we expect to see increase in acl {default_chosen_acl} rule id {default_chosen_rule} counter - cause the first acl should be applied'
            assert new_rule_packets_after[new_rule] == new_rule_packets_before[new_rule], \
                f'counters of acl {new_acl} rule id {new_rule} expected not to change'

    finally:
        with allure.step("cleanup"):
            Acl().unset()
            mgmt_port.interface.acl.unset(new_acl, apply=True)


@pytest.mark.acl
def test_override_default_rule(engines, topology_obj, apply_default_config):
    """
    Override rule – not allowed to delete attr of default rule,
    just add new one or change existing one.
    unset will return to the default rule.
    steps:
    1. sanity check - send SYN packet and validate counters increase
    2. override default rules - add new field
    3. send packet and validate the override rule counters
    4. override default rules - change existing field
    5. send packet and validate the override rule counters
    6. unset acl - validate return to default rules
    7. unset filed of default rule - should fail
    """
    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    src_ip = "10.77.133.200"    # random unrelated ip
    default_chosen_acl = 'ACL_MGMT_INBOUND_CP_DEFAULT'
    default_rule_to_add_field = '20'   # add source ip that not related to us
    default_rule_to_override_field = '130'  # change the dest port
    acl_obj = Acl().acl_id[default_chosen_acl]

    with allure.step("Unset existing field - should fail"):
        acl_obj.rule.rule_id[default_rule_to_override_field].match.unset(apply=True, expected_str="err").verify_result(False)

    with allure.step("Sanity check - send SYN packet and validate counters increase"):
        rule_packets_before = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_add_field)
        packet_tcp = f"IP(dst=\"{engines.dut.ip}\") / TCP(dport=80, flags=\"S\")"
        scapy_send_packet(engines.sonic_mgmt, packet_tcp)
        rule_packets_after = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_add_field)
        assert int(rule_packets_after[default_rule_to_add_field]) > int(rule_packets_before[default_rule_to_add_field]), \
            f'the rule should catch this packet'
        rule_packets_before = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_override_field)
        packet_udp = f"IP(dst=\"{engines.dut.ip}\") / UDP(dport=52)"
        scapy_send_packet(engines.sonic_mgmt, packet_udp)
        rule_packets_after = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_override_field)
        assert rule_packets_after[default_rule_to_override_field] == rule_packets_before[default_rule_to_override_field], \
            f'the rule should not catch this packet cause it is different dest port'
    try:
        with allure.step("save default rules output"):
            default_rule_to_add_field_output = acl_obj.rule.parse_show(default_rule_to_add_field)
            default_rule_to_override_field_output = acl_obj.rule.parse_show(default_rule_to_override_field)

        if not is_redmine_issue_active([4138944])[0]:
            with ((allure.step("override default rules - add new field"))):
                config_rule(engines.dut, acl_obj, default_rule_to_add_field, {AclConsts.SOURCE_IP: src_ip})
                with allure.step("validate with show command"):
                    rule_output = acl_obj.rule.parse_show(default_rule_to_add_field)
                    assert AclConsts.SOURCE_IP in rule_output[AclConsts.MATCH][AclConsts.IP].keys(), \
                        f"{AclConsts.SOURCE_IP} not found in the output"
                    assert rule_output[AclConsts.MATCH][AclConsts.IP][AclConsts.SOURCE_IP] == src_ip, \
                        (f"{AclConsts.SOURCE_IP} = {rule_output[AclConsts.MATCH][AclConsts.IP][AclConsts.SOURCE_IP]}, "
                         f"expected - {src_ip}")

                with allure.step("Validate ACL counters"):
                    rule_packets_before = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_add_field)
                    scapy_send_packet(engines.sonic_mgmt, packet_tcp)
                    rule_packets_after = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_add_field)
                    assert rule_packets_after[default_rule_to_add_field] == rule_packets_before[default_rule_to_add_field], \
                        f'the rule should not catch this packet because we override it with src ip that not exist in this setup'

            with allure.step("override default rules - change existing field"):
                config_rule(engines.dut, acl_obj, default_rule_to_override_field, {AclConsts.UDP_DEST_PORT: '52'})
                with allure.step("validate with show command"):
                    rule_output = acl_obj.rule.parse_show(default_rule_to_override_field)
                    assert '52' in rule_output[AclConsts.MATCH][AclConsts.IP]['udp']['dest-port'].keys()

                with allure.step("Validate ACL counters"):
                    rule_packets_1_before = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_override_field)
                    scapy_send_packet(engines.sonic_mgmt, packet_udp)
                    rule_packets_1_after = get_rule_packets(mgmt_port, default_chosen_acl, default_rule_to_override_field)
                    assert int(rule_packets_1_after[default_rule_to_override_field]) > int(rule_packets_1_before[default_rule_to_override_field]), \
                        f'the rule should catch this packet because we override it'

    finally:
        with allure.step("unset acl - should return all the default rules"):
            acl_obj.unset(apply=True, ask_for_confirmation=True)

            with allure.step("Validate"):
                added_field_output = acl_obj.rule.parse_show(default_rule_to_add_field)
                override_field_output = acl_obj.rule.parse_show(default_rule_to_override_field)
                assert added_field_output == default_rule_to_add_field_output, "should return to default values after unset"
                assert override_field_output == default_rule_to_override_field_output, "should return to default values after unset"


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_nmx_ports(engines, devices, test_api):
    """
    Check if device has acl rules for nmx
    steps:
    1. Check device has nmx support
    2. Parse acl rules show
    3. Find nmx related rule
        * If no nmx rule found -> fail
    4. Verify nmx ports 9351, 9352, 9353, 9370 are open for tcp
    """

    with allure.step("Check if device has nmx"):
        if not devices.dut.has_nmx:
            pytest.skip("This setup doesn't have nmx")

    with allure.step("Show ACL rules and verify nmx ports are open"):
        TestToolkit.tested_api = test_api

        default_chosen_acl = 'ACL_MGMT_INBOUND_CP_DEFAULT'
        acl_obj = Acl().acl_id[default_chosen_acl]
        acl_rules = OutputParsingTool.parse_show_output_to_dict(acl_obj.show()).get_returned_value()[AclConsts.RULE]
        assert acl_rules, "No ACL rules were found"

        nmx_rule = None
        for rule_id, rule in acl_rules.items():
            if "nmx" in rule.get(AclConsts.REMARK, ""):
                nmx_rule = rule
                break
        assert nmx_rule, "No acl rule was found for nmx"
        assert AclConsts.PERMIT in nmx_rule[AclConsts.ACTION], "The acl action is not permit"

    ports_to_check = {"9351", "9352", "9353", "9370"}
    with allure.step(f"Verify ports for nmx are open {ports_to_check}"):
        nmx_open_ports = nmx_rule[AclConsts.MATCH][AclConsts.IP][AclConsts.TCP][AclConsts.DEST_PORT]
        assert ports_to_check <= nmx_open_ports.keys(), "Not all nmx ports are open"


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_dscp_supported_values_ipv4(engines, devices, test_api, topology_obj):
    configure_validate_dscp_acl_value(engines, devices, acl_type=IpConsts.IPV4, protocol=AclConsts.ICMP, sonic_ip=engines.sonic_mgmt.ip)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_dscp_supported_values_ipv6(engines, devices, test_api, topology_obj, sonic_mgmt_ipv6_addr):
    configure_validate_dscp_acl_value(engines, devices, acl_type=IpConsts.IPV6, protocol=AclConsts.ICMPV6, sonic_ip=sonic_mgmt_ipv6_addr)


@pytest.mark.acl
@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_acl_dscp_unsupported_values(engines, devices, test_api, topology_obj):
    """
    Validate ACLs dscp over ipv4.
    steps:
    1. config ACL with a rule and random dscp value - Unsupported
    2. Expect the config apply to fail as unsupported value is provided
    """
    with allure.step("Config outbound ACLs with match protocol icmp and dscp option"):
        acl_type = IpConsts.IPV4
        mgmt_port_name = 'eth0'
        rule_id_1 = '1'
        random_dscp_value, random_dscp_value_hex = list(get_dscp_hexadecimal_dict("unsupported_dec").keys())[0], \
            list(get_dscp_hexadecimal_dict("unsupported_dec").values())[0]
        acl_id = "ACL_OUTBOUND_DSCP_unsupp"
        acl = Acl()
        acl.set(acl_id).verify_result()
        acl_obj = acl.acl_id[acl_id]
        acl_obj.set(AclConsts.TYPE, acl_type).verify_result()
        acl_obj.rule.set(rule_id_1).verify_result()
        rule_id_obj = acl_obj.rule.rule_id[rule_id_1]
        rule_id_obj.action.dscp.set(random_dscp_value).verify_result(should_succeed=False)

# ------------------- functions -------------------


def configure_validate_dscp_acl_value(engines, devices, acl_type, protocol, sonic_ip):
    """
    steps:
    1. config ACL with a rule and random dscp value - supported
    2. Attach ACL to outbound eth0 port on switch
    3. Check the value using nv show commands
    4. send packet ipv4/ipv6 from switch to sonic management ip
    5. Extract tos value from ipv4/ipv6 header (ICMP) packet
    6. Validate tos value by converting to hexadecimal value
    7. Unset the dscp value and check the value using nv show commands
    """
    with allure.step("Config outbound ACLs with match protocol icmp and dscp option"):
        mgmt_port_name = 'eth0'
        mgmt_port = Port(mgmt_port_name)
        rule_id_1 = '1'
        random_dscp_value, random_dscp_value_hex = list(get_dscp_hexadecimal_dict("supported_dec").keys())[0], \
            list(get_dscp_hexadecimal_dict("supported_dec").values())[0]
        rule_configuration_dict = {AclConsts.DEST_IP: 'ANY',
                                   AclConsts.IP_PROTOCOL: protocol, AclConsts.DSCP_SET_ACTION: random_dscp_value}
        acl_id = "ACL_OUTBOUND_DSCP"
        config_acl_with_rule_attached_to_interface(engines.dut, acl_id,
                                                   acl_type, rule_id_1,
                                                   rule_configuration_dict, mgmt_port,
                                                   AclConsts.OUTBOUND, control_plane="")
    with allure.step("Validate configuration with show commands"):
        acl_obj = Acl()
        output = OutputParsingTool.parse_dscp_value_from_acl(engines, acl_obj, acl_id, rule_id_1)
        ValidationTool.verify_field_value_in_output(output, AclConsts.DSCP, random_dscp_value).verify_result()
    try:
        with allure.step("Create a separate process to run tcpdump and validate option tos in packets"):
            tcpdump_process = Process(target=run_tcpdump_validate_option_dscp,
                                      args=(engines.sonic_mgmt, acl_type, random_dscp_value_hex))
            tcpdump_process.start()
        with allure.step("Ping to sonic mgmt ip to initiate packet transfers"):
            ping_from_switch(engines.dut, sonic_ip, mgmt_port_name, count=20).verify_result()
    finally:
        with allure.step("Combine with tcpdump process to finish gracefully"):
            tcpdump_process.join()
            assert tcpdump_process.exitcode == 0, "DSCP tos value not found in dhcp packets"

        with allure.step("Unset dscp option to check CLI command"):
            acl_obj.acl_id[acl_id].rule.rule_id[rule_id_1].action.dscp.unset(apply=True)
            output = OutputParsingTool.parse_dscp_value_from_acl(engines, acl_obj, acl_id, rule_id_1)
            with allure.step("Verify DSCP field in ACL is removed after unset"):
                ValidationTool.verify_field_exist_in_json_output(output, AclConsts.DSCP, should_be_found=False)


def run_tcpdump_validate_option_dscp(dut, acl_type, regex):
    with allure.step('Run tcpdump and validate option dscp'):
        retry_call(validate_dscp_option_tcpdump, [dut, acl_type, regex],
                   exceptions=AssertionError, tries=5, delay=1)


def validate_dscp_option_tcpdump(dut, acl_type, regex):
    if acl_type == IpConsts.IPV4:
        command = f"sudo tcpdump -n -vv -c 200 | grep 'tos {regex}'"
    else:
        command = f"sudo tcpdump -n -vv -c 200 | grep 'class {regex}'"
    tcpdump_output = dut.run_cmd(command)
    assert tcpdump_output, "DSCP TOS value not present in packets"
    logger.info(f"DSCP TOS value - {regex} present in tcpdump")


def sleep():
    logger.info(f"sleep {SLEEP_TIME}")
    time.sleep(SLEEP_TIME)


def get_rule_packets(mgmt_port, acl_id, rule_id=None, rule_direction=AclConsts.INBOUND):
    with allure.step(f"get_rule_packet({mgmt_port.name=}, {acl_id=}, {rule_id=}, {rule_direction=})"):
        output = mgmt_port.interface.acl.acl_id[acl_id].parse_show()
        res = {}
        assert AclConsts.STATISTICS in output.keys(), f"{AclConsts.STATISTICS} is not found in the output"
        if rule_id:
            res[rule_id] = int(output[AclConsts.STATISTICS][rule_id][rule_direction]["packet"])
        else:
            for rule_id, rule_obj in output[AclConsts.STATISTICS].items():
                res[rule_id] = int(rule_obj[rule_direction]["packet"])
        return res


def config_rule(engine, acl_id_obj, rule_id, rule_config_dict):
    with allure.step(f"Config rule {rule_id}"):
        acl_id_obj.rule.set(rule_id).verify_result()
        rule_id_obj = acl_id_obj.rule.rule_id[rule_id]

        for key, value in rule_config_dict.items():
            RULE_CONFIG_FUNCTION[key](rule_id_obj, value).verify_result()

        result_obj = SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config,
                                                     engine, True)
        sleep()
        return result_obj


def config_acl_with_rule_attached_to_interface(engine, acl_id, acl_type, rule_id, rule_configuration_dict, mgmt_port,
                                               rule_direction, control_plane=AclConsts.CONTROL_PLANE, acl_obj=None,
                                               should_succeed=True):
    with allure.step(f"config acl {acl_id} with rule {rule_id} attached to interface {mgmt_port.name}"):
        if acl_obj:
            config_rule(engine, acl_obj, rule_id, rule_configuration_dict).verify_result()
        else:
            acl = Acl()
            acl.set(acl_id).verify_result()
            acl_obj = acl.acl_id[acl_id]
            acl_obj.set(AclConsts.TYPE, acl_type).verify_result()
            config_rule(engine, acl_obj, rule_id, rule_configuration_dict).verify_result()
            attach_acl_to_interface(acl_id, mgmt_port, rule_direction, control_plane).verify_result(should_succeed)
    sleep()
    return acl_obj


def attach_acl_to_interface(acl_id, mgmt_port, rule_direction, control_plane=AclConsts.CONTROL_PLANE):
    with allure.step(f"Attach acl {acl_id} to interface {mgmt_port.name}"):
        mgmt_port.interface.acl.set(acl_id).verify_result()
        if rule_direction == AclConsts.INBOUND:
            result_obj = mgmt_port.interface.acl.acl_id[acl_id].inbound.set(control_plane, apply=True)
        elif rule_direction == AclConsts.OUTBOUND:
            result_obj = mgmt_port.interface.acl.acl_id[acl_id].outbound.set(control_plane, apply=True)
        return result_obj


def validate_counters_after_traffic(engine, rule_direction, mgmt_port, acl_id, rule_id, ping_dest=None, packet=None):
    with allure.step(f"Verify {rule_direction} rule captures relevant traffic"):
        rule_packets_before = get_rule_packets(mgmt_port, acl_id, rule_id, rule_direction=rule_direction)
        if packet:
            scapy_send_packet(engine, packet, interface=mgmt_port.name)
        elif ping_dest:
            ping_from_switch(engine, ping_dest, mgmt_port.name).verify_result()
        time.sleep(5)
        rule_packets_after = get_rule_packets(mgmt_port, acl_id, rule_id, rule_direction=rule_direction)
        assert int(rule_packets_after[rule_id]) > int(rule_packets_before[rule_id]), \
            "expect to see difference in the counters after the ping"


def ping_from_switch(engine: ProxySshEngine, dest: str, source_interface, count=2, optional_params="") -> ResultObj:
    with allure.step(f"Ping from switch through {source_interface} to {dest}"):
        cmd = f"ping {dest} -c {count}"
        if source_interface:
            cmd += " -I " + source_interface
        if optional_params:
            cmd += " " + optional_params
        ping_output = engine.run_cmd(cmd)
        if "100% packet loss" in ping_output:
            return ResultObj(False, f"Failed to ping {dest}", ping_output)

        return ResultObj(True, "", ping_output)


def ping_from_sonic_mgmt(dst: Union[str, Packet], src=None) -> Packet:
    with allure.step(f"ping {dst} from {src or 'default'}"):
        # When running locally (not through MARS), uncomment these 2 lines and delete the following lines.
        # Also you might need to set the src parameter to your VDI rather than the sonic_mgmt ip.
        # subprocess.run(f"ping {dst if isinstance(dst, str) else dst.dst} -c1".split(' '), capture_output=True)
        # return dst if isinstance(dst, Packet) else (IP(dst=dst, src=src) / ICMP())
        try:
            packet = dst if isinstance(dst, Packet) else (IP(dst=dst, src=src) / ICMP())
            send(packet)
            return packet
        except PermissionError as e:
            raise Exception(
                "When running this locally (not through MARS) you need to uncomment in the function's source-code"
            ) from e


def dest_ip_test(engines, mgmt_port, acl_type, acl_id, dest_ip_list, ping_dest):
    with allure.step(f"Define ACL {acl_id} type {acl_type}"):
        rule_id = str(len(dest_ip_list))
        acl_obj = None

    for dest_ip in dest_ip_list:
        with allure.step(f"{dest_ip=}"):
            rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.DEST_IP: dest_ip}
            acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, acl_type, rule_id,
                                                                 rule_configuration_dict, mgmt_port, AclConsts.OUTBOUND,
                                                                 AclConsts.CONTROL_PLANE, acl_obj=acl_obj)
            time.sleep(5)
            validate_counters_after_traffic(engines.dut, AclConsts.OUTBOUND, mgmt_port, acl_id, rule_id, ping_dest=ping_dest)
            rule_id = str(int(rule_id) - 1)


def scapy_send_packet(engine, packet, interface=''):
    args = packet
    if interface:
        args += f', iface="{interface}"'
    cmd = f"send({args})"
    cmd_set = ["sudo scapy", cmd, "exit()"]
    with allure.step(f"On {engine.ip}: sending with scapy {cmd}"):
        ret = engine.run_cmd_set(cmd_set, validate=False, patterns_list=[">>>"])
        if "Traceback" in ret:
            raise Exception("scapy failed: " + ret)


def match_ip_port_test(engines, mgmt_port, acl_type, acl_id, port_list, dest_addr, port_direction, engine_send_packet):
    rule_id = str(len(port_list))
    acl_obj = None

    for port in port_list:
        with allure.step(f"{port=}"):
            src_addr = engine_send_packet.ip
            rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.IP_PROTOCOL: 'tcp', port_direction: port}
            acl_obj = config_acl_with_rule_attached_to_interface(engines.dut, acl_id, acl_type, rule_id,
                                                                 rule_configuration_dict, mgmt_port, AclConsts.INBOUND,
                                                                 control_plane="", acl_obj=acl_obj)
            if port == 'ANY':
                port = 1234
            port = port if isinstance(port, int) else f"\"{port}\""
            packet = f"IP(src=\"{src_addr}\", dst=\"{dest_addr}\") / TCP(sport={port}, dport={port})"
            validate_counters_after_traffic(engine_send_packet, AclConsts.INBOUND, mgmt_port, acl_id, rule_id, dest_addr, packet=packet)
            rule_id = str(int(rule_id) - 1)


def get_dscp_hexadecimal_dict(option):
    if option == 'supported_dec':
        rand_int = random.randint(0, 64)
        return ({rand_int: hex(rand_int * 4)})
    elif option == 'unsupported_dec':
        rand_int = random.randint(64, 100)
        return ({rand_int: hex(rand_int)})
    elif option == 'supported_enum':
        enum_list = [af11, af12, af13, af21, af22, af23, af31, af32, af33, af41, af42, af43, cs1, cs2, cs3, cs4, cs5, cs6, cs7, be, ef]
        return (random.choice(enum_list))
    else:
        logger.info("please provide valid option")
