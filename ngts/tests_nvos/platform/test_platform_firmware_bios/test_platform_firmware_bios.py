import random
import pytest

from ngts.nvos_constants.constants_nvos import ApiType, NvosConst
from ngts.nvos_tools.infra.FWComponentsTool import FWComponentsTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.platform.test_platform_firmware_bios.helpers import *
from infra.tools.redmine.redmine_api import *
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.bios
@pytest.mark.system
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_auto_update_disabled(devices, engines, topology_obj, test_api, original_version, test_name):
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
        system = System()
        component_name = 'bios'

    verify_current_version(original_version, system)
    try:

        verify_bios_auto_update_value(platform, NvosConst.ENABLED)
        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.DISABLED, apply=True).verify_result()
        verify_bios_auto_update_value(platform, NvosConst.DISABLED)
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)
        path, filename, version_name = FWComponentsTool.get_fw_component_version_latest(component_name)
        fetch_and_install_bios(platform=platform, path=path, name=version_name, filename=filename,
                               topology_obj=topology_obj, system_is_ready_timeout=PlatformConsts.TIMEOUT_AFTER_FW_INSTALL)
        verify_bios_version(engines, platform, version_name)

        with allure.step('Reboot with previous BIOS version installation'):
            res, duration = OperationTime.save_duration('reboot with BIOS 006 installation', '',
                                                        test_name, system.reboot.action_reboot, topology_obj=topology_obj)

        verify_bios_version(engines, platform, version_name)

    finally:
        platform.firmware.bios.set(op_param_name=PlatformConsts.FW_AUTO_UPDATE,
                                   op_param_value=NvosConst.ENABLED, apply=True).verify_result()
        verify_bios_auto_update_value(platform, NvosConst.ENABLED)
        TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.bios
@pytest.mark.system
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_auto_update_enabled(devices, engines, topology_obj, test_api, original_version, test_name):
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
        system = System()
        component_name = 'bios'

    verify_current_version(original_version, system)
    verify_bios_auto_update_value(platform, NvosConst.ENABLED)

    path, filename, version_name = FWComponentsTool.get_fw_component_version_latest(component_name)
    verify_bios_version(engines, platform, version_name)
    with allure.step('Installation and reboot with BIOS version 005 '):
        res, duration = OperationTime.save_duration('reboot with BIOS 005 installation', '',
                                                    test_name, system.reboot.action_reboot, topology_obj=topology_obj, system_is_ready_timeout=PlatformConsts.TIMEOUT_AFTER_BIOS_INSTALL)

    path, filename, version_name = FWComponentsTool.get_fw_component_version_previous(component_name)
    verify_bios_version(engines, platform, version_name)