import allure
import logging
import pytest
import time
import os
import json
import copy
import tempfile
import math
from jinja2 import Template

from retry.api import retry_call
from ngts.cli_util.sonic_docker_utils import SwssContainer
from ngts.tools.infra import update_sys_path_by_community_plugins_path

update_sys_path_by_community_plugins_path()
from plugins.loganalyzer.loganalyzer import LogAnalyzer  # noqa: E402


AVAILABLE_TOLERANCE = 0.02
MIN_RESOURCE_PERCENTAGE = 0.01
EXPECT_EXCEEDED = ".* THRESHOLD_EXCEEDED .*"
EXPECT_CLEAR = ".* THRESHOLD_CLEAR .*"
ACL_TABLE_NAME = 'DATAACL'

THR_VERIFY_CMDS = {
    "used": [
        ("exceeded_used",
            "bash -c \"crm config thresholds {{crm_cli_res}}  type used;\
            crm config thresholds {{crm_cli_res}} \
            low {{crm_used|int - 1}}; crm config thresholds {{crm_cli_res}} \
            high {{crm_used|int}}\""
         ),
        ("clear_used",
            "bash -c \"crm config thresholds {{crm_cli_res}} type used && \
            crm config thresholds {{crm_cli_res}} low {{crm_used|int}} && \
            crm config thresholds {{crm_cli_res}} high {{crm_used|int + 1}}\""
         )],
    "free": [
        ("exceeded_free",
            "bash -c \"crm config thresholds {{crm_cli_res}} type free && \
            crm config thresholds {{crm_cli_res}} low {{crm_avail|int - 1}} && \
            crm config thresholds {{crm_cli_res}} high {{crm_avail|int}}\""
         ),
        ("clear_free",
            "bash -c \"crm config thresholds {{crm_cli_res}} type free && \
            crm config thresholds {{crm_cli_res}} low {{crm_avail|int}} && \
            crm config thresholds {{crm_cli_res}} high {{crm_avail|int + 1}}\""
         )],
    "percentage": [
        ("exceeded_percentage",
            "bash -c \"crm config thresholds {{crm_cli_res}} type percentage && \
            crm config thresholds {{crm_cli_res}} low {{th_lo|int}} && \
            crm config thresholds {{crm_cli_res}} high {{th_hi|int}}\""
         ),
        ("clear_percentage",
            "bash -c \"crm config thresholds {{crm_cli_res}} type percentage && \
            crm config thresholds {{crm_cli_res}} low {{th_lo|int}} && \
            crm config thresholds {{crm_cli_res}} high {{th_hi|int}}\""
         )]
}


logger = logging.getLogger()


TH_GENERATOR = None


def th_generator():
    """
    Context manager which generates threshold pairs one by one
    """
    global THR_VERIFY_CMDS
    keys = THR_VERIFY_CMDS.keys()

    while True:
        for key_id in keys:
            yield THR_VERIFY_CMDS[key_id]


def get_threshold_to_verify():
    """
    Return pair of threshold type to be verified.
    return: list of tuples which contains values from dictionary - THR_VERIFY_CMDS
    """
    global TH_GENERATOR
    if TH_GENERATOR is None:
        TH_GENERATOR = th_generator()

    return next(TH_GENERATOR)


def get_main_crm_stat(env, resource):
    """
    Get crm counters of first table from 'crm show resources all' command
    :param env: pytest fixture
    :param resource: CRM resource name. Supported CRM resources:
        ipv4_route, ipv6_route, ipv4_nexthop, ipv6_nexthop, ipv4_neighbor,
        ipv6_neighbor, nexthop_group_member, nexthop_group, fdb_entry
    """
    crm_resources_all = env.sonic_cli.crm.parse_resources_table()
    res = crm_resources_all['main_resources'][resource]
    return int(res['Used Count']), int(res['Available Count'])


def get_all_crm_stat(env):
    """
    Get crm counters of first table from 'crm show resources all' command
    :param env: pytest fixture
    """
    stat = {}
    crm_resources_all = env.sonic_cli.crm.parse_resources_table()
    for resource, value in crm_resources_all['main_resources'].items():
        stat[resource] = {"used": int(value['Used Count']), "available": int(value['Available Count'])}
    return stat


def get_required_minimum(total):
    return math.ceil(total * MIN_RESOURCE_PERCENTAGE)


