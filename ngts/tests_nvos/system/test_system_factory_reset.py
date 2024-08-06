import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tests_nvos.system.factory_reset.helpers import add_verification_data, \
    verify_cleanup_done, verify_the_setup_is_functional, get_current_time
from ngts.tests_nvos.system.factory_reset.post_steps import factory_reset_no_params_post_steps
from ngts.tests_nvos.system.factory_reset.pre_steps import factory_reset_no_params_pre_steps
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
def test_reset_factory_without_params(engines, devices, topology_obj, platform_params):
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
                6.1.	Start openSM
                6.2.	Run several show commands
                6.3.    Run set command & apply
    """
    current_time = get_current_time(engines)
    system = System()
    had_sm_before_test = False
    username = ''

    try:
        with allure.step('pre factory reset steps'):
            apply_and_save_port, current_time, just_apply_port, last_status_line, machine_type, not_apply_port, \
                username, init_cluster_status = factory_reset_no_params_pre_steps(engines, platform_params, system, devices)

        with allure.step("Run reset factory without params"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "", current_time)

        with allure.step('post factory reset steps'):
            factory_reset_no_params_post_steps(apply_and_save_port, engines, just_apply_port, last_status_line,
                                               machine_type, not_apply_port, system, init_cluster_status)

    finally:
        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username)

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=had_sm_before_test, dut=devices.dut)


@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
def test_reset_factory_keep_basic(engines, devices):
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
                6.1.	Start openSM
                6.2.	Run several show commands
                6.3.    Run set command & apply
    """
    try:
        with allure.step('Create System object'):
            system = System()

        # pre-init current time
        date_time_str = engines.dut.run_cmd("date").split(" ", 1)[1]
        current_time = datetime.strptime(date_time_str, '%d %b %Y %H:%M:%S %p %Z')

        with allure.step('Check is Juliet Device'):
            if not isinstance(devices.dut, JulietSwitch):
                with allure.step('Validate health status is OK'):
                    logger.info("Validate health status is OK")
                    system.validate_health_status(HealthConsts.OK)
                    last_status_line = system.health.history.retry_get_health_history_file_summary_line()

        with allure.step('Set description to eth0 port'):
            logger.info("Set description to eth0 port")
            mgmt_port = MgmtPort('eth0')
            mgmt_port.interface.set(NvosConst.DESCRIPTION, 'nvosdescription', apply=True).verify_result()
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
                mgmt_port.interface.show()).get_returned_value()

            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=NvosConst.DESCRIPTION,
                                                              expected_value='nvosdescription')

        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)

        with allure.step("Get current time"):
            update_timezone(system)
            current_time = get_current_time(engines)

        with allure.step("Run reset factory with keep basic param"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep basic", current_time)

        update_timezone(system)

        with allure.step("Validate health status and report"):
            validate_health_status_report(system, last_status_line)

    finally:
        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username, param=KEEP_BASIC)
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=NvosConst.DESCRIPTION,
                                                              expected_value='nvosdescription')
            mgmt_port.interface.unset(NvosConst.DESCRIPTION, apply=True).verify_result()

        update_timezone(system)

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=True, dut=devices.dut)


