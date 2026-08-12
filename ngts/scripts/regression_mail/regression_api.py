"""Regression dashboard API adapter."""

from __future__ import annotations

import gzip
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ngts.scripts.regression_mail.models import DashboardAnalysis, DashboardSnapshot
from ngts.scripts.regression_mail.normalization import normalize_text, normalize_version


_COLLECTION_FROM_VERSION = re.compile(r"^(\d{6}_RC\.\d+)")


class RegressionReportClient:
    """Fetch current summary and engineer analysis for one exact version."""

    def __init__(self, base_url: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch(self, version: str) -> DashboardSnapshot:
        normalized_version = normalize_version(version)
        collection_name = self._resolve_collection(normalized_version)
        collection = self._get_json(
            "/api/collections/{}?rows=1".format(quote(collection_name, safe=""))
        )
        overlay = self._get_json("/api/failure-analysis")
        summary = self._get_json("/api/snapshot-summary", {"version": normalized_version})
        coverage = self._get_json("/api/coverage", {"version": normalized_version})
        analyses = self._join_analyses(collection, overlay)
        return DashboardSnapshot(
            coverage=_extract_coverage(coverage),
            pass_rate=_extract_pass_rate(summary),
            analyses=analyses,
            collection_name=collection_name,
        )

    def _resolve_collection(self, version: str) -> str:
        match = _COLLECTION_FROM_VERSION.match(normalize_version(version))
        if not match:
            raise ValueError("cannot derive an exact collection name from version {!r}".format(version))
        expected = match.group(1)
        payload = self._get_json("/api/collections")
        names = sorted(set(_collection_names(payload)))
        exact = [name for name in names if name == expected]
        if len(exact) != 1:
            raise ValueError(
                "version {!r} must resolve to exactly one current collection {!r}; found {}".format(
                    version,
                    expected,
                    len(exact),
                )
            )
        return exact[0]

    def _get_json(
        self,
        path: str,
        query: Optional[Mapping[str, str]] = None,
    ) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urlencode(query)
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "User-Agent": "sonic-regression-mail/1",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            body = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
        return json.loads(body.decode("utf-8"))

    @staticmethod
    def _join_analyses(collection: Any, overlay: Any) -> List[DashboardAnalysis]:
        records = _find_record_list(collection)
        overlays = _find_record_list(overlay)
        overlay_by_key: Dict[str, Mapping[str, Any]] = {}
        for item in overlays:
            key = normalize_text(item.get("recordKey"))
            if key:
                overlay_by_key[key] = item

        analyses: List[DashboardAnalysis] = []
        for record in records:
            record_id = normalize_text(record.get("id"))
            if not record_id:
                continue
            record_key = "mars-" + record_id
            engineer = overlay_by_key.get(record_key)
            if not engineer:
                continue
            analysis = normalize_text(engineer.get("analysis"))
            if not analysis:
                continue
            analyses.append(
                DashboardAnalysis(
                    record_key=record_key,
                    session_id=normalize_text(record.get("sessionId")),
                    key_id=normalize_text(record.get("keyId")),
                    test_name=normalize_text(record.get("name")),
                    analysis=analysis,
                    owner=normalize_text(engineer.get("owner")),
                    redmine_url=normalize_text(engineer.get("rmUrl")),
                )
            )
        return analyses


def _collection_names(payload: Any) -> Iterable[str]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                yield item
            elif isinstance(item, Mapping):
                name = item.get("name") or item.get("collection")
                if name:
                    yield normalize_text(name)
    elif isinstance(payload, Mapping):
        for key in ("collections", "items", "data", "versions"):
            if key in payload:
                yield from _collection_names(payload[key])
                return
        for key in payload:
            if _COLLECTION_FROM_VERSION.match(str(key)):
                yield normalize_text(key)


def _find_record_list(payload: Any) -> List[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "rows", "items", "data", "failures", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, Mapping)]
            if isinstance(candidate, Mapping):
                nested = _find_record_list(candidate)
                if nested:
                    return nested
    return []


def _extract_coverage(payload: Any) -> Optional[float]:
    try:
        value = payload["coverage"]["totals"]["coverage"]
    except (KeyError, TypeError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_pass_rate(payload: Any) -> Optional[float]:
    groups: Sequence[Any]
    if isinstance(payload, Mapping):
        groups = payload.get("groups") or payload.get("data") or []
    elif isinstance(payload, list):
        groups = payload
    else:
        groups = []
    passed = 0
    failed = 0
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        passed += _as_int(group.get("passed"))
        failed += _as_int(group.get("failed"))
    denominator = passed + failed
    return (passed / denominator * 100.0) if denominator else None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
