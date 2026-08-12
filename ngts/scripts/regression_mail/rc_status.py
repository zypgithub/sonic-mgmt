"""Exact RC_STATUS.md retrieval and parsing."""

from __future__ import annotations

import base64
import re
import subprocess
from typing import Callable, List, Optional, Sequence

from ngts.scripts.regression_mail.models import RcStatus
from ngts.scripts.regression_mail.normalization import normalize_text, normalize_version


_IMAGE_PR = re.compile(r"https://github\.com/sonic-net/sonic-buildimage/pull/\d+")
_HASH = re.compile(r"\b[0-9a-fA-F]{7,40}\b")
_TAG_FROM_VERSION = re.compile(r"^(\d{6}_RC\.\d+)")


class RcStatusClient:
    """Read the private release document through authenticated GitHub CLI."""

    def __init__(
        self,
        gh_command: str = "gh",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.gh_command = gh_command
        self.runner = runner

    def fetch(self, version: str) -> RcStatus:
        normalized_version = normalize_version(version)
        endpoint = "repos/nvidia-sonic/sonic-buildimage/contents/RC_STATUS.md?ref={}".format(
            normalized_version
        )
        completed = self.runner(
            [self.gh_command, "api", endpoint, "--jq", ".content"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        try:
            markdown = base64.b64decode(completed.stdout).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("GitHub returned invalid RC_STATUS.md content") from error
        return parse_rc_status(markdown, normalized_version)


def parse_rc_status(markdown: str, expected_version: str) -> RcStatus:
    tag = _table_value(markdown, "Tag")
    expected_tag_match = _TAG_FROM_VERSION.match(normalize_version(expected_version))
    if not expected_tag_match:
        raise ValueError("cannot derive RC tag from requested version {!r}".format(expected_version))
    expected_tag = expected_tag_match.group(1)
    if _clean_markdown_value(tag) != expected_tag:
        raise ValueError(
            "RC_STATUS.md Tag {!r} does not match requested release tag {!r}".format(
                _clean_markdown_value(tag),
                expected_tag,
            )
        )

    branch = _clean_markdown_value(_table_value(markdown, "RC branch"))
    upstream = _clean_markdown_value(_table_value(markdown, "Upstream base"))
    hash_match = _HASH.search(upstream)
    if not branch:
        raise ValueError("RC_STATUS.md does not contain RC branch")
    if not hash_match:
        raise ValueError("RC_STATUS.md does not contain a valid Upstream base hash")

    return RcStatus(
        tag=expected_tag,
        image_branch=branch,
        image_public_hash=hash_match.group(0),
        image_pr_urls=_unique(_IMAGE_PR.findall(markdown)),
        raw_markdown=markdown,
    )


def _table_value(markdown: str, label: str) -> str:
    escaped = re.escape(label)
    patterns: Sequence[re.Pattern] = (
        re.compile(r"^\|\s*{}\s*\|\s*(.*?)\s*\|?\s*$".format(escaped), re.IGNORECASE | re.MULTILINE),
        re.compile(
            r"^\s*[-*]\s*\*\*{}:\*\*\s*(.+?)\s*$".format(escaped),
            re.IGNORECASE | re.MULTILINE,
        ),
        re.compile(r"^\s*[-*]?\s*{}\s*:\s*(.+?)\s*$".format(escaped), re.IGNORECASE | re.MULTILINE),
    )
    for pattern in patterns:
        match = pattern.search(markdown)
        if match:
            return match.group(1)
    return ""


def _clean_markdown_value(value: str) -> str:
    text = normalize_text(value).strip("`")
    link = re.fullmatch(r"\[([^\]]+)\]\([^)]+\)", text)
    return normalize_text(link.group(1) if link else text)


def _unique(values: Sequence[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
