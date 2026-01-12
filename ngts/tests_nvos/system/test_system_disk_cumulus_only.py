import pytest
import logging
from ngts.nvos_constants.constants_nvos import ApiType, OutputFormat, ConfState, CumulusConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
import re
import yaml
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.StressResourcesTool import StressResourcesTool
logger = logging.getLogger(__name__)


@pytest.mark.system
@pytest.mark.disk
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_disk_info_collection_comparison_nvue_native_formats_and_invalid_options(engines, test_api):
    """
    Test Steps:
    1. Initialize System object and access disk component
    2. Test disk info collection and comparison between native and NVUE in 'full-disk' and 'usage' modes
    3. Verify system behavior with invalid disk options
    4. Test disk info collection with YAML output format and compare with native data
    """
    system = System()
    dut = engines.dut

    with allure.step("Test disk data collection and comparison"):
        for mode in [CumulusConsts.DISK_MODE_FULL_DISK, CumulusConsts.DISK_MODE_USAGE]:
            nvue_result = collect_nvue_system_disk(system_obj=system, mode=mode, output_format=OutputFormat.json)
            native_result = collect_native_system_disk(dut)
            # Compare the data
            comparison_result = compare_disk_data(native_result, nvue_result)
            assert comparison_result, "Disk data comparison failed"

    with allure.step("Test different output formats auto and yaml"):
        for output_format in [OutputFormat.auto, OutputFormat.yaml]:
            for mode in ['full-disk', 'usage']:
                nvue_result = collect_nvue_system_disk(system, mode=mode, output_format=output_format)
            native_result = collect_native_system_disk(dut)
            comparison_result = compare_disk_data(native_result, nvue_result)
            assert comparison_result, f"Disk data comparison failed in {output_format} format"

    with allure.step("Verify invalid options produce expected errors"):
        invalid_result = verify_invalid_options(system)
        assert invalid_result, "Invalid options verification failed"


@pytest.mark.system
@pytest.mark.disk
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_disk_info_collection_comparison_nvue_native_under_stress(engines, devices, test_api):
    """
    Test Steps:
    1. Initialize System object for test device
    2. Enable Debian repositories in sources.list
    3. Update package lists and install stress-ng
    4. Create large files to simulate disk load
    5. Start stress test in background
    6. Test disk info collection under load
    7. Cleanup
       - Kill stress-ng process
       - Remove large files
       - Uninstall stress-ng
       - Restore Debian repositories
    8. Verify disk data under stress conditions
    """
    system = System(force_api=test_api)
    dut = engines.dut

    with allure.step("Create large files to simulate disk load"):
        logger.info("Creating large files in /var and /tmp")
        dut.run_cmd("sudo dd if=/dev/zero of=/var/largefile bs=1M count=3024")
        dut.run_cmd("sudo dd if=/dev/zero of=/tmp/largefile bs=1M count=3024")

    with allure.step("Start stress test in background"):
        logger.info("Starting stress-ng with CPU and memory load")
        packages_to_delete = StressResourcesTool.stress_cpu_and_memory(engines, devices.dut.core_count, cpu_load=70, vm=8, vm_bytes='2.1G', timeout='100s')

    try:
        with allure.step("Test disk info collection under load"):
            for mode in [CumulusConsts.DISK_MODE_FULL_DISK, CumulusConsts.DISK_MODE_USAGE]:
                logger.info(f"Testing disk info collection in {mode} mode")
                nvue_disk = collect_nvue_system_disk(system_obj=system, mode=mode, output_format=OutputFormat.json)
                native_disk = collect_native_system_disk(dut)
                logger.debug(f"Native disk data: {native_disk}")
                comparison_result = compare_disk_data(native_disk, nvue_disk)
                assert comparison_result, f"Disk data comparison failed in {mode} mode under stress"

    finally:
        with allure.step("Cleanup: Kill stress-ng and remove large files"):
            logger.info("Killing stress-ng processes")
            dut.run_cmd("sudo killall stress-ng")
            logger.info("Removing large files")
            dut.run_cmd("sudo rm -f /var/largefile")
            dut.run_cmd("sudo rm -f /tmp/largefile")

        if packages_to_delete:
            StressResourcesTool.delete_packages(engines, packages_to_delete)


