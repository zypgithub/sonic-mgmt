import os
import logging
import json
import jinja2

from ngts.cli_wrappers.sonic.sonic_acl_clis import SonicAclCli
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from retry.api import retry_call


logger = logging.getLogger()

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
ACL_REMOVE_RULES_FILE = "acl_rules_del.json"
ACL_TEMPLATE_FOLDER = "acl"


class ACLConstants:
    PKT_COUNT = 10
    IP_VERSION_LIST = ["ipv4", "ipv6"]
    STAGE_LIST = ["ingress", "egress"]
    PORT_TYPE_LIST = ["physical", "lag"]
    TRAFFIC_TYPE_LIST = ["tcp", "udp", "icmp"]
    RULES = {
        "DATA_INGRESS_L3TEST": {
            "TEMPLATE_FILE": "acl_rules_ipv4.j2",
            "TEMPLATE_FILE_ARGS": {"acl_table_name": "DATA_INGRESS_L3TEST",
                                   "ether_type": "2048",
                                   "forward_src_ip_match": "10.0.1.2/32",
                                   "forward_dst_ip_match": "121.0.0.2/32",
                                   "drop_src_ip_match": "10.0.1.6/32",
                                   "drop_dst_ip_match": "123.0.0.2/32",
                                   "unmatch_dst_ip": "125.0.0.2/32",
                                   "unused_src_ip": "10.0.1.11/32",
                                   "unused_dst_ip": "192.168.0.1/32"
                                   },
        },
        "DATA_EGRESS_L3TEST": {
            "TEMPLATE_FILE": "acl_rules_ipv4.j2",
            "TEMPLATE_FILE_ARGS": {"acl_table_name": "DATA_EGRESS_L3TEST",
                                   "ether_type": "2048",
                                   "forward_src_ip_match": "30.0.0.2/32",
                                   "forward_dst_ip_match": "120.0.0.2/32",
                                   "drop_src_ip_match": "30.0.0.6/32",
                                   "drop_dst_ip_match": "122.0.0.2/32",
                                   "unmatch_dst_ip": "124.0.0.2/32",
                                   "unused_src_ip": "30.0.0.1/32",
                                   "unused_dst_ip": "124.0.0.2/32"
                                   },
        },
        "DATA_INGRESS_L3V6TEST": {
            "TEMPLATE_FILE": "acl_rules_ipv6.j2",
            "TEMPLATE_FILE_ARGS": {"acl_table_name": "DATA_INGRESS_L3V6TEST",
                                   "ether_type": "34525",
                                   "forward_src_ip_match": "7000:a800::2/128",
                                   "forward_dst_ip_match": "7000:121::2/128",
                                   "drop_src_ip_match": "7000:a800::6/128",
                                   "drop_dst_ip_match": "7000:123::2/128",
                                   "unmatch_dst_ip": "7000:125::2/128",
                                   "unused_src_ip": "7000:a800::1/128",
                                   "unused_dst_ip": "25c0:a800::1/128"
                                   },
        },
        "DATA_EGRESS_L3V6TEST": {
            "TEMPLATE_FILE": "acl_rules_ipv6.j2",
            "TEMPLATE_FILE_ARGS": {"acl_table_name": "DATA_EGRESS_L3V6TEST",
                                   "ether_type": "34525",
                                   "forward_src_ip_match": "80c0:a800::2/128",
                                   "forward_dst_ip_match": "7000:120::2/128",
                                   "drop_src_ip_match": "80c0:a800::6/128",
                                   "drop_dst_ip_match": "7000:122::2/128",
                                   "unmatch_dst_ip": "7000:124::2/128",
                                   "unused_src_ip": "80c0:a800::1/128",
                                   "unused_dst_ip": "7000:124::2/128"
                                   },
        }
    }


def get_rules_template_file(table_name):
    """
    Get the template file name for the specified table name which define the acl rules that will be added
    :param table_name: table name
    :return: string of the file name
    """
    return ACLConstants.RULES[table_name]['TEMPLATE_FILE'] if table_name in ACLConstants.RULES else ""


