import pytest
import logging

from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.fixture(scope='function')
def platform_component_with_clear(request):
    platform_component_name = request.param
    platform_component = getattr(Platform().firmware, platform_component_name)
    yield platform_component
    with allure.step('delete fetched firmware image files'):
        files = platform_component.files.get_files()
        platform_component.files.delete_files(files_to_delete=files)
