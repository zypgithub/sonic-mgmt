"""ISSU Test Configuration - Dynamic FW Image Detection for Last_FW testing."""
import logging
import os
import re
import pytest
import subprocess
from pathlib import Path

from ngts.nvos_constants.constants_nvos import IssuConsts
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.system.issu.test_system_issu import install_system_image_and_start_opensm

logger = logging.getLogger()

# Pre-cloned nvos repo (synced by cron: /auto/sw_system_project/NVOS_INFRA/scripts/git_pull_chipsim.sh)
NVOS_REPO_PATH = Path("/auto/sw_system_project/NVOS_INFRA/ChipSim/nvos-master/nvos")
NVOS_RELEASE_PATH = "/auto/sw_system_release/nos/nvos"


def extract_version_from_path(path: str) -> str:
    """Extract version (e.g. '25.03.0104-005') from image path."""
    match = re.search(r'nvos-amd64-(\d+\.\d+\.\d+(?:-\d+)?)', path)
    if not match:
        match = re.search(r'/(\d+\.\d+\.\d+(?:-\d+)?)/amd64/', path)
    return match.group(1) if match else None


def get_image_type_from_path(path: str) -> str:
    """
    Return 'prod' or 'dev' based on path.
    Detection order:
    1. Explicit /prod/ or /dev/ in path
    2. lastrc_prod_* = prod, lastrc_* (without prod) = dev
    3. Version format: no patch suffix (e.g. 25.03.0104) = prod, with patch (e.g. 25.03.0104-005) = dev
    """
    if '/prod/' in path or 'lastrc_prod' in path:
        return 'prod'
    if '/dev/' in path or 'lastrc_' in path:
        return 'dev'
    version = extract_version_from_path(path)
    if version and '-' not in version:
        return 'prod'
    return 'dev'


def parse_version(ver: str) -> tuple:
    """Parse version string to tuple for comparison. E.g. '25.03.0103-008' -> (25, 3, 103, 8)"""
    match = re.match(r'(\d+)\.(\d+)\.(\d+)(?:-(\d+))?', ver)
    if not match:
        return (0, 0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4) or 0))


def git_cmd(repo_dir: Path, args: list) -> subprocess.CompletedProcess:
    """Run git command with safe.directory config to handle shared repo ownership."""
    repo_path = str(repo_dir)

    # Create temporary HOME with .gitconfig to bypass ownership check
    tmp_home = Path("/tmp/issu_git_home")
    tmp_home.mkdir(exist_ok=True)
    tmp_gitconfig = tmp_home / ".gitconfig"
    tmp_gitconfig.write_text("[safe]\n\tdirectory = *\n")

    cmd = ["git", "-c", "safe.directory=*"] + args

    # Set environment variables to bypass ownership check
    env = os.environ.copy()
    env['HOME'] = str(tmp_home)
    env['GIT_CONFIG_GLOBAL'] = str(tmp_gitconfig)
    env['GIT_CONFIG_SYSTEM'] = '/dev/null'
    env['GIT_CONFIG_NOSYSTEM'] = '1'

    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        logger.error(f"Git command failed: {' '.join(args[:3])}... - {result.stderr[:200]}")
    return result


def get_qtm3_fw_at_tag(repo_dir: Path, tag: str) -> str:
    """Get QTM3 FW version from fw.mk at specific tag using git show (no checkout needed)."""
    result = git_cmd(repo_dir, ["show", f"{tag}:platform/mellanox/fw.mk"])
    if result.returncode != 0:
        return None
    match = re.search(r'MLNX_IB_QTM3_FW_VER\s*=\s*(\S+)', result.stdout)
    return match.group(1) if match else None


def build_image_path(ver: str, image_type: str) -> str:
    """Build image path for given version."""
    return f"{NVOS_RELEASE_PATH}/{ver}/amd64/{image_type}/nvos-amd64-{ver}.bin"


def get_tag_prefix(version: str, repo_dir: Path) -> str:
    """
    Determine the git tag prefix based on version.
    - 25.03.xxxx -> master_*
    - 25.02.6xxx -> nvos-25-02-6000_* or nvos-25-02-6100_*
    """
    if version.startswith('25.03.'):
        return 'master'

    result = git_cmd(repo_dir, ["tag", "-l", f"*_{version.split('-')[0]}*", "--sort=-version:refname"])
    if result.stdout.strip():
        first_tag = result.stdout.strip().split('\n')[0]
        if '_' in first_tag:
            return first_tag.split('_')[0]

    return 'master'


