import logging
import pytest
import re
import time

logger = logging.getLogger()

from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.ib_router.constants import IbRouterConsts
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.IbRouterTool import IbRouterTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.ib.Ib import Ib

HOSTNAME_CMD = "hostname"


@pytest.mark.skip_clear_config
def test_setup_health(engines, players, interfaces, setup_name, start_sm_on_hosts, enable_ib_router_profile):
    """
    prepare the setup for functional tests by setting it up
    Test flow:
        1. check all leaf ports are up
        2. make sure IbRouterConsts.OPERATIONAL_SWIDS are all active on the CLI
        3. check hosts on the same SWID see each other (via ibnetdiscover)
        4. check that hosts on different SWID dont se each other
        5. check the router node description is corrects

    """
    with allure.step(f"checking leaf ports status"):
        check_leaf_ports()
    with allure.step(f"checking SWIDs status and enforcement"):
        check_swid_state(engines)
        check_swid_isolation(engines)
        check_swid_gids(engines)


@pytest.mark.skip_clear_config
def test_clean_setup_health(engines, disable_ib_router_profile, stop_sm):
    """
    this checks the setup is back to non-ib-router with the following steps:
    Test flow:
        1. disable ib router profile
        2. make sure profile is now disabled
    note - more checks are done as part of th

    """
    with allure.step(f"make sure the profile is now disabled"):
        system = System(None)
        system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(system.profile.show()) \
            .get_returned_value()
        assert system_profile_output[
            SystemConsts.PROFILE_IB_ROUTING] == SystemConsts.PROFILE_STATE_DISABLED, f"FAILED - after enabling, ib-routing field is {system_profile_output[SystemConsts.PROFILE_IB_ROUTING]}," \
            f" its expected to be disabled"


def check_leaf_ports():
    """
       the Function will check that all leaf ports are up on the router
    """
    with allure.step(f"checking leaf ports {IbRouterConsts.ROUTER_PORTS_TO_LEAFS} are active-linkup"):
        ports_dict = OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            Port.show_interface()).verify_result()
        for port_name in IbRouterConsts.ROUTER_PORTS_TO_LEAFS:
            assert ports_dict[port_name][IbInterfaceConsts.LINK_LOGICAL_PORT_STATE] == IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE, \
                f"Port {port_name} logical state is expected to be {IbInterfaceConsts.LINK_LOGICAL_PORT_STATE} but found to be {ports_dict[port_name][IbInterfaceConsts.LINK_LOGICAL_PORT_STATE]}"
            assert ports_dict[port_name][IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE] == IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP, \
                f"Port {port_name} physical state is expected to be {IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP} but found to be {ports_dict[port_name][IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE]}"


def check_swid_state(engines):
    """
       the Function will check that all active swids are active on the router CLI
    """
    with allure.step('check the active SWIDs are marked as valid and has the correct prefix'):
        ib = Ib(None)
        show_router_output = OutputParsingTool.parse_json_str_to_dictionary(ib.router.routing_table.show()).get_returned_value()
        for idx in range(IbRouterConsts.SWID_NUM):
            swid_name = IbRouterTool.get_swid_name(idx)
            assert swid_name in show_router_output.keys(), f"SWID {swid_name} not in the nv show ib router output"
            swid_state = show_router_output[swid_name][IbRouterConsts.VALID]
            logger.info(f"SWID{idx} state on switch: {swid_state}")
            if idx in IbRouterConsts.OPERATIONAL_SWIDS:
                verify_swid_prefix(engines, idx, swid_name, show_router_output)
                assert str(swid_state).lower() == 'true', f"SWID{idx} / {swid_name} is marked {swid_state} in the switch, it should be 'true'"

            else:
                assert str(swid_state).lower() == 'false', f"SWID{idx} / {swid_name} is marked {swid_state} in the switch, it should be 'false'"


def verify_swid_prefix(engines, idx, swid_name, show_router_output):
    """
       the Function will check that the swid prefix in the CLI matches the prefix configured in the openSM config file
    """
    with allure.step('check the active SWIDs has the correct prefix equal to prefix in the openSM config file'):
        logger.info(f"getting SWID{idx} subnet prefix from openSM file")
        sm_host_nickname = IbRouterConsts.SWID_TO_SM_NICKNAME[idx]
        sm_conf_file_name = IbRouterConsts.OPENSM_CONF_FILE_NAME.format(sm_host_nickname)
        sm_conf_file_path = IbRouterConsts.OPENSM_CONF_PATH + sm_conf_file_name
        subnet_prefix = get_subnet_prefix_from_sm_conf(engines, sm_conf_file_path)
        cli_subnet_prefix = show_router_output[swid_name][IbRouterConsts.SUBNET_PREFIX].replace(':', '')
        err_msg = f"SWID{idx} has the prefix {subnet_prefix} in the opensm file {sm_conf_file_path}, but on CLI output the prefix is {cli_subnet_prefix}"
        assert str(subnet_prefix) == str(cli_subnet_prefix), err_msg


