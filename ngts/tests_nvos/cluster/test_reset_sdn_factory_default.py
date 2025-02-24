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
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
from ngts.tests_nvos.system.factory_reset.helpers import add_verification_data, \
    verify_cleanup_done, verify_the_setup_is_functional, get_current_time
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()
# @disabled_access_ports


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(15 * MINUTE, func_only=True)
def test_cluster_sdn_factory_reset_nmx_down(engines, devices, test_api, has_loopbox):

    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json
    config_files_deleted = False
    try:
        with allure.step("Run sdn reset factory while cluster is disabled"):
            cluster = Cluster()
            sdn = Sdn()
            output = sdn.factory_default.action_reset(param='force').verify_result(should_succeed=False)

            assert ClusterConsts.RESET_FACTORY_CLUSTER_DISABLED[test_api] in output, f'Expected {ClusterConsts.RESET_FACTORY_CLUSTER_DISABLED[test_api]} Got {output}'

        with allure.step("Run sdn reset factory while nmx-conn is disabled (Enable cluster, and then reset factory before nmx-conn is up"):
            cluster.set(op_param_name="state", op_param_value=NvosConst.ENABLED, apply=True)
            cluster.show(output_format=output_format)
            output = sdn.factory_default.action_reset(param='force').verify_result(should_succeed=False)
            assert ClusterConsts.RESET_FACTORY_NMX_CONN_DISABLED[test_api] in output, f'Expected {ClusterConsts.RESET_FACTORY_NMX_CONN_DISABLED[test_api]} Got {output}'

    finally:
        cluster.unset(apply=True).verify_result()
        ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')


# @disabled_access_ports
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
@pytest.mark.timeout(25 * MINUTE, func_only=True)
def test_sdn_reset_factory(engines, devices, test_api, has_loopbox, test_name, setup_name):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json
    with allure.step("Create Cluster object"):
        cluster = Cluster()
        system = System()
        sdn = Sdn()
        initial_config_contents = {}
        initial_configs_paths_to_restore = {}
        initial_configuration_restored = False
    try:
        logger.info("Setting cluster state to enabled")
        ClusterTools.start_cluster(cluster, setup_name, output_format)
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

        config_files_paths = get_current_config_files_paths(sdn)
        for file_type, file_path in config_files_paths.items():
            initial_config_contents[file_type] = engines.dut.run_cmd("sudo cat {}".format(file_path))

        with allure.step("Change initial content"):
            for file_type in ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES:
                edit_cmd = ClusterConsts.CONFIG_FILES_CHANGE[file_type].format(file_path=config_files_paths[file_type])
                engines.dut.run_cmd(edit_cmd)

        with allure.step("Install modified configurations"):
            for file_type in ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES:
                file_name = config_files_paths[file_type].split('/')[-1]
                sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.file_name[file_name].action_file_install(force=False)

        with allure.step("Running sdn factory reset"):
            sdn.factory_default.action_reset(param='force')

        verify_current_config_equals_given_config(sdn, engines, initial_config_contents, output_format)

        with allure.step("Reboot and verify configuration not changed"):
            result_obj, duration = OperationTime.save_duration('reboot', '', test_name, system.reboot.action_reboot)
            verify_current_config_equals_given_config(sdn, engines, initial_config_contents, output_format)

    finally:
        current_time = get_current_time(engines)
        execute_reset_factory(engines, system, devices.dut.reset_factory, "", current_time)


def verify_current_config_equals_given_config(sdn, engines, initial_config_contents, output_format):
    errors_list = []
    with allure.step("Verify config files content restored to initial"):
        for file_type in ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES:
            output = sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn()
            installed_file = ClusterTools.get_generated_file_name(output.returned_value, 'config')
            output = OutputParsingTool.parse_show_output_to_dict(sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            current_installed_config_path = output[installed_file]['path']
            current_config_content = engines.dut.run_cmd("sudo cat {}".format(current_installed_config_path))
            sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.file_name[installed_file].action_delete()
            initial_config_set = set(line.strip() for line in initial_config_contents[file_type].strip().split('\n') if line.strip())
            current_config_set = set(line.strip() for line in current_config_content.strip().split('\n') if line.strip())
            if initial_config_set != current_config_set:
                errors_list.append(f"Configuration mismatch in file {file_type}:\nInitial: {initial_config_set}\nCurrent: {current_config_set}")
        assert not errors_list, "\n\n".join(errors_list)


def execute_reset_factory(engines, system, operation, flag, current_time):
    logging.info("Current time: " + str(current_time))
    system.factory_default.action_reset(operation=operation, param=flag).verify_result()


def get_current_config_files_paths(sdn):
    files_dict = {}
    with allure.step("Fetch & Generate config files"):
        for file_type in ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES:
            output = sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn()
            installed_file = ClusterTools.get_generated_file_name(output.returned_value, 'config')
            output = OutputParsingTool.parse_show_output_to_dict(sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                 output_format=OutputFormat.json).get_returned_value()
            current_installed_config_path = output[installed_file]['path']
            files_dict[file_type] = current_installed_config_path
    return files_dict
