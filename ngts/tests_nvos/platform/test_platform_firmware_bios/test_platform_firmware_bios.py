import random
import pytest

from ngts.nvos_constants.constants_nvos import ApiType, NvosConst
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.platform.test_platform_firmware_bios.helpers import *
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.timeout(25 * MINUTE, func_only=True)
@pytest.mark.bios
@pytest.mark.system
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_auto_update_disabled(devices, engines, test_api, original_version, get_image_data_and_fetch_image, test_name):
    """
    Test flow:
        1. fetch target image version
        2. fetch current and previous BIOS versions
        3. downgrade to previous BIOS version
        4. install target image
        5. validate BIOS version was NOT updated in nv show platform firmware
        6. cleanup
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System objects'):
        platform = Platform()
        fae = Fae()
        system = System()

    verify_current_version(original_version, system)
    verify_bios_auto_update_value(platform, NvosConst.ENABLED)

    with allure.step('Fetch image - target_version_realpath fixture'):
        original_image_partition, fetched_image_curr = get_image_data_and_fetch_image

    try:

        orig_engine: LinuxSshEngine = TestToolkit.engines.dut

        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.DISABLED, apply=True).verify_result()
        verify_bios_auto_update_value(platform, NvosConst.DISABLED)
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)

        install_bios(devices, fae, devices.dut.previous_bios_version_name)
        verify_bios_version(devices, platform)

        install_image_and_verify(orig_engine=orig_engine, image_name=fetched_image_curr, system=system,
                                 test_name=test_name)

        verify_bios_version(devices, platform)

    except Exception as e:
        logger.info("Received Exception during test: {}".format(e))
        raise e

    finally:
        # cleanup
        cleanup_test(system=system, original_image_partition=original_image_partition)
        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.ENABLED, apply=True).verify_result()
        verify_bios_auto_update_value(platform, NvosConst.ENABLED)
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)


@pytest.mark.timeout(25 * MINUTE, func_only=True)
@pytest.mark.bios
@pytest.mark.system
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_auto_update_enabled(devices, engines, test_api, original_version, get_image_data_and_fetch_image, test_name):
    """
    Test flow:
        1. fetch target image version
        2. fetch current and previous BIOS versions
        3. downgrade to previous BIOS version
        4. install target image
        5. validate BIOS version was updated in nv show platform firmware
        6. cleanup
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System objects'):
        platform = Platform()
        fae = Fae()
        system = System()

    verify_current_version(original_version, system)
    verify_bios_auto_update_value(platform, NvosConst.ENABLED)

    with allure.step('Fetch image - target_version_realpath fixture'):
        original_image_partition, fetched_image_curr = get_image_data_and_fetch_image

    try:

        orig_engine: LinuxSshEngine = TestToolkit.engines.dut
        if get_bios_version(platform) == devices.dut.current_bios_version_name:
            platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                       op_param_value=NvosConst.DISABLED, apply=True).verify_result()
            TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)
            verify_bios_auto_update_value(platform, NvosConst.DISABLED)
            install_bios(devices, fae, devices.dut.previous_bios_version_name)
            platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                       op_param_value=NvosConst.ENABLED, apply=True).verify_result()
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)
        verify_bios_version(devices, platform)

        install_image_and_verify(orig_engine=orig_engine, image_name=fetched_image_curr, system=system,
                                 test_name=test_name)

        verify_bios_version(devices, platform, True)

    except Exception as e:
        logger.info("Received Exception during test: {}".format(e))
        raise e

    finally:
        # cleanup
        cleanup_test(system=system, original_image_partition=original_image_partition)