def get_rules_template_file_args(table_name):
    """
    Get the args defined for the table name in the constant that will use to render the template file.
    :param table_name: table name
    :return: dictionary of the args
    """
    return ACLConstants.RULES[table_name]["TEMPLATE_FILE_ARGS"] if table_name in ACLConstants.RULES else ""


def generate_table_name(stage, ip_version, is_mirror=False):
    """
    Generate the ACL table name with the stage, ip version...
    :param stage: ingress or egress
    :param ip_version: ipv4 or ipv6
    :param is_mirror: True if the ACL table type if mirror, else False
    :return: string of table name
    """
    if is_mirror:
        table_type = "MIRROR" if ip_version == "ipv4" else "MIRRORV6"
    else:
        table_type = "L3" if ip_version == "ipv4" else "L3V6"
    return table_type, f"DATA_{stage.upper()}_{table_type}TEST"


def generate_acl_table_config(stage, ip_version, port_list, is_mirror=False):
    """
    Generate the acl table config dictionary
    :param stage: ingress or egress
    :param ip_version: ipv4 or ipv6
    :param port_list: list of ports that the acl table will be bounded to.
    :param is_mirror: True if the ACL table type if mirror, else False
    :return: dictionary of the acl table config, these values will be used to create the acl table and the acl rules.
    """
    table_type, table_name = generate_table_name(stage, ip_version, is_mirror)
    rules_template_file = get_rules_template_file(table_name)
    rules_template_file_args = get_rules_template_file_args(table_name)
    acl_table_config = {
        "table_name": table_name,
        "table_ports": port_list,
        "table_stage": stage,
        "table_type": table_type,
        "rules_template_file": rules_template_file,
        "rules_template_file_args": rules_template_file_args
    }
    return acl_table_config


def add_acl_table(cli_obj, acl_table_config_list):
    """
    Create or remove the acl tables
    :param cli_obj: dut cli_obj object
    :param acl_table_config_list: acl_table_config_list fixture, which is a list of value returned from generate_acl_table
    :return: None
    """
    for acl_table_config in acl_table_config_list:
        table_name = acl_table_config["table_name"]
        logger.info(f"Adding ACL table: {table_name}")
        table_ports = acl_table_config["table_ports"]
        table_type = acl_table_config['table_type']
        stage = acl_table_config['table_stage']
        description = ""
        cli_obj.acl.create_table(table_name, table_type, description, stage, table_ports)


def remove_acl_table(cli_obj, acl_table_config_list):
    """
    Remove the acl tables
    :param cli_obj: dut cli_obj object
    :param acl_table_config_list: acl_table_config_list fixture, which is a list of value returned from generate_acl_table
    :return: None
    """
    for acl_table_config in acl_table_config_list:
        table_name = acl_table_config["table_name"]
        logger.info(f"Removing ACL table: {table_name}")
        cli_obj.acl.remove_table(table_name)


def add_acl_rules(dut_engine, cli_obj, acl_table_config_list):
    """
    Add the acl rules according to the acl rules defined in the template file, the acl rule template file name for
    each acl table is defined in the acl_table_config_list
    :param dut_engine: dut engine ssh object
    :param acl_table_config_list: acl_table_config_list fixture, which is a list of value returned from generate_acl_table
    :return:None
    """
    for acl_table_config in acl_table_config_list:
        table_name = acl_table_config["table_name"]
        template_file_name = acl_table_config['rules_template_file']
        if not template_file_name:
            continue
        template_file = os.path.join(BASE_DIR, f"{ACL_TEMPLATE_FOLDER}/{template_file_name}")
        logger.info(f"Generating basic ACL rules config for ACL table \"{table_name}\" on {dut_engine}")
        dut_conf_file_path = f"acl_rules_{table_name}.json"
        config_template = jinja2.Template(open(template_file).read())
        with open('acl_config_file', 'w') as config_file:
            config_file.write(config_template.render(acl_table_config['rules_template_file_args']))
        dut_engine.copy_file(source_file='acl_config_file',
                             dest_file=dut_conf_file_path,
                             file_system="/home/admin",
                             overwrite_file=True,
                             verify_file=False)
        logger.info(f"Applying ACL rules config \"{dut_conf_file_path}\"")
        cli_obj.acl.apply_acl_rules(dut_conf_file_path)


