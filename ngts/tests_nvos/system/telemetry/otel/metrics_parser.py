"""Parse OTEL collector JSON artifacts into metric structures."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, Iterable, List, Tuple, Union

AttributeKey = Union[Tuple[Any, ...], str]
MetricTimestamps = Dict[str, Dict[AttributeKey, List[int]]]


def prepare_attributes_key(attributes: List[Dict[str, Any]]) -> AttributeKey:
    """Build a hashable key from OTLP attribute objects."""
    parts: List[Any] = []
    for attr in attributes:
        for value in attr.values():
            if isinstance(value, dict):
                parts.extend(value.values())
            else:
                parts.append(value)
    return tuple(parts)


def _append_datapoint_timestamps(
    out: DefaultDict[str, DefaultDict[AttributeKey, List[int]]],
    metric_name: str,
    datapoints: Iterable[Dict[str, Any]],
) -> None:
    for dp in datapoints:
        if "attributes" in dp:
            attribute_key = prepare_attributes_key(dp["attributes"])
        else:
            attribute_key = "No Attr"
        out[metric_name][attribute_key].append(int(dp["timeUnixNano"]))


def metric_timestamps_from_docs(docs: Iterable[Dict[str, Any]]) -> MetricTimestamps:
    """Return ``{metric_name: {attr_key: [timeUnixNano, ...]}}`` from OTLP JSON docs."""
    out: DefaultDict[str, DefaultDict[AttributeKey, List[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for doc in docs:
        for resource in doc.get("resourceMetrics", []) or []:
            for scope in resource.get("scopeMetrics", []) or []:
                for metric in scope.get("metrics", []) or []:
                    name = metric.get("name")
                    if not name:
                        continue
                    for mtype in ("gauge", "histogram", "sum"):
                        payload = metric.get(mtype)
                        if not payload:
                            continue
                        _append_datapoint_timestamps(
                            out, name, payload.get("dataPoints", []) or []
                        )
    return {k: dict(v) for k, v in out.items()}
