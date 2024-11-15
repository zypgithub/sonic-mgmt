import logging
from ipaddress import ip_interface, ip_network

import configs.privatelink_config as pl
import ptf.testutils as testutils
import pytest
from constants import LOCAL_PTF_INTF
from gnmi_utils import apply_messages
from packets import outbound_pl_packets
from tests.smart_switch.conftest import SMARTSWITCH_PLATFORMS, copy_proxy_ssh, skip_unsupported_platform, platform # noqa F401
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from tests.common import config_reload

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t1'),
    pytest.mark.usefixtures('copy_proxy_ssh'),
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(scope="module")
def apply_switch_basic_config(duthost, dpuhost, npu_interface_ip):
    logger.info("Add ip to npu dpu data port")
    cmd_add_npu_dpu_port_ip = f'sudo config interface ip add {dpuhost.data_port_on_npu} {npu_interface_ip}/31'
    duthost.shell(cmd_add_npu_dpu_port_ip)

    yield

    logger.info("Remove the ip of npu dpu data port")
    cmd_remove_npu_dpu_port_ip = f'sudo config interface ip Remove {dpuhost.data_port_on_npu} {npu_interface_ip}/31'
    duthost.shell(cmd_remove_npu_dpu_port_ip)


@pytest.fixture(scope="module")
def apply_dpu_basic_config(dpuhost, dpu_ip, npu_interface_ip, apply_switch_basic_config):
    logger.info("Add ip to Ethernet0")
    cmd_add_data_port_ip = f"sudo config interface ip  add Ethernet0 {dpu_ip}/31"
    dpuhost.shell(cmd_add_data_port_ip)

    logger.info("Add ip to Loopback0")
    cmd_add_l0_ip = f"sudo config interface ip  add Loopback0 {pl.SIP}/255.255.255.255"
    dpuhost.shell(cmd_add_l0_ip)

    logger.info("Add ip default route via Ethernet0")
    cmd_add_npu_neig_route = f"sudo ip route add {pl.OUTBOUND_UNDERLAY_IP}/32 via {npu_interface_ip} dev Ethernet0"
    dpuhost.shell(cmd_add_npu_neig_route)

    yield

    if not is_redmine_issue_active([4125251])[0]:
        if is_redmine_issue_active([4129123])[0]:
            config_reload(dpuhost, safe_reload=True)
        else:
            logger.info("Remove ip default route via Ethernet0")
            cmd_del_npu_neig_route = f"sudo ip route del default via {npu_interface_ip} dev Ethernet0"
            dpuhost.shell(cmd_del_npu_neig_route)

            logger.info("Remove the ip of Loopback0")
            cmd_remove_l0_ip = f"sudo config interface ip  remove Loopback0 {pl.SIP}/255.255.255.255"
            dpuhost.shell(cmd_remove_l0_ip)

            logger.info("Remove ip of Ethernet0")
            cmd_remove_data_port_ip = f"sudo config interface ip  remove Ethernet0 {dpu_ip}/31"
            dpuhost.shell(cmd_remove_data_port_ip)


@pytest.fixture(scope="module")
def dpu_ip(npu_interface_ip):
    dpu_ip = ip_interface(npu_interface_ip)
    return dpu_ip.ip + 1


@pytest.fixture(scope="module")
def npu_interface_ip(duthost):
    npu_interface_ip = ip_interface("10.0.0.74")
    return npu_interface_ip.ip


@pytest.fixture(scope="module", autouse=True)
def add_dpu_static_route(duthost, dpu_ip, apply_switch_basic_config, apply_dpu_basic_config):
    remote_pa_ip = "10.0.0.1"
    logger.info("Add npu to dpu VIP route")
    cmd = f"ip route replace {pl.SIP}/32 via {dpu_ip}"
    duthost.shell(cmd)

    logger.info("Add underlay outbound to ptf route")
    underlay_outbound_to_ptf_route_subnet = ip_network(f'{pl.OUTBOUND_UNDERLAY_IP}/32').supernet(prefixlen_diff=8)
    cmd_add_underlay_outbound_to_ptf_route = f"ip route add {underlay_outbound_to_ptf_route_subnet} via {remote_pa_ip}"
    duthost.shell(cmd_add_underlay_outbound_to_ptf_route)

    yield

    logger.info("Remove underlay outbound to ptf route")
    cmd_del_underlay_outboud_to_ptf_route = f"ip route del {underlay_outbound_to_ptf_route_subnet} via {remote_pa_ip}"
    duthost.shell(cmd_del_underlay_outboud_to_ptf_route)

    logger.info("Remove npu to dpu VIP route")
    duthost.shell(f"ip route del {pl.SIP}")


@pytest.fixture(autouse=True)
def common_setup_teardown(localhost, duthost, ptfhost, dpuhost):
    logger.info(pl.ROUTING_TYPE_PL_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ROUTING_TYPE_PL_CONFIG, dpuhost.dpu_index)
    messages1 = {
        **pl.APPLIANCE_CONFIG,
        **pl.VNET_CONFIG,
        **pl.ENI_CONFIG,
        **pl.VNET_MAPPING_CONFIG,
        **pl.ROUTE_GROUP1_CONFIG
    }

    logger.info(messages1)
    apply_messages(localhost, duthost, ptfhost, messages1, dpuhost.dpu_index)

    messages2 = {
        **pl.ROUTE_VNET_CONFIG,
        **pl.ENI_ROUTE_GROUP1_CONFIG
    }

    logger.info(messages2)
    apply_messages(localhost, duthost, ptfhost, messages2, dpuhost.dpu_index)

    yield

    if is_redmine_issue_active([4125251])[0]:
        config_reload(dpuhost, safe_reload=True)
    else:

        logger.info(f"recover messages2: {messages2}")
        apply_messages(localhost, duthost, ptfhost, messages2, dpuhost.dpu_index, set=False)


        logger.info(f"recover messages1: {messages1}")
        apply_messages(localhost, duthost, ptfhost, messages1, dpuhost.dpu_index, set=False)

        logger.info(f"recover pl.ROUTING_TYPE_PL_CONFIG: {pl.ROUTING_TYPE_PL_CONFIG}")
        apply_messages(localhost, duthost, ptfhost, pl.ROUTING_TYPE_PL_CONFIG, dpuhost.dpu_index, set=False)


def test_privatelink_basic_transform(
    ptfadapter,
    dash_pl_config,
    minigraph_facts,
    config_facts,
):
    pc_member_config = config_facts["PORTCHANNEL_MEMBER"]
    member_ports = []
    for member_config in pc_member_config.values():
        for member in member_config:
            member_ports.append(member)

    expected_ptf_ports = [minigraph_facts["minigraph_ptf_indices"][port] for port in member_ports]
    logger.info(f"Expecting transformed packet on PTF ports: {expected_ptf_ports}")
    pkt, exp_pkt = outbound_pl_packets(dash_pl_config)
    ptfadapter.dataplane.flush()
    testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pkt, 10)
    testutils.verify_packet_any_port(ptfadapter, exp_pkt, expected_ptf_ports)
    #(index, rcv_pkt, received) = testutils.verify_packet_any_port(ptfadapter, exp_pkt, None)
