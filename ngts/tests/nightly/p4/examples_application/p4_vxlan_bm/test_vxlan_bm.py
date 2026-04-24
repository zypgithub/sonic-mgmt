import pytest
import logging
import json
import allure
from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.config_templates.route_config_template import RouteConfigTemplate
from ngts.constants.constants import P4ExamplesConsts
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from dotted_dict import DottedDict
import ngts.helpers.p4nspect_utils as p4nspect_utils

logger = logging.getLogger()

HA_DUT_1_OVERLAY_IP = "192.168.1.3"  # ip on the vxlan
HA_DUT_1_UNDERLAY_IP = "2.2.2.2"
HB_DUT_1_OVERLAY_IP = "192.168.1.4"

HA_DUT_2_OVERLAY_IP = "193.168.1.3"
HB_DUT_2_OVERLAY_IP = "193.168.1.4"  # ip on the vxlan
HB_DUT_2_UNDERLAY_IP = "3.3.3.3"

DUT_HA_1_IP = "2.2.2.1"
DUT_HA_2_IP = "193.168.1.1"
DUT_HB_1_IP = "192.168.1.1"
DUT_HB_2_IP = "3.3.3.1"
HA_DUT_1_VXLAN_ID = 6
HA_DUT_1_VXLAN_NAME = "vxlan6"

HB_DUT_2_VXLAN_ID = 8
HB_DUT_2_VXLAN_NAME = "vxlan8"

ENCAP_ENTRY_PARAMS = ["vni", "underlay_dip", "priority", "action"]
DECAP_ENTRY_PARAMS = ["pbs_port", "priority", "action"]
ENCAP_TABLE_NAME = "table_overlay_router"
DECAP_TABLE_NAME = "table_tenant_forward"
REBOOT_LIST = ["reboot", "config reload -y"]
ENCAP_TABLE_ACTION = "tunnel_encap"
DECAP_TABLE_ACTION = "do_forward"
TUNNEL_SRC_IP = "1.1.1.1"


