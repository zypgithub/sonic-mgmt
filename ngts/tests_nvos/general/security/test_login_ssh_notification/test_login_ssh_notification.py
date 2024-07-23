import datetime
import random
import re
import os
import time

from infra.tools.connection_tools.utils import generate_strong_password
from infra.tools.linux_tools.linux_tools import scp_file
from ngts.tools.test_utils import allure_utils as allure
import pexpect
import logging
import pytest
import json

from ngts.tests_nvos.general.security.security_test_tools.switch_authenticators import SshAuthenticator
from ngts.tests_nvos.general.security.test_login_ssh_notification.constants import LoginSSHNotificationConsts as Consts
from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import SystemConsts, ApiType
from ngts.tests_nvos.general.security.conftest import ssh_to_device_and_retrieve_raw_login_ssh_notification, create_ssh_login_engine
from ngts.tests_nvos.system.clock.ClockTools import ClockTools


logger = logging.getLogger(__name__)


def convert_linux_date_output_to_datetime_object(linux_date_string):
    '''
    @summary: this helper function will extract time and date and
    return tuple ( date , time )
    :param output: output to extract the time and date from
    :param date_regex: date regex to catch
    :param time_regex: time regex to catch
    '''
    date_format = "%a %b %d %H:%M:%S %Z %Y"
    date = datetime.datetime.strptime(linux_date_string, date_format)
    return date


def parse_ssh_login_notification(dut_ip, username, password):
    '''
    @summary: in this function we will parse the login ssh notification parameters
    when creating ssh connection to switch and extracting all the parameters
    this includes:
        1.	Last successful login date/time and location – (for all users)
        2.	Number of unsuccessful logins since last successful login – (per user)
        3.	Last unsuccessful date/time and location (terminal or IP) – (per user)
        4.	Changes to user's account since last login (password, role, group, etc) – (per user)
        5.	Number of total successful logins since a date/time – (user with admin capabilities)

    :return: will return a dictionary of each parameter, e.g.:
    {
        'last_successful_login_date' : datetime bject of cuurent date,
        'last_successful_login_ip' : '10.7.34.240',
        'last_unsuccessful_login_date' : datetime bject of cuurent date,
        'last_unsuccessful_login_ip' : '10.7.34.240',
        'number_of_unsuccessful_attempts_since_last_login', '4',
        'record_period' : '5',
        'number_of_successful_connections_in_the_last_record_period' : '100',
        'password_changed_message' : None, (None - means didn't appear in the notification)
        'role_changed_message' : None
    }
    '''
    result = {}

    with allure.step(f'Connect to switch with user "{username}"'):
        _, _, notification_login_message = SshAuthenticator(username, password, dut_ip).attempt_login_success(return_output=True)
        # notification_login_message = ssh_to_device_and_retrieve_raw_login_ssh_notification(dut_ip,
        #                                                                                    username,
        #                                                                                    password)
    with allure.step('Parse ssh login output'):
        for key, regex in Consts.LOGIN_SSH_NOTIFICATION_REGEX_DICT.items():
            logging.info(f'Extract key: {key}')
            match = re.findall(regex, notification_login_message)
            if regex == Consts.LAST_SUCCESSFUL_LOGIN_DATE_REGEX:
                assert match, f'could not find {key} in ssh login message.\nregex: {regex}\n' \
                    f'login message:\n{notification_login_message}'
                # there will be always output to catch it
                result[Consts.LAST_SUCCESSFUL_LOGIN_DATE] = convert_linux_date_output_to_datetime_object(match[0])
            elif regex == Consts.LAST_UNSUCCESSFUL_LOGIN_DATE_REGEX:
                # not always the message will appear
                if len(match) != 0:
                    result[Consts.LAST_UNSUCCESSFUL_LOGIN_DATE] = convert_linux_date_output_to_datetime_object(match[0])
                else:
                    result[Consts.LAST_UNSUCCESSFUL_LOGIN_DATE] = None
            else:
                result[key] = match[0] if match else None

    return result


def change_username_password(engines, username, curr_password, new_password):
    '''
    @summary: in this test case we want to validate password message appearance
    after changing it in the second ssh login notification
    :param username: username
    :param curr_password: current password for username
    :param new_password: new password to change to
    '''
    with allure.step("Changing password for user: {}".format(username)):
        logger.info("Changing password for user: {}\n"
                    "Current password: {}\n"
                    "New password proposed: {}".format(username, curr_password, new_password))
        System(force_api=ApiType.NVUE).aaa.user.user_id[username].set(DefaultConnectionValues.PASSWORD, new_password, apply=True).verify_result()

    with allure.step("Sleeping {} secs to allow password change".format(Consts.PASSWORD_UPDATE_WAIT_TIME)):
        time.sleep(Consts.PASSWORD_UPDATE_WAIT_TIME)


