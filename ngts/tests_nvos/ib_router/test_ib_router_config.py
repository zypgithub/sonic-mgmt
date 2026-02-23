import pytest
import logging
import random
import time

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.IbRouterTool import IbRouterTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.DutUtilsTool import RebootParams
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()

MIN_SWID_NUM = 2
MAX_SWID_NUM = 4
IB_PORT_INITIAL = "sw"
PROFILE_CHANGE_DOWN_TIME = 150
PORT_CONFIG_APPLY_TIME = 20


@pytest.mark.ib
@pytest.mark.device
def test_ib_router_config(engines, devices, random_api, stop_sm):
    """
    active router profile and randomize port mapping, then verify show commands according to configuration
    and the values are in appropriate range.
    Test flow:
        1. make sure machine is not with ib router enabled
        2. randomize number of SWIDs and configure the machine with ib profile enabled with the SWID amount
        3. make sure profile changed
        4. map all ports to the chosen SWIDs by randomization
        5. verify ports mapping is correct
        6. revert to router-disabled profile
        7. make sure profile changed
        8. make sure all ports are back to default SWID

    """
    with allure.step("Create an system object"):
        system = System(None)

    reboot_params = RebootParams(wait_time_before_reboot=PROFILE_CHANGE_DOWN_TIME)

    with allure.step("Verifying router profile is disabled"):
        IbRouterTool.verify_profile_status(SystemConsts.PROFILE_STATE_DISABLED, 1)
    try:
        with allure.step(f"changing profile to ib router"):
            swids_num = random.randrange(MIN_SWID_NUM, MAX_SWID_NUM + 1)
            logger.info(f"ib router profile will be enabled with {swids_num} swids")
            params = {SystemConsts.PROFILE_IB_ROUTING: SystemConsts.PROFILE_STATE_ENABLED,
                      SystemConsts.PROFILE_NUMBER_OF_SWIDS: swids_num}
            system.profile.action_profile_change(params_dict=params, reboot_params=reboot_params)

        with allure.step(f"verify profile changed"):
            IbRouterTool.verify_profile_status(SystemConsts.PROFILE_STATE_ENABLED, swids_num)

        with allure.step(f"calculate ports to SWIDs data structures"):
            swids_to_port_list, filtered_ports_list = distribute_ports_to_swids(swids_num, devices)

        for idx, port_list in enumerate(swids_to_port_list):
            with allure.step(f"mapping ports {port_list} to SWID{idx}"):
                swid_name = IbRouterTool.get_swid_name(idx)
                for port_name in port_list:
                    port_obj = Port(port_name)
                    port_obj.interface.link.set(op_param_name=IbInterfaceConsts.LINK_IB_SUBNET, op_param_value=swid_name, apply=False).verify_result()
                TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config(TestToolkit.engines.dut, True)

        with allure.step(f"verifying port mapping"):
            time.sleep(PORT_CONFIG_APPLY_TIME)
            ports_dict = OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
                Port.show_interface()).verify_result()
            for idx, port_list in enumerate(swids_to_port_list):
                with allure.step(f"making sure the ports {port_list} now mapped to SWID{idx}"):
                    swid_name = IbRouterTool.get_swid_name(idx)
                    for port_name in port_list:
                        assert port_name in ports_dict, f"{port_name} not in the nv show interfaces output: {ports_dict}"
                        port_swid = ports_dict[port_name][IbInterfaceConsts.LINK_IB_SUBNET]
                        assert port_swid == swid_name, f"port {port_name} does not belong to SWID {swid_name}, it found to be member of unexpected SWID {port_swid}"
    finally:
        with allure.step(f"disabling ib router profile"):
            params = {SystemConsts.PROFILE_IB_ROUTING: SystemConsts.PROFILE_STATE_DISABLED}
            system.profile.action_profile_change(params_dict=params, reboot_params=reboot_params)

    with allure.step("Verifying router profile is disabled"):
        IbRouterTool.verify_profile_status(SystemConsts.PROFILE_STATE_DISABLED, 1)

    with allure.step(f"verifying port mapping is back to infiniband-default"):
        ports_dict = OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            Port.show_interface()).verify_result()
        for port_name in filtered_ports_list:
            port_swid = ports_dict[port_name][IbInterfaceConsts.LINK_IB_SUBNET]
            assert port_swid == IbInterfaceConsts.DEFAULT_SWID, f"port {port_name} does not belong to SWID 0 after profile is disabled, it found to be member of unexpected SWID {port_swid}"


def distribute_ports_to_swids(swids_num, devices):
    """
    helper function that split all the IB ports to groups according to the number of SWIDs configured on the system
    @param swids_num: amount of SWIDs configured
    @param devices: devices obj
    @return: tuple of two lists
    swids_to_port_list - list of port lists, where item #n is the ports assigned to SWID-n
    filtered_ports_list - list of all the IB ports in the system, filtered by ports with keyword IB_PORT_INITIAL in them
    """
    ports_dict = OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
        Port.show_interface()).verify_result()
    filtered_ports_list = [k for k, v in ports_dict.items() if IB_PORT_INITIAL in k]
    assert len(filtered_ports_list) == devices.dut.ib_ports_num, f"found len{filtered_ports_list} ib ports, expected to find {devices.dut.ib_ports_num} " \
        f"ports on BM switch"
    swids_to_port_list = [[] for _ in range(swids_num)]
    for port_name in filtered_ports_list:
        group_idx = random.randrange(swids_num)
        swids_to_port_list[group_idx].append(port_name)

    return swids_to_port_list, filtered_ports_list