@pytest.fixture(scope='module')
def table_params(interfaces, engines, topology_obj):
    """
    Fixture used to create the TableParams object which contains some params used in the test cases
    :param interfaces: interfaces fixture
    :param engines : engines fixture object
    :param topology_obj: topology_obj fixture object
    """
    table_param_data = DottedDict()
    encap_table_entry = {}
    decap_table_entry = {}
    # hb --> ha
    encap_table_entry_params = dict()
    encap_table_entry_params.update({"vni": f"{HA_DUT_1_VXLAN_ID}",
                                     "underlay_dip": f"{HA_DUT_1_UNDERLAY_IP}",
                                     "priority": 2,
                                     "action": f"{ENCAP_TABLE_ACTION}"})

    encap_table_entry_params["traffic_sender"] = "hb"
    encap_table_entry_params["traffic_sender_port"] = interfaces.hb_dut_1
    encap_table_entry_params["traffic_src_ip"] = HB_DUT_1_OVERLAY_IP
    encap_table_entry_params["traffic_receiver"] = "ha"
    encap_table_entry_params["traffic_receiver_port"] = HA_DUT_1_VXLAN_NAME
    encap_table_entry_params["traffic_dst_ip"] = HA_DUT_1_OVERLAY_IP
    encap_table_entry_params["update_params"] = {"vni": 30, "underlay_dip": "10.10.10.10"}
    encap_table_entry[f'{HA_DUT_1_OVERLAY_IP}'] = encap_table_entry_params
    # ha --> hb
    encap_table_entry_params = dict()
    encap_table_entry_params.update({"vni": f"{HB_DUT_2_VXLAN_ID}",
                                     "underlay_dip": f"{HB_DUT_2_UNDERLAY_IP}",
                                     "priority": 2,
                                     "action": f"{ENCAP_TABLE_ACTION}"})

    encap_table_entry_params["traffic_sender"] = "ha"
    encap_table_entry_params["traffic_sender_port"] = interfaces.ha_dut_2
    encap_table_entry_params["traffic_src_ip"] = HA_DUT_2_OVERLAY_IP
    encap_table_entry_params["traffic_receiver"] = "hb"
    encap_table_entry_params["traffic_receiver_port"] = HB_DUT_2_VXLAN_NAME
    encap_table_entry_params["traffic_dst_ip"] = HB_DUT_2_OVERLAY_IP
    encap_table_entry[f'{HB_DUT_2_OVERLAY_IP}'] = encap_table_entry_params

    # ha --> hb
    decap_table_entry_params = dict()
    decap_table_entry_params.update({"pbs_port": f"{interfaces.dut_hb_1}",
                                     "action": f"{DECAP_TABLE_ACTION}",
                                     "priority": 5})
    decap_table_entry_params["traffic_sender"] = "ha"
    decap_table_entry_params["traffic_sender_port"] = HA_DUT_1_VXLAN_NAME
    decap_table_entry_params["traffic_src_ip"] = HA_DUT_1_OVERLAY_IP
    decap_table_entry_params["traffic_receiver"] = "hb"
    decap_table_entry_params["traffic_receiver_port"] = interfaces.hb_dut_1
    decap_table_entry_params["traffic_dst_ip"] = HB_DUT_1_OVERLAY_IP
    decap_table_entry_params["update_params"] = {"pbs_port": f"{interfaces.dut_ha_1}", "priority": 10}
    decap_table_entry[f'{HB_DUT_1_OVERLAY_IP}'] = decap_table_entry_params
    # hb --> ha
    decap_table_entry_params = dict()
    decap_table_entry_params.update({"pbs_port": f"{interfaces.dut_ha_2}",
                                     "action": f"{DECAP_TABLE_ACTION}",
                                     "priority": 5})
    decap_table_entry_params["traffic_sender"] = "hb"
    decap_table_entry_params["traffic_sender_port"] = HB_DUT_2_VXLAN_NAME
    decap_table_entry_params["traffic_src_ip"] = HB_DUT_2_OVERLAY_IP
    decap_table_entry_params["traffic_receiver"] = "ha"
    decap_table_entry_params["traffic_receiver_port"] = interfaces.ha_dut_2
    decap_table_entry_params["traffic_dst_ip"] = HA_DUT_2_OVERLAY_IP
    decap_table_entry[f'{HA_DUT_2_OVERLAY_IP}'] = decap_table_entry_params

    table_param_data.encap_table = encap_table_entry
    table_param_data.decap_table = decap_table_entry

    unmatch_traffic_params = dict()
    unmatch_traffic_params["traffic_sender"] = 'ha'
    unmatch_traffic_params["traffic_sender_port"] = interfaces.ha_dut_1
    unmatch_traffic_params["traffic_src_ip"] = HA_DUT_1_UNDERLAY_IP
    unmatch_traffic_params["traffic_receiver"] = 'hb'
    unmatch_traffic_params["traffic_receiver_port"] = interfaces.hb_dut_2
    unmatch_traffic_params["traffic_dst_ip"] = HB_DUT_2_UNDERLAY_IP
    table_param_data.unmatch_traffic = unmatch_traffic_params
    return table_param_data


