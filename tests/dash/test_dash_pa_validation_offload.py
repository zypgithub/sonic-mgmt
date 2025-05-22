import re
import logging
import configs.privatelink_config as pl_config_eni0
import configs.privatelink_config_1 as pl_config_eni1
import ptf.testutils as testutils
import pytest

from ipaddress import ip_address, ip_network
from constants import LOCAL_PTF_INTF
from gnmi_utils import apply_messages
from copy import deepcopy
from packets import outbound_pl_packets
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.helpers.assertions import pytest_assert
from tests.common import config_reload


ACL_TABLE_KEY_PATTERN = "ACL_TABLE_TABLE:DASH_PA_VALIDATION_DPU"
ACL_DROP_RULE_KEY_PATTERN = "ACL_RULE_TABLE:DASH_PA_VALIDATION_DPU.*:RULE.*DROP"
ACL_PERMIT_RULE_KEY_PATTERN = "ACL_RULE_TABLE:DASH_PA_VALIDATION_DPU.*:RULE(?!.*DROP)"

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t1'),
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(scope="module")
def dpu_duts(dpuhosts, dpuhost):
    next_dpuhost = dpuhosts[(dpuhost.dpu_index + 1) % len(dpuhosts)]
    return [dpuhost, next_dpuhost]


@pytest.fixture(scope="module")
def apply_basic_config(duthost, dpu_duts):
    ptf_gateway_ip = "10.0.0.1"
    for index, dpuhost in enumerate(dpu_duts):
        loopback0_ip = eval(f"pl_config_eni{index}").APPLIANCE_VIP
        npu_data_port_ip = dpuhost.npu_data_port_ip
        dpu_data_port_ip = dpuhost.dpu_data_port_ip
        dataplane_mask_length = dpuhost.dataplane_mask_length
        dpu_npu_port_name = dpuhost.data_port_on_npu
        outbound_underlay_ip = eval(f"pl_config_eni{index}").PE_PA
        underlay_outbound_to_ptf_route_subnet = ip_network(f'{outbound_underlay_ip}/32').supernet(
            prefixlen_diff=8)

        logger.info("Add ip to npu dpu data ports")
        duthost.shell(f'sudo config interface ip add {dpu_npu_port_name} {npu_data_port_ip}/{dataplane_mask_length}')

        logger.info("Add ip to DPU Ethernet0")
        dpuhost.shell(f"sudo config interface ip add Ethernet0 {dpu_data_port_ip}/{dataplane_mask_length}")

        logger.info("Add ip to Loopback0")
        dpuhost.shell(f"sudo config interface ip add Loopback0 {loopback0_ip}/255.255.255.255")

        logger.info("Add npu to dpu VIP route")
        duthost.shell(f"ip route replace {loopback0_ip}/32 via {dpu_data_port_ip}")

        logger.info("Add underlay outbound to ptf route")
        duthost.shell(f"ip route add {underlay_outbound_to_ptf_route_subnet} via {ptf_gateway_ip}")

        logger.info("Add ip default route via Ethernet0")
        pl_config = eval(f"pl_config_eni{index}")
        dpuhost.shell(
            f"sudo ip route add {pl_config.PE_PA}/32 via {npu_data_port_ip} dev Ethernet0")

    yield

    # TODO: WA for issue RM#4125251 and RM#4129123, remove this after the ticket is closed
    if is_redmine_issue_active([4125251, 4129123])[0]:
        return

    for index, dpuhost in enumerate(dpu_duts):
        loopback0_ip = eval(f"pl_config_eni{index}").APPLIANCE_VIP
        npu_data_port_ip = dpuhost.npu_data_port_ip
        dpu_data_port_ip = dpuhost.dpu_data_port_ip
        dataplane_mask_length = dpuhost.dataplane_mask_length
        dpu_npu_port_name = dpuhost.data_port_on_npu
        outbound_underlay_ip = eval(f"pl_config_eni{index}").PE_PA
        underlay_outbound_to_ptf_route_subnet = ip_network(f'{outbound_underlay_ip}/32').supernet(
            prefixlen_diff=8)

        logger.info("Remove ip default route via Ethernet0")
        pl_config = eval(f"pl_config_eni{index}")
        dpuhost.shell(
            f"sudo ip route del {pl_config.OUTBOUND_UNDERLAY_IP}/32 via {npu_data_port_ip} dev Ethernet0")

        logger.info("Remove underlay outbound to ptf route")
        duthost.shell(f"ip route del {underlay_outbound_to_ptf_route_subnet} via {ptf_gateway_ip}")

        logger.info("Remove npu to dpu VIP route")
        duthost.shell(f"ip route del {loopback0_ip}")

        logger.info("Remove the ip of Loopback0")
        dpuhost.shell(f"sudo config interface ip  remove Loopback0 {loopback0_ip}/255.255.255.255")

        logger.info("Remove ip of Ethernet0")
        dpuhost.shell(f"sudo config interface ip  remove Ethernet0 {dpu_data_port_ip}/{dataplane_mask_length}")

        logger.info("Remove the ip of npu dpu data ports")
        duthost.shell(
            f'sudo config interface ip Remove {dpu_npu_port_name} {npu_data_port_ip}/{dataplane_mask_length}')


