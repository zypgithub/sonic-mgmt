from ngts.cli_wrappers.common.bgp_clis_common import BgpCliCommon
from ngts.cli_wrappers.sonic.sonic_multi_asic_cli import SonicMultiAsicCli
from ngts.cli_util.cli_parsers import generic_sonic_output_parser
BGP_SUMMARY_CMD = {'ipv4': 'show ip bgp summary', 'ipv6': 'show ipv6 bgp summary'}


class SonicBgpCli(BgpCliCommon, SonicMultiAsicCli):
    """
    This class is for bgp cli commands for sonic only
    """

    def __init__(self, engine, asic_id=None):
        SonicMultiAsicCli.__init__(self, engine, asic_id)

    def startup_bgp_all(self):
        """
        Startup BGP on SONIC
        """
        cmd = 'sudo config bgp startup all'
        return self.engine.run_cmd(cmd)

    def startup_bgp_neighbor(self, neighbor):
        """
        Startup specific BGP neighbor on SONIC
        """
        cmd = f'sudo config bgp startup neighbor {neighbor}'
        return self.engine.run_cmd(cmd)

    def shutdown_bgp_all(self):
        """
        Shutdown BGP on SONIC
        """
        cmd = 'sudo config bgp shutdown all'
        return self.engine.run_cmd(cmd)

    def shutdown_bgp_neighbor(self, neighbor):
        """
        Shutdown specific BGP neighbor on SONIC
        """
        cmd = f'sudo config bgp shutdown neighbor {neighbor}'
        return self.engine.run_cmd(cmd)

    def restart_bgp_service(self):
        """
        Restart BGP service
        """
        cmd = f'sudo service bgp{self.multi_asic_service_cmd_ext} restart'
        return self.engine.run_cmd(cmd)

    def show_ip_bgp_summary(self, ip_version='ipv4'):
        """
        Run command: "show ip bgp summary"
        """
        cmd = f'sudo {BGP_SUMMARY_CMD.get(ip_version, "show ip bgp summary")} {self.multi_asic_config_cmd_ext}'
        return self.engine.run_cmd(cmd)

    def parse_ip_bgp_summary(self, show_bgp_summary_output=None, ip_version='ipv4'):
        """
        Parse output of command: "show ip bgp summary"
        :param show_bgp_summary_output: "show ip bgp summary" output
        :return: dictionary with parsed data, example:
        {'20.0.0.2': {'Neighbor': '20.0.0.2', 'V': '4', 'AS': '501', 'MsgRcvd': '145', 'MsgSent': '147', 'TblVer': '0',
        'InQ': '0', 'OutQ': '0', 'Up/Down': '00:07:02', 'State/PfxRcd': '2', 'NeighborName': 'HA'},
        '30.0.0.2': {'Neighbor': '30.0.0.2', 'V': '4', 'AS': '501', 'MsgRcvd': '145', 'MsgSent': '150', 'TblVer': '0',
        'InQ': '0', 'OutQ': '0', 'Up/Down': '00:07:02', 'State/PfxRcd': '2', 'NeighborName': 'HB'}}
        """
        if not show_bgp_summary_output:
            show_bgp_summary_output = self.show_ip_bgp_summary(ip_version=ip_version)
        output_key = "Neighbhor" if "Neighbhor" in show_bgp_summary_output else "Neighbor"
        bgp_summary_dict = generic_sonic_output_parser(show_bgp_summary_output,
                                                       headers_ofset=8,
                                                       len_ofset=9,
                                                       data_ofset_from_start=10,
                                                       data_ofset_from_end=-2,
                                                       column_ofset=2,
                                                       output_key=output_key)
        return bgp_summary_dict

    def show_ip_bgp_network(self, network=None):
        """
        Run command: "show ip bgp network"
        """
        cmd = 'sudo show ip bgp network'
        if network:
            cmd += f' {network}'
        return self.engine.run_cmd(cmd)

    def show_ip_bgp_neighbors(self, neighbor=None):
        """
        Run command: "show ip bgp neighbors"
        """
        cmd = 'sudo show ip bgp neighbors'
        if neighbor:
            cmd += f' {neighbor}'
        cmd += f' {self.multi_asic_config_cmd_ext}'
        return self.engine.run_cmd(cmd)

    @staticmethod
    def validate_bgp_session_state(ip_bgp_summary_data, session, expected_state):
        """
        Validate that BGP session in expected state
        :param ip_bgp_summary_data: dict with parsed output of "show ip bgp summary"
        :param session: BGP session name, example: "20.0.0.2"
        :param expected_state: expected BGP session status, example: "Established"
        :return: exception in case of fail, else None
        """
        if expected_state == 'Established':
            assert int(ip_bgp_summary_data[session]['State/PfxRcd']) >= 0, 'BGP session not in "Established" state'
        else:
            assert ip_bgp_summary_data[session]['State/PfxRcd'] == expected_state, \
                f'BGP session: {session} not in {expected_state} state'
