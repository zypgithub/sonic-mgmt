"""ISSU Test Configuration - Dynamic FW Image Detection for Last_FW testing."""
import logging
import os
import pytest

from ngts.nvos_constants.constants_nvos import IssuConsts
from ngts.nvos_tools.infra.NvosGitTool import NvosGitTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.system.issu.test_system_issu import install_system_image_and_start_opensm

logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def prepare_and_recover_issu(engines, devices, target_version, issu_version, request):
    """Setup: find previous FW image. Teardown: recover to target version."""
    logger.info("Starting ISSU session")
    logger.info(f"Target version: {target_version}")

    # Use NvosGitTool to find previous FW image
    git_tool = NvosGitTool()

    try:
        version, image_type = git_tool.parse_version_from_path(target_version)
        logger.info(f"Detected image type: {image_type}")
    except ValueError as e:
        logger.warning(f"Could not parse target version: {e}")
        image_type = 'dev'

    prev_fw_path = git_tool.find_previous_fw_image_path(target_version, asic_type='QTM3')

    if not prev_fw_path or not os.path.exists(prev_fw_path):
        # Fallback to GA version - test will be skipped if Last_FW == Last_GA
        logger.warning(f"Could not find previous FW image, falling back to GA version")
        logger.warning(f"Last_FW test will be skipped (same as Last_GA)")
        prev_fw_path = issu_version  # Set to GA version so skip condition triggers

    logger.info(f"Previous FW image: {prev_fw_path}")
    request.config.issu_last_fw_path = prev_fw_path

    yield

    # Teardown: recover system to target version
    system = System(devices_dut=devices.dut)
    if hasattr(engines, 'ha') and hasattr(engines, 'hb'):
        with allure.step("Recover system to target image"):
            install_system_image_and_start_opensm(engines, devices.dut, system, target_version, False)
        with allure.step("Clean temp files"):
            for engine, output in [(engines.ha, IssuConsts.SERVER_OUTPUT), (engines.hb, IssuConsts.CLIENT_OUTPUT)]:
                if engine.run_cmd(f'ls {output}'):
                    engine.run_cmd(f'rm -f {output}')
    else:
        with allure.step("Recover system to target image"):
            install_system_image_and_start_opensm(engines, devices.dut, system, target_version)
