import time
from datetime import datetime
from typing import List

import pytz

from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.nvos_constants.constants_nvos import TestFlowType
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.AaaServerManager import \
    AaaAccountingLogsFileContent, AaaServerManager
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.AuthVerifier import *
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RemoteAaaServerInfo
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import loganalyzer_ignore


def check_nslcd_service(engines):
    """
    @summary: Check the status of nslcd service, and restart it if needed (for next test cases):
    """
    exit_cmd = 'q'
    status_cmd = 'sudo service nslcd status'
    restart_cmd = 'sudo service nslcd restart'

    with allure.step('Check nslcd service status'):
        output = engines.dut.run_cmd_after_cmd([status_cmd, exit_cmd])
        if 'Active: failed' in output:
            logging.info('Service nslcd failed')
            with allure.step('Restart nslcd service'):
                engines.dut.run_cmd(restart_cmd)
            with allure.step('Check nslcd service status again'):
                output = engines.dut.run_cmd([status_cmd, exit_cmd])
                logging.info(f'Service nslcd is active: {"Active: active (running)" in output}')


def sleep_before_auth(sleep_time: int = 3):
    wait_time_before_auth_test = sleep_time
    logging.info(f'Wait {wait_time_before_auth_test} seconds')
    time.sleep(wait_time_before_auth_test)


def verify_auth_with_medium(medium, user: UserInfo, expect_login_success: bool, verify_authorization: bool, engines,
                            topology_obj):
    with allure.step(f'Verify auth with medium: {medium}'):
        user_is_admin = user.role == AaaConsts.ADMIN
        medium_obj = AUTH_VERIFIERS[medium](user.username, user.password, engines, topology_obj)

        with allure.step(f'Verify authentication. Expect login success: {expect_login_success}'):
            medium_obj.verify_authentication(expect_login_success)

        if verify_authorization and expect_login_success:
            with allure.step(f'Verify authorization. Role: {user.role}'):
                medium_obj.verify_authorization(user_is_admin=user_is_admin)


def clear_accounting_logs_on_servers(accounting_server_mngrs: List[AaaServerManager]):
    with allure.step('Clear accounting logs on servers'):
        for mngr in accounting_server_mngrs:
            mngr.clear_accounting_logs()


def check_accounting(after_time: str, client_ip: str, client_username: str,
                     accounting_server_mngrs: List[AaaServerManager], expect_accounting_logs: List[bool]):
    with allure.step('Verify accounting logs on given servers'):
        for i, mngr in enumerate(accounting_server_mngrs):
            expect_logs = expect_accounting_logs[i]
            with allure.step(f'Check accounting on server: {mngr.ip} , Expect logs: {expect_logs}'):
                accounting_logs: AaaAccountingLogsFileContent = mngr.tail_accounting_logs(
                    grep=[client_ip, client_username], after_time=after_time)
                assert bool(accounting_logs.logs) == expect_logs, \
                    f'There are {"no " if expect_logs else ""}accounting logs ' \
                    f'on server "{mngr.ip}" for user "{client_username}", ' \
                    f'while expected {"" if expect_logs else "not "}to have logs.\n' \
                    f'Actual raw content:\n{accounting_logs.raw_content}'