def apply_pl_config(localhost, duthost, ptfhost, dpu_index, pl_config):
    logger.info(pl_config.ROUTING_TYPE_PL_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl_config_eni0.ROUTING_TYPE_PL_CONFIG, dpu_index)
    messages1 = {
        **pl_config.APPLIANCE_CONFIG,
        **pl_config.VNET_CONFIG,
        **pl_config.ENI_CONFIG,
        **pl_config.PE1_VNET_MAPPING_CONFIG,
        **pl_config.ROUTE_GROUP1_CONFIG
    }
    logger.info(messages1)
    apply_messages(localhost, duthost, ptfhost, messages1, dpu_index)
    messages2 = {
        **pl_config.PE_SUBNET_ROUTE_CONFIG,
        **pl_config.ENI_ROUTE_GROUP1_CONFIG
    }
    logger.info(messages2)
    apply_messages(localhost, duthost, ptfhost, messages2, dpu_index)
    messages_applied = {
        **pl_config_eni0.ROUTING_TYPE_PL_CONFIG,
        **pl_config.APPLIANCE_CONFIG,
        **pl_config.VNET_CONFIG,
        **pl_config.ENI_CONFIG,
        **pl_config.PE1_VNET_MAPPING_CONFIG,
        **pl_config.ROUTE_GROUP1_CONFIG,
        **pl_config.PE_SUBNET_ROUTE_CONFIG,
        **pl_config.ENI_ROUTE_GROUP1_CONFIG,
    }
    return messages_applied


@pytest.fixture(scope="module", autouse=True)
def common_setup_teardown(localhost, duthost, ptfhost, dpu_duts, apply_basic_config):
    messages = apply_pl_config(localhost, duthost, ptfhost, dpu_duts[0].dpu_index, pl_config_eni0)

    yield

    logger.info(f"Clean the pl config: {messages}")
    if is_redmine_issue_active([4125251, 4129123])[0]:
        config_reload_dpu_and_switch(duthost, dpu_duts)
    else:
        apply_messages(localhost, duthost, ptfhost, messages, dpu_duts[0].dpu_index, set_db=False)


def toggle_dpu_control_plane_state(duthost, state, dpu_index_list):
    for dpu_index in dpu_index_list:
        redis_cmd = f'redis-cli -p 6380 -h redis_chassis.server -n 13' \
                    f' HSET "DPU_STATE|DPU{dpu_index}" dpu_control_plane_state {state}'
        duthost.shell(redis_cmd)


@pytest.fixture(scope="session", autouse=True)
def turn_on_the_dpu_control_plane_state(duthost, dpuhosts):
    dpu_index_list = list(range(len(dpuhosts)))
    toggle_dpu_control_plane_state(duthost, 'on', dpu_index_list)


def config_reload_dpu_and_switch(duthost, dpuhost_ist):
    for dpuhost in dpuhost_ist:
        dpuhost.shell("sudo config reload -y -f", module_async=True)
    config_reload(duthost, safe_reload=True)


@pytest.fixture(scope="function", autouse=True)
def pa_validation_case_teardown(request, localhost, duthost, ptfhost, dpu_duts):

    yield

    clean_pa_validation_entries(localhost, duthost, ptfhost, dpu_duts[0].dpu_index)
    if "multi_vni" in request.node.name:
        clean_pa_validation_entries(localhost, duthost, ptfhost, dpu_duts[0].dpu_index, vni=66666)
    if "multi_dpu" in request.node.name:
        clean_pa_validation_entries(localhost, duthost, ptfhost, dpu_duts[1].dpu_index)


