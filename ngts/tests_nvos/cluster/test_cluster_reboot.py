import pytest
import logging

from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.nvos_constants.constants_nvos import OutputFormat, ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts

logger = logging.getLogger()


@disabled_access_ports
@pytest.mark.system
@pytest.mark.nvos_build
@pytest.mark.nmx
@pytest.mark.timeout(35 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_reboot_command(engines, devices, test_name, test_api, has_loopbox, standalone_system, setup_name):
    """
    Test flow:
        1. Enabled Cluster
        2. run nv action reboot system
        3. After reboot, make sure cluster is still enabled.
        4. cleanup - disabled cluster.
    """
    system = System(None)
    cluster = Cluster()
    sdn = Sdn()
    output_format = OutputFormat.json
    TestToolkit.tested_api = test_api
    try:
        logger.info("Setting cluster state to enabled")
        ClusterTools.start_cluster(cluster, setup_name, output_format)
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

        if not standalone_system:
            with allure.step("Creating Empty partition, then adding a GPU to it with no-reroute option"):
                logger.info("After reboot, empty partition should persist, but GPU added to it with no-reroute should be deleted")
                uuid, location, _, partition_to_remove_from = ClusterTools.create_empty_partition_and_add_gpu(sdn, 'no-reroute')

        with allure.step('Run nv action reboot system'):
            result_obj, duration = OperationTime.save_duration('reboot', '', test_name, system.reboot.action_reboot)

        with allure.step("Check Cluster status and cluster apps after reboot"):
            ClusterTools.validate_cluster_enabled(cluster)
            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled',
                                                             nmx_c_expected_state='up')
            ClusterTools.verify_apps_running(engines, devices, cluster, 'ok', output_format, standalone_system, has_loopbox)

        OperationTime.verify_operation_time(duration, devices.dut.reboot_type).verify_result()

        if not standalone_system:
            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            assert ClusterConsts.EMPTY_PARTITION_ID in output.keys(), f'Partition {ClusterConsts.EMPTY_PARTITION_ID} was deleted, while its expected to be kept'
            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[ClusterConsts.EMPTY_PARTITION_ID].show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            uuids, locations = ClusterTools.uuid_location_in_partition(sdn, partition_to_remove_from)
            assert uuid not in uuids, f"uuid {uuid} was not deleted from {partition_to_remove_from} although it was removed with no-reroute, See current uuids: {uuids}"
            assert location not in locations, f"uuid {uuid} was not deleted from {partition_to_remove_from} although it was removed with no-reroute. See current locations: {locations}"

    finally:
        if not standalone_system:
            with allure.step("Running sdn factory reset"):
                sdn.factory_default.action_reset(param='force')
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
