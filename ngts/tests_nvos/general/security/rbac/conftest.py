import pytest

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import ApiType


@pytest.fixture(scope='function', autouse=True)
def clear_system_aaa(test_name):
    yield
    with allure.step(f'cleanup for RBAC test {test_name}'):
        system = System(force_api=ApiType.NVUE)
        system.aaa.user.action_disconnect()
        system.aaa.unset(apply=True, ask_for_confirmation=True)