def clear_acl_rules(dut_engine, cli_obj):
    """
    Remove all the acl rules
    :param dut_engine: dut engine ssh object
    """
    logger.info(f"Clear the acl rules on {dut_engine}")
    acl_config_file = os.path.join(BASE_DIR, f"{ACL_TEMPLATE_FOLDER}/{ACL_REMOVE_RULES_FILE}")
    dut_conf_file_path = f"{ACL_REMOVE_RULES_FILE}"
    dut_engine.copy_file(source_file=acl_config_file,
                         dest_file=dut_conf_file_path,
                         file_system="/home/admin",
                         overwrite_file=True,
                         verify_file=False)
    logger.info(f"Tear down ACL rules config \"{dut_conf_file_path}\"")
    cli_obj.acl.apply_config(dut_conf_file_path)


def verify_acl_tables_exist(cli_obj, acl_table_config_list, expect_exist):
    """
    Check if the ACL tables exist or not.
    :param cli_obj: dut cli_obj object
    :param acl_table_config_list: acl_table_config_list fixture object
    :param expect_exist: True if expect the tables exist, False if not expect the ACL tables exist
    :return: None
    """
    acl_tables = cli_obj.acl.show_and_parse_acl_table()

    for acl_table_config in acl_table_config_list:
        table_name = acl_table_config['table_name']
        if expect_exist:
            assert table_name in acl_tables, f"{table_name} is not added correctly"
        else:
            assert table_name not in acl_tables, f"{table_name} is not removed correctly"


def verify_acl_rules(cli_obj, acl_table_config_list, expect_exist):
    """
    Check if the ACL rules exist or not, and check if the content of the rules are same as defined.
    :param cli_obj: dut cli_obj object
    :param acl_table_config_list: acl_table_config_list fixture object
    :param expect_exist: True if expect  ACL rules exist, False if not expect the ACL rules exist
    :return: None
    """
    acl_table_rules = cli_obj.acl.show_and_parse_acl_rule()
    for acl_table_config in acl_table_config_list:
        table_name = acl_table_config['table_name']
        acl_rule_list = acl_table_rules[table_name] if table_name in acl_table_rules else []
        if expect_exist:
            if acl_table_config['rules_template_file']:
                acl_rules_template_file = acl_table_config['rules_template_file']
                acl_rules_template_file_args = acl_table_config['rules_template_file_args']
                defined_acl_rules = parse_rules_template_file(acl_rules_template_file, acl_rules_template_file_args)
                assert len(acl_rule_list) == len(defined_acl_rules), "The acl rules not added"
                assert compare_acl_rules(acl_rule_list, defined_acl_rules), "The acl rules content is not as expected"
            else:
                assert len(acl_rule_list) == 0, "The acl rules should not be added to this table"
        else:
            assert len(acl_rule_list) == 0, "The acl rules not cleared"


