import os
from ngts.constants.constants import BugHandlerConst


class NvOptimizerEnvVariables:
    """
    Class to handle environment variables
    """

    ngts_dir = BugHandlerConst.NGTS_PATH
    configuration_parameter_file = "configuration_parameter.json"
    traffic_parameter_file = "traffic_parameter.json"
    test_parameter_file = "test_parameter.json"
    result_parameter_file = "performance_tests/nv_optimizer/results.txt"
    log_file = "log.txt"
    report_file = "report.txt"
    nv_optimizer_repo_url = "https://gitlab-master.nvidia.com/autonomous_data_center/storage-optimization.git"
    nv_optimizer_pip_path = "bin/pip"
    nv_optimizer_requirements_path = "requirements.txt"
    nv_optimizer_api_key = os.getenv("NV_OPTIMISER_API_KEY")
    nv_optimizer_api_user = "AAA"
    conda_url = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    conda_path = "/root/miniconda/bin/conda"
    nv_optimizer_venv_path = "/root/miniconda/envs/optimization"
    nv_optimizer_dir = "/root/mars/workspace/nvoptimizer"
    nv_optimizer_git_branch = "switch_perf"
    install_venv_script_path = "/root/mars/workspace/sonic-mgmt/ngts/scripts/nv_optimizer/install_venv.sh"
