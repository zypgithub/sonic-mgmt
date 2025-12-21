from typing import Callable, TypedDict, Dict, List
import pytest
import re
import logging

from ngts.nvos_tools.infra.DfCmdBuilder import DfCmdBuilder
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.LsblkCmdBuilder import LsblkCmdBuilder
from ngts.nvos_tools.infra.SmartctlCmdBuilder import SmartctlCmdBuilder
from ngts.nvos_constants.constants_nvos import PlatformConsts, SSDConsts, SystemConsts
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System

TYPE: str = 'type'
NAME: str = 'name'
SIZE_BYTES: str = 'size_bytes'
NUM_PARTITIONS: str = 'num_partitions'
PARTITIONS: str = 'partitions'

# Constants for size calculations and rounding
ROUNDING_PRECISION: int = 100  # For 2 decimal places (10^2)
SIZE_MULTIPLIERS: Dict[str, int] = {
    'M': 1024**2,  # Megabytes
    'G': 1024**3,  # Gigabytes
    'T': 1024**4   # Terabytes
}

logger = logging.getLogger(__name__)


class PartitionInfo(TypedDict):
    """Type definition for partition information."""
    NAME: str
    SSDConsts.SIZE_GB: float


class DiskDataT(TypedDict):
    """Type definition for disk data returned by fixture."""
    TYPE: SSDConsts.DiskType
    NAME: str
    SIZE_BYTES: int
    SSDConsts.SIZE_GB: float
    SSDConsts.ADVERTISED_SIZE_GB: float
    NUM_PARTITIONS: int
    PARTITIONS: List[PartitionInfo]
    SSDConsts.SSD_PART_NUMBER: str


@pytest.fixture(scope="session")
def disk_data(engines) -> DiskDataT:
    """
    Retrieve disk information from the device under test.
    Parses lsblk and smartctl output to extract disk type, size, partitions,
    and model information.
    Args:
        engines: Test engines fixture providing device access
    Returns:
        DiskDataT: Dictionary containing disk metadata including type, name,
                   size in bytes and GB, advertised size, partition count,
                   partition details, and SSD part number
    Raises:
        ValueError: If disk cannot be detected or smartctl output cannot be parsed
    """
    lsblk_cmd: str = LsblkCmdBuilder().output_columns(['NAME', 'SIZE', 'TYPE', 'MOUNTPOINT']).build()
    lsblk_output: str = engines.dut.run_cmd(lsblk_cmd)

    result: DiskDataT = {}

    match = re.search(r'^(?!loop)([\w\d]+)\s+([\d\.]+)\w+', lsblk_output, re.MULTILINE)
    if not match:
        raise ValueError("Could not detect disk from lsblk output")

    result[NAME] = match.group(1)
    result[TYPE] = SSDConsts.DiskType.NVME if SSDConsts.DiskType.NVME.value in result[NAME] else SSDConsts.DiskType.SDA
    result[SSDConsts.SIZE_GB] = float(match.group(2))

    logger.info(f"Detected disk: {result[NAME]} ({result[TYPE].value}), size from lsblk: {result[SSDConsts.SIZE_GB]}")

    result[PARTITIONS] = []
    matches = re.findall(rf'({result[NAME]}[\w\d]+)\s+([\d\.]+)\w+', lsblk_output)
    for match in matches:
        result[PARTITIONS].append({
            NAME: match[0],
            SSDConsts.SIZE_GB: float(match[1])
        })

    result[NUM_PARTITIONS] = len(result[PARTITIONS])
    logger.info(f"Total partitions found: {result[NUM_PARTITIONS]}")

    smartctl_cmd: str = SmartctlCmdBuilder().all().device(f'/dev/{result[NAME]}').build()
    smartctl_output: str = engines.dut.run_cmd(smartctl_cmd)

    advertizedsize_match, model_match = None, None
    if result[TYPE] == SSDConsts.DiskType.NVME:
        advertizedsize_match = re.search(r'Size\/Capacity:\s+([\d\,]+)\s+\[([\d\.]+) (\w+)\]', smartctl_output)
        model_match = re.search(r'Model Number:\s+(.+)', smartctl_output)
    else:
        advertizedsize_match = re.search(r'User Capacity:\s+([\d\,]+)\sbytes\s\[(\d+) (\w+)\]', smartctl_output)
        model_match = re.search(r'Device Model:\s+(.+)', smartctl_output)
    if not (advertizedsize_match and model_match):
        raise ValueError(f"Could not parse {result[TYPE].value} disk size from smartctl output")

    result[SIZE_BYTES] = int(advertizedsize_match.group(1).replace(',', '')) if ',' in advertizedsize_match.group(1) else int(advertizedsize_match.group(1))
    result[SSDConsts.ADVERTISED_SIZE_GB] = float(advertizedsize_match.group(2))
    result[SSDConsts.SSD_PART_NUMBER] = model_match.group(1)

    return result


