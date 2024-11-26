import logging
import random
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.bmc
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
@pytest.mark.parametrize("platform_component_with_clear", ["fpga"], indirect=True)
def test_fpga_install(engines, devices, topology_obj, test_api, platform_component_with_clear):
    """
    @summary: test all these commands:
        nv show platform firmware BMC files
        nv action delete platform firmware BMC files <file-name>
        nv action fetch platform firmware BMC <remote-url-fetch>
        nv action install platform firmware BMC files <file-name> [force]
    Note: because firmware installation takes a long time and the test does it twice,
    the test randomly chooses to do it on OpenApi or NVUE

    Test flow:
        1. Check if device has BMC or skip
        2. Fetches and installs BMC alternate_version
        3. Verifies correct versioning for installed fw package.
        4. Fetches and installs BMC current_version
        5. Verifies correct versioning for installed fw package.
    """
    device = devices.dut
    with allure.step('Check whether device has BMC'):
        bmc_older_version_path = getattr(device, 'bmc_older_version_path', None)
        if bmc_older_version_path is None:
            pytest.fail("Device does not have BMC. Failing the test on this setup.")

    TestToolkit.tested_api = test_api
    component_name = platform_component_with_clear.get_resource_basename().lower()

    platform = Platform()
    platform_output = OutputParsingTool.parse_show_output_to_dict(platform.show()).get_returned_value()
    # 692-9K36F-A5MV-JQS has encrypted fpga
    if platform_output[PlatformConsts.FW_PART_NUMBER].strip() == "692-9K36F-A5MV-JQS":
        component_name = f"{component_name}_encrypted"

    try:
        path, filename, version_name = BmcTool.get_fw_component_version_previous(component_name)
        BmcTool.fetch_and_install_platfrom_component(platform_component=platform_component_with_clear, path=path,
                                                     name=version_name, filename=filename,
                                                     topology_obj=topology_obj)
        BmcTool.verify_platform_component_version(platform_component_with_clear, version_name)
        with allure.step(f"Sleep for {2 * MINUTE} seconds so background-copy will finish"):
            time.sleep(2 * MINUTE)
    finally:
        path, filename, version_name = BmcTool.get_fw_component_version_latest(component_name)
        BmcTool.fetch_and_install_platfrom_component(platform_component=platform_component_with_clear, path=path,
                                                     name=version_name, filename=filename,
                                                     topology_obj=topology_obj)
        BmcTool.verify_platform_component_version(platform_component_with_clear, version_name)
