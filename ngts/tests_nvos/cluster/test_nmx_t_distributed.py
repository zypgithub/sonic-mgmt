import pytest
import logging
import time
import random
from datetime import datetime
from retry import retry

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts, NmxTelemetryConsts
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.ib.Ib import Ib

logger = logging.getLogger()


@pytest.mark.nmx
def test_nmx_t_distributed_basic_configuration(dut_engines, random_api):
    """
    @summary:
        Verify nmx-telemetry-agent basic configuration.

    Test flow:
        1. Check nmx-telemetry-agent state on all switches, and verify nmx-t docker is running
        2. Select a random switch to use for the rest of the test
        3. On selected switch:
            3.1 Disable nmx-telemetry-agent and verify docker is not running
            3.2 Check logs for message that nmx-telemetry-agent was disabled
            3.3 Enable nmx-telemetry-agent and verify docker is running
            3.4 Check logs for message that nmx-telemetry-agent was enabled
    """
    TestToolkit.tested_api = random_api
    fae = Fae()
    system = System()

    try:
        with allure.step("Check nmx-telemetry-agent state on all switches, and verify nmx-t docker is running"):
            for _, dut_engine in dut_engines.items():
                state = _get_nmx_telemetry_agent_state(fae, dut_engine)
                assert state == NvosConst.ENABLED, f"agent should be enabled, got {state}"
                _verify_docker_running(dut_engine, NmxTelemetryConsts.NMX_TELEMETRY_DOCKER_NAME)

        with allure.step("Select a random switch to use for the rest of the test"):
            random_switch_engine = random.choice(list(dut_engines.values()))
            allure.attach(random_switch_engine.ip)

        with allure.step("Disable nmx-telemetry-agent and verify docker is not running"):
            stop_agent_time = _set_nmx_telemetry_agent_state(fae, random_switch_engine, NvosConst.DISABLED, system)
            state = _get_nmx_telemetry_agent_state(fae, random_switch_engine)
            assert state == NvosConst.DISABLED, f"agent should be disabled, got {state}"
            _verify_docker_running(random_switch_engine, NmxTelemetryConsts.NMX_TELEMETRY_DOCKER_NAME, should_run=False)

        with allure.step(f"Check for '{NmxTelemetryConsts.NMX_T_AGENT_STOPPED_MESSAGE}' in log"):
            _check_message_in_log(random_switch_engine, system,
                                  [NmxTelemetryConsts.NMX_T_AGENT_STOPPED_MESSAGE], stop_agent_time)

        with allure.step("Enable nmx-telemetry-agent and verify docker is running"):
            start_agent_time = _set_nmx_telemetry_agent_state(fae, random_switch_engine, NvosConst.ENABLED, system)
            state = _get_nmx_telemetry_agent_state(fae, random_switch_engine)
            assert state == NvosConst.ENABLED, f"nmx-telemetry-agent should be enabled, got {state}"
            _verify_docker_running(random_switch_engine, NmxTelemetryConsts.NMX_TELEMETRY_DOCKER_NAME)

        with allure.step(f"Check for '{NmxTelemetryConsts.NMX_T_AGENT_STARTED_MESSAGE}' in log"):
            _check_message_in_log(random_switch_engine, system,
                                  [NmxTelemetryConsts.NMX_T_AGENT_STARTED_MESSAGE], start_agent_time)
    finally:
        curr_state = _get_nmx_telemetry_agent_state(fae, dut_engine)
        if curr_state != NvosConst.ENABLED:
            _set_nmx_telemetry_agent_state(fae, random_switch_engine, NvosConst.ENABLED, system)


