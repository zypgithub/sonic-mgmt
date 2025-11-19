import subprocess
import logging
import os
import glob
import re
from ngts.constants.constants import InfraConst, Sonic_Cache
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.system_helpers import copy_files_to_syncd
from infra.tools.exceptions.test_issue import TestIssue

logger = logging.getLogger()


class SdkCliCommon():
    """
    This class hosts methods which are implemented identically for Linux
    """

    def __init__(self, engine, cli_obj=None, dut_alias=None):
        self.engine = engine
        self.cli_obj = cli_obj
        self.dut_alias = dut_alias

    def get_sdk_version(self):
        sdk_version_output = self.engine.run_cmd(InfraConst.CMD_GET_SDK_VERSION, validate=True)
        sdk_version = re.search(r"SX-SDK ETH (\d+\.\d+\.\d+)", sdk_version_output).group(1)
        return sdk_version

    def get_sdk_branch(self, sdk_version):
        command = f"cat /auto/sw_system_release/sx_sdk_eth/sx_sdk_eth-{sdk_version}/SDK_BRANCH.txt"
        sdk_branch = os.popen(command).read().strip()
        if sdk_branch.startswith("sx_sdk_"):
            sdk_branch = re.search(r"(sx_sdk_\d+_\d+_\d{4})", sdk_branch).group(1)
        return sdk_branch

    def get_kernel_version(self):
        kernel_version_output = self.engine.run_cmd('uname -r', validate=True)
        kernel_version = re.search(r"(\d+\.\d+\.\d+)", kernel_version_output).group(1)
        return kernel_version

    def get_latest_sdk_version(self, cur_sdk_version, sdk_branch):
        dut_kernel_version = self.get_kernel_version()
        deb_file_path = os.path.join(PerfConsts.LATEST_SDK_DEB_DIR_TEMPLATE.format(SDK_BRANCH=sdk_branch))
        available_kernel_versions = os.listdir(deb_file_path)

        deb_kernel_version = None
        for kernel_version in available_kernel_versions:
            if kernel_version.startswith(dut_kernel_version):
                deb_file_path = os.path.join(deb_file_path, kernel_version)
                deb_kernel_version = kernel_version
                break
        if not deb_kernel_version:
            logger.warning(f"No matching kernel version found for {dut_kernel_version}")
            return cur_sdk_version
        files_available_in_deb_dir = glob.glob(os.path.join(deb_file_path, PerfConsts.LATEST_SDK_DEB_FILE_TEMPLATE))
        sdk_version = re.search(r"sys-sdk-git_1.mlnx.(\d+.\d+.\d+.*\d*)_", files_available_in_deb_dir[0]).group(1)

        if sdk_version.count('.') == 3:
            last_dot_index = sdk_version.rfind('.')
            sdk_version = sdk_version[:last_dot_index] + '-' + sdk_version[last_dot_index + 1:]

        return sdk_version

    def get_perf_sys_sdk_tar_file_name(self, sdk_branch):
        file_name = PerfConsts.PERF_SYS_SDK_TAR_FILE_TEMPLATE.format(SDK_BRANCH=sdk_branch)
        path = PerfConsts.PERF_SYS_SDK_TAR_FILE_PATH
        if not os.path.exists(path, file_name):
            logger.warning(f"Performance system SDK tar file {file_name} not found in {path}, use master as default")
            file_name = PerfConsts.PERF_SYS_SDK_TAR_FILE_TEMPLATE.format(SDK_BRANCH='master')
        if not os.path.exists(path, file_name):
            raise TestIssue(f"Performance system SDK tar file {file_name} for master not found in {path}, please check the sdk branch")
        return path, file_name

    def get_generic_cmd_prefix(self, prefix_cmd, cmd):
        generic_cmd_prefix = f"{prefix_cmd} '{cmd}'" if prefix_cmd else cmd
        return generic_cmd_prefix

    def overlay_perf_sys_sdk_to_sys_sdk(self, sdk_branch, is_in_syncd=False, tar_file_enabled=False):
        docker_exec_syncd_cmd = InfraConst.DOCKER_EXEC_BASH_CMD.format(DOCKER=InfraConst.SYNCD_DOCKER)
        command_prefix = f"{docker_exec_syncd_cmd}" if is_in_syncd else ""
        if tar_file_enabled:
            self.get_perf_sys_sdk_with_tar(sdk_branch, command_prefix, is_in_syncd)
        else:
            self.get_perf_sys_sdk_with_clone(sdk_branch, command_prefix)
        self.run_overlay_cmd(command_prefix, is_in_syncd)

    def run_overlay_cmd(self, command_prefix, is_in_syncd):
        perf_sys_sdk_path = '/root/perf_sys_sdk'
        sys_sdk_path = '/root/sys_sdk'
        overlay_cmd = f'sudo {perf_sys_sdk_path}/overlay_files.py {sys_sdk_path} {perf_sys_sdk_path} to_sys_sdk --verbose'
        if not is_in_syncd:
            self.engine.run_cmd(overlay_cmd)
        else:
            self.engine.run_cmd(self.get_generic_cmd_prefix(command_prefix, overlay_cmd))

    def get_repo_branches(self, repo_url):
        cmd = ["git", "ls-remote", "--heads", repo_url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        branches = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2:
                ref = parts[1]
                if ref.startswith("refs/heads/"):
                    branches.append(ref.replace("refs/heads/", ""))
        return branches

    def get_perf_sys_sdk_with_clone(self, sdk_branch, command_prefix):
        repo_url = f"https://{Sonic_Cache.gerrit_username}:{Sonic_Cache.gerrit_api_token}@git-nbu-sw.nvidia.com/r/a/switchx/perf_sys_sdk"
        default_sdk_branch = "master"
        remote_branches = self.get_repo_branches(repo_url)
        sdk_branch_to_use = sdk_branch if sdk_branch in remote_branches else default_sdk_branch
        clone_cmd = f'git clone --branch {sdk_branch_to_use} \"{repo_url}\"'
        clone_at_root_cmd = f"cd /root/ && {clone_cmd}"
        self.engine.run_cmd(self.get_generic_cmd_prefix(command_prefix, clone_at_root_cmd))

    def get_perf_sys_sdk_with_tar(self, sdk_branch, command_prefix, is_in_syncd):
        path, file_name = self.get_perf_sys_sdk_tar_file_name(sdk_branch)
        tar_cmd = f'sudo tar -xzf /tmp/{file_name} -C /root/'
        if is_in_syncd:
            copy_files_to_syncd(self.engine, [file_name], path, syncd_dir='/tmp/')
            self.engine.run_cmd(self.get_generic_cmd_prefix(command_prefix, tar_cmd))
        else:
            self.engine.copy_file(source_file=os.path.join(path, file_name),
                                  dest_file=file_name,
                                  file_system='/tmp/', overwrite_file=True, verify_file=False)
            self.engine.run_cmd(tar_cmd)
