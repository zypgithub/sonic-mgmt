import allure
import pytest
from ngts.constants.constants import P4SamplingConsts
from ngts.helpers.p4_sampling_utils import P4SamplingUtils, TrafficParams
import ngts.helpers.p4_sampling_fixture_helper as fixture_helper
import random
from dotted_dict import DottedDict
from ngts.constants.constants import P4SamplingEntryConsts
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
import time


@pytest.fixture(scope='function', autouse=False)
def different_priority_entries(topology_obj, interfaces, engines, ha_dut_1_mac, cli_objects,
                               hb_dut_1_mac, dut_ha_1_mac, dut_hb_2_mac):
    """
    Fixture used to add entries and remove entries after test case finish
    :param topology_obj: topology_obj fixture object
    :param engines: engines fixture object
    :param interfaces: interfaces fixture object
    :param cli_objects: cli_objects fixture
    :param ha_dut_1_mac: ha_dut_1_mac fixture object
    :param hb_dut_1_mac: hb_dut_1_mac fixture object
    :param dut_ha_1_mac: dut_ha_1_mac fixture object
    :param dut_hb_2_mac: dut_hb_2_mac fixture object
    """
    table_param_data = generate_priority_entries(interfaces, cli_objects, ha_dut_1_mac, hb_dut_1_mac, dut_ha_1_mac,
                                                 dut_hb_2_mac, False)
    yield table_param_data
    fixture_helper.remove_p4_sampling_entries(topology_obj, interfaces, engines, table_param_data)


@pytest.fixture(scope='function', autouse=False)
def same_priority_entries(topology_obj, interfaces, engines, ha_dut_1_mac, cli_objects,
                          hb_dut_1_mac, dut_ha_1_mac, dut_hb_2_mac):
    """
    Fixture used to add entries and remove entries after test case finish
    :param topology_obj: topology_obj fixture object
    :param engines: engines fixture object
    :param cli_objects: cli_objects fixture
    :param interfaces: interfaces fixture object
    :param ha_dut_1_mac: ha_dut_1_mac fixture object
    :param hb_dut_1_mac: hb_dut_1_mac fixture object
    :param dut_ha_1_mac: dut_ha_1_mac fixture object
    :param dut_hb_2_mac: dut_hb_2_mac fixture object
    """
    table_param_data = generate_priority_entries(interfaces, cli_objects, ha_dut_1_mac, hb_dut_1_mac, dut_ha_1_mac,
                                                 dut_hb_2_mac, True)
    yield table_param_data
    fixture_helper.remove_p4_sampling_entries(topology_obj, interfaces, engines, table_param_data)


@allure.title('Test when different entries with different priority can match with same traffic, '
              'the entry with high priority will hit. ')
@pytest.mark.usefixtures('skipping_p4_sampling_test_case_for_spc1')
def test_entries_with_different_priority(engines, different_priority_entries, topology_obj, interfaces):
    """
    Test when different entries with different priority can match with same traffic, the entry with high priority will hit.
    :param engines: engines fixture object
    :param different_priority_entries: the entries which will be used in this test
    :param topology_obj: topology_obj fixture object
    :param interfaces: interfaces fixture object
    """
    port_entries = different_priority_entries.port_entry
    flow_entries = different_priority_entries.flow_entry
    cli_obj = topology_obj.players['dut']['cli']
    with allure.step('Check entries are added'):
        P4SamplingUtils.verify_table_entry(engines.dut, cli_obj, P4SamplingConsts.PORT_TABLE_NAME, port_entries)
        P4SamplingUtils.verify_table_entry(engines.dut, cli_obj, P4SamplingConsts.FLOW_TABLE_NAME, flow_entries)
    with allure.step('send traffic and check which entry should increase counter'):
        port_hit_indices = [len(port_entries) - 1]
        flow_hit_indices = [len(flow_entries) - 1]
        verify_send_recv_traffic(topology_obj, interfaces, engines.dut, port_entries, flow_entries, port_hit_indices,
                                 flow_hit_indices)


@allure.title('Test when different entries with same priority can match with same traffic, '
              'only one entry will hit, and the entry is randomly selected.')
