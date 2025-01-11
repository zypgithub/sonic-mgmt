from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import UserRole
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.helpers import set_new_random_users, delete_all_imported_cas, \
    delete_all_imported_certs
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo


@pytest.fixture
def local_admin_users() -> List[UserInfo]:
    users: List[UserInfo] = set_new_random_users(5, UserRole.ADMIN, True)
    return users


@pytest.fixture
def local_monitor_users() -> List[UserInfo]:
    users: List[UserInfo] = set_new_random_users(5, UserRole.MONITOR, True)
    return users


@pytest.fixture(scope='session', autouse=True)
def cleanup_certs():
    System().api.unset(apply=True).verify_result()
    delete_all_imported_cas()
    delete_all_imported_certs()
    yield
    System().api.unset(apply=True).verify_result()
    delete_all_imported_cas()
    delete_all_imported_certs()
