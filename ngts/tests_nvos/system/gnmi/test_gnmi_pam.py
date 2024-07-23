import random
import time
from subprocess import Popen
from typing import List

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import TestFlowType
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.conftest import local_adminuser
from ngts.tests_nvos.general.security.security_test_tools.constants import AuthConsts, AaaConsts
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.constants import RemoteAaaType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, MAX_GNMI_SUBSCRIBERS, GnmicErr
from ngts.tests_nvos.system.gnmi.helpers import verify_gnmi_client, change_interface_description, \
    verify_msg_in_out_or_err, verify_msg_not_in_out_or_err
from ngts.tools.test_utils.nvos_general_utils import wait_for_ldap_nvued_restart_workaround
from ngts.tools.test_utils.switch_recovery import generate_strong_password


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_gnmi_authentication(test_flow, engines, local_adminuser, aaa_users):
    """
    verify that gnmi clients must be properly authenticated to subscribe and get updates

    1. set local-user/AAA-method
    2. good-flow: subscribe with valid user credentials
        bad-flow: subscribe with invalid credentials
    3. change port description
    4. good-flow: expect valid user client gets update
        bad-flow: expect invalid user client doesn't get update
    """
    system = System()
    auth = system.aaa.authentication
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value
    for auth_method in ['default', AuthConsts.LOCAL] + RemoteAaaType.ALL_TYPES:
        with allure.step(f'test with auth method: {auth_method}'):
            user = UserInfo(engines.dut.username, engines.dut.password,
                            'admin') if auth_method == 'default' else local_adminuser
            if auth_method in RemoteAaaType.ALL_TYPES:
                user = aaa_users[auth_method]
                with allure.step(f'enable {auth_method} authentication'):
                    auth.set(AuthConsts.ORDER, f'{auth_method},{AuthConsts.LOCAL}', apply=True).verify_result()
                    if auth_method == RemoteAaaType.LDAP:
                        wait_for_ldap_nvued_restart_workaround(None)
                    else:
                        time.sleep(3)
            verify_gnmi_client(test_flow, engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, user.username,
                               user.password if test_flow == TestFlowType.GOOD_FLOW else 'abcde', True,
                               GnmicErr.AUTH_FAIL, selected_port)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_gnmi_auth_change_local_user_password(test_flow, engines, local_adminuser):
    """
    verify that gnmi properly authenticates local user after password change

    1. change local user's password
    2. good-flow: run client request using new password - expect success
        bad-flow: run client request using old password - expect fail
    """
    with allure.step(f'change password for local user "{local_adminuser.username}"'):
        new_password = generate_strong_password()
        old_password = local_adminuser.password
        System().aaa.user.user_id[local_adminuser.username].set('password', new_password, apply=True).verify_result()
        local_adminuser.password = new_password

    verify_gnmi_client(test_flow, engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, local_adminuser.username,
                       new_password if test_flow == TestFlowType.GOOD_FLOW else old_password, True,
                       GnmicErr.AUTH_FAIL)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_auth_after_remove_local_user(engines, local_adminuser):
    """
    verify that after removing a local user, client cannot request using the credentials of that user

    1. remove local user
    2. run client request using credentials of removed user - expect fail
    """
    with allure.step(f'remove local user "{local_adminuser.username}"'):
        System().aaa.user.user_id[local_adminuser.username].unset(apply=True).verify_result()

    verify_gnmi_client(TestFlowType.BAD_FLOW, engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, local_adminuser.username,
                       local_adminuser.password, True, GnmicErr.AUTH_FAIL)