@pytest.mark.nmx
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_nmx_t_distributed_functionality(dut_engines, random_api, setup_name):
    """
    @summary:
        Verify nmx-telemetry cluster apps status and connectivity.

    Test flow:
        1. Select a random switch to be the primary switch
        2. On selected switch:
            2.1 Configure cluster nodes, enable cluster and verify dockers
            2.2 Verify all nmx-telemetry-agents are connected and healthy
            2.3 Verify nmx-telemetry is in ok state
            2.4 Verify that main switch is able to collect telemetry from all other switches in the rack
            2.5 Cleanup - remove nodes configuration, disable cluster, re-enable nmx-telemetry-agent
    """
    TestToolkit.tested_api = random_api
    fae = Fae()
    cluster = Cluster()

    try:
        with allure.step("Select a random switch to be the primary switch"):
            primary_engine = random.choice(list(dut_engines.values()))
            allure.attach(f"Primary switch: {primary_engine.ip}")

        with allure.step("On primary switch: configure cluster nodes, enable cluster and verify dockers"):
            TestToolkit.tested_api = ApiType.NVUE
            with allure.step("Configure cluster nodes"):
                _configure_cluster_nodes(primary_engine, dut_engines, cluster)

            with allure.step("Enable cluster and verify dockers"):
                ClusterTools.start_cluster(cluster, setup_name, engine=primary_engine)
                _verify_docker_running(primary_engine, NmxTelemetryConsts.NMX_TELEMETRY_DOCKER_NAME)
            TestToolkit.tested_api = random_api

        if len(list(dut_engines.keys())) > 1:
            with allure.step("Verify all nmx-telemetry-agents are connected and healthy"):
                _verify_agents_connectivity_and_health(dut_engines, primary_engine, fae)

        with allure.step("Verify nmx-telemetry is in ok state"):
            _verify_app_status(cluster, app=ClusterConsts.NMX_TELEMETRY,
                               expected_status=NmxTelemetryConsts.STATUS_OK, engine=primary_engine)

        with allure.step("Verify that main switch is able to collect telemetry from all other switches in the rack"):
            with allure.step("Verify all ASICs have LIDs"):
                _check_lids(dut_engines)

            with allure.step("Verify telemetry collection"):
                dut_engines_copy = dut_engines.copy()
                _check_telemetry_collection(dut_engines_copy, primary_engine)

    finally:
        with allure.step("Cleanup"):
            with allure.step("On primary switch, unset cluster nodes configuration"):
                cluster.unset(op_param=SystemConsts.NODE, apply=True, dut_engine=primary_engine)

            with allure.independent_step("On primary switch, stop cluster"):
                ClusterTools.stop_cluster(cluster, engine=primary_engine)


@pytest.mark.nmx
@pytest.mark.timeout(5 * MINUTE, func_only=True)
def test_nmx_t_distributed_bad_flow(dut_engines, setup_name):
    """
    @summary:
        Check nmx-telemetry distributed bad scenarios.

    Test flow:
        1. Select two random switches - one will be the primary switch
        2. On primary switch: configure cluster nodes, enable cluster and verify dockers
        3. On Primary switch, try to disable agent while cluster is enabled - should receive an error
        4. On the secondary switch, disable nmx-telemetry-agent
        5. On primary switch, check nmx-t health
        6. Cleanup - remove nodes configuration, disable cluster, re-enable nmx-telemetry-agent
    """
    TestToolkit.tested_api = ApiType.NVUE
    fae = Fae()
    cluster = Cluster()

    try:
        with allure.step("Select two random switches - one will be the primary switch"):
            primary_engine, secondary_engine = random.sample(list(dut_engines.values()), k=2)
            allure.attach(f"Primary switch: {primary_engine.ip}")
            allure.attach(f"Secondary switch: {secondary_engine.ip}")

        with allure.step("On primary switch: configure cluster nodes, enable cluster and verify dockers"):
            with allure.step("Configure cluster nodes"):
                _configure_cluster_nodes(primary_engine, dut_engines, cluster)

            with allure.step("Enable cluster and verify dockers"):
                ClusterTools.start_cluster(cluster, setup_name, engine=primary_engine)
                _verify_docker_running(primary_engine, NmxTelemetryConsts.NMX_TELEMETRY_DOCKER_NAME)

        with allure.step("On Primary switch, try to disable agent while cluster is enabled - should receive an error"):
            _set_nmx_telemetry_agent_state(fae, primary_engine, NvosConst.DISABLED, should_succeed=False,
                                           expected_value=NmxTelemetryConsts.CHANGE_AGENT_CONFIG_ERR_MESSAGE)
            state = _get_nmx_telemetry_agent_state(fae, primary_engine)
            assert state == NvosConst.ENABLED, NmxTelemetryConsts.CHANGE_AGENT_CONFIG_ERR_MESSAGE
            _unset_nmx_telemetry_agent_state(fae, primary_engine, apply=False)

        with allure.step("On the secondary switch, disable nmx-telemetry-agent"):
            _set_nmx_telemetry_agent_state(fae, secondary_engine, NvosConst.DISABLED)
            state = _get_nmx_telemetry_agent_state(fae, secondary_engine)
            assert state == NvosConst.DISABLED, f"agent should be disabled on switch2, got {state}"

        with allure.step("On primary switch, check nmx-t health"):
            ClusterTools.wait_until_app_expected_status(cluster, app=ClusterConsts.NMX_TELEMETRY,
                                                        expected_status=NmxTelemetryConsts.STATUS_NOT_OK,
                                                        engine=primary_engine)

    finally:
        with allure.step("Cleanup"):
            with allure.step("On primary switch, unset cluster nodes configuration"):
                cluster.unset(op_param=SystemConsts.NODE, apply=True, dut_engine=primary_engine)

            with allure.independent_step("On primary switch, stop cluster"):
                ClusterTools.stop_cluster(cluster, engine=primary_engine)

            with allure.independent_step("re-enable agent on secondary switch"):
                _set_nmx_telemetry_agent_state(fae, secondary_engine, NvosConst.ENABLED)


