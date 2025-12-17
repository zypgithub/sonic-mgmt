"""
AAA Server Configuration Module

This module provides centralized AAA (Authentication, Authorization, Accounting)
server configuration utilities for security-related tests. It consolidates
AAA configuration functionality from test_disconnect_fix_threading.py and test_fips_aaa.py.

Supports configuration for:
- RADIUS servers
- TACACS+ servers
- LDAP servers
- Authentication order management

Usage:
    from ngts.tests_nvos.general.security.security_test_tools.aaa_server_config import (
        configure_radius_server,
        configure_tacacs_server,
        configure_ldap_server,
        set_authentication_order,
        unset_authentication_order
    )

    # Configure RADIUS server
    configure_radius_server(engines)

    # Set authentication order
    set_authentication_order(engines, ['radius', 'local'])
"""

import json
import logging
import re
from typing import List, Optional

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tests_nvos.general.security.radius.constants import CLRadiusPhysicalServer
from ngts.tests_nvos.general.security.tacacs.constants import TacacsPhysicalServer
from ngts.tests_nvos.general.security.test_aaa_ldap.ldap_servers_info import LdapServers

# Import FIPS utilities for disconnect handling
from ngts.tests_nvos.general.security.security_test_tools.security_test_utils import (
    is_fips_enabled,
    _apply_config_with_expected_disconnect
)

logger = logging.getLogger(__name__)


_cached_system = None


def _get_system():
    """Get a cached System object configured for NVUE API. Creates once, reuses thereafter."""
    global _cached_system
    if _cached_system is None:
        _cached_system = System(force_api=ApiType.NVUE)
    return _cached_system


# =============================================================================
# RADIUS Server Configuration
# =============================================================================

def configure_radius_server(engines, apply: bool = True,
                            is_fips_mode: bool = True) -> None:
    """
    Configure RADIUS server for testing using predefined server constants.

    Args:
        engines: Test engines object
        apply: Whether to apply configuration (default: True)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> configure_radius_server(engines)
    """
    system = _get_system()
    radius_config = CLRadiusPhysicalServer.SERVER_IPV4

    with allure.step('Configure the RADIUS server'):
        radius_obj = system.aaa.radius
        radius_server = system.aaa.radius.server.server_id[radius_config.hostname]
        radius_server.set(AaaConsts.PORT, radius_config.port)
        radius_server.set(AaaConsts.SECRET, radius_config.secret)
        radius_server.set(AaaConsts.PRIORITY, radius_config.priority)
        if is_fips_mode:
            # FIPS mode requires CHAP authentication
            radius_obj.set(AaaConsts.AUTH_TYPE, AaaConsts.CHAP)

        if apply:
            _apply_config(engines, is_fips_mode, "RADIUS server config")


def set_radius_server(engines, server_ip: str, secret: Optional[str] = None,
                      priority: Optional[int] = None, port: Optional[int] = None,
                      apply: bool = False, is_fips_mode: bool = True) -> None:
    """
    Set/configure a RADIUS server using System AAA object.

    Args:
        engines: Test engines object
        server_ip: IP address of the RADIUS server
        secret: Shared secret (optional)
        priority: Server priority (optional)
        port: Server port (optional)
        apply: Whether to apply immediately (default: False)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> set_radius_server(engines, "10.0.0.1", secret="radiussecret", priority=1, apply=True)
    """
    with allure.step(f'Set RADIUS server {server_ip}'):
        system = _get_system()
        radius_server = system.aaa.radius.server.server_id[server_ip]

        if secret:
            radius_server.set(AaaConsts.SECRET, secret, dut_engine=engines.dut, apply=False).ignore_result()
        if priority is not None:
            radius_server.set(AaaConsts.PRIORITY, priority, dut_engine=engines.dut, apply=False).ignore_result()
        if port is not None:
            radius_server.set(AaaConsts.PORT, port, dut_engine=engines.dut, apply=False).ignore_result()

        if apply:
            _apply_config(engines, is_fips_mode, f"Set RADIUS server {server_ip}")