def parse_filesystem_data(data):
    '''
    Parse filesystem data from df command output
    Returns:
    '''
    with allure.step("Parse filesystem data from df command output"):
        try:
            pattern = r'(?P<filesystem>\S+)\s+(?P<size>\S+)\s+(?P<used>\S+)\s+(?P<avail>\S+)\s+(?P<used_percent>\d+%)\s+(?P<mount_point>\S+)'
            result = {'usage': {}}
            import re
            for match in re.finditer(pattern, data):
                filesystem = match.group('filesystem')
                size = match.group('size')
                used = match.group('used')
                avail = match.group('avail')
                used_percent = match.group('used_percent')
                mount_point = match.group('mount_point')

                result['usage'][mount_point] = {
                    'file-system': filesystem,
                    'size': size,
                    'used': used,
                    'available': avail,
                    'used-percent': used_percent
                }
            return result
        except Exception as e:
            allure.step(f"Failed to parse filesystem data: {str(e)}")
            raise AssertionError(f"Failed to parse filesystem data: {str(e)}")


def compare_disk_data(native_disk, nvue_disk):
    """
    Compare native usage and NVUE usage disk data for consistency.

    Args:
        native_disk: Dictionary containing native disk data
        nvue_disk: Dictionary containing NVUE disk data

    Returns:
        bool: True if disk data is consistent, False otherwise
    """
    with allure.step("Compare disk data between native and NVUE outputs"):
        try:
            logger.info("Starting disk data comparison between native and NVUE outputs")

            # Handle nested 'usage' key
            native_usage = native_disk.get('usage', native_disk)
            nvue_usage = nvue_disk.get('usage', nvue_disk)

            logger.info(f"Native usage mount points: {list(native_usage.keys())}")
            logger.info(f"NVUE usage mount points: {list(nvue_usage.keys())}")

            for mount_point, native_data in native_usage.items():
                # Check if mount point exists in nvue data
                if mount_point not in nvue_usage:
                    error_msg = f"Mount point '{mount_point}' not found in NVUE data"
                    logger.error(error_msg)
                    return False

                nvue_data = nvue_usage[mount_point]
                logger.info(f"Comparing data for mount point: {mount_point}")

                # Compare file-system values
                native_filesystem = native_data.get('file-system')
                nvue_filesystem = nvue_data.get('file-system')
                if native_filesystem != nvue_filesystem:
                    error_msg = (
                        f"Mismatch in 'file-system' for {mount_point}: "
                        f"native = {native_filesystem}, nvue = {nvue_filesystem}"
                    )
                    logger.error(error_msg)
                    return False

                # Compare size, used, available, and used-percent
                for key in ['size', 'used', 'available', 'used-percent']:
                    native_value = native_data.get(key)
                    nvue_value = nvue_data.get(key)
                    if native_value != nvue_value:
                        error_msg = (
                            f"Mismatch in '{key}' for {mount_point}: "
                            f"native = {native_value}, nvue = {nvue_value}"
                        )
                        logger.error(error_msg)
                        return False

                    logger.info(f"  {key}: {native_value} (matches)")

            logger.info("All disk data matches successfully")
            return True

        except Exception as e:
            error_msg = f"Disk data comparison failed: {str(e)}"
            logger.error(error_msg)
            return False