@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
def test_reset_factory_keep_all_config(engines, devices):
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
                6.1.	Start openSM
                6.2.	Run several show commands
                6.3.    Run set command & apply
    """
    try:
        port_type = devices.dut.switch_type.lower()
        with allure.step('Create System object'):
            system = System()

        with allure.step('Validate health status is OK'):
            logger.info("Validate health status is OK")
            system.validate_health_status(HealthConsts.OK)
            last_status_line = system.health.history.retry_get_health_history_file_summary_line()

        with allure.step(f'Set description to {port_type} ports'):
            logger.info(f"Set description to {port_type} ports")
            description = "with_keep_all_config_param"
            ports = Tools.RandomizationTool.select_random_ports(requested_ports_state="up", requested_ports_type=port_type,
                                                                num_of_ports_to_select=3).get_returned_value()
            apply_and_save_port = ports[0]
            just_apply_port = ports[1]
            not_apply_port = ports[2]

        with allure.step(f'Set and apply description to {port_type} port, save config after it'):
            logger.info(f"Set and apply description to {port_type} port, save config after it")
            apply_and_save_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
            TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
            NvueGeneralCli.save_config(engines.dut)
        with allure.step(f'Set and apply description to {port_type} port'):
            logger.info(f"Set and apply description to {port_type} port")
            just_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
        with allure.step(f'Set description to {port_type} port'):
            logger.info(f"Set description to {port_type} port")
            not_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=False).verify_result()
        with allure.step('Validate ports description'):
            logger.info("Validate ports description")
            validate_port_description(engines.dut, apply_and_save_port, description)
            validate_port_description(engines.dut, just_apply_port, description)
            validate_port_description(engines.dut, not_apply_port, "")

        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)

        with allure.step("Get current time"):
            update_timezone(system)
            current_time = get_current_time(engines)

        with allure.step("Run reset factory with keep all-config param"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep all-config", current_time)

        update_timezone(system)

        with allure.step('Validate ports description after reset factory'):
            logger.info("Validate ports description after reset factory")
            validate_port_description(engines.dut, apply_and_save_port, description)
            validate_port_description(engines.dut, just_apply_port, "")
            validate_port_description(engines.dut, not_apply_port, "")

        with allure.step("Validate health status and report"):
            validate_health_status_report(system, last_status_line)

    finally:
        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username, param=KEEP_ALL_CONFIG)

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=True, dut=devices.dut)


@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
def test_reset_factory_keep_only_files(engines, devices):
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
                6.1.	Start openSM
                6.2.	Run several show commands
                6.3.    Run set command & apply
    """
    try:
        port_type = devices.dut.switch_type.lower()
        with allure.step('Create System object'):
            system = System()
            date_time_str = engines.dut.run_cmd("date").split(" ", 1)[1]
            current_time = datetime.strptime(date_time_str, '%d %b %Y %H:%M:%S %p %Z')

        with allure.step('Validate health status is OK'):
            logger.info("Validate health status is OK")
            system.validate_health_status(HealthConsts.OK)
            last_status_line = system.health.history.retry_get_health_history_file_summary_line()

        with allure.step(f'Set description to {port_type} ports'):
            logger.info(f"Set description to {port_type} ports")
            description = "with_all_files_param"
            ports = Tools.RandomizationTool.select_random_ports(requested_ports_state="up",
                                                                num_of_ports_to_select=2).get_returned_value()
            apply_and_save_port = ports[0]
            just_apply_port = ports[1]
            not_apply_port = Tools.RandomizationTool.select_random_ports(requested_ports_state="down",
                                                                         num_of_ports_to_select=2).get_returned_value()[
                0]

        with allure.step(f'Set and apply description to {port_type} port, save config after it'):
            logger.info(f"Set and apply description to {port_type} port, save config after it")
            apply_and_save_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
            TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
            NvueGeneralCli.save_config(engines.dut)
        with allure.step(f'Set and apply description to {port_type} port'):
            logger.info(f"Set and apply description to {port_type} port")
            just_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
        with allure.step(f'Set description to {port_type} port'):
            logger.info(f"Set description to {port_type} port")
            not_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=False).verify_result()
        with allure.step('Validate ports description'):
            logger.info("Validate ports description")
            validate_port_description(engines.dut, apply_and_save_port, description)
            validate_port_description(engines.dut, just_apply_port, description)
            validate_port_description(engines.dut, not_apply_port, "")

        with allure.step("Add data before reset factory"):
            username = add_verification_data(engines.dut, system)

        with allure.step("Get current time"):
            update_timezone(system)
            current_time = get_current_time(engines)

        with allure.step("Run reset factory without params"):
            execute_reset_factory(engines, system, devices.dut.reset_factory, "keep only-files", current_time)

        update_timezone(system)

        with allure.step("Validate health status and report"):
            validate_health_status_report(system, last_status_line, False)

    finally:
        with allure.step("Verify the cleanup done successfully"):
            verify_cleanup_done(engines.dut, current_time, system, username, param=KEEP_ONLY_FILES)

        with allure.step("Verify the setup is functional"):
            verify_the_setup_is_functional(system, engines, had_sm_before_test=True, dut=devices.dut)


@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_error_flow_reset_factory_with_params(test_api, engines, devices, topology_obj):
    """
    This test is a temporary test - will be changed for GA
    :return:
    """
    TestToolkit.tested_api = test_api
    with allure.step("Create system object"):
        system = System(None)

    with allure.step("Run reset factory with params - expect failure"):
        logging.info("Run reset factory with params - expect failure")
        output = engines.dut.run_cmd("nv action reset system factory-default only-config")
        assert "Invalid parameter" in output, "Reset factory with param should fail"
        # system.factory_default.action_reset(param="only-config").verify_result(should_succeed=False)


def execute_reset_factory(engines, system, operation, flag, current_time):
    logging.info("Current time: " + str(current_time))
    system.factory_default.action_reset(operation=operation, param=flag).verify_result()
