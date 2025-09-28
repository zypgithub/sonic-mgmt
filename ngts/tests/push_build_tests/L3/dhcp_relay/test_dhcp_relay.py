import allure
import logging
import pytest

from ngts.cli_wrappers.linux.linux_dhcp_clis import LinuxDhcpCli
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from retry.api import retry_call
from ngts.helpers.general_helper import is_smartswitch_platform


"""

 DHCP Relay Test Cases

 Documentation: https://wikinox.mellanox.com/pages/viewpage.action?spaceKey=SW&title=SONiC+NGTS+DHCP+Relay+Documentation

"""

logger = logging.getLogger()

dhcp_default_sport = '68'
dhcp_default_dport = '67'
broadcast_mac = 'ff:ff:ff:ff:ff:ff'
broadcast_ip = '255.255.255.255'
dhclient_default_ip = '0.0.0.0'
run_dhcp_client = LinuxDhcpCli.run_dhcp_client
run_dhcp_client_with_conf = LinuxDhcpCli.run_dhcp_client_with_config
dhclient_stop_cmd = LinuxDhcpCli.stop_dhcp_client
dhcp_pkt = 'Ether(src="{}",dst="{}")/IP(src="{}",dst="{}")/UDP(sport={},dport={})/' \
           'BOOTP({},xid=RandInt())/DHCP(options=[{}])'
dhcp_option_53 = 'udp[250:1]'


@pytest.fixture(scope='module', autouse=True)
def skip_dhcp_relay_v4_test(platform_params):
    if is_smartswitch_platform(platform_params):
        pytest.skip(
            "Smartswitch not support the case. \
             Because by default, dhcp relay v4 is enabled on smartswitch and is mainly for DPU.\
             So when configuring dhcp relay in smartswitch, \
             it will return error: Cannot change dhcp_relay configuration when dhcp_server feature is enabled.")