def get_acl_crm_stat(env, resource):
    """
    Get crm counters of third table from 'crm show resources all' command
    :param env: pytest fixture
    :param resource: CRM resource name. Supported CRM resources:
        ipv4_route, ipv6_route, ipv4_nexthop, ipv6_nexthop, ipv4_neighbor,
        ipv6_neighbor, nexthop_group_member, nexthop_group, fdb_entry
    """
    crm_resource_acl = env.sonic_cli.crm.parse_resources_table()['table_resources']
    if not crm_resource_acl:
        return None

    assert len(crm_resource_acl) == 2, 'Expect 2 entries for ACL table'
    for item in crm_resource_acl:
        if item['Resource Name'] == resource:
            current_used = item['Used Count']
            current_available = item['Available Count']
            break
    else:
        raise Exception('Incorrect CRM resource name specified. Excepted {}. Provided - {}'.format(
            'acl_entry, acl_counter', resource)
        )

    return int(current_used), int(current_available)


def ensure_crm_acl_table_not_empty(env):
    """
    Verify that CRM ACL table is not empty
    """
    acl_res = "acl_entry"
    assert get_acl_crm_stat(env, acl_res) is not None, "CRM ACL table is empty"


def verify_counters(env, resource, used, used_sign, available=None):
    """
    Verifies used and available counters for specific CRM resource
    :param env: pytest fixture
    :param resource: CRM resource name. For example (ipv4_route, ipv4_nexthop, nexthop_group_member, etc.)
    :param used: expected value of used counter for specific 'res' CRM resource
    :param used_sign: comparison sign of used value. For example ('==', '>=', '<=')
    :param available: expected value of available counter for specific 'res' CRM resource. If None - not verified
    :param available_sign: comparison sign of available value. For example ('==', '>=', '<=')
    :return: Raise AssertionError if comparison does not match
    """
    if 'acl' in resource:
        current_used, current_available = get_acl_crm_stat(env, resource)
    else:
        current_used, current_available = get_main_crm_stat(env, resource)

    assert eval('{} {} {}'.format(current_used, used_sign, used)), \
        'Unexpected used count for \'{}\': expected \'{}\' {}; actual received - {}'.format(
            resource, used_sign, used, current_used
    )

    if available:
        low_treshold = available - int(available * AVAILABLE_TOLERANCE)
        high_treshold = available + int(available * AVAILABLE_TOLERANCE)
        assert low_treshold <= current_available <= high_treshold, \
            'Unexpected available count for \'{}\': expected range {}...{}; actual received - {}'.format(
                resource, low_treshold, high_treshold, current_available
            )


def apply_acl_config(env, entry_num=1):
    """
    Create acl rules defined in config file
    :param env: Test environment object
    :param entry_num: Number of entries required to be created in ACL rule
    """
    base_dir = os.path.dirname(os.path.realpath(__file__))
    acl_rules_file = 'acl.json'
    acl_rules_path = os.path.join(base_dir, acl_rules_file)
    dst_dir = '/tmp'

    env.dut_engine.run_cmd('mkdir -p {}'.format(dst_dir))

    # Create ACL table
    env.sonic_cli.acl.create_table(tbl_name=ACL_TABLE_NAME, tbl_type='L3',
                                   description='"{} table"'.format(ACL_TABLE_NAME), stage='ingress')

    if entry_num == 1:
        logger.info('Generating config for ACL rule, ACL table - {}'.format(ACL_TABLE_NAME))
        env.dut_engine.copy_file(source_file=acl_rules_path, dest_file=acl_rules_file, file_system=dst_dir,
                                 overwrite_file=True, verify_file=False)
    elif entry_num > 1:
        acl_config = json.loads(open(acl_rules_path).read())
        acl_entry_template = acl_config['acl']['acl-sets']['acl-set'][ACL_TABLE_NAME.lower()]['acl-entries']['acl-entry']['1']
        acl_entry_config = acl_config['acl']['acl-sets']['acl-set'][ACL_TABLE_NAME.lower()]['acl-entries']['acl-entry']
        for seq_id in range(2, entry_num + 2):
            acl_entry_config[str(seq_id)] = copy.deepcopy(acl_entry_template)
            acl_entry_config[str(seq_id)]['config']['sequence-id'] = seq_id

        with tempfile.NamedTemporaryFile(suffix='.json', prefix='acl_config', mode='w') as fp:
            json.dump(acl_config, fp)
            fp.flush()
            logger.info('Generating config for ACL rule, ACL table - {}'.format(ACL_TABLE_NAME))

            env.dut_engine.copy_file(source_file=fp.name, dest_file=acl_rules_file, file_system=dst_dir,
                                     overwrite_file=True, verify_file=False)
    else:
        raise Exception('Incorrect number of ACL entries specified - {}'.format(entry_num))

    logger.info("Applying ACL config on DUT")
    retry_call(env.sonic_cli.acl.apply_config, fargs=[os.path.join(dst_dir, acl_rules_file), True], tries=3, delay=1, logger=None)


