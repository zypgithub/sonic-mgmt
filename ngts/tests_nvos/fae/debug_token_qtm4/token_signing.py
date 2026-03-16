"""
Token Signing Utilities

OOP-based token signing using Template Method pattern.
Signing is performed directly on the switch (DUT) using mlxconfig.
Flow: Generate → Copy to /tmp → Sign in /tmp → Copy to token directory
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Tuple

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.SshCmdBuilder import ScpPassCmdBuilder
from ngts.tests_nvos.fae.debug_token_qtm4.consts import (
    TokenSigningPaths,
    TokenSigningCommands,
)
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


class TokenSigner(ABC):
    """
    Abstract base class for token signing operations.

    Subclasses only define token-specific paths and prefixes.
    Signing is performed directly on the switch (DUT) using mlxconfig.

    Flow:
    1. Token info file is already generated in info directory
    2. Copy to /tmp for signing
    3. Sign using mlxconfig on switch
    4. Copy signed token to token directory for installation
    """

    def __init__(self, engines):
        """
        Initialize token signer.

        Args:
            engines: Test engines dict with 'dut' and 'sonic_mgmt' (player)
        """
        self.dut_engine = engines.dut
        self.player_engine = engines['sonic_mgmt']

        # Create dedicated LinuxSshEngine for player (for copying private key)
        self.scp_engine = LinuxSshEngine(
            self.player_engine.ip,
            self.player_engine.username,
            self.player_engine.password
        )

        self._ensure_private_key_on_switch()

    def _ensure_private_key_on_switch(self):
        """Copy private key from player to switch (DUT) using SCP."""
        with allure.step('Ensure private key is on switch'):
            # Check if key already exists on switch
            check_cmd = TokenSigningCommands.CHECK_FILE_EXISTS.format(path=TokenSigningPaths.DK_PRIVATE_KEY_PATH)
            result = self.dut_engine.run_cmd(check_cmd)

            if "missing" in result:
                # Copy from player to switch using ScpPassCmdBuilder
                sshpass_cmd = ScpPassCmdBuilder(
                    user=self.dut_engine.username,
                    password=self.dut_engine.password,
                    host=self.dut_engine.ip,
                    src=TokenSigningPaths.DK_PRIVATE_KEY_SOURCE,
                    dest=TokenSigningPaths.DK_PRIVATE_KEY_PATH
                ).NoStrictHostKeyChecking().NoUserKnownHostsFile().build()

                self.scp_engine.run_cmd(sshpass_cmd)
                logger.info(f'Copied private key from player to switch at {TokenSigningPaths.DK_PRIVATE_KEY_PATH}')
            else:
                logger.info(f'Private key already exists on switch at {TokenSigningPaths.DK_PRIVATE_KEY_PATH}')

    @abstractmethod
    def get_token_info_dir(self) -> str:
        """Get token info directory path on DUT."""
        pass

    @abstractmethod
    def get_token_dir(self) -> str:
        """Get token directory path on DUT (where signed tokens go)."""
        pass

    @abstractmethod
    def get_file_prefix(self) -> str:
        """Get file prefix for temp files (e.g., 'crcs', 'crdt')."""
        pass

    @abstractmethod
    def get_token_type_name(self) -> str:
        """Get token type name for logging (e.g., 'CRCS', 'CRDT')."""
        pass

    def sign_token(self, token_info_xml: str, output_bin: str) -> str:
        """
        Sign token using mlxconfig on switch.

        Args:
            token_info_xml: Path to token info XML on switch
            output_bin: Output path for signed binary on switch

        Returns:
            Path to signed token binary
        """
        cmd = TokenSigningCommands.MLXCONFIG_SIGN_CMD.format(
            private_key_path=TokenSigningPaths.DK_PRIVATE_KEY_PATH,
            uuid_hex=TokenSigningPaths.UUID_HEX,
            input_xml=token_info_xml,
            output_bin=output_bin
        )
        return self._execute_signing(cmd, token_info_xml, output_bin)

    def sign_on_switch(self, token_info_filename: str) -> Tuple[str, str]:
        """
        Template method: Complete token signing flow on switch.

        Flow:
        1. Copy token info from info directory to /tmp
        2. Sign in /tmp using mlxconfig
        3. Copy signed token to token directory

        Args:
            token_info_filename: Token info filename (in info directory on DUT)

        Returns:
            Tuple of (signed_token_path_in_token_dir, signed_token_filename)
        """
        prefix = self.get_file_prefix()
        token_info_dir = self.get_token_info_dir()
        token_dir = self.get_token_dir()

        # Build simple paths on switch (no test_name to avoid special characters)
        source_xml = f"{token_info_dir}/{token_info_filename}"
        tmp_xml = f"/tmp/{prefix}_token_info.xml"
        tmp_signed_bin = f"/tmp/{prefix}_signed_token.bin"
        signed_token_name = os.path.basename(tmp_signed_bin)
        final_token_path = f"{token_dir}/{signed_token_name}"

        with allure.step(f'Sign {self.get_token_type_name()} token on switch'):
            # Step 1: Copy token info from info directory to /tmp
            self._copy_to_tmp(source_xml, tmp_xml)

            # Step 2: Sign in /tmp
            self.sign_token(tmp_xml, tmp_signed_bin)

            # Step 3: Copy signed token to token directory
            self._copy_to_token_dir(tmp_signed_bin, final_token_path)

        return final_token_path, signed_token_name

    def _copy_to_tmp(self, source: str, dest: str):
        """Copy file to /tmp directory on switch."""
        with allure.step(f'Copy {os.path.basename(source)} to /tmp'):
            self.dut_engine.run_cmd(TokenSigningCommands.COPY_FILE.format(src=source, dest=dest))
            ls_output = self.dut_engine.run_cmd(TokenSigningCommands.LS_FILE.format(path=dest))
            logger.info(f'Copied to /tmp: {ls_output}')

    def _copy_to_token_dir(self, source: str, dest: str):
        """Copy signed token to token directory."""
        with allure.step(f'Copy signed token to token directory'):
            token_dir = os.path.dirname(dest)
            self.dut_engine.run_cmd(TokenSigningCommands.MKDIR.format(path=token_dir))
            self.dut_engine.run_cmd(TokenSigningCommands.COPY_FILE.format(src=source, dest=dest))
            ls_output = self.dut_engine.run_cmd(TokenSigningCommands.LS_FILE.format(path=dest))
            logger.info(f'Copied signed token: {ls_output}')

    def _execute_signing(self, cmd: str, input_file: str, output_file: str) -> str:
        """Execute signing command on switch and verify result."""
        with allure.step(f'Sign {self.get_token_type_name()} token: {os.path.basename(input_file)} -> {os.path.basename(output_file)}'):

            # Run mlxconfig on switch (requires sudo)
            output = self.dut_engine.run_cmd(f'sudo {cmd}')
            logger.info(f'Signing output: {output}')

            # Verify signing succeeded
            assert "Unknown parameter" not in output, f"Token signing failed: {output}"

            # Verify signed token file created
            ls_output = self.dut_engine.run_cmd(TokenSigningCommands.LS_FILE.format(path=output_file))
            assert "cannot access" not in ls_output.lower(), f"Signed token file not created: {output_file}"

        return output_file


class CRCSTokenSigner(TokenSigner):
    """CRCS (Customer Support Token) signer."""

    def get_token_info_dir(self) -> str:
        return TokenSigningPaths.CRCS_INFO_DIR

    def get_token_dir(self) -> str:
        return TokenSigningPaths.CRCS_TOKEN_DIR

    def get_file_prefix(self) -> str:
        return "crcs"

    def get_token_type_name(self) -> str:
        return "CRCS"


class CRDTTokenSigner(TokenSigner):
    """CRDT (Debug Image Token) signer."""

    def get_token_info_dir(self) -> str:
        return TokenSigningPaths.CRDT_INFO_DIR

    def get_token_dir(self) -> str:
        return TokenSigningPaths.CRDT_TOKEN_DIR

    def get_file_prefix(self) -> str:
        return "crdt"

    def get_token_type_name(self) -> str:
        return "CRDT"