@pytest.fixture(scope='module', autouse=True)
def p4_vxlan_bm_configuration(topology_obj, engines, interfaces):
    """
    Pytest fixture which are doing configuration fot test case based on push gate config
    :param topology_obj: topology object fixture
    :param engines: engines fixture
    :param interfaces: interfaces fixture
    """
    ha_engine = engines.ha
    hb_engine = engines.hb

    ip_config_dict = {
        'dut': [{'iface': interfaces.dut_ha_1, 'ips': [(DUT_HA_1_IP, '24')]},
                {'iface': interfaces.dut_ha_2, 'ips': [(DUT_HA_2_IP, '24')]},
                {'iface': interfaces.dut_hb_1, 'ips': [(DUT_HB_1_IP, '24')]},
                {'iface': interfaces.dut_hb_2, 'ips': [(DUT_HB_2_IP, '24')]},
                ],
        'ha': [{'iface': interfaces.ha_dut_1, 'ips': [(HA_DUT_1_UNDERLAY_IP, '24')]},
               {'iface': HA_DUT_1_VXLAN_NAME, 'ips': [(HA_DUT_1_OVERLAY_IP, '24')]},
               {'iface': interfaces.ha_dut_2, 'ips': [(HA_DUT_2_OVERLAY_IP, '24')]}
               ],
        'hb': [{'iface': interfaces.hb_dut_1, 'ips': [(HB_DUT_1_OVERLAY_IP, '24')]},
               {'iface': interfaces.hb_dut_2, 'ips': [(HB_DUT_2_UNDERLAY_IP, '24')]},
               {'iface': HB_DUT_2_VXLAN_NAME, 'ips': [(HB_DUT_2_OVERLAY_IP, '24')]}
               ]
    }

    # Static route config which will be used in test
    static_route_config_dict = {
        'ha': [{'dst': '1.1.1.0', 'dst_mask': 24, 'via': [DUT_HA_1_IP]},
               {'dst': '3.3.3.0', 'dst_mask': 24, 'via': [DUT_HA_1_IP]}],
        'hb': [{'dst': '1.1.1.0', 'dst_mask': 24, 'via': [DUT_HB_2_IP]},
               {'dst': '2.2.2.0', 'dst_mask': 24, 'via': [DUT_HB_2_IP]}]
    }

    logger.info('Starting P4 VXLAN BM configuration')
    ha_engine.run_cmd(f"sudo ip link add name {HA_DUT_1_VXLAN_NAME} type vxlan id {HA_DUT_1_VXLAN_ID} "
                      f"dev {interfaces.ha_dut_1} remote {TUNNEL_SRC_IP} dstport 4789")
    ha_engine.run_cmd(f"sudo ip link set {HA_DUT_1_VXLAN_NAME} up")

    hb_engine.run_cmd(f"sudo ip link add name {HB_DUT_2_VXLAN_NAME} type vxlan id {HB_DUT_2_VXLAN_ID} "
                      f"dev {interfaces.hb_dut_2} remote {TUNNEL_SRC_IP} dstport 4789")
    hb_engine.run_cmd(f"sudo ip link set {HB_DUT_2_VXLAN_NAME} up")

    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    RouteConfigTemplate.configuration(topology_obj, static_route_config_dict)
    logger.info('P4 Sampling Common configuration completed')
    yield
    logger.info('Starting P4 Sampling configuration cleanup')
    RouteConfigTemplate.cleanup(topology_obj, static_route_config_dict)
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    ha_engine.run_cmd(f"sudo ip link delete name {HA_DUT_1_VXLAN_NAME}")
    hb_engine.run_cmd(f"sudo ip link delete name {HB_DUT_2_VXLAN_NAME}")
    logger.info('P4 Sampling cleanup completed')


@pytest.fixture(scope='module', autouse=True)
def p4_vxlan_bm_entry_config(engines, table_params, cli_objects):
    """
    Fixture used to config the vxlan bm entries
    :param engines: engines fixture
    :param table_params: table_params fixture
    :param cli_objects: cli_objects fixture
    """
    encap_entry_dict = table_params.encap_table
    decap_entry_dict = table_params.decap_table
    cli_obj = cli_objects.dut
    with allure.step(f"Start feature {P4ExamplesConsts.VXLAN_BM_FEATURE_NAME} in the p4 examples app"):
        cli_obj.p4_examples.start_p4_example_feature(P4ExamplesConsts.VXLAN_BM_FEATURE_NAME)
    with allure.step("Add entries"):
        with allure.step(f"Add entry for the {ENCAP_TABLE_NAME} table"):
            for encap_entry_key, encap_entry_param_dict in encap_entry_dict.items():
                encap_entry_params = get_encap_entry_params(encap_entry_param_dict)
                cli_obj.p4_vxlan_bm.add_encap_entry(encap_entry_key, encap_entry_params)
            p4nspect_utils.attach_counters(engines.dut, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                           table_name=ENCAP_TABLE_NAME)
        with allure.step(f"Add entry for the {DECAP_TABLE_NAME} table"):
            for decap_entry_key, decap_entry_param_dict in decap_entry_dict.items():
                decap_entry_params = get_decap_entry_params(decap_entry_param_dict)
                cli_obj.p4_vxlan_bm.add_decap_entry(decap_entry_key, decap_entry_params)
            p4nspect_utils.attach_counters(engines.dut, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                           table_name=DECAP_TABLE_NAME)

    yield
    with allure.step("Delete entries"):
        with allure.step(f"Delete entries for the {ENCAP_TABLE_NAME} table"):
            p4nspect_utils.detach_counters(engines.dut, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                           table_name=DECAP_TABLE_NAME)
            for encap_entry_key in encap_entry_dict:
                cli_obj.p4_vxlan_bm.delete_encap_entry(encap_entry_key)
        with allure.step(f"Delete entries for the {DECAP_TABLE_NAME} table"):
            p4nspect_utils.detach_counters(engines.dut, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                           table_name=ENCAP_TABLE_NAME)
            for decap_entry_key in decap_entry_dict:
                cli_obj.p4_vxlan_bm.delete_decap_entry(decap_entry_key)

    with allure.step("Verify entries can be deleted correctly"):
        with allure.step(f"Verify {ENCAP_TABLE_NAME} entries have be deleted correctly"):
            logger.info(f"Verify {ENCAP_TABLE_NAME} entries have be deleted correctly")
            verify_entries_removed(engines.dut, ENCAP_TABLE_NAME, table_params.encap_table)
        with allure.step(f"Verify {DECAP_TABLE_NAME} entries have be deleted correctly"):
            logger.info(f"Verify {DECAP_TABLE_NAME} entries have be deleted correctly")
            verify_entries_removed(engines.dut, DECAP_TABLE_NAME, table_params.decap_table)

    with allure.step(f"Stop feature {P4ExamplesConsts.VXLAN_BM_FEATURE_NAME} in the p4 examples app"):
        cli_obj.p4_examples.stop_p4_example_feature()


