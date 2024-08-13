import logging
import os
import re
import time
import random

from retry.api import retry_call
from retry import retry
from functools import partial
from ngts.tests.nightly.adaptive_routing.constants import ArConsts
from ngts.constants.constants import AppExtensionInstallationConstants, PerfConsts
from ngts.tests.conftest import get_dut_loopbacks
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

logger = logging.getLogger()


class ArHelper:

    def enable_doai_service(self, cli_objects):
        """
        This method is to enable doAI service
        :param cli_objects: cli_objects fixture
        """
        logger.info('Enable doAI feature')
        cli_objects.dut.general.set_feature_state(AppExtensionInstallationConstants.DOAI, 'enabled')

    def disable_doai_service(self, cli_objects):
        """
        This method is to disable doAI service
        :param cli_objects: cli_objects fixture
        """
        logger.info('Disable doAI feature')
        cli_objects.dut.general.set_feature_state(AppExtensionInstallationConstants.DOAI, 'disabled')

    def enable_ar_function(self, cli_objects, restart_swss=False, validate=True):
        """
        This method is to enable AR function
        :param restart_swss: option to restart after enabling AR
        :param cli_objects: cli_objects fixture
        :param validate: adds an option to validate command
        """
        logger.info('Enable AR function')
        cli_objects.dut.ar.enable_ar_function(restart_swss=restart_swss, validate=validate)

    def disable_ar(self, cli_objects, validate=True):
        """
        This method is to disable AR function
        :param cli_objects: cli_objects fixture
        :param validate: adds an option to validate command
        """
        logger.info('Disable AR function')
        cli_objects.dut.ar.disable_ar_function(validate=validate)

    def enable_ar_port(self, cli_objects, port_list, restart_swss=False, validate=True):
        """
        This method is to enable AR function at DUT port
        :param cli_objects: cli_objects fixture
        :param port_list: list of DUT ports where AR must be enabled
        :param restart_swss: if True swss service and all dockers will be restarted
        :param validate: adds an option to validate command
        """
        logger.info(f'Enable AR on {port_list}')
        for port in port_list:
            cli_objects.dut.ar.enable_ar_port(port, restart_swss=restart_swss, validate=validate)

    def config_save_reload(self, cli_objects, topology_obj, reload_force=False):
        """
        This method is to save configuration and reload
        :param cli_objects: cli_objects fixture
        :param topology_obj: topology_obj fixture
        :param reload_force: adds -f option to command
        """
        cli_objects.dut.general.save_configuration()
        cli_objects.dut.general.reload_flow(topology_obj=topology_obj, reload_force=reload_force)

    def disable_ar_port(self, cli_objects, port_list):
        """
        This method is to disable AR function at DUT port
        :param cli_objects: cli_objects fixture
        :param port_list: list of DUT ports where AR must be disabled
        """
        logger.info(f'Disable AR on ports: {port_list}')
        for port in port_list:
            cli_objects.dut.ar.disable_ar_port(port)

    def add_dummy_vlan_intf(self, cli_objects):
        """
        This method is to add dummy vlan interface
        :param cli_objects: cli_objects fixture
        """
        logger.info(f'Add vlan interface with vlan {ArConsts.DUMMY_VLAN} ip {ArConsts.DUMMY_VLAN_IP}')
        cli_objects.dut.vlan.add_vlan(ArConsts.DUMMY_VLAN)
        cli_objects.dut.ip.add_ip_to_interface(ArConsts.DUMMY_VLAN_INTF, ArConsts.DUMMY_VLAN_IP)

    def del_dummy_vlan_intf(self, cli_objects):
        """
        This method is to remove dummy vlan interface
        :param cli_objects: cli_objects fixture
        """
        logger.info(f'Delete vlan interface with vlan {ArConsts.DUMMY_VLAN} ip {ArConsts.DUMMY_VLAN_IP}')
        cli_objects.dut.ip.del_ip_from_interface(ArConsts.DUMMY_VLAN_INTF, ArConsts.DUMMY_VLAN_IP)
        cli_objects.dut.vlan.del_vlan(ArConsts.DUMMY_VLAN)

    def add_lacp_intf(self, cli_objects, lb):
        """
        This method is to add LACP interface
        :param cli_objects: cli_objects fixture
        :param topology_obj: topology_obj fixture
        """
        logger.info(f'Add lag interface {ArConsts.DUMMY_LAG_INTF} with member port {lb[0][0]}')
        cli_objects.dut.lag.create_lag_interface(ArConsts.DUMMY_LAG_INTF)
        cli_objects.dut.lag.add_port_to_port_channel(lb[0][0], ArConsts.DUMMY_LAG_INTF)

    def del_lacp_intf(self, cli_objects, port):
        """
        This method is to delete LACP interface
        :param cli_objects: cli_objects fixture
        :param port: port to be deleted from LAG
        """
        logger.info(f'Remove port {port} from lag {ArConsts.DUMMY_LAG_INTF}')
        cli_objects.dut.lag.delete_port_from_port_channel(port, ArConsts.DUMMY_LAG_INTF)
        cli_objects.dut.lag.delete_lag_interface(ArConsts.DUMMY_LAG_INTF)

    def config_ecmp_ports_speed_to_10G(self, cli_objects, interfaces):
        """
        This method is to config ports speed to 10G in ecmp group
        :param cli_objects: cli_objects fixture
        :param interfaces: interfaces fixture
        """
        logger.info('Config port speed to 10G')
        speed = '10000'
        cli_objects.dut.interface.set_interface_speed(interfaces.dut_hb_1, speed)
        cli_objects.dut.interface.set_interface_speed(interfaces.dut_hb_2, speed)

    def restore_ecmp_ports_speed(self, cli_objects, original_intf_speeds):
        """
        This method is to config ports speed to original in ecmp group
        :param cli_objects: cli_objects fixture
        :param original_intf_speeds: original interface speed
        """
        logger.info('Restore port speed')
        cli_objects.dut.interface.set_interfaces_speed(original_intf_speeds)

    def add_dummy_interface_hb(self, cli_objects):
        """
        This method is to add dummy interface to hb
        :param cli_objects: cli_objects fixture
        """
        logger.info(f'Configure dummy interface: {ArConsts.DUMMY_INTF["name"]}')
        cli_objects.hb.interface.add_interface(ArConsts.DUMMY_INTF['name'], 'dummy')
        cli_objects.hb.ip.add_ip_to_interface(ArConsts.DUMMY_INTF['name'], ArConsts.DUMMY_INTF['ipv4_addr'],
                                              ArConsts.DUMMY_INTF['ipv4_mask'])
        cli_objects.hb.ip.add_ip_to_interface(ArConsts.DUMMY_INTF['name'], ArConsts.DUMMY_INTF['ipv6_addr'],
                                              ArConsts.DUMMY_INTF['ipv6_mask'])
        cli_objects.hb.interface.enable_interface(ArConsts.DUMMY_INTF['name'])

    def del_dummy_interface_hb(self, cli_objects, name):
        """
        This method is to delete dummy interface to hb
        :param cli_objects: cli_objects fixture
        :param name: interface name
        """
        cli_objects.hb.interface.del_interface(name)

    @retry(Exception, tries=10, delay=10)
    def verify_bgp_neighbor(self, cli_objects):
        """
        This method is to verify bgp neighbors
        :param cli_objects: cli_objects fixture
        """
        for neighbor in [
            ArConsts.V4_CONFIG['ha_dut_1'],
            ArConsts.V4_CONFIG['hb_dut_1'],
            ArConsts.V4_CONFIG['hb_dut_2'],
            ArConsts.V6_CONFIG['ha_dut_1'],
            ArConsts.V6_CONFIG['hb_dut_1'],
            ArConsts.V6_CONFIG['hb_dut_2'],
        ]:
            logger.info(f'Validate BGP neighbor {neighbor} established')
            cli_objects.dut.frr.validate_bgp_neighbor_established(neighbor)

    def assert_for_ecmp_routes(self, route, route_next_hops, intf):
        """
        This method is to get next hops for routes
        :param route: route for which ecmp group wll be check
        :param route_next_hops: route_next_hops for route
        :param intf: interface to check
        """
        assert intf in route_next_hops, f'ECMP Next hop for route {route} is incorrect or not available'

    def verify_ecmp_route(self, cli_objects, interfaces):
        """
        Check the ECMP route and its nexthop interface correctness
        :param cli_objects: cli_objects fixture
        :param interfaces: interfaces where ecmp routes will be verified
        Route example:
        B>* 10.0.0.0/24 [200/0] via 2.2.2.3, Ethernet64, weight 1, 01:24:40
          *                     via 3.3.3.3, Ethernet124, weight 1, 01:24:40

        B>* 5000::/64 [200/0] via fe80::e42:a1ff:feb4:ca48, Ethernet64, weight 1, 01:24:51
          *                   via fe80::e42:a1ff:feb4:ca49, Ethernet124, weight 1, 01:24:51
        """
        parsed_ipv4_route_output = cli_objects.dut.route.show_ip_route(is_json=True)
        parsed_ipv6_route_output = cli_objects.dut.route.show_ip_route(ipv6=True, is_json=True)
        ipv4_route_next_hops = cli_objects.dut.route.get_next_hops(parsed_ipv4_route_output[ArConsts.V4_CONFIG['ipv4_network']])
        ipv6_route_next_hops = cli_objects.dut.route.get_next_hops(parsed_ipv6_route_output[ArConsts.V6_CONFIG['ipv6_network']])

        route_nexthops_intf_list = [
            [ArConsts.DUMMY_INTF['ipv4_network'], ipv4_route_next_hops['intf'], interfaces.dut_hb_1],
            [ArConsts.DUMMY_INTF['ipv4_network'], ipv4_route_next_hops['intf'], interfaces.dut_hb_2],
            [ArConsts.DUMMY_INTF['ipv6_network'], ipv6_route_next_hops['intf'], interfaces.dut_hb_1],
            [ArConsts.DUMMY_INTF['ipv6_network'], ipv6_route_next_hops['intf'], interfaces.dut_hb_2],
        ]
        for route_nexthops_intf in route_nexthops_intf_list:
            route = route_nexthops_intf[0]
            nexthop_intfs = route_nexthops_intf[1]
            intf = route_nexthops_intf[2]
            self.assert_for_ecmp_routes(route, nexthop_intfs, intf)

    @retry(Exception, tries=10, delay=2)
    def get_tx_port_in_ecmp(self, cli_objects, port_list, packet_threshold):
        """
        This method is to get next hops for routes
        :param cli_objects: cli_objects fixture
        :param port_list: list of port to be candidates to receive traffic
        :param packet_threshold: packet_threshold
        :return: port to which RoCE traffic must be send
        """
        interface_counters_dict = self.get_interfaces_counters(cli_objects, port_list, "TX_OK")
        for port in port_list:
            if interface_counters_dict[port] >= packet_threshold:
                logger.info(f'Checking {port}, the TX counter is \
                {interface_counters_dict[port]}, need to be at least {packet_threshold}')
                return port

    def search_by_name(self, name, cmd_output, find_all=False):
        """
        This method is to search value by name in command output
        :param name: parameter name
        :param cmd_output: command output to search in
        :param find_all: find all matches by name if True
        :return: find value
        """
        pattern = f"({name}:?)\\s*(.+)"
        if find_all:
            return re.findall(pattern, cmd_output)
        return re.search(pattern, cmd_output).group(2)

    def get_ports_profile_configuration(self, cmd_output):
        """
        This method is to find all values for Ethernet ports
        :param cmd_output: command output to search in
        :return: tuple of port name, found value
        """
        return re.findall("Ethernet\\d+", cmd_output)

    def get_active_profile(self, show_ar_config_output):
        active_profile = None
        try:
            active_profile = self.search_by_name(ArConsts.AR_ACTIVE_PROFILE, show_ar_config_output)
        except AttributeError as err:
            # active profile is the default one
            active_profile = ArConsts.GOLDEN_PROFILE0
        finally:
            return active_profile

    def get_ar_configuration(self, cli_objects):
        """
        This method is to get AR configured at DUT
        :param cli_objects: cli_objects fixture
        :return: dictionary which describes output of "show ar config"
        Return example:
        {
        'Global':
            {'DoAI state': 'enabled', 'AR state': 'enabled', 'AR active profile': 'profile0'},
        'Ports':
            ['Ethernet0', 'Ethernet8']
        }
        """
        # Get show ar config output
        show_ar_config_output = cli_objects.dut.ar.show_ar_config()
        # Get Global values
        ar_result_dict = {}
        global_dict = {
            ArConsts.DOAI_STATE: self.search_by_name(ArConsts.DOAI_STATE, show_ar_config_output),
            ArConsts.AR_STATE: self.search_by_name(ArConsts.AR_STATE, show_ar_config_output),
            ArConsts.AR_ACTIVE_PROFILE: self.get_active_profile(show_ar_config_output),
            ArConsts.LINK_UTIL_STATE: self.search_by_name(ArConsts.LINK_UTIL_STATE, show_ar_config_output)
        }
        ar_result_dict[ArConsts.AR_GLOBAL] = global_dict
        port_util_value = self.get_ports_profile_configuration(show_ar_config_output)
        ar_result_dict[ArConsts.AR_PORTS_GLOBAL] = list(port_util_value)
        return ar_result_dict

    def send_and_validate_traffic(self, player, sender, sender_intf, sender_pkt_format, sender_count, sendpfast=False,
                                  mbps=None, loop=None, timeout=None):
        """
        This method is used to send then validate traffic
        :param player: player
        :param sender: sender, such as 'ha', 'hb'
        :param sender_intf: sender interface
        :param sender_pkt_format: packet to send
        :param sender_count: number of packets to send
        :param sendpfast: use sendpfast method to send traffic
        :param mbps: megabit per second traffic to be sent
        :param loop: number of times packet to be sent
        :param timeout: timeout to be set for sending traffic
        """
        traffic_validation = {'sender': sender,
                              'send_args': {'interface': sender_intf,
                                            'packets': sender_pkt_format,
                                            'count': sender_count
                                            }
                              }
        send_fast = {
            'send_method': 'sendpfast',
            'mbps': mbps,
            'loop': loop,
            'timeout': timeout
        }

        if sendpfast:
            traffic_validation['send_args'].update(send_fast)
        logger.info(f"Traffic parameters: {traffic_validation}")
        ScapyChecker(player, traffic_validation).run_validation()

    def get_received_port(self, interfaces, original_tx_port):
        """
        This method is used to get port to receive traffic
        :param interfaces: interfaces fixture
        :param original_tx_port: port from which traffic will be send
        :return: receiving ecmp port
        """
        ecmp_port_list = [interfaces.dut_hb_1, interfaces.dut_hb_2]
        assert original_tx_port in ecmp_port_list, \
            f'original tx port: {original_tx_port} should in ecmp port list: {ecmp_port_list}'
        ecmp_port_list.remove(original_tx_port)
        return ecmp_port_list.pop()

    @retry(Exception, tries=12, delay=5)
    def get_interfaces_counters(self, cli_objects, ports, stat, device='dut'):
        """
        This method is used to get interfaces counters
        :param cli_objects: cli_objects fixture
        :param ports: list of ports for which statistics must be taken
        :param stat: port stat TX_OK, RX_OK etc.
        :param device: the device which the method runs on
        :return: port statistic dictionary
        """
        port_stat_dict = {}
        counters_data = cli_objects[device].interface.parse_interfaces_counters()
        for port in ports:
            port_stat_dict[port] = port_stat_dict.get(port, 0)
            stat_value = counters_data[port][stat].replace(",", "").replace("%", "")
            stat_value = round(float(stat_value))
            port_stat_dict[port] = int(stat_value)
        return port_stat_dict

    def validate_roce_v2_pkts_traffic(self, players, interfaces, ha_dut_1_mac, dut_ha_1_mac, sender_count,
                                      sendpfast=False, mbps=None, loop=None, timeout=None):
        pkt_tc3_roce_v2_with_ar_flag = ArConsts.TC3_ROCEV2_AR_FLAG_PACKET.format(ha_dut_1_mac, dut_ha_1_mac,
                                                                                 ArConsts.V4_CONFIG['dut_ha_1'],
                                                                                 ArConsts.DUMMY_INTF['ipv4_addr'])
        logger.info("Send and validate traffic")
        self.send_and_validate_traffic(player=players, sender=ArConsts.HOST_A,
                                       sender_intf=interfaces.ha_dut_1,
                                       sender_pkt_format=pkt_tc3_roce_v2_with_ar_flag,
                                       sender_count=sender_count,
                                       sendpfast=sendpfast,
                                       mbps=mbps,
                                       loop=loop,
                                       timeout=timeout
                                       )

    def verify_enable_ar_before_doai_service_start(self, cli_objects):
        """
        This method is used to check if AR enabled before doAI service started
        :param cli_objects: cli_objects fixture
        """
        try:
            self.disable_ar(cli_objects, validate=False)
            self.disable_doai_service(cli_objects)
            warn_output = cli_objects.dut.ar.enable_ar_function(validate=False)
            assert ArConsts.WARNING_MESSAGE in warn_output, f'Adaptive Routing should print warning when enabling' \
                f'ar function before ' \
                f'{AppExtensionInstallationConstants.DOAI} service'
        except Exception as err:
            raise err
        finally:
            self.enable_doai_service(cli_objects)
            self.enable_ar_function(cli_objects)

    def verify_config_non_exist_profile(self, cli_objects):
        """
        This method is used to verify non existing profile can not be added to AR config
        :param cli_objects: cli_objects fixture
        """
        error_output = cli_objects.dut.ar.config_ar_profile(ArConsts.NON_EXIST_PROFILE, validate=False)
        assert ArConsts.NON_EXIST_PROFILE_ERROR_MESSAGE in error_output, \
            f'AR configured with a non exist profile: {ArConsts.NON_EXIST_PROFILE}'

    def verify_config_ar_at_non_exist_port(self, cli_objects):
        """
        This method is used to verify invalid port can not be added to AR config
        :param cli_objects: cli_objects fixture
        """
        error_output = cli_objects.dut.ar.enable_ar_port(ArConsts.NON_EXIST_PORT, validate=False)
        assert ArConsts.NON_EXIST_PORT_ERROR_MESSAGE in error_output, \
            f'AR configured with a non exist port: {ArConsts.NON_EXIST_PORT}'

    def verify_config_ar_on_vlan_intf(self, cli_objects):
        """
        This method is used to verify invalid vlan interface can not be added to AR config
        :param cli_objects: cli_objects fixture
        """
        error_output = cli_objects.dut.ar.enable_ar_port(ArConsts.DUMMY_VLAN_INTF, validate=False)
        assert ArConsts.AR_ON_VLAN_INTF_ERROR_MESSAGE in error_output, \
            f'AR configured with on vlan interface: {ArConsts.DUMMY_VLAN_INTF}'

    def verify_config_ar_on_lag_intf_and_lag_member(self, cli_objects, topology_obj):
        """
        This method is used to verify invalid LAG interface/ LAG member can not be added to AR config
        :param cli_objects: cli_objects fixture
        :param topology_obj: topology_obj fixture
        """
        lb = get_dut_loopbacks(topology_obj)
        error_output = cli_objects.dut.ar.enable_ar_port(ArConsts.DUMMY_LAG_INTF, validate=False)
        assert ArConsts.AR_ON_LAG_INTF_ERROR_MESSAGE in error_output, \
            f'AR configured with on lag interface: {ArConsts.DUMMY_LAG_INTF}'
        error_output = cli_objects.dut.ar.enable_ar_port(lb[0][0], validate=False)
        assert ArConsts.AR_ON_LAG_MEMBER_ERROR_MESSAGE in error_output, f'AR configured with on lag member: {lb[0][0]}'

    def verify_config_ar_on_mgmt_port(self, cli_objects):
        """
        This method is used to verify management port can not be added to AR config
        :param cli_objects: cli_objects fixture
        """
        error_output = cli_objects.dut.ar.enable_ar_port(ArConsts.MGMT_PORT, validate=False)
        assert ArConsts.AR_ON_MGMT_PORT_ERROR_MESSAGE in error_output, \
            f'AR configured with on mgmt interface: {ArConsts.MGMT_PORT}'

    def verify_config_ar_invalid_global_link_utilization(self, cli_objects):
        """
        This method is used to verify invalid value if global link utilization can not be set to AR profile
        :param cli_objects: cli_objects fixture
        """
        error_output = cli_objects.dut.ar.enable_ar_link_utilization(ArConsts.INVALID_LINK_UTIL_PERCENT_VALUE, validate=False)
        assert ArConsts.INVALID_LINK_UTIL_PERCENT_MESSAGE in error_output, \
            f'AR configured with invalid global link utilization: {ArConsts.INVALID_LINK_UTIL_PERCENT_VALUE}'

    def copy_packet_aging_file_to_dut(self, engines):
        """
        This method is used to copy aging file to DUT
        :param engines: engines fixture
        """
        logger.info('Get sonic-mgmt path')
        base_dir = os.path.dirname(os.path.realpath(__file__))
        sonic_mgmt_base_dir = ArConsts.DIR_DELIMITER.join(base_dir.split(ArConsts.DIR_DELIMITER)[:-3])
        logger.info('Get path of packet aging file')
        packet_aging_script_abs_path = os.path.join(sonic_mgmt_base_dir, ArConsts.PACKET_AGING_SCRIPT_PATH)
        logger.info('Copy packet aging file to dut')
        engines.dut.copy_file(source_file=packet_aging_script_abs_path,
                              file_system='/tmp',
                              dest_file=packet_aging_script_abs_path.split(ArConsts.DIR_DELIMITER)[-1],
                              overwrite_file=True)

    def disable_packet_aging(self, engines):
        """
        This method is used to disable packet aging in syncd
        :param engines: engines fixture
        """
        self.copy_packet_aging_file_to_dut(engines)
        logger.info('Copy packet aging file to syncd docker')
        engines.dut.run_cmd('docker cp /tmp/packets_aging.py syncd:/')
        logger.info('Disable packet aging')
        engines.dut.run_cmd('docker exec syncd python /packets_aging.py disable')

    def enable_packet_aging(self, engines):
        """
        This method is used to disable packet aging in syncd
        :param engines: engines fixture
        """
        logger.info('Enable packet aging')
        engines.dut.run_cmd('docker exec syncd python /packets_aging.py enable')
        engines.dut.run_cmd('docker exec syncd rm -rf /packets_aging.py')

    def copy_and_load_profile_config(self, engines, cli_objects, config_folder, custom_profile_json):
        """
        This method is used to copy  profile config file from sonic-mgmt to DUT and perform load
        :param engines: engines fixture
        :param cli_objects: cli_objects fixture
        :param config_folder: folder where config stored
        :param custom_profile_json: name of the custom profile
        """
        engines.dut.copy_file(source_file=os.path.join(config_folder, custom_profile_json),
                              dest_file=custom_profile_json,
                              file_system='/tmp/',
                              overwrite_file=True,
                              verify_file=False)

        cli_objects.dut.general.load_configuration('/tmp/' + custom_profile_json)

    def enable_ar_profile(self, cli_objects, profile_name, restart_swss=False):
        """
        This method is used to enable ar profile
        :param cli_objects: engines fixture
        :param profile_name: profile to be enabled
        :param restart_swss: restart_swss flag
        """
        self.ensure_ar_active(cli_objects)
        cli_objects.dut.ar.config_ar_profile(profile_name, restart_swss=restart_swss)

    def get_all_ports(self, topology_obj):
        """
        This method is used to get all ports of DUT
        :param topology_obj: topology_obj fixture
        :return: list op DUT ports
        """
        return topology_obj.players_all_ports["dut"]

    def run_traffic(self, cli_objects, players):
        cli_objects.dut.watermark.clear_watermarkstat()
        logger.info('Sending iPerf traffic')
        IperfChecker(players, ArConsts.IPERF_VALIDATION).run_validation()

    def enable_global_link_utilization(self, cli_objects, threshold=None, restart_swss=False, validate=True):
        logger.info('enabling global link utilization')
        if threshold:
            logger.info(f"Link utilization is set to {threshold}%")
        cli_objects.dut.ar.enable_ar_link_utilization(threshold=threshold, restart_swss=restart_swss, validate=validate)

    def disable_link_utilization(self, cli_objects, restart_swss=False):
        logger.info('disabling global link utilization')
        cli_objects.dut.ar.disable_ar_link_utilization(restart_swss=restart_swss)

    def add_routes_to_host(self, cli_objects):
        cli_objects.ha.route.add_route(ArConsts.ROUTE_CONFIG['ha'], ArConsts.V4_CONFIG['dut_ha_1'], 24)
        cli_objects.hb.route.add_route(ArConsts.ROUTE_CONFIG['hb'], ArConsts.ROUTE_CONFIG['hb_gw'], 24)

    def del_routes_from_host(self, cli_objects):
        cli_objects.ha.route.del_route(ArConsts.ROUTE_CONFIG['ha'], ArConsts.V4_CONFIG['dut_ha_1'], 24)
        cli_objects.hb.route.del_route(ArConsts.ROUTE_CONFIG['hb'], ArConsts.ROUTE_CONFIG['hb_gw'], 24)

    def ensure_ar_active(self, cli_objects):
        doai_state = self.get_ar_configuration(cli_objects)[ArConsts.AR_GLOBAL][ArConsts.DOAI_STATE]
        ar_state = self.get_ar_configuration(cli_objects)[ArConsts.AR_GLOBAL][ArConsts.AR_STATE]
        if doai_state or ar_state != "enabled":
            self.enable_doai_service(cli_objects)
            self.enable_ar_function(cli_objects, restart_swss=True)

    def validate_all_traffic_sent(self, cli_objects, tx_ports, counters_before, packets_num):
        counters_after = self.get_interfaces_counters(cli_objects, tx_ports, 'TX_OK')
        count_before = 0
        count_after = 0
        for port in tx_ports:
            count_before += counters_before[port]
            count_after += counters_after[port]
        sent_traffic = count_after - count_before
        if sent_traffic < packets_num:
            raise AssertionError(f'Not all packets were sent, expected {packets_num} but sent only {sent_traffic}')
        return counters_after

    def validate_traffic_distribution(self, tx_ports, counters_after, counters_before, allowed_dev=0.1):
        allowed_loss_per_port = (allowed_dev * ArConsts.PACKET_NUM_MID) // len(tx_ports)
        for tx_port in tx_ports:
            sent_traffic = counters_after[tx_port] - counters_before[tx_port]
            expected_sent = (ArConsts.PACKET_NUM_MID // len(tx_ports)) - allowed_loss_per_port
            assert expected_sent <= sent_traffic, \
                (f"Traffic has not been split between ECMP group: {tx_port} Sent {sent_traffic} packets,"
                 f" when expected sending {expected_sent}")

    def uninstall_doai_flow(self, cli_objects, topology_obj):
        self.disable_ar(cli_objects)
        self.disable_doai_service(cli_objects)
        cli_objects.dut.app_ext.uninstall_app(ArConsts.DOAI_CONTAINER_NAME, is_force=False)
        self.config_save_reload(cli_objects, topology_obj, reload_force=True)

    def install_doai_flow(self, cli_objects, topology_obj, tx_ports, doai_version):
        cli_objects.dut.app_ext.install_app(ArConsts.DOAI_CONTAINER_NAME, version=doai_version)
        self.ensure_ar_active(cli_objects)
        self.enable_ar_port(cli_objects, tx_ports)
        self.config_save_reload(cli_objects, topology_obj, reload_force=True)
        self.verify_bgp_neighbor(cli_objects)


class ArPerfHelper(ArHelper):

    def __init__(self, topology_obj, engines):
        self.engines = engines
        self.topology_obj = topology_obj
        self.tg_engines = self.get_tg_engines(engines)
        self.all_engines_ports = self.get_ports_by_type(topology_obj, engines)

    def generate_traffic_from_node(self, engines, dest_mac, num_of_ports, packet_size=4000):
        num_of_packets = PerfConsts.PACKET_SIZE_TO_PACKET_NUM_DICT[packet_size]
        self.verify_traffic_generation_enabled(engines)
        logger.info(f'Generate traffic from left and right node with packet size {packet_size}')
        for engine in self.tg_engines:
            engines[engine].run_cmd(f'sudo python3 {PerfConsts.TRAFFIC_SENDER_SCRIPT_TG} -s {packet_size} '
                                    f'-n {num_of_packets} -m {dest_mac} -g {engine} -p {num_of_ports}', validate=True)

    def get_tg_engines(self, engines):
        tg_engines = [engine for engine in engines if re.search("tg$", engine)]
        logger.info(f'traffic generator engines are {tg_engines}')
        return tg_engines

    def run_cmd_on_syncd(self, engine, script_name, python=False, additional_args=""):
        prefix = "/"
        additional_args_str = " ".join(str(arg) for arg in additional_args)
        if python:
            prefix = "python3 "
        logger.info("Running command on syncd docker:")
        engine.run_cmd("sudo docker exec -i syncd bash -c '{}{} {}'".format(prefix, script_name, additional_args_str),
                       validate=True)

    def copy_traffic_cmds_to_node(self, engine, engine_name):
        dest_file_name = "_".join([PerfConsts.TRAFFIC_SENDER_SCRIPT_TG])
        logger.info("Copying traffic commands to syncd docker")
        engine.copy_file(source_file=os.path.join(PerfConsts.CONFIG_FILES_DIR,
                                                  PerfConsts.TRAFFIC_SENDER_SCRIPT_TG),
                         dest_file=dest_file_name,
                         file_system='/home/admin',
                         direction='put'
                         )

    def copy_ip_neighbor_cmds_to_dut(self, engine):
        logger.info("Copying ip neighbors commands to DUT")
        engine.copy_file(source_file=os.path.join(PerfConsts.CONFIG_FILES_DIR,
                                                  PerfConsts.IP_NEIGH_SCRIPT),
                         dest_file=PerfConsts.IP_NEIGH_SCRIPT,
                         file_system='/home/admin',
                         direction='put'
                         )
        engine.run_cmd(f'chmod +x {PerfConsts.IP_NEIGH_SCRIPT}')

    def config_ip_neighbors_on_dut(self, engines, topology_obj):
        mac_dict = {}
        iterations_num = len(self.all_engines_ports['dut'])
        dut_engine = engines.dut
        for engine in self.tg_engines:
            mac_dict[engine] = self.get_switch_mac(topology_obj, engine)
        logger.info("Config permanent ip neighbors on DUT")
        self.copy_ip_neighbor_cmds_to_dut(dut_engine)
        ip_neigh_cmd = " ".join([PerfConsts.IP_NEIGH_SCRIPT, mac_dict["left_tg"], mac_dict["right_tg"],
                                 PerfConsts.L_IP_NEIGH, PerfConsts.R_IP_NEIGH, str(iterations_num)])
        ip_neigh_cmd = "sudo ./" + ip_neigh_cmd
        dut_engine.run_cmd(ip_neigh_cmd, validate=True)

    def validate_tx_utilization(self, cli_objects, ports_list, device, ibm=False, packet_size=4000,
                                stress_mode=False, negative_mode=False):
        util_threshold = self.get_util_threshold(device, ibm, packet_size)
        logger.info(f'Utilization threshold is {util_threshold}%')
        sample_time = PerfConsts.DEFAULT_SAMPLE_TIME_IN_SEC
        total_sample_time = sample_time + PerfConsts.SLEEP_TIME_BEFORE_SAMPLE
        if stress_mode:
            sample_time = PerfConsts.EXTENDED_SAMPLE_TIME_IN_SEC
            logger.info(f'Stress mode - sampling time of port utilization is {sample_time} seconds')
        util_counters_dict = {}
        logger.info('Check interface counters responding before sampling')
        self.get_interfaces_counters(cli_objects, ports_list, 'TX_UTIL', device=device)
        start_time = time.time()
        while time.time() - start_time < total_sample_time:
            sample_dict = self.get_interfaces_counters(cli_objects, ports_list, 'TX_UTIL', device=device)
            for port, value in sample_dict.items():
                if port not in util_counters_dict:
                    util_counters_dict[port] = []
                util_counters_dict[port].append((value, time.time()))
        with allure.step(f'Check the average port utilization on {device}'):
            for port, util_values in util_counters_dict.items():
                counted_util_values = [value_timestamp_pair for value_timestamp_pair in util_values
                                       if value_timestamp_pair[PerfConsts.TIMESTAMP_INDEX] >=
                                       start_time + PerfConsts.SLEEP_TIME_BEFORE_SAMPLE]
                sum_of_util = sum(value_timestamp_pair[PerfConsts.VALUE_INDEX] for value_timestamp_pair in counted_util_values)
                avg_port_util = round(sum_of_util / len(counted_util_values))
                if not negative_mode:
                    logger.debug(f'Verify that the port utilization of {device} is above {util_threshold}% ')
                    if avg_port_util < util_threshold:
                        raise AssertionError(f'Port utilization of {port} is on average {avg_port_util}% '
                                             f'when at least {util_threshold}% is expected')
                    logger.debug('Port utilization is above threshold as expected')

                else:
                    logger.debug(f'Verify that the port utilization of {device} is 0% ')
                    if avg_port_util != 0:
                        raise AssertionError(f'Port utilization is {avg_port_util}%'
                                             f' but is expected to be 0% after {port} has been shut down')
                    logger.debug('Port utilization is 0% as expected')

    def get_util_threshold(self, device, ibm, packet_size):
        if device == 'dut':
            if ibm:
                util_threshold = PerfConsts.DUT_TX_UTIL_W_IBM_TH_DICT[packet_size]
            else:
                util_threshold = PerfConsts.DUT_TX_UTIL_TH_DICT[packet_size]
        else:
            util_threshold = PerfConsts.TG_TX_UTIL_TH
        return util_threshold

    def stop_traffic_generation(self, engines):

        for engine in self.tg_engines:
            logger.info(f'Stop traffic generation on {engine}')
            engines[engine].run_cmd("redis-cli -n 4 hset 'SCHEDULER|scheduler.traffic' pir 1")

    def verify_traffic_generation_enabled(self, engines):
        for engine in self.tg_engines:
            logger.info(f'Enable traffic generation on {engine}')
            engines[engine].run_cmd("redis-cli -n 4 hset 'SCHEDULER|scheduler.traffic' pir 0")

    def get_ports_by_type(self, topology_obj, engines):
        ports_dict = {}
        all_engines = [engine for engine in engines if re.search("tg$", engine) or re.search("dut$", engine)]
        dut_switch_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        for engine in all_engines:
            ports_dict[engine] = {}
            cli_object = topology_obj.players[engine]['cli']
            lldp_table_output = cli_object.lldp.parse_lldp_table_info()
            if engine in self.tg_engines:
                tg_switch_name = topology_obj.players[engine]['attributes'].noga_query_data['attributes']['Common']['Name']
                mloop_ports_list = []
                egress_ports_list = []
                logger.debug(f'Define the type of port - MLOOP or egress,'
                             f' by checking if it is connected to the DUT or to itself')
                for port, port_info in lldp_table_output.items():
                    if port_info[0] == tg_switch_name:
                        mloop_ports_list.append(port)
                    elif port_info[0] == dut_switch_name:
                        egress_ports_list.append(port)
                ports_dict[engine]['mloop_ports'] = mloop_ports_list
                ports_dict[engine]['egress_ports'] = egress_ports_list
            else:
                dut_ports_list = []
                for port, port_info in lldp_table_output.items():
                    dut_ports_list.append(port)
                ports_dict[engine] = dut_ports_list

        return ports_dict

    def ensure_ar_perf_config_set(self, cli_objects, topology_obj, engines):
        logger.info('Check if AR is enabled, and enable AR if is not')
        self.ensure_ar_active(cli_objects)
        logger.info('Verify that all ports are configured with AR enabled')
        actual_ar_ports = sorted(self.get_ar_configuration(cli_objects)[ArConsts.AR_PORTS_GLOBAL])
        expected_ar_ports = sorted(self.all_engines_ports['dut'])
        if actual_ar_ports != expected_ar_ports:
            non_ar_ports = list(set(expected_ar_ports) - set(actual_ar_ports))
            logger.info(f'Not all ports are configured with AR enabled, enabling AR on {non_ar_ports}')
            self.enable_ar_port(cli_objects, non_ar_ports, restart_swss=True)

    def link_flap_flow(self, cli_objects, port_list, flap_count=1):
        for i in range(flap_count):
            logger.info(f'Shutdown ports {port_list} and check they are down')
            cli_objects.dut.interface.disable_interfaces(port_list)
            cli_objects.dut.interface.check_link_state(port_list, expected_status='down')
            retry_call(self.validate_tx_utilization,
                       fargs=[cli_objects, port_list, "dut"],
                       fkwargs={"ibm": False, "packet_size": 4000,
                                "stress_mode": False, "negative_mode": True},
                       tries=10,
                       delay=5,
                       logger=logger)
            logger.info(f'Startup ports {port_list} and check they are up')
            cli_objects.dut.interface.enable_interfaces(port_list)
            cli_objects.dut.interface.check_link_state(port_list)

    def get_switch_mac(self, topology_obj, engine_name):
        """
        Pytest fixture which are returning mac address for the selected switch
        """
        cli_object = topology_obj.players[engine_name]['cli']
        return cli_object.mac.get_mac_address_for_interface("Ethernet0")

    def choose_reboot_type(self, supported_types_list):
        reboot_type = random.choice(supported_types_list)
        return reboot_type
