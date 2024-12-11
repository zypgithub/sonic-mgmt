from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import UserRole
from ngts.tests_nvos.general.security.helpers import set_new_random_users
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo


@pytest.fixture
def local_admin_users() -> List[UserInfo]:
    users: List[UserInfo] = set_new_random_users(5, UserRole.ADMIN)
    return users


@pytest.fixture
def local_monitor_users() -> List[UserInfo]:
    users: List[UserInfo] = set_new_random_users(5, UserRole.MONITOR)
    return users
