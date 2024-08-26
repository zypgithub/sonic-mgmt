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
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.factory_reset.helpers import add_verification_data, \
    verify_cleanup_done, verify_the_setup_is_functional, get_current_time
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()
NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG = 'Output was expected to contain:\nAction succeeded\nBut the output is:\nAction executing ...\nError: Action failed with the following issue:\n  cluster is not enabled'
TELEMETRY_SERVICES = ['nmx-connector', 'ib-telemetry']
CONTROLLER_SERVICES = ['nmxc-sdn', 'nmxc-fib', 'redis']
ClusterAppsLogLevelsList = [ClusterAppsLogLevels.DEBUG, ClusterAppsLogLevels.INFO, ClusterAppsLogLevels.NOTICE, ClusterAppsLogLevels.WARNING, ClusterAppsLogLevels.ERROR, ClusterAppsLogLevels.CRITICAL]
NMX_CONTROLLER_CONFIG_FILE_TYPES = ['fm_config', 'sm_config']  # Todo - add rdm_config once bug is fixed [NVOS - Design] Bug SW #4047277: [Functional] [NMX -Juliet] | Cannot generate SDN rdm_config config file | Assignee: Oren Reiss | Status: Assigned
NMX_CONTROLLER_STATE_FILE_TYPES = ['conn_info', 'sm_dump', 'topology']
NMX_LOG_MESSAGES_TAGS = ['nmxc-sm', 'nmxc-fm', 'nmxc-fib', 'nmxc-gw_api', 'nmxc-rest', 'nmxc-config_daemon']
INITIAL_CONFIGURATIONS_PATH = '/auto/sw_system_project/NVOS_INFRA/verification_files/cluster/uploaded_control_plane_files'


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_default_factory_reset(engines, devices, test_api):

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
    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents)

        # with allure.step('pre factory reset security checks'):
        #     pre_factory_reset_security_checks()

        with allure.step("Run reset factory without params"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()

        # with allure.step('post factory reset steps'):
        #     with allure.step('pre factory reset security checks'):
        #         post_factory_reset_security_checks()

        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username)

        with allure.step("Verify cluster in correct state"):
            verify_cluster_state_resetted(cluster)
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_down(engines, app)
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.start_cluster(cluster, OutputFormat.json)
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            logger.info("Sleeping for 30 seconds to gather nmx log messages")
            time.sleep(30)
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(ClusterAppsLogLevels.NOTICE, app, output_format, cluster)
            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok')
    finally:
        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {INITIAL_CONFIGURATIONS_PATH + '/*'}")
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state()

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=False, dut=devices.dut)

        if not sdn_files_deleted:
            delete_all_sdn_fetched_generated_files(sdn, all_config_files_paths, all_state_files_paths)


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_factory_reset_keep_basic(engines, devices, test_api, test_name):
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

    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents)

        with allure.step("Run reset factory without params"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep basic", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()

        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username, param='keep basic')

        with allure.step("Verify cluster in correct state"):
            verify_cluster_state_resetted(cluster)
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_down(engines, app)
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.start_cluster(cluster, OutputFormat.json)
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            logger.info("Sleeping for 30 seconds to gather nmx log messages")
            time.sleep(30)
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(ClusterAppsLogLevels.NOTICE, app, output_format, cluster)
            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok')
    finally:
        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {INITIAL_CONFIGURATIONS_PATH + '/*'}")
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state()

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=False, dut=devices.dut)

        if not sdn_files_deleted:
            delete_all_sdn_fetched_generated_files(sdn, all_config_files_paths, all_state_files_paths)


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_factory_keep_only_files(engines, devices, test_api, test_name):
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
    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents)

        with allure.step("Run reset factory without params"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep only-files", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()

        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username, param='only-files')

        with allure.step("Verify cluster in correct state"):
            verify_cluster_state_resetted(cluster)
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_down(engines, app)
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.start_cluster(cluster, OutputFormat.json)
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            logger.info("Sleeping for 30 seconds to gather nmx log messages")
            time.sleep(30)
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(ClusterAppsLogLevels.NOTICE, app, output_format, cluster)
            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok')
    finally:
        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {INITIAL_CONFIGURATIONS_PATH + '/*'}")
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state()

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=False, dut=devices.dut)

        if not sdn_files_deleted:
            delete_all_sdn_fetched_generated_files(sdn, all_config_files_paths, all_state_files_paths)


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_cluster_factory_reset_keep_all_config(engines, devices, test_api, test_name):
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
    try:
        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)
        log_level = reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents)

        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

        with allure.step("Run reset factory without params"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep all-config", current_time)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()

        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username, param='keep-all-config')

        with allure.step("Verify cluster in correct state"):
            cluster_state = ClusterTools.check_cluster_state(cluster, output_format)
            assert cluster_state == NvosConst.ENABLED, f"Expected cluster state {NvosConst.ENABLED}, Actual {cluster_state}"
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_app_is_up(engines, app)  # Verify apps are running
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_config_files_paths[file_type])
            for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
                verify_all_files_are_deleted(engines, all_state_files_paths[file_type])
            ClusterTools.verify_sdn_config_files_deleted(sdn)
            ClusterTools.verify_sdn_state_files_deleted(sdn)
            sdn_files_deleted = True
            rotate_logs(system)
            time.sleep(30)
            for app in INITIAL_EXPECTED_APPS:
                ClusterTools.verify_log_level(log_level, app, output_format, cluster)
            verify_config_files_content_not_changed(sdn, initial_config_contents, engines)
            verify_apps_in_expected_state(cluster, 'ok')  # Apps should be running

    finally:
        engines.sonic_mgmt.run_cmd(f"sudo rm -rf {INITIAL_CONFIGURATIONS_PATH + '/*'}")
        for app in INITIAL_EXPECTED_APPS:
            cluster.apps.apps_name[app].loglevel.action_restore_cluster()
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state()

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=False, dut=devices.dut)

        if not sdn_files_deleted:
            delete_all_sdn_fetched_generated_files(sdn, all_config_files_paths, all_state_files_paths)


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


