from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.Restrictions import Restrictions
import logging
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class Authentication(BaseComponent):
    def __init__(self, parent_obj=None):
        resource_name = 'authentication-order' if TestToolkit.is_eth_dut() else 'authentication'
        BaseComponent.__init__(self, parent=parent_obj, path=f'/{resource_name}')
        self.restrictions = Restrictions(self)

        # Configuration storage for version-aware authentication order handling
        self._authentication_order = {}  # Legacy format: {priority: method}
        self._new_format_methods = []    # New format: [method1, method2, ...]
        self._use_new_format = False     # Format flag

    def add_authentication_order(self, priority, auth_method, dut_engine=None, apply=False, ask_for_confirmation=None, **kwargs):
        """
        Legacy API: add_authentication_order(10, 'radius')
        Maintains backward compatibility
        """
        with allure.step(f'Add authentication order {priority}: {auth_method}'):
            logger.info(f'Adding authentication order with priority {priority}: {auth_method}')
            self._authentication_order[priority] = auth_method
            self._use_new_format = False

            # Execute the appropriate command based on version
            if self._should_use_new_format():
                # Convert to new format and execute
                methods_list = [method for _, method in sorted(self._authentication_order.items())]
                return self._execute_new_format_command(methods_list, dut_engine, apply, ask_for_confirmation, **kwargs)
            else:
                # Use legacy format
                return self.set(str(priority), auth_method, dut_engine=dut_engine, apply=apply,
                                ask_for_confirmation=ask_for_confirmation, **kwargs)

    def set_authentication_order(self, methods, dut_engine=None, apply=False, ask_for_confirmation=None, **kwargs):
        """
        New API: set_authentication_order(['radius', 'local'])
        Uses modern format where supported
        """
        with allure.step(f'Set authentication order methods: {methods}'):
            logger.info(f'Setting authentication order methods: {methods}')
            if not isinstance(methods, list):
                methods = [methods] if isinstance(methods, str) else list(methods)

            self._new_format_methods = methods
            self._use_new_format = True

            # Execute the appropriate command based on version
            if self._should_use_new_format():
                return self._execute_new_format_command(methods, dut_engine, apply, ask_for_confirmation, **kwargs)
            else:
                # Convert to legacy format and execute
                return self._execute_legacy_format_commands(methods, dut_engine, apply, ask_for_confirmation, **kwargs)

    def _should_use_new_format(self):
        """
        Determine if we should use the new authentication order format
        by delegating to the device's method.

        Returns:
            bool: True if new format should be used, False for legacy format
        """
        with allure.step('Check if should use new auth format'):
            logger.info('Authentication: Checking if should use new format...')

            if not TestToolkit.is_eth_dut():
                logger.info('Authentication: Not an ETH device, using NVOS format')
                return False  # NVOS devices use different format

            try:
                # Delegate to the device's _should_use_new_format method
                if hasattr(TestToolkit, 'devices') and TestToolkit.devices and hasattr(TestToolkit.devices, 'dut'):
                    return TestToolkit.devices.dut._should_use_new_format()
                else:
                    logger.warning('Authentication: TestToolkit.devices.dut not available, using LEGACY format')
                    return False
            except Exception as e:
                logger.exception(f'Authentication: Exception during format check - using LEGACY format: {e}')
                return False

    def _execute_new_format_command(self, methods, dut_engine=None, apply=False, ask_for_confirmation=None, **kwargs):
        """
        Execute new format command: nv set system aaa authentication order radius local
        Note: We need to unset first to avoid duplicate entries in the order.

        This method is only called for ETH devices with version >= 5.15.0.
        """
        with allure.step('Execute new format command'):
            methods_str = ' '.join(methods)

            # For ETH devices, we need to use the authentication resource (not authentication-order)
            # and set the order property. This should generate: nv set system aaa authentication order radius local
            auth_resource = BaseComponent(self.parent_obj, path='/authentication')

            # First unset the existing order to avoid duplicates (don't apply yet)
            try:
                logger.info('Unsetting existing authentication order before setting new one')
                auth_resource.unset('order', dut_engine=dut_engine, apply=False, ask_for_confirmation=None)
            except Exception as e:
                logger.warning(f'Failed to unset authentication order (may not exist): {e}')

            # Now set the new order
            return auth_resource.set('order', methods_str, dut_engine=dut_engine, apply=apply,
                                     ask_for_confirmation=ask_for_confirmation, **kwargs)

    def _execute_legacy_format_commands(self, methods, dut_engine=None, apply=False, ask_for_confirmation=None, **kwargs):
        """
        Execute legacy format commands:
        First clear existing authentication-order configuration, then set new ones:
        nv unset system aaa authentication-order
        nv set system aaa authentication-order 10 radius
        nv set system aaa authentication-order 20 local
        """
        with allure.step('Execute legacy format commands'):
            logger.info(f'Executing legacy format authentication order for methods: {methods}')

            results = []

            # First, clear existing authentication-order configuration to avoid conflicts
            logger.info('Clearing existing authentication-order configuration before setting new one')
            clear_result = self.unset('', dut_engine=dut_engine, apply=False,
                                      ask_for_confirmation=None, **kwargs)
            results.append(clear_result)

            # Then set the new authentication order methods
            for i, method in enumerate(methods, start=1):
                priority = i * 10  # 10, 20, 30, etc.
                # Apply only on the last command
                is_last = (i == len(methods))
                result = self.set(str(priority), method, dut_engine=dut_engine,
                                  apply=apply if is_last else False,
                                  ask_for_confirmation=ask_for_confirmation if is_last else None, **kwargs)
                results.append(result)

            return results[-1] if results else None  # Return the last result

    def is_using_new_format(self):
        """
        Returns True if the configuration is using the new format
        """
        return self._use_new_format

    def get_methods_list(self):
        """
        Get the list of authentication methods in order
        """
        if self._use_new_format:
            return self._new_format_methods.copy()
        else:
            return [method for _, method in sorted(self._authentication_order.items())]

    def clear(self):
        """
        Clear all authentication order configuration
        """
        with allure.step('Clear authentication order config'):
            logger.info('Clearing authentication order configuration')
            self._authentication_order.clear()
            self._new_format_methods.clear()
            self._use_new_format = False

    def unset_authentication_order(self, dut_engine=None, apply=False, ask_for_confirmation=None, **kwargs):
        """
        Version-aware unset of authentication order configuration
        """
        with allure.step('Unset authentication order'):
            logger.info('Unsetting authentication order configuration')

            try:
                if self._should_use_new_format():
                    # New format: unset the order configuration
                    auth_resource = BaseComponent(self.parent_obj, path='/authentication')
                    result = auth_resource.unset('order', dut_engine=dut_engine, apply=apply,
                                                 ask_for_confirmation=ask_for_confirmation, **kwargs)
                else:
                    # Legacy format: unset authentication-order entirely
                    result = self.unset('', dut_engine=dut_engine, apply=apply,
                                        ask_for_confirmation=ask_for_confirmation, **kwargs)

                # Clear internal state
                self.clear()
                return result

            except Exception as e:
                logger.warning(f'Error during unset, trying fallback approach: {e}')
                # Fallback: try unsetting the entire resource
                result = self.unset('', dut_engine=dut_engine, apply=apply,
                                    ask_for_confirmation=ask_for_confirmation, **kwargs)
                self.clear()
                return result