@pytest.mark.usefixtures('skipping_p4_sampling_test_case_for_spc1')
def test_entries_with_same_priority(engines, same_priority_entries, topology_obj, interfaces):
    """
    Test when different entries with same priority can match with same traffic, only one entry will hit, and the entry
    is randomly selected.
    :param engines: engines fixture object
    :param same_priority_entries: the entries which will be used in this test
    :param topology_obj: topology_obj fixture object
    :param interfaces: interfaces fixture object
    """
    port_entries = same_priority_entries.port_entry
    flow_entries = same_priority_entries.flow_entry
    pkt_count = 3
    cli_obj = topology_obj.players['dut']['cli']
    with allure.step('Check entries are added'):
        P4SamplingUtils.verify_table_entry(engines.dut, cli_obj, P4SamplingConsts.PORT_TABLE_NAME, port_entries)
        P4SamplingUtils.verify_table_entry(engines.dut, cli_obj, P4SamplingConsts.FLOW_TABLE_NAME, flow_entries)
    with allure.step("Clear counters before send traffic"):
        P4SamplingUtils.clear_statistics(cli_obj)
    with allure.step("Send traffic for some of port and flow table"):
        verify_send_traffic(topology_obj, interfaces, port_entries, flow_entries, pkt_count)
    with allure.step("Check the counter of all entries and find the entry which can match"):
        port_hit_indices = get_hit_entry_list(cli_obj, P4SamplingConsts.PORT_TABLE_NAME, port_entries, pkt_count)
        flow_hit_indices = get_hit_entry_list(cli_obj, P4SamplingConsts.FLOW_TABLE_NAME, flow_entries, pkt_count)
    with allure.step("verify the traffic is mirrored for one entry and can not be mirrored for other entries"):
        verify_send_recv_traffic(topology_obj, interfaces, engines.dut, port_entries, flow_entries, port_hit_indices,
                                 flow_hit_indices)


def generate_priority_entries(interfaces, cli_objects, ha_dut_1_mac, hb_dut_1_mac, dut_ha_1_mac, dut_hb_2_mac,
                              same_prio):
    """
    Fixture used to add entries and remove entries after test case finish
    :param cli_objects: cli_objects fixture object
    :param interfaces: interfaces fixture object
    :param ha_dut_1_mac: ha_dut_1_mac fixture object
    :param hb_dut_1_mac: hb_dut_1_mac fixture object
    :param dut_ha_1_mac: dut_ha_1_mac fixture object
    :param dut_hb_2_mac: dut_hb_2_mac fixture object
    :param same_prio: to generate entries with same priority or not
    """
    table_param_data = DottedDict()
    flow_params = generate_flow_entries_params(1, interfaces, dut_ha_1_mac, ha_dut_1_mac, same_prio)
    port_params = generate_port_entries_params(1, interfaces, dut_hb_2_mac, hb_dut_1_mac, same_prio)
    table_param_data.port_entry = port_params
    table_param_data.flow_entry = flow_params
    fixture_helper.add_p4_sampling_entries(cli_objects.dut, table_param_data)
    return table_param_data


def verify_send_recv_traffic(topology_obj, interfaces, engine_dut, port_entries, flow_entries, port_hit_indices, flow_hit_indices):
    """
    send traffic and validate the traffic can be mirrored by the hit entry and can not be mirrored by the other entries
    :param topology_obj: topology_obj fixture object
    :param interfaces: interfaces fixture object
    :param engine_dut: dut ssh engine object
    :param port_entries: port table entries
    :param flow_entries: flow table entries
    :param port_hit_indices: index list of port table entries which will match traffic
    :param flow_hit_indices: index list of flow table entries which will match traffic
    """
    cli_obj = topology_obj.players['dut']['cli']
    with allure.step("Clear counters before send traffic"):
        P4SamplingUtils.clear_statistics(cli_obj)
    with allure.step("Send traffic for some of port table entry and do validation"):
        verify_port_table_send_recv_traffic(topology_obj, interfaces, engine_dut, port_entries, port_hit_indices)
    with allure.step("Send traffic for some of port table entry and do validation"):
        verify_flow_table_send_recv_traffic(topology_obj, interfaces, engine_dut, flow_entries, flow_hit_indices)


