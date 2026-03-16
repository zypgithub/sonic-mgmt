"""
Constants for Debug Token (CRDT/CRCS) tests.

Consolidates all paths, commands, filenames, timeouts, and error messages
used across the debug token test module.
"""
import re
from enum import Enum


# ====================
# Paths
# ====================

class DebugFwPaths:
    """Paths for debug firmware generation and storage."""

    # Firmware release base path (using /.autodirect path for MARS player compatibility)
    FW_RELEASE_BASE = "/.autodirect/sw/release/switch_fw/BUILDS/fw-Quantum-4"

    # Output directory for generated debug firmware
    DEBUG_FW_OUTPUT_DIR = "/auto/sw_system_project/NVOS_INFRA/verification_files/debug_token"

    # MFT internal package path (required for mlxburn)
    MFT_INTERNAL_PATH = (
        "/auto/mswg_release_mft/mft-4.34.0/mft-4.34.0-5015/Deliverables/"
        "linux-x86_64/mft-4.34.0-5015-int/DEBS/mft-int_4.34.0-5015_amd64.deb"
    )

    # Temporary directory on switch for generation
    SWITCH_TMP_DIR = "/tmp/debug_fw_gen"


# ====================
# Filenames
# ====================

class DebugFwFilenames:
    """Filenames and prefixes for debug firmware."""

    # INI file for Rosalind platform
    ROSALIND_INI_FILE = "920-9K42W-00L6-GS0_Ax.ini"

    # MLX firmware file
    MLX_FW_FILE = "fw-Quantum-4.mlx"

    # Prefix for generated debug firmware files
    DEBUG_FW_PREFIX = "debug_fw_"

    # Log files for background commands
    MLXBURN_LOG = "mlxburn.log"
    MLXBURN_DONE = "mlxburn.done"
    MFA_LOG = "mfa.log"
    MFA_DONE = "mfa.done"


# ====================
# Commands
# ====================

class DebugFwCommands:
    """Commands for debug firmware generation."""

    # mlxburn command template: -f <mlx_file> -c <ini_file> -wrimage <output>
    MLXBURN_CMD = "mlxburn -f {mlx_path} -c {ini_path} -wrimage {output}"

    # mlx_mfa_gen_old command template: -p <package_name> -s <source_dir>
    MFA_GEN_CMD = "/usr/bin/mlx_mfa_gen_old -p {pkg_name} -s {source_dir}"

    # Sed command to add debug_fw = 1 after signed_fw = 1
    ADD_DEBUG_FW_CMD = "sudo sed -i '/^signed_fw = 1/a debug_fw = 1' {ini_path}"

    # Check for pycryptodome
    CHECK_PYCRYPTO = "python3 -c 'import Crypto' 2>&1 || echo 'not_found'"

    # Install pycryptodome
    INSTALL_PYCRYPTO = "sudo pip3 install pycryptodome"

    # Create temp directory
    CREATE_TMP_DIR = "sudo mkdir -p {tmp_dir} && sudo chmod 777 {tmp_dir}"

    # Install MFT internal package
    INSTALL_MFT = "sudo dpkg -i /tmp/{mft_name}"

    # Cleanup temp directory
    CLEANUP_TMP_DIR = "sudo rm -rf {tmp_dir}"

    # Background command wrapper
    BACKGROUND_CMD = "sudo nohup sh -c '{cmd} > {log_file} 2>&1; echo $? > {done_marker}' &"

    # Check done marker
    CHECK_DONE_MARKER = "cat {done_marker} 2>/dev/null || echo 'running'"

    # Read log tail
    READ_LOG_TAIL = "tail -50 {log_file}"


# ====================
# Timeouts
# ====================

class DebugFwTimeouts:
    """Timeouts for debug firmware generation."""

    # mlxburn timeout (15 minutes)
    MLXBURN_MAX_WAIT = 900
    MLXBURN_POLL_INTERVAL = 30

    # MFA generation timeout (10 minutes)
    MFA_MAX_WAIT = 600
    MFA_POLL_INTERVAL = 15

    # pip install timeout
    PIP_INSTALL_TIMEOUT = 120