@pytest.mark.nmx
@pytest.mark.timeout(15 * MINUTE, func_only=True)
def test_nmx_t_distributed_reboot(dut_engines, setup_name):
    """
    @summary:
        Verify nmx-t distributed functionality is retrieved after reboot.

    Test flow:
        1. Select a random switch to be the primary switch
        2. On primary switch: configure cluster nodes, enable cluster and verify dockers
        3. Select a random switch to reboot - random_dut
        4. Save config and reboot
        5. On primary switch, verify cluster state
        6. On primary switch, check nmx-t health
        7. Check nmx-telemetry-agent state on all switches, and verify nmx-t docker is running
        8. Verify all nmx-t-agents are connected
        9. Verify that main switch is able to collect telemetry from all other switches in the rack
        10. Cleanup - unset cluster nodes configuration and disable cluster
    """
    TestToolkit.tested_api = ApiType.NVUE
    fae = Fae()
    cluster = Cluster()
    system = System()

    try:
        with allure.step("Select a random switch to be the primary switch"):
            primary_engine = random.choice(list(dut_engines.values()))
            allure.attach(f"Primary switch: {primary_engine.ip}")

        with allure.step("On primary switch: configure cluster nodes, enable cluster and verify dockers"):
            with allure.step("Configure cluster nodes"):
                _configure_cluster_nodes(primary_engine, dut_engines, cluster)

            with allure.step("Enable cluster and verify dockers"):
                ClusterTools.start_cluster(cluster, setup_name, engine=primary_engine)
                _verify_docker_running(primary_engine, NmxTelemetryConsts.NMX_TELEMETRY_DOCKER_NAME)

        with allure.step("Select a random switch to reboot - random_dut"):
            random_engine = random.choice(list(dut_engines.values()))
            allure.attach(f"Selected switch to reboot: {random_engine.ip}")

        with allure.step(f"Save config and reboot: {random_engine.ip}"):
            NvueGeneralCli.save_config(random_engine)
            _reboot(random_engine, system)
            _post_reboot_check(random_engine)

        with allure.step(f"On primary switch, verify cluster state"):
            output = OutputParsingTool.parse_show_output_to_dict(cluster.show(dut_engine=primary_engine)).get_returned_value()
            state = output.get(SystemConsts.STATE, '')
            assert state == NvosConst.ENABLED, "Cluster is not enabled"

        with allure.step("On primary switch, check nmx-t health"):
            _verify_app_status(cluster, app=ClusterConsts.NMX_TELEMETRY,
                               expected_status=NmxTelemetryConsts.STATUS_OK, engine=primary_engine)

        if random_engine.ip != primary_engine.ip:
            with allure.step("On primary switch, restart nmx-controller app"):
                _restart_app(cluster, ClusterConsts.NMX_CONTROLLER, primary_engine)

        if len(list(dut_engines.keys())) > 1:
            with allure.step("Check nmx-telemetry-agent state on all switches, and verify nmx-t docker is running"):
                for _, dut_engine in dut_engines.items():
                    state = _get_nmx_telemetry_agent_state(fae, dut_engine)
                    assert state == NvosConst.ENABLED, f"agent should be enabled, got {state}"
                    _verify_docker_running(dut_engine, NmxTelemetryConsts.NMX_TELEMETRY_DOCKER_NAME)

            with allure.step("Verify all nmx-t-agents are connected"):
                _verify_agents_connectivity_and_health(dut_engines, primary_engine, fae)

        with allure.step("Verify that main switch is able to collect telemetry from all switches in rack"):
            with allure.step("Verify all ASICs have LIDs"):
                _check_lids(dut_engines)

            with allure.step("Verify telemetry collection"):
                dut_engines_copy = dut_engines.copy()
                _check_telemetry_collection(dut_engines_copy, primary_engine)

    finally:
        with allure.step("Cleanup"):
            with allure.step("On primary switch, unset cluster nodes configuration"):
                cluster.unset(op_param=SystemConsts.NODE, apply=True, dut_engine=primary_engine)

            with allure.independent_step("On primary switch, stop cluster"):
                ClusterTools.stop_cluster(cluster, engine=primary_engine)


