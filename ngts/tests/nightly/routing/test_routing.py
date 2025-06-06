import allure
import logging
import pytest
import re
import json
import random
import ipaddress

from retry.api import retry_call
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker

logger = logging.getLogger()

"""
Test plan details could be found by link(section "Test cases MS #5)":
https://confluence.nvidia.com/pages/viewpage.action?spaceKey=SW&title=SONiC+NGTS+Bluefield+Documentation
"""


class TestRouting:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, engines, cli_objects, interfaces, players, platform_params, dut_mac, dut_ha_1_mac):
        self.topology_obj = topology_obj
        self.dut = engines.dut
        self.ha = engines.ha
        self.hb = engines.hb
        self.dut_cli = cli_objects.dut
        self.ha_cli = cli_objects.ha
        self.hb_cli = cli_objects.hb
        self.interfaces = interfaces
        self.players = players
        self.platform_params = platform_params
        self.hwsku = platform_params.hwsku
        self.dut_mac = dut_mac
        self.dut_ha_1_mac = dut_ha_1_mac

        self.default_route = '0.0.0.0/0'
        self.dut_loopback_route = '10.10.10.10/32'
        self.static_route_24 = '50.0.0.0/24'
        self.static_route_32 = '50.0.0.1/32'
        self.dut_loopback_ip = '10.10.10.10'
        self.dut_ha_1_ip = '20.0.0.1'
        self.dut_hb_1_ip = '30.0.0.1'
        self.ha_dut_1_ip = '20.0.0.2'
        self.hb_dut_1_ip = '30.0.0.2'

        self.tcpdump_src_mac = self.dut_mac if self.dut_cli.general.is_bluefield(self.hwsku) else self.dut_ha_1_mac
        # Get random IP in range: 59.154.200.0 - 196.178.1.0
        self.test_ip = str(ipaddress.IPv4Address(random.choice(range(1000000000, 3300000000))))
        self.static_route_32_ip = '50.0.0.1'
        self.static_route_24_ip = '50.0.0.{}'.format(random.choice(range(2, 255)))

        self.ha_or_hb_regex = f'({self.ha_dut_1_ip}|{self.hb_dut_1_ip})'

        # Check that all BGPs established before run test(in other case first test may pass because session not yet UP)
        retry_call(self.check_bgp_sessions, fargs=[], tries=10, delay=5, logger=logger)

    def validate_arp(self, arp_table_data):
        """
        Validate that ARP entries available for HA and HB
        :param arp_table_data: parsed ARP table output
        """
        assert self.ha_dut_1_ip in arp_table_data, f'ARP entry not available for: {self.ha_dut_1_ip}'
        assert self.hb_dut_1_ip in arp_table_data, f'ARP entry not available for: {self.hb_dut_1_ip}'

    def validate_ip_bgp_summary(self, ip_bgp_summary_data):
        """
        Validated that BGP peers available in "show ip bgp summary" output
        :param ip_bgp_summary_data: parsed "show ip bgp summary" output
        """
        assert self.ha_dut_1_ip in ip_bgp_summary_data, f'BGP peer {self.ha_dut_1_ip} not available'
        assert self.hb_dut_1_ip in ip_bgp_summary_data, f'BGP peer {self.hb_dut_1_ip} not available'

    def validate_ip_bgp_network(self, show_ip_bgp_network_output):
        """
        Validate that default route available via 2 BGP in "show ip bgp network" command output
        :param show_ip_bgp_network_output: "show ip bgp network" command output
        """
        regexp = fr'\*(>|=)\s+{self.default_route}\s+{self.ha_or_hb_regex}\s+0\s+0\s501\si\s+\*(>|=)\s+{self.ha_or_hb_regex}\s+0\s+0\s501\si'
        '''
        *= 0.0.0.0/0        20.0.0.2                 0             0 501 i
        *>                  30.0.0.2                 0             0 501 i
        '''
        default_route_peers_match = re.search(regexp, show_ip_bgp_network_output)
        assert default_route_peers_match, f'Default route not available in "show ip bgp network" output'
        default_route_peers = default_route_peers_match.groups()
        assert self.ha_dut_1_ip in default_route_peers, f'Default route via {self.ha_dut_1_ip} not available'
        assert self.hb_dut_1_ip in default_route_peers, f'Default route via {self.hb_dut_1_ip} not available'

    def validate_ip_bgp_network_0(self, show_ip_bgp_network_output):
        """
        Validate that default route available via 2 BGP in "show ip bgp network 0.0.0.0" command output
        :param show_ip_bgp_network_output: "show ip bgp network 0.0.0.0" command output
        :return:
        """
        regexp = fr'.*2\savailable.*{self.ha_or_hb_regex}\s{self.ha_or_hb_regex}'
        '''
        Paths: (2 available, best #2, table default)
          Advertised to non peer-group peers:
          20.0.0.2 30.0.0.2
        '''
        default_route_peers_0 = re.search(regexp, show_ip_bgp_network_output, re.DOTALL).groups()
        assert self.ha_dut_1_ip in default_route_peers_0, f'Default route via {self.ha_dut_1_ip} not available'
        assert self.hb_dut_1_ip in default_route_peers_0, f'Default route via {self.hb_dut_1_ip} not available'

    @staticmethod
    def validate_ip_bgp_neighbors(show_ip_bgp_neighbors_output):
        """
        Validate that 2 BGP peers available in "show ip bgp neighbors" output
        :param show_ip_bgp_neighbors_output: "show ip bgp neighbors" output
        """
        ip_bgp_neighbors_info = [neigh for neigh in show_ip_bgp_neighbors_output.split('BGP neighbor is') if neigh]
        available_bgp_neighbors = len(ip_bgp_neighbors_info)
        assert available_bgp_neighbors == 2, f'Available BGP peers: {available_bgp_neighbors}, expected: 2'

    def validate_ip_bgp_neighbor(self, show_ip_bgp_neighbors_output):
        """
        Validate that BGP peer info available in "show ip bgp neighbors 20.0.0.2" output
        :param show_ip_bgp_neighbors_output: "show ip bgp neighbors 20.0.0.2" output
        """
        # BGP neighbor is 20.0.0.2, remote AS 501, local AS 500, external link
        regexp_neigh = fr'.*BGP neighbor is {self.hb_dut_1_ip}, remote AS 501, local AS 500'
        #   BGP state = Established, up for 01:19:00
        regexp_status = r'.*BGP state = Established, up for'
        #   2 accepted prefixes
        regexp_prefixes = r'.*\d+ accepted prefixes'
        # Foreign host: 20.0.0.2, Foreign port: 179
        regexp_peer_info = fr'.*Foreign\shost:\s{self.hb_dut_1_ip},\sForeign\sport:\s\d+'
        assert re.search(regexp_neigh, show_ip_bgp_neighbors_output), 'Not all info about BGP peer available, check log'
        assert re.search(regexp_status, show_ip_bgp_neighbors_output), 'BGP session not in Established state'
        assert re.search(regexp_prefixes, show_ip_bgp_neighbors_output), 'No BGP accepted prefixes'
        assert re.search(regexp_peer_info, show_ip_bgp_neighbors_output), \
            'No info about BGP session(peer host, peer port)'

    def validate_routes_on_dut(self, parsed_ip_route_output):
        """
        Validate that all expected(2 static and default via 2 BGP peers) routes available on DUT
        :param parsed_ip_route_output: parsed show ip route output
        """
        def get_next_hops(routes):
            next_hops = {'intf': [], 'ip': []}
            for route in routes:
                for next_hop in route['nexthops']:
                    next_hops['intf'].append(next_hop['interfaceName'])
                    next_hops['ip'].append(next_hop['ip'])
            return next_hops

        default_route_next_hops = get_next_hops(parsed_ip_route_output[self.default_route])
        for iface in [self.interfaces.dut_ha_1, self.interfaces.dut_hb_1]:
            assert iface in default_route_next_hops['intf'], f'Interface: {iface} are not used for default route'
        for nh in [self.ha_dut_1_ip, self.hb_dut_1_ip]:
            assert nh in default_route_next_hops['ip'], 'Next hop {nh} are not used for default route'

        static_route_24_next_hops = get_next_hops(parsed_ip_route_output[self.static_route_24])
        assert [self.ha_dut_1_ip] == static_route_24_next_hops['ip'], \
            f'Next hop for static route {self.static_route_24} incorrect or not available'
        assert [self.interfaces.dut_ha_1] == static_route_24_next_hops['intf'], \
            f'Next hop interface for static route {self.static_route_24} incorrect or not available'

        static_route_32_next_hops = get_next_hops(parsed_ip_route_output[self.static_route_32])
        assert [self.hb_dut_1_ip] == static_route_32_next_hops['ip'], \
            f'Next hop for static route {self.static_route_32} incorrect or not available'
        assert [self.interfaces.dut_hb_1] == static_route_32_next_hops['intf'], \
            f'Next hop interface for static route {self.static_route_32} incorrect or not available'

    def validate_default_route(self, show_ip_route_output_default):
        """
        Validate that default route available in "show ip route 0.0.0.0/0" output
        :param show_ip_route_output_default: "show ip route 0.0.0.0/0" parsed output
        """
        assert self.ha_dut_1_ip in show_ip_route_output_default, f'No default route via {self.ha_dut_1_ip}'
        assert self.hb_dut_1_ip in show_ip_route_output_default, f'No default route via {self.hb_dut_1_ip}'

    def validate_ip_interfaces(self, interface, expected_ip, mask='24'):
        """
        Validate that DUT IP from specific interface available in "show ip interfaces" output
        :param interface: interface on which we will check IPs
        :param expected_ip: expected IP for specific interface
        :param mask: expected IP mask
        """
        iface_ips = self.dut_cli.ip.get_interface_ips(interface=interface)
        assert {'ip': expected_ip, 'mask': mask} in iface_ips, \
            f'IP address: {expected_ip} not available in "show ip interfaces" output'

    def validate_loopback_route_on_host(self, host_engine):
        """
        Validate that on hosts available(advertised via BGP) route to DUT Loopback0 interface
        :param host_engine: host engine
        """
        host_routes = json.loads(host_engine.run_cmd('ip -j route'))
        host_loopback_route_exist = False
        for route_entry in host_routes:
            if route_entry['dst'] == self.dut_loopback_ip:
                host_loopback_route_exist = True
                break
        assert host_loopback_route_exist, f'Route to DUT interface {self.dut_loopback_route} not available on host'

    def validate_loopback_reachable_from_hosts(self):
        """
        Validate that DUT Loopback IP are reachable from hosts
        """
        with allure.step(f'Checking ping from HA to DUT loopback IP: {self.dut_loopback_ip}'):
            validation_ha_dut_loopback = {'sender': 'ha', 'args': {'interface': self.interfaces.ha_dut_1, 'count': 3,
                                                                   'dst': self.dut_loopback_ip}}
            PingChecker(self.players, validation_ha_dut_loopback).run_validation()

        with allure.step(f'Checking ping from HB to DUT loopback IP: {self.dut_loopback_ip}'):
            validation_hb_dut_loopback = {'sender': 'hb', 'args': {'interface': self.interfaces.hb_dut_1, 'count': 3,
                                                                   'dst': self.dut_loopback_ip}}
            PingChecker(self.players, validation_hb_dut_loopback).run_validation()

    def validate_traffic_via_bgp_routes(self, expected_pass=True):
        """
        Validated that traffic pass from DUT according to default routes via BGP
        """
        with allure.step('Checking functionally default route on DUT'):
            tcpdump_filter = f'ether host {self.tcpdump_src_mac} and host {self.test_ip}'
            if expected_pass:
                validation = {'name': 'ping8', 'background': 'start', 'expected_successful_receivers': 'single',
                              'receivers': [
                                  {'receiver': 'ha', 'receive_args': {'interface': self.interfaces.ha_dut_1,
                                                                      'filter': tcpdump_filter, 'count': 1}},
                                  {'receiver': 'hb', 'receive_args': {'interface': self.interfaces.hb_dut_1,
                                                                      'filter': tcpdump_filter, 'count': 1}}]
                              }
            else:
                validation = {'name': 'ping8', 'background': 'start',
                              'receivers': [
                                  {'receiver': 'ha', 'receive_args': {'interface': self.interfaces.ha_dut_1,
                                                                      'filter': tcpdump_filter, 'count': 0}},
                                  {'receiver': 'hb', 'receive_args': {'interface': self.interfaces.hb_dut_1,
                                                                      'filter': tcpdump_filter, 'count': 0}}]
                              }
            scapy_validation_obj = ScapyChecker(self.players, validation)
            scapy_validation_obj.run_background_validation()

            self.dut.run_cmd(f'ping {self.test_ip} -c 1')

            scapy_validation_obj.complete_validation()

    def validate_traffic_via_static_routes(self):
        """
        Validated that traffic pass from DUT according to static routes
        """
        with allure.step(f'Checking that traffic to {self.static_route_32_ip} forwarded to HB and not to HA'):
            tcpdump_filter = f'ether host {self.tcpdump_src_mac} and host {self.static_route_32_ip}'
            validation = {'name': 'ping50_1', 'background': 'start', 'receivers': [
                {'receiver': 'ha', 'receive_args': {'interface': self.interfaces.ha_dut_1, 'filter': tcpdump_filter,
                                                    'count': 0}},
                {'receiver': 'hb', 'receive_args': {'interface': self.interfaces.hb_dut_1, 'filter': tcpdump_filter,
                                                    'count': 1}}]
            }
            scapy_validation_obj = ScapyChecker(self.players, validation)
            scapy_validation_obj.run_background_validation()

            self.dut.run_cmd(f'ping {self.static_route_32_ip} -c 1')

            scapy_validation_obj.complete_validation()

        with allure.step(f'Checking that traffic to {self.static_route_24_ip} forwarded to HA and not to HB'):
            tcpdump_filter = f'ether host {self.tcpdump_src_mac} and host {self.static_route_24_ip}'
            validation = {'name': 'ping50_100', 'background': 'start', 'receivers': [
                {'receiver': 'ha', 'receive_args': {'interface': self.interfaces.ha_dut_1, 'filter': tcpdump_filter,
                                                    'count': 1}},
                {'receiver': 'hb', 'receive_args': {'interface': self.interfaces.hb_dut_1, 'filter': tcpdump_filter,
                                                    'count': 0}}]
            }
            scapy_validation_obj = ScapyChecker(self.players, validation)
            scapy_validation_obj.run_background_validation()

            self.dut.run_cmd(f'ping {self.static_route_24_ip} -c 1')

            scapy_validation_obj.complete_validation()

    def validate_increased_counters(self, expected_threshold=1):
        counters_data = self.dut_cli.interface.parse_interfaces_counters()
        iface_rx_count = counters_data[self.interfaces.dut_ha_1]['RX_OK']
        assert int(iface_rx_count) >= expected_threshold, f'Unexpected RX counter for {self.interfaces.dut_ha_1}.' \
            f' current {iface_rx_count}, expected >={expected_threshold}'

    def test_check_existing_network_show_commands(self):
        """
        This test will check existing show commands output
        :return: raise assertion error in case when test failed
        """
        with allure.step('Validate ARP table'):
            arp_table_data = self.dut_cli.arp.show_arp_table()
            self.validate_arp(arp_table_data)

        with allure.step('Validate "show ip bgp summary"'):
            ip_bgp_summary_data = self.dut_cli.bgp.parse_ip_bgp_summary()
            self.validate_ip_bgp_summary(ip_bgp_summary_data)

        with allure.step('Validate "show ip bgp network"'):
            show_ip_bgp_network_output = self.dut_cli.bgp.show_ip_bgp_network()
            self.validate_ip_bgp_network(show_ip_bgp_network_output)

        with allure.step('Validate "show ip bgp network 0.0.0.0/0"'):
            show_ip_bgp_network_0_output = self.dut_cli.bgp.show_ip_bgp_network(network=self.default_route)
            self.validate_ip_bgp_network_0(show_ip_bgp_network_0_output)

        with allure.step('Validate "show ip bgp neighbors"'):
            show_ip_bgp_neighbors_output = self.dut_cli.bgp.show_ip_bgp_neighbors()
            self.validate_ip_bgp_neighbors(show_ip_bgp_neighbors_output)

        with allure.step('Validate "show ip bgp neighbors 30.0.0.2"'):
            show_ip_bgp_neighbor_output = self.dut_cli.bgp.show_ip_bgp_neighbors(neighbor=self.hb_dut_1_ip)
            self.validate_ip_bgp_neighbor(show_ip_bgp_neighbor_output)

        with allure.step('Validate "show ip route"'):
            parsed_ip_route_output = self.dut_cli.route.show_ip_route(is_json=True)

            self.validate_routes_on_dut(parsed_ip_route_output)

        with allure.step('Validate "show ip route 0.0.0.0/0"'):
            show_ip_route_output_default = self.dut_cli.route.show_ip_route(route=self.default_route)
            self.validate_default_route(show_ip_route_output_default)

        with allure.step('Validate "show ip interfaces"'):
            self.validate_ip_interfaces(interface=self.interfaces.dut_ha_1, expected_ip=self.dut_ha_1_ip)
            self.validate_ip_interfaces(interface=self.interfaces.dut_hb_1, expected_ip=self.dut_hb_1_ip)
            self.validate_ip_interfaces(interface='Loopback0', expected_ip=self.dut_loopback_ip, mask='32')

    def test_check_existing_network_config_commands(self):
        """
        This test will check existing config commands functionality
        :return: raise assertion error in case when test failed
        """
        try:
            with allure.step('Checking command: "config bgp shutdown all"'):
                self.dut_cli.bgp.shutdown_bgp_all()
                ip_bgp_summary_data = self.dut_cli.bgp.parse_ip_bgp_summary()
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.ha_dut_1_ip,
                                                            expected_state='Idle (Admin)')
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.hb_dut_1_ip,
                                                            expected_state='Idle (Admin)')

            with allure.step('Checking command: "config bgp startup all"'):
                self.dut_cli.bgp.startup_bgp_all()
                ip_bgp_summary_data = self.dut_cli.bgp.parse_ip_bgp_summary()
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.ha_dut_1_ip,
                                                            expected_state='Established')
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.hb_dut_1_ip,
                                                            expected_state='Established')

            with allure.step(f'Checking command: "config bgp shutdown neighbor {self.ha_dut_1_ip}"'):
                self.dut_cli.bgp.shutdown_bgp_neighbor(neighbor=self.ha_dut_1_ip)
                ip_bgp_summary_data = self.dut_cli.bgp.parse_ip_bgp_summary()
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.ha_dut_1_ip,
                                                            expected_state='Idle (Admin)')
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.hb_dut_1_ip,
                                                            expected_state='Established')

            with allure.step(f'Checking command: "config bgp startup neighbor {self.ha_dut_1_ip}"'):
                self.dut_cli.bgp.startup_bgp_neighbor(neighbor=self.ha_dut_1_ip)
                ip_bgp_summary_data = self.dut_cli.bgp.parse_ip_bgp_summary()
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.ha_dut_1_ip,
                                                            expected_state='Established')
                self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, self.hb_dut_1_ip,
                                                            expected_state='Established')
        except Exception as err:
            self.dut_cli.bgp.startup_bgp_all()
            raise err

    def test_routing(self):
        """
        This test will do functional validation for routing
        :return: raise assertion error in case when test failed
        """
        with allure.step('Clear counters'):
            self.dut_cli.interface.clear_counters()

        with allure.step('Checking ping from HA to DUT'):
            validation_ha_dut = {'sender': 'ha', 'args': {'interface': self.interfaces.ha_dut_1, 'count': 3,
                                                          'dst': self.dut_ha_1_ip}}
            PingChecker(self.players, validation_ha_dut).run_validation()

        # TODO: restore validation once will get response from developers(or DPU will support counters)
        # with allure.step('Checking increased counters'):
        #     retry_call(self.validate_increased_counters, fargs=[1], tries=3, delay=5, logger=logger)

        with allure.step('Checking ping from HB to DUT'):
            validation_hb_dut = {'sender': 'hb', 'args': {'interface': self.interfaces.hb_dut_1, 'count': 3,
                                                          'dst': self.dut_hb_1_ip}}
            PingChecker(self.players, validation_hb_dut).run_validation()

        with allure.step('Checking routes on HA'):
            self.validate_loopback_route_on_host(self.ha)

        with allure.step('Checking routes on HB'):
            self.validate_loopback_route_on_host(self.hb)

        with allure.step('Traffic validation to Loopback'):
            self.validate_loopback_reachable_from_hosts()

        with allure.step('Checking routes on DUT'):
            parsed_ip_route_output = self.dut_cli.route.show_ip_route(is_json=True)
            self.validate_routes_on_dut(parsed_ip_route_output)

        # TODO: restore validation once will get response from developers(or DPU will support BGP)
        # with allure.step('Traffic validation'):
        #     self.validate_traffic_via_bgp_routes(expected_pass=True)
        #     self.validate_traffic_via_static_routes()

        with allure.step('Shutdown all BGP sessions'):
            self.dut_cli.bgp.shutdown_bgp_all()

        try:
            # TODO: restore validation once will get response from developers(or DPU will support BGP)
            # with allure.step('Traffic validation'):
            #     self.validate_traffic_via_bgp_routes(expected_pass=False)
            #     self.validate_traffic_via_static_routes()
            pass
        except Exception as err:
            raise err
        finally:
            with allure.step('Startup all BGP sessions'):
                self.dut_cli.bgp.startup_bgp_all()

    def test_reboot(self, ha_dut_1_mac, hb_dut_1_mac):
        """
        This test will do reboot/reload and then will call test case which will run functional validation for routing
        :return: raise assertion error in case when test failed
        """
        supported_reboot_modes = ['config reload -y', 'reboot']
        reboot_type = random.choice(supported_reboot_modes)
        self.dut_cli.general.reboot_reload_flow(r_type=reboot_type, topology_obj=self.topology_obj)

        # config below for ARP must be removed later, it's temporary workaround
        self.dut.run_cmd(f'sudo ip neigh add 20.0.0.2 dev {self.interfaces.dut_ha_1} lladdr {ha_dut_1_mac}')
        self.dut.run_cmd(f'sudo ip neigh change 20.0.0.2 dev {self.interfaces.dut_ha_1} lladdr {ha_dut_1_mac}')
        self.dut.run_cmd(f'sudo ip neigh add 30.0.0.2 dev {self.interfaces.dut_hb_1} lladdr {hb_dut_1_mac}')
        self.dut.run_cmd(f'sudo ip neigh change 30.0.0.2 dev {self.interfaces.dut_hb_1} lladdr {hb_dut_1_mac}')

        retry_call(self.check_bgp_sessions, fargs=[], tries=3, delay=5, logger=logger)

        self.test_routing()

    def check_bgp_sessions(self):
        ip_bgp_summary_data = self.dut_cli.bgp.parse_ip_bgp_summary()
        self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, session=self.ha_dut_1_ip,
                                                    expected_state='Established')
        self.dut_cli.bgp.validate_bgp_session_state(ip_bgp_summary_data, session=self.hb_dut_1_ip,
                                                    expected_state='Established')
