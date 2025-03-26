import logging
import random
import pytest
import time
import re

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts, ClusterAppsLogLevels, NvosConst, ImageConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.factory_reset.helpers import add_verification_data, \
    verify_cleanup_done, verify_the_setup_is_functional, get_current_time
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(35 * MINUTE, func_only=True)
def test_cluster_sdn(engines, devices, test_api, has_loopbox, standalone_system, setup_name):

    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json
    config_files_deleted = False
    with allure.step("Create Cluster object"):
        cluster = Cluster()
        current_time = get_current_time(engines)
        system = System()
        sdn = Sdn()
        all_state_files_paths = {}
        all_config_files_paths = {}
        initial_config_contents = {}
        initial_configs_paths_to_restore = {}
        initial_configuration_restored = False
        path_to_config = {config_type: '' for config_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES}
        config_file_name = {config_type: '' for config_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES}

    try:

        logger.info("Setting cluster state to enabled")
        ClusterTools.start_cluster(cluster, setup_name, output_format)

        controller_config_files_paths = ClusterTools.get_current_config_files_paths(sdn, ClusterConsts.NMX_CONTROLLER, ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES)
        telemetry_config_files_paths = ClusterTools.get_current_config_files_paths(sdn, ClusterConsts.NMX_TELEMETRY, ClusterConsts.NMX_TELEMETRY_CONFIG_FILE_TYPES)
        config_files_paths = dict(list(controller_config_files_paths.items()) + list(telemetry_config_files_paths.items()))
        for file_type, file_path in config_files_paths.items():
            initial_config_contents[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))

        with allure.step('Upload initial configurations'):
            for file_type, path_to_file in config_files_paths.items():
                app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[path_to_file.split('/')[-1]].action_upload(ImageConsts.SCP_PATH + ClusterConsts.INITIAL_CONFIGURATIONS_PATH)
                initial_configs_paths_to_restore[file_type] = ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/' + path_to_file.split('/')[-1]
                logger.info(f"Uploading files: {initial_configs_paths_to_restore[file_type]}")

                # Create a dummy config file.
                file_name = 'dummy_' + (initial_configs_paths_to_restore[file_type]).split('/')[-1]
                dummy_file_path = ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/' + file_name
                engines.sonic_mgmt.run_cmd("sudo cp {} {}".format(initial_configs_paths_to_restore[file_type], dummy_file_path))

                edit_cmd = ClusterConsts.CONFIG_FILES_CHANGE[file_type].format(file_path=dummy_file_path)
                engines.sonic_mgmt.run_cmd(edit_cmd)

                path_to_config[file_type] = dummy_file_path
                config_file_name[file_type] = file_name

        with allure.step("Fetch & Generate config files"):
            for _ in range(2):
                for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                    app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                    sdn.config.apps.app_name[app].type.file_type[file_type].action_fetch_sdn(path_to_config[file_type])
                    output = sdn.config.apps.app_name[app].type.file_type[file_type].action_generate_sdn()

        with allure.step("Generate state files"):
            for _ in range(2):
                for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                    app = ClusterConsts.MAP_STATE_FILE_TYPE_TO_APP[file_type]
                    output = sdn.state.apps.app_name[app].type.file_type[file_type].action_generate_sdn()
                    output = OutputParsingTool.parse_show_output_to_dict(sdn.state.apps.app_name[app].type.file_type[file_type].files.show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    all_state_files_paths[file_type] = [item['path'] for item in output.values()]

        with allure.step("Install config file"):
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                sdn.config.apps.app_name[app].type.file_type[file_type].action_fetch_sdn(path_to_config[file_type])
                sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[config_file_name[file_type]].action_file_install(force=False)
                output = sdn.config.apps.app_name[app].type.file_type[file_type].action_generate_sdn()
                installed_file = ClusterTools.get_generated_file_name(output.returned_value, 'config')
                output = OutputParsingTool.parse_show_output_to_dict(sdn.config.apps.app_name[app].type.file_type[file_type].files.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                all_config_files_paths[file_type] = [item['path'] for item in output.values()]
                current_installed_config_path = output[installed_file]['path']
                current_config_content = engines.dut.run_cmd("sudo cat {}".format(current_installed_config_path))
                expected_config_content = engines.sonic_mgmt.run_cmd("sudo cat {}".format(path_to_config[file_type]))
                if file_type == 'chassis_mapping' and is_bug_active(4222718):
                    continue
                assert set(current_config_content.split('\n')) == set(expected_config_content.split('\n')), f"Config file was not loaded properly. Expected content {expected_config_content}, Actual content: {current_config_content}"
                if ClusterConsts.CONFIG_FILES_CHANGE[file_type] != 'true':
                    assert set(current_config_content.split('\n')) != set((initial_config_contents[file_type]).split('\n')), f"Current content has not changed, still same as in init state. init: {initial_config_contents[file_type]}, \ncurrent{current_config_content}"

        with allure.step("Install initial configurations"):
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                sdn.config.apps.app_name[app].type.file_type[file_type].action_fetch_sdn(initial_configs_paths_to_restore[file_type])
                conf_file_name = initial_configs_paths_to_restore[file_type].split('/')[-1]
                sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[conf_file_name].action_file_install(force=False)

        initial_configuration_restored = True

        with allure.step("Delete state/config Files"):
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                if all_config_files_paths[file_type]:
                    for file in all_config_files_paths[file_type]:
                        app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                        file = file.split('/')[-1]
                        sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[file].action_delete()
                engines.sonic_mgmt.run_cmd(f"sudo rm -rf {initial_configs_paths_to_restore[file_type]}")
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                if all_state_files_paths[file_type]:
                    for file in all_state_files_paths[file_type]:
                        app = ClusterConsts.MAP_STATE_FILE_TYPE_TO_APP[file_type]
                        file = file.split('/')[-1]
                        sdn.state.apps.app_name[app].type.file_type[file_type].files.file_name[file].action_delete()

            # INSTEAD OF THE ABOVE, YOU CAN USE THE FOLLOWING: sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.delete_files() and provide with a files list
            # Make sure all files are deleted.
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            verify_all_files_are_deleted(engines, all_state_files_paths)
            verify_all_files_are_deleted(engines, all_config_files_paths)

        config_files_deleted = True

    finally:
        if not initial_configuration_restored:
            with allure.step("Install initial configurations"):
                for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                    app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                    sdn.config.apps.app_name[app].type.file_type[file_type].action_fetch_sdn(initial_configs_paths_to_restore[file_type])
                    conf_file_name = initial_configs_paths_to_restore[file_type].split('/')[-1]
                    sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[conf_file_name].action_file_install(force=False)

        if not config_files_deleted:
            with allure.step("Delete state/config Files"):
                for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                    if (file_type in all_config_files_paths) and all_config_files_paths[file_type]:
                        for file in all_config_files_paths[file_type]:
                            app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                            file = file.split('/')[-1]
                            sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[file].action_delete()
                    engines.sonic_mgmt.run_cmd(f"sudo rm -rf {initial_configs_paths_to_restore[file_type]}")
                for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                    if (file_type in all_state_files_paths) and all_state_files_paths[file_type]:
                        for file in all_state_files_paths[file_type]:
                            app = ClusterConsts.MAP_STATE_FILE_TYPE_TO_APP[file_type]
                            file = file.split('/')[-1]
                            sdn.state.apps.app_name[app].type.file_type[file_type].files.file_name[file].action_delete()
                    # engines.sonic_mgmt.run_cmd(f"sudo rm -rf {initial_configs_paths_to_restore[file_type]}")


def verify_all_files_are_deleted(engines, files_list):
    for file_path in files_list:
        output = engines.dut.run_cmd(f"ls {file_path}")
        assert "No such file or directory" in output, "File was found, not expected to be found"
