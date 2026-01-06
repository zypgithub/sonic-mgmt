"""
Debug Token Basic File Management Tests

Test Plan Sections 5.1 & 5.2: CRCS and CRDT File Management
Test Plan Sections 10.1 & 10.2: Token Persistence and Factory Reset
"""
import pytest

from ngts.nvos_constants.constants_nvos import ApiType, RebootConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.system.test_system_reboot import validate_reboot_reason_and_user
from ngts.tools.test_utils import allure_utils as allure

from .helpers import (
    CRCSTokenManager,
    CRDTTokenManager,
    DebugTokenFileHelper,
    DebugTokenConsts,
    TokenVerifier,
    cleanup_debug_tokens_function
)
from .token_signing import CRCSTokenSigner, CRDTTokenSigner


# ==================== CRCS File Management Helper ====================

def _test_crcs_file_management(engines, test_name, manager: CRCSTokenManager):
    """Test CRCS file management commands."""
    file_ext = '.xml'

    with allure.step('Generate CRCS token info file'):
        filename = f'crcs_test{file_ext}'
        manager.generate_token_info(filename, test_name)
        manager.verify_files_output(expected_files=[filename])

    with allure.step('Show CRCS token info files'):
        files = manager.get_token_info_files()
        assert filename in files, f"File {filename} not found in {files}"

    with allure.step('Rename CRCS token info file'):
        new_filename = f'crcs_renamed{file_ext}'
        manager.customer_support.files.file_name[filename].action_rename(
            new_name=new_filename
        ).verify_result()
        manager.verify_files_output(expected_files=[new_filename], unexpected_files=[filename])
        filename = new_filename

    with allure.step('Upload CRCS token info file to server'):
        upload_path = DebugTokenFileHelper.get_upload_path(engines)
        manager.customer_support.files.file_name[filename].action_upload(
            upload_path=upload_path
        ).verify_result()
        assert DebugTokenFileHelper.verify_remote_file_exists(engines, filename)
        DebugTokenFileHelper.cleanup_remote_file(engines, filename)
        manager.verify_files_output(expected_files=[filename])

    with allure.step('Delete specific CRCS token info file'):
        manager.delete_token_info(filename).verify_result()
        manager.verify_files_output(unexpected_files=[filename])

    with allure.step('Generate 2 files and delete all'):
        file1 = DebugTokenFileHelper.generate_random_filename(file_ext)
        file2 = DebugTokenFileHelper.generate_random_filename(file_ext)
        manager.generate_token_info(file1, test_name)
        manager.generate_token_info(file2, test_name)
        manager.verify_files_output(expected_files=[file1, file2])

        manager.delete_all_token_info().verify_result()
        manager.verify_files_output()


def _test_crcs_generate_multiple(test_name, manager: CRCSTokenManager):
    """Test generating multiple CRCS files."""
    file_ext = '.xml'
    filenames = []

    with allure.step('Generate 3 CRCS token info files sequentially'):
        for i in range(1, 4):
            filename = DebugTokenFileHelper.generate_random_filename(file_ext)
            filenames.append(filename)
            manager.generate_token_info(filename, test_name)
            manager.verify_files_output(expected_files=filenames)

    with allure.step('Delete all files'):
        manager.delete_all_token_info().verify_result()
        manager.verify_files_output()


# ==================== CRDT File Management Helper ====================

