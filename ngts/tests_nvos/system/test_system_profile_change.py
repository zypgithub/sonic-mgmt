import logging
import pytest
from ngts.tools.test_utils import allure_utils as allure
import random
import time
import os
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_constants.constants_nvos import DatabaseConst
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.constants.constants import LinuxConsts
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool

invalid_cmd_str = ['Invalid config', 'Error', 'command not found', 'Bad Request', 'Not Found', "unrecognized arguments",
                   "error: unrecognized arguments", "invalid choice", "Action failed", "Invalid Command",
                   "You do not have permission", "The requested item does not exist."]
invalid_profile_breakout_mode_change_commands = ['breakout-mode aa adaptive-routing bb',
                                                 'breakout-mode aa adaptive-routing 125',
                                                 'breakout-mode aa',
                                                 'breakout-mode aa adaptive-routing 128']
invalid_profile_adaptive_routing_change_commands = ['adaptive-routing-groups 127',
                                                    'adaptive-routing-groups 1793',
                                                    'adaptive-routing-groups bb']


@pytest.mark.system
@pytest.mark.system_profile_cleanup
def test_system_profile_change_default(engines, devices):
    """
    Test flow:
        1. run nv show system profile
        2. verify default fields
        3. verify default values
    """
    system = System(None)
    with allure.step('Verify default fields'):
        system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(system.profile.show()) \
            .get_returned_value()
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
            system_profile_output, SystemConsts.PROFILE_OUTPUT_FIELDS).verify_result()
        logging.info("All expected fields were found")

    with allure.step("Verify default values"):
        ValidationTool.validate_fields_values_in_output(SystemConsts.PROFILE_OUTPUT_FIELDS,
                                                        devices.dut.system_profile_default_values,
                                                        system_profile_output).verify_result()
        logging.info("All expected values were found")


@pytest.mark.system
@pytest.mark.system_profile_cleanup
def test_system_profile_negative(engines, devices):
    """
    Test flow:
        1. Testing all negative scenarios for action
        2. Verify no changes
    """
    negative_profile_commands = invalid_profile_adaptive_routing_change_commands
    if devices.dut.profile_change_supported:
        negative_profile_commands.extend(invalid_profile_breakout_mode_change_commands)

    system = System(None)
    with allure.step('Negative testing'):
        action_command = 'nv action change system profile'
        for cmd in negative_profile_commands:
            output = engines.dut.run_cmd(action_command + cmd)
            logging.info("Run negative command {}{}".format(action_command, cmd))
            assert any(msg in output for msg in invalid_cmd_str), "FAILED - " + output

    with allure.step('Verify default values'):
        system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(system.profile.show()) \
            .get_returned_value()
        ValidationTool.validate_fields_values_in_output(SystemConsts.PROFILE_OUTPUT_FIELDS,
                                                        devices.dut.system_profile_default_values,
                                                        system_profile_output).verify_result()
        logging.info("All expected values were found")


@pytest.mark.system
@pytest.mark.system_profile_cleanup
def test_system_profile_adaptive_routing(engines, players, interfaces, start_sm, devices, setup_name):
    """
    Test flow:
        1. Check that with different routing group we have traffic
        2. Disable adaptive routing
        3. Return system to default
    """
    system = System(None)
    with allure.step("Verify correct Noga setup"):
        traffic_hosts = [engines.ha, engines.hb]
        assert engines.ha and engines.hb, "Traffic hosts details can't be found in Noga setup"

    with allure.step("Check traffic port up"):
        active_ports = Tools.RandomizationTool.get_random_active_port(number_of_values_to_select=0).get_returned_value()
        for port in active_ports:
            port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_UP,
                                               logical_state=NvosConsts.LINK_LOG_STATE_ACTIVE).verify_result()

    with allure.step('Check host ports up'):
        for host in traffic_hosts:
            _check_port_up_on_hosts(host)

    with allure.step("Run traffic"):
        Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()

    with allure.step('Change adaptive-routing-groups, check changes and traffic'):
        with allure.step("Change adaptive-routing-groups to possible value"):
            positive_group_value = random.randrange(128, 1792, 128)

            params = {'adaptive-routing-groups': positive_group_value}
            system.profile.action_profile_change(params_dict=params)

        with allure.step("Start OpenSm"):
            OpenSmTool.start_open_sm(engines).verify_result()

        with allure.step('Verify changed values'):
            system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(system.profile.show()) \
                .get_returned_value()
            values_to_verify = [SystemConsts.PROFILE_STATE_ENABLED, positive_group_value,
                                SystemConsts.PROFILE_STATE_ENABLED, SystemConsts.PROFILE_STATE_DISABLED,
                                SystemConsts.DEFAULT_NUM_SWIDS]
            ValidationTool.validate_fields_values_in_output(SystemConsts.PROFILE_OUTPUT_FIELDS,
                                                            values_to_verify,
                                                            system_profile_output).verify_result()
            logging.info("All expected values were found")

        update_timezone(engines)

        with allure.step("Check traffic port up"):
            for port in active_ports:
                port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_UP,
                                                   logical_state=NvosConsts.LINK_LOG_STATE_ACTIVE).verify_result()

        with allure.step('Check host ports up'):
            for host in traffic_hosts:
                _check_port_up_on_hosts(host)

        with allure.step("Run traffic"):
            Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()

    with allure.step('Change system profile to default'):
        change_profile_to_default(system, devices, engines)

        with allure.step("Start OpenSm"):
            OpenSmTool.start_open_sm(engines).verify_result()

        with allure.step("Check traffic port up"):
            for port in active_ports:
                port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_UP,
                                                   logical_state=NvosConsts.LINK_LOG_STATE_ACTIVE).verify_result()

        with allure.step('Check host ports up'):
            for host in traffic_hosts:
                _check_port_up_on_hosts(host)

        with allure.step("Run traffic"):
            Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()


