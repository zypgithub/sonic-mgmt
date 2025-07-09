import logging

from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.tests_nvos.general.security.rbac.command_testers import InterfaceCommandTester, SystemCommandTester, \
    PlatformCommandTester
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.Devices.IbDevice import JulietNonScaleoutSwitch
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

PERMISSION_LEVELS = {
    'ro': {'allowed': ['show'], 'denied': ['set', 'unset', 'action']},
    'rw': {'allowed': ['show', 'set', 'unset'], 'denied': ['action']},
    'act': {'allowed': ['action'], 'denied': ['show', 'set', 'unset']},
    'all': {'allowed': ['show', 'set', 'unset', 'action'], 'denied': []}
}


def create_user_connection(engines, username, password):
    return ConnectionTool.create_ssh_conn(engines.dut.ip, username, password).get_returned_value()


def change_class_permissions(system, class_name, command_path, permission):
    with allure.step(f"Configuring {permission} permission for {class_name} on {command_path}"):
        system.aaa.class_rbac.class_id[class_name].change_permission(command_path, permission, apply=True)
        # output = OutputParsingTool.parse_auto_output_to_dict(
        #     system.aaa.class_rbac.class_id[class_name].show_command_path(command_path=command_path)).get_returned_value()
        # ValidationTool.verify_field_value_exist_in_output_dict(output, 'permission')


def verify_permissions(results, permission, is_denied=False):
    if permission not in PERMISSION_LEVELS:
        raise ValueError(f"Invalid permission level: {permission}")

    for op in PERMISSION_LEVELS[permission]['allowed']:
        assert results[
            op] != is_denied, f"{'Denied' if is_denied else 'Allowed'} operation {op} failed for {permission} permission"
    for op in PERMISSION_LEVELS[permission]['denied']:
        assert results[
            op] == is_denied, f"{'Allowed' if is_denied else 'Denied'} operation {op} failed for {permission} permission"


def verify_user_permissions_generic(engines, username, password, permission, test_func, *args, is_denied=False):
    with allure.step(f"Verifying {'denied ' if is_denied else ''}permissions for user {username}"):
        user_engine = create_user_connection(engines, username, password)
        results = test_func(*args, user_engine)
        verify_permissions(results, permission, is_denied)
        return results


def verify_user_permissions_on_interface(engines, username, password, selected_port, permission, fail_on_eth0=False):
    results = verify_user_permissions_generic(engines, username, password, permission, run_commands_on_interface,
                                              selected_port)

    if fail_on_eth0:
        with allure.step("Testing additional capabilities"):
            mgmt_port = Port('eth0')
            TestToolkit.update_tested_ports([mgmt_port])
            other_results = run_commands_on_interface(mgmt_port, create_user_connection(engines, username, password))
            assert not any(other_results.values()), "User should not be able to perform any actions on other interface"


def verify_user_permissions_on_denied_interface(engines, username, password, denied_port, permission):
    verify_user_permissions_generic(engines, username, password, permission, run_commands_on_interface, denied_port,
                                    is_denied=True)


def verify_user_permissions_on_system(engines, devices, username, password, permission):
    results = verify_user_permissions_generic(engines, username, password, permission, run_commands_on_system)

    with allure.step("Testing additional capabilities"):
        platform_results = run_commands_on_platform(create_user_connection(engines, username, password), devices)
        assert not any(platform_results.values()), "User should not be able to perform any actions on platform"


def run_commands_on_interface(selected_port, user_engine):
    tester = InterfaceCommandTester(user_engine, selected_port)
    return tester.test_commands()


def run_commands_on_system(user_engine):
    tester = SystemCommandTester(user_engine)
    return tester.test_commands()


def run_commands_on_platform(user_engine, devices):
    tester = PlatformCommandTester(user_engine, isinstance(devices.dut, JulietNonScaleoutSwitch))
    return tester.test_commands()


def cleanup_rbac_resources(system, users=None, roles=None, classes=None):
    """
    Cleanup RBAC resources.

    Args:
        system (System): The system object.
        users (list): List of usernames to unset.
        roles (list): List of role names to unset.
        classes (list): List of class names to unset.
    """
    with allure.step("Cleaning up created RBAC resources"):
        if users:
            for user in users:
                system.aaa.user.user_id[user].action_disconnect()
                system.aaa.user.unset(op_param=user)

        if roles:
            for role in roles:
                system.aaa.role.unset(op_param=role)

        if classes:
            for class_name in classes:
                system.aaa.class_rbac.unset(op_param=class_name, apply=True)


def verify_groups(dut_engine, username, groups):
    with allure.step(f"Verifying groups for user {username}"):
        output = dut_engine.run_cmd('groups')
        missing_groups = [group for group in groups if group not in output]
        assert not missing_groups, f"The following groups are missing from the string: {output}"


def verify_rbac_classes_in_role(system, role_name, classes_to_verify, expected_results=None, user_engine=None):
    """
    Verifies that specific RBAC classes exist in the role's RBAC class configuration.
    """
    # Parse the output of the RBAC class configuration for the role
    output_dict = OutputParsingTool.parse_json_str_to_dictionary(
        system.aaa.role.role_id[role_name].class_rbac.show(dut_engine=user_engine)
    ).get_returned_value()

    # Default all expected results to True if not explicitly provided
    if expected_results is None:
        expected_results = [True] * len(classes_to_verify)

    # Verify each class against its expected result
    for class_name, expected in zip(classes_to_verify, expected_results):
        ValidationTool.verify_field_value_exist_in_output_dict(output_dict, class_name).verify_result(expected)