def unset_radius_server(engines, server_ip: str, apply: bool = False,
                        is_fips_mode: bool = True) -> None:
    """
    Unset/remove a RADIUS server using System AAA object.

    Args:
        engines: Test engines object
        server_ip: IP address of the RADIUS server to remove
        apply: Whether to apply immediately (default: False)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> unset_radius_server(engines, "10.0.0.1", apply=True)
    """
    with allure.step(f'Unset RADIUS server {server_ip}'):
        system = _get_system()
        system.aaa.radius.server.server_id[server_ip].unset(
            dut_engine=engines.dut, apply=False
        ).ignore_result()

        if apply:
            _apply_config(engines, is_fips_mode, f"Unset RADIUS server {server_ip}")


# =============================================================================
# TACACS+ Server Configuration
# =============================================================================

def configure_tacacs_server(engines, apply: bool = True,
                            is_fips_mode: bool = True) -> None:
    """
    Configure TACACS+ server for testing using predefined server constants.

    Args:
        engines: Test engines object
        apply: Whether to apply configuration (default: True)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> configure_tacacs_server(engines)
    """
    with allure.step('Configure TACACS+ server'):
        system = _get_system()
        tacacs_config = TacacsPhysicalServer.SERVER_IPV4
        tacacs_server = system.aaa.tacacs.server.server_id[tacacs_config.hostname]
        tacacs_server.set(AaaConsts.PORT, tacacs_config.port)
        tacacs_server.set(AaaConsts.SECRET, tacacs_config.secret)
        tacacs_server.set(AaaConsts.PRIORITY, tacacs_config.priority)

        if apply:
            _apply_config(engines, is_fips_mode, "TACACS+ server config")


def set_tacacs_server(engines, server_ip: str, secret: Optional[str] = None,
                      priority: Optional[int] = None, port: Optional[int] = None,
                      apply: bool = False, is_fips_mode: bool = True) -> None:
    """
    Set/configure a TACACS+ server using System AAA object.

    Args:
        engines: Test engines object
        server_ip: IP address of the TACACS+ server
        secret: Shared secret (optional)
        priority: Server priority (optional)
        port: Server port (optional)
        apply: Whether to apply immediately (default: False)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> set_tacacs_server(engines, "10.0.0.1", secret="tacacssecret", priority=1, apply=True)
    """
    with allure.step(f'Set TACACS+ server {server_ip}'):
        system = _get_system()
        tacacs_server = system.aaa.tacacs.server.server_id[server_ip]

        if secret:
            tacacs_server.set(AaaConsts.SECRET, secret, dut_engine=engines.dut, apply=False).ignore_result()
        if priority is not None:
            tacacs_server.set(AaaConsts.PRIORITY, priority, dut_engine=engines.dut, apply=False).ignore_result()
        if port is not None:
            tacacs_server.set(AaaConsts.PORT, port, dut_engine=engines.dut, apply=False).ignore_result()

        if apply:
            _apply_config(engines, is_fips_mode, f"Set TACACS+ server {server_ip}")


def unset_tacacs_server(engines, server_ip: str, apply: bool = False,
                        is_fips_mode: bool = True) -> None:
    """
    Unset/remove a TACACS+ server using System AAA object.

    Args:
        engines: Test engines object
        server_ip: IP address of the TACACS+ server to remove
        apply: Whether to apply immediately (default: False)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> unset_tacacs_server(engines, "10.0.0.1", apply=True)
    """
    with allure.step(f'Unset TACACS+ server {server_ip}'):
        system = _get_system()
        system.aaa.tacacs.server.server_id[server_ip].unset(
            dut_engine=engines.dut, apply=False
        ).ignore_result()

        if apply:
            _apply_config(engines, is_fips_mode, f"Unset TACACS+ server {server_ip}")


