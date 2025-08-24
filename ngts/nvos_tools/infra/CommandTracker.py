import time
import logging
import inspect
from typing import List, Tuple, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class CommandTracker:
    """
    Tracks command execution times and provides analytics.
    Designed to wrap existing engine run_cmd methods without modifying them.
    """

    def __init__(self):
        self.executed_commands: List[Tuple[str, float, str]] = []  # [(cmd, response_time, status)]
        self.is_enabled = True
        self._wrapped_engines = set()  # Track which engines we've already wrapped
        self._monkey_patching_enabled = False  # Track if monkey patching is active
        self._visited_ids = set()  # Track visited objects to avoid cycles

    def clear(self):
        """Clear all tracked commands - call at start of each test."""
        self.executed_commands.clear()

    def enable(self):
        """Enable command tracking."""
        self.is_enabled = True

    def disable(self):
        """Disable command tracking."""
        self.is_enabled = False

    def get_commands(self) -> List[Tuple[str, float, str]]:
        """Get all tracked commands."""
        return self.executed_commands.copy()

    def get_total_time(self) -> float:
        """Get total execution time for all commands."""
        return sum(cmd[1] for cmd in self.executed_commands)

    def get_slowest_commands(self, n: int = 5) -> List[Tuple[str, float, str]]:
        """Get the N slowest commands."""
        return sorted(self.executed_commands, key=lambda x: x[1], reverse=True)[:n]

    def track_command(self, original_run_cmd):
        """
        Decorator to wrap an engine's run_cmd method and track execution time.

        Usage:
            engine.run_cmd = command_tracker.track_command(engine.run_cmd)
        """
        @wraps(original_run_cmd)
        def wrapper(cmd, *args, **kwargs):
            if not self.is_enabled:
                return original_run_cmd(cmd, *args, **kwargs)

            start_time = time.time()
            status = "success"

            try:
                result = original_run_cmd(cmd, *args, **kwargs)
                return result
            except Exception as e:
                status = f"error: {type(e).__name__}"
                raise
            finally:
                end_time = time.time()
                response_time = end_time - start_time

                # Log and store the command data
                self.executed_commands.append((cmd, response_time, status))
                logger.debug(f"Command tracked: '{cmd}' took {response_time:.3f}s - {status}")

        return wrapper

    def track_command_set(self, original_run_cmd_set):
        """
        Decorator to wrap an engine's run_cmd_set method and track execution time.
        Tracks the first command in the set as the primary command.

        Usage:
            engine.run_cmd_set = command_tracker.track_command_set(engine.run_cmd_set)
        """
        @wraps(original_run_cmd_set)
        def wrapper(cmd_set, *args, **kwargs):
            if not self.is_enabled:
                return original_run_cmd_set(cmd_set, *args, **kwargs)

            # Get the primary command (first command in the set)
            primary_cmd = cmd_set[0] if cmd_set and len(cmd_set) > 0 else "Empty command set"

            start_time = time.time()
            status = "success"

            try:
                result = original_run_cmd_set(cmd_set, *args, **kwargs)
                return result
            except Exception as e:
                status = f"error: {type(e).__name__}"
                raise
            finally:
                end_time = time.time()
                response_time = end_time - start_time

                # Log and store the primary command data
                # Include indicator that this was a command set
                cmd_display = f"{primary_cmd} [cmd_set of {len(cmd_set)} commands]"
                self.executed_commands.append((cmd_display, response_time, status))
                logger.debug(f"Command set tracked: '{primary_cmd}' ({len(cmd_set)} commands) took {response_time:.3f}s - {status}")

        return wrapper

    def track_send_config_set(self, original_send_config_set):
        """
        Decorator to wrap an engine's send_config_set method and track execution time.
        This is used by IB devices for reboot commands.
        Tracks the first command in the set as the primary command.

        Usage:
            engine.send_config_set = command_tracker.track_send_config_set(engine.send_config_set)
        """
        @wraps(original_send_config_set)
        def wrapper(cmd_set, *args, **kwargs):
            if not self.is_enabled:
                return original_send_config_set(cmd_set, *args, **kwargs)

            # Get the primary command (first command in the set)
            primary_cmd = cmd_set[0] if cmd_set and len(cmd_set) > 0 else "Empty command set"

            start_time = time.time()
            status = "success"

            try:
                result = original_send_config_set(cmd_set, *args, **kwargs)
                return result
            except Exception as e:
                status = f"error: {type(e).__name__}"
                raise
            finally:
                end_time = time.time()
                response_time = end_time - start_time

                # Log and store the primary command data
                # Include indicator that this was a send_config_set
                cmd_display = f"{primary_cmd} [send_config_set of {len(cmd_set)} commands]"
                self.executed_commands.append((cmd_display, response_time, status))
                logger.debug(f"Send config set tracked: '{primary_cmd}' ({len(cmd_set)} commands) took {response_time:.3f}s - {status}")

        return wrapper

    def wrap_engine(self, engine):
        """
        Wrap an engine's run_cmd, run_cmd_set, and send_config_set methods with tracking.
        Safe to call multiple times on the same engine.

        Args:
            engine: Any object with run_cmd, run_cmd_set, and/or send_config_set methods

        Returns:
            The same engine (for chaining)
        """
        engine_id = id(engine)

        # Check if already wrapped to avoid double-wrapping
        if engine_id not in self._wrapped_engines:
            wrapped_methods = []

            # Wrap run_cmd if it exists
            if hasattr(engine, 'run_cmd'):
                engine.run_cmd = self.track_command(engine.run_cmd)
                wrapped_methods.append('run_cmd')

            # Wrap run_cmd_set if it exists
            if hasattr(engine, 'run_cmd_set'):
                engine.run_cmd_set = self.track_command_set(engine.run_cmd_set)
                wrapped_methods.append('run_cmd_set')

            # Wrap send_config_set if it exists (used by IB devices for reboot)
            if hasattr(engine, 'send_config_set'):
                engine.send_config_set = self.track_send_config_set(engine.send_config_set)
                wrapped_methods.append('send_config_set')

            # Also wrap underlying Netmiko connection if exposed as `engine.engine`
            # This ensures commands issued via send_command/send_command_timing are tracked
            try:
                inner = getattr(engine, 'engine', None)
                if inner is not None:
                    inner_id = id(inner)
                    if inner_id not in self._wrapped_engines:
                        netmiko_wrapped = False
                        if hasattr(inner, 'send_command'):
                            inner.send_command = self.track_command(inner.send_command)
                            netmiko_wrapped = True
                        if hasattr(inner, 'send_command_timing'):
                            inner.send_command_timing = self.track_command(inner.send_command_timing)
                            netmiko_wrapped = True
                        if netmiko_wrapped:
                            self._wrapped_engines.add(inner_id)
                            wrapped_methods.append('engine.send_command')
                            wrapped_methods.append('engine.send_command_timing')
            except Exception:
                # Be conservative: failure to wrap inner engine should not break test execution
                pass

            if wrapped_methods:
                self._wrapped_engines.add(engine_id)
                methods_str = ', '.join(wrapped_methods)
                logger.debug(f"Wrapped engine {engine.__class__.__name__} methods: {methods_str}")
            else:
                logger.warning(f"Engine {engine.__class__.__name__} has no run_cmd, run_cmd_set, or send_config_set methods")

        return engine

    def wrap_engines_recursively(self, obj, max_depth=3, _current_depth=0):
        """
        Recursively search for and wrap any engines in an object structure.

        Args:
            obj: Object to search (could be engines dict, DottedDict, etc.)
            max_depth: Maximum recursion depth to prevent infinite loops
            _current_depth: Internal parameter for recursion tracking
        """
        # Reset visited set at the start of a new traversal
        if _current_depth == 0:
            self._visited_ids.clear()

        if _current_depth >= max_depth:
            return

        # Avoid infinite recursion on cyclic graphs
        try:
            obj_id = id(obj)
        except Exception:
            obj_id = None
        if obj_id is not None:
            if obj_id in self._visited_ids:
                return
            self._visited_ids.add(obj_id)

        if hasattr(obj, 'run_cmd') or hasattr(obj, 'run_cmd_set') or hasattr(obj, 'send_config_set'):
            # This looks like an engine, wrap it
            self.wrap_engine(obj)
        elif isinstance(obj, dict):
            # Search dictionary values
            for value in obj.values():
                self.wrap_engines_recursively(value, max_depth, _current_depth + 1)
        elif isinstance(obj, (list, tuple, set)):
            # Search iterable items
            for item in obj:
                self.wrap_engines_recursively(item, max_depth, _current_depth + 1)
        elif hasattr(obj, '__dict__'):
            # Prefer __dict__ to avoid triggering properties/descriptors
            for attr_name, attr_value in obj.__dict__.items():
                if attr_name.startswith('_'):
                    continue
                if callable(attr_value):
                    continue
                self.wrap_engines_recursively(attr_value, max_depth, _current_depth + 1)
            # Fallback: inspect non-data attributes on the class without invoking properties
            for attr_name in dir(obj):
                if attr_name.startswith('_'):
                    continue
                # Skip if already seen via __dict__
                if attr_name in obj.__dict__:
                    continue
                try:
                    class_attr = getattr(type(obj), attr_name, None)
                    # Skip properties and data descriptors to avoid executing code
                    if isinstance(class_attr, property) or inspect.isdatadescriptor(class_attr):
                        continue
                    # Accessing here should be safe (non-descriptor), but guard anyway
                    attr_value = getattr(obj, attr_name, None)
                except Exception:
                    continue
                if callable(attr_value):
                    continue
                self.wrap_engines_recursively(attr_value, max_depth, _current_depth + 1)
        else:
            # Last resort: try to iterate attributes carefully
            try:
                for attr_name in dir(obj):
                    if attr_name.startswith('_'):
                        continue
                    class_attr = getattr(type(obj), attr_name, None)
                    if isinstance(class_attr, property) or inspect.isdatadescriptor(class_attr):
                        continue
                    attr_value = getattr(obj, attr_name, None)
                    if callable(attr_value):
                        continue
                    self.wrap_engines_recursively(attr_value, max_depth, _current_depth + 1)
            except Exception:
                return

    def log_summary(self):
        """Log a summary of command execution statistics."""
        if not self.executed_commands:
            logger.info("No commands tracked")
            return

        total_time = self.get_total_time()
        avg_time = total_time / len(self.executed_commands)
        slowest = self.get_slowest_commands(3)

        logger.info(f"Command Execution Summary:")
        logger.info(f"  Total commands: {len(self.executed_commands)}")
        logger.info(f"  Total time: {total_time:.3f}s")
        logger.info(f"  Average time: {avg_time:.3f}s")
        logger.info(f"  Slowest commands:")
        for i, (cmd, time_taken, status) in enumerate(slowest, 1):
            logger.info(f"    {i}. {cmd[:50]}... - {time_taken:.3f}s ({status})")

    def enable_monkey_patching(self):
        """Enable monkey patching for automatic engine wrapping."""
        if not self._monkey_patching_enabled:
            _monkey_patch_engine_classes()
            self._monkey_patching_enabled = True
            logger.debug("Monkey patching enabled for automatic command tracking")


# Global instance for easy access
command_tracker = CommandTracker()


# Monkey patch engine classes to auto-wrap new instances
def _monkey_patch_engine_classes():
    """
    Monkey patch common engine classes to automatically wrap new instances.
    This ensures that any engine created during testing gets tracking.
    """
    try:
        from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
        from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine

        # Store original __init__ methods
        original_linux_init = LinuxSshEngine.__init__
        original_proxy_init = ProxySshEngine.__init__

        def wrapped_linux_init(self, *args, **kwargs):
            result = original_linux_init(self, *args, **kwargs)
            command_tracker.wrap_engine(self)
            return result

        def wrapped_proxy_init(self, *args, **kwargs):
            result = original_proxy_init(self, *args, **kwargs)
            command_tracker.wrap_engine(self)
            return result

        LinuxSshEngine.__init__ = wrapped_linux_init
        ProxySshEngine.__init__ = wrapped_proxy_init

        logger.debug("Monkey patched engine classes for automatic command tracking")

    except ImportError as e:
        logger.warning(f"Could not monkey patch engine classes: {e}")


# Monkey patching is disabled by default to avoid affecting other test suites
# To enable, call: command_tracker.enable_monkey_patching()
# _monkey_patch_engine_classes()
