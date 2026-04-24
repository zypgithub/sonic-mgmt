import logging
import allure
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from ngts.constants.constants import P4SamplingConsts
from ngts.constants.constants import P4SamplingEntryConsts
from ngts.helpers.p4nspect_utils import get_p4nspect_query_parsed
from datetime import datetime
import time

logger = logging.getLogger()
APP_NAME = P4SamplingConsts.APP_NAME
PORT_TABLE_NAME = P4SamplingConsts.PORT_TABLE_NAME
FLOW_TABLE_NAME = P4SamplingConsts.FLOW_TABLE_NAME
ACTION_NAME = P4SamplingConsts.ACTION_NAME
TRAFFIC_INTERVAL = P4SamplingConsts.TRAFFIC_INTERVAL


class P4SamplingUtils:
    @staticmethod
    def clear_statistics(cli_obj):
        """
        clear the statistic data
        :param cli_obj: cli_obj object
        :return: None
        """
        logger.info("Clear the Interface counters before send traffic")
        cli_obj.interface.clear_counters()
        logger.info("Clear the entry counters before send traffic")
        cli_obj.p4_sampling.clear_all_table_counters()

    @staticmethod
    def verify_traffic_hit(topology_obj, engines, interfaces, table_params, count, expect_count):
        """
        Send traffic which should hit one of the entries
        :param topology_obj: topology_obj fixture object
        :param engines: engines fixture object
        :param interfaces: interfaces fixture object
        :param table_params: table_params fixture object
        :param count: the count of packets to be sent
        :param expect_count: the count of packets expect to receive
        :return: None
        """
        # do validation for all the entries.
        indices = list(range(len(table_params.port_entry)))
        P4SamplingUtils.verify_port_table_send_recv_traffic(topology_obj, engines.dut, interfaces,
                                                            table_params.port_entry, indices, count,
                                                            expect_count, 'match')

        indices = list(range(len(table_params.flow_entry)))
        P4SamplingUtils.verify_flow_table_send_recv_traffic(topology_obj, engines.dut, interfaces,
                                                            table_params.flow_entry, indices, count,
                                                            expect_count, 'match')

    @staticmethod
    def verify_traffic_miss(topology_obj, engines, interfaces, table_params, count, expect_count):
        """
        Send traffic which will not hit the entry, and do verify for the send and receive packets
        :param topology_obj: topology_obj fixture object
        :param engines: engines fixture object
        :param interfaces: interfaces fixture object
        :param table_params: table_params fixture object
        :param count: the count of packets to be sent
        :param expect_count: the count of packets expect to receive
        :return: None
        """
        indices = list(range(len(table_params.port_entry)))
        P4SamplingUtils.verify_port_table_send_recv_traffic(topology_obj, engines.dut, interfaces,
                                                            table_params.port_entry, indices, count,
                                                            expect_count, 'mismatch')
        indices = list(range(len(table_params.flow_entry)))
        P4SamplingUtils.verify_flow_table_send_recv_traffic(topology_obj, engines.dut, interfaces,
                                                            table_params.flow_entry, indices, count,
                                                            expect_count, 'mismatch')

    @staticmethod
    def verify_port_table_send_recv_traffic(topology_obj, engine, interfaces, port_entries, indices, count,
                                            expect_count, chksum_type):
        """

        :param topology_obj: topology_obj fixture object
        :param engine: ssh engine object
        :param interfaces: interfaces fixture object
        :param port_entries: list of port table entry params
        :param indices: index list to indicate for which entries the traffic should sent for
        :param count: the count of packets to be sent
        :param expect_count: the count of packets expect to receive
        :param chksum_type: checksum type: match or mismatch
        :return:
        """
        logger.info("Send traffic for one of the port entry")

        port_entry_keys = []
        for index in indices:
            port_entry_keys.append(list(port_entries.keys())[index])
        port_traffic_params_list = \
            TrafficParams.prepare_port_table_send_receive_traffic_params(interfaces, topology_obj, port_entries,
                                                                         indices, chksum_type)
        P4SamplingUtils.send_recv_port_table_traffic(topology_obj, port_traffic_params_list, count, expect_count)
        P4SamplingUtils.verify_entry_counter(
            topology_obj.players['dut']['cli'],
            PORT_TABLE_NAME,
            port_entry_keys,
            expect_count)

    @staticmethod
    def verify_flow_table_send_recv_traffic(topology_obj, engine, interfaces, flow_entries, indices, count,
                                            expect_count,
                                            chksum_type):
        """

        :param topology_obj: topology_obj fixture object
        :param engine: ssh engine object
        :param interfaces: interfaces fixture object
        :param flow_entries: list of flow table entry params
        :param indices: index list to indicate for which entries the traffic should sent for
        :param count: the count of packets to be sent
        :param expect_count: the count of packets expect to receive
        :param chksum_type: checksum type: match or mismatch
        :return:
        """
        logger.info("Send traffic for one of the flow entry")
        flow_entry_keys, flow_traffic_params_list = \
            TrafficParams.prepare_flow_table_send_receive_traffic_params(interfaces, topology_obj, flow_entries,
                                                                         indices, chksum_type)
        P4SamplingUtils.send_recv_flow_table_traffic(
            topology_obj, flow_traffic_params_list, count, expect_count)
        P4SamplingUtils.verify_entry_counter(
            topology_obj.players['dut']['cli'],
            FLOW_TABLE_NAME,
            flow_entry_keys,
            expect_count)

    @staticmethod
    def verify_table_entry(engine, cli_obj, table_name, entries, expected_match=True):
        """
        Verify the entries which is added in the table with cli command and p4nspect tool
        :param engine: ssh engine object
        :param table_name: table name
        :param entries: entries params
        :param expected_match: value is True when want to verify the entries added, False to verify the entries removed
        :return: None
        """

        P4SamplingUtils.verify_cli_table_entry(cli_obj, table_name, entries, expected_match)
        # TODO: un-comment it after the ticket is resolved #2799656:
        # P4SamplingUtils.verify_p4nspect_table_entry(engine, table_name, entries, expected_match)
        engine.run_cmd("docker exec -i syncd bash -c 'sx_api_flex_acl_dump.py'")

    @staticmethod
    def verify_cli_table_entry(cli_obj, table_name, entries, expected_match=True):
        """
        Verify the entries which is added in the table with cli command
        :param cli_obj: cli_obj object
        :param table_name: table name
        :param entries: entries params
        :param expected_match: value is True when want to verify the entries added, False to verify the entries removed
        :return: None
        """
        with allure.step('Get entries with cli command'):
            start_time = datetime.now()
            entries_added_cli = cli_obj.p4_sampling.show_and_parse_table_entries(table_name, exclude_keys=["Rule"])
            end_time = datetime.now()
            time_used = (end_time - start_time).seconds
            logger.info('Show entries for port table takes {} seconds'.format(time_used))
            with allure.step('Verify added entries'):
                for entry_key in entries.keys():
                    entry_params = entries[entry_key]
                    entry = {'key': entry_key,
                             'action': " ".join([ACTION_NAME,
                                                 entry_params.action]),
                             'priority': '{}'.format(entry_params.priority)}
                    if expected_match:
                        assert entry in entries_added_cli
                    else:
                        assert entry not in entries_added_cli

    @staticmethod
    def verify_p4nspect_table_entry(engine, table_name, entries, expected_match=True):
        """
        Verify the entries which is added in the table with p4nspect tool
        :param engine: ssh engine object
        :param table_name: table name
        :param entries: entries params
        :param expected_match: value is True when want to verify the entries added, False to verify the entries removed
        :return: None
        """
        with allure.step('Get entries with p4nspect tool'):
            entries_added_p4nspect = get_p4nspect_query_parsed(engine, table_name.replace('-', '_'))
            with allure.step('Verify added entries'):
                for entry_key in entries.keys():
                    if expected_match:
                        assert entry_key in entries_added_p4nspect.keys()
                    else:
                        assert entry_key not in entries_added_p4nspect.keys()

    @staticmethod
    def send_recv_port_table_traffic(topology_obj, port_traffic_params_list, count, expect_mirror_count):
        """
        Send and verify traffic for the port table.
        :param topology_obj: topology_obj fixture object
        :param port_traffic_params_list: the traffic params which will be used when send traffic.
        :param count: the count of the packets to be sent
        :param expect_mirror_count: expected packet count to be received on the mirror port
        :return:
        """
        for port_traffic_params in port_traffic_params_list:
            chksum = port_traffic_params['chksum']
            port_entry_pkt = 'Ether()/IP(dst="{}", chksum={})'.format(port_traffic_params['dst_ip'],
                                                                      chksum)
            validation_r = {'sender': '{}'.format(port_traffic_params['sender']),
                            'send_args': {'interface': "{}".format(port_traffic_params['src_port']),
                                          'packets': port_entry_pkt, 'count': count},
                            'receivers':
                                [
                                    {'receiver': '{}'.format(port_traffic_params['receiver']),
                                     'receive_args': {'interface': "{}".format(port_traffic_params['mirror_port']),
                                                      'filter': port_traffic_params['filter'],
                                                      'count': expect_mirror_count, 'timeout': 60}}
            ]
            }
            scapy_r = ScapyChecker(topology_obj.players, validation_r)
            scapy_r.run_validation()

    @staticmethod
    def send_recv_flow_table_traffic(topology_obj, flow_traffic_params_list, count, expect_mirror_count):
        """
        Send and verify traffic for the flow table.
        :param topology_obj: topology_obj fixture object
        :param flow_traffic_params_list: the traffic params which will be used when send traffic.
        :param count: the count of the packets to be sent
        :param expect_mirror_count: expected packet count to be received on the mirror port
        :return: None
        """
        for flow_traffic_params in flow_traffic_params_list:
            flow_entry_keys = flow_traffic_params['flow_entry_key'].split()
            src_ip = flow_entry_keys[0]
            dst_ip = flow_entry_keys[1]
            proto = flow_entry_keys[2]
            src_port = flow_entry_keys[3]
            dst_port = flow_entry_keys[4]
            chksum = flow_traffic_params['chksum']
            flow_entry_pkt = 'Ether()/IP(src="{}",dst="{}", proto={}, chksum={})/TCP(sport={}, dport={})'.format(
                src_ip, dst_ip, proto, chksum, src_port, dst_port)
            validation = {'sender': '{}'.format(flow_traffic_params['sender']),
                          'send_args': {'interface': "{}".format(flow_traffic_params['src_port']),
                                        'packets': flow_entry_pkt, 'count': count},
                          'receivers':
                          [
                                    {'receiver': '{}'.format(flow_traffic_params['receiver']),
                                     'receive_args': {'interface': "{}".format(flow_traffic_params['mirror_port']),
                                                      'filter': flow_traffic_params['filter'],
                                                      'count': expect_mirror_count,
                                                      'timeout': 60}}
            ]
            }
            scapy_r = ScapyChecker(topology_obj.players, validation)
            scapy_r.run_validation()

    @staticmethod
    def send_port_table_traffic(topology_obj, port_traffic_params_list, count):
        """
        Send and verify traffic for the port table.
        :param topology_obj: topology_obj fixture object
        :param port_traffic_params_list: the traffic params which will be used when send traffic.
        :param count: the count of the packets to be sent
        :return:
        """
        for port_traffic_params in port_traffic_params_list:
            chksum = port_traffic_params['chksum']
            port_entry_pkt = 'Ether()/IP(dst="{}", chksum={})'.format(port_traffic_params['dst_ip'],
                                                                      chksum)
            validation_r = {'sender': '{}'.format(port_traffic_params['sender']),
                            'send_args': {'interface': "{}".format(port_traffic_params['src_port']),
                                          'packets': port_entry_pkt, 'count': count}
                            }
            scapy_r = ScapyChecker(topology_obj.players, validation_r)
            scapy_r.run_validation()

    @staticmethod
    def send_flow_table_traffic(topology_obj, flow_traffic_params_list, count):
        """
        Send and verify traffic for the flow table.
        :param topology_obj: topology_obj fixture object
        :param flow_traffic_params_list: the traffic params which will be used when send traffic.
        :param count: the count of the packets to be sent
        :return: None
        """
        for flow_traffic_params in flow_traffic_params_list:
            flow_entry_keys = flow_traffic_params['flow_entry_key'].split()
            src_ip = flow_entry_keys[0]
            dst_ip = flow_entry_keys[1]
            proto = flow_entry_keys[2]
            src_port = flow_entry_keys[3]
            dst_port = flow_entry_keys[4]
            chksum = flow_traffic_params['chksum']
            flow_entry_pkt = 'Ether()/IP(src="{}",dst="{}", proto={}, chksum={})/TCP(sport={}, dport={})'.format(
                src_ip, dst_ip, proto, chksum, src_port, dst_port)
            validation = {'sender': '{}'.format(flow_traffic_params['sender']),
                          'send_args': {'interface': "{}".format(flow_traffic_params['src_port']),
                                        'packets': flow_entry_pkt, 'count': count}
                          }
            scapy_r = ScapyChecker(topology_obj.players, validation)
            scapy_r.run_validation()

    @staticmethod
    def verify_entry_counter(cli_obj, table_name, entry_keys, expect_count):
        """
        Verify the counter of the entry
        :param cli_obj: cli_obj object
        :param table_name: table name, flow table name or port table name in p4-sampling
        :param entry_keys: the entry keys to indicate in which entry the counter will be verified
        :param expect_count: expect counter
        :return: None
        """

        time.sleep(P4SamplingConsts.COUNTER_REFRESH_INTERVAL)
        hit_counters = cli_obj.p4_sampling.show_and_parse_table_counters(table_name)
        for entry_key in entry_keys:
            if not hit_counters:
                packet_count = 0
            else:
                packet_count = hit_counters[entry_key]['packets']
            assert int(packet_count) >= expect_count

    @staticmethod
    def start_background_port_table_traffic(topology_obj, port_traffic_params_list):
        """
        Send continuous traffic for the port table
        :param topology_obj: topology_obj fixture object
        :param port_traffic_params_list: the traffic params for the port table
        :return: list of ScapyChecker object which can be used to stop the traffic later
        """
        scapy_senders = []
        for port_traffic_params in port_traffic_params_list:
            chksum = port_traffic_params['chksum']
            port_entry_pkt = 'Ether()/IP(dst="{}", chksum={})'.format(port_traffic_params['dst_ip'],
                                                                      chksum)
            validation_r = {'sender': '{}'.format(port_traffic_params['sender']),
                            'name': 'port_traffic_{}_{}'.format(port_traffic_params['src_port'], chksum),
                            'background': 'start',
                            'send_args': {'interface': "{}".format(port_traffic_params['src_port']),
                                          'packets': port_entry_pkt, 'loop': 1, 'inter': TRAFFIC_INTERVAL}}
            scapy_sender = ScapyChecker(topology_obj.players, validation_r)
            scapy_sender.run_validation()
            scapy_senders.append(scapy_sender)
        return scapy_senders

    @staticmethod
    def start_background_flow_table_traffic(topology_obj, flow_traffic_params_list):
        """
        Send continuous traffic for the flow table
        :param topology_obj: topology_obj fixture object
        :param flow_traffic_params_list: the traffic params for the flow table
        :return: list of ScapyChecker object which can be used to stop the traffic later
        """
        scapy_senders = []
        for flow_traffic_params in flow_traffic_params_list:
            flow_entry_keys = flow_traffic_params['flow_entry_key'].split()
            src_ip = flow_entry_keys[0]
            dst_ip = flow_entry_keys[1]
            proto = flow_entry_keys[2]
            src_port = flow_entry_keys[3]
            dst_port = flow_entry_keys[4]
            chksum = flow_traffic_params['chksum']
            flow_entry_pkt = 'Ether()/IP(src="{}",dst="{}", proto={}, chksum={})/TCP(sport={}, dport={})'.format(
                src_ip, dst_ip, proto, chksum, src_port, dst_port)
            validation_r = {'sender': '{}'.format(flow_traffic_params['sender']),
                            'name': 'flow_traffic_{}_{}_{}_{}_{}_{}'.format(src_ip, dst_ip, proto, src_port, dst_port,
                                                                            chksum),
                            'background': 'start',
                            'send_args': {'interface': "{}".format(flow_traffic_params['src_port']),
                                          'packets': flow_entry_pkt, 'loop': 1, 'inter': TRAFFIC_INTERVAL}
                            }
            scapy_sender = ScapyChecker(topology_obj.players, validation_r)
            scapy_sender.run_validation()
            scapy_senders.append(scapy_sender)
        return scapy_senders

    @staticmethod
    def stop_background_traffic(scapy_senders):
        """
        stop the continuous traffic
        :param scapy_senders: list of ScapyChecker object which can be used to stop the traffic
        :return: None
        """
        for scapy_sender in scapy_senders:
            scapy_sender.stop_processes()

    @staticmethod
    def verify_port_table_recv_traffic(topology_obj, port_traffic_params_list, operator, expect_count):
        """
        Verify the traffic received for the port entries
        :param topology_obj: topology_obj fixture object
        :param port_traffic_params_list: the traffic params for the port table which used to send traffic
        :param operator: operator
        :param expect_count: packets count expect to be received
        :return: None
        """
        for port_traffic_params in port_traffic_params_list:
            validation_r = {'receivers':
                            [
                                {'receiver': '{}'.format(port_traffic_params['receiver']),
                                 'receive_args': {'interface': "{}".format(port_traffic_params['mirror_port']),
                                                  'filter': port_traffic_params['filter'], 'operator': operator,
                                                  'count': expect_count, 'timeout': 60}}
                            ]
                            }
            scapy_r = ScapyChecker(topology_obj.players, validation_r)
            scapy_r.run_validation()

    @staticmethod
    def verify_flow_table_recv_traffic(topology_obj, flow_traffic_params_list, operator, expect_count):
        """
        Verify the traffic received for the flow entries
        :param topology_obj: topology_obj fixture object
        :param flow_traffic_params_list: the traffic params for the flow table which used to send traffic
        :param operator: operator
        :param expect_count: packets count expect to be received
        :return: None
        """
        for flow_traffic_params in flow_traffic_params_list:
            validation_r = {'receivers':
                            [
                                {'receiver': '{}'.format(flow_traffic_params['receiver']),
                                 'receive_args': {'interface': "{}".format(flow_traffic_params['mirror_port']),
                                                  'filter': flow_traffic_params['filter'], 'operator': operator,
                                                  'count': expect_count, 'timeout': 60}}
                            ]
                            }
            scapy_r = ScapyChecker(topology_obj.players, validation_r)
            scapy_r.run_validation()

    @staticmethod
    def get_memory_cpu_usage(engine):
        """
        :param engine: ssh engine object
        :return:
        """
        processes_summary = engine.run_cmd('show processes summary')
        contents = processes_summary.splitlines()[1:-1]
        total_mem = 0
        total_cpu = 0
        for line in contents:
            total_mem += float(line.split()[-2])
            total_cpu += float(line.split()[-1])

        return format(total_mem, '.1f'), format(total_cpu, '.1f')

    @staticmethod
    def convert_int_to_hex(i):
        """
        convert the integer to hex value
        :param i: integer value
        :return: string in hex format
        """
        return "{:#06x}".format(i)

    @staticmethod
    def check_p4_sampling_installed(cli_obj):
        if cli_obj.app_ext.verify_version_support_app_ext():
            app_installed = cli_obj.app_ext.parse_app_package_list_dict()
            if APP_NAME in app_installed:
                app_install_content = app_installed[APP_NAME]
                if app_install_content["Status"] == "Installed":
                    return True
        return False


