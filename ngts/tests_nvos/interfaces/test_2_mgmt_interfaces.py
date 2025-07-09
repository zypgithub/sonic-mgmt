import pytest
from retry import retry
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure
from scapy.layers.inet import IP, ICMP
from scapy.all import *
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.HostMethods import HostMethods
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst, AclConsts, ApiType
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive

logger = logging.getLogger()


RULE_CONFIG_FUNCTION = {
    AclConsts.ACTION: lambda rule_id_obj, param: rule_id_obj.action.set(param),
    AclConsts.ACTION_LOG_PREFIX: lambda rule_id_obj, param: rule_id_obj.action.log.set_log_prefix(param),
    AclConsts.REMARK: lambda rule_id_obj, param: rule_id_obj.set_remark(param),

    AclConsts.TCP_SOURCE_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.source_port.set(param),
    AclConsts.UDP_SOURCE_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.udp.source_port.set(param),
    AclConsts.TCP_DEST_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.dest_port.set(param),
    AclConsts.UDP_DEST_PORT: lambda rule_id_obj, param: rule_id_obj.match.ip.udp.dest_port.set(param),
    AclConsts.FRAGMENT: lambda rule_id_obj, param: rule_id_obj.match.ip.set_fragment(),
    AclConsts.ECN_FLAGS: lambda rule_id_obj, param: rule_id_obj.match.ip.ecn.flags.set(param),
    AclConsts.ECN_IP_ECT: lambda rule_id_obj, param: rule_id_obj.match.ip.ecn.set_ecn_ip_ect(param),
    AclConsts.TCP_FLAGS: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.flags.set(param),
    AclConsts.TCP_MASK: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.mask.set(param),
    AclConsts.TCP_STATE: lambda rule_id_obj, param: rule_id_obj.match.ip.state.set(param),
    AclConsts.MSS: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.set_mss(param),
    AclConsts.ALL_MSS_EXCEPT: lambda rule_id_obj, param: rule_id_obj.match.ip.tcp.set_all_mss_except(param),
    AclConsts.SOURCE_IP: lambda rule_id_obj, param: rule_id_obj.match.ip.set_source_ip(param),
    AclConsts.DEST_IP: lambda rule_id_obj, param: rule_id_obj.match.ip.set_dest_ip(param),
    AclConsts.ICMP_TYPE: lambda rule_id_obj, param: rule_id_obj.match.ip.set_icmp_type(param),
    AclConsts.ICMPV6_TYPE: lambda rule_id_obj, param: rule_id_obj.match.ip.set_icmpv6_type(param),
    AclConsts.IP_PROTOCOL: lambda rule_id_obj, param: rule_id_obj.match.ip.set_protocol(param),
    AclConsts.RECENT_LIST_NAME: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.set_name(param),
    AclConsts.RECENT_LIST_UPDATE: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.set_update_interval(param),
    AclConsts.RECENT_LIST_HIT: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.set_hit_count(param),
    AclConsts.RECENT_LIST_ACTION: lambda rule_id_obj, param: rule_id_obj.match.ip.recent_list.set_action(param),
    AclConsts.HASHLIMIT_NAME: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_name(param),
    AclConsts.HASHLIMIT_RATE: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_rate_limit(param),
    AclConsts.HASHLIMIT_BURST: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_burst(param),
    AclConsts.HASHLIMIT_MODE: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_mode(param),
    AclConsts.HASHLIMIT_EXPIRE: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_expire(param),
    AclConsts.HASHLIMIT_DEST_MASK: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_destination_mask(param),
    AclConsts.HASHLIMIT_SRC_MASK: lambda rule_id_obj, param: rule_id_obj.match.ip.hashlimit.set_source_mask(param),

    AclConsts.SOURCE_MAC: None,
    AclConsts.SOURCE_MAC_MASK: None,
    AclConsts.DEST_MAC: None,
    AclConsts.DEST_MAC_MASK: None,
    AclConsts.MAC_PROTOCOL: None
}


@pytest.mark.system
def test_2_mgmt_snmp(engines, topology_obj):
    """
    Test flow:
        1. Enable snmp
        3. Check default values after enable
        4. Snmpget for both mgmt interfaces ip
        5. Unset
    """
    skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
    system = System(None)
    host_engine = engines.ha
    dut_setup_specific_attributes: Dict[str, str] = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']
    setup_mgmt_ips = [dut_setup_specific_attributes['ip_address'], dut_setup_specific_attributes['ip_address_2']]
    dhcp_hostname = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['dhcp_hostname']
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut, state=NvosConst.ENABLED, readonly_community='qwerty12',
                                      listening_address='all')
        HostMethods.wait_for_snmp_is_running(system)

    with allure.step('Verify fields and values after snmp enabled'):
        listening_address_output = OutputParsingTool.parse_json_str_to_dictionary(
            system.snmp_server.listening_address.show()).get_returned_value()
        ValidationTool.compare_values(listening_address_output, SystemConsts.SNMP_ENABLED_DEFAULT_LISTENING_ADDRESS).verify_result()

    with allure.step("Check snmpget with listening on 2 mgmt interfaces ip address"):
        for ip in setup_mgmt_ips:
            host_output = HostMethods.host_snmp_get(host_engine, ip)
            assert dhcp_hostname in host_output, 'snmp get with wrong port returned output'

    with allure.step("Unset snmp"):
        system.snmp_server.unset(apply=True).verify_result()
        HostMethods.wait_for_snmp_is_running(system, SystemConsts.SNMP_DEFAULT_STATE)