@pytest.fixture(scope="module")
def expected_ptf_ports(config_facts, minigraph_facts):
    pc_member_config = config_facts["PORTCHANNEL_MEMBER"]
    member_ports = []
    for member_config in pc_member_config.values():
        for member in member_config:
            member_ports.append(member)
    expected_ptf_ports = [minigraph_facts["minigraph_ptf_indices"][port] for port in member_ports]
    logger.info(f"Expecting transformed packet on PTF ports: {expected_ptf_ports}")
    return expected_ptf_ports


def add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, address_list, vni=pl_config_eni0.VM_VNI):
    pa_validation_config = {
        f"DASH_PA_VALIDATION_TABLE:{vni}": {
            "addresses": address_list
        }
    }
    logger.info(pa_validation_config)
    apply_messages(localhost, duthost, ptfhost, pa_validation_config, dpu_index)


def clean_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, vni=pl_config_eni0.VM_VNI):
    pa_validation_config = {
        f"DASH_PA_VALIDATION_TABLE:{vni}": {
            "addresses": []
        }
    }
    logger.info(pa_validation_config)
    apply_messages(localhost, duthost, ptfhost, pa_validation_config, dpu_index, set_db=False)


def check_acl_entries_in_db(duthost, dpu_index, pa_count):
    acl_entries_in_db = duthost.shell(f"redis-cli -n 0 keys *PA_VALIDATION_DPU{dpu_index}*")['stdout_lines']
    acl_table_count = acl_drop_rule_count = acl_permit_rule_count = 0
    for entry in acl_entries_in_db:
        if re.search(ACL_TABLE_KEY_PATTERN, entry):
            acl_table_count += 1
        elif re.search(ACL_DROP_RULE_KEY_PATTERN, entry):
            acl_drop_rule_count += 1
        elif re.search(ACL_PERMIT_RULE_KEY_PATTERN, entry):
            acl_permit_rule_count += 1
    pytest_assert(acl_table_count == 1,
                  f"There should and only be 1 acl table entry of dpu{dpu_index}, actual: {acl_table_count}")
    pytest_assert(acl_drop_rule_count == 1,
                  f"There should and only be 1 acl drop rule entry of dpu{dpu_index}, actual: {acl_drop_rule_count}")
    pytest_assert(acl_permit_rule_count == pa_count,
                  f"The number of acl permit rules of dpu{dpu_index} doesn't equal to the pa count {pa_count}")


def check_no_acl_rules_in_db(duthost, dpu_index):
    acl_entries_in_db = duthost.shell(f"redis-cli -n 0 keys *PA_VALIDATION_DPU{dpu_index}*RULE*")['stdout']
    pytest_assert(acl_entries_in_db == "",
                  f"There are acl entries not cleaned for dpu{dpu_index}:\n{acl_entries_in_db}")


def test_pa_validation_single_dpu_single_vni(ptfadapter, dash_pl_config, localhost, dpu_duts,
                                             duthost, ptfhost, expected_ptf_ports):
    dpu_index = dpu_duts[0].dpu_index
    with allure.step("Add pa validation entries"):
        add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, [pl_config_eni0.VM1_PA])
    with allure.step("Check the ACL entries in db"):
        check_acl_entries_in_db(duthost, dpu_index, 1)
    with allure.step("Send the pa matched packet and check it is received by ptf"):
        pa_matched_pkt, exp_pkt = outbound_pl_packets(dash_pl_config, outer_encap='vxlan')
        ptfadapter.dataplane.flush()
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_matched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Send the pa unmatched packets and check the traffic is not received by ptf"):
        pa_unmatched_pkt = pa_matched_pkt.copy()
        unmatched_pa_ip = ip_address(pa_matched_pkt["IP"].src) + 1
        pa_unmatched_pkt["IP"].src = str(unmatched_pa_ip)
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_unmatched_pkt, 1)
        testutils.verify_no_packet_any(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Add a new pa validation entry for the unmatched source IP address and check the ACL"):
        add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, [unmatched_pa_ip])
        check_acl_entries_in_db(duthost, dpu_index, 2)
    with allure.step("Send the unmatched packet again and check it is received by ptf"):
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_unmatched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Clean the pa validation entries and check the ACL"):
        clean_pa_validation_entries(localhost, duthost, ptfhost, dpu_index)
        check_no_acl_rules_in_db(duthost, dpu_index)
    with allure.step("Send the matched and unmatched packets again and check all packets are received by ptf"):
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_matched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_unmatched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Add the pa validation entry for the matched IP address again"):
        add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, [pl_config_eni0.VM1_PA])
    with allure.step("Send the matched and unmatched packets again and check the result"):
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_matched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_unmatched_pkt, 1)
        testutils.verify_no_packet_any(ptfadapter, exp_pkt, ports=expected_ptf_ports)


