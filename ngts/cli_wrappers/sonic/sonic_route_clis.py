import json
import re

from ngts.cli_wrappers.common.route_clis_common import RouteCliCommon
from ngts.cli_wrappers.sonic.sonic_multi_asic_cli import SonicMultiAsicCli
from ngts.helpers.network import is_ip_address


class SonicRouteCli(RouteCliCommon, SonicMultiAsicCli):

    def __init__(self, engine, asic_id=None):
        SonicMultiAsicCli.__init__(self, engine, asic_id)

    def add_del_route(self, action, dst, via, dst_mask, vrf):
        """
        This method create/remove static IP route
        :param action: action which should be executed - add or del
        :param dst: IP address for host or subnet
        :param via: Gateway IP address or interface name
        :param dst_mask: mask for dst IP
        :param vrf: vrf name - in case when need to add/remove route in custom vrf
        :return: command output
        """
        if action not in ['add', 'del']:
            raise NotImplementedError('Incorrect action {} provided, supported only add/del'.format(action))

        cmd = 'sudo config route {} {} prefix '.format(self.multi_asic_config_cmd_ext, action)
        if vrf:
            cmd += 'vrf {} '.format(vrf)

        if not is_ip_address(via):
            via = 'dev {}'.format(via)

        cmd += '{}/{} nexthop {}'.format(dst, dst_mask, via)

        return self.engine.run_cmd(cmd)

    def add_route(self, dst, via, dst_mask, vrf=None):
        """
        This method create static IP route
        :param dst: IP address for host or subnet
        :param via: Gateway IP address or interface name
        :param dst_mask: mask for dst IP
        :param vrf: vrf name - in case when need to add route in custom vrf
        :return: add_del_route method
        """
        self.add_del_route('add', dst, via, dst_mask, vrf)

    def del_route(self, dst, via, dst_mask, vrf=None):
        """
        This method deletes static IP route
        :param dst: IP address for host or subnet
        :param via: Gateway IP address or interface name
        :param dst_mask: mask for dst IP
        :param vrf: vrf name - in case when need to del route in custom vrf
        :return: add_del_route method
        """
        self.add_del_route('del', dst, via, dst_mask, vrf)

    def show_ip_route(self, route_type=None, ipv6=False, route=None, vrf=None, is_json=False):
        """
        This method gets IP routes from device
        :param route_type: route type(example: static, bgp)
        :param ipv6: True if need to get IPv6 routes
        :param route: IP address - for which we need to find route(example: 1.1.1.1 or 1.1.1.0/24)
        :param vrf: vrf name for which we need to see routes(example: all)
        :return: command output
        """
        if route_type and route:
            raise Exception('It is not allowed to use together route_type and route arguments')

        cmd = 'show {} route '.format('ipv6' if ipv6 else 'ip')
        if vrf:
            cmd += 'vrf {} '.format(vrf)
        if route_type:
            cmd += route_type
        if route:
            cmd += route
        cmd = "{} {}".format(cmd, self.multi_asic_config_cmd_ext)
        if is_json:
            cmd += ' json'
            return json.loads(self.engine.run_cmd(cmd))
        return self.engine.run_cmd(cmd)

    @staticmethod
    def generate_route_app_data(route_list, mask_list, n_hop_list, ifaces_list, route_app_config_path=None, op='SET'):
        """
        This method generate APP route json data - save it to file. It can be used by swss docker for apply routes
        :param route_list: list with route subnet IPs: ["192.168.0.0", "192.168.0.1"]
        :param mask_list: list with subnet masks ["32", "32"]
        :param n_hop_list: list with route next-hops ["192.168.5.1", "10.20.30.5"]
        :param ifaces_list: list with route interfaces ["Ethernet0", "Ethernet12"]
        :param route_app_config_path: path to file where app config should be stored: "/tmp/route_config.json"
        :param op: app config operation, can be "SET" for add route or "DEL" for remove route
        :return: routes app config(the same as written in file)
        """
        route_app_config_data = []

        for route, mask, n_hop, iface in zip(route_list, mask_list, n_hop_list, ifaces_list):
            route_entry = {"ROUTE_TABLE:{}/{}".format(route, mask): {"nexthop": n_hop, "ifname": iface},
                           "OP": "{}".format(op)}
            route_app_config_data.append(route_entry)

        if route_app_config_path:
            with open(route_app_config_path, 'w') as file:
                json.dump(route_app_config_data, file)

        return route_app_config_data

    @staticmethod
    def parse_show_ip_route(show_ip_route_output):
        """
        Parse output of command "show ip route"
        :param show_ip_route_output: "show ip route" output, example:
        Codes: K - kernel route, C - connected, S - static, R - RIP,
        O - OSPF, I - IS-IS, B - BGP, E - EIGRP, N - NHRP,
        T - Table, v - VNC, V - VNC-Direct, A - Babel, D - SHARP,
        F - PBR, f - OpenFabric,
        > - selected route, * - FIB route, q - queued, r - rejected, b - backup

        B>* 0.0.0.0/0 [20/0] via 20.0.0.2, Ethernet128, weight 1, 00:04:56
          *                  via 30.0.0.2, Ethernet0, weight 1, 00:04:56
        C>* 10.10.10.10/32 is directly connected, Loopback0, 00:05:53
        C>* 10.210.24.0/22 is directly connected, eth0, 00:06:07
        C>* 20.0.0.0/24 is directly connected, Ethernet128, 00:04:57
        C>* 30.0.0.0/24 is directly connected, Ethernet0, 00:04:57
        S>* 50.0.0.0/24 [1/0] via 20.0.0.2, Ethernet128, weight 1, 00:04:57
        S>* 50.0.0.1/32 [1/0] via 30.0.0.2, Ethernet0, weight 1, 00:04:57
        :return: dictionary with parsed "show ip route" output, example:
        {'0.0.0.0/0': {'route_dst': '0.0.0.0/0', 'route_type': 'B', 'weight': '1',
        'interfaces': ['Ethernet128', 'Ethernet0'], 'next_hops': ['20.0.0.2', '30.0.0.2']},
        '10.10.10.10/32': {'route_dst': '10.10.10.10/32', 'route_type': 'C', 'weight': None,
        'interfaces': ['Loopback0'], 'next_hops': [None]},
        ...
        """
        _, routes_data = show_ip_route_output.split('\n\n')
        route_entries_list = prapare_route_entries_list(routes_data)
        routes_dict = parse_route_entris_list_as_dict(route_entries_list)

        return routes_dict

    def get_next_hops(self, routes):
        """
        This method is to get next hops for routes
        :param routes: list of routes
        :return: list of next hops
        """
        next_hops = {'intf': [], 'ip': []}
        for route in routes:
            for next_hop in route['nexthops']:
                next_hops['intf'].append(next_hop['interfaceName'])
                next_hops['ip'].append(next_hop['ip'])
        return next_hops


