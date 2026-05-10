import pytest
import logging
import random
import time
import itertools
import pprint

from ngts.nvos_tools.infra.Tools import Tools
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.IbRouterTool import IbRouterTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.tests_nvos.ib_router.constants import IbRouterConsts
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.SerialConsoleTool import SerialConsoleTool
logger = logging.getLogger()

PKTS_PER_STREAM = 30


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
    with allure.step(f"Sending traffic between all hosts on different SWIDs"):
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
def test_traffic_counter(engines, players, interfaces, devices, verify_sm_running_on_all_hosts):
    """
    on a configured setup, the test will chose hosts on the following SWID combinations
    SWID0 - SWID1
    SWID0 - SWID2
    and son on, according to the pairs (source SWID, dst SWID)
    (0,1), (0,2), (0,3), (0,4), (1,2), (1,3), (1,4), (2,3), (2,4), (3,4)

    then the test will run short traffic with known amount of packets
    and then
    """
    ib = Ib(None)
    swid_pairs = list(itertools.combinations(range(IbRouterConsts.SWID_NUM), 2))
    with allure.step(f"Sending traffic between different SWIDs and checking counters"):
        for (source_swid, dst_swid) in swid_pairs:
            sender_host = IbRouterConsts.SWID_TO_SM_NICKNAME[source_swid]
            receiver_host = IbRouterConsts.SWID_TO_SM_NICKNAME[dst_swid]
            sender_swid = IbRouterConsts.HOST_TO_SWID[sender_host]
            sender_ip = engines[sender_host].ip
            sender_flid = IbRouterConsts.SWID_TO_FLID[sender_swid]
            receiver_swid = IbRouterConsts.HOST_TO_SWID[receiver_host]
            receiver_flid = IbRouterConsts.SWID_TO_FLID[receiver_swid]
            receiver_ip = engines[receiver_host].ip

            with allure.step("Clearing counters before traffic"):
                ib.router.counters.clear_counters().verify_result()
                check_empty_counters(ib)

            with allure.step(f"Sending short traffic between host {sender_host} - {sender_ip} -SWID{sender_swid} "
                             f"and host {receiver_host} - {receiver_ip} on SWID{receiver_swid}"):
                traffic_params = {'sender': sender_host,
                                  'sender_interface': interfaces[f"{sender_host}_dut_1"],
                                  'sender_flags': f'--dlid {receiver_flid} -x 1 ',
                                  'receiver': receiver_host,
                                  'data_size': '1024',
                                  'receiver_interface': interfaces[f"{receiver_host}_dut_1"],
                                  'receiver_flags': f'--dlid {sender_flid} -x 1 '
                                  }
                rc = Tools.TrafficGeneratorTool.send_ib_traffic_with_params(players, should_success=True,
                                                                            traffic_params=traffic_params)
                if not rc.result:
                    raise Exception(f"Traffic between host {sender_host} - {sender_ip} SWID{sender_swid} and host {receiver_host} - {receiver_ip} SWID{receiver_swid} failed")

                with allure.step(f"checking counters on traffic between SWID{sender_swid} and SWID{receiver_swid}"):
                    check_counters_after_traffic(ib, sender_swid, receiver_swid)


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
def test_traffic_after_leaf_reboot(engines, players, interfaces, devices, topology_obj, verify_sm_running_on_all_hosts):
    """
    on a configured setup, the test will reboot one of the leaf croc switches then run test_sanity_traffic
    """
    valid_reboot_types = ["", "force"]
    reboot_type = random.choice(valid_reboot_types)
    logger.info(f"Randomly choose {reboot_type} from {valid_reboot_types}")
    chosen_leaf = random.choice(IbRouterConsts.CROC_SWITCHES_NICKNAMES)
    leaf_engine = engines[chosen_leaf]
    leaf_device = devices[chosen_leaf]
    leaf_serial_engine = SerialConsoleTool.get_serial_console_session(topology_obj, chosen_leaf)

    system = System(devices_dut=leaf_device)
    system.reboot.action_reboot(engine=leaf_engine, params=reboot_type, device=leaf_device, should_wait_till_system_ready=False)
    DutUtilsTool.wait_for_system_ready_in_serial(topology_obj, leaf_serial_engine, 300)
    time.sleep(120)
    test_sanity_traffic(engines, players, interfaces, devices, verify_sm_running_on_all_hosts)


def check_empty_counters(ib_object):
    """
    helper function that will check after a clear counters that all swids counter are empty
    """
    def all_fields_zero(d):
        for value in d.values():
            if isinstance(value, dict):
                if not all_fields_zero(value):
                    return False
            elif value != 0:
                return False
        return True

    for swid_idx in range(IbRouterConsts.SWID_NUM):
        swid_name = IbRouterTool.get_swid_name(swid_idx)
        swid_counters = OutputParsingTool.parse_json_str_to_dictionary(ib_object.router.ib_subnet.swid_id[swid_name].counters.show()).get_returned_value()
        res = all_fields_zero(swid_counters)
        pprint.pprint(swid_counters)
        assert res, f"counters for SWID {swid_name} are not empty after a clear counters initiated"


def check_counters_after_traffic(ib_object, sender_swid, receiver_swid):
    """
    helper function that will check counters on swids after traffic session ran, and check that the relevant swids has the correct packets count and other swids has no packets count
    """
    def all_fields_zero(d):
        for value in d.values():
            if isinstance(value, dict):
                if not all_fields_zero(value):
                    return False
            elif value != 0:
                return False
        return True

    for swid_idx in range(IbRouterConsts.SWID_NUM):
        swid_name = IbRouterTool.get_swid_name(swid_idx)
        swid_counters = OutputParsingTool.parse_json_str_to_dictionary(ib_object.router.ib_subnet.swid_id[swid_name].counters.show()).get_returned_value()
        if swid_idx == sender_swid:
            assert swid_counters[IbInterfaceConsts.LINK_STATS_OUT_PKTS] == PKTS_PER_STREAM, f"counter for packets coming out of SWID {swid_idx}-{swid_name} should be {PKTS_PER_STREAM} but found {swid_counters[IbInterfaceConsts.LINK_STATS_OUT_PKTS]}"
        elif swid_idx == receiver_swid:
            assert swid_counters[IbInterfaceConsts.LINK_STATS_IN_PKTS] == PKTS_PER_STREAM, f"counter for packets coming in SWID {swid_idx}-{swid_name} should be {PKTS_PER_STREAM} but found {swid_counters[IbInterfaceConsts.LINK_STATS_OUT_PKTS]}"
        else:
            res = all_fields_zero(swid_counters)
            assert res, f"counters for SWID {swid_name} should be empty, as this SWID is not part of traffic"
