import pytest
import logging

from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import PlatformConsts, SystemConsts


@pytest.fixture(scope='module')
def skip_for_fanless_setup(devices):
    """
    If setup has no fans, JulietNonScaleoutSwitchGB300, skip test.
    """
    if len(devices.dut.fan_list) == 0:
        pytest.skip("Skipping all tests in this module because setup has no fans")


logger = logging.getLogger()


@pytest.fixture(scope='function')
def clear_asic_files():
    yield
    platform = Platform()
    with allure.step('delete fetched firmware asic image files'):
        files = platform.firmware.asic.files.get_files()
        platform.firmware.asic.files.delete_files(files_to_delete=files).verify_result()