def verify_port_table_send_recv_traffic(topology_obj, interfaces, engine_dut, port_entries, port_hit_indices):
    """
    send traffic and validate the traffic can be mirrored by the hit entry and can not be mirrored by the other entries for the port table
    :param topology_obj: topology_obj fixture object
    :param interfaces: interfaces fixture object
    :param engine_dut: dut ssh engine object
    :param port_entries: port table entries
    :param port_hit_indices: index list of port table entries which will match traffic
    """
    pkt_count = 3
    chksum_type = 'match'
    port_indices = list(range(len(port_entries)))
    port_miss_indices = [port_entry_index for port_entry_index in port_indices if port_entry_index not in port_hit_indices]
    port_traffic_params_list = \
        TrafficParams.prepare_port_table_send_receive_traffic_params(interfaces, topology_obj, port_entries,
                                                                     port_indices, chksum_type)
    send_recv_port_table_traffic(topology_obj, port_traffic_params_list, pkt_count, pkt_count, port_hit_indices,
                                 port_miss_indices)
    port_entry_keys_match = []
    for index in port_hit_indices:
        port_entry_keys_match.append(list(port_entries.keys())[index])
    P4SamplingUtils.verify_entry_counter(
        topology_obj.players['dut']['cli'],
        P4SamplingConsts.PORT_TABLE_NAME,
        port_entry_keys_match,
        pkt_count)
    port_entry_keys_miss = []
    for index in port_miss_indices:
        port_entry_keys_miss.append(list(port_entries.keys())[index])
    P4SamplingUtils.verify_entry_counter(
        topology_obj.players['dut']['cli'],
        P4SamplingConsts.PORT_TABLE_NAME,
        port_entry_keys_miss,
        0)


def verify_flow_table_send_recv_traffic(topology_obj, interfaces, engine_dut, flow_entries, flow_hit_indices):
    """
    send traffic and validate the traffic can be mirrored by the hit entry and can not be mirrored by the other entries for the flow table
    :param topology_obj: topology_obj fixture object
    :param interfaces: interfaces fixture object
    :param engine_dut: dut ssh engine object
    :param flow_entries: port table entries
    :param flow_hit_indices: index list of port table entries which will match traffic
    """
    pkt_count = 3
    chksum_type = 'match'
    flow_indices = list(range(len(flow_entries)))
    flow_miss_indices = [i for i in flow_indices if i not in flow_hit_indices]
    _, flow_traffic_params_list = \
        TrafficParams.prepare_flow_table_send_receive_traffic_params(interfaces, topology_obj, flow_entries,
                                                                     flow_indices, chksum_type)
    send_recv_flow_table_traffic(topology_obj, flow_traffic_params_list, pkt_count, pkt_count, flow_hit_indices,
                                 flow_miss_indices)
    flow_entry_keys_match = []
    for index in flow_hit_indices:
        flow_entry_keys_match.append(list(flow_entries.keys())[index])
    P4SamplingUtils.verify_entry_counter(
        topology_obj.players['dut']['cli'],
        P4SamplingConsts.FLOW_TABLE_NAME,
        flow_entry_keys_match,
        pkt_count)
    flow_entry_keys_miss = []
    for index in flow_miss_indices:
        flow_entry_keys_miss.append(list(flow_entries.keys())[index])
    P4SamplingUtils.verify_entry_counter(
        topology_obj.players['dut']['cli'],
        P4SamplingConsts.FLOW_TABLE_NAME,
        flow_entry_keys_miss,
        0)


def send_recv_port_table_traffic(topology_obj, port_traffic_params_list, count, expect_mirror_count, hit_indices, miss_indices):
    """
    Send and verify traffic for the port table.
    :param topology_obj: topology_obj fixture object
    :param port_traffic_params_list: the traffic params which will be used when send traffic.
    :param count: the count of the packets to be sent
    :param expect_mirror_count: expected packet count to be received on the mirror port
    :param hit_indices: index list of entries which will match traffic
    :param miss_indices: index list of entries which will not match traffic
    """

    for i in hit_indices:
        port_traffic_params = port_traffic_params_list[i]
        chksum = port_traffic_params['chksum']
        port_entry_pkt = 'Ether()/IP(dst="{}", chksum={})'.format(port_traffic_params['dst_ip'],
                                                                  chksum)
        validation = {'sender': '{}'.format(port_traffic_params['sender']),
                      'send_args': {'interface': "{}".format(port_traffic_params['src_port']),
                                    'packets': port_entry_pkt, 'count': count},
                      'receivers':
                      [
                                {'receiver': '{}'.format(port_traffic_params['receiver']),
                                 'receive_args': {'interface': "{}".format(port_traffic_params['mirror_port']),
                                                  'filter': port_traffic_params['filter'], 'count': expect_mirror_count}}
        ]
        }
        for j in miss_indices:
            port_traffic_params = port_traffic_params_list[j]
            receiver = {'receiver': '{}'.format(port_traffic_params['receiver']),
                        'receive_args': {'interface': "{}".format(port_traffic_params['mirror_port']),
                                         'filter': port_traffic_params['filter'], 'count': 0}}
            validation['receivers'].append(receiver)
        scapy_r = ScapyChecker(topology_obj.players, validation)
        scapy_r.run_validation()


