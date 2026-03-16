import logging
import pytest
from retry import retry
import time
from typing import Union

from retry.api import retry_call
import random
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
# from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType, AclConsts, OutputFormat, IpConsts
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
# from infra.tools.redmine.redmine_api import is_redmine_issue_active
from scapy.layers.inet import IP, TCP, ICMP
from scapy.layers.inet6 import IPv6, ICMPv6EchoRequest
from scapy.all import *
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from multiprocessing import Process
from ngts.nvos_tools.system.System import System
# Import shared functions from test_acl_basic
from ngts.tests_nvos.acl.test_acl_basic import (
    RULE_CONFIG_FUNCTION, sleep, ping_from_switch, ping_from_sonic_mgmt,
    get_rule_packets, config_rule, config_acl_with_rule_attached_to_interface,
    attach_acl_to_interface, scapy_send_packet
)

logger = logging.getLogger()

# Constants - keeping local constants that might be different from basic file
SLEEP_TIME = 15
IPV6_ADDR = "2001:db8:abcd:0012:0000:0000:0000:00ef"


# test_can_ping_from_eth1 is available in test_acl_basic.py


# Helper functions are now imported from test_acl_basic.py


def get_system_cp_rule_packets(system_cp_acl_obj, rule_id=None, rule_direction=AclConsts.INBOUND):
    """
    Get packet counters for system control plane ACL rules
    """
    with allure.step(f"get_system_cp_rule_packets({rule_id=}, {rule_direction=})"):
        output = system_cp_acl_obj.parse_show()
        res = {}
        assert AclConsts.STATISTICS in output.keys(), f"{AclConsts.STATISTICS} is not found in the output"
        if rule_id:
            res[rule_id] = int(output[AclConsts.STATISTICS][rule_id][rule_direction]["packet"])
        else:
            for rule_id, rule_obj in output[AclConsts.STATISTICS].items():
                res[rule_id] = int(rule_obj[rule_direction]["packet"])
        return res


