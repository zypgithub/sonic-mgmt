import logging
import pytest
import ptf.testutils as testutils
import packets

from constants import LOCAL_PTF_INTF, REMOTE_PTF_INTF
from configs import vnet_to_vnet_config
from gnmi_utils import apply_messages
from ipaddress import ip_network
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from tests.common import config_reload
from dash_eni_counter_utils import get_eni_counters, get_eni_counter_oid, verify_eni_counter,\
    WAIT_DASH_ENI_COUNTER_READY_TIME, eni_counter_setup
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
import time

VIP = "10.2.0.1"

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t1'),
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(scope="module")
def apply_switch_basic_config(duthost, dpuhost):
    logger.info("Add ip to npu dpu data port")
    duthost.shell(
        f'sudo config interface ip add {dpuhost.data_port_on_npu} {dpuhost.npu_data_port_ip}/{dpuhost.dataplane_mask_length}')

    yield

    logger.info("Remove the ip of npu dpu data port")
    duthost.shell(f'sudo config interface ip remove '
                  f'{dpuhost.data_port_on_npu} {dpuhost.npu_data_port_ip}/{dpuhost.dataplane_mask_length}')


@pytest.fixture(scope="function")
def apply_dpu_basic_config(dpuhost, apply_switch_basic_config, dash_config_info):
    logger.info("Add ip to Ethernet0")
    npu_data_port_ip = dpuhost.npu_data_port_ip
    dpu_data_port_ip = dpuhost.dpu_data_port_ip
    dpuhost.shell(f"sudo config interface ip add Ethernet0 {dpu_data_port_ip}/{dpuhost.dataplane_mask_length}")

    logger.info("Add ip to Loopback0")
    dpuhost.shell(f"sudo config interface ip add Loopback0 {VIP}/255.255.255.255")

    logger.info("Add underlay route via Ethernet0")
    dpuhost.shell(f"sudo ip route add {dash_config_info['local_pa_ip']}/32 via {npu_data_port_ip} dev Ethernet0")

    yield

    # TODO: WA for issue RM#4129123, remove this after the ticket is closed
    if is_redmine_issue_active([4125251])[0]:
        config_reload(dpuhost, safe_reload=True)
        return

    logger.info("Remove ip underlay route via Ethernet0")
    dpuhost.shell(f"sudo ip route del {dash_config_info['local_pa_ip']}/32 via {npu_data_port_ip} dev Ethernet0")

    logger.info("Remove the ip of Loopback0")
    dpuhost.shell(f"sudo config interface ip remove Loopback0 {VIP}/255.255.255.255")

    logger.info("Remove ip of Ethernet0")
    dpuhost.shell(
        f"sudo config interface ip remove Ethernet0 {dpu_data_port_ip}/{dpuhost.dataplane_mask_length}")


@pytest.fixture(scope="function", autouse=True)
def add_static_route_from_npu_to_dpu(duthost, dpuhost, apply_switch_basic_config, apply_dpu_basic_config, dash_config_info):
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
def apply_inbound_configs(localhost, duthost, ptfhost, dpuhost, eni_counter_setup):

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
    apply_messages(localhost, duthost, ptfhost, config_messages, dpuhost.dpu_index)

    yield

    # TODO: WA for issue RM#4125251, remove this after the ticket is closed
    if is_redmine_issue_active([4125251])[0]:
        config_reload(dpuhost, safe_reload=True)
        return

    apply_messages(localhost, duthost, ptfhost, config_messages, dpuhost.dpu_index, set=False)


def test_inbound_pkt_eni_counter(
    ptfadapter,
    apply_inbound_configs,
    dash_config_info,
    acl_default_rule,
    dpuhost
):
    """
    1. Get the eni_counter_before_sending_pkt before sending the dash pkt
    2. Send a inbound pkt, and the pkt pass the pipeline successfully
    3. Get the eni_counter_after_sending_pkt after sending the dash pkt
    4. Check the following counter change as follows by comparing eni_counter_before_sending_pkt
    with eni_counter_after_sending_pkt
            SAI_ENI_STAT_FLOW_CREATED: +1
            SAI_ENI_STAT_INBOUND_RX_BYTES:  +len(packet)
            SAI_ENI_STAT_INBOUND_RX_PACKETS: +1
            SAI_ENI_STAT_RX_PACKETS: +1
            SAI_ENI_STAT_RX_BYTES:   +len(packet)
    5. Send n packets with mismatched vni
    6. Check SAI_ENI_STAT_INBOUND_ROUTING_ENTRY_MISS_DROP_PACKETS increase n
    """
    eni = dash_config_info["eni"]
    eni_counter_oid = get_eni_counter_oid(dpuhost, eni)
    packet_len = 150
    packet_number = 1

    _, pa_match_packet, pa_mismatch_packet, expected_packet = packets.inbound_vnet_packets(
        dash_config_info, inner_extra_conf={}, inner_packet_type='tcp')
    pa_match_packet['IP'].dst = VIP
    pa_mismatch_packet['IP'].dst = VIP
    expected_packet.exp_pkt['IP'].src = VIP
    expected_packet.exp_pkt['IP'].ttl = expected_packet.exp_pkt['IP'].ttl - 1

    with allure.step("send the inbound packet and verify the relevant eni counter"):
        eni_counter_check_point_dict = {"SAI_ENI_STAT_FLOW_CREATED": 0,
                                        "SAI_ENI_STAT_INBOUND_RX_BYTES": packet_len * packet_number,
                                        "SAI_ENI_STAT_INBOUND_RX_PACKETS": packet_number,
                                        "SAI_ENI_STAT_RX_PACKETS": packet_number,
                                        "SAI_ENI_STAT_RX_BYTES": packet_len * packet_number
                                        }
        # before sending packet, get dash counter
        eni_counter_before_sending_pkt = get_eni_counters(dpuhost, eni_counter_oid)
        testutils.send(ptfadapter, dash_config_info[REMOTE_PTF_INTF], pa_match_packet, 1)
        testutils.verify_packets_any(ptfadapter, expected_packet, ports=[dash_config_info[LOCAL_PTF_INTF]])

        time.sleep(WAIT_DASH_ENI_COUNTER_READY_TIME)
        # after sending packet, get dash counter
        eni_counter_after_sending_pkt = get_eni_counters(dpuhost, eni_counter_oid)

        # compare eni_counter_after_sending_pkt with eni_counter_before_sending_pkt
        verify_eni_counter(eni_counter_check_point_dict, eni_counter_before_sending_pkt, eni_counter_after_sending_pkt)

    with allure.step("send the inbound packet with mismatched vin and verify the relevant eni counter"):
        eni_counter_check_point_dict = {"SAI_ENI_STAT_INBOUND_ROUTING_ENTRY_MISS_DROP_PACKETS": packet_number}
        # before sending packet, get dash counter
        eni_counter_before_sending_pkt = get_eni_counters(dpuhost, eni_counter_oid)
        pa_match_packet["VXLAN"].vni = 234
        testutils.send(ptfadapter, dash_config_info[REMOTE_PTF_INTF], pa_match_packet, packet_number)
        time.sleep(WAIT_DASH_ENI_COUNTER_READY_TIME)

        # after sending packet, get dash counter
        eni_counter_after_sending_pkt = get_eni_counters(dpuhost, eni_counter_oid)

        verify_eni_counter(eni_counter_check_point_dict, eni_counter_before_sending_pkt, eni_counter_after_sending_pkt)

