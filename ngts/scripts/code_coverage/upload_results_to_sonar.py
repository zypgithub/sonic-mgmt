from pathlib import Path
import logging
import shutil
import allure
import pytest

from ngts.scripts.code_coverage.code_coverage_consts import NvosConsts, SharedConsts
from ngts.nvos_tools.infra.JenkinsTool import JenkinsQueryBuilder, JenkinsTool
from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.scripts.code_coverage import coverage_helpers
from ngts.ngts_types import EnginesT, TopologyT

logger = logging.getLogger(__name__)

python_job_name = "NVOS_Python_upload_results_to_sonar"
cpp_job_name = "NVOS_C_upload_results_to_sonar"


@pytest.fixture(scope='module')
def results_path(topology_obj: TopologyT, engines: EnginesT) -> Path:
    with allure.step("Create device object if needed"):
        if not TestToolkit.devices:
            devices = DeviceFactory.create_devices_object(topology_obj)
            TestToolkit.update_devices(devices)

    with allure.step("Create coverage report path"):
        return coverage_helpers.get_dest_path(engines.dut, NvosConsts.DEST_PATH)


@pytest.mark.disable_loganalyzer
@allure.title('Upload results to sonar')
def test_upload_results_to_sonar(target_version: str, results_path: Path) -> None:
    try:
        with allure.step("Get coverage results paths, branch name and commit id"):
            python_results_path = results_path / SharedConsts.PYTHON_DIR
            logger.info(f"python results path: {python_results_path}")

            cpp_results_path = results_path / SharedConsts.C_DIR
            logger.info(f"cpp results path: {cpp_results_path}")

            branch_name = _get_branch_name(python_results_path.as_posix())
            logger.info(f"branch name: {branch_name}")

            commit_id = _get_commit_id(python_results_path.as_posix())
            logger.info(f"commit id: {commit_id}")

        client = JenkinsTool(project_job_path=SharedConsts.JENKINS_SONAR_PROJECT_PATH)
        general_job_params = (
            JenkinsQueryBuilder()
            .branch(branch_name)
            .commit_id(commit_id)
            .version(1)
            .mailing_list(["yport,ramih"])
        )

        with allure.step('Upload python coverage results to sonar'):
            python_job_params = (
                general_job_params
                .project("NVOS-Python")
                .coverage_folder(python_results_path)
                .build()
            )
            client.trigger_with_query(python_job_name, python_job_params)

        with allure.step('Upload cpp coverage results to sonar'):
            cpp_job_params = (
                general_job_params
                .project("NVOS_CPP")
                .coverage_folder(cpp_results_path)
                .build()
            )
            client.trigger_with_query(cpp_job_name, cpp_job_params)

    except Exception as err:
        raise AssertionError(err)


@pytest.mark.disable_loganalyzer
def test_copy_unitests_results(engines: EnginesT, target_version: str, topology_obj: TopologyT, results_path: Path) -> None:
    """
    Copies unitests coverage XML files from the coverage directory to the destination path.
    The function finds all XML files in the coverage directory and its sub-directories
    and copies them to the destination path.

    Args:
        engines: Test engines object containing DUT information
        target_version: Path to the target version, used to determine the coverage path
        topology_obj: Topology object containing DUT information
    """
    with allure.step("Copy unitests results"):
        with allure.step("Get coverage path from target version"):
            coverage_path = coverage_helpers.get_coverage_path_from_target_version(target_version)
            logger.info(f"coverage path: {coverage_path}")

        with allure.step("Check if destination path exists"):
            with allure.step("Create device object if needed"):
                devices = DeviceFactory.create_devices_object(topology_obj)
                TestToolkit.update_devices(devices)
            dest = results_path / SharedConsts.PYTHON_DIR
            logger.info(f"destination path: {dest}")

        with allure.step("Copy unitests results"):
            for file in map(Path.resolve, Path(coverage_path).rglob('*.xml')):
                dir_path = str(file.parent.relative_to(coverage_path)).replace('/', '_')
                new_filename = f"{dir_path}-{file.name}" if dir_path else file.name
                dest_file = dest / new_filename

                dest_file.unlink(True)  # delete file if it exists
                shutil.copy2(str(file), str(dest_file))

            logger.info(f"Unitests results: {dest}")


def _get_branch_name(target_version: str) -> str:
    """
    Extract branch name from a coverage path.

    Args:
        target_version: Path like '/auto/sw_system_project/NVOS_INFRA/coverage/nvos-25-02-5000_25.02.4936-029/c_coverage_origin'

    Returns:
        str: Branch name like 'nvos-25-02-5000'

    Examples:
        '/auto/sw_system_project/NVOS_INFRA/coverage/nvos-25-02-5000_25.02.4936-029/c_coverage_origin' -> 'nvos-25-02-5000'
    """
    import re

    # Pattern to match nvos branch format like nvos-25-02-5000
    pattern = r'/.+[-_](\d+[-.]\d+[-.]\d+)'

    if grep := re.search(pattern, target_version):
        logger.debug(f'{(result := ('nvos-%s' % grep.group(1)))=!r}')
        release: str = TestToolkit.version_to_release(result)
        logger.debug(f'{release=!r}')
        return release
    else:
        raise ValueError(f"Could not extract branch name from path: {target_version}")


def _get_version_name(target_version: str) -> str:
    """
    Extract version name from a coverage path.

    Args:
        target_version: Path like '/auto/sw_system_release/nos/nvos/25.02.4936-029/amd64/dev/nvos-coverage-amd64-25.02.4936-029.bin'

    Returns:
        str: Version name like '25.02.4936-029'

    Examples:
        '/auto/sw_system_release/nos/nvos/25.02.4936-029/amd64/dev/nvos-coverage-amd64-25.02.4936-029.bin' -> '25.02.4936-029'
        '/auto/sw_system_release/nos/nvos/25.02.2000/amd64/dev/nvos-coverage-amd64-25.02.2000.bin' -> '25.02.2000'
    """
    import re

    # Pattern to match version format like 25.02.4936-029 or 25.02.2000
    pattern = r'\d+\.\d+\.\d+(?:-\d+)?'
    match = re.search(pattern, target_version)

    if match:
        return match.group(0)
    else:
        raise ValueError(f"Could not extract version name from path: {target_version}")


def _get_commit_id(target_version: str) -> str:
    version_name = _get_version_name(target_version)
    branch_name = _get_branch_name(target_version)
    return branch_name + "_" + version_name