# =============================================================================
# LDAP Server Configuration
# =============================================================================

def configure_ldap_server(engines, apply: bool = True,
                          is_fips_mode: bool = True) -> None:
    """
    Configure LDAP server for testing using predefined server constants.

    Args:
        engines: Test engines object
        apply: Whether to apply configuration (default: True)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> configure_ldap_server(engines)
    """
    with allure.step('Configure LDAP server'):
        system = _get_system()
        ldap_config = LdapServers.PHYSICAL_SERVER

        # Configure global LDAP settings
        ldap_obj = system.aaa.ldap
        ldap_obj.set(AaaConsts.PORT, ldap_config.port)
        ldap_obj.set(AaaConsts.SECRET, ldap_config.secret)
        ldap_obj.set('bind-dn', ldap_config.bind_dn)
        ldap_obj.set('base-dn', ldap_config.base_dn)
        ldap_obj.set('version', ldap_config.version)
        ldap_obj.set('timeout-bind', ldap_config.timeout_bind)
        ldap_obj.set('timeout-search', ldap_config.timeout_search)

        # Configure server-specific settings
        ldap_server = ldap_obj.server.server_id[ldap_config.hostname]
        ldap_server.set(AaaConsts.PRIORITY, ldap_config.priority)

        if apply:
            _apply_config(engines, is_fips_mode, "LDAP server config")


def set_ldap_server(engines, server_ip: str, priority: Optional[int] = None,
                    apply: bool = False, is_fips_mode: bool = True) -> None:
    """
    Set/configure an LDAP server using System AAA object.

    Args:
        engines: Test engines object
        server_ip: IP address of the LDAP server
        priority: Server priority (optional)
        apply: Whether to apply immediately (default: False)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> set_ldap_server(engines, "10.0.0.1", priority=1, apply=True)
    """
    with allure.step(f'Set LDAP server {server_ip}'):
        system = _get_system()
        ldap_server = system.aaa.ldap.server.server_id[server_ip]

        if priority is not None:
            ldap_server.set(AaaConsts.PRIORITY, priority, dut_engine=engines.dut, apply=False).ignore_result()

        if apply:
            _apply_config(engines, is_fips_mode, f"Set LDAP server {server_ip}")


def unset_ldap_server(engines, server_ip: str, apply: bool = False,
                      is_fips_mode: bool = True) -> None:
    """
    Unset/remove an LDAP server using System AAA object.

    Args:
        engines: Test engines object
        server_ip: IP address of the LDAP server to remove
        apply: Whether to apply immediately (default: False)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Example:
        >>> unset_ldap_server(engines, "10.0.0.1", apply=True)
    """
    with allure.step(f'Unset LDAP server {server_ip}'):
        system = _get_system()
        system.aaa.ldap.server.server_id[server_ip].unset(
            dut_engine=engines.dut, apply=False
        ).ignore_result()

        if apply:
            _apply_config(engines, is_fips_mode, f"Unset LDAP server {server_ip}")


# =============================================================================
# Authentication Order Management
# =============================================================================

def set_authentication_order(engines, order_list: List[str], apply: bool = True,
                             is_fips_mode: bool = True,
                             verify: bool = True) -> Optional[str]:
    """
    Set the authentication order for the system.

    Args:
        engines: Test engines object
        order_list: List of authentication methods in order (e.g., ['radius', 'local'])
        apply: Whether to apply immediately (default: True)
        is_fips_mode: Use FIPS-aware apply method (default: True)
        verify: Verify the order after setting (default: True)

    Returns:
        Apply command result if apply=True, None otherwise

    Example:
        >>> set_authentication_order(engines, ['radius', 'local'])
        >>> set_authentication_order(engines, ['tacacs', 'local'])
    """
    with allure.step(f'Set authentication order: {order_list}'):
        system = _get_system()

        # Set authentication order without applying
        system.aaa.authentication.set_authentication_order(
            order_list,
            dut_engine=engines.dut,
            apply=False
        )

        result = None
        if apply:
            result = _apply_config(engines, is_fips_mode, f"Set auth order {order_list}")

        if verify and apply:
            verify_authentication_order(engines, order_list)

        return result


