import logging
from contextlib import contextmanager, nullcontext
from typing import Any, Optional
from ngts.helpers.system_helpers import PrefixEngine
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger(__name__)


def _find_engine_key(engine: Any) -> Optional[str]:
    """Return the key in TestToolkit.engines that holds this engine (identity match)."""
    if TestToolkit.engines is None:
        return None
    for key in dir(TestToolkit.engines):
        if key.startswith("_"):
            continue
        try:
            if getattr(TestToolkit.engines, key) is engine:
                return key
        except (AttributeError, TypeError):
            continue
    return None


@contextmanager
def sudo_scope(engine: Optional[Any] = None):
    """
    Context manager that runs all engine commands with sudo for the duration of the block.
    :param engine: Engine to wrap (e.g. engines.dut). If None, uses TestToolkit.get_engine().
    """
    if engine is None:
        engine = TestToolkit.get_engine()
    key = _find_engine_key(engine)
    if key is None:
        key = TestToolkit.active_dut
        original = getattr(TestToolkit.engines, key, None)
        if original is not engine:
            logger.debug(
                "sudo_scope: engine not found in TestToolkit.engines by identity; "
                "replacing %s (active_dut) with PrefixEngine(provided engine)", key
            )
    else:
        original = getattr(TestToolkit.engines, key)
    wrapper = PrefixEngine(engine, 'sudo')
    try:
        setattr(TestToolkit.engines, key, wrapper)
        yield wrapper
    finally:
        setattr(TestToolkit.engines, key, original)


def sudo_scope_if(condition: bool, engine: Optional[Any] = None):
    """
    Context manager that uses sudo_scope when condition is True, otherwise a no-op.
    Use this to avoid if/else branches when sudo is only needed for certain devices (e.g. eth).
    :param condition: When True, enter sudo_scope; when False, do nothing.
    :param engine: Passed to sudo_scope when condition is True. If None, uses TestToolkit.get_engine().
    """
    return sudo_scope(engine) if condition else nullcontext()
