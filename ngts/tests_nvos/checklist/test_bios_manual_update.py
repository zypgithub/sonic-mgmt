import logging
import random

import pytest

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.platform.test_platform_firmware_bios.helpers import get_bios_info_from_device, fetch_and_install_bios, verify_bios_version
from ngts.nvos_tools.platform.Platform import Platform
from ngts.scripts.bios_config import configure_bios
from ngts.tests_nvos.constants import MINUTE

logger = logging.getLogger()


@pytest.fixture(scope='module', autouse=True)
def restore_bios(topology_obj):
    yield
    configure_bios(topology_obj)


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.bios
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_manual_update(engines, devices, topology_obj, test_api):
    """
    Test flow:
        1. fetch alternate BIOS version
        2. install the alternate BIOS version using nv action install fae platform firmware BIOS <abs-path-to-file>
        3. power cycle
        4. validate BIOS version was changed in nv show platform firmware
        5. install the current latest BIOS version (the one the machine begun the test with)
        6. power cycle
        7. validate BIOS version was changed in nv show platform firmware

    Description:
    This test is specifically for systems that do not have BIOS auto-update feature. It is pruned for such systems,
    as the following test logic will not work if auto-update is enabled.
    Currently, only Juliet systems are supported.

    """

    TestToolkit.tested_api = test_api

    with allure.step('Create System object'):
        platform = Platform()

    try:
        path, filename, version_name, date = get_bios_info_from_device(devices.dut, 'alternate_version')
        fetch_and_install_bios(platform=platform, path=path, name=version_name, filename=filename,
                               topology_obj=topology_obj)
        verify_bios_version(engines, platform, version_name, date)

    finally:
        path, filename, version_name, date = get_bios_info_from_device(devices.dut, 'current_version')
        fetch_and_install_bios(platform=platform, path=path, name=version_name, filename=filename,
                               topology_obj=topology_obj)
        verify_bios_version(engines, platform, version_name, date)
