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
from ngts.nvos_tools.nmx.ControlPlane import ControlPlane
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts, ClusterAppsLogLevels, NvosConst, ImageConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.system.factory_reset.post_steps import factory_reset_no_params_post_steps
from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
from ngts.tests_nvos.system.factory_reset.helpers import add_verification_data, \
    verify_cleanup_done, verify_the_setup_is_functional, get_current_time
from ngts.nvos_tools.system.System import System

logger = logging.getLogger()
NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG = 'Output was expected to contain:\nAction succeeded\nBut the output is:\nAction executing ...\nError: Action failed with the following issue:\n  cluster is not enabled'
TELEMETRY_SERVICES = ['nmx-connector', 'ib-telemetry']
CONTROLLER_SERVICES = ['nmxc-sdn', 'nmxc-fib', 'redis']
ClusterAppsLogLevelsList = [ClusterAppsLogLevels.DEBUG, ClusterAppsLogLevels.INFO, ClusterAppsLogLevels.NOTICE, ClusterAppsLogLevels.WARNING, ClusterAppsLogLevels.ERROR, ClusterAppsLogLevels.CRITICAL]
NMX_CONTROLLER_CONFIG_FILE_TYPES = ['fm_config', 'sm_config']  # TODO, add 'rdm_config' once bug is fixed  #3982375
NMX_CONTROLLER_STATE_FILE_TYPES = ['conn_info']  # TODO add sm_dump and topology once bug is fixed #3985684
PATH_TO_CONFIG = {'fm_config': '/auto/sw_system_release/sx_mlnx_os/developers/chrisy1/fabricmanager_dummy.cfg',
                  'sm_config': '/auto/sw_system_release/sx_mlnx_os/developers/chrisy1/sm_config_dummy.cfg'}  # TODO, add 'rdm_config' once bug is fixed  #3982375
CONFIG_FILE_NAME = {'fm_config': 'fabricmanager_dummy.cfg',
                    'sm_config': 'sm_config_dummy.cfg'}  # TODO, add 'rdm_config' once bug is fixed  #3982375