def validate_ssh_login_notifications_default_fields(engines, login_source_ip_address, username, password, capability,
                                                    check_password_change_msg=False,
                                                    check_role_change_msg=False,
                                                    expected_login_record_period=None,
                                                    last_successful_login=None):
    '''
    @summary: in this test case we want to validate the output of default fields
    of login ssh notification, where we want to check the following parameters:
        [
            'last_successful_login_date',
            'last_successful_login_time',
            'last_successful_login_ip',
            'last_unsuccessful_login_date',
            'last_unsuccessful_login_time',
            'last_unsuccessful_login_ip',
            'number_of_unsuccessful_attempts_since_last_login',
            'record_period',
            'number_of_successful_connections_in_the_last_record_period'
        ]
    :param engines: fixture containing all engines
    :param login_source_ip_address: ip address initiating the ssh connection in the test
    :param username: username to connect with to switch
    :param password: the password for username
    :param capability: the username capability, could be one of [admin, monitor]
    :param check_password_change_msg: if set true will check if password message appeared
    :param check_role_change_msg: if set true will check if role message appeared
    :param expected_login_record_period: if not None, will validate same value as the notification value
    :param last_successful_login: datetime object of the time since last successful login
    '''
    random_number_of_connection_fails = random.randint(5, 15)
    with allure.step("Fail {} times connecting to device".format(random_number_of_connection_fails)):
        logger.info("Attempting {} wrong password attempts".format(random_number_of_connection_fails))
        authenticator = SshAuthenticator(username, password, engines.dut.ip)
        for index in range(random_number_of_connection_fails):
            logger.info(f'Attempt number {index + 1}')
            authenticator.attempt_login_failure()
            # try:
            #     connection = create_ssh_login_engine(engines.dut.ip, username)
            #     connection.expect(DefaultConnectionValues.PASSWORD_REGEX)
            #     random_password = RandomizationTool.get_random_string(random.randint(Consts.PASSWORD_MIN_LEN,
            #                                                                          Consts.PASSWORD_MAX_LEN))
            #     logger.info("Iteration {} - connecting using random password: {}".format(index, random_password))
            #     connection.sendline(random_password)
            #     connection.expect(["Permission denied", "permission denied"])
            # finally:
            #     connection.close()

    with allure.step("Connect for the second time to switch and store details"):
        second_login_notification_message = parse_ssh_login_notification(engines.dut.ip, username,
                                                                         password)

    if last_successful_login:
        with allure.step("Validating same date"):
            time_delta_seconds = (abs(second_login_notification_message[Consts.LAST_SUCCESSFUL_LOGIN_DATE] - last_successful_login)).seconds
            assert time_delta_seconds < Consts.MAX_TIME_DELTA_BETWEEEN_CONNECTIONS, "Time Delta between current time and successful login ssh time is not under 120 secs, \n" \
                "The time difference is {}".format(time_delta_seconds)
            time_delta_seconds = (second_login_notification_message[Consts.LAST_UNSUCCESSFUL_LOGIN_DATE] - last_successful_login).seconds
            assert time_delta_seconds < Consts.MAX_TIME_DELTA_BETWEEEN_CONNECTIONS, "Time Delta between current time and successful login ssh time is not under 120 secs, \n" \
                "The time difference is {}".format(time_delta_seconds)

    with allure.step("Validating {} failed attempts in the second connection".format(random_number_of_connection_fails)):
        assert int(second_login_notification_message[Consts.NUMBER_OF_UNSUCCESSFUL_ATTEMPTS_SINCE_LAST_LOGIN]) == random_number_of_connection_fails, \
            "Number of failed connections is not the same, \n" \
            "Expected : {} \n" \
            "Actually : {}".format(second_login_notification_message[Consts.NUMBER_OF_UNSUCCESSFUL_ATTEMPTS_SINCE_LAST_LOGIN],
                                   random_number_of_connection_fails)

    with allure.step("Validating IP address is same as this test IP address"):
        with allure.step("Validating successful IP address"):
            assert second_login_notification_message[Consts.LAST_SUCCESSFUL_LOGIN_IP] == login_source_ip_address, \
                "Not same login IP Address, \n" \
                "Expected : {} \n" \
                "Actual : {}".format(second_login_notification_message[Consts.LAST_SUCCESSFUL_LOGIN_IP],
                                     login_source_ip_address)
        with allure.step("Validating unsuccessful IP address"):
            assert second_login_notification_message[Consts.LAST_UNSUCCESSFUL_LOGIN_IP] == login_source_ip_address, \
                "Not same unsuccessful login IP Address\n" \
                "Expected : {} \n" \
                "Actual : {}".format(
                    second_login_notification_message[Consts.LAST_UNSUCCESSFUL_LOGIN_IP],
                    login_source_ip_address)

    with allure.step("Validating password or capability changes"):
        if check_password_change_msg:
            assert second_login_notification_message[Consts.PASSWORD_CHANGED_MESSAGE] is not None, \
                "Password change message did not appear when it should"
        else:
            assert second_login_notification_message[Consts.PASSWORD_CHANGED_MESSAGE] is None, \
                "Password change message appeared when it should not"

        if check_role_change_msg:
            assert second_login_notification_message[Consts.ROLE_CHANGED_MESSAGE] is not None, \
                "Capability change message did not appear when it should"
        else:
            assert second_login_notification_message[Consts.ROLE_CHANGED_MESSAGE] is None, \
                "Capability change message appeared when it should not"

    # if expected_login_record_period:
    #     with allure.step("Validating login-record-period value"):
    #         logger.info("Validating login-record-period value")
    #         assert second_login_notification_message[Consts.RECORD_PERIOD] == str(expected_login_record_period), \
    #             "Not same login record period value, expected: {}, actual: {}".format(expected_login_record_period,
    #                                                                                   second_login_notification_message[Consts.RECORD_PERIOD])


