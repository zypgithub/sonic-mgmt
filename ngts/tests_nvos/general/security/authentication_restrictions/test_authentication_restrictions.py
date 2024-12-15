import logging
import random
import time

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.general_constants.constants import DefaultTestServerCred
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.conftest import topology_obj
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.authentication_restrictions.constants import RestrictionsConsts
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AuthConsts
from ngts.tests_nvos.general.security.security_test_tools.resource_utils import configure_resource
from ngts.tests_nvos.general.security.security_test_tools.switch_authenticators import SshAuthenticator
from ngts.tests_nvos.general.security.tacacs.constants import TacacsDockerServer0, TacacsPhysicalServer
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import loganalyzer_ignore


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.nvos_chipsim_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_authentication_show_commands(test_api, engines):
    """
    @summary: Validate output of relevant show commands

        Steps:
        1. Run show restrictions command
        2. Validate output
        3. Run show authentication command (more general)
        4. Validate output
    """
    TestToolkit.tested_api = test_api

    with allure.step('Run show restrictions command'):
        auth_obj = System().aaa.authentication
        output1 = OutputParsingTool.parse_json_str_to_dictionary(auth_obj.restrictions.show()).get_returned_value()

    with allure.step('Validate output'):
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output1, RestrictionsConsts.FIELDS) \
            .verify_result()

    with allure.step('Run show authentication command'):
        output2 = OutputParsingTool.parse_json_str_to_dictionary(auth_obj.show()).get_returned_value()

    with allure.step('Validate output'):
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output2[RestrictionsConsts.RESTRICTIONS],
                                                                          RestrictionsConsts.FIELDS).verify_result()
        ValidationTool.compare_dictionaries(output1, output2[RestrictionsConsts.RESTRICTIONS]).verify_result()


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_auth_restrictions_set_unset(test_api, engines):
    """
    @summary: Verify (in show output) that configuration is changing correctly with the set/unset commands

        Steps:
        1. Run set command
        2. Verify new configuration
        3. Run unset command
        4. Verify default configuration
        5. Change all fields (again) to non-default values
        6. Verify new configuration
        7. Run unset to system, aaa, authentication, restrictions (not specific field)
        8. Verify default configuration
    """
    TestToolkit.tested_api = test_api
    system = System()
    restrictions = system.aaa.authentication.restrictions

    for field in RestrictionsConsts.FIELDS:
        with allure.step(f'Run set command for field: {field}'):
            val = random.choice(RestrictionsConsts.VALID_VALUES[field])
            logging.info(f'Set field "{field}" with value "{val}"')
            restrictions.set(field, val, apply=True).verify_result()

        with allure.step('Verify new configuration'):
            output = OutputParsingTool.parse_json_str_to_dictionary(restrictions.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output, field, val).verify_result()

        with allure.step('Run unset command'):
            restrictions.unset(field, apply=True).verify_result()

        with allure.step('Verify default configuration'):
            output = OutputParsingTool.parse_json_str_to_dictionary(restrictions.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output, field, RestrictionsConsts.DEFAULT_VALUES[field]) \
                .verify_result()

    with allure.step(
            'Change configuration and unset with general resources (system, aaa, authentication, restrictions)'):
        new_conf = {
            field: random.choice(RestrictionsConsts.VALID_VALUES[field]) for field in RestrictionsConsts.FIELDS
        }

        for resource_to_unset in [system.aaa.authentication, system.aaa.authentication.restrictions]:
            with allure.step('Change all fields'):
                configure_resource(engines, restrictions, new_conf, apply=True)

            with allure.step('Verify new configuration'):
                output = OutputParsingTool.parse_json_str_to_dictionary(restrictions.show()).get_returned_value()
                ValidationTool.validate_fields_values_in_output(new_conf.keys(), new_conf.values(),
                                                                output).verify_result()

            with allure.step('Run unset to system, aaa, authentication, restrictions (not specific field)'):
                resource_to_unset.unset(apply=True).verify_result()

            with allure.step('Verify default configuration'):
                output = OutputParsingTool.parse_json_str_to_dictionary(restrictions.show()).get_returned_value()
                ValidationTool.validate_fields_values_in_output(RestrictionsConsts.DEFAULT_VALUES.keys(),
                                                                RestrictionsConsts.DEFAULT_VALUES.values(), output) \
                    .verify_result()


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_auth_restrictions_fail_delay(test_api, engines, test_user):
    """
    @summary: Verify the functionality of the fail-delay configuration

        Steps:
        1. Configure fail-delay
        2. Make authentication failures and sample time in between
        3. Verify sample is higher or equal to fail-delay
    """
    TestToolkit.tested_api = test_api
    fail_delay = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.FAIL_DELAY])
    margin = int(max(RestrictionsConsts.ALLOWED_MARGIN, 0.1 * fail_delay))

    with allure.step(f'Configure fail-delay: {fail_delay}'):
        restrictions = System().aaa.authentication.restrictions
        restrictions.set(RestrictionsConsts.FAIL_DELAY, fail_delay, apply=True).verify_result()
        cur_fail_delay = OutputParsingTool.parse_json_str_to_dictionary(restrictions.show()).get_returned_value()[
            RestrictionsConsts.FAIL_DELAY]
        assert str(fail_delay) == str(cur_fail_delay), f'Fail delay was not changed.\n' \
            f'Expected {fail_delay}\n' \
            f'Actual: {cur_fail_delay}'

    with allure.step('Make 2 authentication failures'):
        attempter = SshAuthenticator(test_user[AaaConsts.USERNAME], test_user[AaaConsts.PASSWORD], engines.dut.ip)
        _, timestamp1 = attempter.attempt_login_failure()
        _, timestamp2 = attempter.attempt_login_failure()

    with allure.step(f'Verify delay until the 2nd attempt was at least {fail_delay} (+-{margin}) seconds'):
        assert timestamp2 - timestamp1 >= fail_delay - margin, \
            f'Delta of time between failure to success is not as expected.\n' \
            f'Expected: {timestamp2 - timestamp1} (delta) >= {fail_delay - margin} (fail-delay)'


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_auth_restrictions_lockout(test_api, engines, test_user):
    """
    @summary: Validate the functionality of the lockout mechanism and its configurations.

        Steps:
        1. Set lockout-attempts and high lockout-reattempt, and disable lockout-state
        2. Make more than <lockout-attempts> auth failures
        3. Verify user is not blocked
        4. Enable lockout-state
        5. Make <lockout-attempts> auth failures
        6. Verify user is blocked
    """
    TestToolkit.tested_api = test_api

    with allure.step('Set lockout-attempts and high lockout-reattempt, and disable lockout-state'):
        restrictions = System().aaa.authentication.restrictions
        lockout_attempts = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.LOCKOUT_ATTEMPTS])
        lockout_reattempt = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.LOCKOUT_REATTEMPT])

        configure_resource(engines, restrictions, conf={
            RestrictionsConsts.FAIL_DELAY: 0,
            RestrictionsConsts.LOCKOUT_ATTEMPTS: lockout_attempts,
            RestrictionsConsts.LOCKOUT_REATTEMPT: lockout_reattempt,
            RestrictionsConsts.LOCKOUT_STATE: RestrictionsConsts.DISABLED
        }, apply=True)

    with allure.step(f'Make {lockout_attempts} auth failures'):
        attempter = SshAuthenticator(test_user[AaaConsts.USERNAME], test_user[AaaConsts.PASSWORD], engines.dut.ip)

        for i in range(1, lockout_attempts + 1):
            logging.info(f'\n\nAttempt number {i}')
            attempter.attempt_login_failure()

    with allure.step('Verify user is not blocked'):
        auth_succeeded, _ = attempter.attempt_login_success()
        assert auth_succeeded, f'Error: User "{attempter.username}" should not be blocked, but could not log in'

    with allure.step('Enable lockout-state'):
        restrictions.set(RestrictionsConsts.LOCKOUT_STATE, RestrictionsConsts.ENABLED, apply=True).verify_result()

    with allure.step(f'Make {lockout_attempts} auth failures again'):
        for i in range(1, lockout_attempts + 1):
            logging.info(f'\n\nAttempt number {i}')
            attempter.attempt_login_failure()

    with allure.step(f'Verify user is blocked until {lockout_reattempt} seconds pass'):
        with allure.step('Attempt auth success and expect fail (blocked)'):
            auth_succeeded, _ = attempter.attempt_login_success()
            assert not auth_succeeded, f'Error: User "{attempter.username}" should be blocked, but log in success'

        sleep_time = lockout_reattempt

        if lockout_reattempt >= 20:  # if there is enough time to make another attempt in the middle
            sleep_time = lockout_reattempt // 2 + 1

            with allure.step(f'Sleep {sleep_time} seconds'):
                time.sleep(sleep_time)

            with allure.step('Attempt auth success and expect fail (blocked)'):
                auth_succeeded, _ = attempter.attempt_login_success()
                assert not auth_succeeded, f'Error: User "{attempter.username}" should be blocked, but log in success'

        logging.info(f'Sleep {sleep_time} seconds')
        time.sleep(sleep_time)

        logging.info('Attempt auth success and expect success (lockout-reattempt passed)')
        auth_succeeded, _ = attempter.attempt_login_success()
        assert auth_succeeded, f'Error: User "{attempter.username}" should be unblocked, but log in failed'


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_auth_restrictions_action_clear_user(test_api, engines, test_user):
    """
    @summary: Verify the functionality of action clear command

        Steps:
        1. Enable lockout
        2. Block user
        3. Unblock user using action clear command
        4. Verify user unblocked
    """
    TestToolkit.tested_api = test_api

    with allure.step('Enable lockout'):
        restrictions = System().aaa.authentication.restrictions
        lockout_attempts = 3
        lockout_reattempt = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.LOCKOUT_REATTEMPT])
        configure_resource(engines, restrictions, conf={
            RestrictionsConsts.FAIL_DELAY: 0,
            RestrictionsConsts.LOCKOUT_ATTEMPTS: lockout_attempts,
            RestrictionsConsts.LOCKOUT_REATTEMPT: lockout_reattempt,
            RestrictionsConsts.LOCKOUT_STATE: RestrictionsConsts.ENABLED
        }, apply=True)

    with allure.step('Block user'):
        attempter = SshAuthenticator(test_user[AaaConsts.USERNAME], test_user[AaaConsts.PASSWORD], engines.dut.ip)
        for i in range(1, lockout_attempts + 1):
            logging.info(f'\n\nAttempt number {i}')
            _, timestamp1 = attempter.attempt_login_failure()

    with allure.step('Verify user blocked'):
        login_succeeded, _ = attempter.attempt_login_success()
        assert not login_succeeded, f'User should be blocked.\n' \
            f'Expect 2 - Login fail: {not login_succeeded}'

    with allure.step('Unblock user using action clear command'):
        restrictions.action_clear(user_to_clear=test_user[AaaConsts.USERNAME])  # todo: verify if its per user

    with allure.step('Verify user unblocked'):
        login_succeeded, timestamp2 = attempter.attempt_login_success()
        assert timestamp2 - timestamp1 < lockout_reattempt and login_succeeded, \
            f'User should be unblocked.\n' \
            f'Expect 1: {timestamp2 - timestamp1} (delta) < {lockout_reattempt} (lockout-reattempt)\n' \
            f'Expect 2 - Login success: {login_succeeded}'


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_auth_restrictions_action_clear_all(test_api, engines, test_users):
    """
    @summary: Verify the functionality of action clear command

        Steps:
        1. Enable lockout
        2. Block one user
        3. Unblock user using the clear all command
        4. Verify user unblocked
        5. Block both users
        6. Unblock all
        7. Verify both are unblocked
    """
    TestToolkit.tested_api = test_api

    with allure.step('Enable lockout'):
        restrictions = System().aaa.authentication.restrictions
        lockout_attempts = 3
        lockout_reattempt = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.LOCKOUT_REATTEMPT])
        configure_resource(engines, restrictions, conf={
            RestrictionsConsts.FAIL_DELAY: 0,
            RestrictionsConsts.LOCKOUT_ATTEMPTS: lockout_attempts,
            RestrictionsConsts.LOCKOUT_REATTEMPT: lockout_reattempt,
            RestrictionsConsts.LOCKOUT_STATE: RestrictionsConsts.ENABLED
        }, apply=True)

        user1, user2 = test_users[0], test_users[1]

    with allure.step(f'Block user {user1[AaaConsts.USERNAME]}'):
        attempter = SshAuthenticator(user1[AaaConsts.USERNAME], user1[AaaConsts.PASSWORD], engines.dut.ip)
        for i in range(1, lockout_attempts + 1):
            logging.info(f'\n\nAttempt number {i}')
            _, timestamp1 = attempter.attempt_login_failure()

    with allure.step(f'Verify user {user1[AaaConsts.USERNAME]} blocked'):
        login_succeeded, _ = attempter.attempt_login_success()
        assert not login_succeeded, f'User should be blocked.\n' \
            f'Expect 2 - Login fail: {not login_succeeded}'

    with allure.step(f'Unblock user {user1[AaaConsts.USERNAME]} using action clear command'):
        restrictions.action_clear()  # todo: verify if its per user

    with allure.step(f'Verify user {user1[AaaConsts.USERNAME]} unblocked'):
        login_succeeded, timestamp2 = attempter.attempt_login_success()
        assert timestamp2 - timestamp1 < lockout_reattempt and login_succeeded, \
            f'User should be unblocked.\n' \
            f'Expect 1: {timestamp2 - timestamp1} (delta) < {lockout_reattempt} (lockout-reattempt)\n' \
            f'Expect 2 - Login success: {login_succeeded}'

    with allure.step('Block both users'):
        attempters = [SshAuthenticator(user1[AaaConsts.USERNAME], user1[AaaConsts.PASSWORD], engines.dut.ip),
                      SshAuthenticator(user2[AaaConsts.USERNAME], user2[AaaConsts.PASSWORD], engines.dut.ip)]
        timestamps = [0, 0]

        for i in range(1, lockout_attempts + 1):
            for k in range(2):
                logging.info(f'\n\nAttempt number {i} for user {attempters[k].username}')
                _, timestamps[k] = attempters[k].attempt_login_failure()

        for k in range(2):
            with allure.step(f'Verify user {attempters[k].username} blocked'):
                login_succeeded, _ = attempters[k].attempt_login_success()
                assert not login_succeeded, f'User should be blocked.\n' \
                    f'Expect 2 - Login fail: {not login_succeeded}'

    with allure.step('Unblock all users'):
        restrictions.action_clear()  # todo: verify if its per user

    with allure.step('Verify both users unblocked'):
        for k in range(2):
            with allure.step(f'Verify user {attempters[k].username} unblocked'):
                login_succeeded, timestamp2 = attempter.attempt_login_success()
                assert timestamp2 - timestamps[k] < lockout_reattempt and login_succeeded, \
                    f'User should be unblocked.\n' \
                    f'Expect 1: {timestamp2 - timestamps[k]} (delta) < {lockout_reattempt} (lockout-reattempt)\n' \
                    f'Expect 2 - Login success: {login_succeeded}'


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_auth_restrictions_multi_user(test_api, engines):
    """
    @summary: Verify that users don't affect each other, from auth restrictions perspective.

        Steps:
        1. Set 2 users (test_admin and TEST_ADMIN)
        2. Enable lockout
        3. Make one of the users blocked
        4. Verify one is blocked and the other is not
    """
    TestToolkit.tested_api = test_api

    with allure.step('Set 2 users (test_admin and TEST_ADMIN)'):
        TestToolkit.tested_api = ApiType.NVUE  # todo: remove after fix set user with password in openapi
        test_admin_lower = RestrictionsConsts.TEST_ADMIN
        test_admin_upper = RestrictionsConsts.TEST_ADMIN.copy()
        test_admin_upper[AaaConsts.USERNAME] = test_admin_upper[AaaConsts.USERNAME].upper()
        system = System()
        _, password = system.aaa.user.set_new_user(test_admin_lower[AaaConsts.USERNAME])
        test_admin_lower[AaaConsts.PASSWORD] = password
        _, password = system.aaa.user.set_new_user(test_admin_upper[AaaConsts.USERNAME], apply=True)
        test_admin_upper[AaaConsts.PASSWORD] = password
        TestToolkit.tested_api = test_api  # todo: remove after fix set user with password in openapi

    with allure.step('Enable lockout'):
        lockout_attempts = 3
        lockout_reattempt = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.LOCKOUT_REATTEMPT])
        configure_resource(engines, System().aaa.authentication.restrictions, conf={
            RestrictionsConsts.FAIL_DELAY: 0,
            RestrictionsConsts.LOCKOUT_ATTEMPTS: lockout_attempts,
            RestrictionsConsts.LOCKOUT_REATTEMPT: lockout_reattempt,
            RestrictionsConsts.LOCKOUT_STATE: RestrictionsConsts.ENABLED
        }, apply=True)

    with allure.step('Verify the configuration'):
        fd = RestrictionsConsts.FAIL_DELAY
        ls = RestrictionsConsts.LOCKOUT_STATE
        la = RestrictionsConsts.LOCKOUT_ATTEMPTS
        lr = RestrictionsConsts.LOCKOUT_REATTEMPT
        enabled = RestrictionsConsts.ENABLED
        o = OutputParsingTool.parse_json_str_to_dictionary(
            System().aaa.authentication.restrictions.show()).get_returned_value()
        logging.info(
            f'Verify conf:\nfd\tls\tla\tlr\n{0}\t{enabled}\t{3}\t{lockout_reattempt}\t<-- Expected\n{o[fd]}\t{o[ls]}\t{o[la]}\t{o[lr]}\t<-- Actual')
        assert (str(0) == str(o[fd]) and enabled == str(o[ls]) and str(3) == str(o[la]) and str(
            lockout_reattempt) == str(o[
                lr])), f'Error:\nfd\tls\tla\tlr\n{0}\t{enabled}\t{3}\t{lockout_reattempt}\t<-- Expected\n{o[fd]}\t{o[ls]}\t{o[la]}\t{o[lr]}\t<-- Actual'

    with allure.step(f'Make user "{test_admin_lower[AaaConsts.USERNAME]}" blocked'):
        logging.info('Create authenticators')
        lower_attempter = SshAuthenticator(test_admin_lower[AaaConsts.USERNAME], test_admin_lower[AaaConsts.PASSWORD],
                                           engines.dut.ip)
        upper_attempter = SshAuthenticator(test_admin_upper[AaaConsts.USERNAME], test_admin_upper[AaaConsts.PASSWORD],
                                           engines.dut.ip)
        logging.info(f'Attempt with each until user "{test_admin_lower[AaaConsts.USERNAME]}" is blocked')
        lower_attempter.attempt_login_failure()  # no block
        upper_attempter.attempt_login_failure()  # no block
        lower_attempter.attempt_login_failure()  # no block
        lower_attempter.attempt_login_failure()  # only lower should be blocked

    with allure.step(f'Verify user "{test_admin_lower[AaaConsts.USERNAME]}" is blocked '
                     f'and user "{test_admin_upper[AaaConsts.USERNAME]}" other is not'):
        login_succeeded, _ = lower_attempter.attempt_login_success()
        assert not login_succeeded, f'User {test_admin_lower[AaaConsts.USERNAME]} should be blocked.\n' \
            f'Expect login fail: {not login_succeeded}'
        login_succeeded, _ = upper_attempter.attempt_login_success()
        assert login_succeeded, f'User {test_admin_upper[AaaConsts.USERNAME]} should not be blocked.\n' \
            f'Expect login success: {login_succeeded}'


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_auth_restrictions_auth_success_clears_user(test_api, engines, test_user):
    """
    @summary: Verify that authentication success clears the user from being blocked.

        Steps:
        1. Enable lockout
        2. Make <lockout-attempts> auth failures
        3. Make authentication success
        4. Verify user is not blocked
    """
    TestToolkit.tested_api = test_api

    with allure.step('Enable lockout'):
        lockout_attempts = 3
        lockout_reattempt = random.randint(20, 30)
        configure_resource(engines, System().aaa.authentication.restrictions, conf={
            RestrictionsConsts.FAIL_DELAY: 0,
            RestrictionsConsts.LOCKOUT_ATTEMPTS: lockout_attempts,
            RestrictionsConsts.LOCKOUT_REATTEMPT: lockout_reattempt,
            RestrictionsConsts.LOCKOUT_STATE: RestrictionsConsts.ENABLED
        }, apply=True)

    with allure.step(f'Make {lockout_attempts} auth failures'):
        attempter = SshAuthenticator(test_user[AaaConsts.USERNAME], test_user[AaaConsts.PASSWORD], engines.dut.ip)
        for i in range(1, lockout_attempts + 1):
            logging.info(f'\n\nAttempt number {i}')
            attempter.attempt_login_failure()  # block

    with allure.step('Verify user is blocked'):
        login_succeeded, _ = attempter.attempt_login_success()
        assert not login_succeeded, f'User {test_user[AaaConsts.USERNAME]} should be blocked.\n' \
            f'Expect login fail: {not login_succeeded}'

    with allure.step(f'Sleep {lockout_reattempt + RestrictionsConsts.ALLOWED_MARGIN} seconds'):
        time.sleep(lockout_reattempt + RestrictionsConsts.ALLOWED_MARGIN)

    with allure.step('Verify user can login with success'):
        login_succeeded, _ = attempter.attempt_login_success()
        assert login_succeeded, f'Expect login success: {login_succeeded}'

    with allure.step('Verify user is unblocked after one login success'):
        with allure.step('Make 2 auth failures'):
            for i in range(1, 3):
                logging.info(f'\n\nAttempt number {i}')
                attempter.attempt_login_failure()  # should not be blocked and able to login

        with allure.step('Verify user can login with success'):
            login_succeeded, _ = attempter.attempt_login_success()
            assert login_succeeded, f'Expect login success: {login_succeeded}'


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_auth_restrictions_ssh_and_openapi_counting(test_api, engines, test_user, devices, topology_obj):
    """
    @summary: Verify that both authentication through ssh and through openapi request are both count as auth attempts.

        Steps:
        1. Configure lockout-attempts to 4
        2. Make 2 authentication failures through openapi requests
        3. Make (another) 2 ssh authentication failures
        4. Verify user is blocked
    """
    TestToolkit.tested_api = test_api

    with allure.step('Configure lockout-attempts to 4'):
        restrictions = System().aaa.authentication.restrictions
        lockout_reattempt = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.LOCKOUT_REATTEMPT])
        configure_resource(engines, restrictions, conf={
            RestrictionsConsts.FAIL_DELAY: 0,
            RestrictionsConsts.LOCKOUT_STATE: RestrictionsConsts.ENABLED,
            RestrictionsConsts.LOCKOUT_ATTEMPTS: 4,
            RestrictionsConsts.LOCKOUT_REATTEMPT: lockout_reattempt
        }, apply=True)

    with allure.step('Verify user is not blocked before'):
        ip = engines.dut.ip
        user = test_user[AaaConsts.USERNAME]
        password = test_user[AaaConsts.PASSWORD]
        openapi_request = "curl -k --user {}:{} --request GET 'https://{}/nvue_v1/system/version'"
        good_request = openapi_request.format(user, password, ip)
        server_ip = NvueGeneralCli(engines.dut, devices.dut).get_site_server_ip(topology_obj)
        request_engine = LinuxSshEngine(server_ip, DefaultTestServerCred.DEFAULT_USERNAME,
                                        DefaultTestServerCred.DEFAULT_PASS)
        out = request_engine.run_cmd(good_request)
        assert 'fail' not in out and '</html>' not in out, f'OpenApi request failed:\n{out}'
        # openapi_attempter = OpenapiAuthenticator(test_user[AaaConsts.USERNAME], test_user[AaaConsts.PASSWORD], engines.dut.ip)
        # succeeded, _, output = openapi_attempter.attempt_login_success()

    with allure.step('Make another 2 authentication failures, through openapi requests'):
        bad_request = openapi_request.format(user, 'asd', ip)
        for _ in range(2):
            out = request_engine.run_cmd(bad_request)
            assert RestrictionsConsts.OPENAPI_AUH_ERROR in out, f'Unexpected OpenApi response.\n' \
                f'expected: {RestrictionsConsts.OPENAPI_AUH_ERROR}\n' \
                f'actual:\n{out}'
        # openapi_bad_attempter = LinuxSshEngine(engines.dut.ip, 'asd', test_user[AaaConsts.PASSWORD])
        # succeeded, _, output = openapi_attempter.attempt_login_failure()
        # assert not succeeded and RestrictionsConsts.OPENAPI_AUH_ERROR in output, 'Expected auth error from openapi'
        # succeeded, _, output = openapi_attempter.attempt_login_failure()
        # assert not succeeded and RestrictionsConsts.OPENAPI_AUH_ERROR in output, 'Expected auth error from openapi'

    with allure.step('Make 2 authentication failures through SSH'):
        ssh_attempter = SshAuthenticator(test_user[AaaConsts.USERNAME], test_user[AaaConsts.PASSWORD], engines.dut.ip)
        ssh_attempter.attempt_login_failure()
        ssh_attempter.attempt_login_failure()

    with allure.step('Verify user is blocked'):
        out = engines.dut.run_cmd(good_request)
        assert RestrictionsConsts.OPENAPI_AUH_ERROR in out, f'Unexpected OpenApi response.\n' \
            f'expected: {RestrictionsConsts.OPENAPI_AUH_ERROR}\n' \
            f'actual:\n{out}'
        # succeeded, _, output = openapi_attempter.attempt_login_success()
        # assert not succeeded and RestrictionsConsts.OPENAPI_AUH_ERROR in output, 'Expected auth error from openapi'


