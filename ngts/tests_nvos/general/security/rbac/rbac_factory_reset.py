import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, RbacConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.rbac.helpers import verify_rbac_classes_in_role
from ngts.tests_nvos.system.aaa.helpers import create_new_user

from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.system
@pytest.mark.rbac
@pytest.mark.security_ci
def rbac_factory_reset_no_params_check():
    """
    Verify that:
    when saving config with RBAC settings – config and RBAC settings should be cleared after factory reset

    1. Create RBAC class
    2. Create RBAC role
    3. Create user with the new role
    4. Save configuration
    5. Perform factory reset
    6. Verify no RBAC class in show
    7. Verify no RBAC role in show
    8. Verify user does not exist or has default permissions
    """
    engines = TestToolkit.engines
    system = System()

    test_class_name = "TestClass"
    test_role_name = "TestRole"
    interface_path = "/interface/"

    with allure.step('Create RBAC class'):
        system.aaa.class_rbac.set_new_class(test_class_name, RbacConsts.ALLOW, interface_path, permission='all')

    with allure.step('Create RBAC role'):
        system.aaa.role.set_new_role(test_role_name, test_class_name, apply=True)

    with allure.step('Create user with new role'):
        test_user, test_password = create_new_user(role=test_role_name, apply=True)

    with allure.step('Save configuration'):
        NvueGeneralCli.save_config(engines.dut)

    yield  # factory reset

    with allure.step('Verify after factory reset'):
        with allure.step('Verify no RBAC class in show'):
            class_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.class_rbac.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(class_output, test_class_name).verify_result(False)

        with allure.step('Verify no RBAC role in show'):
            role_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.role.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(role_output, test_role_name).verify_result(False)

        with allure.step('Verify user does not exist or has default permissions'):
            user_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.user.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(user_output, test_user).verify_result(False)

    yield  # to prevent StopIteration on the 2nd next() call


@pytest.mark.system
@pytest.mark.rbac
@pytest.mark.security_ci
def rbac_factory_reset_keep_roles():
    """
    Verify that:
    when saving config with RBAC roles and classes, they should be preserved after factory reset

    1. Create RBAC class
    2. Create RBAC role
    3. Create user with the new role
    4. Save configuration
    5. Perform factory reset
    6. Verify RBAC class exists in show output
    7. Verify RBAC role exists in show output
    8. Verify user exists with the assigned role
    """
    engines = TestToolkit.engines
    system = System()

    test_class_name = "TestClass"
    test_role_name = "TestRole"
    interface_path = "/interface/"

    with allure.step('Create RBAC class'):
        system.aaa.class_rbac.set_new_class(test_class_name, RbacConsts.ALLOW, interface_path, permission='all')

    with allure.step('Create RBAC role'):
        system.aaa.role.set_new_role(test_role_name, test_class_name, apply=True)

    with allure.step('Create user with new role'):
        test_user, test_password = create_new_user(role=test_role_name, apply=True)

    with allure.step('Save configuration'):
        NvueGeneralCli.save_config(engines.dut)

    yield  # factory reset

    with allure.step('Verify after factory reset'):
        with allure.step('Verify RBAC class in show'):
            class_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.class_rbac.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(class_output, test_class_name).verify_result()

        with allure.step('Verify RBAC role in show'):
            role_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.role.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(role_output, test_role_name).verify_result()

        verify_rbac_classes_in_role(system, test_role_name, [test_class_name])

        with allure.step('Verify user does exist or has default permissions'):
            user_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.user.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(user_output, test_user).verify_result()

    yield  # to prevent StopIteration on the 2nd next() call


@pytest.mark.system
@pytest.mark.rbac
@pytest.mark.security_ci
def rbac_upgrade_check(engines, test_api):
    """
    Verify that:
    when saving config with RBAC settings – config and RBAC settings should be kept after upgrade

    1. Create RBAC class
    2. Create RBAC role
    3. Create user with the new role
    4. Save configuration
    5. Upgrade
    6. Verify RBAC class exists in show output
    7. Verify RBAC role exists in show output
    8. Verify user exists with the assigned role
    9. Verify permissions are still applied correctly
    """
    TestToolkit.tested_api = test_api
    system = System()

    test_class_name = "TestClass"
    test_role_name = "TestRole"
    interface_path = "/interface/"

    with allure.step('Create RBAC class'):
        system.aaa.rbac_class.set_new_class(test_class_name, RbacConsts.ALLOW, interface_path, permission='all')

    with allure.step('Create RBAC role'):
        system.aaa.role.set_new_role(test_role_name, test_class_name, apply=True)

    with allure.step('Create user with new role'):
        test_user, test_password = create_new_user(role=test_role_name, apply=True)

    with allure.step('Save configuration'):
        NvueGeneralCli.save_config(engines.dut)

    yield  # upgrade

    with allure.step('Verify after upgrade'):
        with allure.step('Verify RBAC class in show'):
            class_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.aaa.class_rbac.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(class_output, test_class_name).verify_result()

        with allure.step('Verify RBAC role in show'):
            role_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.role.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(role_output, test_role_name).verify_result()

        verify_rbac_classes_in_role(system, test_role_name, [test_class_name])

        with allure.step('Verify user does exist or has default permissions'):
            user_output = OutputParsingTool.parse_json_str_to_dictionary(system.aaa.user.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(user_output, test_user).verify_result()

    yield  # to prevent StopIteration on the 2nd next() call