class TrafficParams:
    @staticmethod
    def prepare_port_table_send_receive_traffic_params(interfaces, topology_obj, port_entries, indices, chksum_type):
        """
        prepare the traffic params to be used when send traffic
        :param topology_obj fixture object
        :param interfaces: interfaces fixture object
        :param port_entries: list of port_entry params
        :param indices: index list to indicate for which entries the traffic should sent for
        :param chksum_type: the checksum type: match/mismatch
        :return: list of traffic params for the port entries
        """
        port_entry_keys = []
        for index in indices:
            port_entry_keys.append(list(port_entries.keys())[index])
        port_traffic_params_list = []
        for port_entry_key in port_entry_keys:
            port_entry_chksum = TrafficParams.get_checkusm(port_entries[port_entry_key], chksum_type)
            ingress_port = port_entry_key.split()[0]
            dst_ip = TrafficParams.get_port_table_traffic_dst_ip(interfaces, ingress_port)
            src_port, sender = TrafficParams.get_port_table_traffic_sender_src_port(interfaces, topology_obj, port_entry_key)
            mirror_host_port, receiver = TrafficParams.get_port_table_traffic_mirror_receiver(interfaces, topology_obj,
                                                                                              port_entries[port_entry_key].action)
            filter_template = TrafficParams.get_pkt_filter(port_entries[port_entry_key].action)

            port_traffic_params_list.append(
                {
                    'sender': sender,
                    'receiver': receiver,
                    'src_port': src_port,
                    'mirror_port': mirror_host_port,
                    'dst_ip': dst_ip,
                    'chksum': port_entry_chksum,
                    'filter': filter_template},
            )
        return port_traffic_params_list

    @staticmethod
    def get_pkt_filter(entry_action_params):
        entry_action_param_list = entry_action_params.split()
        src_mac = entry_action_param_list[1]
        dst_mac = entry_action_param_list[2]
        src_ip = entry_action_param_list[3]
        dst_ip = entry_action_param_list[4]
        vlan = entry_action_param_list[5]
        return 'ether src {} and ether dst {} and vlan and src {} and dst {}'.format(src_mac, dst_mac, src_ip, dst_ip)

    @staticmethod
    def get_port_table_traffic_sender_src_port(interfaces, topology_obj, port_entry_key):
        """
        get the traffic sender and the port on the sender for port entry traffic
        :param topology_obj fixture object
        :param interfaces:interfaces fixture object
        :param port_entry_key:port entry key
        :return: port and sender name
        """
        ingress_port = port_entry_key.split()[0]
        src_port = TrafficParams.get_neighbor_host_interface(topology_obj, ingress_port)
        sender = TrafficParams.get_host(interfaces, src_port)
        return src_port, sender

    @staticmethod
    def get_port_table_traffic_mirror_receiver(interfaces, topology_obj, port_entry_action):
        """
        get the mirror traffic receive port and the receiver for port entry traffic
        :param topology_obj fixture object
        :param interfaces:interfaces fixture object
        :param port_entry_action: port entry action params
        :return: mirror traffic receive port and receiver
        """
        mirror_port = port_entry_action.split()[0]
        mirror_host_port = TrafficParams.get_neighbor_host_interface(topology_obj, mirror_port)
        receiver = TrafficParams.get_host(interfaces, mirror_host_port)
        return mirror_host_port, receiver

    @staticmethod
    def prepare_flow_table_send_receive_traffic_params(interfaces, topology_obj, flow_entries, indices, chksum_type):
        """
        prepare the traffic params to be used when send traffic
        :param topology_obj fixture object
        :param interfaces: interfaces fixture object
        :param flow_entries: list of flow entry params
        :param indices: index list to indicate for which entries the traffic should sent for
        :param chksum_type: the checksum type: match/mismatch
        :return list of flow entry keys and list of traffic params
        """
        flow_entry_keys = []
        for index in indices:
            flow_entry_keys.append(list(flow_entries.keys())[index])
        flow_traffic_params_list = []
        for flow_entry_key in flow_entry_keys:
            src_port, sender = TrafficParams.get_flow_table_traffic_sender_src_port(interfaces, flow_entry_key)
            mirror_host_port, receiver = TrafficParams.get_flow_table_traffic_mirror_receiver(interfaces,
                                                                                              topology_obj,
                                                                                              flow_entries[flow_entry_key].action)
            flow_entry_chksum = TrafficParams.get_checkusm(
                flow_entries[flow_entry_key], chksum_type)

            filter_template = TrafficParams.get_pkt_filter(flow_entries[flow_entry_key].action)

            flow_traffic_params_list.append(
                {
                    'flow_entry_key': flow_entry_key,
                    'sender': sender,
                    'receiver': receiver,
                    'src_port': src_port,
                    'mirror_port': mirror_host_port,
                    'chksum': flow_entry_chksum,
                    'filter': filter_template})
        return flow_entry_keys, flow_traffic_params_list

    @staticmethod
    def get_flow_table_traffic_sender_src_port(interfaces, flow_entry_key):
        """
        get the traffic sender and the port on the sender for flow entry traffic
        :param interfaces: interfaces fixture object
        :param flow_entry_key: flow entry key params
        :return: port and sender host
        """
        src_ip = flow_entry_key.split()[0]
        src_port = TrafficParams.get_port_with_ip(interfaces, src_ip)
        sender = TrafficParams.get_host(interfaces, src_port)
        return src_port, sender

    @staticmethod
    def get_flow_table_traffic_mirror_receiver(interfaces, topology_obj, flow_entry_action):
        """
        get the mirror traffic receive port and the receiver for flow entry traffic
        :param topology_obj: topology_obj fixture object
        :param interfaces: interfaces fixture object
        :param flow_entry_action: flow entry action params
        :return: mirror traffic receive port and receiver
        """
        mirror_port = flow_entry_action.split()[0]
        mirror_host_port = TrafficParams.get_neighbor_host_interface(topology_obj, mirror_port)
        receiver = TrafficParams.get_host(interfaces, mirror_host_port)
        return mirror_host_port, receiver

    @staticmethod
    def get_neighbor_host_interface(topology_obj, intf):
        """
        get the interface neighbor
        :param topology_obj: topology_obj fixture object
        :param intf: the interface name
        :return: the neighbor interface alias, example: Ethernet116, enp4s0f1
        """
        intf_alias = [k for k, v in topology_obj.ports.items() if v == intf][0]
        neighbor_intf_alias = topology_obj.ports_interconnects[intf_alias]
        return topology_obj.ports[neighbor_intf_alias]

    @staticmethod
    def get_checkusm(entry_key_value, chksum_type):
        """
        get the checksum value which will be used in the traffic
        :param entry_key_value: the params of the entry(except the key params)
        :param chksum_type: checksum value type. possible value: match, mismatch
        :return: checksum value in hex format
        """
        if chksum_type == 'match':
            return entry_key_value.match_chksum
        return entry_key_value.mismatch_chksum

    @staticmethod
    def get_host(interfaces, intf):
        """
        get the host of the interface
        :param interfaces: interfaces fixture object
        :param intf: the interface name
        :return: string, example: ha, hb
        """
        for k, v in interfaces.items():
            if v == intf:
                return k.split('_')[0]

    @staticmethod
    def get_port_to_ip_mapping(interfaces):
        return {
            interfaces.dut_ha_1: P4SamplingEntryConsts.dutha1_ip,
            interfaces.dut_ha_2: P4SamplingEntryConsts.dutha2_ip,
            interfaces.dut_hb_1: P4SamplingEntryConsts.duthb1_ip,
            interfaces.dut_hb_2: P4SamplingEntryConsts.duthb2_ip,
            interfaces.ha_dut_2: P4SamplingEntryConsts.hadut2_ip,
            interfaces.hb_dut_1: P4SamplingEntryConsts.hbdut1_ip
        }

    @staticmethod
    def get_port_table_traffic_dst_ip(interfaces, ingress_port):
        """
        get the dst ip address for traffic send for the port entry
        :param interfaces: interfaces fixture object
        :param ingress_port: ingress port of port entry
        :return: dst ip address
        """

        port_to_ip_mapping = TrafficParams.get_port_to_ip_mapping(interfaces)
        return port_to_ip_mapping[ingress_port]

    @staticmethod
    def get_port_with_ip(interfaces, ip):
        """
        get the dst ip address for traffic send for the port entry
        :param interfaces: interfaces fixture object
        :param ingress_port: ingress port of port entry
        :return: dst ip address
        """
        port_to_ip_mapping = TrafficParams.get_port_to_ip_mapping(interfaces)
        return list(port_to_ip_mapping.keys())[list(port_to_ip_mapping.values()).index(ip)]