def collect_nvue_system_disk(system_obj, mode=CumulusConsts.DISK_MODE_FULL_DISK, output_format=OutputFormat.json):
    '''
    Collect NVUE system disk information
    Returns:
    '''
    with allure.step(f"Collect NVUE system disk information in {mode} mode"):
        try:
            if mode == CumulusConsts.DISK_MODE_FULL_DISK:
                if output_format == OutputFormat.yaml:
                    yaml_output = system_obj.disk.show(output_format=output_format)
                    yaml_dict = yaml.safe_load(yaml_output)
                    return yaml_dict
                elif output_format == OutputFormat.auto:
                    auto_output = OutputParsingTool.parse_auto_output_to_dict(system_obj.disk.show(output_format=output_format)).get_returned_value()
                    return normalize_disk_data(auto_output)
                else:
                    return OutputParsingTool.parse_json_str_to_dictionary(system_obj.disk.show(output_format=output_format)).get_returned_value()
            elif mode == CumulusConsts.DISK_MODE_USAGE:
                if output_format == OutputFormat.yaml:
                    yaml_output = system_obj.disk.show("usage", output_format=output_format)
                    yaml_dict = yaml.safe_load(yaml_output)
                    return yaml_dict
                elif output_format == OutputFormat.auto:
                    auto_output = OutputParsingTool.parse_auto_output_to_dict(system_obj.disk.show("usage", output_format=output_format)).get_returned_value()
                    return normalize_disk_data(auto_output)
                else:
                    return OutputParsingTool.parse_json_str_to_dictionary(system_obj.disk.show("usage", output_format=output_format)).get_returned_value()
        except Exception as e:
            allure.step(f"Failed to collect NVUE disk data: {str(e)}")
            raise AssertionError(f"Failed to collect NVUE disk data: {str(e)}")


def normalize_disk_data(data):
    '''
    Normalize disk data from auto output format to json format
    Returns:
    '''
    key_map = {
        "filesystem": "file-system",
        "avail": "available",
        "use%": "used-percent"
    }

    normalized = {"usage": {}}

    for mount_point, values in data.items():
        normalized["usage"][mount_point] = {}
        for k, v in values.items():
            new_key = key_map.get(k, k)  # rename only if key in key_map
            normalized["usage"][mount_point][new_key] = v

    return normalized


def collect_native_system_disk(engine, command: str = 'df -h'):
    """
    Collect disk information using native Linux commands.

    Args:
        engine: The engine object to run commands on
        command: The command to execute (default: 'df -h')

    Returns:
        dict: Parsed filesystem data, or raises exception on failure
    """
    with allure.step(f"Collect native system disk information using: {command}"):
        try:
            logger.info(f"Executing native disk command: {command}")
            result = engine.run_cmd(command)
            logger.info(f"Native disk command output received, length: {len(result)} characters")

            parsed_data = parse_filesystem_data(result)
            logger.info(f"Successfully parsed filesystem data with {len(parsed_data.get('usage', {}))} mount points")

            return parsed_data

        except Exception as e:
            error_msg = f"Failed to collect native disk data: {str(e)}"
            logger.error(error_msg)
            raise AssertionError(error_msg)


def verify_invalid_options(system_obj):
    """
    Verify that invalid options produce expected error messages.

    Args:
        system_obj: System object to use for testing invalid options
        dut_engine: Engine to use for commands (optional)

    Returns:
        bool: True if invalid options produce expected errors, False otherwise
    """
    with allure.step("Verify invalid disk options produce proper errors"):
        try:
            logger.info("Starting invalid options verification for disk commands")

            for rev in [ConfState.APPLIED, ConfState.STARTUP]:
                result = system_obj.disk.show(rev=rev, should_succeed=False)
                if rev == ConfState.APPLIED:
                    ValidationTool.verify_expected_output(result, "Error: Showing 'configuration' is not supported for this resource")
                else:
                    ValidationTool.verify_expected_output(result, "Rev must be 'operational', but got 'startup'")

            logger.info("Invalid disk options verification passed")
            return True
        except Exception as e:
            error_msg = f"Invalid disk options verification failed: {str(e)}"
            logger.error(error_msg)
            return False