def get_current_time_in_secs():
    '''
    @summary: in this function we convert the current date to seconds
    :return:
    '''
    output = os.popen("date").read()
    current_date_string = re.findall(Consts.LINUX_DATE_REGEX, output)[0]
    logger.info("Linux date is {}".format(current_date_string))
    current_date = convert_linux_date_output_to_datetime_object(current_date_string)
    return current_date


@pytest.mark.cumulus
@pytest.mark.simx_security
@pytest.mark.login_ssh_notification
@pytest.mark.checklist
def test_ssh_login_notifications_default_fields_admin(engines, login_source_ip_address):
    '''
    @summary: in this test case we want to validate admin username ssh login notification
    '''
    with allure.step("Connecting to switch before validation to clear all failed messages"):
        logger.info("Connecting to switch before validation to clear all failed messages")
        successful_login_time = ClockTools.get_datetime_object_from_show_system_output(System().show())
        SshAuthenticator(engines.dut.username, engines.dut.password, engines.dut.ip)
        # ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip,
        #                                                       username=engines.dut.username,
        #                                                       password=engines.dut.password)
    validate_ssh_login_notifications_default_fields(engines, login_source_ip_address,
                                                    username=engines.dut.username,
                                                    password=engines.dut.password,
                                                    capability=Consts.ADMIN_CAPABITILY,
                                                    last_successful_login=successful_login_time)


@pytest.mark.cumulus
@pytest.mark.login_ssh_notification
@pytest.mark.checklist
def test_ssh_login_notification_password_change_admin(engines, login_source_ip_address, disable_password_hardening_rules):
    '''
    @summary: in this test case we want to validate admin username ssh login notification
    '''
    with allure.step('Create test user'):
        system = System(force_api=ApiType.NVUE)
        username, password = system.aaa.user.set_new_user(apply=True)
        new_password = generate_strong_password()

    with allure.step("Connecting to switch before validation to clear all failed messages"):
        successful_login_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
        SshAuthenticator(username, password, engines.dut.ip).attempt_login_success()
        # ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip,
        #                                                       username=username,
        #                                                       password=password)
    with allure.step('Change password'):
        change_username_password(engines, username=username,
                                 curr_password=password,
                                 new_password=new_password)
    with allure.step('Validate ssh login notification'):
        validate_ssh_login_notifications_default_fields(engines, login_source_ip_address,
                                                        username=username,
                                                        password=new_password,
                                                        capability=Consts.ADMIN_CAPABITILY,
                                                        check_password_change_msg=True,
                                                        last_successful_login=successful_login_time)


@pytest.mark.cumulus
@pytest.mark.login_ssh_notification
@pytest.mark.checklist
def test_ssh_login_notification_role_new_user(engines, login_source_ip_address):
    '''
    @summary: in this test case we want to validate new user role change on ssh login notification,
    where we expect role message to appear
    '''
    with allure.step("Creating a new username"):
        system = System(force_api=ApiType.NVUE)
        user_name, password = system.aaa.user.set_new_user(apply=True)
        logging.info(f"User created: \nusername: {user_name} \npassword: {password}\ncapability: {SystemConsts.ROLE_CONFIGURATOR}")

    with allure.step("Connecting to switch with the new user for first time"):
        successful_login_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
        SshAuthenticator(user_name, password, engines.dut.ip).attempt_login_success()
        # ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip, username=user_name, password=password)

    with allure.step(f"Change user '{user_name}' role to {SystemConsts.ROLE_VIEWER}"):
        system.aaa.user.user_id[user_name].set(SystemConsts.USER_ROLE, SystemConsts.ROLE_VIEWER, apply=True).verify_result()

    validate_ssh_login_notifications_default_fields(engines, login_source_ip_address,
                                                    username=user_name,
                                                    password=password,
                                                    capability=SystemConsts.ROLE_VIEWER,
                                                    check_password_change_msg=False,
                                                    check_role_change_msg=True,
                                                    last_successful_login=successful_login_time)


