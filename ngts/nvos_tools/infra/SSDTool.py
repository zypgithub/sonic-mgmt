from ngts.nvos_constants.constants_nvos import SSDConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.FWComponentsTool import FWComponentsTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import FW_COMPONENT_SSD
from ngts.tools.test_utils import allure_utils as allure


class SSDTool:
    """Tool for SSD firmware operations."""

    @staticmethod
    def _get_ssd_firmware_commands(part_number: str, firmware_file: str) -> tuple:
        """
        Get SSD firmware install commands based on SSD type.

        Args:
            part_number: SSD part number
            firmware_file: Path to firmware file

        Returns:
            tuple: (fw_download_command, fw_commit_command)
        """
        # Virtium VTPM24CEXI080-BM110006 (NVMe)
        if part_number == SSDConsts.VIRTIUM_VTPM24CEXI08_BM110006[SSDConsts.SSD_PART_NUMBER]:
            device = '/dev/nvme0'
            fw_download = f"sudo nvme fw-download -f {firmware_file} {device}"
            fw_commit = f"sudo nvme fw-commit -a 1 {device}"
            return (fw_download, fw_commit)

        # Unsupported SSD type
        raise ValueError(f"Unsupported SSD part number: {part_number}")

    @staticmethod
    def downgrade_ssd_firmware(engines, ssd_component):
        """
        Downgrade SSD firmware to previous version.

        Args:
            engines: Test engines
            ssd_component: Platform SSD component
        """
        # Get previous version info
        version_path, version_filename, version_name = (
            FWComponentsTool.get_fw_component_version_previous(FW_COMPONENT_SSD)
        )

        firmware_file = f"/tmp/{version_filename}"

        with allure.step(f"Downgrade SSD firmware to {version_name}"):
            # Copy firmware file to DUT
            with allure.step(f"Copy firmware file from {version_path}"):
                engines.dut.copy_file(
                    source_file=version_path,
                    dest_file=version_filename,
                    file_system='/tmp',
                    direction='put',
                    overwrite_file=True
                )

            # Get SSD part number
            with allure.step("Get SSD part number"):
                ssd_output = OutputParsingTool.parse_json_str_to_dictionary(
                    ssd_component.show()
                ).get_returned_value()
                ssd_part_number = ssd_output.get('part-number', '').strip()

            fw_download_cmd, fw_commit_cmd = SSDTool._get_ssd_firmware_commands(
                ssd_part_number, firmware_file
            )

            with allure.step("Download firmware to NVMe device"):
                engines.dut.run_cmd(fw_download_cmd)

            with allure.step("Commit firmware to NVMe device"):
                engines.dut.run_cmd(fw_commit_cmd)

            with allure.step("Reboot to activate SSD firmware"):
                System().action_reboot(flags='force').verify_result()

        with allure.step(f"Verify SSD firmware is at {version_name}"):
            BmcTool.verify_platform_component_version(ssd_component, version_name)

        with allure.step("Cleanup downloaded firmware file"):
            engines.dut.run_cmd(f"sudo rm -f {firmware_file}")
