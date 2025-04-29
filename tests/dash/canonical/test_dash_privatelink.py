import logging
from ipaddress import ip_interface, ip_network

import configs.privatelink_config as pl
import ptf.testutils as testutils
import pytest
from constants import LOCAL_PTF_INTF, REMOTE_DUT_INTF, REMOTE_PTF_MAC, REMOTE_PTF_INTF, DUT_MAC, LOCAL_PTF_MAC, LOCAL_CA_IP, VXLAN_UDP_BASE_SRC_PORT
from gnmi_utils import apply_messages
from packets import outbound_pl_packets, inbound_pl_packets
from tests.common import config_reload


logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]

DUT_IP_ON_DUT_HOST_A_0 = "10.10.10.2"
HOST_IP_ON_HOST_DUT_A_0 = "10.10.10.1"


def get_ptf_port(duthost, dut_port):
    lldp_table_list = duthost.show_and_parse('show lldp table')
    ptf_port = ''
    for lldp_info in lldp_table_list:
        if lldp_info["localport"] == dut_port:
            ptf_port = lldp_info["remoteportdescr"].split(' ')[-1]
    if not ptf_port:
        raise Exception(f"Not find the ptf port for dut port {dut_port}")
    logger.info(f"ptf port is {ptf_port} for dut port {dut_port}")
    return ptf_port


@pytest.fixture(scope="module")
def dash_pl_config(duthost, config_facts, minigraph_facts):
    dash_info = {DUT_MAC: config_facts["DEVICE_METADATA"]["localhost"]["mac"],
                 LOCAL_CA_IP: "10.2.2.2",
                 LOCAL_PTF_INTF: 0,
                 LOCAL_PTF_MAC: 'a0:88:c2:7c:d8:e6',
                 REMOTE_PTF_INTF: 0,
                 REMOTE_PTF_MAC: 'a0:88:c2:7c:d8:e7',
                 REMOTE_DUT_INTF: 0
                 }
    return dash_info


@pytest.fixture(scope="module")
def apply_switch_basic_config(duthost, dpuhost, ptfhost, dpuhosts, dpu_index):
    dpuhost = dpuhosts[dpu_index]
    npu_interface_ip = dpuhost.npu_data_port_ip
    logger.info("Add ip to npu dpu data port")
    cmd_add_npu_dpu_port_ip = f'sudo config interface ip add {dpuhost.data_port_on_npu} {npu_interface_ip}/31'
    duthost.shell(cmd_add_npu_dpu_port_ip)

    logger.info("Add dut ip for port connecting to  port 0 on ptf host")
    cmd_add_dut_ip_on_dut_host_a_0 = f'sudo config interface ip add Ethernet0  {DUT_IP_ON_DUT_HOST_A_0}/24'
    duthost.shell(cmd_add_dut_ip_on_dut_host_a_0)

    ptf_port = get_ptf_port(duthost, "Ethernet0")

    logger.info("Add ptf ip for port host a")
    cmd_add_host_ip_on_host_a_0 = f'ip addr add  {HOST_IP_ON_HOST_DUT_A_0}/24 dev {ptf_port}'
    ptfhost.shell(cmd_add_host_ip_on_host_a_0)

    yield

    logger.info("Remove the ip of npu dpu data port")
    cmd_remove_npu_dpu_port_ip = f'sudo config interface ip remove {dpuhost.data_port_on_npu} {npu_interface_ip}/31'
    duthost.shell(cmd_remove_npu_dpu_port_ip)

    logger.info("Remove dut ip for port connecting to port 0 on ptf host a")
    cmd_remove_npu_dpu_port_ip = f'sudo config interface ip remove Ethernet0  {DUT_IP_ON_DUT_HOST_A_0}/24'
    duthost.shell(cmd_remove_npu_dpu_port_ip)

    logger.info("Remove ptf ip for port host a")
    cmd_del_host_ip_on_host_a_0 = f'ip addr del  {HOST_IP_ON_HOST_DUT_A_0}/24 dev {ptf_port}'
    ptfhost.shell(cmd_del_host_ip_on_host_a_0)


@pytest.fixture(scope="module")
def apply_dpu_basic_config(dpuhost, apply_switch_basic_config, dpuhosts, dpu_index):
    dpuhost = dpuhosts[dpu_index]
    dpu_ip = dpuhost.dpu_data_port_ip
    npu_interface_ip = dpuhost.npu_data_port_ip
    logger.info("Add ip to Ethernet0")
    cmd_add_data_port_ip = f"sudo config interface ip  add Ethernet0 {dpu_ip}/31"
    dpuhost.shell(cmd_add_data_port_ip)

    logger.info("Add ip to Loopback0")
    cmd_add_l0_ip = f"sudo config interface ip  add Loopback0 {pl.APPLIANCE_VIP}/255.255.255.255"
    dpuhost.shell(cmd_add_l0_ip)

    logger.info("Add ip default route via Ethernet0")
    cmd_add_npu_neig_route = f"sudo ip route add {pl.PE_PA}/32 via {npu_interface_ip} dev Ethernet0"
    dpuhost.shell(cmd_add_npu_neig_route)