def unset_authentication_order(engines, apply: bool = True,
                               is_fips_mode: bool = True,
                               verify: bool = True) -> Optional[str]:
    """
    Unset/reset the authentication order to default.

    Args:
        engines: Test engines object
        apply: Whether to apply immediately (default: True)
        is_fips_mode: Use FIPS-aware apply method (default: True)
        verify: Verify the order after unsetting (default: True)

    Returns:
        Apply command result if apply=True, None otherwise

    Example:
        >>> unset_authentication_order(engines)
    """
    with allure.step('Unset authentication order'):
        system = _get_system()

        # Unset authentication order without applying
        system.aaa.authentication.unset_authentication_order(
            dut_engine=engines.dut,
            apply=False
        )

        result = None
        if apply:
            result = _apply_config(engines, is_fips_mode, "Unset auth order")

        if verify and apply:
            verify_authentication_order(engines, None)

        return result


def verify_authentication_order(engines, expected_order: Optional[List[str]]) -> bool:
    """
    Verify the operational authentication order matches expected.

    Args:
        engines: Test engines object
        expected_order: Expected authentication order (list) or None for unset/default

    Returns:
        True if matches expected, False otherwise

    Example:
        >>> if verify_authentication_order(engines, ['radius', 'local']):
        ...     print("Auth order verified")
    """
    with allure.step(f'Verify operational auth order is {expected_order}'):
        try:
            auth_status_json = engines.dut.run_cmd("nv show system aaa authentication -o json")
            logger.debug(f"Authentication order (JSON):\n{auth_status_json}")

            auth_data = json.loads(auth_status_json)
            operational_order = auth_data.get('order', None)

            if expected_order is None:
                # Expecting unset - should be None, [], or ['local'] (default)
                if operational_order is None or operational_order == []:
                    logger.info("✓ Authentication order successfully unset (no order field)")
                    return True
                elif operational_order == ['local']:
                    logger.info("✓ Authentication order reset to default ['local']")
                    return True
                else:
                    logger.warning(f"✗ Unexpected auth order after unset: {operational_order}")
                    return False
            else:
                # Expecting specific order
                if operational_order == expected_order:
                    logger.info(f"✓ Operational auth order matches expected: {operational_order}")
                    return True
                else:
                    logger.warning(f"✗ Operational auth order mismatch! Expected: {expected_order}, Got: {operational_order}")
                    return False

        except Exception as e:
            logger.warning(f"Could not verify auth order (may be disconnected): {e}")
            return False


# =============================================================================
# AAA Server Cleanup
# =============================================================================