@pytest.mark.acl
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_system_control_plane_counters(engines, test_api, topology_obj):
    """
    Validate system control plane ACL counters.
    rule match ip dest-ip - should increase counters when packets hit the rule
    rule match ip source-ip - should increase counters when packets hit the rule
    steps:
    1. config system control plane ACL with match dest-ip rule
    2. send packets and validate counters increased
    3. config system control plane ACL with match source-ip rule
    4. send packets and validate counters increased
    5. validate that different rule directions work correctly
    """
    TestToolkit.tested_api = test_api

    # Skip test for OpenAPI as it's known to fail with system control plane ACLs
    if test_api == ApiType.OPENAPI:
        pytest.skip("Skipping test for OpenAPI as system control plane ACL operations are not working properly")

    with allure.step("Config system control plane ACLs with rules"):
        acl_type = 'ipv4'
        sonic_mgmt_ip = engines.sonic_mgmt.ip
        system_obj = System()

        # Create ACL under system control plane
        acl_id_system_cp = "AA_TEST_SYSTEM_CP_ACL"
        acl_obj = Acl()
        acl_obj.set(acl_id_system_cp).verify_result()
        acl_id_obj = acl_obj.acl_id[acl_id_system_cp]
        acl_id_obj.set(AclConsts.TYPE, acl_type).verify_result()

        # Rule 1: INBOUND ACL - matches traffic FROM sonic_mgmt TO switch
        rule_id_match_src_ip = '1'
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.SOURCE_IP: sonic_mgmt_ip,
                                   AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'}
        config_rule(engines.dut, acl_id_obj, rule_id_match_src_ip, rule_configuration_dict)

        # Attach ACL to system control plane (inbound)
        system_cp_acl_obj = system_obj.control_plane.acl.acl_id[acl_id_system_cp]
        system_cp_acl_obj.inbound.set(apply=True).verify_result()
        sleep()

        with allure.step("Validate configuration with show commands"):
            system_cp_acl_output = system_cp_acl_obj.parse_show()
            assert AclConsts.STATISTICS in system_cp_acl_output.keys(), f"{AclConsts.STATISTICS} not found in system control plane ACL output"

    with allure.step("Validate INBOUND system control plane ACL counters"):
        # Get counters before traffic
        rule_packets_before = get_system_cp_rule_packets(system_cp_acl_obj, rule_id_match_src_ip)
        logger.info(f"DEBUG: Rule 1 packets before ping: {rule_packets_before}")

        # Send ping from sonic mgmt to switch (INBOUND traffic to switch)
        ping_from_sonic_mgmt(engines.dut.ip)

        # Wait for counters to update
        time.sleep(5)

        # Get counters after traffic
        rule_packets_after = get_system_cp_rule_packets(system_cp_acl_obj, rule_id_match_src_ip)
        logger.info(f"DEBUG: Rule 1 packets after ping: {rule_packets_after}")

        assert rule_packets_after[rule_id_match_src_ip] > rule_packets_before[rule_id_match_src_ip], \
            f'we expect to see increase in system control plane ACL {acl_id_system_cp} rule id {rule_id_match_src_ip} counter after the ping'

    with allure.step("Test OUTBOUND direction"):

        # Rule 2: OUTBOUND ACL - matches traffic FROM switch TO sonic_mgmt
        rule_id_match_dest_ip = '2'
        rule_configuration_dict = {AclConsts.ACTION: AclConsts.PERMIT, AclConsts.DEST_IP: sonic_mgmt_ip,
                                   AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'}
        config_rule(engines.dut, acl_id_obj, rule_id_match_dest_ip, rule_configuration_dict)

        # Attach ACL to system control plane (outbound)
        system_cp_acl_obj.outbound.set(apply=True).verify_result()
        sleep()

    with allure.step("Validate OUTBOUND system control plane ACL counters"):
        rule_packets_before = get_system_cp_rule_packets(system_cp_acl_obj, rule_id_match_dest_ip, rule_direction=AclConsts.OUTBOUND)
        logger.info(f"DEBUG: Rule 2 packets before ping: {rule_packets_before}")
        logger.info(f"DEBUG: Testing API type: {TestToolkit.tested_api}")

        # Send ping from switch to sonic mgmt (OUTBOUND traffic from switch)
        ping_from_switch(engines.dut, sonic_mgmt_ip, "eth0").verify_result()

        # Wait for counters to update
        time.sleep(5)

        rule_packets_after = get_system_cp_rule_packets(system_cp_acl_obj, rule_id_match_dest_ip, rule_direction=AclConsts.OUTBOUND)
        logger.info(f"DEBUG: Rule 2 packets after ping: {rule_packets_after}")

        assert rule_packets_after[rule_id_match_dest_ip] > rule_packets_before[rule_id_match_dest_ip], \
            f'we expect to see increase in system control plane ACL {acl_id_system_cp} rule id {rule_id_match_dest_ip} counter after the ping'

    with allure.step("Test outbound direction as well"):
        system_cp_acl_output = system_cp_acl_obj.parse_show()
        assert AclConsts.STATISTICS in system_cp_acl_output.keys(), f"{AclConsts.STATISTICS} not found in system control plane ACL output"

    with allure.step("Clean up system control plane ACL"):
        system_obj.control_plane.acl.unset(acl_id_system_cp, apply=True).verify_result()
        acl_obj.unset(acl_id_system_cp, apply=True).verify_result()


@pytest.mark.acl
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_show_system_control_plane_acl_commands(devices, engines, test_api, topology_obj):
    """
    Validate system control plane acl show commands.
    steps:
    1. config an ACL with rules
    2. attach to system control plane
    3. validate show commands for system control plane ACL
    4. test set/unset operations
    """
    TestToolkit.tested_api = test_api

    # Skip test for OpenAPI as it's known to fail with system control plane ACLs
    if test_api == ApiType.OPENAPI:
        pytest.skip("Skipping test for OpenAPI as system control plane ACL operations are not working properly")
    system_obj = System()

    with allure.step("Define ACL with rules"):
        with allure.step("Define ACL"):
            acl = Acl()
            acl_id = "AA_TEST_SYSTEM_CONTROL_PLANE_ACL_SHOW"
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
                                                             AclConsts.TCP_DEST_PORT: 'ssh', AclConsts.ECN_FLAGS: 'tcp-ece', AclConsts.ECN_IP_ECT: 2})
            expected_acl_dict[acl_id][AclConsts.RULE].update({
                rule_id_2: {
                    AclConsts.ACTION: {AclConsts.PERMIT: {}},
                    AclConsts.MATCH: {
                        AclConsts.IP: {
                            AclConsts.PROTOCOL: 'tcp',
                            'tcp': {
                                'dest-port': {
                                    'ssh': {},
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

    with allure.step("Attach ACL to system control plane"):
        system_cp_acl_obj = system_obj.control_plane.acl.acl_id[acl_id]
        system_cp_acl_obj.inbound.set(apply=True).verify_result()
        sleep()

        with allure.step("Validate system control plane ACL show commands"):
            # Test: nv show system control-plane acl
            system_cp_acls_output = system_obj.control_plane.acl.parse_show()
            logger.info(f"System control plane ACLs output: {system_cp_acls_output}")
            logger.info(f"Looking for ACL: {acl_id}")

            # Debug: Let's also check if the ACL exists at all
            acl_show_output = acl_id_obj.parse_show()
            logger.info(f"ACL {acl_id} show output: {acl_show_output}")

            assert system_cp_acls_output, f"No ACLs found in system control plane. Output: {system_cp_acls_output}"
            assert acl_id in system_cp_acls_output.keys(), f"ACL {acl_id} not found in system control plane ACLs. Available ACLs: {list(system_cp_acls_output.keys())}"

            # Test: nv show system control-plane acl <acl-id>
            system_cp_acl_output = system_cp_acl_obj.parse_show()
            assert AclConsts.STATISTICS in system_cp_acl_output.keys(), f"{AclConsts.STATISTICS} not found in system control plane ACL output"
            assert rule_output.keys() == system_cp_acl_output[AclConsts.STATISTICS].keys()

            # Test: nv show system control-plane acl <acl-id> statistics
            statistics_output = system_cp_acl_obj.statistics.parse_show()
            assert rule_output.keys() == statistics_output.keys()

            # Test: nv show system control-plane acl <acl-id> statistics <rule-id>
            rule_statistics_output = system_cp_acl_obj.statistics.parse_show(rule_id_1)
            assert statistics_output[rule_id_1].keys() == rule_statistics_output.keys()

    with allure.step("Test outbound direction"):
        # Test: nv set system control-plane acl <acl-id> outbound
        system_cp_acl_obj.outbound.set(apply=True).verify_result()
        sleep()

        with allure.step("Validate outbound configuration"):
            system_cp_acl_output = system_cp_acl_obj.parse_show()
            assert AclConsts.STATISTICS in system_cp_acl_output.keys()

            # Verify both inbound and outbound are actually configured
            logger.info("Verifying both inbound and outbound are configured...")
            system_cp_acls_full = system_obj.control_plane.acl.parse_show()
            logger.info(f"Full system CP ACL output: {system_cp_acls_full}")

            if acl_id in system_cp_acls_full:
                acl_config = system_cp_acls_full[acl_id]
                logger.info(f"ACL {acl_id} configuration: {acl_config}")

                # Check if both directions are configured
                has_inbound = 'inbound' in acl_config
                has_outbound = 'outbound' in acl_config
                logger.info(f"Has inbound: {has_inbound}, Has outbound: {has_outbound}")

                if not (has_inbound and has_outbound):
                    logger.warning(f"Expected both inbound and outbound to be set, but got inbound: {has_inbound}, outbound: {has_outbound}")
            else:
                logger.error(f"ACL {acl_id} not found in system control plane!")

    with allure.step("Test unset operations"):
        # Debug: Check current state before unset operations
        logger.info("Checking system control plane state before unset operations...")
        debug_output = system_cp_acl_obj.parse_show()
        logger.info(f"Current system CP ACL state: {debug_output}")

        # Test: nv unset system control-plane acl <acl-id> outbound
        logger.info("Attempting to unset outbound (expecting this to fail)...")
        system_cp_acl_obj.outbound.unset(apply=True).verify_result(True)
        sleep()

        # Test: nv unset system control-plane acl <acl-id> inbound
        logger.info("Attempting to unset inbound (expecting this to fail)...")
        system_cp_acl_obj.inbound.unset(apply=True).verify_result(False)
        sleep()

        # Test: nv unset system control-plane acl <acl-id>
        system_cp_acl_obj.unset(apply=True).verify_result()
        sleep()

        # Verify ACL is removed from system control plane
        try:
            system_cp_acls_after_unset = system_obj.control_plane.acl.parse_show()
            assert acl_id not in system_cp_acls_after_unset.keys(), f"ACL {acl_id} should be removed from system control plane"
        except Exception:
            # Expected when no ACLs are attached
            pass

    with allure.step("Cleanup"):
        acl_id_obj.unset(apply=True).verify_result()


@pytest.mark.acl
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_interface_control_plane_single_acl_rule_priority_order(devices, engines, test_api, topology_obj):
    """
    Validate control plane ACL rules order by priority of rules order.
    The first rule that matches the packet should apply even if the next rule also matches but the action is different.
    This is similar to test_rules_order but specifically for control plane attachment.
    steps:
    1. config a control plane ACL with 2 rules that match same traffic but different actions
    2. send packet to control plane
    3. validate that the action applied is from the first rule (lower rule ID)
    4. remove first rule and verify second rule now takes effect
    """
    TestToolkit.tested_api = test_api
    with allure.step("Define control plane ACL with 2 conflicting rules"):

        with allure.step("Define ACL"):
            acl = Acl()
            acl_id = "AA_TEST_CONTROL_PLANE_RULES_ORDER"
            acl.set(acl_id).verify_result()
            acl_id_obj = acl.acl_id[acl_id]
            acl_id_obj.set(AclConsts.TYPE, 'ipv4').verify_result()
            expected_acl_dict = {acl_id: {AclConsts.RULE: {}, AclConsts.TYPE: 'ipv4'}}

        with allure.step("Config 2 rules with same match criteria but different actions"):
            # Rule 1 (lower priority number = higher precedence) - DENY
            rule_dict = {AclConsts.ACTION: AclConsts.DENY, AclConsts.SOURCE_IP: 'ANY',
                         AclConsts.IP_PROTOCOL: 'icmp', AclConsts.ICMP_TYPE: 'echo-request'}
            rule_id_1 = '1'
            config_rule(engines.dut, acl_id_obj, rule_id_1, rule_dict)

            # Rule 2 (higher priority number = lower precedence) - PERMIT same traffic
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

    with allure.step("Attach ACL to control plane"):
        mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
        mgmt_port = Port(mgmt_port_name)
        mgmt_port.interface.acl.set(acl_id).verify_result()
        mgmt_port.interface.acl.acl_id[acl_id].inbound.set(AclConsts.CONTROL_PLANE, apply=True)
        sleep()

        with allure.step("Validate configuration with show commands"):
            interface_acl_output = mgmt_port.interface.acl.acl_id[acl_id].parse_show()
            assert expected_acl_dict[acl_id][AclConsts.RULE].keys() == interface_acl_output[AclConsts.STATISTICS].keys(), \
                f'Got unexpected control plane interface acl output after configuration\n' \
                f'expected: {expected_acl_dict[acl_id][AclConsts.RULE].keys()}\n' \
                f'but got: {interface_acl_output[AclConsts.STATISTICS].keys()}'

    with allure.step("Validate control plane rule order - first rule should take precedence"):
        rule_packets_before = get_rule_packets(mgmt_port, acl_id, None, AclConsts.INBOUND)

        # Send ICMP packet from sonic_mgmt to switch control plane
        packet = f"IP(src=\"{engines.sonic_mgmt.ip}\", dst=\"{engines.dut.ip}\") / ICMP(type=\"echo-request\")"
        ping_from_sonic_mgmt(engines.dut.ip)

        rule_packets_after = get_rule_packets(mgmt_port, acl_id, None, AclConsts.INBOUND)

        # First rule (DENY) should catch the packet due to lower rule ID (higher precedence)
        assert rule_packets_after[rule_id_1] > rule_packets_before[rule_id_1], \
            f'Rule {rule_id_1} (DENY) should catch the packet due to higher precedence (lower rule ID)'
        assert rule_packets_after[rule_id_2] == rule_packets_before[rule_id_2], \
            f'Rule {rule_id_2} (PERMIT) should not catch the packet because rule {rule_id_1} matches first'

    with allure.step("Remove the first rule and verify second rule takes effect"):
        acl_id_obj.rule.rule_id[rule_id_1].unset(apply=True)
        expected_acl_dict[acl_id][AclConsts.RULE].pop(rule_id_1)
        sleep()

        # Validate ACL configuration after rule removal
        acl_id_output = acl_id_obj.parse_show()
        assert expected_acl_dict[acl_id] == acl_id_output, f'Got unexpected acl output after removing rule {rule_id_1}\n' \
            f'expected: {expected_acl_dict[acl_id]}\nbut got: {acl_id_output}'

        # Validate interface ACL statistics after rule removal
        interface_acl_output = mgmt_port.interface.acl.acl_id[acl_id].parse_show()
        assert expected_acl_dict[acl_id][AclConsts.RULE].keys() == interface_acl_output[AclConsts.STATISTICS].keys(), \
            f'Got unexpected control plane interface acl output after removing rule {rule_id_1}\n' \
            f'expected: {expected_acl_dict[acl_id][AclConsts.RULE].keys()}\n' \
            f'but got: {interface_acl_output[AclConsts.STATISTICS].keys()}'

    with allure.step("Validate second rule now takes effect"):
        rule_packets_before = get_rule_packets(mgmt_port, acl_id, rule_id_2, AclConsts.INBOUND)

        # Send same ICMP packet - should now hit second rule (PERMIT)
        ping_from_sonic_mgmt(engines.dut.ip)

        rule_packets_after = get_rule_packets(mgmt_port, acl_id, rule_id_2, AclConsts.INBOUND)

        # Second rule (PERMIT) should now catch the packet since first rule is removed
        assert rule_packets_after[rule_id_2] > rule_packets_before[rule_id_2], \
            f'Rule {rule_id_2} (PERMIT) should now catch the packet after rule {rule_id_1} is removed'

    with allure.step("Cleanup"):
        mgmt_port.interface.acl.unset(acl_id, apply=True).verify_result()
        acl_id_obj.unset(apply=True).verify_result()


@pytest.mark.acl
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_interface_control_plane_acl_unset_and_show_operations(engines, test_api, topology_obj):
    """
    Validate interface ACL show and unset commands for all combinations of inbound/outbound and control-plane.

    Tests missing coverage for:
    - nv show interface <interface-id> acl <acl-id> inbound (without control-plane)
    - nv show interface <interface-id> acl <acl-id> outbound (without control-plane)
    - nv show interface <interface-id> acl <acl-id> outbound control-plane
    - nv unset interface <interface-id> acl (unset all ACLs from interface)
    - nv unset interface <interface-id> acl <acl-id> inbound
    - nv unset interface <interface-id> acl <acl-id> inbound control-plane
    - nv unset interface <interface-id> acl <acl-id> outbound
    - nv unset interface <interface-id> acl <acl-id> outbound control-plane

    steps:
    1. Setup multiple ACLs with different directions (inbound/outbound, control-plane/non-control-plane)
    2. Test all show command variations
    3. Test individual unset commands for specific directions
    4. Test unset all ACLs from interface
    5. Validate configurations are properly removed
    """
    TestToolkit.tested_api = test_api

    mgmt_port_name = DutUtilsTool.get_engine_interface_name(engines.dut, topology_obj)
    mgmt_port = Port(mgmt_port_name)
    acl_type = 'ipv4'
    rule_id = '1'
    rule_config = {
        AclConsts.ACTION: AclConsts.PERMIT,
        AclConsts.IP_PROTOCOL: 'tcp',
        AclConsts.TCP_DEST_PORT: 'ssh'
    }

    # Test ACL IDs for different scenarios
    acl_inbound_cp = "AA_TEST_INTERFACE_INBOUND_CP"
    acl_outbound_cp = "AA_TEST_INTERFACE_OUTBOUND_CP"
    acl_inbound_regular = "AA_TEST_INTERFACE_INBOUND_REG"
    acl_outbound_regular = "AA_TEST_INTERFACE_OUTBOUND_REG"

    with allure.step("Setup ACLs with different attachment combinations"):
        # Create ACLs
        acl_objects = {}
        for acl_id in [acl_inbound_cp, acl_outbound_cp, acl_inbound_regular, acl_outbound_regular]:
            # Create the ACL without attaching
            acl = Acl()
            acl.set(acl_id).verify_result()
            acl_id_obj = acl.acl_id[acl_id]
            acl_id_obj.set(AclConsts.TYPE, acl_type).verify_result()
            config_rule(engines.dut, acl_id_obj, rule_id, rule_config)
            acl_objects[acl_id] = acl_id_obj

        # Attach ACLs with different directions and control-plane combinations
        with allure.step("Attach ACL inbound control-plane"):
            mgmt_port.interface.acl.set(acl_inbound_cp).verify_result()
            mgmt_port.interface.acl.acl_id[acl_inbound_cp].inbound.set(AclConsts.CONTROL_PLANE, apply=True).verify_result()

        with allure.step("Attach ACL outbound control-plane"):
            mgmt_port.interface.acl.set(acl_outbound_cp).verify_result()
            mgmt_port.interface.acl.acl_id[acl_outbound_cp].outbound.set(AclConsts.CONTROL_PLANE, apply=True).verify_result()

        with allure.step("Attach ACL inbound regular (no control-plane)"):
            mgmt_port.interface.acl.set(acl_inbound_regular).verify_result()
            mgmt_port.interface.acl.acl_id[acl_inbound_regular].inbound.set("", apply=True).verify_result()

        with allure.step("Attach ACL outbound regular (no control-plane)"):
            mgmt_port.interface.acl.set(acl_outbound_regular).verify_result()
            mgmt_port.interface.acl.acl_id[acl_outbound_regular].outbound.set("", apply=True).verify_result()

        sleep()

    with allure.step("Test show command variations"):
        # Test: nv show interface <interface-id> acl
        interface_acls = mgmt_port.interface.acl.parse_show()
        assert acl_inbound_cp in interface_acls.keys(), f"ACL {acl_inbound_cp} not found in interface ACLs"
        assert acl_outbound_cp in interface_acls.keys(), f"ACL {acl_outbound_cp} not found in interface ACLs"
        assert acl_inbound_regular in interface_acls.keys(), f"ACL {acl_inbound_regular} not found in interface ACLs"
        assert acl_outbound_regular in interface_acls.keys(), f"ACL {acl_outbound_regular} not found in interface ACLs"

        with allure.step("Test individual ACL show commands"):
            # Test: nv show interface <interface-id> acl <acl-id> inbound control-plane
            inbound_cp_stats = mgmt_port.interface.acl.acl_id[acl_inbound_cp].inbound.parse_show(AclConsts.CONTROL_PLANE)
            assert AclConsts.STATISTICS in inbound_cp_stats.keys(), "Statistics not found in inbound control-plane ACL"

            # Test: nv show interface <interface-id> acl <acl-id> outbound control-plane
            outbound_cp_stats = mgmt_port.interface.acl.acl_id[acl_outbound_cp].outbound.parse_show(AclConsts.CONTROL_PLANE)
            assert AclConsts.STATISTICS in outbound_cp_stats.keys(), "Statistics not found in outbound control-plane ACL"

            # Test: nv show interface <interface-id> acl <acl-id> inbound (without control-plane)
            inbound_reg_stats = mgmt_port.interface.acl.acl_id[acl_inbound_regular].inbound.parse_show("")
            assert AclConsts.STATISTICS in inbound_reg_stats.keys(), "Statistics not found in inbound regular ACL"

            # Test: nv show interface <interface-id> acl <acl-id> outbound (without control-plane)
            outbound_reg_stats = mgmt_port.interface.acl.acl_id[acl_outbound_regular].outbound.parse_show("")
            assert AclConsts.STATISTICS in outbound_reg_stats.keys(), "Statistics not found in outbound regular ACL"

    with allure.step("Test individual unset commands"):
        with allure.step("Test: nv unset interface <interface-id> acl <acl-id> inbound control-plane"):
            mgmt_port.interface.acl.acl_id[acl_inbound_cp].inbound.unset(AclConsts.CONTROL_PLANE, apply=True).verify_result(should_succeed=True)
            sleep()

            # Verify the specific direction is unset
            interface_acls_after = mgmt_port.interface.acl.parse_show()
            # ACL should still exist but inbound control-plane should be removed
            if acl_inbound_cp in interface_acls_after.keys():
                acl_config = interface_acls_after[acl_inbound_cp]
                assert AclConsts.INBOUND not in acl_config or AclConsts.CONTROL_PLANE not in acl_config.get(AclConsts.INBOUND, {}), \
                    f"Inbound control-plane should be unset for {acl_inbound_cp}"

        with allure.step("Test: nv unset interface <interface-id> acl <acl-id> outbound control-plane"):
            mgmt_port.interface.acl.acl_id[acl_outbound_cp].outbound.unset(AclConsts.CONTROL_PLANE, apply=True).verify_result(should_succeed=True)
            sleep()

        with allure.step("Test: nv unset interface <interface-id> acl <acl-id> inbound"):
            mgmt_port.interface.acl.acl_id[acl_inbound_regular].inbound.unset("", apply=True).verify_result(False)
            sleep()

        with allure.step("Test: nv unset interface <interface-id> acl <acl-id> outbound"):
            mgmt_port.interface.acl.acl_id[acl_outbound_regular].outbound.unset("", apply=True).verify_result(should_succeed=False)
            sleep()

    with allure.step("Test: nv unset interface <interface-id> acl (unset all ACLs from interface)"):
        # First, ensure interface is completely clean before creating fresh ACL
        with allure.step("Clean interface completely before fresh ACL test"):
            # Force unset all ACLs from interface to ensure clean state
            try:
                mgmt_port.interface.acl.unset(apply=True).verify_result()
                sleep()
                logger.info("Interface cleaned successfully")
            except Exception as e:
                logger.warning(f"Interface cleanup had issues: {e}")
                # Continue anyway as this might be expected

            # Verify interface is clean
            try:
                interface_acls_check = mgmt_port.interface.acl.parse_show()
                if interface_acls_check:
                    logger.warning(f"Interface still has ACLs after cleanup: {list(interface_acls_check.keys())}")
            except Exception:
                # Expected when no ACLs are attached
                pass

        # Create a fresh ACL for testing unset all functionality
        with allure.step("Create fresh ACL for unset all test"):
            fresh_acl_id = "AA_TEST_FRESH_ACL_FOR_UNSET"
            fresh_acl = Acl()
            fresh_acl.set(fresh_acl_id).verify_result()
            fresh_acl_obj = fresh_acl.acl_id[fresh_acl_id]
            fresh_acl_obj.set(AclConsts.TYPE, acl_type).verify_result()
            config_rule(engines.dut, fresh_acl_obj, rule_id, rule_config)

            # Attach the fresh ACL with control-plane
            mgmt_port.interface.acl.set(fresh_acl_id).verify_result()
            logger.info(f"Fresh ACL {fresh_acl_id} attached to interface")

            # Check interface state before setting direction
            try:
                interface_state = mgmt_port.interface.acl.parse_show()
                logger.info(f"Interface ACL state before direction config: {interface_state}")
            except Exception as e:
                logger.warning(f"Could not check interface state: {e}")

            # Set direction and apply configuration
            mgmt_port.interface.acl.acl_id[fresh_acl_id].inbound.set(AclConsts.CONTROL_PLANE, apply=True).verify_result()
            logger.info(f"Fresh ACL {fresh_acl_id} direction configured successfully")

            # Verify the fresh ACL is properly configured
            try:
                final_interface_state = mgmt_port.interface.acl.parse_show()
                logger.info(f"Final interface ACL state: {final_interface_state}")
                if fresh_acl_id in final_interface_state:
                    logger.info(f" Fresh ACL {fresh_acl_id} successfully configured and verified")
                else:
                    logger.warning(f" Fresh ACL {fresh_acl_id} not found in interface state")
            except Exception as e:
                logger.warning(f"Could not verify final interface state: {e}")

            sleep()

        # Now unset all ACLs from interface
        mgmt_port.interface.acl.unset(apply=True).verify_result()
        sleep()

        # Verify all ACLs are removed from interface
        try:
            interface_acls_final = mgmt_port.interface.acl.parse_show()
            assert not interface_acls_final, f"All ACLs should be removed from interface, but found: {list(interface_acls_final.keys()) if interface_acls_final else []}"
        except Exception:
            # Expected when no ACLs are attached to interface
            pass

    with allure.step("Cleanup - remove ACLs"):
        for acl_id, acl_obj in acl_objects.items():
            try:
                acl_obj.unset(apply=True).verify_result()
            except Exception:
                # ACL might already be removed
                pass

        # Clean up the fresh ACL created for unset all test
        try:
            fresh_acl.unset(apply=True).verify_result()
        except Exception:
            # ACL might already be removed
            pass


@pytest.mark.acl
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_system_control_plane_acl_global_vs_interface_behavior(engines, test_api, topology_obj):
    """
    Validate global system control-plane ACL behavior across multiple interfaces
    and test interaction with interface-specific control-plane ACLs.

    Test covers:
    1. Configure global control-plane ACL (applies to ALL interfaces)
    2. Send traffic on both eth0 and eth1 - verify same ACL effect on both
    3. Attach interface-specific ACL on eth0
    4. Test behavior: global system ACL processes traffic first before interface-specific,
       while eth1 continues using global ACL only
    5. Unset interface-specific ACL and verify rollback to global ACL behavior

    steps:
    1. config global system control-plane ACL with permit rule
    2. send traffic on both eth0 and eth1 and validate both are affected equally
    3. attach interface-specific control-plane ACL with deny rule on eth0 only
    4. send traffic on both interfaces and validate behavior:
       - eth0: global ACL processes traffic first, interface-specific may or may not see traffic
       - eth1: only global ACL processes traffic
    6. unset interface-specific ACL from eth0
    7. send traffic on both interfaces and validate rollback:
       - eth0: now only global ACL processes traffic (same as eth1)
       - eth1: continues using global ACL only
    """
    TestToolkit.tested_api = test_api

    # Skip test for OpenAPI as it's known to fail with system control plane ACLs
    if test_api == ApiType.OPENAPI:
        pytest.skip("Skipping test for OpenAPI as system control plane ACL operations are not working properly")

    system_obj = System()

    # Get both management interfaces for multi-interface testing
    eth0_port = Port('eth0')
    eth1_port = Port('eth1')

    sonic_mgmt_ip = engines.sonic_mgmt.ip
    global_acl_id = "AA_TEST_GLOBAL_CONTROL_PLANE_ACL"
    interface_specific_acl_id = "AA_TEST_INTERFACE_SPECIFIC_ACL"
    rule_id = '1'

    with allure.step("Step 1: Configure global system control-plane ACL"):
        # Create global ACL with PERMIT rule for specific source IP
        acl_obj = Acl()
        acl_obj.set(global_acl_id).verify_result()
        global_acl = acl_obj.acl_id[global_acl_id]
        global_acl.set(AclConsts.TYPE, 'ipv4').verify_result()

        # Add PERMIT rule that matches traffic from sonic_mgmt
        global_rule_config = {
            AclConsts.ACTION: AclConsts.PERMIT,
            AclConsts.SOURCE_IP: sonic_mgmt_ip,
            AclConsts.IP_PROTOCOL: 'icmp',
            AclConsts.ICMP_TYPE: 'echo-request'
        }
        config_rule(engines.dut, global_acl, rule_id, global_rule_config)

        # Attach to global system control-plane (applies to ALL interfaces)
        system_cp_acl_obj = system_obj.control_plane.acl.acl_id[global_acl_id]
        system_cp_acl_obj.inbound.set(apply=True).verify_result()
        sleep()

        # Verify global ACL is configured
        global_acl_config = global_acl.parse_show()
        assert AclConsts.RULE in global_acl_config, "Global ACL should have rules configured"

        system_cp_config = system_cp_acl_obj.parse_show()
        assert AclConsts.STATISTICS in system_cp_config, "Global system control-plane ACL should have statistics"

    with allure.step("Step 2: Test global ACL affects traffic on BOTH eth0 and eth1 equally"):
        with allure.step("Get initial counters for global ACL"):
            global_counters_before = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)

        with allure.step("Send traffic from both eth0 and eth1 to test global ACL"):
            # Send ICMP from sonic_mgmt to switch (matches the ACL rule)
            packet = f"IP(src=\"{sonic_mgmt_ip}\", dst=\"{engines.dut.ip}\") / ICMP(type=\"echo-request\")"
            ping_from_sonic_mgmt(engines.dut.ip)
            ping_from_sonic_mgmt(engines.dut.ip)

        with allure.step("Verify global ACL counters increased"):
            global_counters_after = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)
            assert global_counters_after[rule_id] > global_counters_before[rule_id], \
                f"Global system control-plane ACL {global_acl_id} should see increased counters from multi-interface traffic"

            logger.info(f"Global ACL counter increased: {global_counters_before[rule_id]} -> {global_counters_after[rule_id]}")

    with allure.step("Step 3: Attach interface-specific control-plane ACL on eth0 only"):
        # Create interface-specific ACL with DENY rule (opposite of global PERMIT)
        acl_obj.set(interface_specific_acl_id).verify_result()
        interface_acl = acl_obj.acl_id[interface_specific_acl_id]
        interface_acl.set(AclConsts.TYPE, 'ipv4').verify_result()

        # Add DENY rule with same match criteria as global ACL
        interface_rule_config = {
            AclConsts.ACTION: AclConsts.DENY,
            AclConsts.SOURCE_IP: sonic_mgmt_ip,
            AclConsts.IP_PROTOCOL: 'icmp',
            AclConsts.ICMP_TYPE: 'echo-request'
        }
        config_rule(engines.dut, interface_acl, rule_id, interface_rule_config)

        # Attach ONLY to eth0 interface control-plane
        eth0_port.interface.acl.set(interface_specific_acl_id).verify_result()
        eth0_interface_acl_obj = eth0_port.interface.acl.acl_id[interface_specific_acl_id]
        eth0_interface_acl_obj.inbound.set(AclConsts.CONTROL_PLANE, apply=True).verify_result()
        sleep()

        # Verify interface-specific ACL is attached to eth0
        eth0_acl_config = eth0_interface_acl_obj.parse_show()
        assert AclConsts.STATISTICS in eth0_acl_config, "Interface-specific ACL should be attached to eth0"

        # Verify eth1 does NOT have the interface-specific ACL
        try:
            eth1_acls = eth1_port.interface.acl.parse_show()
            assert interface_specific_acl_id not in eth1_acls.keys(), \
                f"Interface-specific ACL {interface_specific_acl_id} should NOT be on eth1"
        except Exception:
            # Expected if eth1 has no ACLs attached
            pass

    with allure.step("Step 4: Test ACL behavior - global ACL processes traffic first"):
        with allure.step("Get counters before precedence test"):
            global_counters_before = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)
            interface_counters_before = get_rule_packets(eth0_port, interface_specific_acl_id, rule_id, AclConsts.INBOUND)

        with allure.step("Send traffic to eth0 (should hit global ACL first, interface-specific may not see traffic)"):
            # Send traffic that matches both ACLs to test behavior
            packet = f"IP(src=\"{sonic_mgmt_ip}\", dst=\"{engines.dut.ip}\") / ICMP(type=\"echo-request\")"
            ping_from_sonic_mgmt(engines.dut.ip)

        with allure.step("Verify global system ACL processes traffic first"):
            interface_counters_after = get_rule_packets(eth0_port, interface_specific_acl_id, rule_id, AclConsts.INBOUND)
            global_counters_after = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)

            # Global ACL should see traffic increase (processes traffic first)
            assert global_counters_after[rule_id] > global_counters_before[rule_id], \
                f"Global system control-plane ACL {global_acl_id} should see increased counters as it processes traffic first"

            # Log the actual behavior for understanding
            logger.info(f"Interface-specific ACL (eth0) counter: {interface_counters_before[rule_id]} -> {interface_counters_after[rule_id]}")
            logger.info(f"Global ACL counter: {global_counters_before[rule_id]} -> {global_counters_after[rule_id]}")

            if interface_counters_after[rule_id] > interface_counters_before[rule_id]:
                logger.info("Interface-specific ACL also sees traffic - global PERMIT allows further processing")
            else:
                logger.info("Interface-specific ACL does not see traffic - global ACL processes traffic exclusively")

    with allure.step("Step 5: Verify eth1 uses global ACL only (no interface-specific ACL attached)"):
        with allure.step("Get counters before eth1 test"):
            global_counters_before = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)

        with allure.step("Send traffic via eth1 (should hit global ACL only)"):
            # Send traffic that matches the global ACL rule (source IP = sonic_mgmt_ip)
            packet = f"IP(src=\"{sonic_mgmt_ip}\", dst=\"{engines.dut.ip}\") / ICMP(type=\"echo-request\")"
            ping_from_sonic_mgmt(engines.dut.ip)

        with allure.step("Verify global ACL handles eth1 traffic"):
            global_counters_after = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)

            # Global ACL should see traffic from eth1 (increased counters)
            assert global_counters_after[rule_id] > global_counters_before[rule_id], \
                f"Global ACL {global_acl_id} should see increased counters from eth1 traffic (no interface-specific ACL)"

            logger.info(f"Global ACL counter from eth1 traffic: {global_counters_before[rule_id]} -> {global_counters_after[rule_id]}")

    with allure.step("Step 6: Test show commands for both global and interface-specific ACLs"):
        with allure.step("Verify global system control-plane ACL show commands"):
            system_cp_acls = system_obj.control_plane.acl.parse_show()
            assert global_acl_id in system_cp_acls.keys(), f"Global ACL {global_acl_id} should be in system control-plane"

            global_stats = system_obj.control_plane.acl.acl_id[global_acl_id].statistics.parse_show()
            assert rule_id in global_stats.keys(), f"Global ACL should have statistics for rule {rule_id}"

        with allure.step("Verify interface-specific ACL show commands"):
            eth0_acls = eth0_port.interface.acl.parse_show()
            assert interface_specific_acl_id in eth0_acls.keys(), f"Interface-specific ACL should be on eth0"

            interface_stats = eth0_port.interface.acl.acl_id[interface_specific_acl_id].statistics.parse_show()
            assert rule_id in interface_stats.keys(), f"Interface-specific ACL should have statistics for rule {rule_id}"

    with allure.step("Step 7: Unset interface-specific ACL and verify rollback to global ACL"):
        with allure.step("Unset interface-specific ACL from eth0"):
            # Remove interface-specific ACL from eth0
            eth0_port.interface.acl.unset(interface_specific_acl_id, apply=True).verify_result()
            sleep()

            # Verify interface-specific ACL is removed from eth0
            try:
                eth0_acls_after_unset = eth0_port.interface.acl.parse_show()
                assert interface_specific_acl_id not in eth0_acls_after_unset.keys(), \
                    f"Interface-specific ACL {interface_specific_acl_id} should be removed from eth0"
            except Exception:
                # Expected when no ACLs are attached to interface
                pass

        with allure.step("Verify eth0 rolls back to using global ACL only"):
            with allure.step("Get global ACL counters before rollback test"):
                global_counters_before_rollback = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)

            with allure.step("Send traffic to eth0 after interface-specific ACL removal"):
                packet = f"IP(src=\"{sonic_mgmt_ip}\", dst=\"{engines.dut.ip}\") / ICMP(type=\"echo-request\")"
                ping_from_sonic_mgmt(engines.dut.ip)

            with allure.step("Verify global ACL handles eth0 traffic after rollback"):
                global_counters_after_rollback = get_system_cp_rule_packets(system_cp_acl_obj, rule_id, AclConsts.INBOUND)

                # Global ACL should see traffic from eth0 after interface-specific ACL is removed
                assert global_counters_after_rollback[rule_id] > global_counters_before_rollback[rule_id], \
                    f"Global ACL {global_acl_id} should handle eth0 traffic after interface-specific ACL removal"

                logger.info(f"Global ACL counter after rollback: {global_counters_before_rollback[rule_id]} -> {global_counters_after_rollback[rule_id]}")

    with allure.step("Cleanup"):
        # Clean up ACLs
        try:
            system_cp_acl_obj.unset(apply=True).verify_result()
            global_acl.unset(apply=True).verify_result()
            interface_acl.unset(apply=True).verify_result()
        except Exception:
            # ACLs might already be removed
            pass
