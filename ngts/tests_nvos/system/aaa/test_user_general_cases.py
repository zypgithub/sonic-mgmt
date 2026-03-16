import logging
import random
import time

import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.nvos_constants.constants_nvos import SystemConsts, DatabaseConst, ApiType
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tests_nvos.general.security.test_login_ssh_notification.test_login_ssh_notification import parse_ssh_login_notification
from ngts.tests_nvos.general.security.test_login_ssh_notification.constants import LoginSSHNotificationConsts
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.simx
def test_delete_user_with_multiple_terminals(engines):
    """
    Test flow:
            1. create new user random [viewer, configurator]
            2. connect multiple times using the new user
            3. delete new user
            5. verify the user name is not exist if delete.
                all the terminals are not connected if disconnect, disable
            6. same steps for a  user
    """
    with allure.step('Create new user'):
        system = System(force_api=ApiType.NVUE)
        username, password = system.aaa.user.set_new_user(apply=True)

    with allure.step(f'Connect multiple times with user "{username}"'):
        num_connections = 5
        connections = [ConnectionTool.create_ssh_conn(engines.dut.ip, username, password) for _ in range(num_connections)]

    with allure.step(f'delete user "{username}" with {num_connections} connections'):
        system.aaa.user.user_id[username].unset(apply=True).verify_result()
        verify_after_delete(system, username, engines.dut)


@pytest.mark.system
@pytest.mark.simx
def test_disconnect_user_with_multiple_terminals(engines):
    """
    Test flow:
            1. create new user random [viewer, configurator]
            2. connect multiple times using the new user
            3. disconnect new user
            5. verify the user name is not exist if delete.
                all the terminals are not connected if disconnect, disable
            6. same steps for a  user
    """
    num_connections = 3

    with allure.step('Set new user'):
        username, password = System(force_api=ApiType.NVUE).aaa.user.set_new_user(username='test', apply=True)

    with allure.step(f'Make {num_connections} connections with user {username}'):
        connections = [ConnectionTool.create_ssh_conn(engines.dut.ip, username, password).get_returned_value()
                       for _ in range(num_connections)]

    with allure.step('disconnect {username} with {conn} connection'.format(username=username, conn=num_connections)):
        system = System()
        system.aaa.user.user_id[username].action_disconnect().verify_result()
        verify_after_disconnect(engines.dut, system, username, password)


@pytest.mark.system
@pytest.mark.simx
def test_disable_user_with_multiple_terminals(engines):
    """
    Test flow:
            1. create new user random [viewer, configurator]
            2. connect multiple times using the new user
            3. disable new user
            5. verify the user name is not exist if delete.
                all the terminals are not connected if disconnect, disable
            6. same steps for a  user
    """
    with allure.step('Create new user'):
        system = System(force_api=ApiType.NVUE)
        username, password = system.aaa.user.set_new_user(apply=True)

    with allure.step(f'Connect multiple times with user "{username}"'):
        num_connections = 3
        connections = [ConnectionTool.create_ssh_conn(engines.dut.ip, username, password) for _ in range(num_connections)]

    with allure.step(f'disable user "{username}" with {num_connections} connections'):
        system.aaa.user.user_id[username].set(SystemConsts.USER_STATE, SystemConsts.USER_STATE_DISABLED, apply=True).verify_result()
        verify_after_disable(engines.dut, system, username, password, num_connections)


@pytest.mark.system
@pytest.mark.simx
def test_disconnect_nonuser(engines):
    """
    Test flow:
            1. generate username
            2. run nv action disconnect system aaa user <username>
            3. verify output message includes "No such user"
    """
    with allure.step('Disconnect a random username'):
        system = System()
        username = system.aaa.user.generate_username()
        output = system.aaa.user.user_id[username].action_disconnect().get_returned_value(False)

    with allure.step('Verify user do not exist error'):
        assert 'does not exist' in output, "{username} is not a user!".format(username=username)


