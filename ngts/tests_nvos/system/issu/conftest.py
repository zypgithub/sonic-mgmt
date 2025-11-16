import logging
import pytest
import shutil
import subprocess
from ngts.nvos_constants.constants_nvos import IssuConsts
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.system.issu.test_system_issu import install_system_image_and_start_opensm
from pathlib import Path

logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def prepare_and_recover_issu(engines, devices, target_version, request):
    """
    Prepare to run ISSU and recover system when ISSU session is done
    """
    logger.info(f"start running ISSU session")

    with allure.step("Update ISSU base path"):
        update_issu_base_path(request)

    yield

    system = System(devices_dut=devices.dut)

    if hasattr(engines, 'ha') and hasattr(engines, 'hb'):
        with allure.step(f"Recover system to target image"):
            install_system_image_and_start_opensm(engines, devices.dut, system, target_version, False)

        with allure.step("Clean test temporary files"):
            host_a = engines.ha
            host_b = engines.hb

            if host_a.run_cmd(f'ls {IssuConsts.SERVER_OUTPUT}'):
                host_a.run_cmd(f'rm -f {IssuConsts.SERVER_OUTPUT}')
            if host_b.run_cmd(f'ls {IssuConsts.CLIENT_OUTPUT}'):
                host_b.run_cmd(f'rm -f {IssuConsts.CLIENT_OUTPUT}')
    else:
        with allure.step(f"Recover system to target image and start opensm"):
            install_system_image_and_start_opensm(engines, devices.dut, system, target_version)


def pytest_addoption(parser):
    parser.addoption(
        "--branch",
        action="store",
        default="nvos-25-02-6000",
        help="Branch name to check FW tag from (default: nvos-25-02-6000)"
    )
    parser.addoption(
        "--issu_base",
        action="store",
        default="last_GA",
        help="ISSU base version (last_GA/prev_FW)"
    )


def update_issu_base_path(request):
    """
    Update ISSU base path according to issu_base flag. In case of:
    - 'last_GA': Take the default issu_version path (should be the last GA image)
    - 'last_FW': Call 'get_last_fw_image_path' to get the last image in branch containing the previous FW version.
    """
    issu_base = request.config.getoption("--issu_base")
    issu_version = request.config.getoption("--issu_version")

    if issu_base == 'last_FW':
        # TBD [L.A] update to get_last_fw_image_path(request) after adding
        # deploy key to nbu-sws/nos/nvos.git for the build server
        request.config.issu_base_path = ('/auto/sw_system_release/nos/nvos/25.02.5938-038/'
                                         'amd64/dev/nvos-amd64-25.02.5938-038.bin')
        if request.config.issu_base_path == issu_version:
            request.config.issu_base_path = None
    else:
        # issu_base == 'last_GA'
        request.config.issu_base_path = issu_version


def get_last_fw_image_path(request):
    """
    Clone the repo, find the latest image with the previous FW tag in the last 2 weeks for the given branch,
    and return the full path this image.
    """
    branch = request.config.getoption("--branch")
    branch_full = f"origin/{branch}"
    repo_dir = Path("nvos-test")

    with allure.step("Cleanup from previous runs"):
        if repo_dir.exists():
            shutil.rmtree(repo_dir)

    with allure.step(f"Cloning repo for branch {branch} ..."):
        clone_cmd = [
            "git",
            "clone",
            "ssh://git@gitlab-master.nvidia.com:12051/nbu-sws/nos/nvos.git",
            str(repo_dir),
        ]
        subprocess.run(clone_cmd, check=True)
        cwd = repo_dir

    with allure.step("find latest commit affecting fw.mk in the past 2 weeks"):
        log_cmd = [
            "git",
            "log",
            branch_full,
            "--since=2 weeks ago",
            "--pretty=format:%H",
            "-1",
            "--",
            "platform/mellanox/fw.mk",
        ]
        result = subprocess.run(log_cmd, cwd=cwd, capture_output=True, text=True)
        last_commit_hash = result.stdout.strip()

        if not last_commit_hash:
            logger.info("No update in FW in the last 2 weeks")
            fw_path = "NONE"
        else:
            describe_cmd = [
                "git",
                "describe",
                "--tags",
                "--abbrev=0",
                "--match",
                f"{branch}_*",
                "--exclude",
                "dev*",
                last_commit_hash,
            ]
            tag_result = subprocess.run(
                describe_cmd, cwd=cwd, capture_output=True, text=True, check=True
            )
            tag = tag_result.stdout.strip()
            logger.info(f"Found FW tag: {tag}")

    with allure.step("Derive full image path"):
        if "_" in tag:
            version = tag.split("_", 1)[1]
            fw_path = f"/auto/sw_system_release/nos/nvos/{version}/amd64/dev/nvos-amd64-{version}.bin"
        else:
            fw_path = "NONE"

    with allure.step("Cleanup"):
        shutil.rmtree(repo_dir, ignore_errors=True)

    logger.info(f"FW image path: {fw_path}")
    return fw_path
