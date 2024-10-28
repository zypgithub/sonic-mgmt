import logging
import random
import pytest
import time

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.StressResourcesTool import StressResourcesTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts

logger = logging.getLogger()
NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]

START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG = 'Output was expected to contain:\nApp has been successfully started\nBut the output is:\nAction executing ...\nError: Action failed with the following issue:\n  cluster is not enabled'
STOP_APP_WHILE_CLUSTER_DISABLED_ERR_MSG = 'Output was expected to contain:\nAction succeeded\nBut the output is:\nAction executing ...\nError: Action failed with the following issue:\n  cluster is not enabled'
CLUSTER_IS_NOT_ENABLED_MESSAGE = 'cluster is not enabled'
INVALID_SHOW_EXPECTED_OUTPUT = 'Error: The requested item does not exist.'


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_app_start_stop(engines, devices, test_api, has_loopbox):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    def verify_apps_attributes(output):
        app_names = list(output.keys())

        with allure.step("Verify initial existing apps"):
            assert set(app_names) == set(INITIAL_EXPECTED_APPS), f"Expected apps:{INITIAL_EXPECTED_APPS} Actual apps:{app_names}"

        with allure.step("Verify 'nv show cluster apps' output"):
            ValidationTool.validate_output_of_show(output[NMX_TELEMETRY], devices.dut.cluster_app_nmx_telemetry).verify_result()
            ValidationTool.validate_output_of_show(output[NMX_CONTROLLER], devices.dut.cluster_app_nmx_controller).verify_result()

    with allure.step("Create Cluster object"):
        # interface_wa_called = False
        cluster = Cluster()
        sdn = Sdn()
        # interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines)

    try:
        logger.info("Setting cluster state to enabled")
        # if has_loopbox:
        # next(interfaces_wa)
        # interface_wa_called = True
        ClusterTools.start_cluster(cluster, output_format)

        with allure.step("Running 'nv show cluster apps' command and parsing output"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            verify_apps_attributes(output)

        with allure.step("Running 'nv show cluster apps <app-name>' command and parsing output"):
            for app in INITIAL_EXPECTED_APPS:
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.apps.apps_name[app].show(output_format=OutputFormat.json),
                    output_format=OutputFormat.json).get_returned_value()
                ValidationTool.validate_output_of_show(output, devices.dut.cluster_app[app]).verify_result()

        TestToolkit.tested_api = 'NVUE'
        with allure.step("Running 'nv show cluster apps installed' command and verifying output"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.installed.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            for app in INITIAL_EXPECTED_APPS:
                ValidationTool.validate_output_of_show(output[app], devices.dut.cluster_app[app]).verify_result()
            # verify_apps_attributes(output)

        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            ClusterTools.wait_for_apps_to_be_in_wanted_state()
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.running.show(output_format=OutputFormat.json),
                output_format=OutputFormat.json).get_returned_value()
            for app in INITIAL_EXPECTED_APPS:
                app_status = output[app]['status']
                assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok'"
            logger.info("Make sure there are no extra Unexpected apps")
            assert len(INITIAL_EXPECTED_APPS) == len(output), f"Expected apps {INITIAL_EXPECTED_APPS}, actual apps: {output}"

        # TestToolkit.tested_api = test_api

        ClusterTools.stop_start_app(cluster, engines, devices, has_loopbox)

    finally:
        # if interface_wa_called:
        #     next(interfaces_wa)
        TestToolkit.tested_api = test_api
        with allure.step("Reset cluster state"):
            cluster.unset(apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()


@disabled_access_ports
@pytest.mark.timeout(30 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_stress_cluster_app_start_stop(engines, devices, test_api, test_name):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        # interface_wa_called = False
        cluster = Cluster()
        sdn = Sdn()
        # interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines)
    try:
        with allure.step("Stress testing start/stop apps"):
            # if has_loopbox:
            #     next(interfaces_wa)
            #     interface_wa_called = True
            ClusterTools.start_cluster(cluster, output_format)
            for i in range(5):
                logger.info(f"Starting iteration {i}")
                result_obj, duration = OperationTime.save_duration('start stop cluster app', '', test_name, ClusterTools.stop_start_app, cluster, engines, devices, has_loopbox)
                OperationTime.verify_operation_time(duration, 'start stop cluster app').verify_result()

    finally:
        # if interface_wa_called:
        #     next(interfaces_wa)
        with allure.step("Reset cluster state"):
            cluster.unset(apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_app_start_stop_under_stressed_resources(engines, devices, test_api, test_name):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        # interface_wa_called = False
        cluster = Cluster()
        sdn = Sdn()
        installed_packages = []
        # interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines)
    try:
        with allure.step("Test cluster with stressed CPU and Memory utilization"):
            # This will run in background &
            installed_packages = StressResourcesTool.stress_cpu_and_memory(engines, devices.dut.core_count, timeout='600s')
            timeout = 600  # for example, 600 seconds

            # Get the current time
            start_time = time.time()

            # Loop until the timeout is reached
            while time.time() - start_time < timeout:
                # if has_loopbox:
                #     next(interfaces_wa)
                #     interface_wa_called = True
                ClusterTools.start_cluster(cluster, output_format)
                result_obj, duration = OperationTime.save_duration('start stop cluster app stressed resources', '', test_name, ClusterTools.stop_start_app, cluster, engines, devices, has_loopbox)
                OperationTime.verify_operation_time(duration, 'start stop cluster app stressed resources').verify_result()

    finally:
        # if interface_wa_called:
        #     next(interfaces_wa)
        with allure.step("Reset cluster state"):
            cluster.unset(apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()
        if installed_packages:
            StressResourcesTool.delete_packages(engines, installed_packages)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_app_start_stop_disabled_cluster(engines, devices, test_api):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()

    with allure.step("Running 'nv show cluster apps' command and parsing output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert output == {}, f"Expected to get empty output, but instead received {output}"

    with allure.step("Running 'nv show cluster apps <app-name>' command and parsing output"):
        for app in INITIAL_EXPECTED_APPS:
            try:
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.apps.apps_name[app].show(output_format=OutputFormat.json),
                    output_format=OutputFormat.json).get_returned_value()
            except Exception as e:
                err = e.args[0].split('\n')[-1]
                assert err == INVALID_SHOW_EXPECTED_OUTPUT, f"Expected {INVALID_SHOW_EXPECTED_OUTPUT}, but instead received {output}"

    TestToolkit.tested_api = 'NVUE'

    with allure.step("Running 'nv show cluster apps installed' command and verifying output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.installed.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert output == {}, f"Expected to get empty output, but instead received {output}"

    with allure.step("Running 'nv show cluster apps running' command and verifying output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.running.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert output == {}, f"Expected to get empty output, but instead received {output}"

    TestToolkit.tested_api = test_api
    with allure.step("Start/Stop apps"):
        for app in INITIAL_EXPECTED_APPS:
            with allure.step(f"Start app {app} and validate action fails"):
                output = cluster.apps.apps_name[app].action_start_cluster_apps().get_returned_value(False)
                assert CLUSTER_IS_NOT_ENABLED_MESSAGE in output, f"Expected output to contain {CLUSTER_IS_NOT_ENABLED_MESSAGE}, actual output {output}"
            with allure.step(f"Stop app {app} and validate action fails"):
                output = cluster.apps.apps_name[app].action_stop_cluster_apps().get_returned_value(False)
                assert CLUSTER_IS_NOT_ENABLED_MESSAGE in output, f"Expected output to contain {CLUSTER_IS_NOT_ENABLED_MESSAGE}, actual output {output}"
