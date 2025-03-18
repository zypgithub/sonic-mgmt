import logging

from ngts.cli_wrappers.common.vlan_clis_common import VlanCliCommon

logger = logging.getLogger()


class SonicVlanCli:

    def __new__(cls, **kwargs):
        branch = kwargs['branch']
        engine = kwargs['engine']

        supported_cli_classes = {'default': SonicVlanCliDefault(engine),
                                 '202012': SonicVlanCli202012(engine)}

        cli_class = supported_cli_classes.get(branch, supported_cli_classes['default'])
        cli_class_name = cli_class.__class__.__name__
        logger.info(f'Going to use VLAN CLI class: {cli_class_name}')

        return cli_class


class SonicVlanCliDefault(VlanCliCommon):

    def __init__(self, engine):
        self.engine = engine

    def configure_vlan_and_add_ports(self, vlan_info):
        """
        Method which adding VLAN and ports to VLAN on SONiC device
        :param vlan_info: vlan info dictionary
        {'vlan_id': vlan id, 'vlan_members': [{port name: vlan mode}]}
        Example: {'vlan_id': 500, 'vlan_members': [{eth1: 'trunk'}]}
        :return: command output
        """
        self.add_vlan(vlan_info['vlan_id'])
        for vlan_port_and_mode_dict in vlan_info['vlan_members']:
            for vlan_port, mode in vlan_port_and_mode_dict.items():
                self.add_port_to_vlan(vlan_port, vlan_info['vlan_id'], mode)

    def delete_vlan_and_remove_ports(self, vlan_info):
        """
        Method which remove ports from VLANs and VLANs on SONiC device
        :param vlan_info: vlan info dictionary
        {'vlan_id': vlan id, 'vlan_members': [{port name: vlan mode}]}
        Example: {'vlan_id': 500, 'vlan_members': [{eth1: 'trunk'}]}
        :return: command output
        """
        for vlan_port_and_mode_dict in vlan_info['vlan_members']:
            for vlan_port, mode in vlan_port_and_mode_dict.items():
                self.del_port_from_vlan(vlan_port, vlan_info['vlan_id'])
        self.del_vlan(vlan_info['vlan_id'])

    def add_vlan(self, vlan):
        """
        Method which adding VLAN to SONiC dut
        :param vlan: vlan ID
        :return: command output
        """
        return self.engine.run_cmd("sudo config vlan add {}".format(vlan))

    def del_vlan(self, vlan):
        """
        Method which removing VLAN from SONiC dut
        :param vlan: vlan ID
        :return: command output
        """
        return self.engine.run_cmd("sudo config vlan del {}".format(vlan))

    def add_port_to_vlan(self, port, vlan, mode='trunk'):
        """
        Method which adding physical port to VLAN on SONiC dut
        :param port: network port which should be VLAN member
        :param vlan: vlan ID
        :param mode: port mode - access or trunk
        :return: command output
        """
        if mode == 'trunk':
            return self.engine.run_cmd("sudo config vlan member add {} {}".format(vlan, port))
        elif mode == 'access':
            return self.engine.run_cmd("sudo config vlan member add --untagged {} {}".format(vlan, port))
        else:
            raise Exception('Incorrect port mode: "{}" provided, expected "trunk" or "access"')

    def del_port_from_vlan(self, port, vlan):
        """
        Method which deleting physical port from VLAN on SONiC dut
        :param port: network port which should be deleted from VLAN members
        :param vlan: vlan ID
        :return: command output
        """
        return self.engine.run_cmd("sudo config vlan member del {} {}".format(vlan, port))

    def show_vlan_config(self):
        """
        This method performs show vlan command
        :return: command output
        """
        return self.engine.run_cmd("show vlan config")

    def shutdown_vlan(self, vlan):
        """
        This method is to shutdown vlan
        :param vlan: vlan ID
        :return: command output
        """
        return self.engine.run_cmd("sudo ip link set dev Vlan{} down".format(vlan))

    def startup_vlan(self, vlan):
        """
        This method is to startup vlan
        :param vlan: vlan ID
        :return: command output
        """
        return self.engine.run_cmd("sudo ip link set dev Vlan{} up".format(vlan))

    def disable_vlan_arp_proxy(self, vlan):
        """
        This method is to disable arp proxy in vlan
        :param vlan: vlan ID
        :return: command output
        """
        return self.engine.run_cmd("sudo config vlan proxy_arp {} disabled".format(vlan), validate=True)

    def enable_vlan_arp_proxy(self, vlan):
        """
        This method is to enable arp proxy in vlan
        :param vlan: vlan ID
        :return: command output
        """
        return self.engine.run_cmd("sudo config vlan proxy_arp {} enabled".format(vlan), validate=True)

    def show_vlan_brief(self):
        """
        This method performs "show vlan brief"
        :return: command output
        """
        return self.engine.run_cmd("show vlan brief")

    def get_show_vlan_brief_parsed_output(self, show_vlan_brief_output=None, data_line_index=4):
        """
        This method parses the "show vlan brief" output and returns a dictionary with the parsed data
        :param show_vlan_brief_output: output from command "show vlan brief"
        :return: dictionary with parsed data
        """
        if not show_vlan_brief_output:
            show_vlan_brief_output = self.show_vlan_brief()
        show_vlan_brief_parsed_dict = self.show_vlan_brief_parser(show_vlan_brief_output, data_line_index=data_line_index)
        return show_vlan_brief_parsed_dict

    @staticmethod
    def show_vlan_brief_parser(output, vlan_index=0, ip_addr_index=1, vlan_port_index=2, vlan_port_mode_index=3,
                               proxy_arp_index=4, dhcp_server_index=5, data_line_index=4):
        """
        This method doing parse for command "show vlan brief" output
        :param output: command "show vlan brief" output which should be parsed
        :param vlan_index: index for VLAN id in output list
        :param ip_addr_index: index for IP address in output list
        :param vlan_port_index: index for VLAN port in output list
        :param vlan_port_mode_index: index for VLAN port mode in output list
        :param proxy_arp_index: index for proxy ARP in output list
        :param dhcp_server_index: index for DHCP server in output list
        :param data_line_index: index from which data lines starts in output
        :return: dictionary with parsed data.

        Example:
        {'40': {'ips': ['4000::1/64', '40.0.0.1/24'],
                'ports': {'Ethernet236': 'tagged', 'PortChannel0002': 'tagged'},
                'dhcp_servers': [], 'proxy_arp': 'disabled'},
        '69': {'ips': ['69.0.0.1/24'..... ]}}
        """
        result_dict = {}

        # Read data without headers
        data_lines = output.splitlines()[data_line_index:]

        vlan = None
        vlan_ips = []
        vlan_ports = {}
        dhcp_servers = []
        proxy_arp = None

        for line in data_lines:
            # Skip lines like: +-----------+--------------+----- which does not
            # have data, analyze only lines with data
            splited_data_line = line.split('|')[1:]
            if splited_data_line:
                vlan_id = splited_data_line[vlan_index].strip()
                if vlan_id:
                    # If next vlan data started - clean previous data
                    if vlan != vlan_id:
                        vlan = None
                        vlan_ips = []
                        vlan_ports = {}
                        dhcp_servers = []
                        proxy_arp = None

                    vlan = vlan_id
                    proxy_arp = splited_data_line[proxy_arp_index].strip()

                vlan_ip = splited_data_line[ip_addr_index].strip()
                vlan_port = splited_data_line[vlan_port_index].strip()
                dhcp_server = splited_data_line[dhcp_server_index].strip()

                if vlan_ip:
                    vlan_ips.append(vlan_ip)
                if vlan_port:
                    vlan_ports[vlan_port] = splited_data_line[vlan_port_mode_index].strip()
                if dhcp_server:
                    dhcp_servers.append(dhcp_server)

                result_dict[vlan] = {'ips': vlan_ips, 'ports': vlan_ports, 'dhcp_servers': dhcp_servers,
                                     'proxy_arp': proxy_arp}

        return result_dict


class SonicVlanCli202012(SonicVlanCliDefault):

    def __init__(self, engine):
        self.engine = engine

    def get_show_vlan_brief_parsed_output(self, show_vlan_brief_output=None):
        """
        :param show_vlan_brief_output: output from command "show vlan brief"
        :return: dictionary with parsed data
        """
        if not show_vlan_brief_output:
            show_vlan_brief_output = self.show_vlan_brief()
        show_vlan_brief_parsed_dict = self.show_vlan_brief_parser(show_vlan_brief_output, proxy_arp_index=5,
                                                                  dhcp_server_index=4)
        return show_vlan_brief_parsed_dict
