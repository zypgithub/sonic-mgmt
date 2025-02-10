import logging
from typing import List

import pytest
import re
import random

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.nvos_tools.Devices.IbDevice import CrocodileSwitch
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import ApiType, IbConsts, SystemConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
logger = logging.getLogger()


# todo openapi - need to implement OpenApiIbInterfaceCli.clear_stats
@pytest.mark.ib_interfaces
def test_ib_clear_counters(engines, players, interfaces, start_sm, setup_name, fae_param=""):
    """
    Clear counters test
    Commands:
        > nv action interface {port_name} link clear counters

    flow:
    1. Select a random port (which is up)
    2. Run traffic and identify which ports are connected to a traffic server
    3. Select a random traffic port
    4. Run clear counters for selected port
    5. Make sure the counters were cleared
    6. Run traffic and make sure the counters are not 0
    """
    _clear_counters_test_flow(engines, players, interfaces, setup_name, False, fae_param)


# todo openapi - need to implement OpenApiIbInterfaceCli.clear_stats
@pytest.mark.ib_interfaces
def test_clear_all_counters(engines, players, interfaces, start_sm, setup_name, fae_param=""):
    """
    Clear counters for all interfaces
    Commands:
        > nv action clear interface counters
    """
    _clear_counters_test_flow(engines, players, interfaces, setup_name, True, fae_param)


@pytest.mark.ib_interfaces
# todo openapi - need to implement OpenApiIbInterfaceCli.clear_stats
def test_range_clear_counters_negative(engines, players, interfaces, start_sm, fae_param=""):
    """
    verify all these commands fail with the right error message.
        1. nv action clear interface sw5-7p1-2 counters - out of range
        2. nv action clear interface sw5-1000p1-2 counters - out of range
        3. nv action clear interface sw7-5p1-2 counters - reversed range
        4. nv action clear interface sw5-7p2-1 counters - undefined p2-1
    """
    with allure.step("Get a random active port"):
        selected_ports = Tools.RandomizationTool.get_random_traffic_port().get_returned_value()

    out_of_range_p, out_of_range_sw, reversed_range, undefined_range = create_invalid_ranges(selected_ports[0].name)
    error_msg1 = 'does not exist'
    error_msg2 = "is not a 'interface-name'. Valid interface types are"

    with allure.step("Create Interface"):
        interface = Interface(parent_obj=None)

    with allure.step('Tests'):
        with allure.independent_step("check out of range {}".format(out_of_range_p)):
            interface.action_clear_counter_for_interface(interface_name=out_of_range_p
                                                         ).verify_result(False, error_msg1)

        with allure.independent_step("check out of range {}".format(out_of_range_sw)):
            interface.action_clear_counter_for_interface(interface_name=out_of_range_sw
                                                         ).verify_result(False, error_msg1)

        with allure.independent_step("check reversed range"):
            interface.action_clear_counter_for_interface(interface_name=reversed_range
                                                         ).verify_result(False, error_msg2)

        with allure.independent_step("check undefined range"):
            interface.action_clear_counter_for_interface(interface_name=undefined_range
                                                         ).verify_result(False, error_msg2)


