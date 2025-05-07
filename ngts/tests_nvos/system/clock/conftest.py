import time
from ngts.tests_nvos.system.clock.ClockConsts import ClockConsts
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
import pytest
import datetime
import logging
import yaml
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import OutputFormat, SystemConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.system.System import System


@pytest.fixture(scope='session')
def valid_timezones():
    """
    @summary:
    Return valid system timezones, extracted from timezone.yaml file
    @return: list of valid system timezones (strings)
    """
    timezone_yaml_dic = ClockTools.parse_yaml_to_dic(ClockConsts.PATH_TIMEZONE_YAML).get_returned_value()
    timezones = \
        timezone_yaml_dic['components']['schemas']['system-timezone-config']['properties']['timezone']['enum']

    return timezones


@pytest.fixture(scope='session')
def system():
    """
    @summary:
    Return a System object
    """
    return System()


@pytest.fixture(scope='function')
def orig_timezone(system, engines):
    """
    @summary:
    Backup original timezone before a test, and restore it after
    @yield: original timezone (before test)
    """
    with allure.step("Backup current timezone from 'nv show system date-time'"):
        original_timezone = ClockTools.normalize_timezone(OutputParsingTool.parse_json_str_to_dictionary(system.datetime.show())
                                                          .get_returned_value()[SystemConsts.TIMEZONE])
        logging.info("Backup current timezone from 'nv show system date-time'\torig timezone: {tz}".format(tz=original_timezone))

    yield original_timezone

    with allure.step("Restore timezone to original (after test)"):
        logging.info("Restore timezone to original (after test)\torig timezone: {tz}".format(tz=original_timezone))
        ClockTools.set_timezone(original_timezone, system).verify_result()


# @pytest.fixture(scope='function')
# def datetime_backup_restore(system, valid_system_timezones, orig_timezone):
#     """
#     @summary:
#         Fixture for fixing date-time value after a test.
#         this fixture mainly uses orig_timezone fixture.
#         the current fixture changes to another different timezone,
#         then the test does whatever it needs to, and eventually the
#         orig_timezone fixture will restore the timezone, which will fix
#         the date-time value too.
#     """
#     with allure.step("Backup date-time: saving orig_datetime"):
#         logging.info("Backup date-time: saving orig_datetime")
#         orig_datetime = ClockTools.get_datetime_from_show_system_output(system.show())
#         logging.info("Backup date-time: saving orig_datetime - {dt}".format(dt=orig_datetime))

#     with allure.step("Backup date-time: changing to another timezone"):
#         logging.info("Backup date-time: changing to another timezone")
#         different_timezone = RandomizationTool.select_random_value(valid_system_timezones,
#                                                                    forbidden_values=[orig_timezone])\
#             .get_returned_value()
#         logging.info("Backup date-time: changing to another timezone\t{tz}".format(tz=different_timezone))
#         set_timezone(different_timezone).verify_result()

#     yield orig_datetime

#     with allure.step("Restore date-time: orig_timezone restores the timezone -> fixes the date-time too"):
#         logging.info("Restore date-time: orig_timezone restores the timezone -> fixes the date-time too")


@pytest.fixture(scope='function')
def ntp_off(system):
    """Fixture to disable NTP before test, and restore it to it's original state
    """
    with allure.step('Getting the original state of ntp'):
        orig_ntp_state = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()) \
            .get_returned_value()[ClockConsts.STATE]
        logging.info('Original ntp state: "{}"'.format(orig_ntp_state))

    should_change = orig_ntp_state == ClockConsts.ENABLED

    if should_change:
        with allure.step('Changing ntp state from "{}" to "{}"'.format(ClockConsts.ENABLED, ClockConsts.DISABLED)):
            system.ntp.set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.DISABLED, apply=True).verify_result()

    yield should_change

    if should_change:
        with allure.step('Changing back ntp state from "{}" to "{}"'.format(ClockConsts.DISABLED, ClockConsts.ENABLED)):
            system.ntp.set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.ENABLED, apply=True).verify_result()
            time.sleep(10)


@pytest.fixture(scope='function')
def ntp_on(system):
    """Fixture to enable NTP before test, and restore it to it's original state
    """
    with allure.step('Getting the original state of ntp'):
        orig_ntp_state = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()) \
            .get_returned_value()[ClockConsts.STATE]
        logging.info('Original ntp state: "{}"'.format(orig_ntp_state))

    should_change = orig_ntp_state == ClockConsts.DISABLED

    if should_change:
        with allure.step('Changing ntp state from "{}" to "{}"'.format(ClockConsts.DISABLED, ClockConsts.ENABLED)):
            system.ntp.set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.ENABLED, apply=True).verify_result()

    yield

    if should_change:
        with allure.step('Changing back ntp state from "{}" to "{}"'.format(ClockConsts.ENABLED, ClockConsts.DISABLED)):
            system.ntp.set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.DISABLED, apply=True).verify_result()


@pytest.fixture(scope='function')
def init_datetime(system):
    """Fixture to enable NTP before test, and restore it to it's original state
    """
    with allure.step('Getting current date-time before test'):
        orig_dt = ClockTools.get_local_time_from_show_system_date_time_output(system.datetime.show())
        logging.info('date-time before test: {}'.format(orig_dt))

    yield orig_dt

    with allure.step('Getting current state of ntp after test'):
        cur_ntp_state = OutputParsingTool.parse_json_str_to_dictionary(system.ntp.show()) \
            .get_returned_value()[ClockConsts.STATE]
        logging.info('ntp state after test: "{}"'.format(cur_ntp_state))

    if cur_ntp_state == ClockConsts.DISABLED:
        with allure.step('Changing ntp state from "{}" to "{}"'.format(ClockConsts.DISABLED, ClockConsts.ENABLED)):
            system.ntp.set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.ENABLED, apply=True).verify_result()

        with allure.step('Wait {} seconds for ntp to sync time'.format(ClockConsts.WAIT_TIME)):
            time.sleep(ClockConsts.WAIT_TIME)

        with allure.step('Changing back ntp state from "{}" to "{}"'.format(ClockConsts.ENABLED, ClockConsts.DISABLED)):
            system.ntp.set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.DISABLED, apply=True).verify_result()


@pytest.fixture(scope='function')
def pwh_off(system):
    """Fixture to disable Password Hardening before test, and restore it to it's original state
    """
    with allure.step('Getting the original state of ntp'):
        orig_pwh_state = OutputParsingTool.parse_json_str_to_dictionary(system.security.password_hardening.show()) \
            .get_returned_value()[ClockConsts.STATE]
        logging.info('Original pwh state: "{}"'.format(orig_pwh_state))

    should_change = orig_pwh_state == ClockConsts.ENABLED

    if should_change:
        with allure.step('Changing pwh state from "{}" to "{}"'.format(ClockConsts.ENABLED, ClockConsts.DISABLED)):
            system.security.password_hardening \
                .set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.DISABLED, apply=True).verify_result()

    yield

    if should_change:
        with allure.step('Changing back pwh state from "{}" to "{}"'.format(ClockConsts.DISABLED, ClockConsts.ENABLED)):
            system.security.password_hardening \
                .set(op_param_name=ClockConsts.STATE, op_param_value=ClockConsts.ENABLED, apply=True).verify_result()
