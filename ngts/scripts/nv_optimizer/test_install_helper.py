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
    @allure.title('Install nv optimizer and dependencies')
    def test_install_nv_optimizer(self):
        with allure.step("Clone the repository"):
            clone_nv_optimizer_repo()

        with allure.step("Create and activate virtual environment"):
            install_conda()
            process_worker(cmd_list=["bash", NvOptimizerEnvVariables.install_venv_script_path])

        with allure.step("Install requirements using pip"):
            venv_path = NvOptimizerEnvVariables.nv_optimizer_venv_path
            install_pip_dependencies(repo_path=NvOptimizerEnvVariables.nv_optimizer_dir, venv_path=venv_path)


def install_conda():
    if not os.path.exists("/root/miniconda"):
        conda_url = NvOptimizerEnvVariables.conda_url
        logger.info(f"Downloading conda from {conda_url}")
        process_worker(cmd_list=["wget", "--no-verbose", "--tries=3", "--timeout=30", conda_url, "-O", "/root/mars/workspace/Miniconda3-latest-Linux-x86_64.sh"], check=True)
        logger.info("Installing conda")
        process_worker(cmd_list=["bash", "/root/mars/workspace/Miniconda3-latest-Linux-x86_64.sh", "-b", "-p", "/root/miniconda"], check=True)
        logger.info("Initializing conda")
        process_worker(cmd_list=[NvOptimizerEnvVariables.conda_path, "init"], check=True)
    else:
        pass


def clone_nv_optimizer_repo():
    repo_path = NvOptimizerEnvVariables.nv_optimizer_dir
    repo_url = NvOptimizerEnvVariables.nv_optimizer_repo_url
    repo_url_without_protocol = repo_url.replace("https://", "")
    clone_url = f"https://{NvOptimizerEnvVariables.nv_optimizer_api_user}:{NvOptimizerEnvVariables.nv_optimizer_api_key}@{repo_url_without_protocol}"
    if not os.path.exists(repo_path):
        logger.info(f"Cloning the repository to {repo_path}")
        process_worker(cmd_list=["git", "clone", clone_url, repo_path], check=True)
        logger.info("Repository cloned successfully")
    else:
        logger.warning(f"Repository already exists in {repo_path}")

    # Todo: Remove this after the dev branch is merged
    logger.info("Checking out the dev branch")
    process_worker(cmd_list=["git", "-C", repo_path, "checkout", "dev"], check=True)


def install_pip_dependencies(repo_path, venv_path):
    pip_path = os.path.join(venv_path, "bin", "pip")
    dev_requirements_path = repo_path + "/.[dev]"
    logger.info(f"Installing requirements from {dev_requirements_path}")
    process_worker(cmd_list=[pip_path, "install", "-e", dev_requirements_path], check=True)
    logger.info("Requirements installed successfully")


def print_output(process):
    for line in process.stdout:
        logger.info(line.strip())
    for line in process.stderr:
        logger.error(line.strip())


def check_process_success(process):
    if process.returncode != 0:
        raise Exception(f"Failed to complete the process: {process.returncode}")


def process_worker(cmd_list, check=False):
    process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print_output(process)
    process.wait()
    check_process_success(process)