@pytest.mark.p4_examples
def test_vxlan_bm_basic(topology_obj, engines, table_params, cli_objects):
    """
    Vxlan BM basic test
    :param topology_obj:topology object fixture
    :param engines:engines fixture
    :param table_params:table_params fixture
    """
    with allure.step("Verify entries have be added correctly"):
        with allure.step(f"Verify {ENCAP_TABLE_NAME} entries have be added correctly"):
            logger.info(f"Verify {ENCAP_TABLE_NAME} entries have be added correctly")
            verify_entries_added(engines.dut, ENCAP_TABLE_NAME, table_params.encap_table, ENCAP_ENTRY_PARAMS)
        with allure.step(f"Verify {DECAP_TABLE_NAME} entries have be added correctly"):
            logger.info(f"Verify {DECAP_TABLE_NAME} entries have be added correctly")
            verify_entries_added(engines.dut, DECAP_TABLE_NAME, table_params.decap_table, DECAP_ENTRY_PARAMS)
    with allure.step("Clear counters"):
        p4nspect_utils.clear_counters(engines.dut, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME)

    with allure.step("Send traffic from VTEP to BM which will match and hit entry with high priority"):
        verify_decap_table_traffic(topology_obj, engines, table_params.decap_table, 3, 3)

    with allure.step("Send traffic from BM to VTEP which will match and hit entry with high priority"):
        verify_encap_table_traffic(topology_obj, engines, table_params.encap_table, 3, 3)

    with allure.step("Clear counters"):
        p4nspect_utils.clear_counters(engines.dut, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME)

    with allure.step("Send traffic which will not match any entries"):
        logger.info("Verify the traffic can be received on the other side")
        verify_traffic(topology_obj, table_params.unmatch_traffic, 20, 20)
        logger.info("verify that the traffic can not match any entries")
        verify_entries_not_hit(engines.dut, DECAP_TABLE_NAME, table_params.decap_table.keys(), 20)
        verify_entries_not_hit(engines.dut, ENCAP_TABLE_NAME, table_params.encap_table.keys(), 20)

    with allure.step("Edit existing entries"):
        edit_existing_entries(table_params, cli_objects)
    with allure.step("Very entries have been updated"):
        verify_entries_updated(engines.dut, ENCAP_TABLE_NAME, table_params.encap_table, ENCAP_ENTRY_PARAMS)
        verify_entries_updated(engines.dut, DECAP_TABLE_NAME, table_params.decap_table, DECAP_ENTRY_PARAMS)


def convert_entry_params_from_dict_to_string(entry_param_dict, entry_params_name_map):
    """
    Covert the entry params which defined in dict format to the string format
    :param entry_param_dict: entry params in dictionary
    :param entry_params_name_map: entry params name map, map between sdk param name and cli param name
    :return: string of the entry params
    """
    ret = ""
    for param_key, param_name in entry_params_name_map.items():
        if param_key not in entry_param_dict:
            continue
        if param_key == "action":
            ret += f"--{param_name} {entry_param_dict[param_key].upper()} "
        else:
            ret += f"--{param_name} {entry_param_dict[param_key]} "
    return ret