def cleanup_test_aaa_servers(engines, apply: bool = True,
                             is_fips_mode: bool = True) -> bool:
    """
    Remove any RADIUS, TACACS, and LDAP servers that were added during tests
    but are not part of the original configuration.

    Original servers (kept):
    - RADIUS: CLRadiusPhysicalServer.SERVER_IPV4.hostname
    - TACACS: TacacsPhysicalServer.SERVER_IPV4.hostname
    - LDAP: LdapServers.PHYSICAL_SERVER.hostname

    Args:
        engines: Test engines object
        apply: Whether to apply immediately (default: True)
        is_fips_mode: Use FIPS-aware apply method (default: True)

    Returns:
        True if any changes were made, False otherwise

    Example:
        >>> if cleanup_test_aaa_servers(engines):
        ...     print("Cleaned up test AAA servers")
    """
    with allure.step('Cleanup test AAA servers'):
        system = _get_system()

        # Get original server hostnames
        original_radius_server = CLRadiusPhysicalServer.SERVER_IPV4.hostname
        original_tacacs_server = TacacsPhysicalServer.SERVER_IPV4.hostname
        original_ldap_server = LdapServers.PHYSICAL_SERVER.hostname

        logger.info(f"Original RADIUS server: {original_radius_server}")
        logger.info(f"Original TACACS server: {original_tacacs_server}")
        logger.info(f"Original LDAP server: {original_ldap_server}")

        changes_made = False

        # Get current config
        try:
            config_output = engines.dut.run_cmd("nv config show -o commands")
            logger.debug("Got config output, parsing for AAA servers...")
        except Exception as e:
            logger.warning(f"Failed to get config output: {e}")
            config_output = ""

        # Parse and cleanup RADIUS servers
        try:
            radius_server_pattern = re.compile(r'nv set system aaa radius server (\S+)')
            radius_servers = set(radius_server_pattern.findall(config_output))
            logger.info(f"Found RADIUS servers in config: {radius_servers}")

            for server_ip in radius_servers:
                if server_ip != original_radius_server:
                    logger.info(f"Removing non-original RADIUS server: {server_ip}")
                    system.aaa.radius.server.server_id[server_ip].unset(
                        apply=False, dut_engine=engines.dut
                    ).ignore_result()
                    changes_made = True
        except Exception as e:
            logger.warning(f"Failed to cleanup RADIUS servers: {e}")

        # Parse and cleanup TACACS servers
        try:
            tacacs_server_pattern = re.compile(r'nv set system aaa tacacs server (\S+)')
            tacacs_servers = set(tacacs_server_pattern.findall(config_output))
            logger.info(f"Found TACACS servers in config: {tacacs_servers}")

            for server_ip in tacacs_servers:
                if server_ip != original_tacacs_server:
                    logger.info(f"Removing non-original TACACS server: {server_ip}")
                    system.aaa.tacacs.server.server_id[server_ip].unset(
                        apply=False, dut_engine=engines.dut
                    ).ignore_result()
                    changes_made = True
        except Exception as e:
            logger.warning(f"Failed to cleanup TACACS servers: {e}")

        # Parse and cleanup LDAP servers
        try:
            ldap_server_pattern = re.compile(r'nv set system aaa ldap server (\S+)')
            ldap_servers = set(ldap_server_pattern.findall(config_output))
            logger.info(f"Found LDAP servers in config: {ldap_servers}")

            for server_ip in ldap_servers:
                if server_ip != original_ldap_server:
                    logger.info(f"Removing non-original LDAP server: {server_ip}")
                    system.aaa.ldap.server.server_id[server_ip].unset(
                        apply=False, dut_engine=engines.dut
                    ).ignore_result()
                    changes_made = True
        except Exception as e:
            logger.warning(f"Failed to cleanup LDAP servers: {e}")

        # Apply changes if any were made
        if changes_made and apply:
            logger.info("Applying AAA server cleanup changes")
            _apply_config(engines, is_fips_mode, "AAA server cleanup")
            logger.info("AAA server cleanup completed")
        elif changes_made:
            logger.info("AAA server cleanup changes pending (not applied)")
        else:
            logger.info("No AAA server cleanup needed")

        return changes_made


# =============================================================================
# Helper Functions
# =============================================================================

def _apply_config(engines, use_fips_aware: bool, operation_name: str) -> str:
    """
    Apply configuration with optional FIPS-aware handling.

    Args:
        engines: Test engines object
        use_fips_aware: Whether to check FIPS mode and use appropriate apply
        operation_name: Name of operation for logging

    Returns:
        Result of apply command
    """
    with allure.step(f'Apply config: {operation_name}'):
        if use_fips_aware and is_fips_enabled(engines):
            return _apply_config_with_expected_disconnect(engines.dut, f"{operation_name} in FIPS mode")
        else:
            return NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation='-y')
