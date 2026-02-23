import pytest
import logging
import random
import time

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.IbRouterTool import IbRouterTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.tests_nvos.ib_router.constants import IbRouterConsts
from ngts.nvos_tools.ib.Ib import Ib

logger = logging.getLogger()

TEMP_FOLDER = "/tmp/"
PORT_UP_TIME = 30


@pytest.mark.skip_clear_config
def test_port_migration(engines, devices, verify_sm_running_on_all_hosts, random_api):
    """
    on a configured setup, it takes the leaf ports belong to SWID0 and move them to another SWID X few times and then back to SWID0
    this is done because multiple errors and fatal state scenarios that have been observed
    note - mapping ports to SWIDs beyond initial configuration is not something a customer is expected to do, but it should not cause fatal state
    """
    siwds_order_list = [1, 2, 3, 0]
    try:
        for swid_idx in siwds_order_list:
            swid_name = IbRouterTool.get_swid_name(swid_idx)
            for port in IbRouterConsts.SWID_TO_PORTS_DICT[0]:
                with allure.step(f"mapping port {port} to SWID{swid_idx} - {swid_name}"):
                    port_obj = Port(port)
                    port_obj.interface.link.ib_subnet.set(op_param_name=swid_name, apply=True).verify_result()

                with allure.step(f"verifying port mapping"):
                    time.sleep(PORT_UP_TIME)
                    ports_dict = OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
                        Port.show_interface()).verify_result()
                    port_swid = ports_dict[port][IbInterfaceConsts.LINK_IB_SUBNET]
                    assert port_swid == swid_name, f"port {port} does not belong to SWID {swid_name}, it found to be member of unexpected SWID {port_swid}"
    finally:
        with allure.step(f"as cleanup, resetting all leaf ports to their intended config"):
            IbRouterTool.configure_leaf_port_mapping(engines)


@pytest.mark.skip_clear_config
def test_sm_configuration_change(engines, devices, verify_sm_running_on_all_hosts, random_api):
    """
    on a configured setup, it will take one of the active SM, randomize network prefix for it and make sure the switch is updated with those changes
    """
    chosen_swid = random.choice(IbRouterConsts.OPERATIONAL_SWIDS)
    chosen_sm_nickname = IbRouterConsts.SWID_TO_SM_NICKNAME[chosen_swid]
    sm_engine = engines[chosen_sm_nickname]
    original_prefix = '0xfec000000000000{}'.format(chosen_swid + 1)
    new_dec_value = random.randint(0, 0xFFFF)
    new_hex_value = format(new_dec_value, '04X')
    new_prefix = '0xfec000000000{}'.format(new_hex_value)
    try:
        with allure.step(f"setting prefix {new_prefix} to SWID{chosen_swid} on SM host {chosen_sm_nickname} - {engines[chosen_sm_nickname].ip}"):
            IbRouterTool.stop_sm_on_hosts(engines)
            change_prefix_on_infra_files(sm_engine, chosen_sm_nickname, original_prefix, new_prefix)
            IbRouterTool.start_sm_on_hosts(engines, skip_copy_files=True)
            swid_name = IbRouterTool.get_swid_name(chosen_swid)

        with allure.step(f"checking that SWID{chosen_swid} now has the new prefix of {new_prefix} - {new_dec_value} in the nv show command"):
            ib = Ib(None)
            show_router_output = OutputParsingTool.parse_json_str_to_dictionary(ib.router.show()).get_returned_value()
            cli_subnet_prefix = show_router_output[IbRouterConsts.ROUTING_TABLE][swid_name][IbRouterConsts.SUBNET_PREFIX]
            logger.info(f"found prefix for swid{chosen_swid} is: {cli_subnet_prefix}, expected {new_dec_value}")
            err_msg = f"SWID{chosen_swid} has the prefix {cli_subnet_prefix} , expected to have the new prefix {new_dec_value}"
            assert str(new_dec_value) == str(cli_subnet_prefix), err_msg
    finally:
        IbRouterTool.stop_sm_on_hosts(engines)
        IbRouterTool.reset_router_config_file(engines)
        IbRouterTool.start_sm_on_hosts(engines)


def change_prefix_on_infra_files(sm_engine, host_nicknames, old_prefix, new_prefix):
    """
    the function will update subnet prefix for the given host engine the subnet prefix
    this will update it under /tmp/opensm_conf_{host_nicknames}.cfg"
    and under the shared file
    "/auto/sw_system_project/NVOS_INFRA/verification_files/xdr_ib_router/router_policy.cfg"
    """
    sm_conf_file_name = IbRouterConsts.OPENSM_CONF_FILE_NAME.format(host_nicknames)
    sm_conf_file_path = TEMP_FOLDER + sm_conf_file_name
    sm_engine.run_cmd(f"sed -i 's/{old_prefix}$/{new_prefix}/' {sm_conf_file_path}")
    sm_engine.run_cmd(f"sed -i 's/{old_prefix}$/{new_prefix}/' {IbRouterConsts.OPENSM_CONF_PATH}{IbRouterConsts.ROUTER_POLICY_FILE_NAME}")