@pytest.mark.simx
@pytest.mark.security
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_auth_restrictions_remote_counting(test_api, engines, request, devices, test_user):
    """
    @summary: Verify that when there are more than <lockout-attempts> remote authentication servers configured,
        an authentication failure still counts as 1 attempt.

        Steps:
        1. Configure remote auth with more than <lockout-attempts> servers
        2. Configure lockout and enable it
        3. Make 1 authentication failure
        4. Verify user is not blocked
    """
    item = request.node
    TestToolkit.tested_api = test_api

    with allure.step('Configure remote auth with more than <lockout-attempts> servers'):
        servers_info = [TacacsPhysicalServer.SERVER_IPV4.copy(), TacacsDockerServer0.SERVER_IPV4.copy(),
                        TacacsDockerServer0.SERVER_DN.copy()]
        prio = 3
        for server in servers_info:
            server.priority = prio
            server.configure(engines, set_explicit_priority=True)
            prio -= 1

    with allure.step('Enable tacacs'):
        aaa = System().aaa
        configure_resource(engines, aaa.authentication, conf={
            AuthConsts.ORDER: f'{AuthConsts.TACACS},{AuthConsts.LOCAL}',
            AuthConsts.FAILTHROUGH: AaaConsts.ENABLED
        })

    with allure.step('Configure and enable lockout'):
        lockout_reattempt = random.choice(RestrictionsConsts.VALID_VALUES[RestrictionsConsts.LOCKOUT_REATTEMPT])

        configure_resource(engines, aaa.authentication.restrictions, conf={
            RestrictionsConsts.FAIL_DELAY: 0,
            RestrictionsConsts.LOCKOUT_ATTEMPTS: 3,
            RestrictionsConsts.LOCKOUT_REATTEMPT: lockout_reattempt,
            RestrictionsConsts.LOCKOUT_STATE: RestrictionsConsts.ENABLED
        }, apply=True, verify_apply=False)
        # update_active_aaa_server(item, servers_info[0])

    with allure.step('Make 1 authentication failure'):
        with loganalyzer_ignore(False):
            attempter = SshAuthenticator(test_user[AaaConsts.USERNAME], test_user[AaaConsts.PASSWORD], engines.dut.ip)
            attempter.attempt_login_failure()

    with allure.step('Verify user is not blocked'):
        succeeded, _ = attempter.attempt_login_success()
        assert succeeded, f'User should not be blocked and should be able to login'