@pytest.fixture(scope="module", autouse=True)
def add_npu_static_routes(duthost, dpu_index, apply_switch_basic_config, apply_dpu_basic_config, dpuhosts):
    dpuhost = dpuhosts[dpu_index]
    cmds = []
    vm_nexthop_ip = HOST_IP_ON_HOST_DUT_A_0
    pe_nexthop_ip = HOST_IP_ON_HOST_DUT_A_0

    cmds.append(f"ip route replace {pl.APPLIANCE_VIP}/32 via {dpuhost.dpu_data_port_ip}")
    cmds.append(f"ip route replace {pl.VM1_PA}/32 via {vm_nexthop_ip}")
    cmds.append(f"ip route replace {pl.PE_PA}/32 via {pe_nexthop_ip}")
    logger.info(f"Adding static routes: {cmds}")
    duthost.shell_cmds(cmds=cmds)

    yield

    cmds = []
    cmds.append(f"ip route del {pl.APPLIANCE_VIP}/32 via {dpuhost.dpu_data_port_ip}")
    cmds.append(f"ip route del {pl.VM1_PA}/32 via {vm_nexthop_ip}")
    cmds.append(f"ip route del {pl.PE_PA}/32 via {pe_nexthop_ip}")
    logger.info(f"Removing static routes: {cmds}")
    duthost.shell_cmds(cmds=cmds)


@pytest.fixture(autouse=True, scope="module")
def common_setup_teardown(localhost, duthost, ptfhost, dpu_index, dpuhosts, skip_config, set_vxlan_udp_sport_range):
    if skip_config:
        return
    dpuhost = dpuhosts[dpu_index]
    logger.info(pl.ROUTING_TYPE_PL_CONFIG)
    base_config_messages = {
        **pl.APPLIANCE_CONFIG,
        **pl.ROUTING_TYPE_PL_CONFIG,
        **pl.VNET_CONFIG,
        **pl.ROUTE_GROUP1_CONFIG,
        **pl.METER_POLICY_V4_CONFIG
    }
    logger.info(base_config_messages)

    apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index)

    route_and_mapping_messages = {
        **pl.PE_VNET_MAPPING_CONFIG,
        **pl.PE_SUBNET_ROUTE_CONFIG,
        **pl.VM_SUBNET_ROUTE_CONFIG
    }
    logger.info(route_and_mapping_messages)
    apply_messages(localhost, duthost, ptfhost, route_and_mapping_messages, dpu_index)

    meter_rule_messages = {
        **pl.METER_RULE1_V4_CONFIG,
        **pl.METER_RULE2_V4_CONFIG,
    }
    logger.info(meter_rule_messages)
    apply_messages(localhost, duthost, ptfhost, meter_rule_messages, dpu_index)

    logger.info(pl.ENI_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_CONFIG, dpu_index)

    logger.info(pl.ENI_ROUTE_GROUP1_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpuhost.dpu_index)

    yield
    apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpu_index, False)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_CONFIG, dpu_index, False)
    apply_messages(localhost, duthost, ptfhost, meter_rule_messages, dpu_index, False)
    apply_messages(localhost, duthost, ptfhost, route_and_mapping_messages, dpu_index, False)
    apply_messages(localhost, duthost, ptfhost, base_config_messages, dpu_index, False)
    config_reload(dpuhost, safe_reload=True)


@pytest.mark.parametrize("encap_proto", ["vxlan", "gre"])
def test_privatelink_basic_transform(
    ptfadapter,
    dash_pl_config,
    encap_proto
):

    vm_to_dpu_pkt, exp_dpu_to_pe_pkt = outbound_pl_packets(dash_pl_config, outer_encap=encap_proto)
    pe_to_dpu_pkt, exp_dpu_to_vm_pkt = inbound_pl_packets(dash_pl_config)

    ptfadapter.dataplane.flush()
    testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], vm_to_dpu_pkt, 1)
    testutils.verify_packet_any_port(ptfadapter, exp_dpu_to_pe_pkt, [dash_pl_config[LOCAL_PTF_INTF]])
    testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pe_to_dpu_pkt, 1)
    testutils.verify_packet(ptfadapter, exp_dpu_to_vm_pkt, dash_pl_config[LOCAL_PTF_INTF])
