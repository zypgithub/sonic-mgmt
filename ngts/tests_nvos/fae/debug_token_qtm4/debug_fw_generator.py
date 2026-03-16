"""
Debug Firmware Generator Tool

Generates debug firmware (bin and mfa) from the ASIC firmware release.
Uses git-based approach to find the correct FW version based on target NVOS version.

Usage:
    generator = DebugFirmwareGenerator(engines, target_version)
    bin_path, mfa_path = generator.generate_debug_firmware()
"""
import os
import time
import glob
import logging
from dataclasses import dataclass
from typing import Tuple, Optional

from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.FilesTool import FilesTool
from ngts.nvos_tools.infra.NvosGitTool import NvosGitTool
from ngts.tests_nvos.fae.debug_token_qtm4.consts import (
    DebugFwPaths,
    DebugFwFilenames,
    DebugFwCommands,
    DebugFwTimeouts,
)
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@dataclass
class FirmwareVersionInfo:
    """Firmware version paths and info."""
    version: str
    mlx_path: str
    ini_path: str


class DebugFirmwareGenerator:
    """Generates debug firmware from ASIC firmware release."""

    def __init__(self, engines, target_version: str):
        """
        Initialize generator.

        Args:
            engines: Test engines dict with 'dut'
            target_version: Target NVOS version path
        """
        self.dut_engine = engines.dut
        self.target_version = target_version
        self.git_tool = NvosGitTool()

    # ==================== JSON Fallback (using BmcTool) ====================

    def _get_firmware_from_json(self) -> Optional[Tuple[str, str]]:
        """
        Fallback: Get debug firmware paths from JSON using BmcTool.

        Returns:
            Tuple of (bin_path, mfa_path) if found, None otherwise
        """
        try:
            debug_asic = BmcTool.get_fw_component_version_dict("debug_asic", "latest")
            bin_path = debug_asic.get('bin_path')
            mfa_path = debug_asic.get('mfa_path')

            if bin_path and mfa_path and os.path.exists(bin_path) and os.path.exists(mfa_path):
                logger.info(f"Found debug firmware in JSON: bin={bin_path}, mfa={mfa_path}")
                return bin_path, mfa_path
            return None
        except Exception as e:
            logger.warning(f"JSON fallback failed: {e}")
            return None

    # ==================== Filename Helpers ====================

    def _get_fw_filenames(self, fw_version: str) -> Tuple[str, str]:
        """Get bin and mfa filenames for a FW version."""
        version_safe = fw_version.replace('.', '_').replace('-', '_')
        bin_name = f"{DebugFwFilenames.DEBUG_FW_PREFIX}{version_safe}.bin"
        mfa_name = f"{DebugFwFilenames.DEBUG_FW_PREFIX}{version_safe}.mfa"
        return bin_name, mfa_name

    def _get_fw_paths(self, fw_version: str) -> Tuple[str, str]:
        """Get full paths for bin and mfa files."""
        bin_name, mfa_name = self._get_fw_filenames(fw_version)
        return f"{DebugFwPaths.DEBUG_FW_OUTPUT_DIR}/{bin_name}", f"{DebugFwPaths.DEBUG_FW_OUTPUT_DIR}/{mfa_name}"

    def _check_existing_firmware(self, required_fw_version: str) -> Optional[Tuple[str, str]]:
        """Check if debug firmware for required version already exists."""
        bin_path, mfa_path = self._get_fw_paths(required_fw_version)

        if os.path.exists(bin_path) and os.path.exists(mfa_path):
            if os.path.getsize(bin_path) > 0 and os.path.getsize(mfa_path) > 0:
                logger.info(f"Found existing firmware: {bin_path}, {mfa_path}")
                return bin_path, mfa_path

        logger.info(f"No existing firmware found for version {required_fw_version}")
        return None

    # ==================== File Operations (using engine.copy_file) ====================

    def _fw_version_to_paths(self, fw_version: str) -> FirmwareVersionInfo:
        """Get file paths for FW version.

        Handles BUILDS directory structure: fw-Quantum-4-rel-{version}-build-XXX/
        with dist/ for mlx and etc/beta_ini/ for ini files.
        """
        version_under = fw_version.replace('.', '_').replace('-', '_')
        base = '_'.join(version_under.split('_')[:3])

        # BUILDS path pattern: fw-Quantum-4-rel-{version}-build-XXX
        # Try exact version first, then base version with glob
        patterns = [
            f"{DebugFwPaths.FW_RELEASE_BASE}/fw-Quantum-4-rel-{version_under}-build-*",
            f"{DebugFwPaths.FW_RELEASE_BASE}/fw-Quantum-4-rel-{base}-build-*",
        ]

        build_dir = None
        for pattern in patterns:
            matches = sorted(glob.glob(pattern))
            if matches:
                build_dir = matches[-1]  # Use latest build
                break

        if not build_dir:
            raise ValueError(f"FW release not found for: {fw_version}")

        return FirmwareVersionInfo(
            version=fw_version,
            mlx_path=f"{build_dir}/dist/{DebugFwFilenames.MLX_FW_FILE}",
            ini_path=f"{build_dir}/etc/beta_ini/{DebugFwFilenames.ROSALIND_INI_FILE}"
        )

    def _copy_to_switch(self, fw_info: FirmwareVersionInfo) -> Tuple[str, str]:
        """Copy mlx and ini files to switch using engine.copy_file."""
        mlx_name = os.path.basename(fw_info.mlx_path)
        ini_name = os.path.basename(fw_info.ini_path)

        switch_mlx = f"{DebugFwPaths.SWITCH_TMP_DIR}/{mlx_name}"
        switch_ini = f"{DebugFwPaths.SWITCH_TMP_DIR}/{ini_name}"

        self.dut_engine.copy_file(source_file=fw_info.mlx_path, dest_file=mlx_name,
                                  file_system=DebugFwPaths.SWITCH_TMP_DIR, direction='put')
        self.dut_engine.copy_file(source_file=fw_info.ini_path, dest_file=ini_name,
                                  file_system=DebugFwPaths.SWITCH_TMP_DIR, direction='put')

        return switch_mlx, switch_ini

    def _copy_from_switch(self, bin_path: str, mfa_path: str, fw_version: str) -> Tuple[str, str]:
        """Copy generated files from switch using engine.copy_file."""
        output_bin, output_mfa = self._get_fw_paths(fw_version)

        os.makedirs(DebugFwPaths.DEBUG_FW_OUTPUT_DIR, exist_ok=True)

        self.dut_engine.copy_file(source_file=bin_path, dest_file=output_bin,
                                  file_system=os.path.dirname(output_bin), direction='get')
        self.dut_engine.copy_file(source_file=mfa_path, dest_file=output_mfa,
                                  file_system=os.path.dirname(output_mfa), direction='get')

        return output_bin, output_mfa

    # ==================== Generation ====================

    def _setup_switch(self) -> None:
        """Setup switch workspace and install dependencies."""
        self.dut_engine.run_cmd(DebugFwCommands.CREATE_TMP_DIR.format(tmp_dir=DebugFwPaths.SWITCH_TMP_DIR))

        # Always install MFT internal - mlxburn needs internal image generation tools
        # Even if mlx_mfa_gen_old exists, mlxburn may be missing required components
        mft_name = os.path.basename(DebugFwPaths.MFT_INTERNAL_PATH)
        self.dut_engine.copy_file(source_file=DebugFwPaths.MFT_INTERNAL_PATH, dest_file=mft_name,
                                  file_system='/tmp', direction='put')
        self.dut_engine.run_cmd(DebugFwCommands.INSTALL_MFT.format(mft_name=mft_name))

        # Install pycryptodome if needed
        if "not_found" in self.dut_engine.run_cmd(DebugFwCommands.CHECK_PYCRYPTO):
            self.dut_engine.run_cmd(DebugFwCommands.INSTALL_PYCRYPTO, timeout=DebugFwTimeouts.PIP_INSTALL_TIMEOUT)

    def _run_background_cmd(self, cmd: str, done_marker: str, log_file: str,
                            max_wait: int, poll_interval: int) -> None:
        """Run command in background and poll for completion. Checks exit code."""
        bg_cmd = DebugFwCommands.BACKGROUND_CMD.format(cmd=cmd, log_file=log_file, done_marker=done_marker)
        self.dut_engine.run_cmd(bg_cmd, timeout=60)

        elapsed = 0
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                result = self.dut_engine.run_cmd(
                    DebugFwCommands.CHECK_DONE_MARKER.format(done_marker=done_marker),
                    timeout=30,
                    retry_run=False
                )
                exit_code = result.strip()
            except Exception as e:
                logger.warning(f"SSH error while polling ({elapsed}s): {e}. Reconnecting...")
                try:
                    self.dut_engine.disconnect()
                except Exception:
                    pass
                time.sleep(5)
                continue

            if exit_code != 'running':
                logger.info(f"Command completed after {elapsed}s with exit code: {exit_code}")
                if exit_code != '0':
                    log_content = self.dut_engine.run_cmd(
                        DebugFwCommands.READ_LOG_TAIL.format(log_file=log_file),
                        timeout=30
                    )
                    raise ValueError(f"Command failed with exit code {exit_code}: {log_content}")
                return

            logger.info(f"Still running... ({elapsed}s)")

        raise ValueError(f"Command timed out after {max_wait}s")

    def _generate_bin(self, mlx_path: str, ini_path: str, fw_version: str) -> str:
        """Generate debug bin using mlxburn."""
        bin_name, _ = self._get_fw_filenames(fw_version)
        output = f"{DebugFwPaths.SWITCH_TMP_DIR}/{bin_name}"

        # Modify ini for debug
        self.dut_engine.run_cmd(DebugFwCommands.ADD_DEBUG_FW_CMD.format(ini_path=ini_path))

        # Run mlxburn in background
        cmd = DebugFwCommands.MLXBURN_CMD.format(mlx_path=mlx_path, ini_path=ini_path, output=output)
        done_marker = f"{DebugFwPaths.SWITCH_TMP_DIR}/{DebugFwFilenames.MLXBURN_DONE}"
        log_file = f"{DebugFwPaths.SWITCH_TMP_DIR}/{DebugFwFilenames.MLXBURN_LOG}"
        self._run_background_cmd(cmd, done_marker, log_file,
                                 DebugFwTimeouts.MLXBURN_MAX_WAIT, DebugFwTimeouts.MLXBURN_POLL_INTERVAL)

        if not FilesTool.file_exists(self.dut_engine, output):
            log = self.dut_engine.run_cmd(f"cat {log_file}")
            raise ValueError(f"mlxburn failed: {log}")

        return output

    def _generate_mfa(self, fw_version: str) -> str:
        """Generate mfa from bin."""
        bin_name, mfa_name = self._get_fw_filenames(fw_version)
        pkg_name = bin_name.replace('.bin', '')

        cmd = f"cd {DebugFwPaths.SWITCH_TMP_DIR} && " + DebugFwCommands.MFA_GEN_CMD.format(
            pkg_name=pkg_name, source_dir=DebugFwPaths.SWITCH_TMP_DIR)
        done_marker = f"{DebugFwPaths.SWITCH_TMP_DIR}/{DebugFwFilenames.MFA_DONE}"
        log_file = f"{DebugFwPaths.SWITCH_TMP_DIR}/{DebugFwFilenames.MFA_LOG}"
        self._run_background_cmd(cmd, done_marker, log_file,
                                 DebugFwTimeouts.MFA_MAX_WAIT, DebugFwTimeouts.MFA_POLL_INTERVAL)

        output = f"{DebugFwPaths.SWITCH_TMP_DIR}/{mfa_name}"
        if not FilesTool.file_exists(self.dut_engine, output):
            mfa_files = self.dut_engine.run_cmd(f"ls {DebugFwPaths.SWITCH_TMP_DIR}/*.mfa 2>/dev/null || echo 'none'")
            if "none" in mfa_files:
                log = self.dut_engine.run_cmd(f"cat {log_file}")
                raise ValueError(f"mfa generation failed: {log}")
            output = mfa_files.strip().split('\n')[0]

        return output

    # ==================== Main Entry Point ====================

    def generate_debug_firmware(self, cleanup: bool = True, force_regenerate: bool = False) -> Tuple[str, str]:
        """
        Generate debug firmware.

        Args:
            cleanup: Cleanup temp files on switch
            force_regenerate: Skip existing firmware check

        Returns:
            Tuple of (bin_path, mfa_path)
        """
        with allure.step('Generate debug firmware'):
            try:
                # Find required FW version using NvosGitTool
                _, fw_version = self.git_tool.find_previous_fw_version(self.target_version)
                logger.info(f"Required FW version: {fw_version}")

                # Check for existing firmware
                if not force_regenerate:
                    existing = self._check_existing_firmware(fw_version)
                    if existing:
                        return existing

                # Get FW paths
                fw_info = self._fw_version_to_paths(fw_version)

                # Setup and generate
                self._setup_switch()
                switch_mlx, switch_ini = self._copy_to_switch(fw_info)
                bin_path = self._generate_bin(switch_mlx, switch_ini, fw_version)
                mfa_path = self._generate_mfa(fw_version)

                # Copy to output
                output_bin, output_mfa = self._copy_from_switch(bin_path, mfa_path, fw_version)

                return output_bin, output_mfa

            except Exception as e:
                logger.error(f"Generation failed: {e}")

                # Fallback to JSON
                logger.info("Trying fallback: loading from JSON file")
                fallback = self._get_firmware_from_json()
                if fallback:
                    return fallback
                raise

            finally:
                if cleanup:
                    self.dut_engine.run_cmd(DebugFwCommands.CLEANUP_TMP_DIR.format(tmp_dir=DebugFwPaths.SWITCH_TMP_DIR))
