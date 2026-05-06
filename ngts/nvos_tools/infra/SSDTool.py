import json
import os

import pytest

from ngts.nvos_constants.constants_nvos import ChassisLocationConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


class SSDTool:
    """Tool for SSD firmware operations."""

    @staticmethod
    def _get_ssd_pkg_info(pkg_file_name: str) -> dict:
        with allure.step('Get SSD part number from device'):
            ssd_output = OutputParsingTool.parse_json_str_to_dictionary(
                Platform().firmware.ssd.show()
            ).get_returned_value()
            ssd_part_number_full = ssd_output.get('part-number', '').strip()
            assert ssd_part_number_full and ssd_part_number_full != ChassisLocationConsts.NA, (
                "SSD part-number is not shown in 'nv show platform firmware ssd' output"
            )
            part_number = ssd_part_number_full.split()[-1]
        with open(TestToolkit.get_device().ssd_pkg_info_path, 'r', encoding='utf-8') as f:
            root = json.load(f)
        assert pkg_file_name in root, (f"SSD package {pkg_file_name!r} not found in pkg info file")
        group = root[pkg_file_name]
        sub = None
        if isinstance(group, dict) and part_number in group:
            sub = group[part_number]
        return sub

    @staticmethod
    def get_ssd_version_name(pkg_file_name: str) -> str | None:
        return (SSDTool._get_ssd_pkg_info(pkg_file_name) or {}).get("version_name")

    @staticmethod
    def ssd_downgrade_requires_reboot(pkg_file_name: str) -> bool:
        pkg_info = SSDTool._get_ssd_pkg_info(pkg_file_name)
        assert pkg_info is not None, (f"No SSD package info entry for current device part number under {pkg_file_name!r}")
        return bool(pkg_info['requires_reboot'])

    @staticmethod
    def downgrade_ssd_firmware(engines, ssd_component, pkg_file_name: str, version_name: str):
        """
        Manually downgrade SSD firmware to previous version.

        Args:
            engines: Test engines
            ssd_component: Platform SSD component
        """
        version_path = SSDTool._get_ssd_pkg_info(pkg_file_name)['version_path']
        fw_basename = os.path.basename(version_path)
        firmware_file = f"/tmp/{fw_basename}"

        with allure.step(f"Downgrade SSD firmware to {version_name}"):
            # Copy firmware file to DUT
            with allure.step(f"Copy firmware file from {version_path}"):
                engines.dut.copy_file(
                    source_file=version_path,
                    dest_file=fw_basename,
                    file_system='/tmp',
                    direction='put',
                    overwrite_file=True
                )

            _pkg_info = SSDTool._get_ssd_pkg_info(pkg_file_name)
            fw_download_cmd = _pkg_info['fw_download']
            fw_commit_cmd = _pkg_info['fw_commit']

            with allure.step("Download firmware to NVMe device"):
                engines.dut.run_cmd(fw_download_cmd)

            with allure.step("Commit firmware to NVMe device"):
                engines.dut.run_cmd(fw_commit_cmd)

            if SSDTool.ssd_downgrade_requires_reboot(pkg_file_name):
                with allure.step("Reboot to activate SSD firmware"):
                    System().action_reboot(flags='force').verify_result()

        with allure.step(f"Verify SSD firmware is at {version_name}"):
            BmcTool.verify_platform_component_version(ssd_component, version_name)

        with allure.step("Cleanup downloaded firmware file"):
            engines.dut.run_cmd(f"sudo rm -f {firmware_file}")