def _configure_cluster_nodes(primary_engine, dut_engines, cluster):
    """Configure cluster nodes."""
    for _, dut_engine in dut_engines.items():
        cluster.set(op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER, op_param_value=dut_engine.ip,
                    dut_engine=primary_engine)


def _get_nmx_telemetry_agent_state(fae, dut_engine):
    """Get the nmx-telemetry-agent state from a switch."""
    output = OutputParsingTool.parse_show_output_to_dict(
        fae.nmx_telemetry_agent.show(dut_engine=dut_engine)
    ).verify_result()
    return output[SystemConsts.STATE]


def _set_nmx_telemetry_agent_state(fae, dut_engine, state, system_obj=None, apply=True, should_succeed=True, expected_value=''):
    """Set the nmx-telemetry-agent state on a switch."""
    date_format = "%Y-%m-%d %H:%M:%S"
    start_time = None
    if system_obj:
        start_time = datetime.strptime(ClockTools.get_local_time_from_show_system_date_time_output(system_obj.datetime.show()),
                                       date_format)
    fae.nmx_telemetry_agent.set(
        op_param_name=SystemConsts.STATE,
        op_param_value=state,
        apply=apply,
        dut_engine=dut_engine
    ).verify_result(should_succeed, expected_value)
    return start_time


def _unset_nmx_telemetry_agent_state(fae, dut_engine, apply=True, should_succeed=True, expected_value=''):
    """Unset the nmx-telemetry-agent state on a switch."""
    fae.nmx_telemetry_agent.unset(
        op_param=SystemConsts.STATE,
        apply=apply,
        dut_engine=dut_engine
    ).verify_result(should_succeed, expected_value)


@retry(Exception, tries=15, delay=5)
def _verify_docker_running(engine, docker_name, should_run=True):
    """Verify if a docker container is running or not."""
    output = engine.run_cmd(f"sudo docker ps | grep {docker_name} | wc -l")
    is_running = True if str(output) == '1' else False
    if should_run:
        if not is_running:
            raise Exception(f"Docker {docker_name} is not running")
        else:
            return True
    else:
        if is_running:
            raise Exception(f"Docker {docker_name} is still running")
        else:
            return True