def test_device_disk(engines, devices, disk_data: DiskDataT):
    """
    Test device disk configuration and verification against supported specifications.
    Validates that the detected disk hardware meets all platform requirements including
    part number compatibility, size specifications, and correct reporting across multiple
    system interfaces (platform firmware, platform show, and system disk commands).
    Test Steps:
        1. Verify disk part number exists in devices.dut.supported_disk_list
        2. Verify disk SIZE_GB matches expected size from supported disk list entry
        3. Verify disk ADVERTISED_SIZE_GB matches expected advertised size from supported list
        4. Verify disk part number is correctly reported in 'platform firmware show' JSON output
        5. Verify disk part number is correctly reported in 'platform firmware show ssd' JSON output
        6. Verify disk size is correctly reported in 'platform show' JSON output
        7. Verify all mounted partition sizes match between 'system disk show' and 'df -B 1' commands
    """
    with allure.step(f"Verify disk {disk_data[SSDConsts.SSD_PART_NUMBER]} is supported"):
        assert disk_data[SSDConsts.SSD_PART_NUMBER] in [disk[SSDConsts.SSD_PART_NUMBER] for disk in devices.dut.supported_disk_list], (
            f"Disk part number {disk_data[SSDConsts.SSD_PART_NUMBER]} not found in supported disk list"
        )
    with allure.step(f"Verify disk {disk_data[SSDConsts.SSD_PART_NUMBER]} size and advertised size are supported"):
        device_disk = next(
            disk for disk in devices.dut.supported_disk_list if disk[SSDConsts.SSD_PART_NUMBER] == disk_data[SSDConsts.SSD_PART_NUMBER]
        )
        assert disk_data[SSDConsts.SIZE_GB] == device_disk[SSDConsts.SIZE_GB], (
            f"Disk size {disk_data[SSDConsts.SIZE_GB]} does not match expected size {device_disk[SSDConsts.SIZE_GB]}"
        )
        assert disk_data[SSDConsts.ADVERTISED_SIZE_GB] == device_disk[SSDConsts.ADVERTISED_SIZE_GB], (
            f"Disk advertised size {disk_data[SSDConsts.ADVERTISED_SIZE_GB]} does not match "
            f"expected size {device_disk[SSDConsts.ADVERTISED_SIZE_GB]}"
        )
    with allure.step("Verify disk data is displayed correctly"):
        platform = Platform()
        with allure.step("Verify disk part number"):
            ssd_part_number_sources: Dict[str, Callable[[], str]] = {
                "platform firmware": lambda: OutputParsingTool.parse_json_str_to_dictionary(
                    platform.firmware.show()
                ).get_returned_value()[PlatformConsts.FW_SSD][SSDConsts.SSD_PART_NUMBER],
                "platform firmware ssd": lambda: OutputParsingTool.parse_json_str_to_dictionary(
                    platform.firmware.show(op_param=PlatformConsts.FW_SSD)
                ).get_returned_value()[SSDConsts.SSD_PART_NUMBER]
            }
            for source, source_func in ssd_part_number_sources.items():
                with allure.step(f"Verify disk part number from {source}"):
                    ssd_firmware_output = source_func()
                    assert ssd_firmware_output, f"SSD part number from {source} is None"
                    assert ssd_firmware_output == disk_data[SSDConsts.SSD_PART_NUMBER], (
                        f"Disk part number {ssd_firmware_output} does not match expected part number {disk_data[SSDConsts.SSD_PART_NUMBER]}"
                    )
        with allure.step("Verify disk size"):
            disk_size_output = OutputParsingTool.parse_json_str_to_dictionary(platform.show()).get_returned_value()[PlatformConsts.DISK_SIZE]
            disk_size_output = float(disk_size_output.split()[0])
            assert disk_size_output == disk_data[SSDConsts.SIZE_GB], (
                f"Disk size {disk_size_output} does not match expected size {disk_data[SSDConsts.SIZE_GB]}"
            )
        with allure.step("Verify mounts sizes"):
            system = System()
            system_disk_output = OutputParsingTool.parse_json_str_to_dictionary(system.disk.show()).get_returned_value()
            mounts_dict: Dict[str, Dict[str, str]] = system_disk_output['usage']
            df_cmd = DfCmdBuilder().block_size('1').build()
            df_output = engines.dut.run_cmd(df_cmd)
            for mount in mounts_dict:
                with allure.step(f"Verify mount {mount} size"):
                    m = re.search(rf'{mounts_dict[mount]["file-system"]}\s+(\d+)', df_output)
                    assert m, f"Mount {mount} size not found in df output"
                    output_size = float(mounts_dict[mount]["size"][:-1])
                    df_size = round(float(m.group(1)) / SIZE_MULTIPLIERS[mounts_dict[mount]["size"][-1]] * ROUNDING_PRECISION) / ROUNDING_PRECISION
                    assert df_size == output_size, (
                        f"Mount {mount} size {df_size} does not match expected size {output_size}"
                    )


def test_device_memory(devices):
    """
    Test device memory size verification.
    Test Steps:
        1. Verify memory size from platform show command
        2. Verify memory size from system show memory command
        3. Compare both outputs against expected device memory size
    """
    with allure.step("Verify memory size"):
        with allure.step("Verify memory size from platform"):
            device_expected_memory_sizes: List[float] = [round(memory_size * 10) / 10 for memory_size in devices.dut.memory_size]
            platform = Platform()
            memory_output: str = OutputParsingTool.parse_json_str_to_dictionary(platform.show()).get_returned_value()[PlatformConsts.MEMORY]
            memory_output: float = float(memory_output.split()[0])
            assert memory_output in device_expected_memory_sizes, (
                f"Memory size {memory_output} does not match expected size {device_expected_memory_sizes}"
            )
        with allure.step("Verify memory size from system"):
            system = System()
            memory_output: int = OutputParsingTool.parse_json_str_to_dictionary(system.show("memory")).get_returned_value()[SystemConsts.MEMORY_PHYSICAL_KEY]["total"]
            memory_output: float = round((float(memory_output / (1024 ** 3))) * ROUNDING_PRECISION) / ROUNDING_PRECISION
            assert memory_output in devices.dut.memory_size, (
                f"Memory size {memory_output} does not match expected size {devices.dut.memory_size}"
            )
