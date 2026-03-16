import json
import random
import re

import pytest
import logging
from retry import retry
from retry.api import retry_call

from ngts.nvos_constants.constants_nvos import ApiType, PeerPortConsts, LogComponentsConsts, HealthConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.nmx.PeerPort import PeerPort
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, ClusterSimulation
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.fixture(scope="module")
def start_cluster_and_sdn_fm_config(engines, setup_name):
    cluster = Cluster()
    topology_value = "vr_nvl8r1_c2g4_rtf_topology"
    try:
        with allure.step("Enable cluster"):
            ClusterTools.start_cluster(cluster, setup_name)

        with allure.step("Config fm config"):
            ClusterSimulation.config_fm_config(engines.dut, topology_value=topology_value)

        with allure.step("Wait for nmx-controller to be in ok status"):
            ClusterTools.wait_until_app_expected_status(cluster, ClusterConsts.NMX_CONTROLLER, "ok")

        yield

    finally:
        with allure.step("Reset sdn fm config"):

            with allure.step("Disable cluster"):
                ClusterTools.stop_cluster(cluster)

            with allure.step("Reset sdn factory default"):
                Sdn().factory_default.action_reset(param='force')


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_peer_port_show(engines, test_api):

    TestToolkit.tested_api = test_api
    peer_port = PeerPort(parent_obj=None)

    with allure.step(f"Validate 'nv show peer-port' command"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port.show()).verify_result()

    with allure.step(f"Get list of peer ports"):
        peer_ports = peer_port.get_list_of_ports()
        list_of_ports = [port.peer_port_name for port in peer_ports]
        logger.info(f"List of Peer Ports: {list_of_ports}")

    with allure.step(f"Validate show commands for all Peer Ports"):
        for port in peer_ports:
            with allure.step(f"Validate show commands for Peer Port {port.peer_port_name}"):
                helper_validate_peer_port_show(port)


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_peer_port_fae_show(engines, test_api):

    TestToolkit.tested_api = test_api
    fae = Fae()
    with allure.step(f"Validate 'nv show fae peer-port' command"):
        OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_peer_port_state_fae_set(engines, test_api):

    TestToolkit.tested_api = test_api
    fae = Fae()
    try:
        helper_fae_peer_port_disable_enable(fae)

    finally:
        with allure.step(f"Validate unset peer-port state command"):
            fae.system.peer_port.unset(op_param=PeerPortConsts.STATE, apply=True).verify_result()

        with allure.step(f"Validate peer-port state is set to default (enabled) in show command"):
            show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()
            ValidationTool.verify_field_value_in_output(show_output, PeerPortConsts.STATE, PeerPortConsts.STATE_ENABLED).\
                verify_result()


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_peer_port_state_fae_set_unset_stress(engines, test_api):

    TestToolkit.tested_api = test_api
    fae = Fae()
    system = System()
    try:
        for i in range(20):
            helper_fae_peer_port_disable_enable(fae)
            with allure.step(f"Check health status"):
                health_op = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).verify_result()
                ValidationTool.verify_field_value_in_output(health_op, HealthConsts.STATUS, HealthConsts.OK).\
                    verify_result()

    finally:
        with allure.step(f"Validate unset peer-port state command"):
            fae.system.peer_port.unset(op_param=PeerPortConsts.STATE, apply=True).verify_result()

        with allure.step(f"Validate peer-port state is set to default (enabled) in show command"):
            show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()
            ValidationTool.verify_field_value_in_output(show_output, PeerPortConsts.STATE, PeerPortConsts.STATE_ENABLED).\
                verify_result()


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_nmx_t_lite_start_stop(engines, test_api):

    TestToolkit.tested_api = test_api
    fae = Fae()
    system = System()
    nmx_t_lite = "nmx-t-lite"
    try:
        with allure.step(f"Check health status"):
            with allure.step(f"Check health status"):
                retry_call(helper_validate_health_status, [system], exceptions=AssertionError, tries=1, delay=1)

        with allure.step(f"Stop nmx-t-lite"):
            engines.dut.run_cmd(f"sudo systemctl stop {nmx_t_lite}.service")
            helper_check_service_status(engines, nmx_t_lite, "inactive")

        with allure.step(f"Check health status"):
            retry_call(helper_validate_health_status, [system], exceptions=AssertionError, tries=1, delay=1)

    finally:
        with allure.step(f"Start nmx-t-lite"):
            engines.dut.run_cmd(f"sudo systemctl start {nmx_t_lite}.service")
            helper_check_service_status(engines, nmx_t_lite, "active")

        with allure.step(f"Check health status"):
            retry_call(helper_validate_health_status, [system], exceptions=AssertionError, tries=1, delay=1)


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_peer_port_state_services(engines, test_api):

    TestToolkit.tested_api = test_api
    fae = Fae()
    gpu_t_service = PeerPortConsts.GPU_TELEMETRY_SERVICE
    nmx_t_lite_service = PeerPortConsts.NMX_T_LITE_SERVICE
    with allure.step(f"Validate peer-port state is enabled by default in show command"):
        show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()
        ValidationTool.verify_field_value_in_output(show_output, PeerPortConsts.STATE, PeerPortConsts.STATE_ENABLED).\
            verify_result()

    with allure.step(f"Validate GPU Telemetry service is running"):
        helper_check_service_status(engines, gpu_t_service, "active")

    with allure.step(f"Validate NMX Telemetry Lite service is running"):
        helper_check_service_status(engines, nmx_t_lite_service, "active")

    with allure.step(f"Validate NMX Telemetry Lite docker is running"):
        helper_check_docker_status(engines, nmx_t_lite_service, True)

    with allure.step(f"Validate set disable peer-port state command"):
        fae.system.peer_port.set(op_param_name=PeerPortConsts.STATE, op_param_value=PeerPortConsts.STATE_DISABLED,
                                 apply=True).verify_result()

    with allure.step(f"Validate peer-port state is disabled in show command"):
        show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()
        ValidationTool.verify_field_value_in_output(show_output, PeerPortConsts.STATE, PeerPortConsts.STATE_DISABLED).\
            verify_result()

    with allure.step(f"Validate GPU Telemetry service is running"):
        helper_check_service_status(engines, gpu_t_service, "active")

    with allure.step(f"Validate NMX Telemetry Lite service is not running"):
        helper_check_service_status(engines, nmx_t_lite_service, "inactive")

    with allure.step(f"Validate NMX Telemetry Lite docker is not running"):
        helper_check_docker_status(engines, nmx_t_lite_service, False)

    with allure.step(f"Validate unset peer-port state command"):
        fae.system.peer_port.unset(op_param=PeerPortConsts.STATE, apply=True).verify_result()

    with allure.step(f"Validate peer-port state is set to default (enabled) in show command"):
        show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()
        ValidationTool.verify_field_value_in_output(show_output, PeerPortConsts.STATE, PeerPortConsts.STATE_ENABLED).\
            verify_result()

    with allure.step(f"Validate GPU Telemetry service is running"):
        helper_check_service_status(engines, gpu_t_service, "active")

    with allure.step(f"Validate NMX Telemetry Lite service is running"):
        helper_check_service_status(engines, nmx_t_lite_service, "active")

    with allure.step(f"Validate NMX Telemetry Lite docker is running"):
        helper_check_docker_status(engines, nmx_t_lite_service, True)


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_gpu_telemetry_log_level_set(engines, test_api):

    TestToolkit.tested_api = test_api
    system = System()
    gpu_telemetry = "gpu_telemetry"

    for log_level in LogComponentsConsts.LOG_LEVEL_LIST:
        with allure.step(f"Validate set gpu telemetry log level command"):
            system.log.component.component_id[gpu_telemetry].set(op_param_name=LogComponentsConsts.LEVEL,
                                                                 op_param_value=log_level, apply=True).verify_result()

        with allure.step(f"Validate GPU telemetry log level is set to {log_level} in show command"):
            show_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.log.component.component_id[gpu_telemetry].show()).verify_result()
            ValidationTool.verify_field_value_in_output(show_output, LogComponentsConsts.LEVEL, log_level).\
                verify_result()

    with allure.step(f"Validate unset gpu telemetry log level command"):
        system.log.component.component_id[gpu_telemetry].unset(op_param=LogComponentsConsts.LEVEL, apply=True).\
            verify_result()

    with allure.step(f"Validate gpu telemetry log level is set to default {LogComponentsConsts.LOG_LEVEL_DEFAULT}"):
        show_output = OutputParsingTool.parse_json_str_to_dictionary(system.log.component.component_id[gpu_telemetry].
                                                                     show()).verify_result()
        ValidationTool.verify_field_value_in_output(show_output, LogComponentsConsts.LEVEL,
                                                    LogComponentsConsts.LOG_LEVEL_DEFAULT).verify_result()


