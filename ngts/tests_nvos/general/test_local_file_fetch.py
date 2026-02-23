from dataclasses import dataclass
from functools import partial
from pathlib import Path
import random
from typing import Callable, List, Optional
import pytest

from ngts.tools.test_utils import allure_utils as allure
from ngts.ngts_types.engines_T import EnginesT
from ngts.tools.test_utils.nvos_general_utils import get_file_hash
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.tools.test_utils.nvos_general_utils import generate_file_location_uri
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.general.config_commands.test_config_fetch import YAML_FILES_LIST, YAML_FILES_PATH
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.system.Files import Files


SYSTEM_IMAGE_FETCH = 'System Image Fetch'
SYSTEM_CONFIG_FETCH = 'System Config Fetch'
PLATFORM_FIRMWARE_FETCH = 'Platform Firmware Fetch'


@dataclass
class ComponentHandler:
    """Encapsulates component-specific handlers for fetch operations."""
    action: Callable[[str], None]  # Takes URL, performs fetch action
    verify: Callable[[List[str]], Callable]  # Takes file list, returns verification callable
    path: Path  # DUT path where files are stored
    files_obj: Files  # Files object for the component
    component: Optional[str] = None  # Firmware component name (only for PLATFORM_FIRMWARE_FETCH)


def _cleanup_tmp_file(dut_engine: LinuxSshEngine, tmp_file_path: Path):
    with allure.step("Delete tmp file"):
        dut_engine.run_cmd(f"rm -f {tmp_file_path}")


def _cleanup_fetched_files(files_obj: Files, original_files: List[str], fetched_image_files: List[str]):
    with allure.step(f"Delete all Files at {files_obj.get_resource_path()} that have been fetch during the test and verify"):
        files_obj.delete_files(fetched_image_files)
        files_obj.verify_show_files_output(expected_files=original_files, unexpected_files=fetched_image_files)


@pytest.fixture(scope='session')
def firmware_component(devices) -> str:
    """Select a random firmware component available on the device."""
    return random.choice(devices.dut.components_list)


@pytest.fixture
def test_config(request):
    """Provides test configuration including API type and fetch type."""
    return request.param


@pytest.fixture
def file_fetch_path(test_config, downgrade_version_realpath, firmware_component) -> Path:
    """
    Provides the source file path for fetch operations based on test configuration.
    """
    fetch_type = test_config['fetch_type']

    if fetch_type == SYSTEM_IMAGE_FETCH:
        return Path(downgrade_version_realpath)
    elif fetch_type == SYSTEM_CONFIG_FETCH:
        return Path(YAML_FILES_PATH) / YAML_FILES_LIST[0]
    elif fetch_type == PLATFORM_FIRMWARE_FETCH:
        return Path(BmcTool.get_fw_component_version_dict(firmware_component, "latest")['path'])
    else:
        raise ValueError(f"Unknown file fetch type: {fetch_type}")


@pytest.fixture
def component_handler(test_config, firmware_component) -> ComponentHandler:
    """
    Provides component-specific handlers for fetch actions and file operations.
    Returns a ComponentHandler object with action, verify, path, and files_obj attributes.
    """
    fetch_type = test_config['fetch_type']

    if fetch_type == SYSTEM_IMAGE_FETCH:
        return ComponentHandler(
            action=lambda url: System().image.action_fetch(url, base_url=""),
            verify=lambda files: partial(System().image.files.verify_show_files_output, expected_files=files),
            path=Path(NvosConst.PATH_TO_IMAGES),
            files_obj=System().image.files,
            component=None
        )
    elif fetch_type == SYSTEM_CONFIG_FETCH:
        return ComponentHandler(
            action=lambda url: System().config.action_fetch(url, base_url=""),
            verify=lambda files: partial(System().config.files.verify_show_files_output, expected_files=files),
            path=Path(NvosConst.PATH_TO_CONFIG_FILES_ON_DUT),
            files_obj=System().config.files,
            component=None
        )
    elif fetch_type == PLATFORM_FIRMWARE_FETCH:
        fw_platform = getattr(Platform().firmware, firmware_component)
        return ComponentHandler(
            # Use action_fetch (inherited from BaseComponent) for all firmware components
            action=lambda url: fw_platform.action_fetch(path=url, base_url=""),
            verify=lambda files: partial(fw_platform.files.verify_show_files_output, expected_files=files),
            path=Path(NvosConst.PATH_TO_FW_IMAGES) / firmware_component,
            files_obj=fw_platform.files,
            component=firmware_component
        )
    else:
        raise ValueError(f"Unknown file fetch type: {fetch_type}")