def get_encap_entry_params(encap_entry_param_dict):
    """
    Get the encap table entry params
    :param encap_entry_param_dict: encap entry params dict which defined in the table params
    :return: string of the entry params
    """
    encap_params_name_map = {'vni': 'vni',
                             'underlay_dip': "underlay-ip",
                             'priority': 'priority',
                             'action': 'action'}

    return convert_entry_params_from_dict_to_string(encap_entry_param_dict, encap_params_name_map)


def get_decap_entry_params(decap_entry_param_dict):
    """
    Get the decap table entry params
    :param decap_entry_param_dict: decap entry params dict which defined in the table params
    :return: string of the entry params
    """
    decap_params_name_map = {'pbs_port': 'port',
                             'priority': 'priority',
                             'action': 'action'}

    return convert_entry_params_from_dict_to_string(decap_entry_param_dict, decap_params_name_map)


def verify_entries_added(dut_engine, table_name, entries_expected, entry_action_params):
    """
    Verify that the entries have been added as expected
    :param dut_engine: Dut engine object
    :param table_name: table name
    :param entries_expected:  entries that expected to be added
    :param entry_action_params: the action param name list of the entry
    """
    entries = p4nspect_utils.get_p4nspect_query_json_parsed(dut_engine, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                                            table_name=table_name)
    for entry_key, entry_params in entries_expected.items():
        assert entry_key in entries, f"{entry_key} is not added"
        entry_params_added = entries[entry_key]
        for action_param in entry_action_params:
            assert str(entry_params[action_param]) == entry_params_added[action_param], \
                f"In entry {entry_key}, the value of {action_param} is {entry_params_added[action_param]}, " \
                f"expected {entry_params[action_param]} "


def verify_entries_removed(dut_engine, table_name, entries_expected):
    """
    Verify that the entries have been deleted
    :param dut_engine: Dut engine object
    :param table_name: table name
    :param entries_expected: entries that expected to be deleted
    :return: None
    """
    entries = p4nspect_utils.get_p4nspect_query_json_parsed(dut_engine, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                                            table_name=table_name)
    for entry_key, entry_params in entries_expected.items():
        assert entry_key not in entries, f"{entry_key} is not removed"


def verify_entries_updated(dut_engine, table_name, entries_expected, entry_action_params):
    """
    Verify that the entries have been updated as expected
    :param dut_engine: Dut engine object
    :param table_name: table name
    :param entries_expected:  entries that expected to be added
    :param entry_action_params: the action param name list of the entry
    """
    entries = p4nspect_utils.get_p4nspect_query_json_parsed(dut_engine, feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                                            table_name=table_name)
    for entry_key, entry_params in entries_expected.items():
        if "update_params" in entry_params:
            entry_params_added = entries[entry_key]
            for action_param in entry_action_params:
                if action_param in entry_params["update_params"]:
                    expected_param_value = entry_params["update_params"][action_param]
                else:
                    expected_param_value = entry_params[action_param]
                assert str(expected_param_value) == entry_params_added[action_param], \
                    f"In entry {entry_key}, the value of {action_param} is {entry_params_added[action_param]}, " \
                    f"expected {expected_param_value} "


def verify_encap_table_traffic(topology_obj, engines, encap_table_params, count, expected_count):
    """
    Send and verify traffic for the flow table.
    :param topology_obj: topology_obj fixture object
    :param engines: engines fixture object
    :param encap_table_params: the traffic params which will be used when send traffic.
    :param count: the count of the packets to be sent
    :param expected_count: the expected count of the packets that should be received
    """
    for entry_key, entry_params in encap_table_params.items():
        verify_traffic(topology_obj, entry_params, count, expected_count)
        verify_entry_hit(engines.dut, ENCAP_TABLE_NAME, entry_key, 3)


