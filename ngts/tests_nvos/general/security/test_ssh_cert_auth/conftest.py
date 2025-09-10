import pytest
import logging
from typing import List

from ngts.tests_nvos.general.security.test_ssh_cert_auth.helpers import (
    SshCertAuthHelper,
)
from ngts.tests_nvos.general.security.helpers import (
    set_new_random_users,
)
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.helpers.general_helpers import generate_rand_str
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.nvos_constants.constants_nvos import UserRole

logger = logging.getLogger(__name__)


@pytest.fixture(scope='function')
def ssh_cert_auth_helper():
    return SshCertAuthHelper()


@pytest.fixture(scope='function')
def ssh_cert_auth_helper_with_cleanup():
    """
    Fixture to ensure clean test environment before and after each test.

    This fixture automatically runs before and after each test to ensure
    no leftover keys or certificates interfere with tests.
    """
    ssh_cert_auth_helper: SshCertAuthHelper = SshCertAuthHelper()
    key_name = f'test_key_{generate_rand_str(10)}'
    with allure.step("Pre-test cleanup"):
        ssh_cert_auth_helper.ensure_keys_directory()

    yield ssh_cert_auth_helper, key_name

    with allure.step("Post-test cleanup"):
        ssh_cert_auth_helper.cleanup_generated_keys(key_name)


@pytest.fixture(scope='function')
def local_admin_user() -> UserInfo:
    users: List[UserInfo] = set_new_random_users(1, UserRole.ADMIN, True)
    return users[0]


@pytest.fixture(scope='function')
def local_monitor_user() -> UserInfo:
    users: List[UserInfo] = set_new_random_users(1, UserRole.MONITOR, True)
    return users[0]