@pytest.mark.gpu_tel
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_peer_port_disconnect(engines, test_api):

    TestToolkit.tested_api = test_api
    peer_port = PeerPort(parent_obj=None)

    with allure.step(f"Get random peer port"):
        random_peer_port = peer_port.get_random_peer_port()
        assert random_peer_port is not None, "Port list is empty"

    with allure.step(f"Get the associated switch port for the peer port {random_peer_port.peer_port_name}"):
        peer_port_show = OutputParsingTool.parse_json_str_to_dictionary(random_peer_port.peer_port.show()).verify_result()
        switch_port_name = peer_port_show[PeerPortConsts.ASSOCIATED_SWITCH_PORT]
        switch_port = Port(switch_port_name)

    with allure.step(f"Link down the associated switch port {switch_port_name}"):
        port_state = NvosConsts.LINK_STATE_DOWN
        switch_port.interface.link.state.set(op_param_name=port_state, apply=True,
                                             ask_for_confirmation=True).verify_result()

    with allure.step("Wait till port {} is {}".format(switch_port, port_state)):
        switch_port.interface.wait_for_port_state(port_state)

    with allure.step(f"Check the peer port shall be removed from list of peer ports"):
        helper_find_port_in_peer_ports(peer_port, random_peer_port, False)

    with allure.step(f"Link back Up the associated switch port {switch_port_name}"):
        port_state = NvosConsts.LINK_STATE_UP
        switch_port.interface.link.state.set(op_param_name=port_state, apply=True,
                                             ask_for_confirmation=True).verify_result()

    with allure.step("Wait till port {} is {}".format(switch_port, port_state)):
        switch_port.interface.wait_for_port_state(port_state)

    with allure.step(f"Check the peer port shall be available from list of peer ports"):
        helper_find_port_in_peer_ports(peer_port, random_peer_port, True)