def verify_decap_table_traffic(topology_obj, engines, decap_table_params, count, expected_count):
    """
    Send and verify traffic for the port table.
    :param topology_obj: topology_obj fixture object
    :param engines: engines fixture object
    :param decap_table_params: decap_table_params.
    :param count: the count of the packets to be sent
    :param expected_count: the expected count of the packets that should be received
    """
    for entry_key, entry_params in decap_table_params.items():
        verify_traffic(topology_obj, entry_params, count, expected_count)
        verify_entry_hit(engines.dut, DECAP_TABLE_NAME, entry_key, 3)


def verify_traffic(topology_obj, traffic_param_dict, count, expected_count):
    """
    Send and verify traffic.
    :param topology_obj: topology_obj fixture object
    :param traffic_param_dict: traffic params.
    :param count: the count of the packets to be sent
    :param expected_count: the count of the packets expect to be received
    """
    dst_ip = traffic_param_dict["traffic_dst_ip"]
    src_ip = traffic_param_dict["traffic_src_ip"]
    entry_pkt = f'Ether()/IP(src="{src_ip}",dst="{dst_ip}")'
    sender = traffic_param_dict["traffic_sender"]
    sender_port = traffic_param_dict["traffic_sender_port"]
    receiver = traffic_param_dict["traffic_receiver"]
    receiver_port = traffic_param_dict["traffic_receiver_port"]
    traffic_filter = f"src {src_ip} and dst {dst_ip}"
    validation_r = {f'sender': f'{sender}',
                    'send_args': {'interface': f"{sender_port}",
                                  'packets': entry_pkt, 'count': count},
                    'receivers':
                        [
                            {'receiver': f'{receiver}',
                             'receive_args': {'interface': f"{receiver_port}",
                                              'filter': traffic_filter, 'count': expected_count}}
    ]
    }
    scapy_r = ScapyChecker(topology_obj.players, validation_r)
    scapy_r.run_validation()


def verify_entry_hit(dut_engine, table_name, entry_key, expected_count):
    """
    Verify the count is as expected with the p4nspect tool
    :param dut_engine: dut ssh engine object
    :param table_name: table name in the p4 vxlan bm feature
    :param entry_key: entry key of the entry in p4 vxlan bm table
    :param expected_count: expected okt count
    :return: Raise error is not as expected.
    """
    entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(dut_engine,
                                                               feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                                               table_name=table_name)
    pkt_count = entry_dict[entry_key]['packet_count']
    assert pkt_count >= expected_count, \
        f"The counter for entry {entry_key} is not correct, expect {pkt_count} >= {expected_count}"


def verify_entries_not_hit(dut_engine, table_name, entry_key_list, expected_count):
    """
    Verify the count is as expected with the p4nspect tool
    :param dut_engine: dut ssh engine object
    :param table_name: table name in the p4 vxlan bm feature
    :param entry_key_list: entry keys of the entry in p4 vxlan bm table
    :param expected_count: expected okt count
    :return: Raise error is not as expected.
    """
    for entry_key in entry_key_list:
        entry_dict = p4nspect_utils.get_p4nspect_query_json_parsed(dut_engine,
                                                                   feature_name=P4ExamplesConsts.VXLAN_BM_FEATURE_NAME,
                                                                   table_name=table_name)
        pkt_count = entry_dict[entry_key]['packet_count']
        assert pkt_count < expected_count, \
            f"The counter for entry {entry_key} is not correct, expect {pkt_count} < {expected_count}"


def edit_existing_entries(table_params, cli_objects):
    """
    Edit the existing entries
    :param table_params: table_params fixture object
    :param cli_objects: cli_objects fixture object
    """
    encap_entry_dict = table_params.encap_table
    decap_entry_dict = table_params.decap_table
    for encap_entry_key, encap_entry_param_dict in encap_entry_dict.items():
        if "update_params" in encap_entry_param_dict:
            entry_update_param_dict = encap_entry_param_dict['update_params']
            encap_entry_params = get_encap_entry_params(entry_update_param_dict)
            cli_objects.dut.p4_vxlan_bm.update_encap_entry(encap_entry_key, encap_entry_params)

    for decap_entry_key, decap_entry_param_dict in decap_entry_dict.items():
        if "update_params" in decap_entry_param_dict:
            entry_update_param_dict = decap_entry_param_dict['update_params']
            decap_entry_params = get_decap_entry_params(entry_update_param_dict)
            cli_objects.dut.p4_vxlan_bm.update_decap_entry(decap_entry_key, decap_entry_params)
