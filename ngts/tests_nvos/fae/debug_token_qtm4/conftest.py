"""
Conftest for QTM4 Debug Token tests.
"""
import logging
import os
import pytest

from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.tests_nvos.fae.debug_token_qtm4.consts import DebugFwPatterns
from ngts.tests_nvos.fae.debug_token_qtm4.debug_fw_generator import DebugFirmwareGenerator
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def skip_if_prod_asics():
    """
    Skip functionality tests if the system is OPN (production).

    Use this fixture in tests that require IPN (dev) systems for debug token functionality.
    Basic tests can still run on OPN systems.

    Example:
        >>> def test_crdt_complete_flow(engines, skip_if_prod_asics):
        ...     # Test will be skipped on OPN systems
        ...     pass
    """
    if not Fae().platform.secure_state.is_asic_dev_signed():
        pytest.skip("Debug token functionality tests are only supported on dev signed asics. Skipping on prod asics.")


@pytest.fixture(scope='session')
def ensure_debug_firmware(engines, target_version):
    """
    Ensure debug firmware is available for CRDT tests.

    This fixture checks if debug firmware already exists for the required FW version.
    If not, it generates the debug firmware (bin and mfa files) using DebugFirmwareGenerator.

    The generated files are stored in a shared location and reused across tests.

    Args:
        engines: Test engines dict with 'dut' and 'sonic_mgmt' (player)
        target_version: Target NVOS version path

    Returns:
        Dict with keys: bin_path, bin_filename, mfa_path, mfa_filename, version_name

    Example:
        >>> def test_crdt_complete_flow(engines, ensure_debug_firmware):
        ...     fw_info = ensure_debug_firmware
        ...     debug_fw_bin = fw_info['bin_filename']
        ...     version = fw_info['version_name']
    """
    with allure.step('Ensure debug firmware is available'):
        generator = DebugFirmwareGenerator(
            engines=engines,
            target_version=target_version
        )

        # generate_debug_firmware handles:
        # - Checking for existing firmware (reuses if version matches)
        # - Generating new firmware if needed
        # - Falling back to JSON if generation fails
        bin_path, mfa_path = generator.generate_debug_firmware()

        bin_filename = os.path.basename(bin_path)
        mfa_filename = os.path.basename(mfa_path)

        # Extract version from filename: debug_fw_41_2018_0220.bin -> 41.2018.0220
        match = DebugFwPatterns.VERSION_FROM_FILENAME.search(bin_filename)
        version_name = f"{match.group(1)}.{match.group(2)}.{match.group(3)}" if match else None

        fw_info = {
            'bin_path': bin_path,
            'bin_filename': bin_filename,
            'mfa_path': mfa_path,
            'mfa_filename': mfa_filename,
            'version_name': version_name
        }

        logger.info(f"Debug firmware available: {bin_filename} (version: {version_name})")

        return fw_info