def get_used_percent(crm_used, crm_available):
    """ Returns percentage of used entries """
    return crm_used * 100 / (crm_used + crm_available)


def verify_thresholds(env, test_name, **kwargs):
    """
    Verifies that WARNING message logged if there are any resources that exceeds a pre-defined threshold value.
    Verifies the following threshold parameters: percentage, actual used, actual free
    """
    loganalyzer = LogAnalyzer(ansible_host=env.duthost, marker_prefix=test_name)
    crm_avail = kwargs['crm_avail']

    # Used random selection of thresholds which should be verified, as full thresholds verification takes much time to verify
    th_buff = get_threshold_to_verify()

    if 'percentage' in th_buff[0][0] and 'nexthop group' in kwargs['crm_cli_res'] and 'mellanox' in env.platform_params.asic_type.lower():
        # TODO: Fix this. Temporal skip percentage verification for 'nexthop group' verification
        # Max supported ECMP group values is less then number of entries we need to configure
        # in order to test percentage threshold (Can't even reach 1 percent)
        # For test case used 'nexthop_group' need to be configured at least 1 percent from available
        th_buff = get_threshold_to_verify()

    for th_type_cmd_pair in th_buff:
        th_type, th_cmd = th_type_cmd_pair

        logger.info('Verifying CRM threshold \'{}\''.format(th_type))
        template = Template(th_cmd)
        if 'exceeded' in th_type:
            loganalyzer.expect_regex = [EXPECT_EXCEEDED]
        elif 'clear' in th_type:
            loganalyzer.expect_regex = [EXPECT_CLEAR]

        if 'percentage' in th_type:
            used_percent = get_used_percent(kwargs['crm_used'], crm_avail)
            if th_type == 'exceeded_percentage':
                if used_percent < 1:
                    pytest.skip('The used percentage for {} is {} and verification for exceeded_percentage is skipped'
                                .format(kwargs['crm_cli_res'], used_percent))
                kwargs['th_lo'] = used_percent - 1
                kwargs['th_hi'] = used_percent
                loganalyzer.expect_regex = [EXPECT_EXCEEDED]
            elif th_type == 'clear_percentage':
                if used_percent >= 100:
                    pytest.skip('The used percentage for {} is {} and verification for clear_percentage is skipped'
                                .format(kwargs['crm_cli_res'], used_percent))
                kwargs['th_lo'] = used_percent
                kwargs['th_hi'] = used_percent + 1
                loganalyzer.expect_regex = [EXPECT_CLEAR]
        elif 'exceeded_free' in th_type:
            kwargs['crm_avail'] = crm_avail - (crm_avail * AVAILABLE_TOLERANCE)
        elif 'clear_free' in th_type:
            kwargs['crm_avail'] = crm_avail + (crm_avail * AVAILABLE_TOLERANCE)
        cmd = template.render(**kwargs)

        with loganalyzer:
            env.dut_engine.run_cmd(cmd)
            # Make sure CRM counters updated
            time.sleep(env.MAX_CRM_UPDATE_TIME)


def get_full_stat(env):
    stats = {'ipv4_route': None,
             'ipv6_route': None,
             'ipv4_nexthop': None,
             'ipv6_nexthop': None,
             'ipv4_neighbor': None,
             'ipv6_neighbor': None,
             'nexthop_group_member': None,
             'nexthop_group': None,
             'fdb_entry': None,
             'acl_entry': None,
             'acl_counter': None
             }
    for resource in stats:
        if 'acl' in resource:
            used, available = get_acl_crm_stat(env, resource)
        else:
            used, available = get_main_crm_stat(env, resource)
        stats[resource] = {'used': used, 'available': available}
    return stats


