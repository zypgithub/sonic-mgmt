import logging
import random
import time

import pytest

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.StressResourcesTool import StressResourcesTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_constants.constants_nvos import PlatformConsts, SystemConsts, OutputFormat, ApiType, IbConsts, NvosConst, ClusterAppsLogLevels
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools

logger = logging.getLogger()
NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
UNDEFINED_STATE = 'undefined'
UNDEFINED_STATE_ERR_MSG = 'Error: At state: \'undefined\' is not one of [\'enabled\', \'disabled\']'
NMX_LOG_MESSAGES_TAGS = ['nmxc-sm', 'nmxc-fm', 'nmxc-fib', 'nmxc-gw_api', 'nmxc-rest', 'nmxc-config_daemon']
DEFAULT_LOG_LEVEL = 'notice'
UNDEFINED_LOG_LEVEL = '''Output was expected to contain:
Action succeeded
But the output is:
Error: At @update.parameters.log_level: 'undefined' is not one of ['critical', 'error', 'warn', 'notice', 'info', 'debug', None]'''

ClusterAppsLogLevelsList = [ClusterAppsLogLevels.DEBUG, ClusterAppsLogLevels.INFO, ClusterAppsLogLevels.NOTICE, ClusterAppsLogLevels.WARNING, ClusterAppsLogLevels.ERROR, ClusterAppsLogLevels.CRITICAL]
SLEEP_AFTER_LOG_ROTATE = 20


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_app_log_level(engines, devices, test_api):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    try:
        with allure.step("Create Cluster object"):
            cluster = Cluster()
            system = System()
            logger.info("Setting cluster state to enabled")
            ClusterTools.start_cluster(cluster, output_format)
        with allure.step("Validate initial log level"):
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(DEFAULT_LOG_LEVEL, app, output_format, cluster)
            _rotate_logs(system)
            logger.info(f"Sleeping for {SLEEP_AFTER_LOG_ROTATE} seconds to gather log messages and verify its level")
            time.sleep(SLEEP_AFTER_LOG_ROTATE)
            ClusterTools.verify_log_messages_log_level(DEFAULT_LOG_LEVEL, system)

        with allure.step("Set log level to undefined log level"):
            for app in INITIAL_EXPECTED_APPS:
                output = cluster.apps.apps_name[app].loglevel.action_update_cluster_log_level(level='undefined')
                assert output.info == UNDEFINED_LOG_LEVEL, f"Expected {UNDEFINED_LOG_LEVEL}, Actual: {output.info}"
                ClusterTools.verify_log_level(DEFAULT_LOG_LEVEL, app, output_format, cluster)
            _rotate_logs(system)
            logger.info(f"Sleeping for {SLEEP_AFTER_LOG_ROTATE} seconds to gather log messages and verify its level")
            time.sleep(SLEEP_AFTER_LOG_ROTATE)
            ClusterTools.verify_log_messages_log_level(DEFAULT_LOG_LEVEL, system)

        with allure.step("Choose random log level, and set cluster app log level to"):
            log_level = random.choice(ClusterAppsLogLevelsList)
            for app in INITIAL_EXPECTED_APPS:
                cluster.apps.apps_name[app].loglevel.action_update_cluster_log_level(level=log_level)
                ClusterTools.verify_log_level(log_level, app, output_format, cluster)
            _rotate_logs(system)
            logger.info(f"Sleeping for {SLEEP_AFTER_LOG_ROTATE} seconds to gather log messages and verify its level")
            time.sleep(SLEEP_AFTER_LOG_ROTATE)
            ClusterTools.verify_log_messages_log_level(log_level, system)

    finally:
        for app in INITIAL_EXPECTED_APPS:
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.running.show(output_format=OutputFormat.json),
                output_format=OutputFormat.json).get_returned_value()
            app_status = output[app]['status']
            if app_status != 'ok':
                ClusterTools.stop_app(cluster, app)
                ClusterTools.start_app(cluster, app)
            cluster.apps.apps_name[app].loglevel.action_restore_cluster()
            ClusterTools.verify_log_level(DEFAULT_LOG_LEVEL, app, output_format, cluster)
        _rotate_logs(system)
        logger.info(f"Sleeping for {SLEEP_AFTER_LOG_ROTATE} seconds to gather log messages and verify its level")
        time.sleep(SLEEP_AFTER_LOG_ROTATE)
        ClusterTools.verify_log_messages_log_level(DEFAULT_LOG_LEVEL, system)
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state()


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_app_log_level_under_stress(engines, devices, test_api):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    try:
        with allure.step("Create Cluster object"):
            cluster = Cluster()
            system = System()
            logger.info("Setting cluster state to enabled")
            installed_packages = []
            ClusterTools.start_cluster(cluster, output_format)

            installed_packages = StressResourcesTool.stress_cpu_and_memory(engines, devices.dut.core_count)
            timeout = 300  # for example, 300 seconds

            # Get the current time
            start_time = time.time()

        while time.time() - start_time < timeout:
            with allure.step("Choose random log level, and set cluster app log level to"):
                log_level = random.choice(ClusterAppsLogLevelsList)
                for app in INITIAL_EXPECTED_APPS:
                    result_obj, duration = OperationTime.save_duration('cluster update log level', '', test_name, cluster.apps.apps_name[app].loglevel.action_update_cluster_log_level, log_level)
                    OperationTime.verify_operation_time(duration, 'cluster update log level').verify_result()
                    ClusterTools.verify_log_level(log_level, app, output_format, cluster)
                logger.info(f"Sleeping for 5 seconds between iterations")
                time.sleep(5)
                _rotate_logs(system)
                logger.info(f"Sleeping for {SLEEP_AFTER_LOG_ROTATE} seconds to gather log messages and verify its level")
                time.sleep(SLEEP_AFTER_LOG_ROTATE)
                ClusterTools.verify_log_messages_log_level(log_level, system)
    finally:
        if installed_packages:
            StressResourcesTool.delete_packages(engines, installed_packages)
        for app in INITIAL_EXPECTED_APPS:
            with allure.step("Make sure apps are still running"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.apps.running.show(output_format=OutputFormat.json),
                    output_format=OutputFormat.json).get_returned_value()
                app_status = output[app]['status']
                with allure.step("Start apps that were stopped"):
                    if app_status != 'ok':
                        ClusterTools.stop_app(cluster, app)
                        ClusterTools.start_app(cluster, app)
            with allure.step("Restore log level"):
                cluster.apps.apps_name[app].loglevel.action_restore_cluster()
                ClusterTools.verify_log_level(DEFAULT_LOG_LEVEL, app, output_format, cluster)
        _rotate_logs(system)
        logger.info(f"Sleeping for {SLEEP_AFTER_LOG_ROTATE} seconds to gather log messages and verify its level")
        time.sleep(SLEEP_AFTER_LOG_ROTATE)
        ClusterTools.verify_log_messages_log_level(DEFAULT_LOG_LEVEL, system)
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state()


def _rotate_logs(system):
    with allure.step("Rotate logs"):
        logging.info("Rotate logs")
        system.log.rotate_logs()
