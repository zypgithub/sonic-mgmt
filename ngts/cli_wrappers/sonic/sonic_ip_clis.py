import netaddr
import re
import json

from ngts.cli_wrappers.common.ip_clis_common import IpCliCommon
from ngts.cli_wrappers.sonic.sonic_multi_asic_cli import SonicMultiAsicCli
from ngts.helpers.network import generate_mac
from ngts.cli_util.cli_parsers import generic_sonic_output_parser
from ngts.constants.constants import IpIfaceAddrConst, SonicConst


class SonicIpCli(IpCliCommon, SonicMultiAsicCli):

    def __init__(self, engine, asic_id=None):
        SonicMultiAsicCli.__init__(self, engine, asic_id)

    def add_ip_neigh(self, neighbor, neigh_mac_addr, dev, action="replace"):
        """
        Add or update a neighbor entry in the ARP/NDP table. Uses multi-ASIC namespace when needed.
        :param neighbor: neighbor IP address
        :param neigh_mac_addr: neighbor MAC address
        :param dev: interface to which neighbour is attached
        :param action: "add", "change", or "replace"
        """
        return self.engine.run_cmd(
            "sudo ip {} neigh {} {} lladdr {} dev {}".format(self.multi_asic_config_cmd_ext, action, neighbor, neigh_mac_addr, dev))

    def ip_neigh_flush(self, dev):
        """
        Flush neighbor entries for an interface. Uses multi-ASIC namespace when needed.
        :param dev: interface name (e.g. Ethernet0)
        """
        return self.engine.run_cmd("sudo ip {} neigh flush dev {}".format(self.multi_asic_config_cmd_ext, dev))

    def add_del_ip_from_interface(self, action, interface, ip, mask):
        """
        This method adds/remove ip address to/from network interface
        :param action: action which should be executed: add or remove
        :param interface: interface name to which IP should be assigned/removed
        :param ip: ip address which should be assigned/removed
        :param mask: mask which should be assigned/remove to/from IP
        :return: method which do required action
        """
        if action not in ['add', 'remove']:
            raise NotImplementedError(
                'Incorrect action {} provided, supported only add/del'.format(action))

        self.engine.run_cmd(
            'sudo config interface {} ip {} {} {}/{}'.format(self.multi_asic_config_cmd_ext, action, interface, ip, mask))

    def add_ip_to_interface(self, interface, ip, mask=24):
        """
        This method adds IP to SONiC interface
        :param interface: interface name to which IP should be assigned
        :param ip: ip address which should be assigned
        :param mask: mask which should be assigned to IP
        :return: command output
        """
        self.add_del_ip_from_interface('add', interface, ip, mask)

    def del_ip_from_interface(self, interface, ip, mask=24):
        """
        This method removes IP from SONiC interface
        :param interface: interface name from which IP should be removed
        :param ip: ip address which should be removed
        :param mask: network mask
        :return: command output
        """
        self.add_del_ip_from_interface('remove', interface, ip, mask)

    def show_ip_interfaces(self):
        """
        This method shows ip configuration on interfaces
        :return: the output of the command "show ip interfaces"
        """
        return self.engine.run_cmd('sudo show ip interfaces')

    def show_ipv6_interfaces(self):
        """
        This method shows ipv6 configuration on interfaces
        :return: the output of the command "show ipv6 interfaces"
        """
        return self.engine.run_cmd('sudo show ipv6 interfaces')

    @staticmethod
    def generate_neighbors_cfg(amount, start_ip, iface, family, operation):
        """
        This method generates config with specific amount of IP neighbors which can be applied via swss container
        :param amount: amount of ip neighbors to be created
        :param start_ip: neighbor IP address from which to start counting
        :param iface: the interface to which neighbors are attached
        :param family: IPV4 or IPV6 family
        :param operation: "SET" to apply config. "DEL" to delete config.
        """
        entry_key_template = "NEIGH_TABLE:{iface}:{ip}"
        config_json = []

        mac_lst = generate_mac(amount)

        for cnt in range(amount):
            ip_addr = netaddr.IPAddress(start_ip) + cnt
            entry_json = {entry_key_template.format(iface=iface, ip=ip_addr):
                          {"neigh": mac_lst[cnt], "family": family},
                          "OP": operation
                          }
            config_json.append(entry_json)
        return config_json

    @staticmethod
    def generate_routes_cfg(amount, start_ip, nexthop, iface, operation):
        """
        This method generates config with specific amount of IP routes which can be applied via swss container
        :param amount: amount of ip routes to be created
        :param start_ip: route IP address from which to start counting
        :param nexthop: reachable nexthop IP address
        :param iface: the interface to which nexthop is attached
        :param operation: "SET" to apply config. "DEL" to delete config.
        """
        entry_key_template = "ROUTE_TABLE:{network}"
        config_json = []
        # set mask: 32 for ipv4, 128 for ipv6
        mask = 32 if re.match(r"^([0-9]+(\.|$)){4}", start_ip) else 128

        for cnt in range(amount):
            network = netaddr.IPAddress(start_ip) + cnt
            entry_json = {entry_key_template.format(network=network.format() + "/{}".format(mask)):
                          {"nexthop": nexthop, "ifname": iface},
                          "OP": operation
                          }
            config_json.append(entry_json)
        return config_json

    def generate_routes_cfg_w_nexthop_group(self, nx_group_amount, start_ip, neighbor_cfg, operation):
        """
        This method generates config with specific amount of IP routes which can be applied via swss container
        :param nx_group_amount: amount of ip routes to be created
        :param start_ip: route IP address from which to start counting
        :param neighbor_cfg: config generated by 'generate_neighbors_cfg' method
        :param operation: "SET" to apply config. "DEL" to delete config.
        """
        entry_key_template = "ROUTE_TABLE:{network}"
        config_json = []
        # set mask: 32 for ipv4, 128 for ipv6
        mask = 32 if re.match(r"^([0-9]+(\.|$)){4}", start_ip) else 128

        fail_msg = ("Not enough neighbors to create a unique nexthop group for each route."
                    "Expected routes to be created - {}; Expected neighbors - {}. Available neighbors - {}".format(
                        nx_group_amount, nx_group_amount * 2, len(neighbor_cfg)
                    )
                    )

        assert len(neighbor_cfg) >= (nx_group_amount * 2), fail_msg

        neigh_id = 0
        for cnt in range(nx_group_amount):
            network = netaddr.IPAddress(start_ip) + cnt
            # Sequentially get unique pair of neighbors
            neighs = neighbor_cfg[neigh_id: neigh_id + 2]
            neigh_id += 2

            iface, nexthop = self.compose_neighbor_pairs(neighs)

            entry_json = {entry_key_template.format(network=network.format() + "/{}".format(mask)):
                          {"nexthop": nexthop, "ifname": iface},
                          "OP": operation
                          }
            config_json.append(entry_json)
        return config_json

    @staticmethod
    def compose_neighbor_pairs(lst_neigh_config):
        """
        Compose nexthops and linked with them interfaces
        :param lst_neigh_config: list of neighbors config, generated by 'generate_neighbors_cfg' method
        """
        nexthops = []
        ifnames = []
        # Compose unique pair of neighbors
        for item in lst_neigh_config:
            for key, value in item.items():
                if "NEIGH_TABLE" in key:
                    line = key.replace("NEIGH_TABLE:", "")
                    separator = line.find(":")
                    iface_name = line[:separator]
                    nexthop_name = line[separator + 1:]

                    ifnames.append(iface_name)
                    nexthops.append(nexthop_name)

        iface = ",".join(ifnames)
        nexthop = ",".join(nexthops)
        return iface, nexthop

    def get_interface_ips(self, interface):
        """
        This method get ip address and mask on specified interface
        :return: list of ip and mask of the interface, empty list will return if no ip address configured for the interface
                 example for [{'ip': '10.0.0.2', 'mask': 24},{'ip': '20.0.0.2', 'mask': 24}]
        """

        ip_list = []
        cmd_list = ['sudo show ip interfaces', 'sudo show ipv6 interfaces']
        for cmd in cmd_list:
            output = self.engine.run_cmd(cmd)
            interfaces = generic_sonic_output_parser(output, headers_ofset=0, len_ofset=1, data_ofset_from_start=2,
                                                     data_ofset_from_end=None, column_ofset=2, output_key="Interface")
            if interface in interfaces.keys():
                interface_dict_list = self.get_interface_dict_list(
                    interfaces, interface)
                for interface_dict in interface_dict_list:
                    ip_key = self.get_ip_type_key(interface_dict)
                    if isinstance(interface_dict[ip_key], list):
                        for ip_addr in interface_dict[ip_key]:
                            ip, mask = ip_addr.split('/')
                            ip_list.append({'ip': ip, 'mask': mask})
                    else:
                        ip_addr = interface_dict[ip_key]
                        ip, mask = ip_addr.split('/')
                        ip_list.append({'ip': ip, 'mask': mask})

        return ip_list

    @staticmethod
    def get_interface_dict_list(interfaces, interface):
        """
        This method is to make sure the interface dict for the specified interface is contained into a list
        :param interfaces: the dict of the interfaces
        :param interface: the interface name, such as Ethernet0
        :return: list of interface dict, such as [{Interface: Ethernet0, ....}]
        """

        interface_dict_list = interfaces[interface]
        if not isinstance(interface_dict_list, list):
            interface_dict_list = [interface_dict_list]

        return interface_dict_list

    @staticmethod
    def get_ip_type_key(interface_dict):
        """
        get the ip type key, when IPV6_ADDR_MASK_KEY is in the header, use it, else, use IPV4_ADDR_MASK_KEY
        :param interface_dict: interface dict
        :return: the header name.
        """
        return IpIfaceAddrConst.IPV6_ADDR_MASK_KEY if IpIfaceAddrConst.IPV6_ADDR_MASK_KEY in interface_dict else IpIfaceAddrConst.IPV4_ADDR_MASK_KEY

    def apply_dns_servers_into_resolv_conf(self, is_air_setup=False):
        """
        Set into /etc/resolv.conf DNS servers
        :param is_air_setup: is NvidiaAir setup - True, else False
        """
        if is_air_setup:
            self.apply_nvidia_air_dns_servers_resolv_conf()
        else:
            self.apply_nvidia_lab_dns_servers_resolv_conf()
        self.engine.run_cmd("sudo config save -y")

    def apply_nvidia_lab_dns_servers_resolv_conf(self):
        """
        Set into /etc/resolv.conf Nvidia LAB DNS servers
        """
        if self.is_static_dns_supported():
            nameservers = [SonicConst.NVIDIA_LAB_DNS_FIRST, SonicConst.NVIDIA_LAB_DNS_SECOND,
                           SonicConst.NVIDIA_LAB_DNS_THIRD]
            self.add_dns_nameservers(nameservers)
        else:
            tmp_resolv_conf_path = f'/tmp/{SonicConst.RESOLV_CONF_NAME}'
            self.engine.run_cmd(f'sudo echo "nameserver {SonicConst.NVIDIA_LAB_DNS_FIRST}" > {tmp_resolv_conf_path}')
            self.engine.run_cmd(f'sudo echo "nameserver {SonicConst.NVIDIA_LAB_DNS_SECOND}" >> {tmp_resolv_conf_path}')
            self.engine.run_cmd(f'sudo echo "nameserver {SonicConst.NVIDIA_LAB_DNS_THIRD}" >> {tmp_resolv_conf_path}')
            self.engine.run_cmd(f'sudo echo "search {SonicConst.NVIDIA_LAB_DNS_SEARCH}" >> {tmp_resolv_conf_path}')
            self.engine.run_cmd(f'sudo mv {tmp_resolv_conf_path} {SonicConst.RESOLV_CONF_PATH}')

    def apply_nvidia_air_dns_servers_resolv_conf(self):
        """
        Set into /etc/resolv.conf NvidiaAir DNS servers
        """
        if self.is_static_dns_supported():
            nameservers = [SonicConst.NVIDIA_AIR_DNS_FIRST, SonicConst.NVIDIA_AIR_DNS_SECOND]
            self.add_dns_nameservers(nameservers)
        else:
            tmp_resolv_conf_path = f'/tmp/{SonicConst.RESOLV_CONF_NAME}'
            self.engine.run_cmd(f'sudo echo "nameserver {SonicConst.NVIDIA_AIR_DNS_FIRST}" > {tmp_resolv_conf_path}')
            self.engine.run_cmd(f'sudo echo "nameserver {SonicConst.NVIDIA_AIR_DNS_SECOND}" >> {tmp_resolv_conf_path}')
            self.engine.run_cmd(f'sudo mv {tmp_resolv_conf_path} {SonicConst.RESOLV_CONF_PATH}')

    def is_static_dns_supported(self):
        res = self.engine.run_cmd("show dns nameserver")
        return 'Error: No such command "dns"' not in res

    def add_dns_nameservers(self, nameservers):
        for nameserver in nameservers:
            self.engine.run_cmd("sudo config dns nameserver add {}".format(nameserver))

    def get_mgmt_interface_ipv4_address(self):
        """
        Get eth0 mgmt interface IPv4 address
        :return: string, IPv4 address
        """
        mgmt_iface_data = self.engine.run_cmd('ip -j addr show dev eth0')
        mgmt_ips_list = json.loads(mgmt_iface_data)[0]['addr_info']
        mgmt_ip_v4_addr = None
        for mgmt_ip_data in mgmt_ips_list:
            if mgmt_ip_data['family'] == 'inet':
                mgmt_ip_v4_addr = mgmt_ip_data['local']
                break
        return mgmt_ip_v4_addr
