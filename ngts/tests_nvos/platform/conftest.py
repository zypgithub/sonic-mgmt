import pytest

from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='function')
def clear_asic_files():
    yield
    platform = Platform()
    with allure.step('delete fetched firmware asic image files'):
        files = platform.firmware.asic.files.get_files()
        platform.firmware.asic.files.delete_files(files_to_delete=files)