def verify_user_auth(engines, topology_obj, user: UserInfo, expect_login_success: bool = True,
                     verify_authorization: bool = True, skip_auth_mediums: List[str] = None,
                     accounting_servers: List[RemoteAaaServerInfo] = [], expect_accounting_logs: List[bool] = [],
                     switch_hostname: str = ''):
    """
    @summary: Verify authentication and authorization for the given user.
        Authentication will be verified via all possible mediums - SSH, OpenApi, rcon, SCP.
    @param engines: test engines object
    @param topology_obj: test topology object
    @param user: Details of the given user.
        User is a dictionary in the format:
        {
            username: str,
            password: str,
            role: admin/monitor (str)
        }
    @param expect_login_success: boolean flag, whether login expected to succeed (True) or fail (False).
        Default is True.
    @param verify_authorization: Whether to verify also authorization or not (authentication test only)
    @param skip_auth_mediums: auth mediums to skip from the test (optional)
    """
    assert len(accounting_servers) == len(expect_accounting_logs), \
        f'Arguments "accounting_servers" and "expect_accounting_logs" must be lists of the same length!\n' \
        f'Actual accounting_servers: {accounting_servers}\nActual expect_accounting_logs: {expect_accounting_logs}'

    should_check_accounting = bool(accounting_servers)
    accounting_server_mngrs = [AaaServerManager(server.ipv4_addr, server.docker_name) for server in accounting_servers]
    if should_check_accounting:
        assert switch_hostname, f'Must give "switch_hostname" argument when should check accounting.\n' \
            f'Given hostname: {switch_hostname}'

    with loganalyzer_ignore(False and (not expect_login_success)):
        with allure.step(f'Verify auth: User: {user.username} , Password: {user.password} , Role: {user.role} , '
                         f'Expect login success: {expect_login_success}'):
            sleep_before_auth()

            # for ssh, openapi, rcon: test authentication, and then verify role by running show, set, unset commands
            for medium in AuthMedium.ALL_MEDIUMS:
                if skip_auth_mediums and medium in skip_auth_mediums:
                    continue

                time_at_server: str = datetime.now(pytz.utc).strftime('%b %d %H:%M:%S')  # servers have UTC timezone
                verify_auth_with_medium(medium, user, expect_login_success, verify_authorization, engines, topology_obj)

                if should_check_accounting:
                    check_accounting(time_at_server, switch_hostname, user.username, accounting_server_mngrs,
                                     expect_accounting_logs)

            logging.info('\n')


def verify_auth_mediums(test_flow: str, engines, topology_obj,
                        remote_should_work: bool, local_should_work: bool,
                        server: RemoteAaaServerInfo = None,
                        remote_users_roles_to_check: List[str] = None, local_users: List[UserInfo] = None,
                        verify_authorization: bool = True, skip_auth_mediums: List[str] = None,
                        accounting_servers: List[RemoteAaaServerInfo] = [], expect_accounting_logs: List[bool] = [],
                        switch_hostname: str = ''):
    '''
    if should check accounting:
        accounting_preparations()

    for each medium:
        if good flow:
            if remote_should_work:
                (remote_should_work contains ROLES that should check)
                for each role in remote_should_work:
                    user = server.users_per_medium[medium][role]
                    verify_auth_with_medium(user, expect=is_good_flow)

        if bad flow:
            pass

        if should check accounting:
            accounting_check()
    '''
    is_good_flow = test_flow == TestFlowType.GOOD_FLOW

    assert len(accounting_servers) == len(expect_accounting_logs), \
        f'Arguments "accounting_servers" and "expect_accounting_logs" must be lists of the same length!\n' \
        f'Actual accounting_servers: {accounting_servers}\nActual expect_accounting_logs: {expect_accounting_logs}'

    should_check_accounting = bool(accounting_servers)
    accounting_server_mngrs = [AaaServerManager(server.ipv4_addr, server.docker_name) for server in accounting_servers]
    if should_check_accounting:
        assert switch_hostname, f'Must give "switch_hostname" argument when should check accounting.\n' \
            f'Given hostname: {switch_hostname}'

    auth_mediums = [medium for medium in AuthMedium.ALL_MEDIUMS if (not skip_auth_mediums) or (medium not in skip_auth_mediums)]
    with allure.step(f'verify auth through mediums: {auth_mediums}'):
        for medium in auth_mediums:
            with allure.independent_step(medium):
                sleep_before_auth()
                time_at_server: str = datetime.now(pytz.utc).strftime('%b %d %H:%M:%S')  # our AAA servers have UTC timezone

                if (is_good_flow == remote_should_work) and remote_users_roles_to_check:
                    with allure.independent_step(f'{test_flow} remote users check'):
                        for role in remote_users_roles_to_check:
                            with allure.independent_step(role):
                                user = server.users_per_auth_medium[medium][role][0]
                                with allure.step(f'{user.username} / {user.password} ({user.role}, {medium}) - {remote_should_work}'):
                                    verify_auth_with_medium(medium, user, remote_should_work, verify_authorization, engines, topology_obj)
                if (is_good_flow == local_should_work) and local_users:
                    with allure.independent_step(f'{test_flow} local users check'):
                        for user in local_users:
                            with allure.independent_step(f'{user.username} / {user.password} ({user.role}, {medium}) - {local_should_work}'):
                                verify_auth_with_medium(medium, user, local_should_work, verify_authorization, engines, topology_obj)

                if should_check_accounting:
                    with allure.step('check accounting'):
                        check_accounting(time_at_server, switch_hostname, user.username, accounting_server_mngrs,
                                         expect_accounting_logs)


