import random
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, NvosConst
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.platform.test_platform_firmware_bios.helpers import *
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.timeout(15 * MINUTE, func_only=True)
@pytest.mark.bios
@pytest.mark.system
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_auto_update_disabled(devices, engines, topology_obj, test_api, original_version):
    """
    Test flow:
        1. fetch current and previous BIOS versions
        2. downgrade to previous BIOS version
        3. reboot
        4. validate BIOS version was NOT updated in nv show platform firmware
        5. cleanup
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System objects'):
        platform = Platform()
        fae = Fae()
        system = System()

    verify_current_version(original_version, system)
    verify_bios_auto_update_value(platform, NvosConst.ENABLED)

    try:
        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.DISABLED, apply=True).verify_result()
        verify_bios_auto_update_value(platform, NvosConst.DISABLED)
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)

        install_bios(devices, fae, devices.dut.previous_bios_version_name, topology_obj)
        verify_bios_version(devices, platform)

        system.reboot.action_reboot(topology_obj=topology_obj)

        verify_bios_version(devices, platform)

    except Exception as e:
        logger.info("Received Exception during test: {}".format(e))
        raise e

    finally:
        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.ENABLED, apply=True).verify_result()
        verify_bios_auto_update_value(platform, NvosConst.ENABLED)
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)


@pytest.mark.timeout(15 * MINUTE, func_only=True)
@pytest.mark.bios
@pytest.mark.system
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_auto_update_enabled(devices, engines, topology_obj, test_api, original_version):
    """
    Test flow:
        1. fetch current and previous BIOS versions
        2. downgrade to previous BIOS version
        3. reboot
        4. validate BIOS version was updated in nv show platform firmware
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System objects'):
        platform = Platform()
        fae = Fae()
        system = System()

    verify_current_version(original_version, system)
    verify_bios_auto_update_value(platform, NvosConst.ENABLED)

    if get_bios_version(platform) == devices.dut.current_bios_version_name:
        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.DISABLED, apply=True).verify_result()
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)
        verify_bios_auto_update_value(platform, NvosConst.DISABLED)
        install_bios(devices, fae, devices.dut.previous_bios_version_name, topology_obj)
        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.ENABLED, apply=True).verify_result()
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)

    verify_bios_version(devices, platform)
    system.reboot.action_reboot(topology_obj=topology_obj)

    verify_bios_version(devices, platform, True)