def test_pa_validation_single_dpu_multi_vni(ptfadapter, dash_pl_config, dpu_duts,
                                            localhost, duthost, ptfhost, expected_ptf_ports):
    dpu_index = dpu_duts[0].dpu_index
    with allure.step("Add pa validation entries for 2 VNIs on a same DPU"):
        add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, [pl_config_eni0.VM1_PA])
        dummy_vni = 66666
        add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index,
                                  [pl_config_eni0.VM1_PA], vni=dummy_vni)
    with allure.step("Send the pa matched packet and check it is received by ptf"):
        pa_matched_pkt, exp_pkt = outbound_pl_packets(dash_pl_config, outer_encap='vxlan')
        ptfadapter.dataplane.flush()
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_matched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Send the pa unmatched packets and check the traffic is not received by ptf"):
        pa_unmatched_pkt = pa_matched_pkt.copy()
        unmatched_pa_ip = ip_address(pa_matched_pkt["IP"].src) + 1
        pa_unmatched_pkt["IP"].src = str(unmatched_pa_ip)
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_unmatched_pkt, 1)
        testutils.verify_no_packet_any(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Remove the pa validation entry for the dummy vni"):
        clean_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, vni=dummy_vni)
    with allure.step("Send the pa matched packet and check it is received by ptf"):
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_matched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Send the pa unmatched packets and check the traffic is not received by ptf"):
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_unmatched_pkt, 1)
        testutils.verify_no_packet_any(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Remove the pa validation entry for the real vni and add it again"):
        clean_pa_validation_entries(localhost, duthost, ptfhost, dpu_index)
        add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, [pl_config_eni0.VM1_PA])
    with allure.step("Send the pa matched packet and check it is received by ptf"):
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_matched_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=expected_ptf_ports)
    with allure.step("Send the pa unmatched packets and check the traffic is not received by ptf"):
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pa_unmatched_pkt, 1)
        testutils.verify_no_packet_any(ptfadapter, exp_pkt, ports=expected_ptf_ports)