def _verify_agents_connectivity_and_health(dut_engines, primary_engine, fae):
    """Verify all agents are connected to the main switch and are healthy."""
    agents_dict = None
    for _ in range(15):
        output = OutputParsingTool.parse_show_output_to_dict(fae.cluster.apps.app_name[ClusterConsts.NMX_TELEMETRY]
                                                             .show(dut_engine=primary_engine)).get_returned_value()
        agents_dict = output.get(NmxTelemetryConsts.AGENTS, None)
        if agents_dict is None:
            logger.info("Retrying in 5 seconds...")
            time.sleep(5)
        else:
            break
    assert agents_dict, "nmx telemetry has no agents"

    with allure.independent_step("Verify all agents are connected"):
        ips_list = list(agents_dict.keys())
        missing_switches = []
        for _, dut_engine in dut_engines.items():
            if dut_engine.ip == primary_engine.ip:
                continue
            if dut_engine.ip not in ips_list:
                missing_switches.append(dut_engine.ip)
        assert missing_switches == [], f"Not all switches are connected. Missing switches: {missing_switches}"

    with allure.independent_step("Verify all agents are healthy"):
        unhealthy_switches = []
        for agent_ip, agent_data in agents_dict.items():
            if agent_data['status'] != NmxTelemetryConsts.STATUS_HEALTHY:
                unhealthy_switches.append(agent_ip)
        assert unhealthy_switches == [], f"Not all switches are in healthy state. Unhealthy switches: {unhealthy_switches}"


def _reboot(engine, system):
    """Run reboot command and verify system is unreachable."""
    system.reboot.action_reboot(engine=engine,
                                should_wait_till_system_ready=False)  # this value is false because of simx limitations
    with allure.step("Ping system until down"):
        ping_till_alive(should_be_alive=False, destination_host=engine.ip)


def _post_reboot_check(engine):
    """Verify system is ready."""
    with allure.step("Ping system until alive"):
        ping_till_alive(should_be_alive=True, destination_host=engine.ip)

    with allure.step("Wait until ssh is ready"):
        cli_unavailable_msg = "NVOS CLI is unavailable"
        out = engine.run_cmd('nv show system version')
        while (cli_unavailable_msg in out) or (not out.strip()):
            logger.warning("CLI is not up. Try again after 5 seconds...")
            time.sleep(5)
            out = engine.run_cmd('nv show system version')


@retry(Exception, tries=7, delay=15)
def _check_lids(dut_engines):
    """Verify all ASICs have LIDs allocated to them."""
    ib = Ib()
    for _, dut_engine in dut_engines.items():
        out = OutputParsingTool.parse_show_output_to_dict(ib.device.show(dut_engine=dut_engine)).get_returned_value()
        for _, asic_data in out.items():
            if "lid" in asic_data:
                assert asic_data["lid"] != 0, "Some ASICs do not have LIDs allocated to them."


@retry(Exception, tries=30, delay=5)
def _check_telemetry_collection(dut_engines, primary_engine):
    """Verify that main switch is able to collect telemetry from all other switches in the rack."""
    ip_list = []
    for engine_id, dut_engine in dut_engines.items():
        dut_host_name = dut_engine.run_cmd('hostname')
        out = primary_engine.run_cmd(f"curl -sS http://0.0.0.0:9352/csv/xcset/nvlink_domain_telemetry | grep {dut_host_name}")
        if out:
            logger.info(f"Telemetry found for {dut_engine.ip}.")
            del dut_engines[engine_id]
        if not out:
            ip_list.append(dut_engine.ip)
    if ip_list:
        raise Exception(f"Telemetry from these switches was not found: {ip_list}")


@retry(Exception, tries=5, delay=10)
def _check_message_in_log(engine, system, msg_list, start_time):
    system.log.verify_expected_logs_by_time(msg_list, engine, only_latest_log=False, start_time=start_time)


@retry(Exception, tries=6, delay=20)
def _verify_app_status(cluster, app, expected_status, engine):
    output = OutputParsingTool.parse_show_output_to_dict(
        cluster.apps.show(dut_engine=engine)).get_returned_value()
    app_status = output[app]['status']
    assert app_status == expected_status, f"App {app} status is {app_status} instead of {expected_status}"


def _restart_app(cluster, app, engine):
    """Stop and start a cluster app."""
    with allure.step(f"Stop app {app}"):
        cluster.apps.app_name[app].action_stop_cluster_app(engine=engine)
    with allure.step(f"Start app {app}"):
        cluster.apps.app_name[app].action_start_cluster_app(engine=engine)
