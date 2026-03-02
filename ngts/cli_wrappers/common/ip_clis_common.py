import re
import logging

from ngts.cli_wrappers.interfaces.interface_ip_clis import IpCliInterface

logger = logging.getLogger()


class IpCliCommon(IpCliInterface):
    """
    This class hosts methods which are implemented identically for Linux and SONiC
    """

    def __init__(self, engine):
        self.engine = engine

    def add_ip_neigh(self, neighbor, neigh_mac_addr, dev, action="replace"):
        """
        This method adds an neighbor entry to the ARP table
        :param neighbor: neighbor IP address
        :param neigh_mac_addr: neighbor MAC address
        :param dev: interface to which neighbour is attached
        :param action: it includes replace or add, the two both can add ip neigh, replace can replace old neigh
        :return: command output
        """
        return self.engine.run_cmd("sudo ip neigh {} {} lladdr {} dev {}".format(action, neighbor, neigh_mac_addr, dev))

    def add_ip_neigh_list(self, neighbor_list, neigh_mac_addr_list, dev, action="replace"):
        """
        This method adds neighbors entries to the ARP table
        :param neighbor_list: neighbors IP addresses
        :param neigh_mac_addr_list: neighbors MAC addresses
        :param dev: interface to which neighbour is attached
        :param action: it includes replace or add, the two both can add ip neigh, replace can replace old neigh
        """
        for index, _ in enumerate(neighbor_list):
            self.add_ip_neigh(neighbor_list[index], neigh_mac_addr_list[index], dev, action)

    def show_ip_neigh(self):
        """
        This method shows the ip neigh table
        :return: command output
        """
        return self.engine.run_cmd("sudo ip neigh")

    def del_ip_neigh(self, neighbor, neigh_mac_addr, dev):
        """
        This method delete an neighbor entry to the ARP table
        :param neighbor: neighbor IP address
        :param neigh_mac_addr: neighbor MAC address
        :param dev: interface to which neighbour is attached
        :return: command output
        """
        return self.engine.run_cmd("sudo ip neigh del {} lladdr {} dev {}".format(neighbor, neigh_mac_addr, dev))

    def del_ip_neigh_list(self, neighbor_list, neigh_mac_addr_list, dev):
        """
        This method delete neighbors entry to the ARP table
        :param neighbor_list: neighbors IP addresses
        :param neigh_mac_addr_list: neighbors MAC addresses
        :param dev: interface to which neighbour is attached
        """
        for index, _ in enumerate(neighbor_list):
            self.del_ip_neigh(neighbor_list[index], neigh_mac_addr_list[index], dev)

    def del_static_neigh(self):
        """
        This method del the static(PERMANENT) arp from the arp table
        """
        static_arp_regrex = r"(?P<neigh>.*) dev (?P<dev>.*) lladdr (?P<mac>[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{" \
                            r"2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}) .*PERMANENT"
        ip_neigh_table = self.engine.run_cmd("sudo ip neigh")
        for arp_entry in ip_neigh_table.split("\n"):
            static_arp_entry = re.match(static_arp_regrex, arp_entry.strip())
            if static_arp_entry:
                static_arp_entry = static_arp_entry.groupdict()
                logger.info("Del static arp:{}".format(static_arp_entry))
                self.del_ip_neigh(static_arp_entry["neigh"], static_arp_entry["mac"], static_arp_entry["dev"])
