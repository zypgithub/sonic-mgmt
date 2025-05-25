import pytest

from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.scripts.bios_config import configure_bios
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.platform.test_platform_firmware_bios.helpers import *


@pytest.fixture(scope='function', autouse=True)
def clear_files():
    yield
    platform = Platform()
    with allure.step('delete fetched firmware image files'):
        files = platform.firmware.bios.files.get_files()
        platform.firmware.bios.files.delete_files(files_to_delete=files).verify_result()


@pytest.fixture(scope='module', autouse=True)
def restore_bios(topology_obj):
    yield
    configure_bios(topology_obj)
