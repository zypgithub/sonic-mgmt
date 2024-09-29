import pytest

from ngts.tests_nvos.general.security.test_ssh_pka.helpers import _generate_new_key, keys_path
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.SecuritySshTool import SecuritySshTool
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(autouse=True)
def generate_new_admin_keys(engines):
    with allure.step("generate new key for admin"):
        admin_key, admin_key_type, admin_private_key_path = _generate_new_key(engines.dut, 'admin')

    yield (admin_key, admin_key_type, admin_private_key_path)

    with allure.step(f"delete keys for admin"):
        SecuritySshTool.rm_auth_keypair(f"{keys_path}/admin")
