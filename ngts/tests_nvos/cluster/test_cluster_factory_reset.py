import logging
import random
import re
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, OutputFormat, SystemConsts, ClusterAppsLogLevels, NvosConst, \
    ImageConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.factory_reset.helpers import add_verification_data, \
    verify_the_setup_is_functional, get_current_time
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()


@disabled_access_ports
@pytest.mark.timeout(35 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_default_factory_reset(engines, devices, test_api, has_loopbox, standalone_system, setup_name):

    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        current_time = get_current_time(engines)
        system = System()
        sdn = Sdn()
        all_state_files_paths = {}
        all_config_files_paths = {}
        initial_config_contents = {}
        sdn_files_deleted = False
        interface_wa_called = False
    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents, setup_name)

        if not standalone_system:
            initial_partition_output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                                   output_format=output_format).get_returned_value()
            with allure.step("Create Empty partition"):
                ClusterTools.create_empty_partition(sdn, {})

        with allure.step("Run reset factory without params"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')

        with allure.step("Verify cluster in correct state"):
            verify_cluster_state_resetted(cluster)
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_down(engines, app)
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            logger.info("Sleeping for 30 seconds to gather nmx log messages")
            time.sleep(30)
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(ClusterAppsLogLevels.NOTICE, app, output_format, cluster)

            interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines, has_loopbox, setup_name, standalone_system)
            next(interfaces_wa)
            interface_wa_called = True

            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok', has_loopbox)

            if not standalone_system:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                assert initial_partition_output == output, f'Partition was not restored to initial. initial: {initial_partition_output}\n current: {output}'

    finally:
        if interface_wa_called:
            try:
                next(interfaces_wa)
            except StopIteration:
                pass  # Or handle it if necessary
        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/*'}")
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, dut=devices.dut)

        if not sdn_files_deleted:
            ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
            delete_all_sdn_fetched_generated_files(engines, sdn, all_config_files_paths, all_state_files_paths)


@disabled_access_ports
@pytest.mark.timeout(35 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_factory_reset_keep_basic(engines, devices, test_api, test_name, has_loopbox, setup_name, standalone_system):
    # SAME AS DEFAULT.
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        current_time = get_current_time(engines)
        system = System()
        sdn = Sdn()
        all_state_files_paths = {}
        all_config_files_paths = {}
        initial_config_contents = {}
        sdn_files_deleted = False
        interface_wa_called = False
    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents, setup_name)

        if not standalone_system:
            initial_partition_output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                                   output_format=output_format).get_returned_value()
            with allure.step("Create Empty partition"):
                ClusterTools.create_empty_partition(sdn, {})

        with allure.step("Run reset factory keep basic param"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep basic", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')

        with allure.step("Verify cluster in correct state"):
            verify_cluster_state_resetted(cluster)
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_down(engines, app)
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            logger.info("Sleeping for 30 seconds to gather nmx log messages")
            time.sleep(30)
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(ClusterAppsLogLevels.NOTICE, app, output_format, cluster)

            interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines, has_loopbox, setup_name, standalone_system)
            next(interfaces_wa)
            interface_wa_called = True
            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok', has_loopbox)

            if not standalone_system:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                assert initial_partition_output == output, f'Partition was not restored to initial. initial: {initial_partition_output}\n current: {output}'

    finally:
        if interface_wa_called:
            try:
                next(interfaces_wa)
            except StopIteration:
                pass  # Or handle it if necessary
        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/*'}")

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, dut=devices.dut)

        if not sdn_files_deleted:
            ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
            delete_all_sdn_fetched_generated_files(engines, sdn, all_config_files_paths, all_state_files_paths)


@disabled_access_ports
@pytest.mark.timeout(35 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_factory_keep_only_files(engines, devices, test_api, test_name, has_loopbox, setup_name, standalone_system):
    # SAME
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        current_time = get_current_time(engines)
        system = System()
        sdn = Sdn()
        all_state_files_paths = {}
        all_config_files_paths = {}
        initial_config_contents = {}
        sdn_files_deleted = False
        interface_wa_called = False
    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents, setup_name)

        if not standalone_system:
            initial_partition_output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                                   output_format=output_format).get_returned_value()
            with allure.step("Create Empty partition"):
                ClusterTools.create_empty_partition(sdn, {})

        with allure.step("Run reset factory with keep only-files param"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep only-files", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')

        with allure.step("Verify cluster in correct state"):
            verify_cluster_state_resetted(cluster)
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_down(engines, app)
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            logger.info("Sleeping for 30 seconds to gather nmx log messages")
            time.sleep(30)
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(ClusterAppsLogLevels.NOTICE, app, output_format, cluster)

            interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines, has_loopbox, setup_name, standalone_system)
            next(interfaces_wa)
            interface_wa_called = True
            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok', has_loopbox)

            if not standalone_system:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                assert initial_partition_output == output, f'Partition was not restored to initial. initial: {initial_partition_output}\n current: {output}'

    finally:
        if interface_wa_called:
            try:
                next(interfaces_wa)
            except StopIteration:
                pass  # Or handle it if necessary
        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/*'}")

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, dut=devices.dut)

        if not sdn_files_deleted:
            ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
            delete_all_sdn_fetched_generated_files(engines, sdn, all_config_files_paths, all_state_files_paths)


@disabled_access_ports
@pytest.mark.timeout(50 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_factory_reset_keep_all_config(engines, devices, test_api, test_name, has_loopbox, setup_name, standalone_system):
    # Only fetched and generated files will be cleaned.
    # SAME
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        current_time = get_current_time(engines)
        system = System()
        sdn = Sdn()
        all_state_files_paths = {}
        all_config_files_paths = {}
        log_level = ''
        initial_config_contents = {}
        sdn_files_deleted = False
        interface_wa_called = False
    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        log_level = reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents, setup_name)

        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

        if not standalone_system:
            with allure.step("Create Empty partition"):
                ClusterTools.create_empty_partition(sdn, {})

        with allure.step("Run reset factory with keep all-config param"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep all-config", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled', nmx_c_expected_state='up')

        with allure.step("Verify cluster in correct state"):
            cluster_state = ClusterTools.check_cluster_state(cluster, output_format)
            assert cluster_state == NvosConst.ENABLED, f"Expected cluster state {NvosConst.ENABLED}, Actual {cluster_state}"
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_up(engines, app)  # Verify apps are running
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            time.sleep(30)
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(log_level, app, output_format, cluster)
            # Not expecting content to change.
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                transformation_fn = ClusterConsts.CONFIG_FILES_CONTENT_CHANGE.get(file_type, lambda x: x)
                initial_config_contents[file_type] = transformation_fn(initial_config_contents[file_type])

            interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines, has_loopbox, setup_name, standalone_system)
            next(interfaces_wa)
            interface_wa_called = True
            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok', has_loopbox)  # Apps should be running

            if not standalone_system:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                assert ClusterConsts.EMPTY_PARTITION_ID in output.keys(), f'Partition {ClusterConsts.EMPTY_PARTITION_ID} was deleted, while its expected to be kept'
    finally:
        if interface_wa_called:
            try:
                next(interfaces_wa)
            except StopIteration:
                pass  # Or handle it if necessary
        if not standalone_system:
            with allure.step("Running sdn factory reset"):
                sdn.factory_default.action_reset(param='force')
                time.sleep(2)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled', nmx_c_expected_state='up')

        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/*'}")
        for app in ClusterConsts.INITIAL_EXPECTED_APPS:
            cluster.apps.app_name[app].loglevel.action_restore_cluster()

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, dut=devices.dut)

        if not sdn_files_deleted:
            ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
            delete_all_sdn_fetched_generated_files(engines, sdn, all_config_files_paths, all_state_files_paths)

        with allure.step("Run reset factory to get back to default configuration"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "", current_time)


def execute_reset_factory(engines, system, operation, flag, current_time):
    logging.info("Current time: " + str(current_time))
    system.factory_default.action_reset(operation=operation, param=flag).verify_result()


def verify_cluster_state_resetted(cluster):
    with allure.step("Running 'nv show cluster' command and parsing output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.show(output_format=OutputFormat.json),
            output_format=OutputFormat.json).get_returned_value()
        with allure.step("Validate initial state is disabled"):
            assert output[SystemConsts.STATE] == NvosConst.DISABLED, f"initial state is , " \
                f"{output[SystemConsts.STATE]}, Expected to be: " \
                f"{NvosConst.DISABLED}"


def verify_apps_in_expected_state(cluster, status, has_loopbox):
    with allure.step("Running 'nv show cluster apps running' command and verifying output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.running.show(output_format=OutputFormat.json),
            output_format=OutputFormat.json).get_returned_value()
        for app in ClusterConsts.INITIAL_EXPECTED_APPS:
            app_status = output[app]['status']
            assert app_status == status, f"App {app} status is {app_status} instead of {status}"


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


def reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents, setup_name):

    logger.info("Setting cluster state to enabled")
    ClusterTools.start_cluster(cluster, setup_name, output_format)

    with allure.step("Choose random log level, and set cluster app log level to and start app"):
        log_level = random.choice(ClusterConsts.ClusterAppsLogLevelsList)
        for app in ClusterConsts.INITIAL_EXPECTED_APPS:
            cluster.apps.app_name[app].loglevel.action_update_cluster_log_level(level=log_level)

    controller_config_files_paths = ClusterTools.get_current_config_files_paths(sdn, ClusterConsts.NMX_CONTROLLER, ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES)
    telemetry_config_files_paths = ClusterTools.get_current_config_files_paths(sdn, ClusterConsts.NMX_TELEMETRY, ClusterConsts.NMX_TELEMETRY_CONFIG_FILE_TYPES)
    config_files_paths = dict(list(controller_config_files_paths.items()) + list(telemetry_config_files_paths.items()))

    for file_type, file_path in config_files_paths.items():
        initial_config_contents[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))

    initial_configs_paths_to_restore = {}
    path_to_config = {}
    config_file_name = {}

    for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
        app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
        sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[config_files_paths[file_type].split('/')[-1]].action_upload(ImageConsts.SCP_PATH + ClusterConsts.INITIAL_CONFIGURATIONS_PATH)
        initial_configs_paths_to_restore[file_type] = ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/' + config_files_paths[file_type].split('/')[-1]
        logger.info(f"Uploading files: {initial_configs_paths_to_restore[file_type]}")

        file_name = 'dummy_' + (initial_configs_paths_to_restore[file_type]).split('/')[-1]
        dummy_file_path = ClusterConsts.INITIAL_CONFIGURATIONS_PATH + '/' + file_name
        engines.sonic_mgmt.run_cmd("sudo cp {} {}".format(initial_configs_paths_to_restore[file_type], dummy_file_path))
        with allure.step("Change initial content"):
            edit_cmd = ClusterConsts.CONFIG_FILES_CHANGE[file_type].format(file_path=dummy_file_path)
            engines.sonic_mgmt.run_cmd(edit_cmd)
        path_to_config[file_type] = dummy_file_path
        config_file_name[file_type] = file_name
    with allure.step("Fetch & Generate config files"):
        for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
            app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
            sdn.config.apps.app_name[app].type.file_type[file_type].action_fetch_sdn(path_to_config[file_type])
            output = sdn.config.apps.app_name[app].type.file_type[file_type].action_generate_sdn()

    with allure.step("Generate state files"):
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

            current_config_set = set(line.strip() for line in current_config_content.strip().split('\n') if line.strip())
            expected_config_set = set(line.strip() for line in expected_config_content.strip().split('\n') if line.strip())
            if file_type == 'chassis_mapping' and is_bug_active(4222718):
                continue
            assert current_config_set == expected_config_set, f"Configuration mismatch:\nCurrent: {current_config_set}\nExpected: {expected_config_set}"

    return log_level


def rotate_logs(system):
    with allure.step("Rotate logs"):
        logging.info("Rotate logs")
        system.log.rotate_logs()


def verify_config_files_content_not_changed(sdn, initial_config_contents, engines):
    errors_list = []
    current_config_files_content = {}
    controller_config_files_paths = ClusterTools.get_current_config_files_paths(sdn, ClusterConsts.NMX_CONTROLLER, ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES)
    telemetry_config_files_paths = ClusterTools.get_current_config_files_paths(sdn, ClusterConsts.NMX_TELEMETRY, ClusterConsts.NMX_TELEMETRY_CONFIG_FILE_TYPES)
    config_files_paths = dict(list(controller_config_files_paths.items()) + list(telemetry_config_files_paths.items()))

    for file_type, file_path in config_files_paths.items():
        current_config_files_content[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))
    assert len(current_config_files_content) == len(initial_config_contents), 'Missing configs'
    for file_type, current_file_content in current_config_files_content.items():
        init_file_content = initial_config_contents.get(file_type)
        if set(current_file_content.split('\n')) != set(init_file_content.split('\n')):
            errors_list.append(f"Configuration mismatch in file {file_type}:\nInitial: {init_file_content}\nCurrent: {current_file_content}")
    assert not errors_list, "\n\n".join(errors_list)


def pre_factory_reset_security_checks():
    with allure.step('TPM check'):
        next(factory_reset_tpm_checker)
    with allure.step('GNMI cert check'):
        next(factory_reset_gnmi_checker)
    # with allure.step('NMX cert check'):
    #     next(factory_reset_nmx_cert_checker)
    # Add back once alon navarro tests it on general reset factory test.


def post_factory_reset_security_checks():
    pre_factory_reset_security_checks()


def delete_all_sdn_fetched_generated_files(engines, sdn, all_config_files_paths, all_state_files_paths):
    with allure.step("Delete state/config Files"):
        for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
            if file_type in all_config_files_paths and all_config_files_paths[file_type]:
                for file in all_config_files_paths[file_type]:
                    app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                    file = file.split('/')[-1]
                    try:
                        sdn.config.apps.app_name[app].type.file_type[file_type].files.file_name[file].action_delete()
                    except Exception as e:
                        logger.info("File Already Deleted")
        for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
            if file_type in all_state_files_paths and all_state_files_paths[file_type]:
                for file in all_state_files_paths[file_type]:
                    app = ClusterConsts.MAP_STATE_FILE_TYPE_TO_APP[file_type]
                    file = file.split('/')[-1]
                    try:
                        sdn.state.apps.app_name[app].type.file_type[file_type].files.file_name[file].action_delete()
                    except Exception as e:
                        logger.info("File Already Deleted")
