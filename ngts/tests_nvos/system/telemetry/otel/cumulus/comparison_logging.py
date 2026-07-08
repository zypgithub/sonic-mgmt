"""Structured INFO logging for OTLP artifact inventory and OTEL vs CLI comparisons."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional
from collections.abc import Mapping

import ngts.tools.test_utils.allure_utils as allure

logger = logging.getLogger(__name__)


def _log_sorted_names(section_title: str, names: Iterable[str]) -> None:
    """Emit one INFO line per name (no truncation)."""
    sorted_names = sorted(names)
    logger.info("  --- %s (%d) ---", section_title, len(sorted_names))
    for name in sorted_names:
        logger.info("    %s", name)


def _log_metric_attribute_counts(prefix: str, metrics: Mapping[str, Any]) -> None:
    """Log each metric with its attribute-key count (no truncation)."""
    logger.info("  --- %s (%d metrics) ---", prefix, len(metrics))
    for name in sorted(metrics.keys()):
        attr_count = len(metrics[name]) if isinstance(metrics[name], Mapping) else 0
        logger.info("    %s[%s]: %d attribute keys", prefix, name, attr_count)


def log_otel_cli_comparison(
    metric: str,
    *,
    otel_value: Any,
    reference_value: Any,
    reference_label: str = "CLI",
    deviation_pct: Optional[float] = None,
    max_deviation_pct: Optional[float] = None,
    attr_key: Any = None,
    passed: bool = True,
) -> None:
    """Log one OTEL vs reference comparison line (visible at INFO in pytest live logs)."""
    status = "PASS" if passed else "FAIL"
    attr_part = f" attr={attr_key!r}" if attr_key is not None else ""
    dev_part = ""
    if deviation_pct is not None:
        cap = f" (max {max_deviation_pct}%)" if max_deviation_pct is not None else ""
        dev_part = f" deviation={deviation_pct:.2f}%{cap}"
    logger.info(
        "OTEL vs %s [%s] %s%s: otel=%r %s=%r%s",
        reference_label,
        status,
        metric,
        attr_part,
        otel_value,
        reference_label.lower(),
        reference_value,
        dev_part,
    )


def log_parsed_otel_payload_summary(
    otel_payload: Dict[str, Any],
    *,
    hostname: str,
    collector_label: str = "mgmt VRF",
) -> None:
    """Log full parsed OTLP cache inventory after artifact download/parse (uncapped)."""
    metrics_ts = otel_payload.get("metrics_timestamps") or {}
    intf_stats = otel_payload.get("intf_stats") or {}
    histograms = otel_payload.get("histograms") or {}
    cp_stats = otel_payload.get("cp_stats") or {}
    platform_stats = otel_payload.get("platform_stats") or {}
    hist_list = otel_payload.get("hist_list") or []

    with allure.step(f"Log parsed OTEL cache summary ({collector_label})"):
        logger.info("=" * 72)
        logger.info("OTEL PARSED CACHE SUMMARY — %s (hostname=%s)", collector_label, hostname)
        logger.info("  metrics_timestamps:  %d unique metric names", len(metrics_ts))
        logger.info("  platform_stats:      %d metrics", len(platform_stats))
        logger.info("  intf_stats:          %d metrics", len(intf_stats))
        logger.info("  histograms:          %d metrics", len(histograms))
        logger.info("  cp_stats:            %d metrics", len(cp_stats))
        logger.info("  hist_list objects:   %d", len(hist_list))

        if metrics_ts:
            _log_metric_attribute_counts("metrics_timestamps", metrics_ts)

        if platform_stats:
            _log_metric_attribute_counts("platform_stats", platform_stats)

        if intf_stats:
            _log_metric_attribute_counts("intf_stats", intf_stats)

        if histograms:
            _log_metric_attribute_counts("histograms", histograms)

        if cp_stats:
            for name in sorted(cp_stats.keys()):
                series = next(iter(cp_stats[name].values()), [])
                logger.info(
                    "    cp_stats[%s]: %d samples (first=%s last=%s)",
                    name,
                    len(series),
                    series[0] if series else "n/a",
                    series[-1] if series else "n/a",
                )

        logger.info("=" * 72)


def log_cli_cache_summary(cli_payload: Dict[str, Any], *, hostname: str) -> None:
    """Summarize CLI snapshots stored alongside OTEL cache."""
    with allure.step("Log CLI cache summary"):
        logger.info("=" * 72)
        logger.info("CLI CACHE SUMMARY — hostname=%s", hostname)
        ingress = cli_payload.get("ingress_stats") or {}
        egress = cli_payload.get("egress_stats") or {}
        hist_snap = cli_payload.get("hist_snap") or {}
        cp_stats = cli_payload.get("cp_stats") or {}
        logger.info("  ingress_stats interfaces: %d", len(ingress))
        if ingress:
            _log_sorted_names("ingress_stats interfaces", ingress.keys())
        logger.info("  egress_stats interfaces:  %d", len(egress))
        if egress:
            _log_sorted_names("egress_stats interfaces", egress.keys())
        logger.info(
            "  hist_snap keys: %s",
            sorted(hist_snap.keys()) if hist_snap else "(empty)",
        )
        if cp_stats:
            pre = cp_stats.get("pre", {}).get("Global", {})
            post = cp_stats.get("post", {}).get("Global", {})
            logger.info("  cp_stats Global pre keys:  %s", sorted(pre.keys()) if pre else "()")
            logger.info("  cp_stats Global post keys: %s", sorted(post.keys()) if post else "()")
        logger.info("=" * 72)
