import pytest

from ngts.nvos_tools.infra.Fae import Fae
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='module', autouse=True)
def clear_debug_info_files():
    fae = Fae(None)
    debug_image = fae.platform.debug.info.debug_image
    with allure.step('delete fetched firmware image files'):
        files = debug_image.files.get_files()
        debug_image.files.delete_files(files_to_delete=files)