def verify_apps_in_expected_state(cluster, status):
    with allure.step("Running 'nv show cluster apps running' command and verifying output"):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.apps.running.show(output_format=OutputFormat.json),
            output_format=OutputFormat.json).get_returned_value()
        for app in INITIAL_EXPECTED_APPS:
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


def reset_factory_pre_steps(engines, devices, test_api, cluster, current_time, system, sdn, all_state_files_paths, all_config_files_paths, output_format, initial_config_contents):

    logger.info("Setting cluster state to enabled")
    ClusterTools.start_cluster(cluster, output_format)

    # for app in INITIAL_EXPECTED_APPS:
    #     ClusterTools.start_app(cluster, app)

    with allure.step("Choose random log level, and set cluster app log level to and start app"):
        log_level = random.choice(ClusterAppsLogLevelsList)
        for app in INITIAL_EXPECTED_APPS:
            cluster.apps.apps_name[app].loglevel.action_update_cluster_log_level(level=log_level)

    config_files_paths = get_current_config_files_paths(sdn)
    for file_type, file_path in config_files_paths.items():
        initial_config_contents[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))

    initial_configs_paths_to_restore = {}
    path_to_config = {}
    config_file_name = {}

    for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
        sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[config_files_paths[file_type].split('/')[-1]].action_upload(ImageConsts.SCP_PATH + INITIAL_CONFIGURATIONS_PATH)
        initial_configs_paths_to_restore[file_type] = INITIAL_CONFIGURATIONS_PATH + '/' + config_files_paths[file_type].split('/')[-1]
        logger.info(f"Uploading files: {initial_configs_paths_to_restore[file_type]}")

        file_name = 'dummy_' + (initial_configs_paths_to_restore[file_type]).split('/')[-1]
        dummy_file_path = INITIAL_CONFIGURATIONS_PATH + '/' + file_name
        engines.sonic_mgmt.run_cmd("sudo cp {} {}".format(initial_configs_paths_to_restore[file_type], dummy_file_path))
        engines.sonic_mgmt.run_cmd(f"sudo sh -c 'echo \"# This is dummy config file\" >> {dummy_file_path}'")
        path_to_config[file_type] = dummy_file_path
        config_file_name[file_type] = file_name
    with allure.step("Fetch & Generate config files"):
        for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
            sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_fetch_sdn(path_to_config[file_type])
            output = sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn()

    with allure.step("Generate state files"):
        for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
            output = sdn.state.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn()
            output = OutputParsingTool.parse_show_output_to_dict(sdn.state.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            all_state_files_paths[file_type].extend([item['path'] for item in output.values()])

    with allure.step("Install config file"):
        for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
            sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_fetch_sdn(path_to_config[file_type])
            sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[config_file_name[file_type]].action_file_install(force=False)
            output = sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn()
            installed_file = ClusterTools.get_generated_file_name(output.returned_value, 'config')
            output = OutputParsingTool.parse_show_output_to_dict(sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            all_config_files_paths[file_type].extend([item['path'] for item in output.values()])
            current_installed_config_path = output[installed_file]['path']
            current_config_content = engines.dut.run_cmd("sudo cat {}".format(current_installed_config_path))
            expected_config_content = engines.sonic_mgmt.run_cmd("sudo cat {}".format(path_to_config[file_type]))
            assert current_config_content == expected_config_content, f"Config file was not loaded properly. Expected content {expected_config_content}, Actual content: {current_config_content}"

    return log_level


def rotate_logs(system):
    with allure.step("Rotate logs"):
        logging.info("Rotate logs")
        system.log.rotate_logs()


def get_current_config_files_paths(sdn):
    files_dict = {}
    with allure.step("Fetch & Generate config files"):
        for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
            output = sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn()
            installed_file = ClusterTools.get_generated_file_name(output.returned_value, 'config')
            output = OutputParsingTool.parse_show_output_to_dict(sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                 output_format=OutputFormat.json).get_returned_value()
            current_installed_config_path = output[installed_file]['path']
            files_dict[file_type] = current_installed_config_path
    return files_dict


def verify_config_files_content_not_changed(sdn, initial_config_contents, engines):
    current_config_files_content = {}
    config_files_paths = get_current_config_files_paths(sdn)
    for file_type, file_path in config_files_paths.items():
        current_config_files_content[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))
    assert len(current_config_files_content) == len(initial_config_contents), 'Missing configs'
    for file_type, current_file_content in current_config_files_content.items():
        init_file_content = initial_config_contents.get(file_type)
        assert current_file_content == init_file_content, f"Initial configuration was not restored for {file_type}. Current: {current_file_content}, Initial: {init_file_content}"


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


def delete_all_sdn_fetched_generated_files(sdn, all_config_files_paths, all_state_files_paths):
    with allure.step("Delete state/config Files"):
        for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
            for file in all_config_files_paths[file_type]:
                file = file.split('/')[-1]
                sdn.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[file].action_delete()
            engines.sonic_mgmt.run_cmd(f"sudo rm -rf {initial_configs_paths_to_restore[file_type]}")
        for file_type in NMX_CONTROLLER_STATE_FILE_TYPES:
            for file in all_state_files_paths[file_type]:
                file = file.split('/')[-1]
                sdn.state.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.file_name[file].action_delete()
