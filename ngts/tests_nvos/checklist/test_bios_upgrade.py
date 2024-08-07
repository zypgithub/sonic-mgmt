import logging
import random

import pytest

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.platform.Platform import Platform
from ngts.scripts.bios_config import configure_bios
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot


logger = logging.getLogger()


@pytest.fixture(scope='module', autouse=True)
def restore_bios(topology_obj):
    yield
    configure_bios(topology_obj)


@pytest.mark.bios
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_bios_upgrade(engines, devices, topology_obj, test_api):
    """
    Test flow:
        1. fetch alternate BIOS version
        2. install the alternate BIOS version using nv action install fae platform firmware BIOS <abs-path-to-file>
        3. power cycle
        4. validate BIOS version was changed in nv show platform firmware
        5. install the current latest BIOS version (the one the machine begun the test with)
        6. power cycle
        7. validate BIOS version was changed in nv show platform firmware
    """

    TestToolkit.tested_api = test_api

    with allure.step('Create System object'):
        platform = Platform()
        fae = Fae()

    try:
        path, filename, version_name, date = get_bios_info_from_device(devices.dut, 'alternate_version')
        fetch_and_install_bios(fae=fae, path=path, name=version_name,
                               filename=filename)
        recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)
        verify_bios_version(engines, platform, version_name, date)

    finally:
        path, filename, version_name, date = get_bios_info_from_device(devices.dut, 'current_version')
        fetch_and_install_bios(fae=fae, path=path, name=version_name,
                               filename=filename)
        recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config=False)
        verify_bios_version(engines, platform, version_name, date)


def verify_bios_version(engines, platform, expected_version: str, date: str):
    with allure.step(f'Making sure BIOS is now on version {expected_version}'):
        fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
        new_bios_version = fw_output[PlatformConsts.FW_BIOS][PlatformConsts.FW_ACTUAL]
        logger.info(f"Found BIOS version: {new_bios_version}")

        assert new_bios_version == expected_version, \
            f"BIOS firmware is {new_bios_version}, expected {expected_version} after the install"

        dmidecode_output = engines.dut.run_cmd("sudo dmidecode -t0 -t11 | grep -E 'Release Date:|String 1:'")
        assert date in dmidecode_output, \
            f"Expected to find {date} in this output: {dmidecode_output}"


def fetch_and_install_bios(fae, path, name, filename):
    with allure.step(f'Fetch {name} Bios image from: {path}'):
        fae.platform.firmware.bios.action_fetch(path).verify_result()

    with allure.step(f'installing Bios image {name}'):
        fae.platform.firmware.bios.action_install(filename=filename, device=None, expect_reboot=False)


def get_bios_info_from_device(device, version):
    with allure.step(f'get BIOS info from {device}'):
        bios_image_info = getattr(device.bios_image_info, version)
        return bios_image_info['path'], bios_image_info['filename'], bios_image_info['version_name'], bios_image_info['date']