@pytest.mark.ib_interfaces
# todo openapi - need to implement OpenApiIbInterfaceCli.clear_stats
def test_range_clear_counters_positive(engines, devices, players, interfaces, start_sm, setup_name, fae_param=""):
    """
    verify all these commands fail with the right error message.
        0. get linked ports
        1. create new user
        2. run traffic
        3. pick random range - pick 4 points out of all interfaces list -
        4. nv action clear interface <point2>-<point3>p(1-1 or 2-2) link counters
        5. verify all clear counter files have been created under
        6. verify show counters command for traffic port != 0
        7. nv action clear interface <traffic port>-<point1>p1-2, <point 4> link counters
        8. verify files under user path
        9. verify show counters command for traffic port == 0
    """
    with allure.step("Create Interface"):
        interface = Interface(parent_obj=None)

    with allure.step("Get a random active port"):
        selected_port, = Tools.RandomizationTool.get_random_traffic_port().get_returned_value()
        selected_port_number = int(re.findall(r'\d+', selected_port.name)[0])

    file_name, user_name, ssh_connection = create_new_user(engines.dut)

    with allure.step('Send traffic through selected port'):
        Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()

    with allure.step("Get 4 random numbers - to define ranges"):
        if isinstance(devices.dut, CrocodileSwitch):
            pytest.skip("Test needs to be adapted to crocodile port names")  # todo
        else:
            # Select two non-intersecting ranges and one additional random port, e.g. 12-19, 22 and 30-72.
            # The active port selected previously will be in the second range or be the lone port.
            randoms = random.sample(
                list({x + 1 for x in range(1, devices.dut.ib_ports_num // 2 + 1)} - {selected_port_number}), 4)
            randoms = sorted(randoms + [selected_port_number])
            if selected_port_number in randoms[:2]:
                (first_range_first_point, first_range_last_point, random_port, second_range_first_point,
                 second_range_last_point) = randoms
            else:
                (random_port, second_range_first_point, second_range_last_point, first_range_first_point,
                 first_range_last_point) = randoms
            p_number = random.randint(1, 2)
            random_port = f'sw{random_port}p{p_number}'

    with allure.step("Run clear counters using range for p1 or p2 only"):
        with allure.step('Run clear counter command'):
            interface.action_clear_counter_for_interface(dut_engine=ssh_connection,
                                                         interface_name='sw{first}-{last}p{p_number}-{p_number},{random_port}'.format(
                                                             p_number=p_number, first=second_range_first_point,
                                                             last=second_range_last_point, random_port=random_port)
                                                         ).verify_result()

        verify_files_created(ssh_connection, file_name,
                             get_port_range(second_range_first_point, second_range_last_point, p_number) + [random_port])

        with allure.step('verify show command output'):
            with allure.step('Check selected port counters'):
                check_port_counters(selected_port, False, ssh_connection).verify_result()
                check_port_counters(selected_port, False, engines.dut).verify_result()

    with allure.step("Run clear counters using range and multiple ports and verify results"):

        with allure.step('Run clear counter command'):
            interface.action_clear_counter_for_interface(dut_engine=ssh_connection,
                                                         interface_name='sw{first}-{last}p1-2,{random_port}'.format(
                                                             first=first_range_first_point, last=first_range_last_point,
                                                             random_port=random_port)).verify_result()

        verify_files_created(ssh_connection, file_name,
                             get_port_range(first_range_first_point, first_range_last_point) + [random_port])

        with allure.step('verify show command output'):
            with allure.step('Check selected port counters'):
                check_port_counters(selected_port, True, ssh_connection).verify_result()
                check_port_counters(selected_port, False, engines.dut).verify_result()


def _clear_counters_test_flow(engines, players, interfaces, setup_name, all_counters=False, fae_param=""):
    with allure.step("Get a random active port"):
        temp_selected_ports = Tools.RandomizationTool.get_random_traffic_port().get_returned_value()

        file_name, user_name, ssh_connection = create_new_user(engines.dut)

    with allure.step("Clear counters for the default user"):
        temp_selected_ports[0].interface.action_clear_counter_for_all_interfaces(engines.dut, fae_param).\
            verify_result()

        with allure.step('Send traffic through selected port'):
            Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()

        with allure.step('Check selected port counters'):
            selected_ports = temp_selected_ports.copy()

            for port in temp_selected_ports:
                result = check_port_counters(port, False, engines.dut)
                if not result.result:
                    selected_ports.remove(port)

            assert len(selected_ports) != 0, "No traffic was detected. Counter errors:{}".format(result.info)

            if not all_counters:
                selected_ports = [selected_ports[0]]
                check_port_counters(selected_ports[0], False, engines.dut).verify_result()
            check_port_counters(selected_ports[0], False, ssh_connection).verify_result()

    with allure.step("Clear counters for the a new user '{}'".format(user_name)):
        if all_counters:
            selected_ports[0].interface.action_clear_counter_for_all_interfaces(ssh_connection, fae_param).\
                verify_result()
        else:
            clear_counters_for_user(ssh_connection, user_name, engines.dut.username, engines.dut,
                                    selected_ports[0], fae_param)

        with allure.step("Verify {} was created".format(file_name)):
            output = engines.dut.run_cmd("ls -l {}".format(file_name))
            assert "cannot access" not in output, file_name + " can't be found"

        with allure.step('Check selected port counters'):
            for port in selected_ports:
                check_port_counters(port, True, ssh_connection).verify_result()
            for port in selected_ports:
                check_port_counters(port, False, engines.dut).verify_result()

        with allure.step('Send traffic through selected port'):
            Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()

        with allure.step('Check selected port counters'):
            for port in selected_ports:
                check_port_counters(port, False, ssh_connection).verify_result()
            for port in selected_ports:
                check_port_counters(port, False, engines.dut).verify_result()


def clear_counters_for_user(active_ssh_engine, active_user_name, inactive_user_name,
                            inactive_ssh_engine, selected_port, fae_param=""):
    with allure.step('Clear counter for selected port "{}" for user {}'.format(selected_port.name,
                                                                               active_ssh_engine.username)):
        selected_port.interface.link.stats.clear_stats(dut_engine=active_ssh_engine, fae_param=fae_param).\
            verify_result()
        with allure.step('Check selected port counters for user ' + active_user_name):
            if not check_port_counters(selected_port, True, active_ssh_engine).result:
                raise Exception(f"The counters were not cleared for user: {active_user_name}")
        with allure.step('Check selected port counters for user ' + inactive_user_name):
            if not check_port_counters(selected_port, False, inactive_ssh_engine).result:
                raise Exception(f"The counters were cleared for user {inactive_user_name} "
                                f"while they shouldn't have been")
        logging.info("The counters were cleared for port '{}' successfully".format(
            selected_port.name))


def check_port_counters(selected_port, should_be_zero, ssh_engine):
    logging.info("--- Counters for user: {}".format(ssh_engine.username))
    info = ""
    link_stats_dict = OutputParsingTool.parse_json_str_to_dictionary(
        selected_port.interface.link.stats.show(dut_engine=ssh_engine)).get_returned_value()

    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_IN_DROPS, should_be_zero, 0)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_IN_ERRORS, should_be_zero, 0)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_IN_SYMBOL_ERRORS, should_be_zero, 0)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_IN_BYTES, should_be_zero,
                                    IbInterfaceConsts.MAX_BYTE_COUNTER_AFTER_CLEAR)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_IN_PKTS, should_be_zero,
                                    IbInterfaceConsts.MAX_PKT_COUNTER_AFTER_CLEAR)

    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_OUT_DROPS, should_be_zero, 0)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_OUT_ERRORS, should_be_zero, 0)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_OUT_WAIT, should_be_zero, 0)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_OUT_BYTES, should_be_zero,
                                    IbInterfaceConsts.MAX_BYTE_COUNTER_AFTER_CLEAR)
    info += _validate_link_counters(link_stats_dict, IbInterfaceConsts.LINK_STATS_OUT_PKTS, should_be_zero,
                                    IbInterfaceConsts.MAX_PKT_COUNTER_AFTER_CLEAR)

    return ResultObj(False if info else True, info=info)


