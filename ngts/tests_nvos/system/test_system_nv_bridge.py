import pytest
import logging
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts, OutputFormat
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.nmx.Cluster import Cluster


logger = logging.getLogger(__name__)


@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_default_fields_values(engines, devices, nv_command):
    """
    Test flow:
        1. Check default output
        2. Enable cluster
        3. Set cluster node
        4. Check nv-bridge enable
        5. Check system logs
        6. Check acl
        7. Unset cluster
        8. Check output after unset
    """
    system = nv_command.system
    nv_bridge = nv_command.system.nv_bridge
    acl = nv_command.acl

    with allure.step("Check default values for cpu-debug-config output"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED)

    with allure.step('Start cluster'):
        cluster = Cluster()

        with allure.step("Start cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=OutputFormat.json),
                output_format=OutputFormat.json).get_returned_value()

            if output[SystemConsts.STATE] == SystemConsts.CLUSTER_STATE_DISABLED:
                cluster.set(op_param_name=SystemConsts.STATE, op_param_value=SystemConsts.CLUSTER_STATE_ENABLED, apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state=SystemConsts.CLUSTER_STATE_ENABLED,
                                                                 nmx_c_expected_state=SystemConsts.CLUSTER_APP_STATE_UP)

    with allure.step("Set cluster node"):
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value=SystemConsts.NV_BRIDGE_NODE_IP, apply=True)

    with allure.step("Verify nv bridge output"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, heart_beat=SystemConsts.NV_BRIDGE_HEALTH_NOT_OK, connections=SystemConsts.NV_BRIDGE_NODE_IP)

        with allure.step("Check system logs"):
            show_output = system.log.file.show_log(param=SystemConsts.NV_BRIDGE_GREP)
            ValidationTool.verify_expected_output(show_output, SystemConsts.NV_BRIDGE).verify_result()

    # with allure.step("Verify default nv-bridge acl"):
    #     output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(acl.show()).get_returned_value()
    #     TBD check acl on new version

    with allure.step("Unset node"):
        cluster.unset(apply=True)

        with allure.step("Verify output after unset node"):
            _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED)


@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_functional(engines, devices, nv_command):
    """
    Test flow:
        1.
        2.
        3.
        4.
        5.
        6.
    """
    pytest.skip("Test will be implemented after next integration")
    # TBD


@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_negative(engines, devices, nv_command):
    """
    Test flow:
        1.
        2.
        3.
        4.
        5.
        6.
    """
    pytest.skip("Test will be implemented after next integration")
    # TBD

    system = nv_command.system
    nv_bridge = nv_command.system.nv_bridge

    with allure.step("Check default values for cpu-debug-config output"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_DISABLED)

    with allure.step('Start cluster'):
        cluster = Cluster()

        with allure.step("Start cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=OutputFormat.json),
                output_format=OutputFormat.json).get_returned_value()

            if output[SystemConsts.STATE] == SystemConsts.CLUSTER_STATE_DISABLED:
                cluster.set(op_param_name=SystemConsts.STATE, op_param_value=SystemConsts.CLUSTER_STATE_ENABLED, apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state=SystemConsts.CLUSTER_STATE_ENABLED,
                                                                 nmx_c_expected_state=SystemConsts.CLUSTER_APP_STATE_UP)

    with allure.step("Set cluster node without ip"):
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value='', apply=True, expected_str='specify cluster node')


@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_simulate_issue(engines, devices, nv_command):
    """
    Test flow:
        1.
        2.
        3.
        4.
        5.
        6.
    """
    pytest.skip("Test will be implemented after next integration")
    # TBD


def _verify_nv_bridge_output(nv_bridge, state=None, health=None, health_reason=None, connections=None, heart_beat=None):
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_bridge.show()).get_returned_value()
    if state:
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NV_BRIDGE_STATE, state).verify_result()
    if health:
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NV_BRIDGE_HEALTH, health).verify_result()
    if health_reason:
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NV_BRIDGE_HEALTH_REASON, health_reason).verify_result()
    if heart_beat:
        ValidationTool.verify_field_value_in_output(output_dictionary['connections']['1'], SystemConsts.NV_BRIDGE_HEART_BEAT, heart_beat).verify_result()
    if connections:
        assert connections in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_CLIENT_ADDRESS], f'Node ip {connections} not in client address'
        assert connections in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_SERVER_ADDRESS], f'Node ip {connections} not in server address'
