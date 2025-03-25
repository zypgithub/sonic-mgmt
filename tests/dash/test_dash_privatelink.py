import logging
import time
from ipaddress import ip_interface, ip_network

import configs.privatelink_config as pl
import ptf.testutils as testutils
import pytest
from constants import LOCAL_PTF_INTF, LOCAL_DUT_INTF, REMOTE_DUT_INTF, REMOTE_PTF_RECV_INTF, REMOTE_PTF_SEND_INTF
from gnmi_utils import apply_messages
from packets import outbound_pl_packets, inbound_pl_packets
from tests.dash.conftest import get_interface_ip
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from tests.common import config_reload

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t1'),
    pytest.mark.skip_check_dut_health
]


"""
Test prerequisites:
- DPU needs the Appliance VIP configured as its loopback IP
- Assign IPs to DPU-NPU dataplane interfaces
- Default route on DPU to NPU
"""


@pytest.fixture(scope="module", autouse=True)
def add_npu_static_routes(duthost, dash_pl_config, dpu_index, apply_switch_basic_config, apply_dpu_basic_config, dpuhosts, skip_config, skip_cleanup):
    dpuhost = dpuhosts[dpu_index]
    if not skip_config:
        cmds = []
        vm_nexthop_ip = get_interface_ip(duthost, dash_pl_config[LOCAL_DUT_INTF]).ip + 1
        pe_nexthop_ip = get_interface_ip(duthost, dash_pl_config[REMOTE_DUT_INTF]).ip + 1

        cmds.append(f"ip route replace {pl.APPLIANCE_VIP}/32 via {dpuhost.dpu_data_port_ip}")
        cmds.append(f"ip route replace {pl.VM1_PA}/32 via {vm_nexthop_ip}")
        cmds.append(f"ip route replace {pl.PE_PA}/32 via {pe_nexthop_ip}")
        logger.info(f"Adding static routes: {cmds}")
        duthost.shell_cmds(cmds=cmds)

    yield

    if not skip_config and not skip_cleanup:
        cmds = []
        cmds.append(f"ip route del {pl.APPLIANCE_VIP}/32 via {dpuhost.dpu_data_port_ip}")
        cmds.append(f"ip route del {pl.VM1_PA}/32 via {vm_nexthop_ip}")
        cmds.append(f"ip route del {pl.PE_PA}/32 via {pe_nexthop_ip}")
        logger.info(f"Removing static routes: {cmds}")
        duthost.shell_cmds(cmds=cmds)


@pytest.fixture(autouse=True, scope="module")
def common_setup_teardown(localhost, duthost, ptfhost, dpu_index, dpuhosts, skip_config):
    if skip_config:
        return
    dpuhost = dpuhosts[dpu_index]
    logger.info(pl.ROUTING_TYPE_PL_CONFIG)
    base_config_messages = {
        **pl.APPLIANCE_CONFIG,
        **pl.ROUTING_TYPE_PL_CONFIG,
        **pl.VNET_CONFIG,
        **pl.ENI_CONFIG,
        **pl.PE_VNET_MAPPING_CONFIG,
        **pl.ROUTE_GROUP1_CONFIG
    }
    logger.info(base_config_messages)

    apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index)

    route_messages = {
        **pl.PE_SUBNET_ROUTE_CONFIG,
        **pl.VM_SUBNET_ROUTE_CONFIG
    }
    logger.info(route_messages)
    apply_messages(localhost, duthost, ptfhost, route_messages, dpuhost.dpu_index)

    logger.info(pl.ENI_ROUTE_GROUP1_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpuhost.dpu_index)

    yield

    config_reload(dpuhost, safe_reload=True)



# added by nvidia
@pytest.fixture(scope="module")
def apply_switch_basic_config(duthost, dpuhosts, dpu_index):
    dpuhost = dpuhosts[dpu_index]
    logger.info("Add ip to npu dpu data port")
    cmd_add_npu_dpu_port_ip = f'sudo config interface ip add {dpuhost.data_port_on_npu} {dpuhost.npu_data_port_ip}/31'
    duthost.shell(cmd_add_npu_dpu_port_ip)

    yield

    logger.info("Remove the ip of npu dpu data port")
    cmd_remove_npu_dpu_port_ip = f'sudo config interface ip Remove {dpuhost.data_port_on_npu} {dpuhost.npu_data_port_ip}/31'
    duthost.shell(cmd_remove_npu_dpu_port_ip)


@pytest.fixture(scope="module")
def apply_dpu_basic_config(dpuhost, apply_switch_basic_config, dpuhosts, dpu_index):
    dpuhost = dpuhosts[dpu_index]
    logger.info("Add ip to Ethernet0")
    cmd_add_data_port_ip = f"sudo config interface ip  add Ethernet0 {dpuhost.dpu_data_port_ip}/31"
    dpuhost.shell(cmd_add_data_port_ip)

    logger.info("Add ip to Loopback0")
    cmd_add_l0_ip = f"sudo config interface ip  add Loopback0 {pl.APPLIANCE_VIP}/255.255.255.255"
    dpuhost.shell(cmd_add_l0_ip)

    logger.info("Add ip underlay route via Ethernet0")
    cmd_add_npu_neig_route = f"sudo ip route add {pl.PE_PA}/32 via {dpuhost.npu_data_port_ip} dev Ethernet0"
    dpuhost.shell(cmd_add_npu_neig_route)

    yield

    if not is_redmine_issue_active([4125251])[0]:
        logger.info("Remove ip default route via Ethernet0")
        cmd_del_npu_neig_route = f"sudo ip route del {pl.PE_PA}/32 via {dpuhost.npu_data_port_ip} dev Ethernet0"
        dpuhost.shell(cmd_del_npu_neig_route)

        logger.info("Remove the ip of Loopback0")
        cmd_remove_l0_ip = f"sudo config interface ip  remove Loopback0 {pl.APPLIANCE_VIP}/255.255.255.255"
        dpuhost.shell(cmd_remove_l0_ip)

        logger.info("Remove ip of Ethernet0")
        cmd_remove_data_port_ip = f"sudo config interface ip  remove Ethernet0 {dpuhost.dpu_data_port_ip}/31"
        dpuhost.shell(cmd_remove_data_port_ip)


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
    testutils.verify_packet_any_port(ptfadapter, exp_dpu_to_pe_pkt, dash_pl_config[REMOTE_PTF_RECV_INTF])
    testutils.send(ptfadapter, dash_pl_config[REMOTE_PTF_SEND_INTF], pe_to_dpu_pkt, 1)
    testutils.verify_packet(ptfadapter, exp_dpu_to_vm_pkt, dash_pl_config[LOCAL_PTF_INTF])