def _validate_link_counters(output_dict, field_name, should_be_zero, limit=0):
    field_val = int(output_dict[field_name])
    info = ""
    if should_be_zero:
        if field_val > limit:
            info = "{} is {} instead of being under {}, ".format(field_name, field_val, limit)
    else:
        if field_val < limit:
            info = "{} is {} instead of being over {}, ".format(field_name, field_val, limit)
    return info


def get_port_obj(port_name):
    port_requirements_object = PortRequirements()
    port_requirements_object.set_port_name(port_name)
    port_requirements_object.set_port_state(NvosConsts.LINK_STATE_UP)
    port_requirements_object.set_port_type(IbInterfaceConsts.IB_PORT_TYPE)

    port_list = Port.get_list_of_ports(port_requirements_object=port_requirements_object)
    assert port_list and len(port_list) > 0, "Failed to create Port object for {}. " \
                                             "Make sure the name of the port is accurate and the state of " \
                                             "this port is UP".format(port_name)
    return port_list[0]


def create_invalid_ranges(port_name):
    with allure.step('Create invalid interface ranges'):
        match = re.match(IbConsts.IB_INTERFACE_NAME_REGEX, port_name)
        assert match, "Invalid port name {}".format(port_name)
        prefix = match.group(1)
        numeric_part = int(match.group(2))

        out_of_range_p = prefix + str(numeric_part) + '-' + str(numeric_part + 2) + match.group(3)[0] + '3-5'
        out_of_range_sw = prefix + str(numeric_part) + '-' + str(numeric_part + 2000) + match.group(3)[0] + '1-2'
        reversed_range = prefix + str(numeric_part + 2) + '-' + str(numeric_part) + match.group(3)[0] + '1-2'
        undefined_range = prefix + str(numeric_part) + '-' + str(numeric_part + 2) + match.group(3)[0] + '2-1'

        return out_of_range_p, out_of_range_sw, reversed_range, undefined_range


def create_new_user(engine):
    with allure.step("Create a new user"):
        system = System(force_api=ApiType.NVUE)
        user_name, password = system.aaa.user.set_new_user(role=SystemConsts.DEFAULT_USER_ADMIN, apply=True)
        user_id = system.aaa.user.get_lslogins(engine=engine, username=user_name)["UID"]
        file_name = "/tmp/cache/portstat-{}".format(user_id)
        logging.info("User created: \nuser_name: {} \npassword: {} \nUID: {}".format(user_name, password, user_id))
        with allure.step("Crate an ssh connection for user {user_name} (UID {uid})".format(user_name=user_name,
                                                                                           uid=user_id)):
            ssh_connection = ConnectionTool.create_ssh_conn(engine.ip,
                                                            user_name, password).get_returned_value()
    return file_name, user_name, ssh_connection


def get_port_range(first: int, last: int, p1_2=0) -> List[str]:
    """
    (2, 4) --> ['sw2p1', 'sw2p2', 'sw3p1', 'sw3p2', 'sw4p1', 'sw4p2']
    (2, 4, p1_2=2) --> ['sw2p2', 'sw3p2', 'sw4p2']
    """
    return [f'sw{x}p{p}' for x in range(first, last + 1) for p in ([p1_2] if p1_2 else [1, 2])]


def verify_files_created(ssh_connection: LinuxSshEngine, directory: str, ports: List[str]):
    if is_bug_active(4079803):
        logger.error("Won't check files due to https://redmine.mellanox.com/issues/4079803")
    else:
        with allure.step('verify that a clear file is added to each port'):
            all_files = ssh_connection.run_cmd('ls {}'.format(directory)).split()
            missing_ports = [port for port in ports if port not in all_files]
            msg = "\n".join("{} is missing".format(port) for port in missing_ports)
            assert not missing_ports, msg
