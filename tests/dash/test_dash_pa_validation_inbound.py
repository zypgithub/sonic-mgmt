import logging
import pytest
import ptf.testutils as testutils
import packets
import time

from constants import LOCAL_PTF_INTF, REMOTE_PTF_INTF
from configs import vnet_to_vnet_config
from gnmi_utils import apply_messages
from tests.smart_switch.conftest import SMARTSWITCH_PLATFORMS, copy_proxy_ssh, skip_unsupported_platform, platform # noqa F401
from ipaddress import ip_interface, ip_network
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from tests.smart_switch.conftest import dpuhosts

VIP = "10.2.0.1"

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t1'),
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(scope="module")
def dpuhost(dpuhosts, dpu_index):
    return dpuhosts[dpu_index]


@pytest.fixture(scope="module")
def apply_switch_basic_config(duthost, dpu_index, dpuhost):
    logger.info("Add ip to npu dpu data port")
    duthost.shell(
        f'sudo config interface ip add {dpuhost.data_port} {dpuhost.npu_data_port_ip}/{dpuhost.dataplane_mask_length}')

    yield

    logger.info("Remove the ip of npu dpu data port")
    duthost.shell(f'sudo config interface ip remove '
                  f'{dpuhost.data_port} {dpuhost.npu_data_port_ip}/{dpuhost.dataplane_mask_length}')


def config_reload_dpu(dpuhost):
    dpuhost.shell(f"sudo config reload -y -f")
    time.sleep(100)


@pytest.fixture(scope="module")
def apply_dpu_basic_config(duthost, dpuhost, apply_switch_basic_config):
    logger.info("Add ip to Ethernet0")
    npu_data_port_ip = dpuhost.npu_data_port_ip
    dpu_data_port_ip = dpuhost.dpu_data_port_ip
    dpuhost.shell(f"sudo config interface ip add Ethernet0 {dpu_data_port_ip}/{dpuhost.dataplane_mask_length}")

    logger.info("Add ip to Loopback0")
    dpuhost.shell(f"sudo config interface ip add Loopback0 {VIP}/255.255.255.255")

    logger.info("Add ip default route via Ethernet0")
    dpuhost.shell(f"sudo ip route add default via {npu_data_port_ip} dev Ethernet0")

    yield

    # TODO: WA for issue RM#4125251, remove this after the ticket is closed
    if is_redmine_issue_active([4125251])[0]:
        return

    # TODO: WA for issue RM#4129123, remove this after the ticket is closed
    if is_redmine_issue_active([4129123])[0]:
        config_reload_dpu(dpuhost)
        return

    logger.info("Remove ip default route via Ethernet0")
    duthost.shell(f"sudo ip route del default via {npu_data_port_ip} dev Ethernet0")

    logger.info("Remove the ip of Loopback0")
    duthost.shell(f"sudo config interface ip remove Loopback0 {VIP}/255.255.255.255")

    logger.info("Remove ip of Ethernet0")
    duthost.shell(
        f"sudo config interface ip remove Ethernet0 {dpu_data_port_ip}/{dpuhost.dataplane_mask_length}")


@pytest.fixture(scope="function", autouse=True)
def add_dpu_static_route(duthost, dpuhost, apply_switch_basic_config, apply_dpu_basic_config, dash_config_info):
    remote_pa_ip = "10.0.0.1"
    logger.info("Add npu to dpu route")
    duthost.shell(f"ip route replace {VIP}/32 via {dpuhost.dpu_data_port_ip}")

    logger.info("Add underlay outbound to ptf route")
    underlay_outbound_to_ptf_route_subnet = \
        ip_network(f'{dash_config_info["local_pa_ip"]}/32').supernet(prefixlen_diff=8)
    duthost.shell(f"ip route add {underlay_outbound_to_ptf_route_subnet} via {remote_pa_ip}")

    yield

    logger.info("Remove underlay outbound to ptf route")
    duthost.shell(f"ip route del {underlay_outbound_to_ptf_route_subnet} via {remote_pa_ip}")

    logger.info("Remove npu to dpu VIP route")
    duthost.shell(f"ip route del {VIP}")


@pytest.fixture(scope="function")
def apply_inbound_configs(localhost, duthost, ptfhost, dpuhost, dpu_index):

    config_messages = {
        **vnet_to_vnet_config.APPLIANCE_CONFIG,
        **vnet_to_vnet_config.VNET1_CONFIG,
        **vnet_to_vnet_config.VNET2_CONFIG,
        **vnet_to_vnet_config.ENI_CONFIG,
        **vnet_to_vnet_config.ROUTING_TYPE_CONFIG,
        **vnet_to_vnet_config.VNET_MAPPING_CONFIG,
        **vnet_to_vnet_config.QOS_CONFIG,
        **vnet_to_vnet_config.ROUTE_GROUP_CONFIG,
        **vnet_to_vnet_config.ROUTE_VNET2_CONFIG,
        **vnet_to_vnet_config.ROUTE_RULE_CONFIG,
    }
    apply_messages(localhost, duthost, ptfhost, config_messages, dpu_index)

    yield

    # TODO: WA for issue RM#4125251, remove this after the ticket is closed
    if is_redmine_issue_active([4125251])[0]:
        config_reload_dpu(dpuhost)
        return

    apply_messages(localhost, duthost, ptfhost, config_messages, dpu_index, set=False)


def test_inbound_vnet_pa_validate(ptfadapter, apply_inbound_configs, dash_config_info, acl_default_rule):
    """
    Send VXLAN packets from the remote VNI with PA validation enabled

    1. Send one packet where the source PA (outer source IP) matches the VNET mapping table
        - Expect DPU to forward packet normally
    2. Send one packet where the source PA does not match the mapping table
        - Expect DPU to drop packet
    """
    _,  pa_match_packet, pa_mismatch_packet, expected_packet = packets.inbound_vnet_packets(
        dash_config_info)
    pa_match_packet['IP'].dst = VIP
    pa_mismatch_packet['IP'].dst = VIP
    expected_packet.exp_pkt['IP'].src = VIP
    expected_packet.exp_pkt['IP'].ttl = expected_packet.exp_pkt['IP'].ttl - 1
    logger.info("send the pa matched packet and check it is received by ptf")
    testutils.send(ptfadapter, dash_config_info[REMOTE_PTF_INTF], pa_match_packet, 1)
    testutils.verify_packets_any(ptfadapter, expected_packet, ports=[dash_config_info[LOCAL_PTF_INTF]])
    logger.info("send the pa mismatched packet and check it is not received by ptf")
    testutils.send(ptfadapter, dash_config_info[REMOTE_PTF_INTF], pa_mismatch_packet, 1)
    testutils.verify_no_packet_any(ptfadapter, expected_packet, ports=[dash_config_info[LOCAL_PTF_INTF]])
