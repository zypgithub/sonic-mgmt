import logging
import os
import subprocess
import allure
import pytest
from ngts.constants.nv_optimizer_constant import NvOptimizerEnvVariables

logger = logging.getLogger()


class TestInstallNvOptimizer:
    @pytest.mark.dependency()
    @pytest.mark.disable_loganalyzer
    @allure.title('post installation steps')
    def test_install_nv_optimizer(self):
        with allure.step("Clone the repository"):
            clone_nv_optimizer_repo()

        with allure.step("Create and activate virtual environment"):
            install_conda()
            subprocess.run(["bash", NvOptimizerEnvVariables.install_venv_script_path], check=True)

        with allure.step("Install requirements using pip"):
            venv_path = NvOptimizerEnvVariables.nv_optimizer_venv_path
            install_pip_dependencies(repo_path=NvOptimizerEnvVariables.nv_optimizer_dir, venv_path=venv_path)


def install_conda():
    if not os.path.exists("/root/miniconda"):
        conda_url = NvOptimizerEnvVariables.conda_url
        subprocess.run(["wget", conda_url], check=True)
        subprocess.run(["bash", "Miniconda3-latest-Linux-x86_64.sh", "-b", "-p", "/root/miniconda"], check=True)
        subprocess.check_call([NvOptimizerEnvVariables.conda_path, "init"])
    else:
        pass


def clone_nv_optimizer_repo():
    repo_path = NvOptimizerEnvVariables.nv_optimizer_dir
    repo_url = NvOptimizerEnvVariables.nv_optimizer_repo_url
    repo_url_without_protocol = repo_url.replace("https://", "")
    clone_url = f"https://{NvOptimizerEnvVariables.nv_optimizer_api_user}:{NvOptimizerEnvVariables.nv_optimizer_api_key}@{repo_url_without_protocol}"
    if not os.path.exists(repo_path):
        subprocess.run(["git", "clone", clone_url, repo_path], check=True)


def install_pip_dependencies(repo_path, venv_path):
    pip_path = os.path.join(venv_path, "bin", "pip")
    dev_requirements_path = repo_path + "/.[dev]"
    logger.info(f"Installing requirements from {dev_requirements_path}")
    subprocess.run([pip_path, "install", "-e", dev_requirements_path], check=True)
    logger.info("Requirements installed successfully")
    logger.info("Changing the Git branch to switch_perf")
    subprocess.run(["git", "-C", repo_path, "checkout", "-b", NvOptimizerEnvVariables.nv_optimizer_git_branch, "--track", f"origin/{NvOptimizerEnvVariables.nv_optimizer_git_branch}"], check=True)