def send_recv_flow_table_traffic(topology_obj, flow_traffic_params_list, count, expect_mirror_count, hit_indices, miss_indices):
    """
    Send and verify traffic for the flow table.
    :param topology_obj: topology_obj fixture object
    :param flow_traffic_params_list: the traffic params which will be used when send traffic.
    :param count: the count of the packets to be sent
    :param expect_mirror_count: expected packet count to be received on the mirror port
    :param hit_indices: index list of entries which will match traffic
    :param miss_indices: index list of entries which will not match traffic
    """
    for i in hit_indices:
        flow_traffic_params = flow_traffic_params_list[i]
        flow_entry_pkt = get_flow_entry_pkt(flow_traffic_params)
        validation = {'sender': '{}'.format(flow_traffic_params['sender']),
                      'send_args': {'interface': "{}".format(flow_traffic_params['src_port']),
                                    'packets': flow_entry_pkt, 'count': count},
                      'receivers':
                      [
                                {'receiver': '{}'.format(flow_traffic_params['receiver']),
                                 'receive_args': {'interface': "{}".format(flow_traffic_params['mirror_port']),
                                                  'filter': flow_traffic_params['filter'], 'count': expect_mirror_count}}
        ]
        }
        for j in miss_indices:
            flow_traffic_params = flow_traffic_params_list[j]
            receiver = {'receiver': '{}'.format(flow_traffic_params['receiver']),
                        'receive_args': {'interface': "{}".format(flow_traffic_params['mirror_port']),
                                         'filter': flow_traffic_params['filter'], 'count': 0}}
            validation['receivers'].append(receiver)
        scapy_r = ScapyChecker(topology_obj.players, validation)
        scapy_r.run_validation()


def get_flow_entry_pkt(flow_traffic_params):
    """
    the pkt which will be used to sent to check which flow entry can be matched
    :param flow_traffic_params: flow_traffic_params
    :return: pkt to be used for scapy
    """
    flow_entry_keys = flow_traffic_params['flow_entry_key'].split()
    src_ip = flow_entry_keys[0]
    dst_ip = flow_entry_keys[1]
    proto = flow_entry_keys[2]
    src_port = flow_entry_keys[3]
    dst_port = flow_entry_keys[4]
    chksum = flow_traffic_params['chksum']
    flow_entry_pkt = 'Ether()/IP(src="{}",dst="{}", proto={}, chksum={})/TCP(sport={}, dport={})'.format(
        src_ip, dst_ip, proto, chksum, src_port, dst_port)
    return flow_entry_pkt


def verify_send_traffic(topology_obj, interfaces, port_entries, flow_entries, pkt_count):
    """
    send traffic and verify the send result
    :param topology_obj: topology_obj fixture object
    :param interfaces: interfaces fixture object
    :param port_entries: port entries which are used to get the parameters used to send traffic
    :param flow_entries: flow entries which are used to get the parameters used to send traffic
    :param pkt_count: pkt count to the sent
    :return: None
    """
    chksum_type = 'match'
    port_traffic_params_list_hit = TrafficParams.prepare_port_table_send_receive_traffic_params(interfaces,
                                                                                                topology_obj,
                                                                                                port_entries,
                                                                                                [0],
                                                                                                chksum_type)
    _, flow_traffic_params_list = TrafficParams.prepare_flow_table_send_receive_traffic_params(interfaces,
                                                                                               topology_obj,
                                                                                               flow_entries,
                                                                                               [0],
                                                                                               chksum_type)
    P4SamplingUtils.send_port_table_traffic(topology_obj, port_traffic_params_list_hit, pkt_count)
    P4SamplingUtils.send_flow_table_traffic(topology_obj, flow_traffic_params_list, pkt_count)


