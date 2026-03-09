import pytest
import logging
import random
import time
import itertools
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.IbRouterTool import IbRouterTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.tests_nvos.ib_router.constants import IbRouterConsts
from ngts.nvos_tools.infra.DutUtilsTool import RebootParams
logger = logging.getLogger()


@pytest.mark.skip_clear_config
def test_sanity_traffic(engines, players, interfaces, devices, verify_sm_running_on_all_hosts):
    """
    on a configured setup, it takes the leaf ports belong to SWID 0 and move them to another SWID X few times and then back to SWID0
    this is done because multiple errors and fatal state scenarios that have been observed
    note - mapping ports to SWIDs beyond initial configuration is not something a customer is expected to do, but it should not cause fatal state
    """
    hosts_pairs = list(itertools.combinations(IbRouterConsts.ALL_HOSTS_NICKNAMES, 2))
    same_swid_hosts_pairs = [(host_a, host_b) for host_a, host_b in hosts_pairs if IbRouterConsts.HOST_TO_SWID[host_a] == IbRouterConsts.HOST_TO_SWID[host_b]]
    different_swid_hosts_pairs = [(host_a, host_b) for host_a, host_b in hosts_pairs if IbRouterConsts.HOST_TO_SWID[host_a] != IbRouterConsts.HOST_TO_SWID[host_b]]
    traffic_fails_lists = []
    with allure.step(f"Sending traffic between all hosts on the same SWID"):
        for (sender_host, receiver_host) in same_swid_hosts_pairs:
            sender_swid = IbRouterConsts.HOST_TO_SWID[sender_host]
            sender_ip = engines[sender_host].ip
            receiver_ip = engines[receiver_host].ip
            with allure.step(f"Sending traffic between host {sender_host} - {sender_ip} and host {receiver_host} - {receiver_ip} on SWID{sender_swid}"):
                traffic_params = {'sender': sender_host,
                                  'sender_interface': interfaces[f"{sender_host}_dut_1"],
                                  'sender_flags': '-x 1',
                                  'receiver': receiver_host,
                                  'receiver_interface': interfaces[f"{receiver_host}_dut_1"],
                                  'receiver_flags': '-x 1'
                                  }
                rc = Tools.TrafficGeneratorTool.send_ib_traffic_with_params(players, should_success=True,
                                                                            traffic_params=traffic_params)
                if not rc.result:
                    traffic_fails_lists.append(f"Traffic between host {sender_host} - {sender_ip} and host {receiver_host} - {receiver_ip}, both on SWID{sender_swid} failed")
        if traffic_fails_lists:
            raise Exception(traffic_fails_lists)
    with allure.step(f"Sending traffic between all hosts on the same SWID"):
        for (sender_host, receiver_host) in different_swid_hosts_pairs:
            sender_swid = IbRouterConsts.HOST_TO_SWID[sender_host]
            sender_ip = engines[sender_host].ip
            sender_flid = IbRouterConsts.SWID_TO_FLID[sender_swid]
            receiver_swid = IbRouterConsts.HOST_TO_SWID[receiver_host]
            receiver_flid = IbRouterConsts.SWID_TO_FLID[receiver_swid]
            receiver_ip = engines[receiver_host].ip
            with allure.step(f"Sending traffic between host {sender_host} - {sender_ip} -SWID{sender_swid} "
                             f"and host {receiver_host} - {receiver_ip} on SWID{receiver_swid}"):
                traffic_params = {'sender': sender_host,
                                  'sender_interface': interfaces[f"{sender_host}_dut_1"],
                                  'sender_flags': f'--dlid {receiver_flid} -x 1',
                                  'receiver': receiver_host,
                                  'receiver_interface': interfaces[f"{receiver_host}_dut_1"],
                                  'receiver_flags': f'--dlid {sender_flid} -x 1'
                                  }
                rc = Tools.TrafficGeneratorTool.send_ib_traffic_with_params(players, should_success=True,
                                                                            traffic_params=traffic_params)
                if not rc.result:
                    traffic_fails_lists.append(f"Traffic between host {sender_host} - {sender_ip} SWID{sender_swid} and host {receiver_host} - {receiver_ip} SWID{receiver_swid} failed")
        if traffic_fails_lists:
            raise Exception(traffic_fails_lists)


@pytest.mark.skip_clear_config
def test_traffic_after_reboot(engines, players, interfaces, devices, verify_sm_running_on_all_hosts, ):
    """
    on a configured setup, the test will reboot the DUT and then run test_sanity_traffic
    """
    valid_reboot_types = ["", "force"]
    reboot_type = random.choice(valid_reboot_types)
    logger.info(f"Randomly choose {reboot_type} from {valid_reboot_types}")
    system = System()
    system.reboot.action_reboot(engine=engines.dut, params=reboot_type)
    time.sleep(120)
    test_sanity_traffic(engines, players, interfaces, devices, verify_sm_running_on_all_hosts)


@pytest.mark.skip_clear_config
def test_traffic_after_leaf_reboot(engines, players, interfaces, devices, verify_sm_running_on_all_hosts):
    """
    on a configured setup, the test will reboot one of the leaf croc switches then run test_sanity_traffic
    """
    valid_reboot_types = ["", "force"]
    reboot_type = random.choice(valid_reboot_types)
    logger.info(f"Randomly choose {reboot_type} from {valid_reboot_types}")
    chosen_leaf = random.choice(IbRouterConsts.CROC_SWITCHES_NICKNAMES)
    leaf_engine = engines[chosen_leaf]
    leaf_device = devices[chosen_leaf]
    system = System(devices_dut=leaf_device)
    system.reboot.action_reboot(engine=leaf_engine, params=reboot_type, device=leaf_device)
    time.sleep(120)
    test_sanity_traffic(engines, players, interfaces, devices, verify_sm_running_on_all_hosts)
