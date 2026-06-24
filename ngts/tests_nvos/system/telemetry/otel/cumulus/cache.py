"""Thread-safe telemetry data store for Cumulus OTLP tests.

Stores OTLP, CLI, and GNMI payloads keyed by convention (key must contain ``otel``,
``cli``, ``gnmi``, or ``gnmi_on_change``).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_cli_lock = threading.RLock()
_otel_lock = threading.RLock()
_gnmi_lock = threading.RLock()
_gnmi_on_change_lock = threading.RLock()

_cli_data: Dict[str, Any] = {}
_otel_data: Dict[str, Any] = {}
_gnmi_data: Dict[str, Any] = {}
_gnmi_on_change_data: Dict[str, Any] = {}


def _container_for_key(key: str):
    if "cli" in key:
        return _cli_data, _cli_lock
    if "otel" in key:
        return _otel_data, _otel_lock
    if "gnmi_on_change" in key:
        return _gnmi_on_change_data, _gnmi_on_change_lock
    if "gnmi" in key:
        return _gnmi_data, _gnmi_lock
    raise ValueError(
        f"Invalid telemetry cache key {key!r}: must contain "
        "'cli', 'otel', 'gnmi', or 'gnmi_on_change'"
    )


def add_data(key: str, value: Any) -> None:
    """Store ``value`` under ``key`` in the appropriate container."""
    container, lock = _container_for_key(key)
    with lock:
        container[key] = value
        logger.debug("Telemetry cache: stored key=%s", key)


def get_data(key: str) -> Any:
    """Return cached data for ``key``."""
    container, lock = _container_for_key(key)
    with lock:
        if key not in container:
            raise KeyError(f"Telemetry cache key {key!r} not found")
        return container[key]


def get_data_optional(key: str) -> Optional[Any]:
    try:
        return get_data(key)
    except (KeyError, ValueError):
        return None


def clear_data() -> None:
    """Clear all telemetry cache containers."""
    with _cli_lock, _otel_lock, _gnmi_lock, _gnmi_on_change_lock:
        _cli_data.clear()
        _otel_data.clear()
        _gnmi_data.clear()
        _gnmi_on_change_data.clear()
    logger.info("Telemetry cache cleared")


def merge_otel_data(key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-merge ``patch`` into existing OTLP cache entry (or create)."""
    existing = get_data_optional(key) or {}
    if not isinstance(existing, dict):
        raise TypeError(f"Cache entry {key!r} is not a dict")
    merged = {**existing, **patch}
    add_data(key, merged)
    return merged
