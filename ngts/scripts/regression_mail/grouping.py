"""Deterministic grouping and safe fallback behavior."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import DefaultDict, Iterable, List, Optional, Sequence, Tuple

from ngts.scripts.regression_mail.models import ResultRow, SemanticGroup, SemanticReport, WorkbookSnapshot
from ngts.scripts.regression_mail.normalization import (
    canonical_test_name,
    extract_redmine_urls,
    normalize_text,
    strip_redmine_references,
    unique_sorted,
)


def build_deterministic_report(workbook: WorkbookSnapshot) -> SemanticReport:
    """Build lossless groups without asking a model to infer missing facts."""

    failures: DefaultDict[Tuple[str, str], List[ResultRow]] = defaultdict(list)
    for row in workbook.failures:
        failures[(canonical_test_name(row.test_name), normalize_text(workbook.row_comments.get(row.record_id)))].append(
            row
        )

    skipped: DefaultDict[str, List[ResultRow]] = defaultdict(list)
    for row in workbook.skipped:
        test_file = _test_file(row.test_name)
        scope = test_file or canonical_test_name(row.test_name)
        skipped[scope].append(row)

    return SemanticReport(
        failure_groups=[
            _make_group("failure", rows, comments, comments)
            for (_, comments), rows in sorted(failures.items())
        ],
        skip_groups=[
            _make_group(
                "skip",
                rows,
                _skip_reasons(rows),
                _skip_reasons(rows),
                display_override=_skip_display(rows),
            )
            for _, rows in sorted(skipped.items())
        ],
    )


def _make_group(
    prefix: str,
    rows: Sequence[ResultRow],
    comments: str,
    internal_comments: str,
    display_override: Optional[str] = None,
) -> SemanticGroup:
    canonical = canonical_test_name(rows[0].test_name)
    variants = unique_sorted(row.test_name for row in rows)
    display = (
        display_override
        or (canonical + "[*]" if len(variants) > 1 else rows[0].test_name)
    )
    member_ids = sorted(row.record_id for row in rows)
    digest = hashlib.sha256("\x1f".join(member_ids).encode("utf-8")).hexdigest()[:16]
    redmine_urls = extract_redmine_urls(internal_comments)
    return SemanticGroup(
        group_id="{}-{}".format(prefix, digest),
        member_ids=member_ids,
        test_display=display,
        testbeds=unique_sorted(row.testbed for row in rows),
        comments=strip_redmine_references(comments),
        internal_comments=normalize_text(internal_comments),
        redmine_urls=redmine_urls,
    )


def _skip_display(rows: Sequence[ResultRow]) -> str:
    canonical = unique_sorted(canonical_test_name(row.test_name) for row in rows)
    test_files = unique_sorted(_test_file(row.test_name) for row in rows)
    if len(canonical) > 1 and len(test_files) == 1:
        return test_files[0] + "::*"
    variants = unique_sorted(row.test_name for row in rows)
    if len(variants) > 1:
        return canonical[0] + "[*]"
    return rows[0].test_name


def _test_file(value: object) -> str:
    return normalize_text(value).split("::", 1)[0]


def _skip_reasons(rows: Sequence[ResultRow]) -> str:
    return "; ".join(unique_sorted(row.message for row in rows))