def verify_users_auth(engines, topology_obj, users: List[UserInfo], expect_login_success: List[bool] = None,
                      verify_authorization: bool = True, skip_auth_mediums: List[str] = None):
    """
    @summary: Verify authentication and authorization for the given users.
        Authentication will be verified via all possible mediums - SSH, OpenApi, rcon, SCP.
    @param engines: test engines object
    @param topology_obj: test topology object
    @param users: list of users to verify.
        User is a dictionary in the format:
        {
            username: str,
            password: str,
            role: admin/monitor (str)
        }
    @param expect_login_success: list of boolean flags, whether login expected to succeed (True) or fail (False).
        Default is True for all users.
    @param verify_authorization: Whether to verify also authorization or not (authentication test only)
    @param skip_auth_mediums: auth mediums to skip from the test (optional)
    """
    expect_login_success = [True] * len(users) if not expect_login_success else expect_login_success

    for i, user in enumerate(users):
        verify_user_auth(engines, topology_obj, user, expect_login_success[i], verify_authorization, skip_auth_mediums)


def validate_users_authorization_and_role(engines, users, login_should_succeed=True, check_nslcd_if_login_failed=False):
    """
    @summary:
        in this function we want to iterate on all users given and validate that access to switch
        and role as expected.
        We will restore the engine to default credentials afterwards
    """
    for user in users:
        username = user[AaaConsts.USERNAME]
        password = user[AaaConsts.PASSWORD]
        role = user[AaaConsts.ROLE]
        with allure.step(f"Check user: {username} , password: {password} , role: {role}"):
            with allure.step(f'Try login - expect: {"success" if login_should_succeed else "fail"}'):
                try:
                    new_engine = ProxySshEngine(device_type=engines.dut.device_type, ip=engines.dut.ip,
                                                username=username, password=password)
                    new_engine.run_cmd('')
                    # engines.dut.update_credentials(username=username, password=password)
                except Exception:
                    logging.info("Got an exception - can not connect to switch")
                    if check_nslcd_if_login_failed:
                        check_nslcd_service(engines)
                    assert not login_should_succeed, 'Login fail, expect success'
                    continue
                assert login_should_succeed, 'Login success, expect fail'

            SLEEP_BEFORE_EXECUTING_CMDS = 1
            with allure.step("Sleeping {} secs before executing commands".format(SLEEP_BEFORE_EXECUTING_CMDS)):
                time.sleep(SLEEP_BEFORE_EXECUTING_CMDS)
                if role == AaaConsts.ADMIN:
                    with allure.step('FOR DEBUG - after login, run: sudo stat /var/log/audit.log'):
                        new_engine.run_cmd('sudo stat /var/log/audit.log')

            with allure.step("Running show command - expect: success"):
                system = System(None)
                try:
                    system.version.show(dut_engine=new_engine)
                except Exception as ex:
                    logging.info("Got an exception - can not run show command")
                    raise ex

            is_admin = role == SystemConsts.DEFAULT_USER_ADMIN

            with allure.step(f'Run set command - expect: {"success" if is_admin else "fail"}'):
                system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value='"NVOS TESTS"',
                                   apply=is_admin, dut_engine=new_engine).verify_result(should_succeed=is_admin)

            with allure.step(f'Run unset command - expect: {"success" if is_admin else "fail"}'):
                system.message.unset(op_param=SystemConsts.PRE_LOGIN_MESSAGE, apply=is_admin,
                                     dut_engine=new_engine).verify_result(should_succeed=is_admin)

    # for user_info in users:
    #     username = user_info[AaaConsts.USERNAME]
    #     password = user_info[AaaConsts.PASSWORD]
    #     role = user_info[AaaConsts.ROLE]
    #
    #     with allure.step(f'Verify authentication {username}'):
    #         authenticator = SshAuthenticator(username, password, engines.dut.ip)
    #         login_succeeded, _ = authenticator.attempt_login_success(logout_if_succeeded=False)
    #         assert login_succeeded == login_should_succeed, \
    #             f'User {username} could {"" if login_succeeded else "not "}login'
    #
    #     if login_should_succeed:
    #         with allure.step(f'Verify role of {username}: {role}'):
    #             with allure.step(f'Verify user {username} can make show command'):
    #                 _, _, output = authenticator.send_cmd(AuthConsts.SHOW_COMMAND, AuthConsts.SWITCH_PROMPT_PATTERN)
    #                 assert AuthConsts.PERMISSION_ERROR not in output, \
    #                     f'User {username} do not have permission to run "{AuthConsts.SHOW_COMMAND}"'
    #
    #             can_set = role == AaaConsts.ADMIN
    #             with allure.step(f'Verify user {username} can {"" if can_set else "not "}make set command'):
    #                 _, _, output = authenticator.send_cmd(AuthConsts.SET_COMMAND, AuthConsts.SWITCH_PROMPT_PATTERN)
    #                 cond = AuthConsts.PERMISSION_ERROR not in output if can_set else AuthConsts.PERMISSION_ERROR in output
    #                 assert cond, f'User {username} do not have permission to run "{AuthConsts.SET_COMMAND}"'
    #
    #     del authenticator