def get_previous_fw_image_path(target_version: str, image_type: str = 'dev') -> str:
    """
    Find image with previous QTM3 FW version for Last_FW ISSU testing.
    Returns path to image with different (older) FW, or None.
    For prod images, searches for base version (without patch suffix).
    Uses pre-cloned repo at NVOS_REPO_PATH (synced by cron).
    """
    target_ver = extract_version_from_path(target_version)
    if not target_ver:
        logger.error("Could not parse version from target_version")
        return None
    logger.info(f"Finding previous FW for: {target_ver} ({image_type})")

    repo_dir = NVOS_REPO_PATH
    if not repo_dir.exists():
        logger.error(f"Pre-cloned nvos repo not found: {repo_dir}")
        return None

    tag_prefix = get_tag_prefix(target_ver, repo_dir)
    logger.info(f"Using tag prefix: {tag_prefix}")

    result = git_cmd(repo_dir, ["tag", "-l", f"{tag_prefix}_*", "--sort=-version:refname"])
    if result.returncode != 0:
        logger.error(f"Git tag command failed: {result.stderr}")
        return None

    all_tags = result.stdout.strip().split('\n')
    tags = [t for t in all_tags if t and re.match(rf'{re.escape(tag_prefix)}_\d+\.\d+\.\d+(-\d+)?$', t)]
    logger.info(f"Found {len(tags)} matching tags")

    # Find target tag and FW version
    target_tag, target_idx = None, -1
    target_fw = None
    target_parsed = parse_version(target_ver)
    target_base = target_ver.split('-')[0]
    target_base_parsed = parse_version(target_base)[:3]
    has_patch = '-' in target_ver

    for i, tag in enumerate(tags):
        tag_ver = tag.split("_", 1)[1]
        tag_base = tag_ver.split('-')[0]
        tag_base_parsed = parse_version(tag_base)[:3]
        tag_parsed = parse_version(tag_ver)

        if not has_patch:
            if tag_base_parsed == target_base_parsed and not target_fw:
                target_fw = get_qtm3_fw_at_tag(repo_dir, tag)
            if tag_base_parsed < target_base_parsed:
                target_tag, target_idx = tag, i
                break
        elif tag_parsed <= target_parsed:
            target_tag, target_idx = tag, i
            target_fw = get_qtm3_fw_at_tag(repo_dir, tag)
            break

    if not target_tag:
        logger.error(f"Tag not found for {target_ver}")
        return None
    if not target_fw:
        logger.error(f"Could not get QTM3 FW at target tag: {target_tag}")
        return None

    logger.info(f"Target: {target_ver} ({image_type}) -> QTM3 FW: {target_fw}")

    # Search backwards for different FW with existing image
    prev_path = None
    last_base_ver = None
    last_base_fw = None

    for i in range(target_idx + 1, min(target_idx + 100, len(tags))):
        tag = tags[i]
        ver = tag.split("_", 1)[1]
        base_ver = ver.split('-')[0] if '-' in ver else ver

        if image_type == 'prod' and last_base_ver and base_ver != last_base_ver:
            base_path = build_image_path(last_base_ver, image_type)
            if os.path.exists(base_path):
                prev_path = base_path
                logger.info(f"Found {image_type} {last_base_ver} (base) with FW: {last_base_fw}")
                break

        fw = get_qtm3_fw_at_tag(repo_dir, tag)
        if fw and fw != target_fw:
            path = build_image_path(ver, image_type)
            if os.path.exists(path):
                prev_path = path
                logger.info(f"Found {image_type} {ver} with FW: {fw}")
                break
            else:
                logger.info(f"Version {ver} has different FW ({fw}) but no {image_type} image, searching...")

            last_base_ver = base_ver
            last_base_fw = fw

    return prev_path


@pytest.fixture(scope='session', autouse=True)
def prepare_and_recover_issu(engines, devices, target_version, issu_version, request):
    """Setup: find previous FW image. Teardown: recover to target version."""
    logger.info("Starting ISSU session")
    logger.info(f"Target version: {target_version}")

    image_type = get_image_type_from_path(target_version)
    logger.info(f"Detected image type: {image_type}")

    prev_fw_path = get_previous_fw_image_path(target_version, image_type)

    if not prev_fw_path or not os.path.exists(prev_fw_path):
        # Fallback to GA version - test will be skipped if Last_FW == Last_GA
        logger.warning(f"Could not find previous FW image, falling back to GA version")
        logger.warning(f"Last_FW test will be skipped (same as Last_GA)")
        prev_fw_path = issu_version  # Set to GA version so skip condition triggers

    logger.info(f"Previous FW image: {prev_fw_path}")
    request.config.issu_last_fw_path = prev_fw_path

    yield

    # Teardown: recover system to target version
    system = System(devices_dut=devices.dut)
    if hasattr(engines, 'ha') and hasattr(engines, 'hb'):
        with allure.step("Recover system to target image"):
            install_system_image_and_start_opensm(engines, devices.dut, system, target_version, False)
        with allure.step("Clean temp files"):
            for engine, output in [(engines.ha, IssuConsts.SERVER_OUTPUT), (engines.hb, IssuConsts.CLIENT_OUTPUT)]:
                if engine.run_cmd(f'ls {output}'):
                    engine.run_cmd(f'rm -f {output}')
    else:
        with allure.step("Recover system to target image"):
            install_system_image_and_start_opensm(engines, devices.dut, system, target_version)