@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_gnmi_auth_failthrough(test_flow, engines, local_adminuser, aaa_users):
    """
    verify that gnmi client authentication also takes under count the failthrough mechanism properly

    1. configure some auth order with 2 methods (local + remote AAA)
    2. good-flow: enable failthrough
        bad-flow: disable failthrough
    3. run client using credentials of 2nd auth method user
    4. good-flow: expect success
        bad-flow: expect fail
    """
    users_by_auth_method = aaa_users
    users_by_auth_method[AuthConsts.LOCAL] = local_adminuser

    rand_aaa_method = random.choice(RemoteAaaType.ALL_TYPES)
    auth_methods = [AuthConsts.LOCAL, rand_aaa_method]
    random.shuffle(auth_methods)

    order = ','.join(auth_methods)
    method2 = auth_methods[1]
    failthrough = AaaConsts.ENABLED if test_flow == TestFlowType.GOOD_FLOW else AaaConsts.DISABLED

    with allure.step(f'set auth order: {order}'):
        system = System()
        system.aaa.authentication.set(AuthConsts.ORDER, order).verify_result()
    with allure.step(f'set failthrough: {failthrough}'):
        system.aaa.authentication.set(AuthConsts.FAILTHROUGH, failthrough, apply=True).verify_result()
        if rand_aaa_method == RemoteAaaType.LDAP:
            wait_for_ldap_nvued_restart_workaround(None)
        else:
            time.sleep(3)

    user = aaa_users[method2]
    verify_gnmi_client(test_flow, engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, user.username, user.password, True,
                       GnmicErr.AUTH_FAIL)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_auth_existing_streamed_session(engines, local_adminuser):
    """
    verify that when client establishes streamed grpc session with gnmi, any change to user
        (password change, user remove, etc.) doesn't affect/terminate the existing session

    1. set up streamed gnmi session - subscribe to port description
    2. change port description to X
    3. change client user password
    4. change port description to Y
    5. remove the user
    6. change port description to Z
    7. set the user again from scratch
    8. change port description to W
    9. verify that the client received all the port description changes in the existing streaming session
    """
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value
    new_descriptions: List[str] = []

    with allure.step('set up streamed gnmi session - subscribe client to port description'):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, local_adminuser.username,
                            local_adminuser.password)
        session = client.gnmic_subscribe_interface_and_keep_session_alive(GnmiMode.STREAM, selected_port.name,
                                                                          skip_cert_verify=True)
    with allure.step('change port description'):
        new_descriptions.append(change_interface_description(selected_port))
    with allure.step(f'change password of user "{local_adminuser.username}"'):
        user_obj = System().aaa.user.user_id[local_adminuser.username]
        user_obj.set('password', generate_strong_password(), apply=True).verify_result()
    with allure.step('change port description'):
        new_descriptions.append(change_interface_description(selected_port))
    with allure.step(f'remove user "{local_adminuser.username}"'):
        user_obj.unset(apply=True).verify_result()
    with allure.step('change port description'):
        new_descriptions.append(change_interface_description(selected_port))
    with allure.step(f'recreate the user "{local_adminuser.username}"'):
        local_adminuser.password = generate_strong_password()
        user_obj.set('password', local_adminuser.password, apply=True).verify_result()
    with allure.step('change port description'):
        new_descriptions.append(change_interface_description(selected_port))
    with allure.step('verify that client received all new descriptions in the existing streaming session'):
        out, err = client.close_session_and_get_out_and_err(session)
        verify_msg_not_in_out_or_err(GnmicErr.AUTH_FAIL, out, err)
        for new_description in new_descriptions:
            verify_msg_in_out_or_err(new_description, out)


@pytest.mark.system
@pytest.mark.gnmi
def test_gnmi_auth_failing_clients_ddos(engines, local_adminuser):
    """
    verify that gnmi is not blocked when there are existing >10 failed gnmi clients attempting

    1. run 10 gnmi clients with bad credentials (in bg/processes)
    2. run gnmi client with valid credentials
    3. expect success
    """
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value

    with allure.step('run 10 gnmi clients with bad creds in background'):
        invalid_client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, 'abc', 'abc')
        invalid_clients: List[Popen] = []
        for i in range(MAX_GNMI_SUBSCRIBERS):
            with allure.step(f'run invalid gnmi client #{i}'):
                invalid_clients.append(
                    invalid_client.gnmic_subscribe_interface_and_keep_session_alive(GnmiMode.STREAM, selected_port.name,
                                                                                    skip_cert_verify=True))
    with allure.step('run gnmi client with valid creds'):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, local_adminuser.username,
                            local_adminuser.password)
        out, err = client.gnmic_capabilities(skip_cert_verify=True, wait_till_done=True)
    with allure.step('expect success'):
        for err_msg in GnmicErr.ALL_ERRS:
            verify_msg_not_in_out_or_err(err_msg, out, err)