def compare_acl_rules(added_acl_rule_list, defined_acl_rules):
    """
    Compare the ACL rules get from the cli command with the acl rules defined in the template file to check if the
    rules are added correctly
    :param added_acl_rule_list: list of acl rules get from the cli command.
    :param defined_acl_rules: The acl rules defined in the template file.
    :return: True if the the rules are added correctly, else False
    Examples for added_acl_rule_list:
      [{'Table': 'DATA_INGRESS_L3TEST', 'Rule': 'RULE_1', 'Priority': '9999', 'Action': 'FORWARD',
        'Match': ['ETHER_TYPE: 2048', 'SRC_IP: 10.0.1.2/32']},
       {'Table': 'DATA_INGRESS_L3TEST', 'Rule': 'RULE_2', 'Priority': '9998', 'Action': 'FORWARD',
        'Match': ['DST_IP: 121.0.0.2/32', 'ETHER_TYPE: 2048']}...]
    Examples for defined_acl_rules:
      {'RULE_1': {'Match': {'ETHER_TYPE': 2048, 'SRC_IP': '10.0.1.2/32'}, 'Action': 'FORWARD', 'Priority': '9999'},
       'RULE_2': {'Match': {'DST_IP': '121.0.0.2/32', 'ETHER_TYPE': 2048}, 'Action': 'FORWARD', 'Priority': '9998'}...}
    """
    for added_acl_rule in added_acl_rule_list:
        rule_name = added_acl_rule['Rule']
        if rule_name not in defined_acl_rules:
            logger.error(f"The acl rule {rule_name} can not found in the defined acl rule list")
            return False
        defined_acl_rule = defined_acl_rules[rule_name]
        priority = added_acl_rule['Priority']
        action = added_acl_rule['Action']
        if priority != defined_acl_rule['Priority'] or action != defined_acl_rule['Action']:
            logger.error(f"The priority and action of rule {priority} is {action} and {rule_name}, "
                         f"defined value is {defined_acl_rule['Priority']} and {defined_acl_rule['Action']} ")
            return False
        match = added_acl_rule['Match']
        expected_match = defined_acl_rule["Match"]
        if len(match) != len(expected_match):
            logger.error(f"The match value of rule {rule_name} is not same")
            return False
        for match_item in match:
            key = match_item.split(":")[0].strip()
            value = ":".join(match_item.split(":")[1:]).strip()
            if key not in expected_match:
                logger.error(f"The {key} of rule {rule_name} not found in the defined acl rule")
                return False
            if value != str(expected_match[key]):
                logger.error(f"The value {value} of {key} in rule {rule_name} is not same as defined acl rule")
                return False
    return True


def parse_rules_template_file(acl_rules_template_file, acl_rules_template_file_args):
    """
    Parse the acl rules template file
    :param acl_rules_template_file: acl table and rules information are defined in it.
    :param acl_rules_template_file_args: acl table and rules information are defined in it.
    :return: A dictionary of acl rules defined in the template file. for the example of template file content
            can refer to  helpers/acl/acl_rules_ipv4.j2
    Example: {"RULE_1": {"Priority": 9998, "Action": "FORWARD",
                         "Match":{"ETHER_TYPE": "2048", "SRC_IP":"10.0.1.6/32"}}, ...}
    """

    template_file = os.path.join(BASE_DIR, f"{ACL_TEMPLATE_FOLDER}/{acl_rules_template_file}")
    config_template = jinja2.Template(open(template_file).read())
    acl_rules = json.loads(config_template.render(acl_rules_template_file_args))['ACL_RULE']
    return format_acl_rules(acl_rules)


def format_acl_rules(ori_acl_rule_dict):
    """
    Update the acl rules dictionary to a new dictionary format
    :param ori_acl_rule_dict: the original acl rules dictionary
    :return: a formatted acl rules dictionary
        Example: ori_acl_rules:
            {'DATA_INGRESS_L3TEST|RULE_1':
                {'ETHER_TYPE': 2048,
                'PACKET_ACTION': 'FORWARD',
                'PRIORITY': '9999',
                'SRC_IP': '10.0.1.2/32'}
            }
            return:
            {'RULE_1':
                {'Match': {'ETHER_TYPE': 2048, 'SRC_IP': '10.0.1.2/32'},
                'Action': 'FORWARD',
                'Priority': '9999'}
            }
    """
    updated_acl_rule_dict = {}
    rule_key_map = {'PRIORITY': 'Priority', 'PACKET_ACTION': 'Action'}
    for acl_rule_name, acl_rule in ori_acl_rule_dict.items():
        acl_rule_name = acl_rule_name.split('|')[1]
        updated_acl_rule = {"Match": {}}
        for key, value in acl_rule.items():
            if key in rule_key_map:
                updated_acl_rule[rule_key_map[key]] = value
            else:
                updated_acl_rule["Match"][key] = value
        updated_acl_rule_dict[acl_rule_name] = updated_acl_rule
    return updated_acl_rule_dict


