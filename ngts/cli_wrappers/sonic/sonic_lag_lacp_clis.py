from ngts.cli_wrappers.common.lag_lacp_clis_common import LagLacpCliCommon
from ngts.cli_wrappers.sonic.sonic_multi_asic_cli import SonicMultiAsicCli
from ngts.cli_util.verify_cli_show_cmd import verify_show_cmd


class SonicLagLacpCli(LagLacpCliCommon, SonicMultiAsicCli):

    def __init__(self, engine, asic_id=None):
        SonicMultiAsicCli.__init__(self, engine, asic_id)

    def create_lag_interface_and_assign_physical_ports(self, lag_lacp_info):
        """
        This method is applies LAG configuration, according to the parameters specified in the configuration dict
        :param lag_lacp_info: configuration dictionary with all LAG/LACP related info
        Syntax: {'type': 'lag type', 'name':'port_name', 'members':[list of LAG members], 'params': 'parameters'}
        Example: {'type': 'lacp', 'name': 'PortChannel0001', 'members': [eth1], 'params': '--min-links 2
        --fallback enable'}
        """
        lag_lacp_iface_name = lag_lacp_info['name']
        lag_type = lag_lacp_info['type']
        lag_lacp_interface_params = lag_lacp_info['params'] if 'params' in lag_lacp_info else ''

        if lag_type == 'lag':
            raise Exception('Static LAG mode is currently not supported in SONiC')
        elif lag_type == 'lacp':
            self.create_lag_interface(lag_lacp_iface_name, lag_lacp_interface_params)
        else:
            raise Exception('Unknown lag type was provided by the user: {}. The valid types are: lacp.'
                            .format(lag_type))

        for member_port in lag_lacp_info['members']:
            self.add_port_to_port_channel(member_port, lag_lacp_iface_name)

    def delete_lag_interface_and_unbind_physical_ports(self, lag_lacp_info):
        """
        This method deletes LAG configuration, according to the parameters specified in the configuration dict
        :param lag_lacp_info: configuration dictionary with all LAG/LACP related info
        Syntax: {'type': 'lag type', 'name':'port_name', 'members':[list of LAG members]}
        Example: {'type': 'lacp', 'name': 'PortChannel0001', 'members': [eth1]}
        """
        lag_lacp_iface_name = lag_lacp_info['name']
        lag_type = lag_lacp_info['type']

        for member_port in lag_lacp_info['members']:
            self.delete_port_from_port_channel(member_port, lag_lacp_iface_name)

        if lag_type == 'lag':
            raise Exception('Static LAG mode is currently not supported in SONiC')
        elif lag_type == 'lacp':
            self.delete_lag_interface(lag_lacp_iface_name)
        else:
            raise Exception('Unknown lag type was provided by the user: {}. The valid types are: lacp.'
                            .format(lag_type))

    def verify_port_channel_status(self, lag_name, lag_status, expected_members_status_list):
        """
        Verify the PortChannels from "show interfaces portchannel" output, accordingly to handed statuses
        :param lag_name: port channel name
        :param lag_status: port channel status
        :param expected_members_status_list: list of tuples - [('Ethernet0', 'S'), ('Ethernet120', 'D')]
        """
        if expected_members_status_list:
            lag_expected_info = self.get_port_channel_members_expected_info_regex(lag_name, lag_status,
                                                                                  expected_members_status_list)
        else:
            lag_expected_info = self.get_port_channel_expected_info_regex(lag_name, lag_status)

        port_channel_info = self.show_interfaces_port_channel()
        verify_show_cmd(port_channel_info, lag_expected_info)

    @staticmethod
    def get_port_channel_expected_info_regex(lag_name, lag_status):
        """
        Returns regular expression format for validation of port channel
        :param lag_name: port channel name
        :param lag_status: port channel status
        :return: List with regular expression - [('PortChannel1111.*Up', True)]
        """
        return [(r'{PORTCHANNEL}.*{PORTCHANNEL_STATUS}'.format(PORTCHANNEL=lag_name,
                                                               PORTCHANNEL_STATUS=lag_status), True)]

    @staticmethod
    def get_port_channel_members_expected_info_regex(lag_name, lag_status, expected_members_status_list):
        """
        Returns regular expression format for validation of port channel with members
        :param lag_name: port channel name
        :param lag_status: port channel status
        :param expected_members_status_list: expected_members_status_list
        :return: List with regular expression - [('PortChannel1111.*Up.*Ethernet0\\(S\\)', True),
                                                 ('PortChannel1111.*Up.*Ethernet28\\(S\\)', True)]
        """
        lag_members_expected_info = []
        for member, status in expected_members_status_list:
            lag_members_expected_info.append((r'{PORTCHANNEL}.*{PORTCHANNEL_STATUS}.*{MEMBER}\({MEMBER_STATUS}\)'
                                              .format(PORTCHANNEL=lag_name,
                                                      PORTCHANNEL_STATUS=lag_status,
                                                      MEMBER=member,
                                                      MEMBER_STATUS=status), True))
        return lag_members_expected_info

    def create_lag_interface(self, lacp_interface_name, lacp_interface_params=''):
        """
        This method create a portchannel interface
        :param lacp_interface_name: LACP interface name which should be added
        :param lacp_interface_params: LACP interface parameters which can be added
                    params example: '--min-links 2 --fallback enable/disable'
        :return: command output
        """
        return self.engine.run_cmd("sudo config portchannel {} add {} {}".format(self.multi_asic_config_cmd_ext,
                                                                                 lacp_interface_name,
                                                                                 lacp_interface_params))

    def delete_lag_interface(self, lacp_interface_name):
        """
        Method which deleting LACP interface in SONiC
        :param lacp_interface_name: LACP interface name which should be deleted
        :return: command output
        """
        return self.engine.run_cmd("sudo config portchannel {} del {}".format(self.multi_asic_config_cmd_ext,
                                                                              lacp_interface_name))

    def add_port_to_port_channel(self, interface, lacp_interface_name):
        """
        This methods assign l2 interface to port-channel
        :param interface: interface name which should be added to LACP
        :param lacp_interface_name: LACP interface name to which we will add interface
        :return: command output
        """
        return self.engine.run_cmd("sudo config portchannel {} member add {} {}".format(self.multi_asic_config_cmd_ext,
                                                                                        lacp_interface_name,
                                                                                        interface))

    def delete_port_from_port_channel(self, interface, lacp_interface_name):
        """
        This methods deletes l2 interface from port-channel
        :param interface: interface name which should be deleted from LACP
        :param lacp_interface_name: LACP interface name from which we will remove interface
        :return: command output
        """
        return self.engine.run_cmd("sudo config portchannel {} member del {} {}".format(self.multi_asic_config_cmd_ext,
                                                                                        lacp_interface_name,
                                                                                        interface))

    def show_interfaces_port_channel(self):
        """
        This method performs show portchannel command
        :return: command output
        """
        return self.engine.run_cmd("show interfaces portchannel")
