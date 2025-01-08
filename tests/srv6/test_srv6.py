import logging
import pytest
import ptf.testutils as testutils
import ptf.packet as scapy
from ptf.mask import Mask
from tests.common.utilities import wait_until
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.mellanox_data import is_mellanox_device
from tests.srv6.srv6_helper import SRv6, dump_packet_detail, validate_srv6_in_appl_db, \
    validate_techsupport_generation
from tests.common.dualtor.mux_simulator_control import toggle_all_simulator_ports_to_rand_selected_tor  # noqa: F401


pytestmark = [
    pytest.mark.topology('t0', 't1')
]

logger = logging.getLogger(__name__)


class SRv6Base():

    @pytest.fixture(autouse=True)
    def use_param(self, prepare_param):
        self.params = prepare_param

    def _create_srv6_packet(self,
                            outer_src_mac,
                            outer_dst_mac,
                            outer_src_pkt_ip,
                            outer_dst_pkt_ip,
                            srv6_action,
                            inner_dscp,
                            outer_dscp,
                            exp_outer_dst_pkt_ip,
                            exp_seg_left,
                            exp_dscp_pipe,
                            exp_dscp_uniform,
                            seg_left,
                            sef_list,
                            inner_pkt_ver,
                            dscp_mode):

        if dscp_mode == SRv6.uniform_mode:
            exp_dscp = exp_dscp_uniform
        else:
            exp_dscp = exp_dscp_pipe

        if inner_pkt_ver == '4':
            inner_pkt = testutils.simple_tcp_packet(eth_src=self.params['router_mac'],
                                                    ip_src=self.params['inner_src_ip'],
                                                    ip_dst=self.params['inner_dst_ip'],
                                                    ip_dscp=inner_dscp if inner_dscp else 0)

            exp_inner_pkt = testutils.simple_tcp_packet(eth_src=self.params['router_mac'],
                                                        ip_src=self.params['inner_src_ip'],
                                                        ip_dst=self.params['inner_dst_ip'],
                                                        ip_dscp=exp_dscp if exp_dscp else 0)
            scapy_ver = scapy.IP
        else:
            inner_pkt = testutils.simple_tcpv6_packet(eth_src=self.params['router_mac'],
                                                      ipv6_src=self.params['inner_src_ipv6'],
                                                      ipv6_dst=self.params['inner_dst_ipv6'],
                                                      ipv6_dscp=inner_dscp if inner_dscp else 0)

            exp_inner_pkt = testutils.simple_tcpv6_packet(eth_src=self.params['router_mac'],
                                                          ipv6_src=self.params['inner_src_ipv6'],
                                                          ipv6_dst=self.params['inner_dst_ipv6'],
                                                          ipv6_dscp=exp_dscp if exp_dscp else 0)
            scapy_ver = scapy.IPv6

        if srv6_action == SRv6.uN:
            if exp_outer_dst_pkt_ip:
                if seg_left or sef_list:
                    logger.info('Create SRv6 packets with SRH')
                    srv6_pkt = testutils.simple_ipv6_sr_packet(
                        eth_dst=outer_dst_mac,
                        eth_src=outer_src_mac,
                        ipv6_src=outer_src_pkt_ip,
                        ipv6_dst=outer_dst_pkt_ip,
                        srh_seg_left=seg_left,
                        srh_seg_list=sef_list,
                        ipv6_tc=outer_dscp * 4 if outer_dscp else 0,
                        srh_nh=self.params['srv6_next_header'][scapy_ver],
                        inner_frame=inner_pkt[scapy_ver],
                    )
                    exp_pkt = testutils.simple_ipv6_sr_packet(
                        eth_dst=outer_dst_mac,
                        eth_src=outer_src_mac,
                        ipv6_src=outer_src_pkt_ip,
                        ipv6_dst=exp_outer_dst_pkt_ip,
                        srh_seg_left=exp_seg_left,
                        srh_seg_list=sef_list,
                        ipv6_tc=exp_dscp * 4 if exp_dscp else 0,
                        srh_nh=self.params['srv6_next_header'][scapy_ver],
                        inner_frame=exp_inner_pkt[scapy_ver],
                    )
                    exp_pkt = Mask(exp_pkt)

                else:
                    logger.info('Create SRv6 packet with reduced SRH(no SRH header)')
                    srv6_pkt = testutils.simple_ipv6ip_packet(
                        eth_dst=outer_dst_mac,
                        eth_src=outer_src_mac,
                        ipv6_src=outer_src_pkt_ip,
                        ipv6_dst=outer_dst_pkt_ip,
                        ipv6_tc=outer_dscp * 4 if outer_dscp else 0,
                        inner_frame=inner_pkt[scapy_ver],
                    )
                    exp_pkt = testutils.simple_ipv6ip_packet(
                        eth_dst=outer_dst_mac,
                        eth_src=outer_src_mac,
                        ipv6_src=outer_src_pkt_ip,
                        ipv6_dst=exp_outer_dst_pkt_ip,
                        ipv6_tc=exp_dscp * 4 if exp_dscp else 0,
                        inner_frame=exp_inner_pkt[scapy_ver],
                    )
                    exp_pkt = Mask(exp_pkt)

                logger.info('Do not care packet ethernet destination address')
                exp_pkt.set_do_not_care_packet(scapy.Ether, 'dst')
                logger.info('Do not care packet ethernet source address')
                exp_pkt.set_do_not_care_packet(scapy.Ether, 'src')
                logger.info('Do not care IPv6 packet hop limit')
                exp_pkt.set_do_not_care_packet(scapy.IPv6, 'hlim')

            else:
                if seg_left or sef_list:
                    logger.info('Create SRv6 packets with SRH for USD flavor validation')
                    srv6_pkt = testutils.simple_ipv6_sr_packet(
                        eth_dst=outer_dst_mac,
                        eth_src=outer_src_mac,
                        ipv6_src=outer_src_pkt_ip,
                        ipv6_dst=outer_dst_pkt_ip,
                        srh_seg_left=seg_left,
                        srh_seg_list=sef_list,
                        ipv6_tc=outer_dscp * 4 if outer_dscp else 0,
                        srh_nh=self.params['srv6_next_header'][scapy_ver],
                        inner_frame=inner_pkt[scapy_ver],
                    )
                else:
                    logger.info('Create SRv6 packets without SRH for USD flavor validation')
                    srv6_pkt = testutils.simple_ipv6ip_packet(
                        eth_dst=outer_dst_mac,
                        eth_src=outer_src_mac,
                        ipv6_src=outer_src_pkt_ip,
                        ipv6_dst=outer_dst_pkt_ip,
                        ipv6_tc=outer_dscp * 4 if outer_dscp else 0,
                        inner_frame=inner_pkt[scapy_ver],
                    )
                exp_pkt = Mask(exp_inner_pkt)
                logger.info('Do not care packet ethernet destination address')
                exp_pkt.set_do_not_care_packet(scapy.Ether, 'dst')
                if inner_pkt_ver == '4':
                    logger.info('Do not care packet TTL')
                    exp_pkt.set_do_not_care_packet(scapy.IP, "ttl")
                    logger.info('Do not care packet checksum')
                    exp_pkt.set_do_not_care_packet(scapy.IP, "chksum")
                else:
                    logger.info('Do not care IPv6 packet hop limit')
                    exp_pkt.set_do_not_care_packet(scapy.IPv6, 'hlim')

        return srv6_pkt, exp_pkt

    def _send_verify_srv6_packet(self,
                                 ptfadapter,
                                 pkt,
                                 exp_pkt,
                                 exp_pro,
                                 ptf_src_port_id,
                                 ptf_dst_port_ids):
        ptfadapter.dataplane.flush()
        logger.info(f'Send SRv6 packet(s) from PTF port {ptf_src_port_id} to upstream')
        testutils.send(ptfadapter, ptf_src_port_id, pkt, count=self.params['packet_num'])
        logger.info('SRv6 packet format:\n ---------------------------')
        logger.info(f'{dump_packet_detail(pkt)}\n---------------------------')
        logger.info('Expect receive SRv6 packet format:\n ---------------------------')
        logger.info(f'{dump_packet_detail(exp_pkt.exp_pkt)}\n---------------------------')

        try:
            if exp_pro == 'forward':
                port_index, _ = testutils.verify_packet_any_port(ptfadapter, exp_pkt, ports=ptf_dst_port_ids,
                                                                 timeout=0.2)
                logger.info(f'Received packet(s) on port {ptf_dst_port_ids[port_index]}\n')
            elif exp_pro == 'drop':
                testutils.verify_no_packet_any(ptfadapter, exp_pkt, ports=ptf_dst_port_ids, timeout=0.2)
                logger.info(f'No packet received on {ptf_dst_port_ids}')
            else:
                logger.error(f'Wrong expected process result: {exp_pro}')

        except AssertionError as detail:
            raise detail

    def _validate_srv6_function(self, duthost, ptfadapter, dscp_mode):
        logger.info('Validate SRv6 table in APPL DB')
        wait_until(60, 5, 0, validate_srv6_in_appl_db, duthost)

        ptf_src_mac = ptfadapter.dataplane.get_mac(0, self.params['ptf_downlink_port']).decode('utf-8')
        for srv6_packet in self.params['srv6_packets']:
            logger.info('-------------------------------------------------------------------------')
            logger.info(f'SRv6 tunnel decapsulation mode: {dscp_mode}')
            logger.info(f'Send {self.params["packet_num"]} SRv6 packets with action: {srv6_packet["action"]}')
            logger.info(f'Pkt Src MAC: {ptf_src_mac}')
            logger.info(f'Pkt Dst MAC: {self.params["router_mac"]}')
            if srv6_packet['action'] == SRv6.uN:
                logger.info(f'Outer Pkt Src IP: {self.params["inner_src_ipv6"]}')
                logger.info(f'Outer Pkt Dst IP: {srv6_packet["dst_ipv6"]}')
                if srv6_packet["exp_dst_ipv6"]:
                    logger.info(f'Expect Outer Pkt Dst IP: {srv6_packet["exp_dst_ipv6"]}')
            if dscp_mode == SRv6.uniform_mode:
                if srv6_packet['outer_dscp']:
                    logger.info(f'Outer DSCP value: {srv6_packet["outer_dscp"]}')
                if srv6_packet['exp_outer_dscp_uniform']:
                    logger.info(f'Expect inner DSCP value: {srv6_packet["exp_outer_dscp_uniform"]}')
            else:
                if srv6_packet['inner_dscp']:
                    logger.info(f'Inner DSCP value: {srv6_packet["inner_dscp"]}')
                if srv6_packet['exp_inner_dscp_pipe']:
                    logger.info(f'Expect inner DSCP value: {srv6_packet["exp_inner_dscp_pipe"]}')
            logger.info(f'SRH Segment List: {srv6_packet["srh_seg_list"]}')
            logger.info(f'SRH Segment Left: {srv6_packet["srh_seg_left"]}')

            logger.info(f'Expect Segment Left: {srv6_packet["exp_srh_seg_left"]}')
            logger.info(f'Expect process result: {srv6_packet["exp_process_result"]}')
            logger.info('-------------------------------------------------------------------------')

            srv6_pkt, exp_pkt = self._create_srv6_packet(outer_src_mac=ptf_src_mac,
                                                         outer_dst_mac=self.params['router_mac'],
                                                         outer_src_pkt_ip=self.params['outer_src_ipv6'],
                                                         outer_dst_pkt_ip=srv6_packet['dst_ipv6'],
                                                         srv6_action=srv6_packet['action'],
                                                         inner_dscp=srv6_packet['inner_dscp'],
                                                         outer_dscp=srv6_packet['outer_dscp'],
                                                         exp_outer_dst_pkt_ip=srv6_packet['exp_dst_ipv6'],
                                                         exp_seg_left=srv6_packet['exp_srh_seg_left'],
                                                         exp_dscp_pipe=srv6_packet['exp_inner_dscp_pipe'],
                                                         exp_dscp_uniform=srv6_packet['exp_outer_dscp_uniform'],
                                                         seg_left=srv6_packet['srh_seg_left'],
                                                         sef_list=srv6_packet['srh_seg_list'],
                                                         inner_pkt_ver=srv6_packet['inner_pkt_ver'],
                                                         dscp_mode=dscp_mode)

            self._send_verify_srv6_packet(ptfadapter=ptfadapter,
                                          pkt=srv6_pkt,
                                          exp_pkt=exp_pkt,
                                          exp_pro=srv6_packet["exp_process_result"],
                                          ptf_src_port_id=self.params['ptf_downlink_port'],
                                          ptf_dst_port_ids=self.params['ptf_uplink_ports'])


class TestSRv6Base(SRv6Base):

    def test_srv6_func(self, config_setup, default_tunnel_mode,
                       setup_standby_ports_on_rand_unselected_tor,       # noqa: F811
                       toggle_all_simulator_ports_to_rand_selected_tor,  # noqa: F811
                       ptfadapter, rand_selected_dut, localhost):
        with allure.step('Validate SRv6 packet process'):
            self._validate_srv6_function(rand_selected_dut, ptfadapter, config_setup)

        # TODO: WA for issue https://github.com/sonic-net/sonic-buildimage/issues/21867, remove after it is closed
        # if not is_mellanox_device(rand_selected_dut) or default_tunnel_mode == config_setup:
        #     with allure.step('Randomly choose one action from reload/cold reboot and do the action and wait'):
        #         random_reboot(rand_selected_dut, localhost)
        #
        #     with allure.step('Validate SRv6 packet process'):
        #         self._validate_srv6_function(rand_selected_dut, ptfadapter, config_setup)

        if is_mellanox_device(rand_selected_dut) and config_setup == SRv6.pipe_mode:
            with allure.step('Validate SAI SDK dump contains SRv6 information'):
                validate_techsupport_generation(rand_selected_dut, feature_list=['SRv6'])