@pytest.mark.general
@pytest.mark.simx
@pytest.mark.parametrize('test_config', [
    {'test_api': random.choice(ApiType.ALL_TYPES), 'fetch_type': SYSTEM_IMAGE_FETCH},
    {'test_api': ApiType.NVUE, 'fetch_type': SYSTEM_CONFIG_FETCH},
    {'test_api': random.choice(ApiType.ALL_TYPES), 'fetch_type': PLATFORM_FIRMWARE_FETCH},
], indirect=True, ids=[SYSTEM_IMAGE_FETCH, SYSTEM_CONFIG_FETCH, PLATFORM_FIRMWARE_FETCH])
def test_local_file_fetch(engines: EnginesT, test_config, register_cleanup, file_fetch_path: Path, component_handler: ComponentHandler):
    """
    Test that verifies local file fetch functionality for system images, configuration files, and platform firmware.
    The test copies a file to the DUT's /tmp directory, fetches it using the appropriate component action,
    verifies the file appears in the expected DUT directory, and checks file integrity by comparing hashes.
    Test Flow:
    1. Copy file to DUT's /tmp directory
    2. Fetch file using the appropriate component action
    3. Verify the file appears in the expected DUT directory
    4. Check file integrity by comparing hashes
    """
    with allure.step("Prep Test"):
        TestToolkit.tested_api = test_config['test_api']
        fetched_file_name = file_fetch_path.name
        original_files: List[str] = component_handler.files_obj.get_files().keys()

    with allure.step(f"Copy file {file_fetch_path} to {NvosConst.PATH_TO_TMP_ON_DUT}"):
        original_file_hash = get_file_hash(engines.sonic_mgmt, str(file_fetch_path))
        assert original_file_hash, f"Failed to get file hash for {file_fetch_path}"
        dut_tmp_file_path = Path(NvosConst.PATH_TO_TMP_ON_DUT) / fetched_file_name
        engines.dut.copy_file(source_file=str(file_fetch_path),
                              dest_file=str(dut_tmp_file_path),
                              file_system=NvosConst.PATH_TO_TMP_ON_DUT,
                              direction='put')
        assert fetched_file_name in engines.dut.run_cmd(f'ls {dut_tmp_file_path}'), f"Failed to copy {fetched_file_name} to tmp dut"
        register_cleanup(partial(_cleanup_tmp_file, engines.dut, dut_tmp_file_path))

    with allure.step(f"Fetch local file {fetched_file_name}"):
        file_url = generate_file_location_uri(str(dut_tmp_file_path))
        component_handler.action(file_url)
        component_handler.verify([fetched_file_name])()
        register_cleanup(partial(_cleanup_fetched_files, component_handler.files_obj, original_files, [fetched_file_name]))

    with allure.step(f"Verify fetched file {fetched_file_name} from {component_handler.path} integrity"):
        assert fetched_file_name in engines.dut.run_cmd(f'ls {component_handler.path}'), f"Failed to fetch {fetched_file_name}"
        dut_file_path = component_handler.path / fetched_file_name
        dut_file_hash = get_file_hash(engines.dut, str(dut_file_path))
        assert dut_file_hash == original_file_hash, f"Fetched file {fetched_file_name} integrity is not as expected"