def check_swid_gids(engines):
    """
           the Function will check the "nv show ib router ib-subnet" has the correct gids per subnet
"""
    with allure.step(f"checking gids per subnet"):
        ib = Ib(None)
        show_ib_subnet_output = OutputParsingTool.parse_json_str_to_dictionary(ib.router.ib_subnet.show()).get_returned_value()
        for idx in range(IbRouterConsts.SWID_NUM):
            with allure.step(f"checking gids on SWID {idx}"):
                swid_name = IbRouterTool.get_swid_name(idx)
                router_gids = show_ib_subnet_output[swid_name][IbRouterConsts.GID].keys()
                logger.info(f"for SWID{idx} - {swid_name}, the gids in the show commands are:\n{"\n".join(router_gids)}")
                swid_idx_sm_nickname = IbRouterConsts.SWID_TO_SM_NICKNAME[idx]
                host_engine = engines[swid_idx_sm_nickname]
                ibnetdiscover_router_guids = parse_ibnetdiscover_router_guids(host_engine)
                logger.info(f"for SWID{idx} - {swid_name}, the guids the host sees for router are:{"\n".join(ibnetdiscover_router_guids)}")
                sm_conf_file_name = IbRouterConsts.OPENSM_CONF_FILE_NAME.format(swid_idx_sm_nickname)
                sm_conf_file_path = IbRouterConsts.OPENSM_CONF_PATH + sm_conf_file_name
                subnet_prefix = get_subnet_prefix_from_sm_conf(engines, sm_conf_file_path)
                for guid in ibnetdiscover_router_guids:
                    # converting guid from (for example) b8e924030000b928 to b8e9:2403:0000:b928
                    parsed_guid = ":".join([guid[i:i + 4] for i in range(0, len(guid), 4)])
                    # converting prefix from (for example) 0xfec0000000000001 to fec0:0000:0000:0001
                    parsed_subnet_prefix = ":".join([subnet_prefix[i:i + 4] for i in range(0, len(subnet_prefix), 4)])
                    expected_gid = parsed_subnet_prefix + ":" + parsed_guid
                    logger.info(f"for SWID{idx} - {swid_name} gid calculated form ibnetdiscover and sm file: {expected_gid}")
                    logger.info(f"for SWID{idx} - {swid_name}, the gids in the show commands are:\n{"\n".join(router_gids)}")
                    assert expected_gid in router_gids, f"router guid {expected_gid} on SWID{idx} is not in the show commands guids: {router_gids} "


def check_swid_isolation(engines):
    """
    the Function will verify that hosts on the same SWID can see each other and
    hosts on different SWIDs cant see each other on ibnetdiscover
    """
    with allure.step('Checking with ibnetdiscover output that host on one SWID doesnt see hosts on another SWID'):
        host_nickname_to_hostname = calculate_hosts_hostnames(engines, IbRouterConsts.ALL_HOSTS_NICKNAMES)
        for host_nickname in IbRouterConsts.ALL_HOSTS_NICKNAMES:
            host_engine = engines[host_nickname]
            host_swid = IbRouterConsts.HOST_TO_SWID[host_nickname]
            seen_ib_nodes = parse_ibnetdiscover_nodes(host_engine)
            logger.info(f"IB nodes seen by {host_nickname} - {host_engine.ip}: {seen_ib_nodes}")
            for remote_host_nickname, remote_host_swid in IbRouterConsts.HOST_TO_SWID.items():
                with allure.step(f'Checking if host {host_nickname} - {host_engine.ip} sees host {remote_host_nickname}'
                                 f'- {host_nickname_to_hostname[remote_host_nickname]} on ibnetdiscover '):
                    if remote_host_nickname == host_nickname:
                        continue
                    elif host_swid == remote_host_swid:
                        logger.info(f"host {host_nickname_to_hostname[remote_host_nickname]} should be in the ibnetdiscover output")
                        assert host_nickname_to_hostname[remote_host_nickname] in seen_ib_nodes, f"host {host_nickname} - {host_engine.ip} should see host" \
                            f" {remote_host_nickname} - {host_nickname_to_hostname[remote_host_nickname]}" \
                            f" in its ibnetdiscover output, as they are on the same SWID"
                    else:
                        logger.info(f"host {host_nickname_to_hostname[remote_host_nickname]} should not be in the ibnetdiscover output")
                        assert host_nickname_to_hostname[remote_host_nickname] not in seen_ib_nodes, f"host {host_nickname} - {host_engine.ip} should NOT see" \
                            f" {remote_host_nickname} - {host_nickname_to_hostname[remote_host_nickname]}" \
                            f"in its ibnetdiscover output, as they are on different SWIDs"