# ====================
# Token Constants
# ====================

class DebugTokenConsts:
    """Constants for debug token tests."""

    # Token state enum
    class State(Enum):
        """Token state enum."""
        ENABLED = "enabled"
        DISABLED = "disabled"

    # File extensions
    XML_EXTENSION = '.xml'
    BIN_EXTENSION = '.bin'
    MFA_EXTENSION = '.mfa'

    # Component name for BmcTool lookup
    DEBUG_ASIC_COMPONENT = "debug_asic"

    # Debug firmware path (same as DEBUG_FW_OUTPUT_DIR)
    DEBUG_FW_PATH = DebugFwPaths.DEBUG_FW_OUTPUT_DIR + "/"

    # Token info filenames
    CRCS_TOKEN_INFO = "crcs_token_info.xml"
    CRDT_TOKEN_INFO = "crdt_token_info.xml"


# ====================
# Error Messages
# ====================

class DebugTokenErrors:
    """Error messages for debug token tests."""

    # Validation errors
    INVALID_FILENAME_ERROR = "Invalid filename"
    INVALID_EXTENSION_ERROR = "not in an xml format"
    FILE_NOT_FOUND_ERROR = "File not found"
    FILE_ALREADY_EXISTS_ERROR = "already exists"
    CONNECTION_FAILED_ERROR = "Connection failed"
    NO_ACTIVE_TOKEN_ERROR = "no token installed"


# ====================
# Test Values
# ====================

class DebugTokenTestValues:
    """Test values for error scenarios."""

    INVALID_FILENAME = 'bad<name>.abc'
    NONEXISTENT_FILE = 'nonexistent'
    NONEXISTENT_TOKEN = 'nonexistent_token.bin'
    INVALID_URL = 'scp://nonexistent_host_12345/path/'
    INVALID_TOKEN_URL = 'scp://nonexistent_host_12345/token.bin'


# ====================
# Token Signing Constants
# ====================

class TokenSigningPaths:
    """Paths for token signing operations."""

    # Development key paths
    DK_PRIVATE_KEY_SOURCE = "/auto/sw_system_project/NVOS_INFRA/verification_files/debug_token/token-dk-private-key.pem"
    DK_PRIVATE_KEY_PATH = "/tmp/token-dk-private-key.pem"  # On switch (DUT)

    # UUID for token signing (hex: "InGlEwOoD" in ASCII)
    UUID_HEX = "49 6E 47 6C 45 77 4F 6F 44 0A 00 00 00 00 00 00"

    # Token directories on switch
    CRCS_INFO_DIR = "/etc/platform_debug/info/customer_support"
    CRCS_TOKEN_DIR = "/etc/platform_debug/token/customer_support"
    CRDT_INFO_DIR = "/etc/platform_debug/info/debug_image"
    CRDT_TOKEN_DIR = "/etc/platform_debug/token/debug_image"


class TokenSigningCommands:
    """Commands for token signing operations."""

    # mlxconfig command template for signing
    MLXCONFIG_SIGN_CMD = (
        "mlxconfig -t switch "
        "-p {private_key_path} "
        '-u "{uuid_hex}" '
        "create_conf {input_xml} {output_bin}"
    )

    # Check if file exists
    CHECK_FILE_EXISTS = 'test -f {path} && echo "exists" || echo "missing"'

    # Copy file
    COPY_FILE = "sudo cp {src} {dest}"

    # Create directory
    MKDIR = "sudo mkdir -p {path}"

    # List file details
    LS_FILE = "ls -lh {path}"


# ====================
# Regex Patterns (Pre-compiled for performance)
# ====================

class DebugFwPatterns:
    """Pre-compiled regex patterns for firmware version extraction."""

    # Pattern to extract version from filename: debug_fw_41_2018_0220.bin -> groups (41, 2018, 0220)
    VERSION_FROM_FILENAME = re.compile(r'debug_fw_(\d+)_(\d+)_(\d+)')

    # Pattern to extract version with underscores: debug_fw_41_2018_0220.bin -> "41_2018_0220"
    VERSION_WITH_UNDERSCORES = re.compile(r'debug_fw_(\d+_\d+_\d+)')
