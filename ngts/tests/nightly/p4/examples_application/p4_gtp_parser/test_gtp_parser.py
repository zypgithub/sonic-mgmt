import pytest
import logging
import allure
from .conftest import update_gtp_entries, ORI_PARAMS, UPDATE_PARAMS
from ngts.constants.constants import P4ExamplesConsts
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
import ngts.helpers.p4nspect_utils as p4nspect_utils
from scapy.contrib.gtp import GTPHeader

logger = logging.getLogger()

GTP_U_PORT = 2152
UDP_PROTOCOL = 17


@pytest.mark.p4_examples
@allure.title('Test GTP entries can be added, updated correctly.')
def test_gtp_parser_basic(engines, gtp_table_params, cli_objects):
    with allure.step("Verify the entries added correctly"):
        verify_gtp_entries(gtp_table_params, cli_objects.dut)
        p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                      feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                      table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
    with allure.step("Update the entries"):
        update_gtp_entries(gtp_table_params, cli_objects.dut)
    with allure.step("Verify the entries updated correctly"):
        verify_gtp_entries(gtp_table_params, cli_objects.dut, UPDATE_PARAMS)
        p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                      feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                      table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
    with allure.step("Update the entries back"):
        update_gtp_entries(gtp_table_params, cli_objects.dut, ORI_PARAMS)
    with allure.step("Verify the entries updated correctly"):
        verify_gtp_entries(gtp_table_params, cli_objects.dut)
        p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                      feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                      table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)


@pytest.mark.p4_examples
@allure.title('Test gtp entries can hit as expect.')
def test_gtp_parser_entry_hit(topology_obj, engines, gtp_table_params, cli_objects):
    pkt_count = 3

    with allure.step("Send traffic that match one entry with action value is 'ROUTE'"):
        entry_key = "10.2.2.2/24 10000"
        entry_key_list = [entry_key]
        traffic_expect_receive_count_list = [pkt_count]
        traffic_expect_hit_count_list = [pkt_count]

        with allure.step("Get entry counters before sending traffic, there is no cli to clear the existing counters"):
            current_entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
        with allure.step("Verify traffic can be received on the receiver, the entry matched will hit"):
            verify_traffic(topology_obj, gtp_table_params, entry_key_list, pkt_count, traffic_expect_receive_count_list)
            verify_entries_hit_as_expect(engines.dut, entry_key_list, traffic_expect_hit_count_list,
                                         pre_entry_dict=current_entry_dict)

    with allure.step("Send traffic that match more than one entries with action value is 'ROUTE'"):
        entry_key_low_pri = "20.2.2.2/32 20000"
        entry_key_high_pri = "20.2.2.2/24 20000"
        entry_key_list = [entry_key_high_pri, entry_key_low_pri]
        traffic_expect_receive_count_list = [pkt_count, 0]
        traffic_expect_hit_count_list = [pkt_count, 0]
        with allure.step("Get entry counters before sending traffic, there is no cli to clear the existing counters"):
            current_entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
        with allure.step("Verify traffic can be received on the receiver, and the entry with higher priority will hit"):
            verify_traffic(topology_obj, gtp_table_params, entry_key_list, pkt_count, traffic_expect_receive_count_list)
            verify_entries_hit_as_expect(engines.dut, entry_key_list, traffic_expect_hit_count_list,
                                         pre_entry_dict=current_entry_dict)

    with allure.step("Update entries: change the entry action from 'ROUTE' to 'DROP'"):
        for entry_key, entry_param_dict in gtp_table_params.items():
            entry_params = "--action DROP"
            cli_objects.dut.p4_gtp.update_entry(entry_key, entry_params)

    with allure.step("Send traffic that match one entry with action value is 'DROP'"):
        entry_key = "10.2.2.2/24 10000"
        entry_key_list = [entry_key]
        traffic_expect_receive_count_list = [0]
        traffic_expect_hit_count_list = [pkt_count]

        with allure.step("Get entry counters before sending traffic, there is no cli to clear the existing counters"):
            current_entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
        with allure.step("Verify traffic can not be received on the receiver, the entry matched will hit"):
            verify_traffic(topology_obj, gtp_table_params, entry_key_list, pkt_count, traffic_expect_receive_count_list)
            verify_entries_hit_as_expect(engines.dut, entry_key_list, traffic_expect_hit_count_list,
                                         pre_entry_dict=current_entry_dict)

    with allure.step("Send traffic that match more than one entries with action value is 'DROP'"):
        entry_key_low_pri = "20.2.2.2/32 20000"
        entry_key_high_pri = "20.2.2.2/24 20000"
        entry_key_list = [entry_key_high_pri, entry_key_low_pri]
        traffic_expect_receive_count_list = [0, 0]
        traffic_expect_hit_count_list = [pkt_count, 0]
        with allure.step("Get entry counters before sending traffic, there is no cli to clear the existing counters"):
            current_entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
        with allure.step("Verify traffic can not be received on the receiver, the entry matched will hit"):
            verify_traffic(topology_obj, gtp_table_params, entry_key_list, pkt_count, traffic_expect_receive_count_list)
            verify_entries_hit_as_expect(engines.dut, entry_key_list, traffic_expect_hit_count_list,
                                         pre_entry_dict=current_entry_dict)

    with allure.step("Update entries: change the entry action from 'DROP' back to 'ROUTE'"):
        for entry_key, entry_param_dict in gtp_table_params.items():
            entry_params = "--action ROUTE"
            cli_objects.dut.p4_gtp.update_entry(entry_key, entry_params)