def _test_crdt_file_management(engines, test_name, manager: CRDTTokenManager):
    """Test CRDT file management commands."""
    file_ext = '.xml'
    debug_fw_bin = DebugTokenConsts.DEBUG_FW_FILENAME

    with allure.step('Fetch debug BIN firmware for CRDT token generation'):
        manager.fetch_debug_fw().verify_result()

    with allure.step('Generate CRDT token info file'):
        filename = f'crdt_test{file_ext}'
        manager.generate_token_info(filename, test_name, fw_signed_filename=debug_fw_bin)
        manager.verify_files_output(expected_files=[debug_fw_bin, filename])

    with allure.step('Show CRDT token info files'):
        files = manager.get_token_info_files()
        assert filename in files, f"File {filename} not found in {files}"

    with allure.step('Rename CRDT token info file'):
        new_filename = f'crdt_renamed{file_ext}'
        manager.debug_image.files.file_name[filename].action_rename(
            new_name=new_filename
        ).verify_result()
        manager.verify_files_output(expected_files=[debug_fw_bin, new_filename], unexpected_files=[filename])
        filename = new_filename

    with allure.step('Upload CRDT token info file to server'):
        upload_path = DebugTokenFileHelper.get_upload_path(engines)
        manager.debug_image.files.file_name[filename].action_upload(
            upload_path=upload_path
        ).verify_result()
        assert DebugTokenFileHelper.verify_remote_file_exists(engines, filename)
        DebugTokenFileHelper.cleanup_remote_file(engines, filename)
        manager.verify_files_output(expected_files=[debug_fw_bin, filename])

    with allure.step('Delete specific CRDT token info file'):
        manager.delete_token_info(filename).verify_result()
        manager.verify_files_output(expected_files=[debug_fw_bin], unexpected_files=[filename])

    with allure.step('Generate 2 files and delete all'):
        file1 = DebugTokenFileHelper.generate_random_filename(file_ext)
        file2 = DebugTokenFileHelper.generate_random_filename(file_ext)
        manager.generate_token_info(file1, test_name, fw_signed_filename=debug_fw_bin)
        manager.generate_token_info(file2, test_name, fw_signed_filename=debug_fw_bin)
        manager.verify_files_output(expected_files=[debug_fw_bin, file1, file2])

        manager.delete_all_token_info().verify_result()
        # delete_all removes all files including the debug firmware binary
        manager.verify_files_output()


def _test_crdt_generate_multiple(test_name, manager: CRDTTokenManager):
    """Test generating multiple CRDT files."""
    file_ext = '.xml'
    debug_fw_bin = DebugTokenConsts.DEBUG_FW_FILENAME
    filenames = []

    with allure.step('Fetch debug BIN firmware for CRDT token generation'):
        manager.fetch_debug_fw().verify_result()

    with allure.step('Generate 3 CRDT token info files sequentially'):
        for i in range(1, 4):
            filename = DebugTokenFileHelper.generate_random_filename(file_ext)
            filenames.append(filename)
            manager.generate_token_info(filename, test_name, fw_signed_filename=debug_fw_bin)
            manager.verify_files_output(expected_files=[debug_fw_bin] + filenames)

    with allure.step('Delete all files'):
        manager.delete_all_token_info().verify_result()
        manager.verify_files_output()


# ==================== CRCS Tests ====================

@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crcs
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crcs_file_management_commands(engines, test_name, test_api, cleanup_debug_tokens_function):
    """
    Test Plan Section 5.1: Test CRCS File Management Commands

    Comprehensive test of all CRCS file operations:
    1. Generate token info file
    2. Show files
    3. Rename file
    4. Upload file to server
    5. Delete specific file
    6. Generate multiple files and delete all
    """
    TestToolkit.tested_api = test_api
    manager = CRCSTokenManager()
    _test_crcs_file_management(engines, test_name, manager)


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crcs
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crcs_generate_multiple_files(engines, test_name, test_api, cleanup_debug_tokens_function):
    """
    Test Plan Section 8.1: Test generating multiple CRCS files.
    """
    TestToolkit.tested_api = test_api
    manager = CRCSTokenManager()
    _test_crcs_generate_multiple(test_name, manager)


# ==================== CRDT Tests ====================

