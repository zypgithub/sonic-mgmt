import logging
import pytest

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import OutputFormat, ApiType
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import ChassisLocationConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit


logger = logging.getLogger()

# Error message constants for tray maintenance state tests
ERR_NMX_RESOURCE_BAD = "NMX_ST_RESOURCE_BAD"
ERR_INVALID_TRAY_ID = "is not a 'sdn-tray-id'"


@pytest.fixture(scope="module", autouse=True)
def setup_cluster_for_single_aperture_tests(setup_name, standalone_system):
    """
    Setup fixture to enable cluster and ensure NMX-C is running.
    Skip tests if system is standalone (requires multi-chassis setup).
    Teardown: Disable cluster after all tests in module complete.
    """
    # Skip if standalone system
    if standalone_system:
        pytest.skip("Single aperture support tests require non-standalone system (mini-oberon setup)")

    cluster = Cluster()
    output_format = OutputFormat.json

    with allure.step("Enable cluster and wait for NMX-C to be ready"):
        ClusterTools.start_cluster(cluster, setup_name, output_format)
        ClusterTools.wait_until_app_expected_status(cluster, 'nmx-controller', 'ok')

    yield

    with allure.step("Disable cluster after tests"):
        ClusterTools.stop_cluster(cluster, output_format)


@pytest.fixture(scope="module")
def get_chassis_info():
    """
    Fixture to get chassis serial number and slot ID.
    First tries to get from 'nv show platform chassis-location'.
    If not available, generates chassis_mapping config and extracts from there.

    Returns:
        dict: {
            'slot-number': str,
            'chassis-sn': str or None,
        }
    """
    chassis_info = {
        ChassisLocationConsts.SLOT_NUM: None,
        ChassisLocationConsts.CHAS_SN: None,
    }

    with allure.step("Get chassis location from 'nv show platform chassis-location'"):
        platform = Platform()
        chassis_location_output = OutputParsingTool.parse_show_output_to_dict(
            platform.chassis_location.show()).get_returned_value()
        chassis_info[ChassisLocationConsts.SLOT_NUM] = chassis_location_output.get(ChassisLocationConsts.SLOT_NUM)
        chassis_info[ChassisLocationConsts.CHAS_SN] = chassis_location_output.get(ChassisLocationConsts.CHAS_SN)
    return chassis_info


@pytest.mark.nmx
@pytest.mark.timeout(5 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_update_maintenance_state_up(test_api, get_chassis_info):
    """
    Test Objective:
    Verify that a switch tray on the local chassis can be brought back to maintenance-state up using the
    simplified command syntax (without chassis-sn), and that a tray on a remote chassis can be brought up
    using the full command syntax with explicit chassis serial number.

    Precondition:
    - Cluster state enabled and NMX-C is running
    - Non standalone system
    """
    TestToolkit.tested_api = test_api
    slot_number = get_chassis_info[ChassisLocationConsts.SLOT_NUM]
    chassis_sn = get_chassis_info[ChassisLocationConsts.CHAS_SN]

    with allure.step("Create Sdn object"):
        sdn = Sdn()

    with allure.step("Run 'nv action update sdn trays <chassis-sn>.<slot-number> maintenance-state up' for remote chassis"):
        remote_tray_id = f"{chassis_sn}.{slot_number}"
        sdn.trays.action_update_maintenance_state(tray_id=remote_tray_id, maintenance_state='up').verify_result()

    with allure.step("Run 'nv action update sdn trays <slot-number> maintenance-state up' for local chassis"):
        sdn.trays.action_update_maintenance_state(tray_id=slot_number, maintenance_state='up').verify_result()


@pytest.mark.nmx
@pytest.mark.timeout(5 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_error_flow_single_aperture_support(test_api, get_chassis_info):
    """
    Test Objective:
    Verify proper error handling for invalid slot ID and / or invalid chassis-sn

    Precondition:
    - Cluster state enabled and NMX-C is running
    - Non standalone system
    """
    TestToolkit.tested_api = test_api
    chassis_sn = get_chassis_info[ChassisLocationConsts.CHAS_SN]
    output_format = OutputFormat.json

    with allure.step("Create Cluster and Sdn objects"):
        cluster = Cluster()
        sdn = Sdn()

    with allure.step("Verify cluster state is enabled and NMX-C is running"):
        cluster_output = OutputParsingTool.parse_show_output_to_dict(
            cluster.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert cluster_output['state'] == 'enabled', f"Cluster state is {cluster_output['state']}, expected enabled"

    with allure.step("Verify bad flow commands for single aperture support"):
        with allure.independent_step("Attempt with non-existent slot (999)"):
            sdn.trays.action_update_maintenance_state(tray_id='999').verify_result(should_succeed=False, expected_value=ERR_NMX_RESOURCE_BAD)

        with allure.independent_step("Attempt with negative slot (-1)"):
            sdn.trays.action_update_maintenance_state(tray_id='-1').verify_result(should_succeed=False, expected_value=ERR_INVALID_TRAY_ID)

        with allure.independent_step(f"Attempt with fake slot number ({chassis_sn}.aaa)"):
            sdn.trays.action_update_maintenance_state(tray_id=f"{chassis_sn}.aaa").verify_result(should_succeed=False, expected_value=ERR_INVALID_TRAY_ID)

        with allure.independent_step("Attempt with chassis SN without slot"):
            sdn.trays.action_update_maintenance_state(tray_id=chassis_sn).verify_result(should_succeed=False, expected_value=ERR_NMX_RESOURCE_BAD)

        with allure.independent_step("Attempt with a invalid format of the slot number (.1)"):
            sdn.trays.action_update_maintenance_state(tray_id='.1').verify_result(should_succeed=False, expected_value=ERR_INVALID_TRAY_ID)

    with allure.step("Verify NMX-C is still running after all error tests"):
        cluster_output = OutputParsingTool.parse_show_output_to_dict(
            cluster.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert cluster_output['state'] == 'enabled', \
            f"Cluster state changed to {cluster_output['state']} after error tests, should remain enabled"