@pytest.mark.system
@pytest.mark.system_profile_cleanup
def test_system_profile_changes_stress(engines, devices):
    """
    Test flow:
        1. Stress system
        2. Check we can change profile during stress
    """
    system = System(None)
    logging.info("*********** CLI Stress Test ({}) *********** ".format(engines.dut.ip))
    num_of_iterations = 10

    cmd = 'nv show system version'
    logging.info("Run " + cmd)
    _run_cmd_nvue(engines, [cmd], num_of_iterations)
    logging.info(cmd + " succeeded -----------------------------------")

    cmd = 'nv show interface eth0 link'
    logging.info("Run " + cmd)
    _run_cmd_nvue(engines, [cmd], num_of_iterations)
    logging.info(cmd + " succeeded -----------------------------------")

    cmds = ['nv show platform firmware', 'nv show interface eth0 link']
    logging.info("Run " + cmds[0] + " and " + cmds[1])
    _run_cmd_nvue(engines, cmds, num_of_iterations)
    logging.info(cmds[0] + "and" + cmds[1] + " succeeded -----------------------------------")

    with allure.step('Check that we can change system profile during stress test'):
        with allure.step("Enable adaptive-routing and enable breakout-mode, configure groups"):
            positive_group_value = random.randrange(128, 1792, 128)
            system.profile.action_profile_change(
                params_dict={'adaptive-routing-groups': positive_group_value})
            system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(system.profile.show()) \
                .get_returned_value()
            values_to_verify = [SystemConsts.PROFILE_STATE_ENABLED, positive_group_value,
                                SystemConsts.PROFILE_STATE_ENABLED, SystemConsts.PROFILE_STATE_DISABLED,
                                SystemConsts.DEFAULT_NUM_SWIDS]
            ValidationTool.validate_fields_values_in_output(SystemConsts.PROFILE_OUTPUT_FIELDS,
                                                            values_to_verify,
                                                            system_profile_output).verify_result()

        with allure.step('Verify default values'):
            change_profile_to_default(system, devices, engines)


@pytest.mark.system
@pytest.mark.system_profile_cleanup
def test_system_profile_redis_db_crash(engines, devices):
    """
    Test flow:
        1. Write to config db adaptive routing group value
        2. Check changes
        3. Change system profile to default, verify changes
    """
    system = System(None)
    with allure.step('Write value to adaptive routing groups via redis cli'):
        redis_cli_output = Tools.DatabaseTool.sonic_db_cli_hset(engine=engines.dut, asic="", db_name=DatabaseConst.CONFIG_DB_NAME,
                                                                db_config="DEVICE_METADATA|localhost", param="ar_groups", value="777")
        assert redis_cli_output != 0, "Redis command failed"

    with allure.step('Verify changed values'):
        system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(system.profile.show()) \
            .get_returned_value()
        values_to_verify = [SystemConsts.PROFILE_STATE_ENABLED, 777,
                            SystemConsts.PROFILE_STATE_ENABLED, SystemConsts.PROFILE_STATE_DISABLED,
                            SystemConsts.DEFAULT_NUM_SWIDS]
        ValidationTool.validate_fields_values_in_output(SystemConsts.PROFILE_OUTPUT_FIELDS,
                                                        values_to_verify,
                                                        system_profile_output).verify_result()

    with allure.step('Change system profile to default'):
        change_profile_to_default(system, devices, engines)


def change_profile_to_default(system, devices, engines):
    with allure.step('Change system profile to default'):
        system.profile.action_profile_change(
            params_dict={SystemConsts.PROFILE_ADAPTIVE_ROUTING_GROUPS:
                         devices.dut.system_profile_default_values[SystemConsts.PROFILE_ADAPTIVE_ROUTING_GROUPS_INDEX]})
        system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(system.profile.show()) \
            .get_returned_value()
        ValidationTool.validate_fields_values_in_output(SystemConsts.PROFILE_OUTPUT_FIELDS,
                                                        devices.dut.system_profile_default_values,
                                                        system_profile_output).verify_result()
        logging.info("All values returned successfully")

    update_timezone(engines)


def _check_port_up_on_hosts(host, state='Up', tries=10, timeout=1):
    for _ in range(tries):
        link_info_output = host.run_cmd('ibdev2netdev')
        if state in link_info_output:
            break
        elif state not in link_info_output:
            time.sleep(timeout)
            continue
        else:
            assert 'Traffic port on host not in {} state'.format(state)


def _run_cmd_nvue(engines, cmds_to_run, num_of_iterations):
    with allure.step("Run commands for {} iterations".format(num_of_iterations)):
        i = num_of_iterations
        try:
            for i in range(0, num_of_iterations):
                for cmd in cmds_to_run:
                    logging.info("Run {} iterations of {}".format(cmd, i))
                    output = engines.dut.run_cmd(cmd)
                    if any(msg in output for msg in invalid_cmd_str):
                        raise Exception("FAILED - " + output)
                i -= 1
        except BaseException as ex:
            raise Exception("Failed during iteration #{}: {}".format(i, str(ex)))


def update_timezone(engines):
    with allure.step("Update timezone"):
        logging.info(
            "Configuring same time zone for dut and local engine to {}".format(LinuxConsts.JERUSALEM_TIMEZONE))
        ClockTools.set_timezone(LinuxConsts.JERUSALEM_TIMEZONE, System(), apply=True).verify_result()
        with allure.step('Set timezone using timedatectl command'):
            os.popen('sudo timedatectl set-timezone {}'.format(LinuxConsts.JERUSALEM_TIMEZONE))