def set_op_del(swss_cfg_lst):
    """
    Set 'OP' field to 'DEL' in swss config list for each of the element
    """
    buff = []
    for item in copy.deepcopy(swss_cfg_lst):
        item['OP'] = 'DEL'
        buff.append(item)
    return buff


def th_apply_neighbor_config(env, ip_ver, start_ip, vlan_iface):
    # IP neighbor and nexthop configuration
    # Used to calculate amount of expected neighbors
    _, ip_route_available = get_main_crm_stat(env, "ipv{}_route".format(ip_ver))
    # Required neighbors should be double of routes to create unique nexthop groups, so multiplication per 2 is used
    required_ip_neigh = get_required_minimum(ip_route_available) * 2
    neigh_cfg_add = env.sonic_cli.ip.generate_neighbors_cfg(
        required_ip_neigh, start_ip, vlan_iface, 'IPv{}'.format(ip_ver), 'SET'
    )
    SwssContainer.apply_config(env.dut_engine, neigh_cfg_add)

    with allure.step("Verify 'ipv{ip_ver}_neighbor' and 'ipv{ip_ver}_nexthop' counter incremented".format(ip_ver=ip_ver)):
        retry_call(
            verify_counters, fargs=[env, "ipv{}_neighbor".format(ip_ver), required_ip_neigh, '>='],
            tries=env.APPLY_CFG_MAX_UPDATE_TIME, delay=2, logger=None
        )

    return neigh_cfg_add


def th_apply_nexthop_group_member(env, ip_ver, start_ip, neigh_cfg_json):
    # IP route, nexthop_group and nexthop_group_member configuration
    nexthop_group_stat, _ = get_main_crm_stat(env, "nexthop_group")
    nexthop_group_member_stat, _ = get_main_crm_stat(env, "nexthop_group_member")
    # _, ip_route_available = get_main_crm_stat(env, "ipv{}_route".format(ip_ver))
    # required_ip_route = get_required_minimum(ip_route_available)
    required_ip_route = len(neigh_cfg_json) // 2
    nexthop_group_member_add = env.sonic_cli.ip.generate_routes_cfg_w_nexthop_group(
        required_ip_route, start_ip, neigh_cfg_json, "SET"
    )
    SwssContainer.apply_config(env.dut_engine, nexthop_group_member_add)

    with allure.step("Verify 'ipv{}_route' counter incremented".format(ip_ver)):
        retry_call(
            verify_counters, fargs=[env, "ipv{}_route".format(ip_ver), required_ip_route, '>='],
            tries=env.APPLY_CFG_MAX_UPDATE_TIME, delay=2, logger=None
        )
    with allure.step("Verify 'nexthop_group' counter incremented"):
        retry_call(
            verify_counters, fargs=[env, "nexthop_group", nexthop_group_stat + required_ip_route, '>='],
            tries=env.APPLY_CFG_MAX_UPDATE_TIME, delay=2, logger=None
        )
    with allure.step("Verify 'nexthop_group_member' counter incremented"):
        retry_call(
            verify_counters, fargs=[env, 'nexthop_group_member', (nexthop_group_member_stat + (required_ip_route * 2)), '>='],
            tries=env.APPLY_CFG_MAX_UPDATE_TIME, delay=2, logger=None
        )

    return nexthop_group_member_add


def th_apply_fdb_config(env, fdb_entry_res):
    fdb_entry_res = "fdb_entry"
    _, fdb_entry_available = get_main_crm_stat(env, fdb_entry_res)
    required_fdb_entries = get_required_minimum(fdb_entry_available)
    vlan_id = int(env.vlan_iface_40.replace('Vlan', ''))

    fdb_conf_set = env.sonic_cli.mac.generate_fdb_config(required_fdb_entries, vlan_id, env.dut_ha_2, 'SET')
    SwssContainer.apply_config(env.dut_engine, fdb_conf_set)

    with allure.step('Verify \'{}\' counter incremented'.format(fdb_entry_res)):
        retry_call(
            verify_counters, fargs=[env, fdb_entry_res, required_fdb_entries, '>='],
            tries=env.APPLY_CFG_MAX_UPDATE_TIME, delay=3, logger=None
        )

    return fdb_conf_set