def test_pa_validation_multi_dpu(ptfadapter, dash_pl_config, dpu_duts,
                                 localhost, duthost, ptfhost, expected_ptf_ports):
    dpu_index = dpu_duts[0].dpu_index
    another_dpu_index = dpu_duts[1].dpu_index
    with allure.step("Apply the dash config for another ENI on another DPU"):
        messages = apply_pl_config(localhost, duthost, ptfhost, another_dpu_index, pl_config_eni1)
    with allure.step("Apply the pa validation entries for both ENIs"):
        add_pa_validation_entries(
            localhost, duthost, ptfhost, dpu_index, [pl_config_eni0.VM1_PA])
        add_pa_validation_entries(
            localhost, duthost, ptfhost, another_dpu_index, [pl_config_eni1.VM1_PA])
    try:
        with allure.step("Check the ACL table and rule for ENI0 and ENI1"):
            check_acl_entries_in_db(duthost, dpu_index, 1)
            check_acl_entries_in_db(duthost, another_dpu_index, 1)
        with allure.step("Send the pa matched packets for both ENIs and check they are received by ptf"):
            eni0_pa_matched_pkt, eni0_exp_pkt = outbound_pl_packets(dash_pl_config, outer_encap='vxlan')
            eni1_pa_matched_pkt,  = eni0_pa_matched_pkt.copy()
            eni1_exp_pkt = deepcopy(eni0_exp_pkt)
            eni1_pa_matched_pkt['VXLAN']['Ether'].src = eni1_exp_pkt.exp_pkt['GRE']['Ether'].src = \
                pl_config_eni1.ENI_MAC
            eni1_pa_matched_pkt['IP'].dst = eni1_exp_pkt.exp_pkt['IP'].src = pl_config_eni1.APPLIANCE_VIP
            eni1_exp_pkt.exp_pkt['IP'].dst = pl_config_eni1.PE_PA
            ptfadapter.dataplane.flush()
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni0_pa_matched_pkt, 1)
            testutils.verify_packet_any_port(ptfadapter, eni0_exp_pkt, ports=expected_ptf_ports)
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni1_pa_matched_pkt, 1)
            testutils.verify_packet_any_port(ptfadapter, eni1_exp_pkt, ports=expected_ptf_ports)
        with allure.step("Send the pa unmatched packets for both ENIs and check packets are not received by ptf"):
            eni0_pa_unmatched_pkt = eni0_pa_matched_pkt.copy()
            eni0_unmatched_pa_ip = ip_address(eni0_pa_matched_pkt["IP"].src) + 1
            eni0_pa_unmatched_pkt["IP"].src = str(eni0_unmatched_pa_ip)
            eni1_pa_unmatched_pkt = eni1_pa_matched_pkt.copy()
            eni1_unmatched_pa_ip = ip_address(eni1_pa_matched_pkt["IP"].src) + 1
            eni1_pa_unmatched_pkt["IP"].src = str(eni1_unmatched_pa_ip)
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni0_pa_unmatched_pkt, 1)
            testutils.verify_no_packet_any(ptfadapter, eni0_exp_pkt, ports=expected_ptf_ports)
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni1_pa_unmatched_pkt, 1)
            testutils.verify_no_packet_any(ptfadapter, eni1_exp_pkt, ports=expected_ptf_ports)
        with allure.step("Add a new pa validation entry for the unmatched source IP address for ENI1"):
            add_pa_validation_entries(localhost, duthost, ptfhost, another_dpu_index, [eni1_unmatched_pa_ip])
        with allure.step("Send the pa unmatched packets for ENI0 and check it is not received by ptf"):
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni0_pa_unmatched_pkt, 1)
            testutils.verify_no_packet_any(ptfadapter, eni0_exp_pkt, ports=expected_ptf_ports)
        with allure.step("Send the pa unmatched packets for ENI1 and check it is received by ptf"):
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni1_pa_unmatched_pkt, 1)
            testutils.verify_packet_any_port(ptfadapter, eni1_exp_pkt, ports=expected_ptf_ports)
        with allure.step("Remove the ENI1 pa validation entry for the unmatched source IP address"):
            clean_pa_validation_entries(localhost, duthost, ptfhost, another_dpu_index)
            add_pa_validation_entries(
                localhost, duthost, ptfhost, another_dpu_index, [pl_config_eni1.VM1_PA])
        with allure.step("Add a the pa validation entry for the unmatched source IP address for ENI0"):
            add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, [eni0_unmatched_pa_ip])
        with allure.step("Send the pa unmatched packets for ENI0 and check it is received by ptf"):
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni0_pa_unmatched_pkt, 1)
            testutils.verify_packet_any_port(ptfadapter, eni0_exp_pkt, ports=expected_ptf_ports)
        with allure.step("Send the pa unmatched packets for ENI1 and check it is not received by ptf"):
            testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], eni1_pa_unmatched_pkt, 1)
            testutils.verify_no_packet_any(ptfadapter, eni1_exp_pkt, ports=expected_ptf_ports)
    finally:
        with allure.step("Clean the dash config for ENI1"):
            if is_redmine_issue_active([4125251])[0]:
                config_reload(dpu_duts[1], safe_reload=True)
            else:
                apply_messages(localhost, duthost, ptfhost, messages, another_dpu_index, set_db=False)


def test_pa_validation_dpu_shutdown(localhost, duthost, ptfhost, dpu_duts):
    dpu_index = dpu_duts[0].dpu_index
    another_dpu_index = dpu_duts[1].dpu_index
    with allure.step("Add the pa validation entry for two DPUs"):
        add_pa_validation_entries(localhost, duthost, ptfhost, dpu_index, [pl_config_eni0.VM1_PA])
        add_pa_validation_entries(localhost, duthost, ptfhost, another_dpu_index, [pl_config_eni1.VM1_PA])
    with allure.step("Check the ACL table and rule"):
        check_acl_entries_in_db(duthost, dpu_index, 1)
        check_acl_entries_in_db(duthost, another_dpu_index, 1)
    with allure.step(f"Shutdown the DPU{dpu_index}"):
        # Mock the shutdown by setting the dpu control plane state to down
        toggle_dpu_control_plane_state(duthost, 'down', [dpu_index])
        # TODO: change this after the pmon for smartswitch is available
    with allure.step(f"Check the DPU{dpu_index} ACL table and rule are removed"):
        check_no_acl_rules_in_db(duthost, dpu_index)
    with allure.step(f"Check the DPU{another_dpu_index} DPU ACL table and rule are still there"):
        check_acl_entries_in_db(duthost, another_dpu_index, 1)
    with allure.step("Restart the first DPU and wait for it to boot up"):
        # TODO: add this after the pmon for smartswitch is available
        pass
    with allure.step(f"Check there is no new ACL table and rules added for the DPU{dpu_index}"):
        check_no_acl_rules_in_db(duthost, dpu_index)
