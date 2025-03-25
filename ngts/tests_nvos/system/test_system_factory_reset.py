import random

import pytest

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.RegressionConfigurations import RegressionConfigurations
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tests_nvos.system.factory_reset.helpers import verify_cleanup_done, verify_the_setup_is_functional
from ngts.tests_nvos.system.factory_reset.post_steps import factory_reset_no_params_post_steps
from ngts.tests_nvos.system.factory_reset.pre_steps import (factory_reset_no_params_pre_steps,
                                                            factory_reset_keep_basic_pre_steps,
                                                            factory_reset_general_pre_steps)
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime


@pytest.mark.timeout(50 * MINUTE)
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_reset_factory_without_params(engines, devices, topology_obj, platform_params, test_api, has_loopbox, setup_name, standalone_system, test_name):
    """
    Validate reset factory without params cleanup done as expected

        Test flow:
            1. set description to ib/nvl ports:
                - set, apply and save configuration
                - set and apply
                - set
            2. Validate ports description
            3. Add data
            4. Run reset factory without params
            5. After system is up again, verify the cleanup done successfully
            6. Verify the setup is functional:
                6.1.	Run several show commands
                6.2.    Run set command & apply
    """
    TestToolkit.tested_api = test_api
    system = System()
    cluster = Cluster()
    expected_reboot_reason = SystemConsts.REBOOT_REASON_REBOOT

    with allure.step('pre factory reset steps'):
        apply_and_save_port, current_time, just_apply_port, health_status, machine_type, not_apply_port, \
            username, init_cluster_status = factory_reset_no_params_pre_steps(engines, platform_params, system, devices,
                                                                              has_loopbox, setup_name, standalone_system)

    with allure.step("Run reset factory without params"):
        duration = execute_reset_factory(engines, system, devices.dut.reset_factory, "", current_time, test_name=test_name)

    with allure.step("Check reboot reason event in system events"):
        reboot_reason = OutputParsingTool.get_reboot_reason_system_events(system)
        assert expected_reboot_reason in reboot_reason, 'Reboot reason is {} instead of {}'.\
            format(reboot_reason, expected_reboot_reason)

    with allure.step('post factory reset steps'):
        factory_reset_no_params_post_steps(apply_and_save_port, engines, just_apply_port, health_status,
                                           machine_type, not_apply_port, system, init_cluster_status, has_loopbox,
                                           devices, setup_name, standalone_system)
        RegressionConfigurations.configure_ports_to_legacy(engine=engines.dut, apply=True, throw_exception=True)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, username)

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)

    with allure.step("Verify operation time"):
        OperationTime.verify_operation_time(duration, devices.dut.reset_factory).verify_result()

    with allure.step('Check if NVL Switch'):
        if devices.dut.switch_type == NvosConst.NVL_SWITCH_TYPE:
            cluster.unset(apply=True)


