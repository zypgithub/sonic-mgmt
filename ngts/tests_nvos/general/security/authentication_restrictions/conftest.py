import random
import pytest

from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.authentication_restrictions.constants import RestrictionsConsts
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tests_nvos.general.security.security_test_tools import security_test_utils
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='function')
def test_user(engines):
    """
    @summary: Configure a test user
    @return: Test user info
        * as a dictionary { username: str, password: str, role: <admin/monitor> }
    """
    with allure.step('Configure test user'):
        user_details = random.choice(RestrictionsConsts.TEST_USERS).copy()
        user_details[AaaConsts.USERNAME] += str(random.randint(0, 9999))
        security_test_utils.set_local_users(engines, [user_details], apply=True)

    try:
        yield user_details
    finally:
        security_test_utils.cleanup_local_users(engines, [user_details])


@pytest.fixture(scope='function')
def test_users(engines):
    """
    @summary: Configure two test users
    @return: list of Test users info
        * as a dictionary { username: str, password: str, role: <admin/monitor> }
    """
    users = []
    with allure.step('Configure test users'):
        for _ in range(2):
            user_details = random.choice(RestrictionsConsts.TEST_USERS).copy()
            user_details[AaaConsts.USERNAME] += str(random.randint(0, 9999))
            security_test_utils.set_local_users(engines, [user_details], apply=True)
            users.append(user_details)

    try:
        yield users
    finally:
        security_test_utils.cleanup_local_users(engines, users)


@pytest.fixture(scope='function', autouse=True)
def clear_users(engines):
    """
    @summary: Clear blocked users before and after test
    """
    yield

    with allure.step('Clear all configurations after test'):
        System().aaa.authentication.restrictions.action_clear()