@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crdt
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crdt_file_management_commands(engines, test_name, test_api, cleanup_debug_tokens_function):
    """
    Test Plan Section 5.2: Test CRDT File Management Commands

    Comprehensive test of all CRDT file operations:
    1. Fetch debug firmware
    2. Generate token info file from debug FW
    3. Show files
    4. Rename file
    5. Upload file to server
    6. Delete specific file
    7. Generate multiple files and delete all
    """
    TestToolkit.tested_api = test_api
    manager = CRDTTokenManager()
    _test_crdt_file_management(engines, test_name, manager)


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crdt
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crdt_generate_multiple_files(engines, test_name, test_api, cleanup_debug_tokens_function):
    """
    Test Plan Section 8.2: Test generating multiple CRDT files.
    """
    TestToolkit.tested_api = test_api
    manager = CRDTTokenManager()
    _test_crdt_generate_multiple(test_name, manager)


# ==================== Error Flow Tests ====================

def _test_error_flows(test_name, manager):
    """
    Test common error scenarios for both CRCS and CRDT tokens.

    Args:
        test_name: Test name for tracking
        manager: Token manager (CRCSTokenManager or CRDTTokenManager)
    """
    token_type = manager.TOKEN_TYPE

    with allure.step(f"Test {token_type} error flows"):

        with allure.independent_step("Generate with non-xml extension - expect error"):
            invalid_ext_filename = DebugTokenFileHelper.generate_random_filename(DebugTokenConsts.BIN_EXTENSION)
            manager.generate_token_info(invalid_ext_filename, test_name).verify_result(
                False, DebugTokenConsts.INVALID_EXTENSION_ERROR
            )

            files = manager.get_token_info_files()
            assert invalid_ext_filename not in files, "Invalid extension filename should not create file"

        with allure.independent_step("Delete non-existent file - expect error"):
            nonexistent_file = f'{DebugTokenConsts.NONEXISTENT_FILE}{DebugTokenConsts.XML_EXTENSION}'
            manager.info.files.file_name[nonexistent_file].action_delete().verify_result(
                False, DebugTokenConsts.FILE_NOT_FOUND_ERROR
            )

        with allure.independent_step("Rename collision - expect error"):
            file1 = DebugTokenFileHelper.generate_random_filename(DebugTokenConsts.XML_EXTENSION)
            file2 = DebugTokenFileHelper.generate_random_filename(DebugTokenConsts.XML_EXTENSION)

            manager.generate_token_info(file1, test_name)
            manager.generate_token_info(file2, test_name)

            manager.info.files.file_name[file1].action_rename(
                new_name=file2,
                rewrite_file_name=False
            ).verify_result(False, DebugTokenConsts.FILE_ALREADY_EXISTS_ERROR)

            # Cleanup
            manager.info.files.file_name[file1].action_delete()
            manager.info.files.file_name[file2].action_delete()

        with allure.independent_step("Install non-existent token - expect file not found"):
            manager.install_token(DebugTokenConsts.NONEXISTENT_TOKEN).verify_result(
                False, DebugTokenConsts.FILE_NOT_FOUND_ERROR
            )

        with allure.independent_step("Uninstall when no token enabled - expect success with message"):
            manager.uninstall_token().verify_result(
                True, DebugTokenConsts.NO_ACTIVE_TOKEN_ERROR
            )


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crcs
@pytest.mark.error_flow
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crcs_error_flows(engines, test_name, test_api, cleanup_debug_tokens_function):
    """
    Test Plan Section 7.1: CRCS (Customer Support Token) error handling.
    """
    TestToolkit.tested_api = test_api
    manager = CRCSTokenManager()
    _test_error_flows(test_name, manager)


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crdt
@pytest.mark.error_flow
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crdt_error_flows(engines, test_name, test_api, cleanup_debug_tokens_function):
    """
    Test Plan Section 7.2: CRDT (Debug Image Token) error handling.
    """
    TestToolkit.tested_api = test_api
    manager = CRDTTokenManager()

    with allure.step("Setup: Fetch debug FW for CRDT token generation"):
        manager.fetch_debug_fw().verify_result()

    _test_error_flows(test_name, manager)