@pytest.mark.timeout(25 * MINUTE, func_only=True)
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_reset_factory_keep_basic(engines, devices, test_api, test_name):
    """
    Validate reset factory with keep basic param cleanup done as expected

        Test flow:
            1. set description to eth0 port:
                - set, apply and save configuration
                - set and apply
                - set
            2. Validate ports description
            3. Add data
            4. Run reset factory with keep basic param
            5. After system is up again, verify the cleanup done successfully
            6. Verify the setup is functional:
                6.1.	Run several show commands
                6.2.    Run set command & apply
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System object'):
        system = System()

    with allure.step('pre factory reset steps'):
        current_time, username, health_status, mgmt_port, \
            output_dictionary_mgmt_show = factory_reset_keep_basic_pre_steps(engines, system)

    with allure.step("Run reset factory with keep basic param"):
        duration = execute_reset_factory(engines, system, devices.dut.reset_factory, "keep basic", current_time, test_name=test_name)

    update_timezone(system)

    with allure.step("Validate health status and report"):
        validate_health_status_report(system, health_status)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, username, param=KEEP_BASIC)

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary_mgmt_show,

                                                          field_name=NvosConst.DESCRIPTION,

                                                          expected_value='nvosdescription')

        mgmt_port.interface.unset(NvosConst.DESCRIPTION, apply=True).verify_result()

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)

    with allure.step("Verify operation time"):
        OperationTime.verify_operation_time(duration, devices.dut.reset_factory).verify_result()


@pytest.mark.timeout(25 * MINUTE)
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_reset_factory_keep_all_config(engines, devices, test_api, test_name):
    """
    Validate reset factory with keep all config param cleanup done as expected

        Test flow:
            1. set description to ib/nvl ports:
                - set, apply and save configuration
                - set and apply
                - set
            2. Validate ports description
            3. Add data
            4. Run reset factory with keep all config params
            5. After system is up again, verify the cleanup done successfully
            6. Verify the setup is functional:
                6.1.	Run several show commands
                6.2.    Run set command & apply
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System object'):
        system = System()

    with allure.step('pre factory reset steps'):
        health_status, current_time, apply_and_save_port, description, just_apply_port, \
            not_apply_port, username = factory_reset_general_pre_steps(engines, devices, system)

    with allure.step("Run reset factory with keep all-config param"):
        duration = execute_reset_factory(engines, system, devices.dut.reset_factory, "keep all-config", current_time, test_name=test_name)

    update_timezone(system)

    with allure.step('Validate ports description after reset factory'):
        logger.info("Validate ports description after reset factory")
        validate_port_description(engines.dut, apply_and_save_port, description)
        validate_port_description(engines.dut, just_apply_port, "")
        validate_port_description(engines.dut, not_apply_port, "")

    with allure.step("Validate health status and report"):
        validate_health_status_report(system, health_status)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, username, param=KEEP_ALL_CONFIG)

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)

    with allure.step("Verify operation time"):
        OperationTime.verify_operation_time(duration, devices.dut.reset_factory).verify_result()


@pytest.mark.timeout(30 * MINUTE)
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_reset_factory_keep_only_files(engines, devices, test_api, test_name):
    """
    Validate reset factory with keep only files param cleanup done as expected

        Test flow:
            1. set description to ib/nvl ports:
                - set, apply and save configuration
                - set and apply
                - set
            2. Validate ports description
            3. Add data
            4. Run reset factory with keep only files param
            5. After system is up again, verify the cleanup done successfully
            6. Verify the setup is functional:
                6.1.	Run several show commands
                6.2.    Run set command & apply
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System object'):
        system = System()

    with allure.step('pre factory reset steps'):
        health_status, current_time, apply_and_save_port, description, just_apply_port, \
            not_apply_port, username = factory_reset_general_pre_steps(engines, devices, system)

    with allure.step("Run reset factory keep only-files"):
        duration = execute_reset_factory(engines, system, devices.dut.reset_factory, "keep only-files", current_time, test_name=test_name)

    update_timezone(system)

    with allure.step("Validate health status and report"):
        validate_health_status_report(system, health_status)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, username, param=KEEP_ONLY_FILES)

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)

    with allure.step("Verify operation time"):
        OperationTime.verify_operation_time(duration, devices.dut.reset_factory).verify_result()


@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_error_flow_reset_factory_with_params(test_api, engines, devices, topology_obj):
    """
    This test is a temporary test - will be changed for GA
    :return:
    """
    TestToolkit.tested_api = test_api
    with allure.step("Run reset factory with params - expect failure"):
        logging.info("Run reset factory with params - expect failure")
        output = engines.dut.run_cmd("nv action reset system factory-default only-config")
        assert "Invalid parameter" in output, "Reset factory with param should fail"


def execute_reset_factory(engines, system, operation, flag, current_time, topology_obj=None, test_name=''):
    logging.info("Current time: " + str(current_time))
    topology_obj = topology_obj or (TestToolkit.topology_obj if TestToolkit else None)
    result_obj = system.factory_default.action_reset(operation=operation, param=flag, topology_obj=topology_obj, test_name=test_name)
    result_obj.verify_result()
    return result_obj.duration


def get_last_status_line(system):
    with allure.step('Validate health status is OK'):
        logger.info("Validate health status is OK")
        try:
            system.validate_health_status(HealthConsts.OK)
            return system.health.history.retry_get_health_history_file_summary_line()
        except BaseException:
            return ""