def get_subnet_prefix_from_sm_conf(engines, sm_conf_file_path):
    """
    the function will get path to openSM conf file, for example
    /auto/sw_system_project/NVOS_INFRA/verification_files/xdr_ib_router/opensm_conf_hc.cfg
    and get the subnet prefix ID from it, usually designated by the line 0xfec000000000000X where X is the ID

    @param engines: engines obj
    @param sm_conf_file_path: the path to the opensm conf file
    @return: string, the prefix of the SM configuration
    """
    subnet_prefix = engines['sonic_mgmt'].run_cmd("grep 'subnet_prefix' {}".format(sm_conf_file_path) + "| awk '{print $2}'")
    assert IbRouterConsts.SUBNET_PREFIX_INITITAL in subnet_prefix, f"failed to parse the subnet prefix from the file {sm_conf_file_path}"
    return subnet_prefix.replace('0x', '')


def parse_ibnetdiscover_nodes(engine_obj):
    """
    parse ibnetdiscover output on given engine object and return list of ib nodes
    for example
    [MF0;croc-61-mgmt2:QM3400/U1,
    MF0;croc-61-mgmt2:QM3400/U2,
    fit-nos-vrt-40-041,
    fit-nos-vrt-40-043]
    """
    def get_unique_node_labels(ibnetdiscover_output):
        labels = set()
        pattern = re.compile(r'#\s*"([^"]+)"')
        for line in ibnetdiscover_output.splitlines():
            match = pattern.search(line)
            if match:
                first_word = match.group(1).split()[0]
                labels.add(first_word)
        return labels

    ibnetdiscover_output = engine_obj.run_cmd("sudo ibnetdiscover -C smi0")
    assert ibnetdiscover_output, f"failed to get ibnetdiscover on {engine_obj.ip} "
    unique_labels = get_unique_node_labels(ibnetdiscover_output)
    assert unique_labels, f"failed to parse ib nodes from ibnetdiscover on {engine_obj.ip}, or there were none in the ibnetdiscover output: {ibnetdiscover_output}"
    return unique_labels


def parse_ibnetdiscover_router_guids(engine_obj):
    """
    parse ibnetdiscover output on given engine object and return list of router interface guids
    router asics will be found in the name (for example)
    "MF0;mamba-2132:Q3400_RA/U1/RT"
    "MF0;mamba-2132:Q3400_RA/U2/RT"
    "MF0;mamba-2132:Q3400_RA/U3/RT"
    "MF0;mamba-2132:Q3400_RA/U4/RT"
    along with their GUID - in the example below the GUID is b8e924030000b929

    vendid=0x2c9
    devid=0xc839
    sysimgguid=0xb8e924030000b900
    rtguid=0xb8e924030000b928
    Rt      8 "R-b8e924030000b928"          # "MF0;mamba-2132:Q3400_RA/U2/RT"
    [2](b8e924030000b929)   "S-b8e924030000b921"[149]               # lid 9 lmc 0 "MF0;mamba-2132:Q3400_RA/U2" lid 8 1xXDR


    """
    def get_unique_router_node_guid(ibnetdiscover_output):
        # pattern = re.compile(r'"R-([^"]+)".*#\s*"[^"]+\/RT"')
        pattern = r'RT.*\n\[\d+\]\((.*)\).*U\d+'
        matches = re.findall(pattern, ibnetdiscover_output, re.MULTILINE)
        return matches

    ibnetdiscover_output = engine_obj.run_cmd("sudo ibnetdiscover -C smi0")
    assert ibnetdiscover_output, f"failed to get ibnetdiscover on {engine_obj.ip} "
    guid_list = get_unique_router_node_guid(ibnetdiscover_output)
    assert guid_list, f"failed to parse ib nodes from ibnetdiscover on {engine_obj.ip}, or there were none in the ibnetdiscover output: {ibnetdiscover_output}"
    return guid_list


def calculate_hosts_hostnames(engines, host_nicknames):
    """
    get list of host nicknames and return dict of nickname to hostname
    @param engines: engines obj
    @params host_nicknames: list of host nicknames, for example ['ha','hb']
    @returns: dict in the format -
                                    {ha: fit-nos-vrt-40-043,
                                    bh: fit-nos-vrt-40-041}
    """
    host_dict = {}
    for host_nickname in host_nicknames:
        engine = engines[host_nickname]
        output = engine.run_cmd(HOSTNAME_CMD)
        host_dict[host_nickname] = output
    return host_dict