NMX_LOG_MESSAGES_TAGS = ['nmxc-sm', 'nmxc-fm', 'nmxc-fib', 'nmxc-gw_api', 'nmxc-rest', 'nmxc-config_daemon']
INITIAL_CONFIGURATIONS_PATH = '/auto/sysgwork/eabboud/nmx_test_configurations'


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_default_factory_reset(engines, devices, test_api):

    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        current_time = get_current_time(engines)
        system = System()
        control_plane = ControlPlane()
        all_state_files_paths = {}
        all_config_files_paths = {}
        initial_config_contents = {}
        initial_configs_paths_to_restore = {}
    try:

        logger.info("Setting cluster state to enabled")
        ClusterTools.start_cluster(cluster, output_format)

        for app in INITIAL_EXPECTED_APPS:
            ClusterTools.start_app(cluster, app)

        time.sleep(3)

        config_files_paths = get_current_config_files_paths(control_plane)
        for file_type, file_path in config_files_paths.items():
            initial_config_contents[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))

        with allure.step('Upload initial configurations'):
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[config_files_paths[file_type].split('/')[-1]].action_upload(ImageConsts.SCP_PATH + INITIAL_CONFIGURATIONS_PATH)
                initial_configs_paths_to_restore[file_type] = INITIAL_CONFIGURATIONS_PATH + config_files_paths[file_type].split('/')[-1]
                logger.info(f"Uploading files: {initial_configs_paths_to_restore[file_type]}")

        with allure.step("Fetch & Generate config files"):
            for i in range(2):
                for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                    control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_fetch_control_plane(PATH_TO_CONFIG[file_type])
                    output = control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_control_plane()

        with allure.step("Generate state files"):
            for i in range(2):
                for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
                    output = control_plane.state.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_control_plane()
                    output = OutputParsingTool.parse_show_output_to_dict(control_plane.state.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=output_format),
                                                                         output_format=output_format).get_returned_value()
                    all_state_files_paths[file_type] = [item['path'] for item in output.values()]

        with allure.step("Install config file"):
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_fetch_control_plane(PATH_TO_CONFIG[file_type])
                control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[CONFIG_FILE_NAME[file_type]].action_file_install(force=False)
                output = control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_control_plane()
                installed_file = get_generated_file_name(output.returned_value, 'config')
                output = OutputParsingTool.parse_show_output_to_dict(control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                all_config_files_paths[file_type] = [item['path'] for item in output.values()]
                current_installed_config_path = output[installed_file]['path']
                current_config_content = engines.dut.run_cmd("sudo cat {}".format(current_installed_config_path))
                expected_config_content = engines.sonic_mgmt.run_cmd("sudo cat {}".format(PATH_TO_CONFIG[file_type]))
                assert current_config_content == expected_config_content, f"Config file was not loaded properly. Expected content {expected_config_content}, Actual content: {current_config_content}"
                assert current_config_content != initial_config_contents[file_type], f"Current content has not changed, still same as in init state. init: {initial_config_contents[file_type]}, \ncurrent{current_config_content}"

        with allure.step("Install initial configurations"):
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_fetch_control_plane(initial_configs_paths_to_restore[file_type])
                conf_file_name = initial_configs_paths_to_restore[file_type].split('/')[-1]
                control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[conf_file_name].action_file_install(force=False)

        with allure.step("Delete state/config Files"):
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                for file in all_config_files_paths[file_type]:
                    control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[file].action_delete()
            for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
                for file in all_state_files_paths[file_type]:
                    control_plane.state.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[file].action_delete()

            # INSTEAD OF THE ABOVE, YOU CAN USE THE FOLLOWING: control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.delete_files() and provide with a files list
            # Make sure all files are deleted.
            verify_control_plane_config_files_deleted(control_plane)
            verify_control_plane_state_files_deleted(control_plane)
            verify_all_files_are_deleted(engines, all_state_files_paths)
            verify_all_files_are_deleted(engines, all_config_files_paths)
            pass

    finally:
        for app in INITIAL_EXPECTED_APPS:
            ClusterTools().stop_app(cluster, app)
        cluster.unset(apply=True)


def verify_control_plane_config_files_deleted(control_plane: ControlPlane):
    with allure.step("Running nv show control-plane config app <app> type <type> files and make sure files are deleted"):
        for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
            files = OutputParsingTool.parse_show_output_to_dict(control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                output_format=OutputFormat.json).get_returned_value()
            assert not files, f"Expected to get empty output, but instead received {output}"


def verify_control_plane_state_files_deleted(control_plane: ControlPlane):
    with allure.step("Running nv show control-plane state app <app> type <type> files and make sure files are deleted"):
        for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
            files = OutputParsingTool.parse_show_output_to_dict(control_plane.state.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                output_format=OutputFormat.json).get_returned_value()
            assert not files, f"Expected to get empty output, but instead received {output}"


def get_generated_file_name(output, file_type):
    # Regular expression to match the file name
    match = re.search(rf'App {file_type} file (\S+) is successfully generated', output)
    file_name = None
    # Extract the file name if found
    assert match, f"File was not generated successfully"
    if match:
        file_name = match.group(1)
        logger.info(f"Extracted file name: {file_name}")
    return file_name


def verify_all_files_are_deleted(engines, files_list):
    for file_path in files_list:
        output = engines.dut.run_cmd(f"ls {file_path}")
        assert "No such file or directory" in output, "File was found, not expected to be found"


def get_current_config_files_paths(control_plane):
    files_dict = {}
    with allure.step("Fetch & Generate config files"):
        for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
            output = control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_control_plane()
            installed_file = get_generated_file_name(output.returned_value, 'config')
            output = OutputParsingTool.parse_show_output_to_dict(control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                 output_format=OutputFormat.json).get_returned_value()
            current_installed_config_path = output[installed_file]['path']
            files_dict[file_type] = current_installed_config_path
    return files_dict


def verify_config_files_content_not_changed(control_plane, initial_config_contents):
    current_config_files_content = {}
    config_files_paths = get_current_config_files_paths(control_plane)
    for file_type, file_path in config_files_paths.items():
        current_config_files_content[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))
    assert len(current_config_files_content) == len(initial_config_contents), 'Missing configs'
    for file_type, current_file_content in current_config_files_content.items():
        init_file_content = initial_config_contents.get(file_type)
        assert current_file_content == init_file_content, f"Initial configuration was not restored for {file_type}. Current: {current_file_content}, Initial: {init_file_content}"


def verify_config_files_content_changed(control_plane, initial_config_contents, engines):
    current_config_files_content = {}
    config_files_paths = get_current_config_files_paths(control_plane)
    for file_type, file_path in config_files_paths.items():
        current_config_files_content[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))
    assert len(current_config_files_content) == len(initial_config_contents), 'Missing configs'
    for file_type, current_file_content in current_config_files_content.items():
        init_file_content = initial_config_contents.get(file_type)
        assert current_file_content != init_file_content, f"Initial configuration was not changed for {file_type}. Current: {current_file_content}, Initial: {init_file_content}"
