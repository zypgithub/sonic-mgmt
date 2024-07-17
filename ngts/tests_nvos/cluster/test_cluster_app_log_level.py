import logging
import random
import time

import pytest

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
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
NMX_LOG_MESSAGES_TAGS = ['sm', 'fm', 'fib', 'gw_api', 'rest', 'config_daemon']
DEFAULT_LOG_LEVEL = 'notice'
UNDEFINED_LOG_LEVEL = '''Output was expected to contain:
Action succeeded
But the output is:
Error: At @update.parameters.log_level: 'undefined' is not one of ['critical', 'error', 'warn', 'notice', 'info', 'debug', None]'''

ClusterAppsLogLevelsList = [ClusterAppsLogLevels.DEBUG, ClusterAppsLogLevels.INFO, ClusterAppsLogLevels.NOTICE, ClusterAppsLogLevels.WARNING, ClusterAppsLogLevels.ERROR, ClusterAppsLogLevels.CRITICAL]


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
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.apps.apps_name[app].loglevel.show(output_format=output_format),
                    output_format=output_format).get_returned_value()
                _rotate_logs(system)
                logger.info("Sleeping for 30 seconds to gather log messages and verify its level")
                time.sleep(30)
                _verify_log_level(DEFAULT_LOG_LEVEL, app, output_format, cluster, system)

        with allure.step("Set log level to undefined log level"):
            for app in INITIAL_EXPECTED_APPS:
                output = cluster.apps.apps_name[app].loglevel.action_update_cluster_log_level(level='undefined')
                assert output.info == UNDEFINED_LOG_LEVEL, f"Expected {UNDEFINED_LOG_LEVEL}, Actual: {output.info}"
                _rotate_logs(system)
                logger.info("Sleeping for 30 seconds to gather log messages and verify its level")
                time.sleep(30)
                _verify_log_level(DEFAULT_LOG_LEVEL, app, output_format, cluster, system)

        with allure.step("Choose random log level, and set cluster app log level to"):
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.start_app(cluster, app)
                log_level = random.choice(ClusterAppsLogLevelsList)
                cluster.apps.apps_name[app].loglevel.action_update_cluster_log_level(level=log_level)
                _rotate_logs(system)
                logger.info("Sleeping for 30 seconds to gather log messages and verify its level")
                time.sleep(30)
                _verify_log_level(log_level, app, output_format, cluster, system)
                ClusterTools.stop_app(cluster, app)

    finally:
        for app in INITIAL_EXPECTED_APPS:
            ClusterTools.start_app(cluster, app)
            cluster.apps.apps_name[app].loglevel.action_restore_cluster()
            _rotate_logs(system)
            logger.info("Sleeping for 30 seconds to gather log messages and verify its level")
            time.sleep(30)
            _verify_log_level(DEFAULT_LOG_LEVEL, app, output_format, cluster, system)
            ClusterTools.stop_app(cluster, app)


def _verify_log_level(log_level, app, output_format, cluster, system):
    with allure.step(f"Verifying log level is updated to {log_level}"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.apps_name[app].loglevel.show(output_format=output_format),
            output_format=output_format).get_returned_value()
        # Add assert on log level
        assert output['log-level'] == log_level, f"Expected log level: {log_level}, Actual log-level {output['log-level']}"

        # Get the index of the current log level
        current_level_index = ClusterAppsLogLevelsList.index(log_level)

        # Define the expected log levels based on the current log level
        expected_log_levels = ClusterAppsLogLevelsList[current_level_index:]

        # Convert expected log levels to uppercase
        expected_log_levels_upper = [level.upper() for level in expected_log_levels]

        show_output = system.log.show_log(param=f"| grep -E \"{'|'.join(NMX_LOG_MESSAGES_TAGS)}\"", exit_cmd='q').split('\n')[1:]
        for line in show_output:
            assert any(level in line for level in expected_log_levels_upper), f"Line in logs is {line}, which does not contain any of the expected log levels {expected_log_levels_upper}"


def _rotate_logs(system):
    with allure.step("Rotate logs"):
        logging.info("Rotate logs")
        system.log.rotate_logs()
