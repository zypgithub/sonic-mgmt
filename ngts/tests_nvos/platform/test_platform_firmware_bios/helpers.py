import time
import re
import logging
import string
from typing import Tuple
import string
import pytest


from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.redmine.redmine_api import *
from ngts.nvos_constants.constants_nvos import ImageConsts, PlatformConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.Tools import Tools

logger = logging.getLogger()


def get_bios_version(platform) -> str:
    with allure.step('get  BIOS version '):
        fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
        return fw_output[PlatformConsts.FW_BIOS][PlatformConsts.FW_ACTUAL]


def verify_current_version(original_version, system):
    with allure.step(f"Verify that current image is {original_version}"):
        current_version = system.version.get_nvos_image_version()
        assert current_version == original_version, f"Current version is invalid: {current_version}, expected: {original_version}"


def verify_bios_auto_update_value(platform, value):
    with allure.step(f'verify nv show platform firmware BIOS auto-update is {value}'):
        logging.info(f'verify nv show platform firmware BIOS auto-update is {value}')
        output = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.bios.show()).verify_result()
        assert value == output[PlatformConsts.FW_AUTO_UPDATE], f"auto-update should be {value}"


def verify_bios_version(engines, platform, expected_version: str):
    with allure.step(f'Making sure BIOS is now on version {expected_version}'):
        fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
        new_bios_version = fw_output[PlatformConsts.FW_BIOS][PlatformConsts.FW_ACTUAL]
        logger.info(f"Found BIOS version: {new_bios_version}")

        assert new_bios_version == expected_version, \
            f"BIOS firmware is {new_bios_version}, expected {expected_version} after the install"


def fetch_and_install_bios(platform, path, name, filename, topology_obj, test_name) -> ResultObj:
    with allure.step(f'Fetch {name} Bios image from: {path}'):
        platform.firmware.bios.action_fetch(path).verify_result()

    with allure.step(f'installing Bios image {name}'):
        res, duration = OperationTime.save_duration(f'install BIOS {name}', '',
                                                    test_name, platform.firmware.bios.files.file_name[filename].action_file_install_with_reboot,
                                                    topology_obj=topology_obj, system_is_ready_timeout=PlatformConsts.TIMEOUT_AFTER_BIOS_INSTALL)
        return res