def helper_fae_peer_port_disable_enable(fae):
    with allure.step(f"Validate set enable peer-port state command"):
        fae.system.peer_port.set(op_param_name=PeerPortConsts.STATE, op_param_value=PeerPortConsts.STATE_ENABLED,
                                 apply=True).verify_result()

    with allure.step(f"Validate peer-port state is enabled in show command"):
        show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()
        ValidationTool.verify_field_value_in_output(show_output, PeerPortConsts.STATE, PeerPortConsts.STATE_ENABLED). \
            verify_result()

    with allure.step(f"Validate set disable peer-port state command"):
        fae.system.peer_port.set(op_param_name=PeerPortConsts.STATE, op_param_value=PeerPortConsts.STATE_DISABLED,
                                 apply=True).verify_result()

    with allure.step(f"Validate peer-port state is disabled in show command"):
        show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.peer_port.show()).verify_result()
        ValidationTool.verify_field_value_in_output(show_output, PeerPortConsts.STATE, PeerPortConsts.STATE_DISABLED). \
            verify_result()


@retry(AssertionError, tries=36, delay=5)
def helper_find_port_in_peer_ports(peer_port, peer_port_interface, available=True):
    port_found = True if peer_port_interface.peer_port_name in peer_port.peer_port_names_get() else False
    assert port_found == available, 'Port {name} find status in list of peer ports is {found} instead of {available}'.\
        format(name=peer_port_interface.peer_port_name, found=port_found, available=available)


def helper_validate_peer_port_show(peer_port_interface):
    with allure.step(f"Validate show_peer_port API for Port {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.show_peer_port()).verify_result()

    with allure.step(f"Validate 'nv show peer-port <port>' for Port {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.show()).verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> counters' for Port {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.counters.show()).verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> counters link' for Port {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.counters.link.show()).verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> counters nvl' for Port {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.counters.nvl.show()).verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> link' for Port {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.link.show()).verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> link phy' for Port {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.link.phy.show()).verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> link phy detail' for {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.link.phy.detail.show()).\
            verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> link phy health' for {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.link.phy.health.show()).\
            verify_result()

    with allure.step(f"Validate 'nv show peer-port <port> link phy health histogram' for Port"
                     f" {peer_port_interface.peer_port_name}"):
        OutputParsingTool.parse_json_str_to_dictionary(peer_port_interface.peer_port.link.phy.health.histogram.show()).\
            verify_result()


@retry(AssertionError, tries=3, delay=4)
def helper_check_service_status(engines, service, exp_status):
    status = engines.dut.run_cmd(f"sudo systemctl is-active {service}.service")
    assert exp_status == status, f"Status of service {service} is {status} instead of {exp_status}"


@retry(AssertionError, tries=3, delay=4)
def helper_check_docker_status(engines, service, running_status):
    output = engines.dut.run_cmd(f'docker ps --filter "name=^/{service}" --filter "status=running" -q')
    assert bool(output) == running_status, f"Running Status of docker {service} is not {running_status}"


def helper_validate_health_status(system, status=HealthConsts.OK):
    health_op = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).verify_result()
    ValidationTool.verify_field_value_in_output(health_op, HealthConsts.STATUS, status).verify_result()
