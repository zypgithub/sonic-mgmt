import pytest
import logging

from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_constants.constants_nvos import OutputFormat, ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.nvos_build
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_reboot_command(engines, devices, test_name, test_api):
    """
    Test flow:
        1. Enabled Cluster
        2. run nv action reboot system
        3. After reboot, make sure cluster is still enabled.
        4. cleanup - disabled cluster.
    """
    system = System(None)
    cluster = Cluster()
    output_format = OutputFormat.json
    TestToolkit.tested_api = test_api
    try:
        logger.info("Setting cluster state to enabled")
        ClusterTools.start_cluster(cluster, output_format)
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

        with allure.step('Run nv action reboot system'):
            result_obj, duration = OperationTime.save_duration('reboot', '', test_name, system.reboot.action_reboot)

        with allure.step("Check Cluster status and cluster apps after reboot"):
            ClusterTools.validate_cluster_enabled(cluster)
            ClusterTools.verify_apps_running(engines, devices, cluster, 'ok', output_format)

        OperationTime.verify_operation_time(duration, devices.dut.reboot_type).verify_result()
    finally:
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state()
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
