import re
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.password_hardening.PwhConsts import PwhConsts
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tests_nvos.general.security.security_test_tools.security_test_utils import set_local_users
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session')
def system():
    """
    Fixture that returns a System object
    """
    return System()


@pytest.fixture(scope='function')
def testing_users(engines, devices, system):
    """
    Fixture that sets new users especially for test (and cleans them afterwards).
    There are 2 test users: 'test_admin' and 'test_monitor'.
    @return: (yield) Dictionary of
        {
            <username (str)>:    {
                                    'user_object': <User obj>, 'password': <pw (str)>
                                }
        }
    """
    with allure.step("Before test: set local test users"):
        users_info = devices.dut.local_test_users
        set_local_users(engines, users_info, apply=True)

        users = {
            user[AaaConsts.USERNAME]: {
                PwhConsts.USER_OBJ: System(force_api=ApiType.NVUE).aaa.user.user_id[user[AaaConsts.USERNAME]],
                AaaConsts.PASSWORD: user[AaaConsts.PASSWORD]
            } for user in users_info
        }

    return users


@pytest.fixture(scope='function')
def init_time(engines, system):
    """
    Prepare test in perspective of time. including:
        - disable ntp before test, and re-enable it after
        - set time to an early enough hour of the day, such that a day won't pass during the test
            (and restore it after the test)
        - restores the date to original before test
    """

    with allure.step('Disable NTP'):
        system.ntp.set(op_param_name=PwhConsts.STATE, op_param_value=PwhConsts.DISABLED, apply=True).verify_result()
        time.sleep(3)

    with allure.step('Save original datetime before test'):
        orig_datetime = ClockTools.get_local_time_from_show_system_date_time_output(system.datetime.show())
        morning_datetime = re.sub(PwhConsts.REGEX_TIME, '03:00:00', orig_datetime)

    with allure.step('Change time to 3AM ({})'.format(morning_datetime)):
        system.datetime.action_change(params=morning_datetime).verify_result()

    yield

    with allure.step('Enable NTP'):
        system.ntp.set(op_param_name=PwhConsts.STATE, op_param_value=PwhConsts.ENABLED, apply=True).verify_result()
        time.sleep(3)


@pytest.fixture()
def disable_password_hardening():
    with allure.step('disable password hardening before test'):
        pwh = System().security.password_hardening
        pwh.set(PwhConsts.STATE, PwhConsts.DISABLED, apply=True).verify_result()
    yield
    with allure.step('reset password hardening after test'):
        pwh.unset(apply=True).verify_result()
