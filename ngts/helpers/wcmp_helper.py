import logging
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from ngts.tests.nightly.wcmp.constants import WcmpConsts
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from retry import retry
logger = logging.getLogger()


class WcmpHelper:
    @staticmethod
    def add_and_enable_interface(cli_obj, intf_config):
        """
        Add and enable an interface with IPv4 and IPv6 addresses.

        :param cli_obj: The CLI object for the host.
        :param intf_config: A dictionary containing interface configuration.
        """
        with allure.step(f"Add dummy interface {intf_config['name']}"):
            cli_obj.interface.add_interface(intf_config['name'], 'dummy')
            cli_obj.ip.add_ip_to_interface(intf_config['name'], intf_config['ipv4_addr'], intf_config['ipv4_mask'])
            cli_obj.ip.add_ip_to_interface(intf_config['name'], intf_config['ipv6_addr'], intf_config['ipv6_mask'])
            cli_obj.interface.enable_interface(intf_config['name'])

    @staticmethod
    def get_wcmp_route(host_obj, route, vrf=None):
        """
        Execute command "ip route show x.x.x.x" or "ip route show vrf <vrf-name> x.x.x.x" to get route info on host.
        This function is only available for routes with multiple next hops. If the route has only one next hop,
        the output is different and therefore not applicable.

        :param host_obj: The engine object that has a method to execute commands on the host.
        :param route: The IP route prefix.
        :param vrf: The VRF name (optional).
        :return: A list of dictionaries, each containing the 'nexthop', 'dev', and 'weight' for the route.

        Example:
        admin@r-leopard-41:~$ ip route show 10.0.0.0/24
        10.0.0.0/24 proto bgp metric 20
            nexthop via 2.2.2.3 dev Ethernet0 weight 50
            nexthop via 3.3.3.3 dev Ethernet120 weight 50

        Return:
        [
            {'nexthop': '2.2.2.3', 'dev': 'Ethernet0', 'weight': 50},
            {'nexthop': '3.3.3.3', 'dev': 'Ethernet120', 'weight': 50}
        ]
        """
        if not vrf:
            cmd = f"ip route show {route}"
        else:
            cmd = f"ip route show vrf {vrf} {route}"
        route_info = host_obj.run_cmd(cmd).split('\n')
        route_info_list = [line.strip() for line in route_info]
        routes = []

        for line in route_info_list:
            match = WcmpConsts.ROUTE_PATTERN.search(line)
            if match:
                nexthop, dev, weight = match.groups()
                routes.append({'nexthop': nexthop, 'dev': dev, 'weight': int(weight)})
        logger.info(f'The route is {routes}')

        return routes

    @staticmethod
    def send_recv_traffic(topology_obj, interfaces):
        """
        Send and verify traffic with filter template specified.
        :param topology_obj: topology_obj fixture object
        :param interfaces: interfaces fixture object
        :return: None
        """
        src_ip = WcmpConsts.V4_CONFIG['ha_dut_1']
        dst_ip = WcmpConsts.DUMMY_INTF_HB['ipv4_addr']
        pkt = f'Ether()/IP(src="{src_ip}",dst="{dst_ip}")'
        traffic_validation = {
            'sender': 'ha',
            'send_args': {'interface': f'{interfaces.ha_dut_1}',
                          'packets': pkt,
                          'count': WcmpConsts.PKT_COUNT},
            'receivers': [
                {'receiver': 'hb',
                 'receive_args': {'interface': f'{interfaces.hb_dut_1}',
                                  'filter': WcmpConsts.PKT_FILTER}}
            ]
        }
        logger.info(f"Traffic parameters: {traffic_validation}")
        scapy_r = ScapyChecker(topology_obj.players, traffic_validation)
        scapy_r.run_validation()

    @staticmethod
    @retry(Exception, tries=30, delay=10)
    def get_route_and_verify_weight(duthost, advertised_route, expected_weights, vrf=None):
        """
        Get the routing entries and verify the weight value in the routing entries.

        :param duthost: The DUT host object.
        :param advertised_route: The advertised route to verify.
        :param expected_weights: Dictionary mapping interfaces to their expected weights.
        :param vrf: The VRF name.

        Example:
        routing_entries = [
            {'nexthop': '10.10.26.1', 'dev': 'Ethernet100', 'weight': 16},
            {'nexthop': '10.10.27.1', 'dev': 'Ethernet104', 'weight': 16},
            {'nexthop': '10.10.28.1', 'dev': 'Ethernet108', 'weight': 33},
            {'nexthop': '10.10.29.1', 'dev': 'Ethernet112', 'weight': 33}
        ]

        expected_weights = {
            'Ethernet100': 16,
            'Ethernet104': 16,
            'Ethernet108': 33,
            'Ethernet112': 33
        }
        """
        routing_entries = WcmpHelper.get_wcmp_route(duthost, advertised_route, vrf=vrf)
        logger.info(f'The routing_entries is: {routing_entries}')
        logger.info(f'The expected_weights is: {expected_weights}')

        # Create a set to track which interfaces have been verified
        verified_interfaces = set()

        for route in routing_entries:
            dev_interface = route.get('dev')
            if dev_interface in expected_weights:
                current_weight = route.get('weight')
                expected_weight = expected_weights[dev_interface]
                assert current_weight == expected_weight, f"Expected weight is {expected_weight}, got {current_weight}"
                verified_interfaces.add(dev_interface)

        # Check if all expected_weights interfaces have been verified
        for interface in expected_weights:
            assert interface in verified_interfaces, f"Interface {interface} expected in routing entries but not found"

    @staticmethod
    def verify_wcmp_config_error_info(duthost, invalid_parameter):
        assert f'WCMP: invalid value({invalid_parameter})' in duthost.run_cmd(WcmpConsts.GET_ERR_SYSLOG_CMD)
