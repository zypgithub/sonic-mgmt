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


@pytest.fixture(scope='module')
def asic_conf_dict(engines) -> dict:
    """
    Parses asic.conf file to dict
        NUM_ASIC = 4
        DEV_ID_ASIC_0 = 05:00.0
        DEV_ID_ASIC_1 = 04:00.0
        DEV_ID_ASIC_2 = 03:00.0
        DEV_ID_ASIC_3 = 09:00.0
    """
    asic_conf = dict()

    system = System()
    system_info = OutputParsingTool.parse_json_str_to_dictionary(
        system.show()).get_returned_value()
    asic_conf_path = PlatformConsts.ASIC_CONF_FILE_PATH.format(system_info[SystemConsts.PLATFORM])
    with allure.step(f"Generate asic conf dictionary from {asic_conf_path}"):
        asic_conf_values = engines.dut.run_cmd(f"cat {asic_conf_path}")
        for line in asic_conf_values.split('\n'):
            line = line.strip()

            if not line or '=' not in line:
                continue

            asic_dev_id, value = line.split('=')

            asic_conf[asic_dev_id] = value

        return asic_conf


@pytest.fixture(scope='function')
def clear_asic_files():
    yield
    platform = Platform()
    with allure.step('delete fetched firmware asic image files'):
        files = platform.firmware.asic.files.get_files()
        platform.firmware.asic.files.delete_files(files_to_delete=files)
