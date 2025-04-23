import logging
from ipaddress import ip_network, IPv4Address
import copy

import configs.privatelink_config as pl
import ptf.testutils as testutils
import pytest
from constants import LOCAL_PTF_INTF, REMOTE_PTF_RECV_INTF
from gnmi_utils import apply_messages
from packets import outbound_pl_packets, inbound_pl_packets
from tests.smart_switch.conftest import SMARTSWITCH_PLATFORMS, copy_proxy_ssh, skip_unsupported_platform, platform # noqa F401
from tests.common import config_reload
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until
from dash_eni_counter_utils import get_eni_counters, get_eni_counter_oid, verify_eni_counter, \
    eni_counter_setup, ENI_COUNTER_READY_MAX_TIME
import time
from infra.tools.redmine.redmine_api import is_redmine_issue_active


logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t1')
]


@pytest.fixture(scope="module")
def apply_switch_basic_config(duthost, dpuhost):
    logger.info("Add ip to npu dpu data port")
    cmd_add_npu_dpu_port_ip = f'sudo config interface ip add {dpuhost.data_port_on_npu} {dpuhost.npu_data_port_ip}/31'
    duthost.shell(cmd_add_npu_dpu_port_ip)

    yield

    logger.info("Remove the ip of npu dpu data port")
    cmd_remove_npu_dpu_port_ip = f'sudo config interface ip Remove {dpuhost.data_port_on_npu} {dpuhost.npu_data_port_ip}/31'
    duthost.shell(cmd_remove_npu_dpu_port_ip)


@pytest.fixture(scope="module")
def apply_dpu_basic_config(dpuhost, apply_switch_basic_config):
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


@pytest.fixture(scope="module", autouse=True)
def add_static_route_from_npu_to_dpu(duthost, dpuhost, apply_dpu_basic_config, common_setup_teardown):
    remote_pa_ip = "10.0.0.1"
    logger.info("Add npu to dpu VIP route")
    cmd = f"ip route replace {pl.APPLIANCE_VIP}/32 via {dpuhost.dpu_data_port_ip}"
    duthost.shell(cmd)

    logger.info("Add underlay outbound to ptf route")
    underlay_outbound_to_ptf_route_subnet = ip_network(f'{pl.PE_PA}/32').supernet(prefixlen_diff=8)
    cmd_add_underlay_outbound_to_ptf_route = f"ip route add {underlay_outbound_to_ptf_route_subnet} via {remote_pa_ip}"
    duthost.shell(cmd_add_underlay_outbound_to_ptf_route)

    yield

    logger.info("Remove underlay outbound to ptf route")
    cmd_del_underlay_outboud_to_ptf_route = f"ip route del {underlay_outbound_to_ptf_route_subnet} via {remote_pa_ip}"
    duthost.shell(cmd_del_underlay_outboud_to_ptf_route)

    logger.info("Remove npu to dpu VIP route")
    duthost.shell(f"ip route del {pl.APPLIANCE_VIP}")


@pytest.fixture(scope="module")
def common_setup_teardown(localhost, duthost, ptfhost, dpuhost, eni_counter_setup):

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

    if is_redmine_issue_active([4125251])[0]:
        config_reload(dpuhost, safe_reload=True)
    else:

        logger.info(f"recover messages2: {pl.ENI_ROUTE_GROUP1_CONFIG}")
        apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpuhost.dpu_index, set_db=False)

        logger.info(f"recover messages1: {route_messages}")
        apply_messages(localhost, duthost, ptfhost, route_messages, dpuhost.dpu_index, set_db=False)

        logger.info(f"recover pl.ROUTING_TYPE_PL_CONFIG: {base_config_messages}")
        apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index, set_db=False)


@pytest.fixture(scope="function", params=["vxlan", "gre"])
def outer_encap(request):
    return request.param


@pytest.fixture(scope="function", params=['udp', 'tcp'])
def inner_packet_type(request):
    return request.param