def find_server_admin_user(server_info):
    admin_user = None
    for user in server_info[AuthConsts.USERS]:
        if user[AaaConsts.ROLE] == AaaConsts.ADMIN:
            admin_user = user
    assert admin_user, "Couldn't find admin user, check server configuration"
    return admin_user


def restore_original_engine_credentials(engines, devices):
    """
    @summary:
        in this fixture we will restore default credentials to dut engine
    """
    logging.info("Restoring default credentials, and logging in to switch")
    engines.dut.update_credentials(username=devices.dut.default_username,
                                   password=devices.dut.default_password)


def validate_authentication_fail_with_credentials(engines, username, password):
    """
    @summary: in this helper function we want to validate authentication failure while using
    username and password credentials
    """
    with allure.step("Validating failed authentication with new credentials, username: {}".format(username)):
        ConnectionTool.create_ssh_conn(engines.dut.ip, username=username, password=password).verify_result(
            should_succeed=False)


def validate_services_and_dockers_availability(engines, devices):
    """
    @summary: validate all services and dockers are up
    """
    with allure.step("validating all services and dockers are up"):
        devices.dut.verify_dockers(engines.dut).verify_result()
        devices.dut.verify_services(engines.dut).verify_result()


def configure_authentication(engines, devices, order=None, failthrough=None, fallback=None, apply=False,
                             dut_engine=None):
    """
    @summary:
        Configure different authentication settings as given
    """
    if order == failthrough == fallback is None:
        return

    dut_engine = engines.dut if not dut_engine else dut_engine

    with allure.step('Configure authentication settings'):
        auth_obj = System().aaa.authentication
        if order:
            logging.info(f'Set authentication order: {order}')
            order = ','.join(order)
            auth_obj.set(AuthConsts.ORDER, order, dut_engine=dut_engine).verify_result()
        if failthrough:
            logging.info(f'Set authentication failthrough: {failthrough}')
            auth_obj.set(AuthConsts.FAILTHROUGH, failthrough, dut_engine=dut_engine).verify_result()
        # if fallback:
        #     logging.info(f'Set authentication fallback: {fallback}')
        #     auth_obj.set(AuthConsts.FALLBACK, fallback).verify_result()

    if apply:
        with allure.step('Apply settings'):
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config, dut_engine,
                                            True)

        if order:
            with allure.step('Validate that services and dockers are up'):
                DutUtilsTool.wait_for_nvos_to_become_functional(engines.dut)