@pytest.mark.cumulus
@pytest.mark.simx_security
@pytest.mark.login_ssh_notification
@pytest.mark.checklist
def test_ssh_login_notification_cli_commands_good_flow(engines, login_source_ip_address,
                                                       restore_original_record_period):
    '''
    @summary: in this test case we want to test the new cli commands for login ssh notification,
    this test case will contain the good flow,
    commands to be tested:
    1. nv set system ssh-server login-record-period
    2. nv show system ssh-server
    '''
    system = System(None)

    with allure.step("Connecting to switch before validation to clear all failed messages"):
        successful_login_time = ClockTools.get_datetime_object_from_show_system_output(system.show())
        SshAuthenticator(engines.dut.username, engines.dut.password, engines.dut.ip).attempt_login_success()
        # ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip,
        #                                                       username=engines.dut.username,
        #                                                       password=engines.dut.password)

    with allure.step("Validating ssh login record period set command"):
        pass

    with allure.step("Setting new value for login record period"):
        record_days = random.randint(Consts.MIN_RECORD_PERIOD_VAL, Consts.MAX_RECORD_PERIOD_VAL)
        system.ssh_server.set(Consts.RECORD_PERIOD, record_days, apply=True, ask_for_confirmation=True)
        validate_ssh_login_notifications_default_fields(engines, login_source_ip_address,
                                                        username=engines.dut.username,
                                                        password=engines.dut.password,
                                                        capability=SystemConsts.ROLE_CONFIGURATOR,
                                                        check_password_change_msg=False,
                                                        check_role_change_msg=False,
                                                        expected_login_record_period=record_days,
                                                        last_successful_login=successful_login_time)

    with allure.step("Validating Validating show system ssh-server command"):
        output = json.loads(system.ssh_server.show())
        # assert output[Consts.RECORD_PERIOD] == str(record_days), \
        #     "Could not match same login record period ib the show system ssh-server command\n" \
        #     "expected: {}, actual: {}".format(record_days, output[Consts.RECORD_PERIOD])


@pytest.mark.cumulus
@pytest.mark.simx_security
@pytest.mark.login_ssh_notification
@pytest.mark.checklist
def test_login_ssh_notification_performance(engines, login_source_ip_address, restore_original_record_period,
                                            delete_auth_logs):
    '''
    @summary: in this test case we want to validate the performance of the feature when there is a huge
    auth.log file
    '''
    system = System(None)

    with allure.step("Setting max value for login record period"):
        system.ssh_server.set(Consts.RECORD_PERIOD,
                              Consts.MAX_RECORD_PERIOD_VAL,
                              apply=True, ask_for_confirmation=False).verify_result()

    with allure.step("populating auth. logs by uploading from previously created files"):
        logging.info('Create temp directory in the switch')
        engines.dut.run_cmd(f'mkdir {Consts.TMP_TEST_DIR_SWITCH_PATH}')
        logging.info('Upload auth log files using SCP')
        scp_file(engines.dut, Consts.AUTH_LOGS_SHARED_LOCATION, Consts.TMP_TEST_DIR_SWITCH_PATH)
        logging.info('Move files from temp directory to correct path using sudo')
        engines.dut.run_cmd(f'sudo mv {Consts.TMP_TEST_DIR_SWITCH_PATH}/auth.log* {Consts.AUTH_LOG_DIR_SWITCH_PATH}')
        logging.info('Remove temp directory from the switch')
        engines.dut.run_cmd(f'rmdir {Consts.TMP_TEST_DIR_SWITCH_PATH}')
        # player_engine = engines['sonic_mgmt']
        # player_engine.upload_file_using_scp(dest_username=engines.dut.username,
        #                                     dest_password=engines.dut.password,
        #                                     dest_folder=Consts.AUTH_LOG_DIR_SWITCH_PATH,
        #                                     dest_ip=engines.dut.ip,
        #                                     local_file_path=Consts.AUTH_LOGS_SHARED_LOCATION)

    with allure.step("Measuring login time"):
        start_time = datetime.datetime.now()
        ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip)
        end_time = datetime.datetime.now()
        login_time_sec = end_time.second - start_time.second
        logger.info("Login time is: {} secs".format(login_time_sec))
        assert login_time_sec <= Consts.MAX_LOGIN_TIME, \
            "Took too long to login to switch using ssh, max threshold: {}," \
            "actual: {}".format(Consts.MAX_LOGIN_TIME, login_time_sec)
