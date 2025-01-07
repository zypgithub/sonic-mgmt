import logging
import pytest
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.system.issu.test_system_issu import install_system_image_and_start_opensm

logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def prepare_and_recover_issu(engines, devices, target_version):
    """
    Prepare to run ISSU and recover system when ISSU session is done
    """

    logger.info(f"start running ISSU session")

    yield

    system = System(devices_dut=devices.dut)

    with allure.step(f"Recover system to target image"):
        install_system_image_and_start_opensm(engines, devices.dut, system, target_version)