@pytest.mark.ib
@pytest.mark.simx
def test_2_mgmt_dhcp_hostname(engines, topology_obj, serial_engine, devices):
    """
    Verify switch receive hostname by dhcp

    flow:
    1. Disable 2 mgmt interfaces
    2. Set hostname to the system
    3. Enable back mgmt interface
    4. Verify it receive hostname by mgmt port
    """
    mgmt_ports = devices.dut.get_mgmt_ports()
    system = System()
    dhcp_hostname = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['dhcp_hostname']
    try:
        with allure.step('Disable 2 mgmt interfaces'):
            for mgmt_port in mgmt_ports:
                mgmt_port_obj = Port(mgmt_port)
                mgmt_port_obj.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True,
                                                       ask_for_confirmation=True,
                                                       dut_engine=serial_engine).verify_result(True)
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)

        with allure.step('Set hostname'):
            serial_engine.serial_engine.sendline(f"nv set system hostname {SystemConsts.HOSTNAME}")
            serial_engine.serial_engine.sendline("nv config apply --assume-yes")
            serial_engine.serial_engine.expect("applied", timeout=120)

        with allure.step('Enable mgmt ports'):
            for mgmt_port in mgmt_ports:
                mgmt_port_obj = Port(mgmt_port)
                mgmt_port_obj.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                                                       ask_for_confirmation=True,
                                                       dut_engine=serial_engine)
            check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port, tries=15, delay=2)
    finally:
        with allure.step('Check hostname received by dhcp'):
            system.unset(op_param=SystemConsts.HOSTNAME, apply=True, ask_for_confirmation=True)
            wait_for_hostname_changed(system, dhcp_hostname)


@pytest.mark.acl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_2_mgmt_acl(engines, test_api):
    """
    Validate acl rules will apply to mgmt port
    1. config an ACL with icmp deny rule
    2. send packet
    3. unset
    """
    TestToolkit.tested_api = test_api
    try:
        with allure.step("Define ACL with icmp deny rule"):

            with allure.step("Define ACL"):
                acl = Acl()
                acl_id = "AA_TEST_ACL1"
                acl.set(acl_id).verify_result()
                acl_id_obj = acl.acl_id[acl_id]
                acl_id_obj.set(AclConsts.TYPE, 'ipv4').verify_result()

            with allure.step("Config icmp deny rule and send ping"):
                rule_dict = {AclConsts.ACTION: AclConsts.DENY, AclConsts.SOURCE_IP: 'ANY',
                             AclConsts.IP_PROTOCOL: 'icmp',
                             AclConsts.ICMP_TYPE: 'echo-request'}
                rule_id_1 = '1'
                config_rule(engines.dut, acl_id_obj, rule_id_1, rule_dict)
                ping_packet = IP(dst=engines.dut.ip) / ICMP()
                send(ping_packet)

    finally:
        with allure.step("cleanup"):
            Acl().unset()


def skip_if_engines_does_not_exist_in_setup(required_engines_list, engines):
    not_existed_engines = []
    for engine_name in required_engines_list:
        if engine_name not in engines:
            not_existed_engines.append(engine_name)
    if not_existed_engines:
        pytest.skip("Skip this test cause don't have the required engines {}".format(not_existed_engines))


@retry(Exception, tries=10, delay=2)
def wait_for_hostname_changed(system, dhcp_hostname):
    with allure.step("Waiting for system hostname changed to {}".format(dhcp_hostname)):
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        assert dhcp_hostname in system_output[SystemConsts.HOSTNAME], \
            "hostname {0} wasn't changed to {1}".format(system_output[SystemConsts.HOSTNAME], dhcp_hostname)


def _wait_for_snmp_is_running(system, state='yes', tries=5, timeout=2):
    for _ in range(tries):
        system_snmp_output = OutputParsingTool.parse_json_str_to_dictionary(system.snmp_server.show()) \
            .get_returned_value()
        if state in system_snmp_output[SystemConsts.SNMP_IS_RUNNING]:
            break
        elif state not in system_snmp_output[SystemConsts.SNMP_IS_RUNNING]:
            time.sleep(timeout)
            continue
        else:
            assert 'SNMP not in {} is-running state'.format(state)


def get_rule_packets(mgmt_port, acl_id, rule_id=None, rule_direction=AclConsts.INBOUND):
    output = mgmt_port.interface.acl.acl_id[acl_id].parse_show()
    res = {}
    if rule_id:
        res[rule_id] = int(output[AclConsts.STATISTICS][rule_id][rule_direction]["packet"])
    else:
        for rule_id, rule_obj in output[AclConsts.STATISTICS].items():
            res[rule_id] = int(rule_obj[rule_direction]["packet"])
    return res


def config_rule(engine, acl_id_obj, rule_id, rule_config_dict):
    with allure.step(f"Config rule {rule_id}"):
        acl_id_obj.rule.set(rule_id).verify_result()
        rule_id_obj = acl_id_obj.rule.rule_id[rule_id]

        for key, value in rule_config_dict.items():
            RULE_CONFIG_FUNCTION[key](rule_id_obj, value).verify_result()

        result_obj = SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config,
                                                     engine, True)
        return result_obj
