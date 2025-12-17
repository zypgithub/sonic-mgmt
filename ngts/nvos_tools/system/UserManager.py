"""
User Manager Module

This module provides centralized user creation and management utilities
for test automation. It handles user creation with various roles and permissions.

Usage:
    from ngts.nvos_tools.system.UserManager import (
        create_user,
        add_user_with_system_admin,
        add_user_with_sudo,
        get_all_users,
        get_user_role
    )

    # Create a basic user
    username, password = create_user(system, 'testuser')

    # Create admin users
    admin_user, admin_pass = add_user_with_system_admin(engines, 'admin1')
    sudo_user, sudo_pass = add_user_with_sudo(engines, 'sudouser')
"""

import logging
from typing import Optional, Tuple, List

from ngts.nvos_constants.constants_nvos import ApiType, CumulusConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


_cached_system = None


def _get_system():
    """Get a cached System object configured for NVUE API. Creates once, reuses thereafter."""
    global _cached_system
    if _cached_system is None:
        _cached_system = System(force_api=ApiType.NVUE)
    return _cached_system


def create_user(system: System, username: str, password: Optional[str] = None,
                apply: bool = False, dut_engine=None) -> Tuple[str, str]:
    """
    Create a new user in the system with specified or randomly generated credentials.

    This function creates a new user using the AAA user management interface.
    If no password is provided, a random password will be generated. The function
    can either apply the changes immediately or defer the application.

    Args:
        system: System object that provides AAA user management functionality
        username: The username to create
        password: Password for the user. If None, a random password will be generated
        apply: Whether to apply the changes immediately (default: False)
        dut_engine: DUT engine for applying config (optional, uses default if None)

    Returns:
        Tuple of (username, password) where password is either provided or generated

    Example:
        >>> from ngts.nvos_tools.system.System import System
        >>> system = System()
        >>> username, password = create_user(system, "testuser")
        >>> print(f"Created user {username} with password {password}")
    """
    with allure.step(f'Create user "{username}"'):
        if password is None:
            username, password = system.aaa.user.set_new_user(username=username, apply=False)
        else:
            username, _ = system.aaa.user.set_new_user(username=username, password=password, apply=False)

        if apply:
            if dut_engine:
                NvueGeneralCli.apply_config(dut_engine, ask_for_confirmation='-y')
            else:
                NvueGeneralCli.apply_config(TestToolkit.engines.dut, ask_for_confirmation='-y')

        return username, password


def add_user_with_system_admin(engines, username: str, password: Optional[str] = None,
                               apply: bool = False) -> Tuple[str, str]:
    """
    Add a new user with system-admin role/permissions.

    Creates a user and assigns them the system-admin role, which provides
    administrative privileges on the system.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to create
        password: Password for the user. If None, a random password will be generated
        apply: Whether to apply the changes immediately (default: False)

    Returns:
        Tuple of (username, password)

    Example:
        >>> admin_user, admin_pass = add_user_with_system_admin(engines, 'system_admin')
    """
    with allure.step(f'Add user "{username}" with system-admin permissions'):
        system = _get_system()

        _user, _password = system.aaa.user.set_new_user(
            username=username,
            password=password,
            role=CumulusConsts.ROLE_SYSTEM_ADMIN,
            apply=False
        )

        if apply:
            NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation='-y')

            # Verify user was created with correct role
            users = get_all_users(engines)
            assert username in users, f"User {username} was not created"

            user_role = get_user_role(engines, username)
            assert user_role == CumulusConsts.ROLE_SYSTEM_ADMIN, \
                f"User {username} was not assigned system-admin role, got: {user_role}"

        return _user, _password


