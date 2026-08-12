"""Deterministic normalization helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, List


_PARAMETERS = re.compile(r"\[[^\[\]]*\]$")
_SPACE = re.compile(r"\s+")
_REDMINE_URL = re.compile(r"https?://redmine\.mellanox\.com/issues/\d+", re.IGNORECASE)
_PUBLIC_ISSUE_URL = re.compile(
    r"https://github\.com/(?:sonic-net|nvidia-sonic)/[A-Za-z0-9_.-]+/issues/\d+",
    re.IGNORECASE,
)


def normalize_version(value: object) -> str:
    version = str(value or "").strip()
    if version.lower().startswith("sonic."):
        version = version[6:]
    return version


def normalize_text(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def canonical_test_name(value: object) -> str:
    name = normalize_text(value)
    return _PARAMETERS.sub("", name)


def stable_record_id(version: str, session_id: str, key_id: str, test_name: str) -> str:
    identity = "\x1f".join(
        (
            normalize_version(version),
            normalize_text(session_id),
            normalize_text(key_id),
            normalize_text(test_name),
        )
    )
    return "row-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def unique_sorted(values: Iterable[str]) -> List[str]:
    return sorted({normalize_text(value) for value in values if normalize_text(value)})


def strip_redmine_references(value: object) -> str:
    text = _REDMINE_URL.sub("", normalize_text(value))
    return normalize_text(text.strip(" -;,"))


def extract_redmine_urls(value: object) -> List[str]:
    return unique_sorted(match.group(0).lower() for match in _REDMINE_URL.finditer(str(value or "")))


def extract_public_issue_urls(value: object) -> List[str]:
    return unique_sorted(match.group(0) for match in _PUBLIC_ISSUE_URL.finditer(str(value or "")))