class TestEniCounter:

    @pytest.fixture(autouse=True)
    def setup_param(self, dpuhost, ptfadapter, config_facts, minigraph_facts):
        self.ptfadapter = ptfadapter
        self.dpuhost = dpuhost
        self.eni = pl.ENI_ID
        self.eni_counter_oid = get_eni_counter_oid(dpuhost, self.eni)
        pc_member_config = config_facts["PORTCHANNEL_MEMBER"]
        member_ports = []
        for member_config in pc_member_config.values():
            for member in member_config:
                member_ports.append(member)

        self.expected_ptf_ports = [minigraph_facts["minigraph_ptf_indices"][port] for port in member_ports]
        logger.info(f"Expecting transformed packet on PTF ports: {self.expected_ptf_ports}")

    def test_outbound_pkt_pass_eni_counter(self, dash_pl_config, outer_encap, inner_packet_type):
        """
        1. Get the eni_counter_before_sending_pkt before sending the dash pkt
        2. Send a outbound pkt, and the pkt pass the pipeline successfully
        3. Get the eni_counter_after_sending_pkt after sending the dash pkt
        4. Check the following counter change as follows by comparing eni_counter_before_sending_pkt
        with eni_counter_after_sending_pkt
               SAI_ENI_STAT_FLOW_CREATED:  +1
               SAI_ENI_STAT_OUTBOUND_RX_BYTES:  +len(packet)*packet_number
               SAI_ENI_STAT_OUTBOUND_RX_PACKETS: +packet_number
               SAI_ENI_STAT_RX_PACKETS: +packet_number
               SAI_ENI_STAT_RX_BYTES: +len(packet)*packet_number
               SAI_ENI_STAT_FLOW_AGED: +1
        """
        packet_len = 150 if outer_encap == "vxlan" else 142
        packet_number = 10

        eni_counter_check_point_dict = {"SAI_ENI_STAT_FLOW_CREATED": 1,
                                        "SAI_ENI_STAT_OUTBOUND_RX_BYTES": packet_len * packet_number,
                                        "SAI_ENI_STAT_OUTBOUND_RX_PACKETS": packet_number,
                                        "SAI_ENI_STAT_RX_PACKETS": packet_number,
                                        "SAI_ENI_STAT_RX_BYTES": packet_len * packet_number,
                                        "SAI_ENI_STAT_FLOW_AGED": 1
                                        }

        pkt, exp_pkt = outbound_pl_packets( \
            dash_pl_config, outer_encap=outer_encap, inner_packet_type=inner_packet_type)
        verify_packets = [{'send': pkt, 'exp': exp_pkt}]
        self.send_packet_and_verify_dash_eni_counter(
            dash_pl_config, eni_counter_check_point_dict, packet_number, verify_packets)

    def test_outbound_pkt_miss_routing_entry_drop_counter(self, dash_pl_config, outer_encap, inner_packet_type):
        """
        1. Get the eni_counter_before_sending_pkt before sending the dash pkt
        2. Send a outbound pkt with inner dst dip which cannot match the dash route
        3. Get the eni_counter_after_sending_pkt after sending the dash pkt
        4. Check the following counter change as follows by comparing eni_counter_before_sending_pkt
        with eni_counter_after_sending_pkt
               SAI_ENI_STAT_OUTBOUND_ROUTING_ENTRY_MISS_DROP_PACKETS: +1
        """
        packet_number = 1
        eni_counter_check_point_dict = {"SAI_ENI_STAT_OUTBOUND_ROUTING_ENTRY_MISS_DROP_PACKETS": packet_number}
        pkt, _ = outbound_pl_packets(dash_pl_config, outer_encap, inner_packet_type)
        pkt[outer_encap.upper()]['IP'].dst = "10.3.3.4"
        verify_packets = [{'send': pkt, 'exp': None}]
        self.send_packet_and_verify_dash_eni_counter(
            dash_pl_config, eni_counter_check_point_dict, packet_number, verify_packets)

    def test_outbound_pkt_ca_pa_entry_miss_drop_counter(self, dash_pl_config, outer_encap, inner_packet_type):
        """
        1. Get the eni_counter_before_sending_pkt before sending the dash pkt
        2. Send a outbound pkt that matches to routing but no ca_to_pa exist for the vnet ID
        3. Get the eni_counter_after_sending_pkt after sending the dash pkt
        4. Check the following counter change as follows by comparing eni_counter_before_sending_pkt
        with eni_counter_after_sending_pkt
               SAI_ENI_STAT_OUTBOUND_CA_PA_ENTRY_MISS_DROP_PACKETS: +1
        """
        packet_number = 1
        eni_counter_check_point_dict = {"SAI_ENI_STAT_OUTBOUND_CA_PA_ENTRY_MISS_DROP_PACKETS": packet_number}
        pkt, _ = outbound_pl_packets(dash_pl_config, outer_encap, inner_packet_type)
        ip_with_same_outbound_route_prefix1 = format(IPv4Address(pl.PE_CA) + 1)
        pkt[outer_encap.upper()]['IP'].dst = ip_with_same_outbound_route_prefix1
        verify_packets = [{'send': pkt, 'exp': None}]

        self.send_packet_and_verify_dash_eni_counter(
            dash_pl_config, eni_counter_check_point_dict, packet_number, verify_packets)

    def test_eni_flow_deleted_counter(self, dash_pl_config, outer_encap):
        """
        1. Send 1 pass TCP SYN packet
        2. Get the eni_counter_before_sending_pkt before sending the dash pkt
        3. Send 1 pass RST packet
        4. Get the eni_counter_after_sending_pkt before sending the dash pkt
        4. Check the following counter change as follows by comparing eni_counter_before_sending_pkt
        with eni_counter_after_sending_pkt
                SAI_ENI_STAT_FLOW_DELETED increase by 1
        """
        packet_number = 1
        flow_del_counter = 1
        flow_created_counter = 1

        eni_counter_check_point_dict = {"SAI_ENI_STAT_FLOW_CREATED": flow_created_counter,
                                        "SAI_ENI_STAT_FLOW_DELETED": flow_del_counter}

        pkt, _ = outbound_pl_packets(dash_pl_config, outer_encap, inner_packet_type='tcp')
        pkt_rst = copy.deepcopy(pkt)
        pkt_rst[outer_encap.upper()]["TCP"].flags = "R"
        verify_packets = [{'send': pkt, 'exp': None},
                          {'send': pkt_rst, 'exp': None}]
        self.send_packet_and_verify_dash_eni_counter(
            dash_pl_config, eni_counter_check_point_dict, packet_number, verify_packets)

    def test_inbound_pkt_eni_counter(
            self,
            dash_pl_config,
            outer_encap,
            inner_packet_type
    ):
        """
        1. Get the eni_counter_before_sending_pkt before sending the dash pkt
        2. Send a outbound pkt and a inbound pkt
        3. Get the eni_counter_after_sending_pkt after sending the dash pkt
        4. Check the following counter change as follows by comparing eni_counter_before_sending_pkt
        with eni_counter_after_sending_pkt
               SAI_ENI_STAT_FLOW_CREATED: +1
               SAI_ENI_STAT_INBOUND_RX_BYTES: +len(inbound_packet)*packet_number
               SAI_ENI_STAT_INBOUND_RX_PACKETS: +packet_number
               SAI_ENI_STAT_RX_PACKETS: +packet_number*2
               SAI_ENI_STAT_RX_BYTES: +len(inbound_packet)*packet_number + len(outbound_packet)*packet_number
        5. Send a inbound pkt without inbound route
        6. Get the eni_counter_after_sending_pkt after sending the inbound pkt
        7. Check the following counter change as follows by comparing eni_counter_before_sending_pkt
        with eni_counter_after_sending_pkt
               SAI_ENI_STAT_INBOUND_ROUTING_ENTRY_MISS_DROP_PACKETS: +packet_number
        """
        outbound_packet_len = 150 if outer_encap == "vxlan" else 142
        inbound_packet_len = 142
        packet_number = 1

        vm_to_dpu_pkt, _ = outbound_pl_packets(dash_pl_config, outer_encap, inner_packet_type)
        pe_to_dpu_pkt, exp_dpu_to_vm_pkt = inbound_pl_packets(dash_pl_config, inner_packet_type)

        with allure.step("send outbound and inbound packet and verify the relevant eni counter"):
            eni_counter_check_point_dict = {"SAI_ENI_STAT_FLOW_CREATED": 1,
                                            "SAI_ENI_STAT_INBOUND_RX_BYTES":
                                                inbound_packet_len*packet_number,
                                            "SAI_ENI_STAT_INBOUND_RX_PACKETS": packet_number,
                                            "SAI_ENI_STAT_RX_PACKETS": packet_number*2,
                                            "SAI_ENI_STAT_RX_BYTES":
                                                outbound_packet_len * packet_number + inbound_packet_len*packet_number,
                                                "SAI_ENI_STAT_FLOW_AGED": 1
                                            }
            verify_packets = [{'send': vm_to_dpu_pkt, 'exp': None},
                              {'send': pe_to_dpu_pkt, 'exp': exp_dpu_to_vm_pkt}]
            self.send_packet_and_verify_dash_eni_counter(
                dash_pl_config, eni_counter_check_point_dict, packet_number, verify_packets)

        with allure.step("send the inbound packet without inbound route and verify the relevant eni counter"):
            eni_counter_check_point_dict = {"SAI_ENI_STAT_INBOUND_ROUTING_ENTRY_MISS_DROP_PACKETS": packet_number}
            verify_packets = [{'send': pe_to_dpu_pkt, 'exp': None}]
            self.send_packet_and_verify_dash_eni_counter(
                dash_pl_config, eni_counter_check_point_dict, packet_number, verify_packets)

    def send_packet_and_verify_dash_eni_counter(
            self, dash_pl_config, eni_counter_check_point_dict, packet_number, verify_packets):
        self.ptfadapter.dataplane.flush()

        with allure.step("get dash eni counter before sending pkt"):
            eni_counter_before_sending_pkt = get_eni_counters(self.dpuhost, self.eni_counter_oid)

        with allure.step("sending packets"):
            for pkts in verify_packets:
                testutils.send(self.ptfadapter, dash_pl_config[LOCAL_PTF_INTF], pkts['send'], packet_number)
                if pkts['exp']:
                    testutils.verify_packet_any_port(self.ptfadapter, pkts['exp'], self.expected_ptf_ports)
        def _verify_eni_counter():
            with allure.step("get dash eni counter after sending pkts"):
                eni_counter_after_sending_pkt = get_eni_counters(self.dpuhost, self.eni_counter_oid)

            # compare eni_counter_after_sending_pkt with eni_counter_before_sending_pkt
            return verify_eni_counter( \
                eni_counter_check_point_dict, eni_counter_before_sending_pkt, eni_counter_after_sending_pkt)

        pytest_assert(wait_until(ENI_COUNTER_READY_MAX_TIME, 2, 0, _verify_eni_counter), \
                       "The actual eni counter is not as expected")