class TestDHCPRelay:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, cli_objects, engines, players, interfaces):
        self.topology = topology_obj
        self.players = players
        self.dut_engine = engines.dut
        self.dut_cli_object = cli_objects.dut
        self.dhcp_client_engine = engines.ha
        self.dhcp_client_cli_obj = cli_objects.ha
        self.dhcp_server_engine = engines.hb
        self.dhclient_vlan = '690'
        self.hadut2 = interfaces.ha_dut_2
        self.dhclient_iface = '{}.{}'.format(self.hadut2, self.dhclient_vlan)
        self.dut_vlan_iface = 'Vlan' + self.dhclient_vlan
        self.dhcp_server_iface = 'bond0.69'
        self.dhcp_server_ip = '69.0.0.2'
        self.dut_dhclient_vlan_ip = '69.0.1.1'
        self.expected_ip = '69.0.1.150'
        self.dhclient_mac = cli_objects.ha.mac.get_mac_address_for_interface(self.dhclient_iface)
        self.dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(self.dut_vlan_iface)
        self.chaddr = bytes.fromhex(self.dhclient_mac.replace(':', ''))

    @pytest.mark.dhcp_relay
    def test_basic_dhcp_relay(self):
        try:
            with allure.step('Validate the IP address provided by the DHCP server'):
                assert self.expected_ip in self.dhcp_client_engine.run_cmd(run_dhcp_client.format(self.dhclient_iface))

            with allure.step('Unassign DHCP client IP by stopping dhclient'):
                self.dhcp_client_engine.run_cmd(dhclient_stop_cmd.format(self.dhclient_iface))
        except BaseException as err:
            raise AssertionError(err)
        finally:
            self.dhcp_client_cli_obj.dhcp.kill_all_dhcp_clients()

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_remove_dhcp_server(self):
        try:
            with allure.step('Remove DHCP relay setting from DUT'):
                self.dut_cli_object.dhcp_relay.del_dhcp_relay(self.dhclient_vlan, self.dhcp_server_ip,
                                                              topology_obj=self.topology)

            with allure.step('Trying to GET ip address from DHCP server when DHCP relay settings removed'):
                assert LinuxDhcpCli.dhcp_client_no_offers in self.dhcp_client_engine.run_cmd(
                    run_dhcp_client_with_conf.format(self.dhclient_iface, 'dhclient.conf'))
        except BaseException as err:
            raise AssertionError(err)
        finally:
            self.dhcp_client_cli_obj.dhcp.kill_all_dhcp_clients()
            self.dut_cli_object.dhcp_relay.add_dhcp_relay(self.dhclient_vlan, self.dhcp_server_ip,
                                                          topology_obj=self.topology)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_release_message(self):
        dhcp_release = '0x7'
        bootp_body = 'chaddr={},ciaddr="{}"'.format(self.chaddr, self.expected_ip)
        dhcp_options = '("message-type","release"),"end"'
        tcpdump_filter_release = "'((port 67 or port 68) and ({} = {}))'".format(dhcp_option_53, dhcp_release)

        release_pkt = dhcp_pkt.format(self.dhclient_mac, self.dut_mac, self.expected_ip, self.dut_dhclient_vlan_ip,
                                      dhcp_default_sport, dhcp_default_dport, bootp_body, dhcp_options)
        try:
            with allure.step('Validate RELEASE message from DHCP client'):
                validation = {'sender': 'ha', 'send_args': {'interface': self.dhclient_iface, 'packets': release_pkt,
                                                            'count': 3},
                              'receivers':
                                  [
                                      {'receiver': 'hb', 'receive_args': {'interface': self.dhcp_server_iface,
                                                                          'filter': tcpdump_filter_release, 'count': 1}}
                ]
                }
                ScapyChecker(self.players, validation).run_validation()

        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    @pytest.mark.build
    def test_dhcp_relay_nak_message(self):
        dhcp_nak = '0x6'
        bootp_body = 'chaddr={}'.format(self.chaddr)
        tcpdump_filter_nak = "'((port 67 or port 68) and ({} = {}))'".format(dhcp_option_53, dhcp_nak)
        dhcp_options_request_out_of_range_ip = '("message-type","request"),("requested_addr","1.2.3.4"),"end"'
        dhcp_options_request_out_of_range_ip_pkt = dhcp_pkt.format(self.dhclient_mac, broadcast_mac, dhclient_default_ip,
                                                                   broadcast_ip, dhcp_default_sport, dhcp_default_dport,
                                                                   bootp_body, dhcp_options_request_out_of_range_ip)
        try:
            with allure.step('Validate that DHCPNAK message from DHCP server received on DHCP client'):
                validation_nak_default_vrf = {'sender': 'ha',
                                              'send_args': {'interface': self.dhclient_iface,
                                                            'packets': dhcp_options_request_out_of_range_ip_pkt,
                                                            'count': 3},
                                              'receivers':
                                                  [
                                                  {'receiver': 'ha', 'receive_args':
                                                   {'interface': self.dhclient_iface,
                                                    'filter': tcpdump_filter_nak, 'count': 1}}
                                              ]
                                              }
                ScapyChecker(self.players, validation_nak_default_vrf).run_validation()
        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_decline_message(self):
        dhcp_decline = '0x4'
        bootp_body = 'chaddr={}'.format(self.chaddr)
        tcpdump_filter_decline = "'((port 67 or port 68) and ({} = {}))'".format(dhcp_option_53, dhcp_decline)
        dhcp_options_decline = '("message-type","decline"),"end"'
        decline_pkt = dhcp_pkt.format(self.dhclient_mac, broadcast_mac, dhclient_default_ip, broadcast_ip,
                                      dhcp_default_sport, dhcp_default_dport, bootp_body, dhcp_options_decline)
        try:
            with allure.step('Validate that DHCPDECLINE message from DHCP client received on DHCP server'):
                validation_decline_default_vrf = {'sender': 'ha',
                                                  'send_args': {'interface': self.dhclient_iface,
                                                                'packets': decline_pkt, 'count': 3},
                                                  'receivers':
                                                      [
                                                          {'receiver': 'hb',
                                                           'receive_args': {'interface': self.dhcp_server_iface,
                                                                            'filter': tcpdump_filter_decline,
                                                                            'count': 1}}
                                                  ]
                                                  }
                scapy_checker = ScapyChecker(self.players, validation_decline_default_vrf)
                retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=5, logger=logger)
        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_inform_message(self):
        dhcp_inform = '0x8'
        bootp_body = 'chaddr={}'.format(self.chaddr)
        tcpdump_filter_inform = "'((port 67 or port 68) and ({} = {}))'".format(dhcp_option_53, dhcp_inform)
        dhcp_options_inform = '("message-type","inform"),"end"'
        inform_pkt = dhcp_pkt.format(self.dhclient_mac, broadcast_mac, dhclient_default_ip, broadcast_ip,
                                     dhcp_default_sport, dhcp_default_dport, bootp_body, dhcp_options_inform)
        try:
            with allure.step('Validate that DHCPINFORM message from DHCP client received on DHCP server'):
                validation_inform_default_vrf = {'sender': 'ha',
                                                 'send_args': {'interface': self.dhclient_iface,
                                                               'packets': inform_pkt, 'count': 3},
                                                 'receivers':
                                                     [
                                                         {'receiver': 'hb',
                                                          'receive_args': {'interface': self.dhcp_server_iface,
                                                                           'filter': tcpdump_filter_inform, 'count': 1}}
                                                 ]
                                                 }
                ScapyChecker(self.players, validation_inform_default_vrf).run_validation()
        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_unicast_request_message(self):
        try:
            with allure.step('Getting IP address from DHCP server via DHCP relay functionality'):
                assert self.expected_ip in self.dhcp_client_engine.run_cmd(run_dhcp_client.format(self.dhclient_iface))

            with allure.step('Trying to GET ip address from DHCP server when DHCP request sent to not broadcast address'):
                dhclient_with_server_ip_run_cmd = 'dhclient {} -cf dhclient.conf -s {} -v'.format(self.dhclient_iface,
                                                                                                  self.dut_dhclient_vlan_ip)
                dhcp_client_output = self.dhcp_client_engine.run_cmd(dhclient_with_server_ip_run_cmd)
                assert self.expected_ip in dhcp_client_output
                assert LinuxDhcpCli.dhcp_client_no_offers not in dhcp_client_output

            with allure.step('Release DHCP address from client'):
                self.dhcp_client_engine.run_cmd(dhclient_stop_cmd.format(self.dhclient_iface))
        except BaseException as err:
            raise AssertionError(err)
        finally:
            self.dhcp_client_cli_obj.dhcp.kill_all_dhcp_clients()

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_request_message_with_custom_src_port(self):
        dhcp_ack = '0x5'
        bootp_body = 'chaddr={}'.format(self.chaddr)
        # ACK on server side - dst port 67
        tcpdump_filter_ak = "'(dst port 67 and ({} = {}))'".format(dhcp_option_53, dhcp_ack)
        tcpdump_filter_ak_on_client = "'(dst port 68 and ({} = {}))'".format(dhcp_option_53, dhcp_ack)
        sport = '6800'
        dhcp_options_request_ip = '("message-type","request"),("requested_addr","69.0.1.156"),"end"'
        request_from_custom_port_pkt = dhcp_pkt.format(self.dhclient_mac, broadcast_mac, dhclient_default_ip,
                                                       broadcast_ip, sport, dhcp_default_dport, bootp_body,
                                                       dhcp_options_request_ip)

        try:
            with allure.step('Validate that DHCPREQUEST message from DHCP client from custom SRC port received on '
                             'server and server replied'):
                validation_custom_request_src_prt = {'sender': 'ha',
                                                     'send_args': {'interface': self.dhclient_iface,
                                                                   'packets': request_from_custom_port_pkt, 'count': 3},
                                                     'receivers':
                                                         [
                                                             {'receiver': 'hb',
                                                              'receive_args': {'interface': self.dhcp_server_iface,
                                                                               'filter': tcpdump_filter_ak,
                                                                               'count': 1}},
                                                             {'receiver': 'ha',
                                                              'receive_args': {'interface': self.dhclient_iface,
                                                                               'filter': tcpdump_filter_ak_on_client,
                                                                               'count': 1}}
                                                     ]
                                                     }
                ScapyChecker(self.players, validation_custom_request_src_prt).run_validation()
        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_request_message_with_empty_payload(self):
        """
        This test case check that if we send DHCP request packet with empty payload - packet forwarded to DHCP
        server and no more field were added by the DHCP relay other than option 82, by checking packet size is less
        thank 330 bytes
        Test related to GitHub issue: https://github.com/Azure/sonic-buildimage/issues/6052
        """
        bootp_body = 'chaddr={}'.format(self.chaddr)

        # REQUEST message on server side - should be less than 330 bytes
        tcpdump_filter_empty_request = "'((port 67 and dst 69.0.0.2) and (udp[4:2] <= 330))'"

        empty_dhcp_request = dhcp_pkt.format(self.dhclient_mac, broadcast_mac, dhclient_default_ip, broadcast_ip,
                                             dhcp_default_sport, dhcp_default_dport, bootp_body, '')

        try:
            with allure.step('Validate that empty DHCPREQUEST message from DHCP client received on DHCP server'):
                validation_empty_dhcp_request = {'sender': 'ha',
                                                 'send_args': {'interface': self.dhclient_iface,
                                                               'packets': empty_dhcp_request, 'count': 3},
                                                 'receivers':
                                                     [
                                                         {'receiver': 'hb',
                                                          'receive_args': {'interface': self.dhcp_server_iface,
                                                                           'filter': tcpdump_filter_empty_request,
                                                                           'count': 1}}
                                                 ]
                                                 }
                scapy_checker = ScapyChecker(self.players, validation_empty_dhcp_request)
                retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=5, logger=logger)
        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_udp_packet_with_src_and_dst_ports_the_same_as_dhcp(self):
        tcpdump_filter_src_1_2_3_4 = "src 1.2.3.4"
        dst_ip = "30.0.0.2"
        udp_pkt = 'Ether(src="b0:09:0f:09:04:00", dst="{}")/IP(src="1.2.3.4",dst="{}")/UDP(sport=68,dport=67)/Raw()'.format(self.dut_mac, dst_ip)

        try:
            with allure.step('Validate UDP message with SRC and DST port the same as DHCP not forwarded to DHCP server'):
                # PING below need to prevent issue when packet not forwarded to host from switch
                validation_ping = {'sender': 'ha', 'args': {'count': 3, 'dst': '30.0.0.1'}}
                retry_call(PingChecker(self.players, validation_ping).run_validation, fargs=[], tries=2, delay=5,
                           logger=logger)
                validation_udp_packet = {'sender': 'ha', 'send_args': {'interface': self.dhclient_iface,
                                                                       'packets': udp_pkt, 'count': 3},
                                         'receivers':
                                             [
                                                 {'receiver': 'ha',
                                                  'receive_args': {'interface': 'bond0',
                                                                   'filter': tcpdump_filter_src_1_2_3_4, 'count': 1}},
                                                 {'receiver': 'hb',
                                                  'receive_args': {'interface': self.dhcp_server_iface,
                                                                   'filter': tcpdump_filter_src_1_2_3_4, 'count': 0}}
                ]
                }
                ScapyChecker(self.players, validation_udp_packet).run_validation()
        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_packet_with_malformed_payload(self):
        mac1 = self.dhclient_mac.replace(':', '')[:8]
        mac2 = self.dhclient_mac.replace(':', '')[8:]
        tcpdump_filter_random_payload = "'((port 67 or port 68) and (udp[36:4] = 0x{}) and (udp[40:2] = 0x{}))'".format(
            mac1, mac2)

        pkt_with_random_payload = 'Ether(src="{}", dst="{}")/IP(dst="{}",src="{}")/UDP(sport={},dport={})/' \
                                  'BOOTP(chaddr={}, xid=RandInt())/Raw(RandString(size=1024))'.format(
                                      self.dhclient_mac, broadcast_mac, broadcast_ip, dhclient_default_ip, dhcp_default_sport,
                                      dhcp_default_dport, self.chaddr)

        try:
            with allure.step('Send BOOTP packet with invalid payload'):
                validation_invalid_payload = {'sender': 'ha',
                                              'send_args': {'interface': self.dhclient_iface,
                                                            'packets': pkt_with_random_payload, 'count': 3},
                                              'receivers':
                                                  [
                                                      {'receiver': 'hb',
                                                       'receive_args': {'interface': self.dhcp_server_iface,
                                                                        'filter': tcpdump_filter_random_payload,
                                                                        'count': 1}}
                                              ]
                                              }
                ScapyChecker(self.players, validation_invalid_payload).run_validation()
        except BaseException as err:
            raise AssertionError(err)

    @pytest.mark.dhcp_relay
    def test_dhcp_relay_multiple_dhcp_servers(self, configure_additional_dhcp_server):
        """
        This test will check DHCP Relay functionality in case when multiple DHCP servers configured
        :return: raise assertion error in case when test failed
        """
        try:
            with allure.step('Getting IP address from DHCP server when 2 DHCP servers configured and active'):
                assert self.expected_ip in self.dhcp_client_engine.run_cmd(run_dhcp_client.format(self.dhclient_iface))

            with allure.step('Release DHCP address from client'):
                self.dhcp_client_engine.run_cmd(dhclient_stop_cmd.format(self.dhclient_iface))

            with allure.step('Disable first DHCP server'):
                self.dhcp_server_engine.run_cmd(LinuxDhcpCli.dhcp_server_stop_cmd)

            with allure.step('Getting IP from DHCP server when 2 DHCP servers configured and only second active'):
                assert self.expected_ip in self.dhcp_client_engine.run_cmd(run_dhcp_client.format(self.dhclient_iface))

            with allure.step('Release DHCP address from client'):
                self.dhcp_client_engine.run_cmd(dhclient_stop_cmd.format(self.dhclient_iface))

            with allure.step('Disable second DHCP server'):
                self.dhcp_client_engine.run_cmd(LinuxDhcpCli.dhcp_server_stop_cmd)

            with allure.step('Trying to GET ip address from DHCP server when all DHCP servers disabled'):
                assert LinuxDhcpCli.dhcp_client_no_offers in self.dhcp_client_engine.run_cmd(
                    run_dhcp_client_with_conf.format(self.dhclient_iface, 'dhclient.conf'))
                self.dhcp_client_engine.run_cmd(dhclient_stop_cmd.format(self.dhclient_iface))

            with allure.step('Enable first DHCP server'):
                self.dhcp_server_engine.run_cmd(LinuxDhcpCli.dhcp_server_start_cmd)

            with allure.step('Getting IP address from DHCP server when 2 DHCP servers configured and first only active'):
                assert self.expected_ip in self.dhcp_client_engine.run_cmd(run_dhcp_client.format(self.dhclient_iface))

            with allure.step('Release DHCP address from client'):
                self.dhcp_client_engine.run_cmd(dhclient_stop_cmd.format(self.dhclient_iface))

            with allure.step('Enable second DHCP server'):
                self.dhcp_client_engine.run_cmd(LinuxDhcpCli.dhcp_server_start_cmd)

            with allure.step('Getting IP address from DHCP server when 2 DHCP servers configured and 2 active'):
                assert self.expected_ip in self.dhcp_client_engine.run_cmd(run_dhcp_client.format(self.dhclient_iface))

            with allure.step('Release DHCP address from client'):
                self.dhcp_client_engine.run_cmd(dhclient_stop_cmd.format(self.dhclient_iface))

        except BaseException as err:
            raise AssertionError(err)
        finally:
            self.dhcp_client_cli_obj.dhcp.kill_all_dhcp_clients()