def prapare_route_entries_list(routes_data):
    """
    Prepare list with strings info about routes
    :param routes_data: string with routes data, example:
    B>* 0.0.0.0/0 [20/0] via 20.0.0.2, Ethernet128, weight 1, 00:12:41
      *                  via 30.0.0.2, Ethernet0, weight 1, 00:12:41
    C>* 10.10.10.10/32 is directly connected, Loopback0, 00:13:38
    ...
    :return: list with strings which contains routes data, example:
    [['B>* 0.0.0.0/0 [20/0] via 20.0.0.2, Ethernet128, weight 1, 00:12:41',
    '  *                  via 30.0.0.2, Ethernet0, weight 1, 00:12:41'],
    ['C>* 10.10.10.10/32 is directly connected, Loopback0, 00:13:38'], ...]
    """

    route_entries_list = []
    for route_entry in routes_data.splitlines():
        if not route_entry.startswith(' '):
            route_entries_list.append([route_entry])
        else:
            route_entries_list[-1].append(route_entry)

    return route_entries_list


def parse_route_entris_list_as_dict(route_entries_list):
    """
    Parse route entries list as dict
    :param route_entries_list: example:
    [['B>* 0.0.0.0/0 [20/0] via 20.0.0.2, Ethernet128, weight 1, 00:12:41',
    '  *                  via 30.0.0.2, Ethernet0, weight 1, 00:12:41'],
    ['C>* 10.10.10.10/32 is directly connected, Loopback0, 00:13:38'], ...]
    :return: dictionary with parsed "show ip route" output, example:
    {'0.0.0.0/0': {'route_dst': '0.0.0.0/0', 'route_type': 'B', 'weight': '1',
    'interfaces': ['Ethernet128', 'Ethernet0'], 'next_hops': ['20.0.0.2', '30.0.0.2']},
    '10.10.10.10/32': {'route_dst': '10.10.10.10/32', 'route_type': 'C', 'weight': None,
    'interfaces': ['Loopback0'], 'next_hops': [None]},
    ...
    """
    routes_dict = {}
    for route_entry_list in route_entries_list:
        result = {}
        route_dst = None
        for route_entry in route_entry_list:
            if not result:
                data = parse_route_from_str(route_entry)
                route_dst = data['route_dst']
                result[route_dst] = data
            else:
                next_hop, iface = parse_ecmp_route(route_entry)
                result[route_dst]['interfaces'].append(iface)
                result[route_dst]['next_hops'].append(next_hop)
        '''
        example of result variable:
        {'50.0.0.1/32': {'route_dst': '50.0.0.1/32', 'route_type': 'S', 'weight': '1', 'interfaces': ['Ethernet0'],
        'next_hops': ['30.0.0.2']}}
        '''
        routes_dict.update(result)

    return routes_dict


def parse_route_from_str(route_entry):
    """
    Parse route entry from string
    :param route_entry: string with route info, could be one of:
    B>* 0.0.0.0/0 [20/0] via 20.0.0.2, Ethernet128, weight 1, 00:04:56
      *                  via 30.0.0.2, Ethernet0, weight 1, 00:04:56
    C>* 10.10.10.10/32 is directly connected, Loopback0, 00:05:53
    :return: dictionary with parsed data
    """
    next_hop = None
    weight = None

    regexp_route = r'(\w)>\*\s(\d+.\d+.\d+.\d+/\d+)\s\[\d+/0]\svia\s(\d+.\d+.\d+.\d+),\s(\w+),\sweight\s(\d+)'
    try:
        route_type, route_dst, next_hop, interface, weight = re.search(regexp_route, route_entry).groups()
    except AttributeError:
        regexp_direct_route = r'(\w)>\*\s(\d+.\d+.\d+.\d+/\d+)\sis\sdirectly\sconnected,\s(\w+)'
        route_type, route_dst, interface = re.search(regexp_direct_route, route_entry).groups()

    result = {'route_dst': route_dst, 'route_type': route_type, 'weight': weight, 'interfaces': [interface],
              'next_hops': [next_hop]}

    return result


def parse_ecmp_route(route_entry):
    """
    Parse ECMP route
    :param route_entry: string, example:
      *                  via 30.0.0.2, Ethernet0, weight 1, 00:04:56
    :return: strings with nexthop and interface, example: '30.0.0.2', 'Ethernet0'
    """
    regexp_route = r'\s+\*\s+via\s(\d+.\d+.\d+.\d+),\s(\w+)'
    next_hop, interface = re.search(regexp_route, route_entry).groups()
    return next_hop, interface