@pytest.mark.system
@pytest.mark.simx
def test_disconnect_all_users(engines):
    """
    Test flow:
            1. create new users [admin, monitor]
            2. connect the new users once
            3. run nv action disconnect system aaa user
            4. validate disconnect from all the users

    """
    with allure.step('Set new user'):
        username1, password1 = System(force_api=ApiType.NVUE).aaa.user.set_new_user(username='admin1', role=SystemConsts.DEFAULT_USER_ADMIN)
        username2, password2 = System(force_api=ApiType.NVUE).aaa.user.set_new_user(username='monitor1', apply=True)

    with allure.step(f'Create connections with users "{username1}" and "{username2}"'):
        connections = [ConnectionTool.create_ssh_conn(engines.dut.ip, username, password).get_returned_value()
                       for username, password in [(username1, password1), (username2, password2)]]

    with allure.step('Disconnect all users'):
        system = System()
        system.aaa.user.action_disconnect().verify_result()
        # DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut,
        #                                    command="nv action disconnect system aaa user").verify_result()
        # logger.info("sleep 5 sec after the disconnection")
        # time.sleep(5)
        for connection in connections:
            verify_after_disconnect(engines.dut, system, connection.username, connection.password)


@pytest.mark.system
@pytest.mark.simx
def test_unset_then_set_back_same_user(engines):
    """
    Test that a user that was unset and then set back has a clean state (no errors, connection count reset).

    Test flow:
        1. Set new user [viewer, configurator]
        2. Connect using the new user
        3. Unset new user
        4. Set back the same user
        5. Connect again using the same user
        6. Verify connection count is reset to 0 and got no errors

    """
    system = System(force_api=ApiType.NVUE)

    with allure.step('Configure SSH server login-record-period to ensure connection count tracking'):
        # Set login-record-period to 1 day (minimum value) to enable connection count tracking
        system.ssh_server.set(LoginSSHNotificationConsts.RECORD_PERIOD, 1, apply=True).verify_result()

    # Randomize user role
    available_roles = [SystemConsts.ROLE_VIEWER, SystemConsts.ROLE_CONFIGURATOR]
    selected_role = random.choice(available_roles)

    with allure.step(f'Create new user with role: {selected_role}'):
        username, password = system.aaa.user.set_new_user(role=selected_role, apply=True)

    with allure.step(f'Connect using user "{username}"'):
        ConnectionTool.create_ssh_conn(engines.dut.ip, username, password).verify_result()

    with allure.step(f'Unset user "{username}"'):
        system.aaa.user.user_id[username].unset(apply=True).verify_result()
        verify_after_delete(system, username, engines.dut)

    # wait for the logs to be written to the file (sometimes I/O could be slower)
    time.sleep(5)

    with allure.step(f'Verify user deletion logged in /var/log/auth.log'):
        auth_log = engines.dut.run_cmd(f"sudo grep \"userdel\\[.*\\]: delete user '{username}'\" /var/log/auth.log | tail -1")
        assert auth_log.strip(), f"Expected 'userdel: delete user {username}' in auth.log but not found"

    # wait for the logs to be written to the file (sometimes I/O could be slower)
    time.sleep(5)

    with allure.step(f'Set back user "{username}" with role: {selected_role}'):
        system.aaa.user.user_id[username].set('role', selected_role).verify_result()
        system.aaa.user.user_id[username].set(SystemConsts.USER_PASSWORD, password, apply=True).verify_result()

    with allure.step(f'Verify user re-creation logged in /var/log/auth.log'):
        auth_log = engines.dut.run_cmd(f"sudo grep \"usermod\\[.*\\]: change user '{username}' password\" /var/log/auth.log | tail -1")
        assert auth_log.strip(), f"Expected 'usermod: change user {username} password' in auth.log after set-back but not found"

    with allure.step(f'Connect again with user "{username}" and verify clean state'):
        # Note: Errors in SSH notification (like date parsing errors) are checked by parse_ssh_login_notification()
        login_notification = parse_ssh_login_notification(engines.dut.ip, username, password, assert_last_login=False, assert_no_errors=True)

        # Verify number of successful connections is reset (should be 0)
        successful_connections = login_notification.get('number_of_successful_connections_in_the_last_record_period')
        assert successful_connections == '0', \
            f"User should have 0 successful connections in history, but got: {successful_connections}"


