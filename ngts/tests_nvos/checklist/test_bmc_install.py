import logging
import random

import pytest
from retry import retry

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import BmcUsers
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.timeout(60 * MINUTE, func_only=True)
@pytest.mark.bmc
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
@pytest.mark.parametrize("platform_component_with_clear", ["bmc"], indirect=True)
def test_bmc_install(engines, devices, topology_obj, test_api, platform_component_with_clear, test_name):
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
    curl_tool = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=BmcUsers.root.username,
                         password=BmcUsers.root.another_password)

    try:
        path, filename, version_name = BmcTool.get_fw_component_version_previous(component_name)
        BmcTool.fetch_and_install_platform_component(platform_component=platform_component_with_clear, path=path,
                                                     name=version_name, filename=filename, topology_obj=topology_obj,
                                                     test_name=test_name)
        BmcTool.verify_platform_component_version(platform_component_with_clear, version_name)
        with allure.step(f"Verify background copy status is completed in 7 minutes time"):
            _check_background_copy_completed(curl_tool, path='/Chassis/MGX_ERoT_BMC_0')
    finally:
        path, filename, version_name = BmcTool.get_fw_component_version_latest(component_name)
        BmcTool.fetch_and_install_platform_component(platform_component=platform_component_with_clear, path=path,
                                                     name=version_name, filename=filename, topology_obj=topology_obj,
                                                     test_name=test_name)
        BmcTool.verify_platform_component_version(platform_component_with_clear, version_name)
        # BmcTool.compare_bmc_version_issu_module(engines, version_name)  !TBD uncomment after merge 1800 to master


@retry(AssertionError, tries=14, delay=30)
def _check_background_copy_completed(curl_tool, path):
    erot_bmc_output = curl_tool.run_redfish_command(rest_op='GET', path=path)
    erot_status_dict = OutputParsingTool.parse_json_str_to_dictionary(erot_bmc_output).get_returned_value()
    background_copy_status = erot_status_dict['Oem']['Nvidia']['BackgroundCopyStatus']
    assert background_copy_status == "Completed", "Background copy status is not completed"