def user_lists_difference(users_a, users_b):
    """
    @summary: Get the difference of the two given user lists.
        * Difference (like sets difference): A - B = all elements of A that are not in B.
        * Here, the elements are users (dictionaries {username: str, password: str, role: <admin, monitor>}),
            then the result will be all users of A, that don't have the same username as any user of B.
    @param users_a: users list A
    @param users_b: users list B
    @return: list of the difference.
    """
    with allure.step('Get users lists difference'):
        a_usernames = [user[AaaConsts.USERNAME] for user in users_a]
        b_usernames = [user[AaaConsts.USERNAME] for user in users_b]
        logging.info(f'A: {a_usernames}\nB: {b_usernames}')

        usernames_diff = list(set(a_usernames) - set(b_usernames))
        logging.info(f'Diff: {usernames_diff}')

        return [user for user in users_a if user[AaaConsts.USERNAME] in usernames_diff]


def mutual_users(users_a, users_b):
    """
    @summary: Get the mutual of the two given user lists.
    @param users_a: users list A
    @param users_b: users list B
    @return: list of the mutual users.
    """
    with allure.step('Get mutual users list'):
        a_usernames = [user[AaaConsts.USERNAME] for user in users_a]
        b_usernames = [user[AaaConsts.USERNAME] for user in users_b]
        logging.info(f'A: {a_usernames}\nB: {b_usernames}')

        mutual_usernames = list(set(a_usernames).intersection(set(b_usernames)))
        logging.info(f'Mutual users: {mutual_usernames}')

        return [user for user in users_a if user[AaaConsts.USERNAME] in mutual_usernames]


def set_local_users(engines, users, apply=False):
    """
    @summary: Set the given users on local.
        * users should be a list of users.
        * a user should be a dictionary in the following format:
            {
                username: str ,
                password: str ,
                role: <admin, monitor>
            }
    @param engines: engines object
    @param users: users list (list of dictionaries)
    """
    with allure.step(f'Set {len(users)} local users'):
        for user in users:
            if isinstance(user, UserInfo):
                username = user.username
                password = user.password
                role = user.role
            else:
                username = user[AaaConsts.USERNAME]
                password = user[AaaConsts.PASSWORD]
                role = user[AaaConsts.ROLE]
            with allure.step(f'Set user "{username}" with role: {role}'):
                user_obj = System(force_api=ApiType.NVUE).aaa.user.user_id[username]
                logging.info(f'Set user: {username} , password: {password}')
                user_obj.set(AaaConsts.PASSWORD, password).verify_result()
                logging.info(f'Set user: {username} , role: {role}')
                user_obj.set(AaaConsts.ROLE, role).verify_result()

    if apply:
        with allure.step('Apply changes together'):
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config, engines.dut,
                                            True)


def check_ldap_user_with_getent_passwd(engine: ProxySshEngine, username: str, user_should_exist: bool):
    with allure.step('Get getent passwd output'):
        output = engine.run_cmd('getent passwd | grep ldap')
    with allure.step(f'Verify "{username}" does not exist'):
        err_msg = f'username "{username}" unexpectedly {"does not " if not user_should_exist else ""}exist ' \
            f'in getent passwd output\ngetent passwd output: {output}\n'
        if not output:
            assert not user_should_exist, err_msg
        else:
            rows = output.split('\n')
            assert rows, f'Unknown error. Could not split output "{output}" to rows.\nActual split: {rows}'
            assert any(row.startswith(f'{username}:') for row in rows) == user_should_exist, err_msg


def check_ldap_user_groups_with_id(engine: ProxySshEngine, username: str, groupname, group_should_exist: bool):
    with allure.step('Get id output'):
        cmd = f'id {username}'
        output = engine.run_cmd(cmd)

    groups = [groupname] if isinstance(groupname, str) else groupname
    if group_should_exist:
        violating_groups = [group for group in groups if f'({group})' not in output]
    else:
        violating_groups = [group for group in groups if f'({group})' in output]

    assert not violating_groups, (f'some groups violating the expectations.\n'
                                  f'groups that expected{"" if group_should_exist else " not"} to exist for user "{username}": {groups}\n'
                                  f'violating groups: {violating_groups}\n'
                                  f'cmd: {cmd}\n'
                                  f'full output: {output}')