def verify_acl_traffic(topology_obj, dut_engine, traffic_params, rule_name, is_match, expect_received):
    """
    Verify the acl rule work successfully with sending traffic.
    :param topology_obj: topology_obj fixture
    :param dut_engine: dut engine ssh object
    :param traffic_params: a dictionary contains all information needed to send traffic
    :param rule_name: rule name
    :param is_match: True if the traffic is expected to match the acl rule, False if the traffic is expected to
                     not match any of the acl rules.
    :param expect_received: True if the traffic is expected to be received on the dst port, else False
    """
    traffic_type = traffic_params['traffic_type']
    table_name = traffic_params['table_name']
    cli_obj = topology_obj.players['dut']['cli']
    if traffic_type == 'udp':
        pkt, pkt_filter = generate_udp_pkt(traffic_params)
    elif traffic_type == 'icmp':
        pkt, pkt_filter = generate_icmp_pkt(traffic_params)
    else:
        pkt, pkt_filter = generate_tcp_pkt(traffic_params)
    logger.info(f"The pkt to be sent is: {pkt}")
    cli_obj.acl.clear_acl_counters(table_name)
    logger.info("dump the flex acl with sx_api_flex_acl_dump before sending traffic")
    dut_engine.run_cmd("docker exec -i syncd bash -c 'sx_api_flex_acl_dump.py'")
    send_recv_traffic(topology_obj, traffic_params, pkt, pkt_filter, expect_received)
    logger.info("dump the flex acl with sx_api_flex_acl_dump after traffic sent")
    dut_engine.run_cmd("docker exec -i syncd bash -c 'sx_api_flex_acl_dump.py'")
    acl_rule_expect_match_count = ACLConstants.PKT_COUNT if is_match else 0
    retry_call(verify_acl_rule_count,
               fargs=[cli_obj, table_name, rule_name, acl_rule_expect_match_count],
               tries=10,
               delay=2,
               logger=logger)


def generate_tcp_pkt(traffic_params, sport=0x4321, dport=0x51):
    """
    Generate the tcp pkt content
    :param traffic_params: dictionary of the params which is used to generate the pkt
    :param sport: src port value for the tcp
    :param dport: dst port value for the tcp
    :return: pkt and the pkt filter
    """
    ip_pkt, ip_pkt_filter = generate_ip_pkt(traffic_params)
    pkt = f'{ip_pkt}/TCP(sport={sport}, dport={dport})'
    pkt_filter = f'{ip_pkt_filter} and tcp and tcp src port {sport} and tcp dst port {dport}'
    return pkt, pkt_filter


def generate_udp_pkt(traffic_params, sport=0x4321, dport=0x51):
    """
    Generate the udp pkt content
    :param traffic_params: dictionary of the params which is used to generate the pkt
    :param sport: src port value for the udp
    :param dport: dst port value for the udp
    :return: pkt and the pkt filter
    """
    ip_pkt, ip_pkt_filter = generate_ip_pkt(traffic_params)
    pkt = f'{ip_pkt}/UDP(sport={sport}, dport={dport})'
    pkt_filter = f'{ip_pkt_filter} and udp and udp src port {sport} and udp dst port {dport}'
    return pkt, pkt_filter


def generate_icmp_pkt(traffic_params):
    """
    Generate the icmp pkt content
    :param traffic_params: dictionary of the params which is used to generate the pkt
    :return: pkt and the pkt filter
    """
    icmp_type = 'ICMP' if traffic_params['ip_version'] == 'ipv4' else 'ICMPv6EchoRequest'
    icmp_filter_type = 'icmp' if traffic_params['ip_version'] == 'ipv4' else 'icmpv6'
    ip_pkt, ip_pkt_filter = generate_ip_pkt(traffic_params)
    pkt = f'{ip_pkt}/{icmp_type}()'
    pkt_filter = f'{ip_pkt_filter} and {icmp_filter_type}'
    return pkt, pkt_filter


