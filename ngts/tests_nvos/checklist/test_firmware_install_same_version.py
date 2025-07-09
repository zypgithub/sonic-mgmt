import pytest
import logging
import random

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import OperationTimeConsts, NvosConst
from ngts.tests_nvos.constants import (FW_COMPONENT_EROT, FW_COMPONENT_BMC, FW_COMPONENT_FPGA,
                                       FW_COMPONENT_CPLD, FW_COMPONENT_BIOS)
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.FWComponentsTool import FWComponentsTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.system.gnmi.helpers import verify_msg_in_out_or_err, verify_msg_not_in_out_or_err
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.timeout(5 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_firmware_install_same_version(devices, test_api, test_name):
    """
       @summary: test 'nv action install platform firmware <component>' command without using 'skip-version-check'
        option (no need to reboot)

        Test flow:
            1.Select a random component on device
            2. Fetch and install same firmware version on component without using 'skip-version-check' option
    """
    TestToolkit.tested_api = test_api

    with allure.step("Select a random component to test"):
        component = select_random_component(devices)
        platform_component = getattr(Platform().firmware, component)

    with allure.step("Install same fw version without using 'skip-version-check' option"):
        result = install_same_firmware_version(test_name=test_name,
                                               component=component,
                                               platform_component=platform_component,
                                               skip_version_check=False)

    with allure.step("Verify output"):
        msg = "Same image already installed on the component, skipping update"
        verify_msg_in_out_or_err(msg, result)


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_firmware_install_same_version_skip_check(devices, test_api, test_name):
    """
        @summary: test 'nv action install platform firmware <component>' command while using 'skip-version-check'
        option (no need to reboot)

        Test flow:
            1.Select a random component on device
            2. Fetch and install same firmware version on component while using 'skip-version-check' option
    """
    TestToolkit.tested_api = test_api

    with allure.step("Select a random component to test"):
        component = select_random_component(devices)
        platform_component = getattr(Platform().firmware, component)

    with allure.step("Install same fw version while using 'skip-version-check' option"):
        result = install_same_firmware_version(test_name=test_name,
                                               component=component,
                                               platform_component=platform_component,
                                               skip_version_check=True)

    with allure.step("Verify output"):
        msg = "Same image already installed on the component, skipping update"
        verify_msg_not_in_out_or_err(msg, result)


@pytest.mark.timeout(15 * MINUTE, func_only=True)
@pytest.mark.erot
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_fae_erot_firmware_install(devices, test_api, test_name):
    """
        @summary: test 'skip-version-check' option on 'nv action install fae platform firmware <erot-component>' command
        (no need to reboot)

        Test flow:
            1. Check if device has BMC. Otherwise, nothing to do.
            2. Given that device has BMC, select a random erot component on device.
            3. Install same fw version on selected component without using 'skip-version-check' option.
            4. Install same fw version on selected component while using 'skip-version-check' option.
    """
    TestToolkit.tested_api = test_api

    with allure.step('Check whether device is NVL'):
        if devices.dut.switch_type != NvosConst.NVL_SWITCH_TYPE:
            pytest.skip("Device is not NVL (does not have EROT) - Nothing to do")

    with allure.step("Select a random erot component to test"):
        fae = Fae()
        erots_list = devices.dut.constants.erots
        erot_name = random.choice(erots_list)
        firmware_component = fae.platform.firmware.erot_id[erot_name]

    with allure.step("Install same fw version without using 'skip-version-check' option"):
        result_obj = install_same_firmware_version(test_name=test_name,
                                                   component=FW_COMPONENT_EROT,
                                                   platform_component=firmware_component,
                                                   skip_version_check=False)

    with allure.step("Verify output"):
        msg = "Same image already installed on the component, skipping update"
        verify_msg_in_out_or_err(msg, result_obj)

    with allure.step("Install same fw version while using 'skip-version-check' option"):
        result_obj = install_same_firmware_version(test_name=test_name,
                                                   component=FW_COMPONENT_EROT,
                                                   platform_component=firmware_component,
                                                   skip_version_check=True)

    with allure.step("Verify output"):
        msg = "Next reboot will perform a power cycle to load the new firmware"
        verify_msg_in_out_or_err(msg, result_obj)


@pytest.mark.timeout(2 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_firmware_install_invalid_version(devices, test_api, test_name):
    """
        @summary: test installing invalid fw version (already deleted version)

        Test flow:
            1. Check if device had BMC, otherwise nothing to od.
            2. If device has BMC, randomize a component from list [BMC, FPGA, BIOS, EROT].
            3. Install invalid fw version for chosen component, and expect an error.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Select a random component to test"):
        component = select_random_component(devices)
        platform_component = getattr(Platform().firmware, component)

    with allure.step(f"Delete fw image files"):
        files = platform_component.files.get_files()
        platform_component.files.delete_files(files_to_delete=files)

    with allure.step('Install deleted firmware file'):
        path, filename, version_name = FWComponentsTool.get_fw_component_version_previous(component)
        result = BmcTool.install_fw_image_without_reboot(platform_component=platform_component,
                                                         test_name=test_name,
                                                         filename=filename).verify_result(False)

    with allure.step("Verify output"):
        msg = "Failed to install firmware file: no such file"
        verify_msg_in_out_or_err(msg, result)


def install_same_firmware_version(test_name, component, platform_component, skip_version_check=False):
    """
        @summary: Given a component, install same firmware version on component (no need to reboot) using
        skip-version_check option if needed (skip_version_check=True)
    """
    try:
        with allure.step("Fetch and install current firmware version on component"):
            path, filename, version_name = FWComponentsTool.get_fw_component_version_latest(component)
            with allure.step(f"Verify current fw version on {component} is {version_name}"):
                if component == 'cpld':
                    BmcTool.verify_cpld_versions(version_name)
                else:
                    BmcTool.verify_platform_component_version(platform_component, version_name)

            operation = f'install {component}'
            duration_threshold = OperationTimeConsts.THRESHOLDS.get(operation)
            result_obj = BmcTool.fetch_and_install_platform_component_without_reboot(platform_component=platform_component,
                                                                                     path=path, name=version_name,
                                                                                     filename=filename,
                                                                                     test_name=test_name,
                                                                                     skip_version_check=skip_version_check).verify_result(expected_duration=duration_threshold)
    finally:
        with allure.step(f"Delete fetched fw image files"):
            files = platform_component.files.get_files()
            platform_component.files.delete_files(files_to_delete=files)
        return result_obj


def select_random_component(devices):
    """
        @summary: Select a random component on tested device
    """
    components_list = [FW_COMPONENT_CPLD]

    with allure.step('Check whether device has BMC'):
        has_bmc = getattr(devices.dut, 'has_bmc', None)
        if not has_bmc:
            logger.info("Device does not have BMC.")
        else:
            components_list = [FW_COMPONENT_CPLD,
                               FW_COMPONENT_BMC,
                               FW_COMPONENT_FPGA,
                               FW_COMPONENT_BIOS,
                               FW_COMPONENT_EROT]

    with allure.step("Randomize a components from components list"):
        logger.info(f"Components list = {components_list}")
        result_obj = RandomizationTool.select_random_value(list_of_values=components_list)
        if not result_obj.result:
            pytest.fail("Failed randomizing a component from list")
        else:
            return result_obj.get_returned_value()
