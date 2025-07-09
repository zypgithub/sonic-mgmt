import logging
import pytest

from ngts.nvos_constants.constants_nvos import OutputFormat, ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.ansible_playbooks_tool import AnsiblePlaybooksTool
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
@pytest.mark.timeout(45 * MINUTE, func_only=True)
def test_cluster_traffic_basic_test(engines, devices, test_api, has_loopbox, standalone_system, setup_name, ansible_inventory_file):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    if standalone_system:
        pytest.skip(f"Skipping test - Standalone system, traffic not supported.")
    try:
        with allure.step("Enable Cluster"):
            cluster = Cluster()
            logger.info("Setting cluster state to enabled")
            ClusterTools.start_cluster(cluster, setup_name, output_format)

        with allure.step("Running run_mpi_basic_test"):
            playbook = "run_mpi_basic_test.yml"
            traffic_status = AnsiblePlaybooksTool.run_playbook_and_check_result(ansible_inventory_file,
                                                                                playbook,
                                                                                '-e "nvflash_path=nvflash/nvflash_eng" ' +
                                                                                "--skip-tags 'check_status'")
            assert traffic_status, f"Playbook {playbook} failed. Please check test log to see what step failed"

    finally:
        pass


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
@pytest.mark.timeout(45 * MINUTE, func_only=True)
def test_cluster_traffic_all_test(engines, devices, test_api, has_loopbox, standalone_system, setup_name,
                                  ansible_inventory_file):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    if standalone_system:
        pytest.skip(f"Skipping test - Standalone system, traffic not supported.")
    try:
        with allure.step("Enable Cluster"):
            cluster = Cluster()
            logger.info("Setting cluster state to enabled")
            ClusterTools.start_cluster(cluster, setup_name, output_format)

        with allure.step("Running run_mpi_all_test"):
            playbook = "run_mpi_all_test.yml"
            traffic_status = AnsiblePlaybooksTool.run_playbook_and_check_result(ansible_inventory_file,
                                                                                playbook,
                                                                                '-e "nvflash_path=nvflash/nvflash_eng" ' +
                                                                                "--skip-tags 'check_status'")
            assert traffic_status, f"Playbook {playbook} failed. Please check test log to see what step failed"

    finally:
        pass