def generate_ip_pkt(traffic_params):
    """
    Generate the ip pkt content
    :param traffic_params: dictionary of the params which is used to generate the pkt
    :return: ip pkt and the ip pkt filter
    """
    src_ip = traffic_params['src_ip']
    dst_ip = traffic_params['dst_ip']
    src_mac = traffic_params['src_mac']
    dst_mac = traffic_params['dst_mac']
    ip_pkt_filter = f'src {src_ip} and dst {dst_ip}'
    ip_type = 'IP' if traffic_params['ip_version'] == 'ipv4' else 'IPv6'
    ip_pkt = f'Ether(src="{src_mac}", dst="{dst_mac}")/{ip_type}(src="{src_ip}", dst="{dst_ip}")'
    return ip_pkt, ip_pkt_filter


def send_recv_traffic(topology_obj, traffic_params, pkt, pkt_filter, expect_received):
    """
    Send and verify traffic with filter template specified.
    :param topology_obj: topology_obj fixture object
    :param traffic_params: the traffic params which will be used when send traffic.
    :param pkt: the pkt content that will send.
    :param pkt_filter: the filter template which will be used on the dst port.
    :param expect_received: True if expect the pkt can be received on the dst port, else False
    :return:None
    """
    send_pkt_count = ACLConstants.PKT_COUNT
    expect_recv_pkt_count = ACLConstants.PKT_COUNT if expect_received else 0
    validation_r = {'sender': traffic_params['sender'],
                    'send_args': {'interface': traffic_params['src_port'],
                                  'packets': pkt, 'count': send_pkt_count},
                    'receivers':
                        [
                            {'receiver': traffic_params['receiver'],
                             'receive_args': {'interface': traffic_params['dst_port'],
                                              'filter': pkt_filter, 'count': expect_recv_pkt_count}}
    ]
    }
    scapy_r = ScapyChecker(topology_obj.players, validation_r)
    scapy_r.run_validation()


def verify_acl_rule_count(cli_obj, table_name, rule_name, expected_count):
    """
    Verify the acl rule count get from the cli command is as expected, if the rule_name is given,
     then verify the pkt count  in specified acl rule equal to expected_count, if rule_name is empty,
     then verify all the acl rules have same pkt count as expected_count, and expected_count is 0.
    :param cli_obj: dut cli_obj object
    :param table_name: ACL table name
    :param rule_name: acl rule name
    :param expected_count: expected match packet count
    :return: None
    """
    acl_rules = cli_obj.acl.show_and_parse_acl_rules_counters(table_name)
    acl_pkt_count = 0
    for acl_rule in acl_rules[table_name]:
        if rule_name:
            if acl_rule['RULE NAME'] == rule_name:
                acl_pkt_count = acl_rule['PACKETS COUNT']
                break
        else:
            # if the rule_name is empty, then the traffic should not match any acl rules
            acl_pkt_count = acl_rule['PACKETS COUNT']
            assert expected_count == int(acl_pkt_count)
    assert expected_count == int(acl_pkt_count), f"Expected count is {expected_count}, acl counter is {acl_pkt_count}"


def get_ip_addr_by_acl_rule_action_and_match_key(acl_rules_args, ip_address_type):
    """
    get the ip address from the ACLConstants
    :param acl_rules_args: acl_rules_args specified in ACLConstants, for example:
                                 {"acl_table_name": "DATA_INGRESS_L3TEST",
                                   "ether_type": "2048",
                                   "forward_src_ip_match": "10.0.1.2/32",
                                   "forward_dst_ip_match": "121.0.0.2/32",
                                   "drop_src_ip_match": "10.0.1.6/32",
                                   "drop_dst_ip_match": "123.0.0.2/32",
                                   "unmatch_dst_ip": "125.0.0.2/32",
                                   "unused_src_ip": "10.0.1.11/32",
                                   "unused_dst_ip": "192.168.0.1/32"
                                   },
    :param ip_address_type: specify the ip address type, which kind of ip address should return, for example:
                            forward_src_ip_match
    :return: ip address
    """
    return acl_rules_args[ip_address_type].split('/')[0]