def kill_no_tty_processes(dut_engine, username):
    """
    Kill no-tty processes related to the given user.

    When setting up a connection with our engine, it sets another no-tty process (that terminates after some time),
    which make this testing unstable. Therefore, kill all those processes for that user, rather than wait till
    they terminate by themselves.

    @param dut_engine: dut engine object
    @param username: given username
    """
    pids_to_kill = [pid.split()[1] for pid in dut_engine.run_cmd(f'ps aux | grep {username}@notty').split('\n')]
    if pids_to_kill:
        dut_engine.run_cmd(f'sudo kill {" ".join(pids_to_kill)}')


def check_user_num_connections(username, expected_num_connections, system_obj: System, dut_engine):
    with allure.step('Kill no tty processes'):
        kill_no_tty_processes(dut_engine, username)

    with allure.step(f'Verify num connections of "{username}" is {expected_num_connections}'):
        expected_num_user_processes = expected_num_connections * 2 + 2
        running_processes = system_obj.aaa.user.get_lslogins(dut_engine, username)[
            SystemConsts.PASSWORD_HARDENING_RUNNING_PROCESSES]
        assert int(
            running_processes) is expected_num_user_processes, \
            "user '{user}' processes count is {run_proc} not as expected {expected}".format(
                user=username, run_proc=running_processes, expected=expected_num_user_processes)


def verify_after_disconnect(dut_engine, system, username, password, connections_count=0):
    """
    :param dut_engine: dut engine
    :param system: system obj
    :param username: username
    :param password: user password
    :param connections_count: connections count
    :return:
    """
    with allure.step(f'verify {username} state still enabled'):
        output = OutputParsingTool.parse_json_str_to_dictionary(
            system.aaa.user.user_id[username].show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(output, SystemConsts.USER_STATE,
                                                    SystemConsts.USER_STATE_ENABLED).verify_result()

    with allure.step(f'verify {username} running processes count'):
        check_user_num_connections(username, connections_count, system, dut_engine)

    ConnectionTool.create_ssh_conn(dut_engine.ip, username, password).verify_result()
    with allure.step('verify {user} running processes count after the new connection'.format(user=username)):
        check_user_num_connections(username, connections_count + 1, system, dut_engine)


def verify_after_disable(dut_engine, system, username, password, connections_count):
    """

    :param dut_engine: dut engine
    :param system: system obj
    :param username: username
    :param password: user password
    :param connections_count: connections count
    :return:
    """
    with allure.step(f'verify after disabling username: {username}'):
        with allure.step(f'verify {username} state is disabled'):
            show_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.user.user_id[username].show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(show_output, SystemConsts.USER_STATE,
                                                        SystemConsts.USER_STATE_DISABLED).verify_result()

        with allure.step(f'verify no running processes for user "{username}"'):
            check_user_num_connections(username, 0, system, dut_engine)

        with allure.step(f'verify we can not connect with {username}'):
            ConnectionTool.create_ssh_conn(dut_engine.ip, username, password).verify_result(False)


def verify_after_delete(system, username, dut_engine):
    """

    :param system: system obj
    :param username: username
    :param dut_engine: dut engine
    :return:
    """
    with allure.step(f'verify after delete username: {username}'):
        with allure.step(f'check {username} show command'):
            show_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.user.show()).get_returned_value()
            assert username not in show_output.keys(), "the show output is: {out} not as expected".format(
                out=show_output)

        with allure.step(f'check if {username} in config_DB'):
            redis_output = Tools.DatabaseTool.sonic_db_cli_get_keys(engine=dut_engine, asic="",
                                                                    db_name=DatabaseConst.CONFIG_DB_NAME,
                                                                    grep_str=username)
            # redis_output = dut_engine.run_cmd('sudo redis-cli -n 4 keys * | grep {user}'.format(user=username))
            assert not redis_output, "a deleted user key still in the config db"

        with allure.step(f'check if {username} in all users list'):
            show_output = system.aaa.user.get_lslogins(engine=dut_engine, username=username)
            assert f"lslogins: cannot found '{username}'" in show_output, "a deleted username still users list"