def add_user_with_sudo(engines, username: str, password: Optional[str] = None) -> Tuple[str, str]:
    """
    Add a new user with sudo permissions.

    Creates a user and adds them to the sudo group, providing elevated
    privileges for system administration tasks.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to create
        password: Password for the user. If None, a random password will be generated

    Returns:
        Tuple of (username, password)

    Raises:
        Exception: If user creation or sudo group addition fails

    Example:
        >>> super_user, super_pass = add_user_with_sudo(engines, 'super')
        >>> # User now has sudo privileges
    """
    with allure.step(f'Add user "{username}" with sudo permissions'):
        system = _get_system()

        if password is None:
            username, password = system.aaa.user.set_new_user(username=username, apply=False)
        else:
            username, _ = system.aaa.user.set_new_user(username=username, password=password, apply=False)

        # Apply configuration
        logger.info(f"Applying config for user '{username}' and all pending users")
        try:
            apply_result = NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation='-y')
            logger.debug(f"Apply config result: {apply_result}")

            if apply_result and ("Invalid config" in str(apply_result) or "Error" in str(apply_result)):
                error_msg = f"Apply config failed with error: {apply_result}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Apply config failed: {e}")
            raise

        # Add user to sudo group
        logger.info(f"Adding user '{username}' to sudo group")
        sudo_result = engines.dut.run_cmd(f'sudo usermod -aG sudo {username}')
        logger.debug(f"Sudo group addition result: {sudo_result}")

        # Verify user was created and has sudo permissions
        users = get_all_users(engines)
        assert username in users, f"User {username} was not created"

        groups = engines.dut.run_cmd(f'groups {username}')
        assert 'sudo' in groups, f"User {username} was not added to sudo group"

        return username, password


def get_all_users(engines) -> List[str]:
    """
    Get all users configured in the system using the NVUE API.

    Args:
        engines: The test engines object containing the DUT connection

    Returns:
        List of usernames configured in the system

    Example:
        >>> users = get_all_users(engines)
        >>> print(f"Configured users: {users}")
    """
    with allure.step('Get all users'):
        system = _get_system()
        users = list(system.aaa.user.parse_show(dut_engine=engines.dut).keys())
        return users


def get_user_role(engines, username: str) -> Optional[str]:
    """
    Get the role of a specific user using the NVUE API.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to get the role for

    Returns:
        The role of the user, or None if not found

    Example:
        >>> role = get_user_role(engines, "admin")
        >>> print(f"User role: {role}")
    """
    with allure.step(f'Get user role for "{username}"'):
        system = _get_system()
        user = system.aaa.user.user_id[username]
        user_info = user.parse_show(dut_engine=engines.dut)
        return user_info.get('role')


def delete_user(engines, username: str, apply: bool = True) -> bool:
    """
    Delete a user from the system.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to delete
        apply: Whether to apply the changes immediately (default: True)

    Returns:
        True if successful, False otherwise

    Example:
        >>> success = delete_user(engines, "testuser")
    """
    with allure.step(f'Delete user "{username}"'):
        try:
            system = _get_system()
            system.aaa.user.user_id[username].unset(apply=False)

            if apply:
                NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation='-y')

            return True
        except Exception as e:
            logger.error(f"Failed to delete user {username}: {e}")
            return False


def create_user_with_role(engines, username: str, role: str,
                          password: Optional[str] = None,
                          apply: bool = True) -> Tuple[str, str]:
    """
    Create a user with a specific role.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to create
        role: The role to assign (e.g., 'system-admin', custom role name)
        password: Password for the user. If None, a random password will be generated
        apply: Whether to apply the changes immediately (default: True)

    Returns:
        Tuple of (username, password)

    Example:
        >>> user, pwd = create_user_with_role(engines, "monitor_user", "nvue-monitor")
    """
    with allure.step(f'Create user "{username}" with role "{role}"'):
        system = _get_system()

        _user, _password = system.aaa.user.set_new_user(
            username=username,
            password=password,
            role=role,
            apply=False
        )

        if apply:
            NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation='-y')

        return _user, _password


def verify_user_exists(engines, username: str) -> bool:
    """
    Verify that a user exists in the system.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to verify

    Returns:
        True if user exists, False otherwise

    Example:
        >>> if verify_user_exists(engines, "admin"):
        ...     print("Admin user exists")
    """
    with allure.step(f'Verify user "{username}" exists'):
        users = get_all_users(engines)
        return username in users


def get_user_info(engines, username: str) -> dict:
    """
    Get detailed information about a specific user.

    Args:
        engines: The test engines object containing the DUT connection
        username: The username to get info for

    Returns:
        Dictionary containing user information

    Example:
        >>> info = get_user_info(engines, "admin")
        >>> print(f"User info: {info}")
    """
    with allure.step(f'Get user info for "{username}"'):
        system = _get_system()
        user = system.aaa.user.user_id[username]
        return user.parse_show(dut_engine=engines.dut)
