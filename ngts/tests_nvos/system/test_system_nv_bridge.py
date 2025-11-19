import pytest
import random
import logging
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tests.nightly.dynamic_port_breakout.conftest import dut_engine
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts, OutputFormat
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_constants.constants_nvos import HealthConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.security.password_hardening.PwhConsts import PwhConsts
from ngts.nvos_constants.constants_nvos import ApiType
from retry.api import retry_call


logger = logging.getLogger(__name__)


@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_default_fields_values(engines, devices, nv_command, test_api):
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
    TestToolkit.tested_api = test_api
    system = nv_command.system
    nv_bridge = nv_command.system.nv_bridge
    acl = nv_command.acl

    with allure.step("Check default values for cpu-debug-config output"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=engines.dut)

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
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, heart_beat=SystemConsts.NV_BRIDGE_HEALTH_NOT_OK, connections=SystemConsts.NV_BRIDGE_NODE_IP, local_host=True, dut_engine=engines.dut)

        with allure.step("Check system logs"):
            show_output = system.log.file.show_log(param=SystemConsts.NV_BRIDGE_GREP)
            ValidationTool.verify_expected_output(show_output, SystemConsts.NV_BRIDGE).verify_result()

    # with allure.step("Verify default nv-bridge acl"):
    #     output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(acl.show()).get_returned_value()
    #     TBD check acl on new version

    with allure.step("Unset node"):
        cluster.unset(apply=True)

        with allure.step("Verify output after unset node"):
            _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=engines.dut)


@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_functional(engines, devices, nv_command, dut_engines, test_api):
    """
    Test flow:
        1. Start Cluster
        2. Configure NV bridge
        3. Verify NV bridge output
        4. Send MAD and check no errors
        5. Unset Cluster
    """
    pytest.skip("Test will be enabled after next integration")
    TestToolkit.tested_api = test_api
    dut, dut2 = random.sample(list(dut_engines.values()), k=2)
    system = nv_command.system
    nv_bridge = nv_command.system.nv_bridge

    with allure.step('Start cluster'):
        cluster = Cluster()

    with allure.step("Check default values for nv-bridge output"):
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value=dut.ip,
                    apply=True, dut_engine=dut)
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value=dut2.ip,
                    apply=True, dut_engine=dut)

    with allure.step("Verify output after configure nv bridge"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=dut)
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=dut2)

    with allure.step("Send MAD and check it's successfully"):
        _send_mad_verify_no_errors(dut)

    with allure.step("Unset node"):
        cluster.unset(apply=True, dut_engine=dut)


@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_negative(engines, devices, nv_command, test_api):
    """
    Test flow:
        1. Start Cluster
        2. Configure NV bridge without ip
        3. Configure NV bridge with not nv bridge cluster ip
        4. Unset Cluster
    """

    pytest.skip("Test will be enabled after next integration")
    TestToolkit.tested_api = test_api
    system = nv_command.system
    nv_bridge = nv_command.system.nv_bridge

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
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value='', expected_str=PwhConsts.ERR_INCOMPLETE_SET_CMD)

    with allure.step("Set cluster negative ip"):
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, apply=True, op_param_value=SystemConsts.NV_BRIDGE_NODE_NEGATIVE_IP)

    with allure.step("Verify output after configure wrong nv bridge node"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, no_connection=True, dut_engine=engines.dut)

    with allure.step("Check system status is OK"):
        system.validate_health_status(HealthConsts.OK)

    with allure.step("Unset node"):
        cluster.unset(apply=True)


