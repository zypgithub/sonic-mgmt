import logging
import os
import shutil
import allure
import pytest

from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.scripts.code_coverage.code_coverage_consts import NvosConsts, SharedConsts
from ngts.scripts.code_coverage.coverage_helpers import _get_coverage_path_from_target_version, get_dest_path
from ngts.nvos_tools.infra.JenkinsTool import JenkinsQueryBuilder, JenkinsTool


python_job_name = "NVOS_Python_upload_results_to_sonar"
cpp_job_name = "NVOS_C_upload_results_to_sonar"


@pytest.fixture(scope='module')
def results_path(topology_obj, engines):
    with allure.step("Create device object if needed"):
        if not TestToolkit.devices:
            devices = DeviceFactory.create_devices_object(topology_obj)
            TestToolkit.update_devices(devices)

    with allure.step("Create coverage report path"):
        return get_dest_path(engines.dut, NvosConsts.DEST_PATH)


@pytest.mark.disable_loganalyzer
@allure.title('Upload results to sonar')
def test_upload_results_to_sonar(target_version, results_path):
    try:
        with allure.step("Get coverage results paths, branch name and commit id"):
            python_results_path = results_path + SharedConsts.PYTHON_DIR
            logging.info(f"python results path: {python_results_path}")

            cpp_results_path = results_path + SharedConsts.C_DIR
            logging.info(f"cpp results path: {cpp_results_path}")

            branch_name = _get_branch_name(python_results_path)
            logging.info(f"branch name: {branch_name}")

            commit_id = _get_commit_id(python_results_path)
            logging.info(f"commit id: {commit_id}")

        client = JenkinsTool(project_job_path=SharedConsts.JENKINS_SONAR_PROJECT_PATH)
        general_job_params = (
            JenkinsQueryBuilder()
            .branch(branch_name)
            .commit_id(commit_id)
            .version(1)
            .mailing_list(["yport"])
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
def test_copy_unitests_results(engines, target_version, topology_obj, results_path):
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
            coverage_path = _get_coverage_path_from_target_version(target_version)
            logging.info(f"coverage path: {coverage_path}")

        with allure.step("Check if destination path exists"):
            with allure.step("Create device object if needed"):
                devices = DeviceFactory.create_devices_object(topology_obj)
                TestToolkit.update_devices(devices)
            dest = results_path + SharedConsts.PYTHON_DIR
            logging.info(f"destination path: {dest}")

        with allure.step("Copy unitests results"):
            xml_files = []
            for root, _, files in os.walk(coverage_path):
                for file in files:
                    if file.endswith('.xml'):
                        xml_files.append(os.path.join(root, file))

            for xml_file in xml_files:
                rel_path = os.path.relpath(xml_file, coverage_path)
                dir_path = os.path.dirname(rel_path).replace('/', '_')
                filename = os.path.basename(xml_file)

                new_filename = f"{dir_path}-{filename}" if dir_path else filename
                dest_file = os.path.join(dest, new_filename)

                shutil.copy2(xml_file, dest_file)

            logging.info(f"Unitests results: {dest}")


def _get_branch_name(target_version):
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
    pattern = r'nvos-\d+-\d+-\d+'
    match = re.search(pattern, target_version)

    if match:
        return match.group(0)
    else:
        raise ValueError(f"Could not extract branch name from path: {target_version}")


def _get_version_name(target_version):
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


def _get_commit_id(target_version):
    version_name = _get_version_name(target_version)
    branch_name = _get_branch_name(target_version)
    return branch_name + "_" + version_name
