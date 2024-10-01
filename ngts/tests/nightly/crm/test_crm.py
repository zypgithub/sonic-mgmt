import allure
import pytest
import time

from retry.api import retry_call
from ngts.cli_util.sonic_docker_utils import SwssContainer
from crm_helper import (
    ACL_TABLE_NAME,
)
from crm_helper import (
    get_main_crm_stat,
    get_required_minimum,
    get_acl_crm_stat,
    ensure_crm_acl_table_not_empty,
    verify_counters,
    apply_acl_config,
    verify_thresholds,
    set_op_del,
    th_apply_neighbor_config,
    th_apply_nexthop_group_member,
    th_apply_fdb_config,
)

IPV4_NEIGHBOR_LIST = ["2.2.2.{}".format(i) for i in range(10)]
IPV6_NEIGHBOR_LIST = ["2001::{}".format(i) for i in range(10)]
NEIGH_MAC_ADDR_LIST = ["11:22:33:44:55:6{}".format(i) for i in range(10)]


@pytest.mark.build
@pytest.mark.push_gate
@pytest.mark.parametrize('ip_ver,dst,mask', [('4', '2.2.2.0', 24), ('6', '2001::', 126)], ids=['ipv4', 'ipv6'])
@allure.title('Test CRM route counters')
def test_crm_route(env, cleanup, ip_ver, dst, mask):
    """
    Test doing verification of used and available CRM counters for the following resources:
    ipv4_route
    ipv6_route
    """

    vlan_iface = env.vlan_iface_40
    crm_resource = 'ipv{}_route'.format(ip_ver)
    used, available = get_main_crm_stat(env, crm_resource)

    with allure.step('Add route: {}/{} {}'.format(dst, mask, vlan_iface)):
        env.sonic_cli.route.add_route(dst, vlan_iface, mask)

    cleanup.append((env.sonic_cli.route.del_route, dst, vlan_iface, mask))
    with allure.step('Verify CRM {} counters'.format(crm_resource)):
        retry_call(
            verify_counters, fargs=[env, crm_resource, used + 1, '==', available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    cleanup.pop()

    with allure.step('Remove route: {}/{} {}'.format(dst, mask, vlan_iface)):
        env.sonic_cli.route.del_route(dst, vlan_iface, mask)

    with allure.step('Verify CRM {} counters'.format(crm_resource)):
        retry_call(
            verify_counters, fargs=[env, crm_resource, used, '==', available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )


@pytest.mark.build
@pytest.mark.push_gate
@pytest.mark.parametrize("ip_ver,neighbor_list,neigh_mac_addr_list", [("4", IPV4_NEIGHBOR_LIST, NEIGH_MAC_ADDR_LIST),
                                                                      ("6", IPV6_NEIGHBOR_LIST, NEIGH_MAC_ADDR_LIST)])
@allure.title('Test CRM neighbor and nexthop counters')
def test_crm_neighbor_and_nexthop(env, cleanup, ip_ver, neighbor_list, neigh_mac_addr_list):
    """
    Test doing verification of used and available CRM counters for the following resources:
    ipv4_nexthop
    ipv6_nexthop
    ipv4_neighbor
    ipv6_neighbor
    """
    vlan_iface = env.vlan_iface_40
    nexthop_resource = "ipv{ip_ver}_nexthop".format(ip_ver=ip_ver)
    neighbor_resource = "ipv{ip_ver}_neighbor".format(ip_ver=ip_ver)

    nexthop_used, nexthop_available = get_main_crm_stat(env, nexthop_resource)
    neighbor_used, neighbor_available = get_main_crm_stat(env, neighbor_resource)

    with allure.step('Add {} neighbors to {}'.format(len(neighbor_list), vlan_iface)):
        env.sonic_cli.ip.add_ip_neigh_list(neighbor_list, neigh_mac_addr_list, vlan_iface)

    cleanup.append((env.sonic_cli.ip.del_ip_neigh_list, neighbor_list, neigh_mac_addr_list, vlan_iface))
    # check that all ip neighbors were added
    with allure.step('Verify CRM {} counters'.format(nexthop_resource)):
        retry_call(
            verify_counters, fargs=[env, nexthop_resource, nexthop_used + len(neighbor_list), '>=', nexthop_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    with allure.step('Verify CRM {} counters'.format(neighbor_resource)):
        retry_call(
            verify_counters, fargs=[env, neighbor_resource, neighbor_used + len(neighbor_list), '>=', neighbor_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    cleanup.pop()

    with allure.step('Remove {} neighbors from {}'.format(len(neighbor_list), vlan_iface)):
        env.sonic_cli.ip.del_ip_neigh_list(neighbor_list, neigh_mac_addr_list, vlan_iface)
    # Check that at least (len(neighbor_list)-2) ip neighbors were deleted.
    # In some cases an unexpected background traffic might cause the addition of unexpected neighbors.
    with allure.step('Verify CRM {} counters'.format(nexthop_resource)):
        retry_call(
            verify_counters, fargs=[env, nexthop_resource, nexthop_used + 2, '<=', nexthop_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    with allure.step('Verify CRM {} counters'.format(neighbor_resource)):
        retry_call(
            verify_counters, fargs=[env, neighbor_resource, neighbor_used + 2, '<=', neighbor_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )


@pytest.mark.build
@pytest.mark.push_gate
@allure.title('Test CRM nexthop and nexthop group counters')
def test_crm_nexthop_group_and_member(env, cleanup):
    """
    Test doing verification of used and available CRM counters for the following resources:
    nexthop_group_member
    nexthop_group
    """
    dst_ip = env.dst_ip
    mask = env.mask
    neigh_69 = env.ip_neigh_69
    neigh_40 = env.ip_neigh_40
    mac_addr_templ = '11:22:33:44:55:{}'
    vlan_69 = env.vlan_iface_69
    vlan_40 = env.vlan_iface_40
    vlan_id_69 = env.vlan_iface_69.replace('Vlan', '')
    vlan_id_40 = env.vlan_iface_40.replace('Vlan', '')
    group_member_res = 'nexthop_group_member'
    group_res = 'nexthop_group'

    group_member_used, group_member_available = get_main_crm_stat(env, group_member_res)
    group_used, group_available = get_main_crm_stat(env, group_res)

    with allure.step('Add neighbors: {} {}'.format(neigh_69, neigh_40)):
        env.sonic_cli.ip.add_ip_neigh(neigh_69, mac_addr_templ.format(vlan_id_69), vlan_69)
        env.sonic_cli.ip.add_ip_neigh(neigh_40, mac_addr_templ.format(vlan_id_40), vlan_40)
    cleanup.append((env.sonic_cli.ip.del_ip_neigh, neigh_69, mac_addr_templ.format(vlan_id_69),
                    vlan_69))
    cleanup.append((env.sonic_cli.ip.del_ip_neigh, neigh_40, mac_addr_templ.format(vlan_id_40),
                    vlan_40))

    with allure.step('Add route: {}/{} {}'.format(dst_ip, mask, neigh_69)):
        env.sonic_cli.route.add_route(dst_ip, neigh_69, mask)
    with allure.step('Add route: {}/{} {}'.format(dst_ip, mask, neigh_40)):
        env.sonic_cli.route.add_route(dst_ip, neigh_40, mask)

    cleanup.append((env.sonic_cli.route.del_route, dst_ip, neigh_69, mask))
    cleanup.append((env.sonic_cli.route.del_route, dst_ip, neigh_40, mask))

    with allure.step('Verify CRM nexthop_group_member counters'):
        retry_call(
            verify_counters, fargs=[env, group_member_res, group_member_used + 2, '==', group_member_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    with allure.step('Verify CRM nexthop_group counters'):
        retry_call(
            verify_counters, fargs=[env, group_res, group_used + 1, '==', group_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )

    with allure.step('Delete routes'.format(dst_ip, mask, neigh_40)):
        env.sonic_cli.route.del_route(dst_ip, neigh_69, mask)
        env.sonic_cli.route.del_route(dst_ip, neigh_40, mask)

    cleanup.clear()

    with allure.step('Verify CRM nexthop_group_member counters'):
        retry_call(
            verify_counters, fargs=[env, group_member_res, group_member_used, '==', group_member_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    with allure.step('Verify CRM nexthop_group counters'):
        retry_call(
            verify_counters, fargs=[env, group_res, group_used, '==', group_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )


@pytest.mark.build
@pytest.mark.push_gate
@allure.title('Test CRM FDB counters')
def test_crm_fdb_entry(env, cleanup, interfaces):
    """
    Test doing verification of used and available CRM counters for the following resources:
    fdb_entry
    """
    vlan_id = int(env.vlan_iface_40.replace('Vlan', ''))
    iface = interfaces.dut_ha_2
    fdb_resource = 'fdb_entry'
    fdb_clear_cmd = 'fdbclear'

    fdb_used, fdb_available = get_main_crm_stat(env, fdb_resource)
    with allure.step('Adding FDB config'):
        fdb_conf_set = env.sonic_cli.mac.generate_fdb_config(1, vlan_id, iface, "SET")
        SwssContainer.apply_config(env.dut_engine, fdb_conf_set)
    cleanup.append((env.dut_engine.run_cmd, fdb_clear_cmd))

    with allure.step('Verify CRM {} counters'.format(fdb_resource)):
        retry_call(
            verify_counters, fargs=[env, fdb_resource, fdb_used + 1, '==', fdb_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )

    with allure.step('Removing FDB config'):
        fdb_conf_del = env.sonic_cli.mac.generate_fdb_config(1, vlan_id, iface, "DEL")
        SwssContainer.apply_config(env.dut_engine, fdb_conf_del)

    cleanup.pop()

    with allure.step('Verify CRM {} counters'.format(fdb_resource)):
        retry_call(
            verify_counters, fargs=[env, fdb_resource, fdb_used, '==', fdb_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )


@pytest.mark.build
@pytest.mark.push_gate
@allure.title('Test CRM ACL counters')
def test_crm_acl(env, cleanup):
    """
    Test doing verification of used and available CRM counters for the following resources:
    acl_entry
    acl_counter
    """
    acl_entry_resource = 'acl_entry'
    acl_counter_resource = 'acl_counter'

    with allure.step('Adding basic ACL config'):
        apply_acl_config(env, entry_num=1)
    cleanup.append((env.sonic_cli.acl.delete_config,))

    with allure.step('Wait until CRM ACL table will be created'):
        retry_call(
            ensure_crm_acl_table_not_empty, fargs=[env, ], tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )

    acl_entry_used, acl_entry_available = get_acl_crm_stat(env, acl_entry_resource)
    acl_counter_used, acl_counter_available = get_acl_crm_stat(env, acl_counter_resource)

    with allure.step('Add one entry to ACL config'):
        apply_acl_config(env, entry_num=2)

    with allure.step('Verify CRM {} counters'.format(acl_entry_resource)):
        retry_call(
            verify_counters, fargs=[env, acl_entry_resource, acl_entry_used + 2, '==', acl_entry_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    with allure.step('Verify CRM {} counters'.format(acl_counter_resource)):
        retry_call(
            verify_counters, fargs=[env, acl_counter_resource, acl_counter_used + 2, '==', acl_counter_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )

    with allure.step('Remove one entry from ACL config'):
        apply_acl_config(env, entry_num=1)

    with allure.step('Verify CRM {} counters'.format(acl_entry_resource)):
        retry_call(
            verify_counters, fargs=[env, acl_entry_resource, acl_entry_used, '==', acl_entry_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    with allure.step('Verify CRM {} counters'.format(acl_counter_resource)):
        retry_call(
            verify_counters, fargs=[env, acl_counter_resource, acl_counter_used, '==', acl_counter_available],
            tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )
    cleanup.append((env.sonic_cli.acl.delete_config,))
    cleanup.append((env.sonic_cli.acl.remove_table, ACL_TABLE_NAME))


@pytest.mark.parametrize('ip_ver,start_ip', [('4', '2.2.2.0'), ('6', '2001::')], ids=['ipv4', 'ipv6'])
@pytest.mark.parametrize('disable_rsyslog_ratelimit', ['swss'], indirect=True)
@pytest.mark.disable_loganalyzer
@allure.title('Test CRM thresholds')
def test_crm_thresholds_neighbors(env, cleanup, map_res_to_thr, thresholds_cleanup,
                                  disable_rsyslog_ratelimit, ip_ver, start_ip):
    # Test name used for loganalyzer marker
    test_name = 'test_crm_thresholds'

    with allure.step("Generate and apply neighbors config"):
        # IP neighbor and nexthop configuration
        # Used to calculate amount of expected neighbors
        neigh_cfg_add = th_apply_neighbor_config(env, ip_ver, start_ip, env.vlan_iface_40)
        neigh_cfg_del = set_op_del(neigh_cfg_add)
        cleanup.append((SwssContainer.apply_config, env.dut_engine, neigh_cfg_del))
        cleanup.append((time.sleep, env.MAX_CRM_UPDATE_TIME))

    neigh_used, neigh_available = get_main_crm_stat(env, "ipv{}_neighbor".format(ip_ver))
    with allure.step("Verify thresholds {}".format("ipv{}_neighbor".format(ip_ver))):
        verify_thresholds(env,
                          test_name,
                          crm_cli_res=map_res_to_thr["ipv{}_neighbor".format(ip_ver)],
                          crm_used=neigh_used,
                          crm_avail=neigh_available
                          )


@pytest.mark.parametrize('ip_ver,start_ip', [('4', '2.2.2.0'), ('6', '2001::')], ids=['ipv4', 'ipv6'])
@pytest.mark.parametrize('disable_rsyslog_ratelimit', ['swss'], indirect=True)
@pytest.mark.disable_loganalyzer
@allure.title('Test CRM thresholds nexthop')
def test_crm_thresholds_nexthop(env, cleanup, map_res_to_thr, thresholds_cleanup,
                                disable_rsyslog_ratelimit, ip_ver, start_ip):
    nexthop_group_res = 'nexthop_group'
    nexthop_group_member_res = 'nexthop_group_member'
    # Test name used for loganalyzer marker
    test_name = 'test_crm_thresholds_nexthop'
    with allure.step("Generate and apply nexthop and nexthop group members config"):
        neigh_cfg_add = th_apply_neighbor_config(env, ip_ver, start_ip, env.vlan_iface_40)
        neigh_cfg_del = set_op_del(neigh_cfg_add)
        cleanup.append((SwssContainer.apply_config, env.dut_engine, neigh_cfg_del))

        nexthop_group_member_add = th_apply_nexthop_group_member(env, ip_ver, start_ip, neigh_cfg_add)
        nexthop_group_member_del = set_op_del(nexthop_group_member_add)
        cleanup.append((SwssContainer.apply_config, env.dut_engine, nexthop_group_member_del))

    route_used, route_available = get_main_crm_stat(env, "ipv{}_route".format(ip_ver))
    with allure.step("Verify thresholds {}".format('ipv{}_route'.format(ip_ver))):
        verify_thresholds(env,
                          test_name,
                          crm_cli_res=map_res_to_thr['ipv{}_route'.format(ip_ver)],
                          crm_used=route_used,
                          crm_avail=route_available
                          )

    nexthop_group_used, nexthop_group_available = get_main_crm_stat(env, nexthop_group_res)
    with allure.step("Verify thresholds {}".format(nexthop_group_res)):
        verify_thresholds(env,
                          test_name,
                          crm_cli_res=map_res_to_thr[nexthop_group_res],
                          crm_used=nexthop_group_used,
                          crm_avail=nexthop_group_available
                          )

    nexthop_group_member_used, nexthop_group_member_available = get_main_crm_stat(env, nexthop_group_member_res)
    with allure.step("Verify thresholds {}".format(nexthop_group_member_res)):
        verify_thresholds(env,
                          test_name,
                          crm_cli_res=map_res_to_thr[nexthop_group_member_res],
                          crm_used=nexthop_group_member_used,
                          crm_avail=nexthop_group_member_available
                          )


@pytest.mark.parametrize('disable_rsyslog_ratelimit', ['swss'], indirect=True)
@pytest.mark.disable_loganalyzer
@allure.title('Test CRM thresholds FDB')
def test_crm_thresholds_fdb(env, cleanup, map_res_to_thr, thresholds_cleanup,
                            disable_rsyslog_ratelimit):
    # Test name used for loganalyzer marker
    test_name = 'test_crm_thresholds_fdb'
    fdb_entry_res = "fdb_entry"
    fdb_conf_set = th_apply_fdb_config(env, fdb_entry_res)
    fdb_conf_del = set_op_del(fdb_conf_set)
    cleanup.append((SwssContainer.apply_config, env.dut_engine, fdb_conf_del))

    fdb_used, fdb_available = get_main_crm_stat(env, fdb_entry_res)
    with allure.step("Verify thresholds {}".format(fdb_entry_res)):
        verify_thresholds(env,
                          test_name,
                          crm_cli_res=map_res_to_thr[fdb_entry_res],
                          crm_used=fdb_used,
                          crm_avail=fdb_available
                          )


@pytest.mark.parametrize('disable_rsyslog_ratelimit', ['swss'], indirect=True)
@pytest.mark.disable_loganalyzer
@allure.title('Test CRM thresholds ACL')
def test_crm_thresholds_acl(env, cleanup, map_res_to_thr, thresholds_cleanup,
                            disable_rsyslog_ratelimit):
    # Test name used for loganalyzer marker
    test_name = 'test_crm_thresholds_acl'
    acl_entry_resource = 'acl_entry'
    acl_counter_resource = 'acl_counter'

    # Create ACL table to be able to read available resources
    with allure.step("Apply basic ACL config"):
        apply_acl_config(env, entry_num=1)
    with allure.step('Wait until CRM ACL table will be created'):
        retry_call(
            ensure_crm_acl_table_not_empty, fargs=[env, ], tries=env.MAX_CRM_UPDATE_TIME, delay=1, logger=None
        )

    _, acl_entry_available = get_acl_crm_stat(env, acl_entry_resource)
    _, acl_counter_available = get_acl_crm_stat(env, acl_counter_resource)
    max_from_acl_available = acl_entry_available if acl_entry_available > acl_counter_available else acl_counter_available
    required_acl_entries = get_required_minimum(max_from_acl_available)

    with allure.step("Create ACL config with {} entries".format(required_acl_entries)):
        apply_acl_config(env, entry_num=required_acl_entries)
        cleanup.append((env.sonic_cli.acl.delete_config,))
        cleanup.append((env.sonic_cli.acl.remove_table, ACL_TABLE_NAME))

    with allure.step("Verify 'ACL' counters incremented"):
        retry_call(
            verify_counters, fargs=[env, acl_entry_resource, required_acl_entries, '>='],
            tries=env.APPLY_CFG_MAX_UPDATE_TIME, delay=2, logger=None
        )
        retry_call(
            verify_counters, fargs=[env, acl_counter_resource, required_acl_entries, '>='],
            tries=env.APPLY_CFG_MAX_UPDATE_TIME, delay=2, logger=None
        )

    acl_used, acl_available = get_acl_crm_stat(env, acl_entry_resource)
    with allure.step("Verify thresholds {}".format(acl_entry_resource)):
        verify_thresholds(env,
                          test_name,
                          crm_cli_res=map_res_to_thr[acl_entry_resource],
                          crm_used=acl_used,
                          crm_avail=acl_available
                          )
    acl_used, acl_available = get_acl_crm_stat(env, acl_counter_resource)
    with allure.step("Verify thresholds {}".format(acl_counter_resource)):
        verify_thresholds(env,
                          test_name,
                          crm_cli_res=map_res_to_thr[acl_counter_resource],
                          crm_used=acl_used,
                          crm_avail=acl_available
                          )