@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.nv_bridge
@pytest.mark.system
def test_system_nv_bridge_simulate_issue(engines, devices, nv_command, dut_engines, test_api):
    """
    Test flow:
        1. Configure Cluster
        2. Configure NV-bridge
        3. Check NV-bridge configured
        4. Restart NV-bridge docker
        5. Check NV-bridge connection restored after restart
        6. Unset Cluster
    """
    pytest.skip("Test will be enabled after next integration")
    TestToolkit.tested_api = test_api
    dut, dut2 = random.sample(list(dut_engines.values()), k=2)

    system = nv_command.system
    nv_bridge = nv_command.system.nv_bridge

    with allure.step('Start cluster'):
        cluster = Cluster()
        with allure.step("Start cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=OutputFormat.json, dut_engine=dut),
                output_format=OutputFormat.json).get_returned_value()

            if output[SystemConsts.STATE] == SystemConsts.CLUSTER_STATE_DISABLED:
                cluster.set(op_param_name=SystemConsts.STATE, op_param_value=SystemConsts.CLUSTER_STATE_ENABLED, apply=True, dut_engine=dut)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state=SystemConsts.CLUSTER_STATE_ENABLED,
                                                                 nmx_c_expected_state=SystemConsts.CLUSTER_APP_STATE_UP)

    with allure.step("Check default values for nv-bridge output"):
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value=dut.ip,
                    apply=True, dut_engine=dut)
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value=dut2.ip,
                    apply=True, dut_engine=dut)

    with allure.step("Verify output after configure nv bridge"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=dut, connections=True, active=SystemConsts.NV_BRIDGE_CLIENT_ACTIVE, client_address=dut.ip, client_id=dut.ip, server_address=dut.ip)
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=dut2, connections=True, active=SystemConsts.NV_BRIDGE_CLIENT_ACTIVE, client_address=dut.ip, client_id=dut2.ip, server_address=dut2.ip)

    with allure.step("Simulate nv-bridge docker issue"):
        _restart_nv_bridge_container(dut2)

    with allure.step("Check system status is OK"):
        system.validate_health_status(HealthConsts.NOT_OK, dut_engine=dut2)
        retry_call(system.validate_health_status, [HealthConsts.OK, True, dut], exceptions=AssertionError, tries=2, delay=3)

    with allure.step("Verify output after configure nv bridge"):
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=dut,
                                 connections=True, active=SystemConsts.NV_BRIDGE_CLIENT_ACTIVE,
                                 client_address=engines.dut.ip, client_id=engines.dut.ip, server_address=dut.ip)
        _verify_nv_bridge_output(nv_bridge, state=SystemConsts.NV_BRIDGE_ENABLED, dut_engine=dut2,
                                 connections=True, active=SystemConsts.NV_BRIDGE_CLIENT_ACTIVE,
                                 client_address=dut.ip, client_id=dut2.ip,
                                 server_address=dut2.ip)

    with allure.step("Unset node"):
        cluster.unset(apply=True, dut_engine=dut)


def _verify_nv_bridge_output(nv_bridge, state=None, health=None, health_reason=None, connections=None, no_connection=None, heart_beat=None, dut_engine=None, active=None, client_address=None, client_id=None, server_address=None, local_host=None):
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_bridge.show(dut_engine=dut_engine)).get_returned_value()
    if state:
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NV_BRIDGE_STATE, state).verify_result()
    if health:
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NV_BRIDGE_HEALTH, health).verify_result()
    if health_reason:
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NV_BRIDGE_HEALTH_REASON, health_reason).verify_result()
    if heart_beat:
        ValidationTool.verify_field_value_in_output(output_dictionary['connections']['1'], SystemConsts.NV_BRIDGE_HEART_BEAT, heart_beat).verify_result()
    if connections:
        if active and client_address and client_id and server_address:
            assert active in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_CLIENT_ACTIVE], f'Connection is not {active}'
            assert client_address in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_CLIENT_ADDRESS], f'Client-address {client_address} not in output'
            assert client_id in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_CLIENT_ID], f'Client-id {client_id} not in server address'
            assert server_address in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_SERVER_ADDRESS], f'Server-address {server_address} not in output'
        if local_host:
            assert connections in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_CLIENT_ADDRESS], f'Node ip {connections} not in client address'
            assert connections in output_dictionary['connections']['1'][SystemConsts.NV_BRIDGE_SERVER_ADDRESS], f'Node ip {connections} not in server address'
    if no_connection:
        assert output_dictionary['connections'] == {}, 'Connections not empty'


def _send_mad_verify_no_errors(dut):
    dut.run_cmd('docker exec -it nmx-c-job.nmx-c-group.nmxc bash')
    dut.run_cmd('apt install -y procps vim openssh-client infiniband-diags less iputils-ping')
    dut.run_cmd('export NV_BRIDGE_CLIENT_MODE=bridge NV_BRIDGE_LOG_LEVEL=info LD_PRELOAD=/usr/local/nv-bridge/lib/libnv_bridge.so')
    output = dut.run_cmd('smpquery ni -L 1 ')
    assert 'Connection timed out' not in output, 'MAD send successfully'
    dut.run_cmd('exit')


def _restart_nv_bridge_container(dut):
    dut.run_cmd('sudo systemctl restart nv-bridge.service')
