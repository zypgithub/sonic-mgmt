import logging
import random
import pytest
import time

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools

logger = logging.getLogger()
NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG = 'Output was expected to contain:\nAction succeeded\nBut the output is:\nAction executing ...\nError: Action failed with the following issue:\n  cluster is not enabled'
TELEMETRY_SERVICES = ['nmx-connector', 'ib-telemetry']
CONTROLLER_SERVICES = ['nmxc-sdn', 'nmxc-fib', 'redis']


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_app_start_stop(engines, devices, test_api):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    def verify_apps_attributes(output):
        app_names = list(output.keys())

        with allure.step("Verify initial existing apps"):
            assert set(app_names) == set(INITIAL_EXPECTED_APPS), f"Expected apps:{INITIAL_EXPECTED_APPS} Actual apps:{app_names}"

        with allure.step("Verify 'nv show cluster apps installed' output"):
            ValidationTool.validate_output_of_show(output[NMX_TELEMETRY], devices.dut.cluster_app_nmx_telemetry).verify_result()
            ValidationTool.validate_output_of_show(output[NMX_CONTROLLER], devices.dut.cluster_app_nmx_controller).verify_result()

    with allure.step("Create Cluster object"):
        cluster = Cluster()

    try:
        logger.info("Setting cluster state to enabled")
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

        with allure.step("Running 'nv show cluster apps installed' command and verifying output"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.installed.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            verify_apps_attributes(output)

        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.running.show(output_format=OutputFormat.json),
                output_format=OutputFormat.json).get_returned_value()
            for app in INITIAL_EXPECTED_APPS:
                app_status = output[app]['status']
                assert app_status == 'not ok', f"App {app} status is {app_status} instead of 'not ok'"

        ClusterTools.start_stop_app(cluster, engines, devices)

    finally:
        logger.info("Setting cluster state to disabled")
        ClusterTools.stop_cluster(cluster, output_format)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_stress_cluster_app_start_stop(engines, devices, test_api, test_name):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()

    try:
        with allure.step("Stress testing start/stop apps"):
            ClusterTools.start_cluster(cluster, output_format)
            durations = []
            for i in range(100):
                logger.info(f"Starting iteration {i}")
                result_obj, duration = OperationTime.save_duration('start/stop cluster', '', test_name, ClusterTools.start_stop_app, cluster, engines, devices)
                OperationTime.verify_operation_time(duration, 'start stop cluster app').verify_result()

    finally:
        with allure.step("Stop cluster"):
            ClusterTools.stop_cluster(cluster, output_format)


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
        assert output == '', f"Expected to get empty output, but instead received {output}"

    with allure.step("Running 'nv show cluster apps <app-name>' command and parsing output"):
        for app in INITIAL_EXPECTED_APPS:
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.apps_name[app].show(output_format=OutputFormat.json),
                output_format=OutputFormat.json).get_returned_value()
            assert output == '', f"Expected to get empty output, but instead received {output}"

    with allure.step("Running 'nv show cluster apps installed' command and verifying output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.installed.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert output == '', f"Expected to get empty output, but instead received {output}"

    with allure.step("Running 'nv show cluster apps running' command and verifying output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.running.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        assert output == '', f"Expected to get empty output, but instead received {output}"

    with allure.step("Start/Stop apps"):
        for app in INITIAL_EXPECTED_APPS:
            with allure.step(f"Start app {app} and validate action fails"):
                output = cluster.apps.apps_name[app].action_start_cluster_apps()
                assert output.info == START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG, f"Expected output {START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG}, actual output {output.info}"
            with allure.step(f"Stop app {app} and validate action fails"):
                output = cluster.apps.apps_name[app].action_stop_cluster_apps()
                assert output.info == START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG, f"Expected output {START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG}, actual output {output.info}"