@pytest.mark.p4_examples
@allure.title('Test gtp entries can not hit as expect.')
def test_gtp_parser_entry_not_hit(topology_obj, engines, gtp_table_params, gtp_entry_mismatch_params):
    pkt_count = 3
    entry_key_list = gtp_table_params.keys()
    traffic_expect_hit_count_list = [0] * len(entry_key_list)
    with allure.step("Send traffic that only match key_ip of one entry, and not match any keys of any other entries"):
        with allure.step("Get entry counters before sending traffic, there is no cli to clear the existing counters"):
            current_entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
        with allure.step("Verify traffic can not received on the receiver, none entry will hit"):
            mismatch_entry_key = "10.2.2.2/24 30000"
            verify_mismatch_traffic(topology_obj, mismatch_entry_key, gtp_entry_mismatch_params, pkt_count)
            verify_entries_hit_as_expect(engines.dut, entry_key_list, traffic_expect_hit_count_list,
                                         pre_entry_dict=current_entry_dict)
    with allure.step("Send traffic that only match key_teid of one entry, and not match any keys of any other entries"):
        with allure.step("Get entry counters before sending traffic, there is no cli to clear the existing counters"):
            current_entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
        with allure.step("Verify traffic can not received on the receiver, none entry will hit"):
            mismatch_entry_key = "30.2.2.2/24 10000"
            verify_mismatch_traffic(topology_obj, mismatch_entry_key, gtp_entry_mismatch_params, pkt_count)
            verify_entries_hit_as_expect(engines.dut, entry_key_list, traffic_expect_hit_count_list,
                                         pre_entry_dict=current_entry_dict)
    with allure.step("Send traffic that not match key_ip, and not match key_teid of any entry, "
                     "and not match any other entries"):
        with allure.step("Get entry counters before sending traffic, there is no cli to clear the existing counters"):
            current_entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(engines.dut,
                                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
            mismatch_entry_key = "30.2.2.2/24 30000"
        with allure.step("Verify traffic can not received on the receiver, none entry will hit"):
            verify_mismatch_traffic(topology_obj, mismatch_entry_key, gtp_entry_mismatch_params, pkt_count)
            verify_entries_hit_as_expect(engines.dut, entry_key_list, traffic_expect_hit_count_list,
                                         pre_entry_dict=current_entry_dict)


def verify_gtp_entries(gtp_table_params, cli_obj, params_type=ORI_PARAMS):
    """
    Verify GTP entries has been added or updated correctly.
    :param gtp_table_params: gtp_table_params fixture object
    :param cli_obj: cli_obj object
    :param params_type: ori_params or update_params
    :return:None
    """
    gtp_params_header_list = ["action", "priority", "port"]
    gtp_entries = cli_obj.p4_gtp.show_and_parse_entries()
    assert len(gtp_entries) == len(gtp_table_params), "The entries not added as expected"
    for gtp_entry_key, gtp_entry_all_params in gtp_table_params.items():
        assert gtp_entry_key in gtp_entries, f"{gtp_entry_key} is not added"
        gtp_entry_params = gtp_entry_all_params[params_type]
        for gtp_params_header in gtp_params_header_list:
            assert gtp_entry_params[gtp_params_header] == gtp_entries[gtp_entry_key][gtp_params_header.upper()], \
                "The value of {gtp_params_header} is {gtp_entries[gtp_entry_key][gtp_params_header.upper()]}," \
                " but expect {gtp_entry_params[gtp_params_header]}"
        logger.info(f"The entry for {gtp_entry_key} is added as expect")


def verify_traffic(topology_obj, gtp_table_params, entry_key_list, count, expected_count_list):
    """
    Send and verify traffic.
    :param topology_obj: topology_obj fixture object
    :param gtp_table_params: gtp_table_params fixture objects.
    :param entry_key_list: the entry key list
    :param count: the count of the packets to be sent
    :param expected_count_list: the count of the packets expect to be received
    """
    entry_key = entry_key_list[0]

    traffic_param_dict = gtp_table_params[entry_key]
    traffic_sender = traffic_param_dict["traffic_sender"]
    traffic_sender_port = traffic_param_dict["traffic_sender_port"]

    teid = entry_key.split(" ")[1]
    inner_dst_ip = entry_key.split(" ")[0].split("/")[0]
    inner_src_ip = "66.66.66.66"
    outer_src_ip = "77.77.77.77"
    outer_dst_ip = "88.88.88.88"
    entry_pkt = create_gtp_pkt(teid, outer_src_ip, outer_dst_ip, inner_src_ip, inner_dst_ip)

    receivers = []
    for entry_key, expected_count in zip(entry_key_list, expected_count_list):
        traffic_param_dict = gtp_table_params[entry_key]
        traffic_receiver = traffic_param_dict["traffic_receiver"]
        traffic_receiver_port = traffic_param_dict["traffic_receiver_port"]
        traffic_filter = f"src {outer_src_ip} and dst {outer_dst_ip}"
        receiver = {'receiver': f'{traffic_receiver}',
                    'receive_args': {'interface': f"{traffic_receiver_port}",
                                     'filter': traffic_filter,
                                     'count': expected_count}}
        receivers.append(receiver)

    validation_r = {f'sender': f'{traffic_sender}',
                    'send_args': {'interface': f"{traffic_sender_port}",
                                  'packets': entry_pkt, 'count': count},
                    'receivers': receivers
                    }
    scapy_r = ScapyChecker(topology_obj.players, validation_r)
    logger.info(f"Sending traffic from {traffic_sender} : {traffic_sender_port}")
    scapy_r.run_validation()


def verify_mismatch_traffic(topology_obj, mismatch_entry_key, gtp_entry_mismatch_params, count):
    """
    Send and verify traffic.
    :param topology_obj: topology_obj fixture object
    :param mismatch_entry_key, the entry key will not match any of the entries added
    :param gtp_entry_mismatch_params: gtp_entry_mismatch_params fixture objects.
    :param count: the count of the packets to be sent
    """

    traffic_param_dict = gtp_entry_mismatch_params
    outer_src_ip = traffic_param_dict["outer_src_ip"]
    outer_dst_ip = traffic_param_dict["outer_dst_ip"]
    teid = mismatch_entry_key.split(" ")[1]
    inner_dst_ip = mismatch_entry_key.split(" ")[0].split("/")[0]
    inner_src_ip = "66.66.66.66"
    entry_pkt = create_gtp_pkt(teid, outer_src_ip, outer_dst_ip, inner_src_ip, inner_dst_ip)

    traffic_sender = traffic_param_dict["traffic_sender"]
    traffic_sender_port = traffic_param_dict["traffic_sender_port"]
    traffic_receiver = traffic_param_dict["traffic_receiver"]
    traffic_receiver_port = traffic_param_dict["traffic_receiver_port"]
    traffic_filter = f"src {outer_src_ip} and dst {outer_dst_ip}"

    validation_r = {f'sender': f'{traffic_sender}',
                    'send_args': {'interface': f"{traffic_sender_port}",
                                  'packets': entry_pkt, 'count': count},
                    'receivers': [{'receiver': f'{traffic_receiver}',
                                   'receive_args': {'interface': f"{traffic_receiver_port}",
                                                    'filter': traffic_filter,
                                                    'count': 0}}]
                    }
    scapy_r = ScapyChecker(topology_obj.players, validation_r)
    logger.info(f"Sending traffic from {traffic_sender}:{traffic_sender_port} "
                f"to {traffic_receiver}:{traffic_receiver_port}")
    scapy_r.run_validation()


def verify_entries_hit_as_expect(dut_engine, entry_key_list, expected_count_list, pre_entry_dict=None):
    """
    Verify the count is as expected with the p4nspect tool
    :param dut_engine: dut ssh engine object
    :param entry_key_list: entry key of the entry in p4 vxlan bm table
    :param expected_count_list: expected pkt count list for each entry in entry_key_list
    :return: Raise error is not as expected.
    """
    entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(dut_engine,
                                                               feature_name=P4ExamplesConsts.GTP_PARSER_FEATURE_NAME,
                                                               table_name=P4ExamplesConsts.GTP_PARSER_P4NSPECT_TABLE)
    for entry_key, expected_count in zip(entry_key_list, expected_count_list):
        # TODO: workaround for the teid is not in the key of the entry_dict, correct one
        #  should be: pkt_count = entry_dict[entry_key]['packet_count']
        #  Jira ticket is there: https://jirasw.nvidia.com/browse/P4DT-310
        pkt_count = entry_dict[entry_key.split()[0]]['packet_count']
        pre_pkt_count = pre_entry_dict[entry_key.split()[0]]['packet_count'] if pre_entry_dict else 0
        assert pkt_count == pre_pkt_count + expected_count, \
            f"The counter for entry {entry_key} is not correct, expect {pkt_count} >= {expected_count}"


def create_gtp_pkt(teid, outer_src_ip, outer_dst_ip, inner_src_ip, inner_dst_ip):
    if inner_src_ip:
        gtp_pkt = f'Ether()/IP(proto={UDP_PROTOCOL}, src="{outer_src_ip}", ' \
            f'dst="{outer_dst_ip}")/UDP(dport={GTP_U_PORT})/GTPHeader(seq=12345, ' \
            f'length=9, teid={teid})/IP(src="{inner_src_ip}", dst="{inner_dst_ip}")/TCP()'
    else:
        gtp_pkt = f'Ether()/IP(proto={UDP_PROTOCOL}, src="{outer_src_ip}", ' \
            f'dst="{outer_dst_ip}")/UDP(dport={GTP_U_PORT})/GTPHeader(seq=12345, ' \
            f'length=9, teid={teid})/IP(dst="{inner_dst_ip}")/TCP()'
    return gtp_pkt
