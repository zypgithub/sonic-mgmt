from functools import partial
from pathlib import Path
import random
from typing import Callable, List
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

firmware_components = random.choice(['bios', 'bmc', 'cpld', 'erot', 'fpga'])


def _cleanup_tmp_file(dut_engine: LinuxSshEngine, tmp_file_path: Path):
    with allure.step("Delete tmp file"):
        dut_engine.run_cmd(f"rm -f {tmp_file_path}")


def _cleanup_fetched_files(files_obj: Files, original_files: List[str], fetched_image_files: List[str]):
    with allure.step(f"Delete all Files at {files_obj.get_resource_path()} that have been fetch during the test and verify"):
        files_obj.delete_files(fetched_image_files)
        files_obj.verify_show_files_output(expected_files=original_files, unexpected_files=fetched_image_files)


@pytest.fixture(scope='session', params=[SYSTEM_IMAGE_FETCH, SYSTEM_CONFIG_FETCH, PLATFORM_FIRMWARE_FETCH])
def file_fetch_path(request, downgrade_version_realpath) -> Path:
    """
    Unified fixture for file fetch paths that can provide different version file paths.

    This fixture unifies downgrade_version_realpath, base_version_realpath, and target_version_realpath
    fixtures to provide a single interface for file fetch operations.
    """
    if request.param == SYSTEM_IMAGE_FETCH:
        return Path(downgrade_version_realpath)
    elif request.param == SYSTEM_CONFIG_FETCH:
        return Path(YAML_FILES_PATH) / YAML_FILES_LIST[0]
    elif request.param == PLATFORM_FIRMWARE_FETCH:
        return Path(BmcTool.get_fw_component_version_dict(firmware_components, "latest")['path'])
    else:
        raise ValueError(f"Unknown file fetch type: {request.param}")


@pytest.mark.general
@pytest.mark.simx
@pytest.mark.parametrize('test_api, component_fetch_action, component_fetch_verify_action, file_fetch_path, dut_path, component_files_obj', [
    pytest.param(
        random.choice(ApiType.ALL_TYPES),
        System().image.action_fetch,
        lambda files: partial(System().image.files.verify_show_files_output, expected_files=files),
        SYSTEM_IMAGE_FETCH,
        Path(NvosConst.PATH_TO_IMAGES),
        System().image.files,
        id=SYSTEM_IMAGE_FETCH
    ),
    pytest.param(
        ApiType.NVUE,
        System().config.action_fetch,
        lambda files: partial(System().config.files.verify_show_files_output, expected_files=files),
        SYSTEM_CONFIG_FETCH,
        Path(NvosConst.PATH_TO_CONFIG_FILES_ON_DUT),
        System().config.files,
        id=SYSTEM_CONFIG_FETCH
    ),
    pytest.param(
        random.choice(ApiType.ALL_TYPES),
        getattr(Platform().firmware, firmware_components).action_fetch_firmware,
        lambda files: partial(getattr(Platform().firmware, firmware_components).files.verify_show_files_output, expected_files=files),
        PLATFORM_FIRMWARE_FETCH,
        Path(NvosConst.PATH_TO_FW_IMAGES) / Path(firmware_components),
        getattr(Platform().firmware, firmware_components).files,
        id=PLATFORM_FIRMWARE_FETCH
    )
], indirect=['file_fetch_path'])
def test_local_file_fetch(engines: EnginesT, test_api: ApiType, register_cleanup, file_fetch_path: Path,
                          component_fetch_action: Callable, component_fetch_verify_action: Callable, dut_path: Path, component_files_obj: Files):
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
        TestToolkit.tested_api = test_api
        fetched_file_name = file_fetch_path.name
        original_files: List[str] = component_files_obj.get_files().keys()
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
    with allure.step("Fetch local file {fetched_file_name}"):
        file_url = generate_file_location_uri(str(dut_tmp_file_path))
        component_fetch_action(file_url)
        component_fetch_verify_action([fetched_file_name])()
        register_cleanup(partial(_cleanup_fetched_files, component_files_obj, original_files, [fetched_file_name]))
    with allure.step(f"Verify fetched file {fetched_file_name} from {dut_path} integrity"):
        assert fetched_file_name in engines.dut.run_cmd(f'ls {dut_path}'), f"Failed to fetch {fetched_file_name}"
        dut_file_path = Path(dut_path) / fetched_file_name
        dut_file_hash = get_file_hash(engines.dut, str(dut_file_path))
        assert dut_file_hash == original_file_hash, f"Fetched file {fetched_file_name} integrity is not as expected"