def get_hit_entry_list(cli_obj, table_name, entries, expect_count):
    """
    Check the counter of the entries, return the index list of the entries that will hit.
    This is used when the entries with same priority can match the traffic and need to find which entry should be hit.
    :param cli_obj: dut cli_obj object
    :param table_name: table name, flow table name or port table name in p4-sampling
    :param entries: the entries which are used to check the counters
    :param expect_count: expect count
    :return: list index of entries which have expected count
    """
    hit_indices = []
    entry_keys = list(entries.keys())
    entry_count = len(entry_keys)
    time.sleep(P4SamplingConsts.COUNTER_REFRESH_INTERVAL)
    hit_counters = cli_obj.p4_sampling.show_and_parse_table_counters(table_name)
    for i in range(entry_count):
        entry_key = entry_keys[i]
        if not hit_counters:
            break
        else:
            packet_count = int(hit_counters[entry_key]['packets'])
            if packet_count >= expect_count:
                hit_indices.append(i)
    assert len(hit_indices) != 0, "Expected to find one entry hit, but didn't find any traffic hit. " \
                                  "Either none of the entries was hit or the traffic was not sent"
    assert len(hit_indices) == 1, "Expected only one entry will hit."
    return hit_indices


def generate_port_entries_params(count, interfaces, dut_hb_2_mac, hb_dut_1_mac, same_priority):
    """
    generate params for port entries
    :param count: count of entries to be added or removed
    :param interfaces: interfaces fixture object
    :param dut_hb_2_mac: dut_hb_2_mac fixture object
    :param hb_dut_1_mac: hb_dut_1_mac fixture object
    :param same_priority: True if want to generate entries with same priority, else False
    :return: dictionary of port entries key, action, priority.
    """
    chksum_mask_list = ['0x00ff', '0xffff']
    ret = {}
    ingress_port = interfaces.dut_ha_2
    l3_mirror_vlan = random.randint(0, 1026)
    l3_mirror_is_truc = True
    l3_mirror_truc_size = 512

    match_chksum = P4SamplingUtils.convert_int_to_hex(4)
    priority = random.randint(1, 20)
    mirror_port_list = [interfaces.dut_hb_1, interfaces.dut_hb_2]
    for i in range(count):
        key = '{} {}/{}'.format(ingress_port, P4SamplingUtils.convert_int_to_hex(4), chksum_mask_list[i])
        action_params = '{} {} {} {} {} {} {} {}'.format(mirror_port_list[i], dut_hb_2_mac, hb_dut_1_mac,
                                                         P4SamplingEntryConsts.duthb1_ip,
                                                         P4SamplingEntryConsts.hbdut1_ip, l3_mirror_vlan,
                                                         l3_mirror_is_truc, l3_mirror_truc_size)
        entry_params = DottedDict()
        entry_params.action = action_params
        entry_params.priority = priority if same_priority else priority * (i + 1)
        entry_params.match_chksum = match_chksum
        entry_params.mismatch_chksum = 0x0000
        ret[key] = entry_params
    return ret


def generate_flow_entries_params(count, interfaces, dut_ha_1_mac, ha_dut_1_mac, same_priority):
    """
    generate the params for the flow entries
    :param count: the count of flow entry to generate
    :param interfaces: interfaces fixture object
    :param dut_ha_1_mac: dut_ha_1_mac fixture object
    :param ha_dut_1_mac: ha_dut_1_mac fixture object
    :param same_priority: True if want to generate entries with same priority, else False
    :return: Dictionary of params of flow entries,
    """
    ret = {}
    chksum_mask_list = ['0x00ff', '0xffff']
    l3_mirror_vlan = random.randint(0, 1026)
    l3_mirror_is_truc = True
    l3_mirror_truc_size = 512
    protocol = 6
    src_port = 20
    dst_port = 80
    match_chksum = P4SamplingUtils.convert_int_to_hex(8)
    priority = random.randint(1, 20)
    mirror_port_list = [interfaces.dut_ha_1, interfaces.dut_ha_2]
    for i in range(count):
        key = '{} {} {} {} {} {}/{}'.format(
            P4SamplingEntryConsts.hbdut1_ip,
            P4SamplingEntryConsts.hbdut2_ip,
            protocol,
            src_port,
            dst_port,
            P4SamplingUtils.convert_int_to_hex(8), chksum_mask_list[i])

        action_params = '{} {} {} {} {} {} {} {}'.format(mirror_port_list[i], dut_ha_1_mac, ha_dut_1_mac,
                                                         P4SamplingEntryConsts.dutha1_ip,
                                                         P4SamplingEntryConsts.hadut1_ip, l3_mirror_vlan,
                                                         l3_mirror_is_truc, l3_mirror_truc_size)
        entry_params = DottedDict()
        entry_params.action = action_params
        entry_params.priority = priority if same_priority else priority * (i + 1)
        entry_params.match_chksum = match_chksum
        entry_params.mismatch_chksum = '0x0000'
        ret[key] = entry_params
    return ret
