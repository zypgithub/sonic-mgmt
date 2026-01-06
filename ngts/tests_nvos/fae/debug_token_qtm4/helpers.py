"""
Helper functions and fixtures for Debug Token tests.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum

import pytest

from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import PlatformConsts

from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


# ====================
# Data Classes
# ====================

@dataclass
class TokenStatus:
    """Represents the status of a debug token."""
    is_enabled: bool
    asic_statuses: Dict[str, str]  # asic_id -> status (enabled/disabled)

    @property
    def all_asics_enabled(self) -> bool:
        """Check if all ASICs have enabled tokens."""
        return all(status == DebugTokenConsts.State.ENABLED.value
                   for status in self.asic_statuses.values())


# ====================
# Abstract Base Classes (Interface Segregation)
# ====================

class ITokenFileManager(ABC):
    """Interface for token file management operations."""

    @abstractmethod
    def generate_token_info(self, filename: str, test_name: str = '') -> ResultObj:
        """Generate a token info file."""
        pass

    @abstractmethod
    def delete_token_info(self, filename: str) -> ResultObj:
        """Delete a specific token info file."""
        pass

    @abstractmethod
    def delete_all_token_info(self) -> ResultObj:
        """Delete all token info files."""
        pass

    @abstractmethod
    def get_token_info_files(self) -> List[str]:
        """Get list of token info files."""
        pass


class ITokenLifecycle(ABC):
    """Interface for token lifecycle operations (token status queries)."""

    @abstractmethod
    def get_token_status(self) -> TokenStatus:
        """Get current token status."""
        pass


# ====================
# Concrete Implementations
# ====================

class CRCSTokenManager(ITokenFileManager, ITokenLifecycle):
    """
    Manages CRCS (Customer Support Token) operations.
    Follows Single Responsibility Principle.
    """
    TOKEN_TYPE = 'CRCS'

    def __init__(self, fae: Optional[Fae] = None):
        """
        Initialize CRCS token manager.

        Args:
            fae: Fae object. If None, creates a new one.
        """
        self.fae = fae or Fae(None)
        self.customer_support = self.fae.platform.debug.info.customer_support
        self.token = self.fae.platform.debug.token.customer_support

    @property
    def info(self):
        """Get the info component (customer_support for CRCS)."""
        return self.customer_support

    def generate_token_info(self, filename: str, test_name: str = '') -> ResultObj:
        """Generate CRCS token info file."""
        with allure.step(f'Generate CRCS token info: {filename}'):
            return self.customer_support.action_generate(name=filename, test_name=test_name)

    def delete_token_info(self, filename: str) -> ResultObj:
        """Delete specific CRCS token info file."""
        with allure.step(f'Delete CRCS token info: {filename}'):
            return self.customer_support.files.file_name[filename].action_delete()

    def delete_all_token_info(self) -> ResultObj:
        """Delete all CRCS token info files."""
        with allure.step('Delete all CRCS token info files'):
            return self.customer_support.action_delete_all()

    def get_token_info_files(self) -> List[str]:
        """Get list of CRCS token info files."""
        with allure.step('Get CRCS token info files'):
            files = self.customer_support.files.get_files()
            return list(files.keys()) if files else []

    def get_token_status(self) -> TokenStatus:
        """Get CRCS token status for all ASICs."""
        with allure.step('Get CRCS token status'):
            output = self.token.asic.show()
            parsed = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()

            # Parse ASIC statuses from output like:
            # {"ASIC1": {"token-status": "enabled"}, "ASIC2": {"token-status": "enabled"}, ...}
            asic_statuses = {}
            for asic_name, asic_data in parsed.items():
                if isinstance(asic_data, dict) and 'token-status' in asic_data:
                    asic_statuses[asic_name] = asic_data['token-status']

            # Token is enabled if all ASICs have enabled status
            is_enabled = bool(asic_statuses) and all(
                status == DebugTokenConsts.State.ENABLED.value
                for status in asic_statuses.values()
            )

            return TokenStatus(is_enabled=is_enabled, asic_statuses=asic_statuses)

    def verify_files_output(self, expected_files: List[str] = None,
                            unexpected_files: List[str] = None):
        """Verify token info files match expectations."""
        expected_files = expected_files or []
        unexpected_files = unexpected_files or []
        self.customer_support.files.verify_show_files_output(
            expected_files=expected_files,
            unexpected_files=unexpected_files
        )

    def install_token(self, signed_token_name: str, force: bool = False) -> ResultObj:
        """Install a signed CRCS token."""
        with allure.step(f'Install CRCS token: {signed_token_name}'):
            return self.token.files.file_name[signed_token_name].action_file_install(force=force)

    def uninstall_token(self) -> ResultObj:
        """Uninstall the currently active CRCS token."""
        with allure.step('Uninstall CRCS token'):
            return self.token.action_uninstall()


class CRDTTokenManager(ITokenFileManager, ITokenLifecycle):
    """
    Manages CRDT (Debug Image Token) operations.
    Follows Single Responsibility Principle.
    """
    TOKEN_TYPE = 'CRDT'

    def __init__(self, fae: Optional[Fae] = None):
        """
        Initialize CRDT token manager.

        Args:
            fae: Fae object. If None, creates a new one.
        """
        self.fae = fae or Fae(None)
        self.debug_image = self.fae.platform.debug.info.debug_image
        self.token = self.fae.platform.debug.token.debug_image
        self._debug_fw_filename: Optional[str] = None

    @property
    def info(self):
        """Get the info component (debug_image for CRDT)."""
        return self.debug_image

    def fetch_debug_fw(self, debug_fw_filename: Optional[str] = None,
                       bin_path: Optional[str] = None) -> ResultObj:
        """
        Fetch debug firmware file required for CRDT token generation.

        Args:
            debug_fw_filename: Name of the debug FW file (defaults from JSON or fallback)
            bin_path: Full path to BIN file (defaults from JSON or fallback)

        Returns:
            ResultObj indicating success/failure
        """
        # Get firmware info from JSON or use fallback
        fw_info = DebugTokenConsts.get_debug_asic_fw_info()
        debug_fw_filename = debug_fw_filename or fw_info['bin_filename']
        fetch_url = bin_path or fw_info['bin_path']

        with allure.step(f'Fetch debug firmware: {debug_fw_filename}'):
            result = self.debug_image.action_fetch(fetch_url)
            if result:
                self._debug_fw_filename = debug_fw_filename
            return result

    def fetch_and_install_mfa_fw(self, nv_command, engines,
                                 mfa_filename: Optional[str] = None,
                                 mfa_path: Optional[str] = None) -> ResultObj:
        """
        Fetch and install MFA firmware for CRDT token testing.

        Args:
            nv_command: NV command object for platform firmware operations
            engines: Engines dictionary
            mfa_filename: Name of the MFA file (defaults from JSON or fallback)
            mfa_path: Full path to MFA file (defaults from JSON or fallback)

        Returns:
            ResultObj indicating success/failure
        """
        # Get firmware info from JSON or use fallback
        fw_info = DebugTokenConsts.get_debug_asic_fw_info()
        mfa_filename = mfa_filename or fw_info['mfa_filename']
        fetch_url = mfa_path or fw_info['mfa_path']

        with allure.step(f'Fetch and install MFA firmware: {mfa_filename}'):
            nv_command.platform.firmware.asic.set(
                PlatformConsts.FW_SOURCE,
                PlatformConsts.FW_SOURCE_CUSTOM,
                apply=True
            )
            NvueGeneralCli.save_config(engines.dut)

            nv_command.platform.firmware.asic.action_fetch(fetch_url).verify_result()
            return nv_command.platform.firmware.asic.files.file_name[mfa_filename].action_file_install_with_reboot(force=True)

    def get_debug_fw_filename(self) -> Optional[str]:
        """Get the currently fetched debug FW filename."""
        return self._debug_fw_filename

    def generate_token_info(self, filename: str, test_name: str = '',
                            fw_signed_filename: str = None) -> ResultObj:
        """
        Generate CRDT token info file from debug firmware.

        Args:
            filename: Name for the generated token info file (.xml)
            test_name: Test name for tracking
            fw_signed_filename: Debug firmware file (defaults to fetched debug FW)
        """
        fw_signed_filename = fw_signed_filename or self._debug_fw_filename
        with allure.step(f'Generate CRDT token info: {filename}'):
            # Command: nv action generate fae platform debug info debug-image files <fw_file> new-name <name>
            return self.debug_image.files.file_name[fw_signed_filename].action_generate(new_name=filename)

    def delete_token_info(self, filename: str) -> ResultObj:
        """Delete specific CRDT token info file."""
        with allure.step(f'Delete CRDT token info: {filename}'):
            return self.debug_image.files.file_name[filename].action_delete()

    def delete_all_token_info(self) -> ResultObj:
        """Delete all CRDT token info files."""
        with allure.step('Delete all CRDT token info files'):
            return self.debug_image.action_delete_all()

    def get_token_info_files(self) -> List[str]:
        """Get list of CRDT token info files."""
        with allure.step('Get CRDT token info files'):
            files = self.debug_image.files.get_files()
            return list(files.keys()) if files else []

    def get_token_status(self) -> TokenStatus:
        """Get CRDT token status for all ASICs."""
        with allure.step('Get CRDT token status'):
            output = self.token.asic.show()
            parsed = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()

            # Parse ASIC statuses from output like:
            # {"ASIC1": {"token-status": "enabled"}, "ASIC2": {"token-status": "enabled"}, ...}
            asic_statuses = {}
            for asic_name, asic_data in parsed.items():
                if isinstance(asic_data, dict) and 'token-status' in asic_data:
                    asic_statuses[asic_name] = asic_data['token-status']

            # Token is enabled if all ASICs have enabled status
            is_enabled = bool(asic_statuses) and all(
                status == DebugTokenConsts.State.ENABLED.value
                for status in asic_statuses.values()
            )

            return TokenStatus(is_enabled=is_enabled, asic_statuses=asic_statuses)

    def verify_files_output(self, expected_files: List[str] = None,
                            unexpected_files: List[str] = None):
        """Verify token info files match expectations."""
        expected_files = expected_files or []
        unexpected_files = unexpected_files or []
        self.debug_image.files.verify_show_files_output(
            expected_files=expected_files,
            unexpected_files=unexpected_files
        )

    def install_token(self, signed_token_name: str, force: bool = False) -> ResultObj:
        """Install a signed CRDT token."""
        with allure.step(f'Install CRDT token: {signed_token_name}'):
            return self.token.files.file_name[signed_token_name].action_file_install(force=force)

    def uninstall_token(self) -> ResultObj:
        """Uninstall the currently active CRDT token."""
        with allure.step('Uninstall CRDT token'):
            return self.token.action_uninstall()


# ====================
# File Operation Helpers
# ====================

class DebugTokenFileHelper:
    """
    Helper for common file operations on debug tokens.
    Follows Single Responsibility Principle.
    """

    @staticmethod
    def generate_random_filename(extension: str = '.xml') -> str:
        """
        Generate a random filename with the given extension.

        Args:
            extension: File extension (e.g., '.xml', '.bin')

        Returns:
            Random filename
        """
        return RandomizationTool.get_random_string(8) + extension

    @staticmethod
    def get_upload_path(engines, path: str = '/tmp/') -> str:
        """
        Generate SCP upload path for file server.

        Args:
            engines: Engines dictionary
            path: Remote path

        Returns:
            Full SCP URL
        """
        player = engines['sonic_mgmt']
        return ImageConsts.SCP_PATH_SERVER.format(
            username=player.username,
            password=player.password,
            ip=player.ip,
            path=path
        )

    @staticmethod
    def cleanup_remote_file(engines, filename: str, remote_path: str = '/tmp/'):
        """
        Clean up a file from the remote server.

        Args:
            engines: Engines dictionary
            filename: Name of file to remove
            remote_path: Remote path where file is located
        """
        with allure.step(f'Cleanup remote file: {filename}'):
            player = engines['sonic_mgmt']
            player.run_cmd(f'rm -f {remote_path}{filename}')

    @staticmethod
    def verify_remote_file_exists(engines, filename: str,
                                  remote_path: str = '/tmp/') -> bool:
        """
        Verify a file exists on the remote server.

        Args:
            engines: Engines dictionary
            filename: Name of file to check
            remote_path: Remote path to check

        Returns:
            True if file exists
        """
        with allure.step(f'Verify remote file exists: {filename}'):
            player = engines['sonic_mgmt']
            output = player.run_cmd(f'ls {remote_path} | grep {filename}')
            return bool(output)

    @staticmethod
    def get_asic_firmware_version(nv_command) -> str:
        """
        Get the actual firmware version from the first ASIC.

        Args:
            nv_command: NV command object

        Returns:
            Firmware version string
        """
        show_output = OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.firmware.show()
        ).get_returned_value()
        asic_dictionary = {k: v for k, v in show_output.items()
                           if PlatformConsts.FW_ASIC in k and 'EROT' not in k}
        assert asic_dictionary and len(asic_dictionary.keys()) > 0, "ASIC list is empty"
        first_asic_name = list(asic_dictionary.keys())[0]
        return asic_dictionary[first_asic_name]["actual-firmware"]

    @staticmethod
    def verify_firmware_version(nv_command, expected_version: str, step_description: str = ""):
        """
        Verify the firmware version matches the expected version.

        Args:
            nv_command: NV command object
            expected_version: Expected firmware version string
            step_description: Description for the verification step
        """
        with allure.step(f'Verify firmware version{": " + step_description if step_description else ""}'):
            actual_version = DebugTokenFileHelper.get_asic_firmware_version(nv_command)
            logger.info(f"Expected firmware: {expected_version}, Actual firmware: {actual_version}")
            assert actual_version == expected_version, \
                f"Firmware version mismatch. Expected: {expected_version}, Got: {actual_version}"

# ====================
# Test Fixtures
# ====================


@pytest.fixture(scope='session', autouse=True)
def cleanup_debug_tokens_session():
    """Clean up all debug token files at session start."""
    with allure.step('Session setup: Clean up existing debug token files'):
        fae = Fae(None)

        # Clean up CRDT files
        try:
            debug_image = fae.platform.debug.info.debug_image
            files = debug_image.files.get_files()
            if files:
                debug_image.files.delete_files(files_to_delete=files).verify_result()
        except Exception as e:
            logger.warning(f"Failed to clean up CRDT files: {e}")

        # Clean up CRCS files
        try:
            customer_support = fae.platform.debug.info.customer_support
            files = customer_support.files.get_files()
            if files:
                customer_support.files.delete_files(files_to_delete=files).verify_result()
        except Exception as e:
            logger.warning(f"Failed to clean up CRCS files: {e}")


@pytest.fixture(scope='function')
def cleanup_debug_tokens_function():
    """Clean up debug token files after each test function."""
    yield

    with allure.step('Function teardown: Clean up debug token files'):
        fae = Fae(None)

        # Clean up CRDT files
        try:
            debug_image = fae.platform.debug.info.debug_image
            files = debug_image.files.get_files()
            if files:
                debug_image.files.delete_files(files_to_delete=files)
        except Exception as e:
            logger.warning(f"Failed to clean up CRDT files: {e}")

        # Clean up CRCS files
        try:
            customer_support = fae.platform.debug.info.customer_support
            files = customer_support.files.get_files()
            if files:
                customer_support.files.delete_files(files_to_delete=files)
        except Exception as e:
            logger.warning(f"Failed to clean up CRCS files: {e}")


# ====================
# Verification Helpers
# ====================

class TokenVerifier:
    """
    Verification utilities for debug tokens.
    Follows Single Responsibility Principle.
    """

    @staticmethod
    def verify_token_enabled(manager: ITokenLifecycle, expected_enabled: bool = True):
        """
        Verify token is in expected enabled/disabled state.

        Args:
            manager: Token manager implementing ITokenLifecycle
            expected_enabled: Expected state (True=enabled, False=disabled)
        """
        with allure.step(f'Verify token is {"enabled" if expected_enabled else "disabled"}'):
            status = manager.get_token_status()

            if expected_enabled:
                assert status.is_enabled, "Token should be enabled but is disabled"
                assert status.all_asics_enabled, \
                    f"Not all ASICs enabled: {status.asic_statuses}"
            else:
                assert not status.is_enabled, "Token should be disabled but is enabled"


# ====================
# Constants
# ====================

class DebugTokenConsts:
    """Constants for debug token tests."""

    # Token state enum (like NtpConsts.State)
    class State(Enum):
        """Token state enum."""
        ENABLED = "enabled"
        DISABLED = "disabled"

    # File extensions
    XML_EXTENSION = '.xml'
    BIN_EXTENSION = '.bin'

    # Component name for BmcTool lookup
    DEBUG_ASIC_COMPONENT = "debug_asic"

    # Fallback debug firmware values (used if JSON lookup fails)
    DEBUG_FW_FILENAME = "debug_fw_41_2018_0220.bin"
    DEBUG_MFA_FILENAME = "debug_fw_41_2018_0220.mfa"
    DEBUG_FW_SOURCE_PATH = "/auto/sw_system_project/NVOS_INFRA/verification_files/debug_token/"

    # Token filenames for tests
    CRCS_TOKEN_INFO = "crcs_token_info.xml"
    CRDT_TOKEN_INFO = "crdt_token_info.xml"

    # Error messages
    INVALID_FILENAME_ERROR = "Invalid filename"
    INVALID_EXTENSION_ERROR = "not in an xml format"
    FILE_NOT_FOUND_ERROR = "File not found"
    FILE_ALREADY_EXISTS_ERROR = "already exists"
    CONNECTION_FAILED_ERROR = "Connection failed"
    NO_ACTIVE_TOKEN_ERROR = "no token installed"

    # Test values for error scenarios
    INVALID_FILENAME = 'bad<name>.abc'
    NONEXISTENT_FILE = 'nonexistent'
    NONEXISTENT_TOKEN = 'nonexistent_token.bin'
    INVALID_URL = 'scp://nonexistent_host_12345/path/'
    INVALID_TOKEN_URL = 'scp://nonexistent_host_12345/token.bin'

    @classmethod
    def get_debug_asic_fw_info(cls):
        """
        Get debug ASIC firmware info from platform components JSON.

        Returns:
            Dict with keys: bin_path, bin_filename, mfa_path, mfa_filename, version_name
            Falls back to default constants if JSON lookup fails.
        """
        try:
            component_info = BmcTool.get_fw_component_version_dict(cls.DEBUG_ASIC_COMPONENT, "latest")
            return {
                'bin_path': component_info['bin_path'],
                'bin_filename': component_info['bin_filename'],
                'mfa_path': component_info['mfa_path'],
                'mfa_filename': component_info['mfa_filename'],
                'version_name': component_info['version_name']
            }
        except Exception as e:
            logger.warning(f"Failed to get debug ASIC info from JSON, using fallback values: {e}")
            return {
                'bin_path': f"{cls.DEBUG_FW_SOURCE_PATH}{cls.DEBUG_FW_FILENAME}",
                'bin_filename': cls.DEBUG_FW_FILENAME,
                'mfa_path': f"{cls.DEBUG_FW_SOURCE_PATH}{cls.DEBUG_MFA_FILENAME}",
                'mfa_filename': cls.DEBUG_MFA_FILENAME,
                'version_name': None
            }
