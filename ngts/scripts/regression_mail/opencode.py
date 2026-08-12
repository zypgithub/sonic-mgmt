"""Constrained OpenCode execution and JSON output parsing."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from ngts.scripts.regression_mail.grouping import build_deterministic_report
from ngts.scripts.regression_mail.models import (
    GitResolution,
    RcStatus,
    SemanticGroup,
    SemanticReport,
    WorkbookSnapshot,
)


_REDMINE_URL = re.compile(r"^https://redmine\.mellanox\.com/issues/\d+$", re.IGNORECASE)
_REDMINE_REFERENCE = re.compile(r"(?:redmine\.mellanox\.com|Redmine\s*#?\d+)", re.IGNORECASE)
_MAX_GROUPS_PER_CALL = 50


class OpenCodeClient:
    """Invoke the repository's read-only regression-mail agent."""

    def __init__(
        self,
        command: str,
        model: str,
        repo_root: Path,
        timeout: int,
        parallelism: int = 10,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        if parallelism <= 0:
            raise ValueError("OpenCode parallelism must be positive")
        self.command = command
        self.model = model
        self.repo_root = repo_root
        self.timeout = timeout
        self.parallelism = parallelism
        self.runner = runner

    def analyze(
        self,
        version: str,
        workbook: WorkbookSnapshot,
        rc_status: Optional[RcStatus],
        git: Optional[GitResolution],
        deterministic: Optional[SemanticReport] = None,
    ) -> SemanticReport:
        base = deterministic or build_deterministic_report(workbook)
        work = []
        for chunk_index, chunk in enumerate(_chunk_report(base)):
            include_internal_errors = chunk_index == 0
            payload = _build_evidence(
                version,
                workbook,
                rc_status,
                git,
                chunk,
                include_internal_errors,
            )
            work.append(
                (chunk_index, chunk, payload, include_internal_errors)
            )

        reports: List[Optional[SemanticReport]] = [None] * len(work)
        workers = min(self.parallelism, len(work))
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="regression-mail-opencode",
        ) as executor:
            futures = {
                executor.submit(
                    self._analyze_chunk,
                    payload,
                    chunk,
                    chunk_index,
                    include_internal_errors,
                ): chunk_index
                for chunk_index, chunk, payload, include_internal_errors in work
            }
            for future in as_completed(futures):
                reports[futures[future]] = future.result()

        completed_reports = [report for report in reports if report is not None]
        if len(completed_reports) != len(work):
            raise RuntimeError("OpenCode did not return every scheduled report chunk")

        summaries: List[str] = []
        for report in completed_reports:
            summary = report.executive_summary.strip()
            if summary and summary not in summaries:
                summaries.append(summary)
        combined = SemanticReport(
            failure_groups=[
                group for report in completed_reports for group in report.failure_groups
            ],
            skip_groups=[
                group for report in completed_reports for group in report.skip_groups
            ],
            internal_error_groups=[
                group
                for report in completed_reports
                for group in report.internal_error_groups
            ],
            executive_summary="\n".join(summaries),
        )
        validate_semantic_report(combined, workbook)
        return combined

    def _analyze_chunk(
        self,
        payload: Mapping[str, Any],
        base: SemanticReport,
        chunk_index: int,
        include_internal_errors: bool,
    ) -> SemanticReport:
        validation_error = ""
        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                proposal = self._run_once(
                    payload,
                    validation_error,
                    attempt,
                    chunk_index,
                )
                proposal = _restore_missing_sources(proposal, base)
                _validate_source_partitions(proposal, base)
                if not include_internal_errors and proposal.internal_error_groups:
                    raise ValueError(
                        "internal_error_groups must be empty outside the first chunk"
                    )
                report = _expand_proposal(proposal, base)
                _validate_group_content(report)
                for group in (
                    list(report.failure_groups)
                    + list(report.skip_groups)
                    + list(report.internal_error_groups)
                ):
                    group.group_id = "chunk-{}-{}".format(
                        chunk_index + 1,
                        group.group_id,
                    )
                return report
            except ValueError as error:
                last_error = error
                validation_error = str(error)
            except subprocess.CalledProcessError as error:
                detail = str(error.stderr or error.stdout or "").strip()
                if detail:
                    detail = ": " + detail[-1000:]
                raise RuntimeError(
                    "OpenCode process exited with status {}{}".format(
                        error.returncode,
                        detail,
                    )
                ) from error
            except (OSError, subprocess.SubprocessError) as error:
                raise RuntimeError("OpenCode execution failed: {}".format(error)) from error
        raise RuntimeError("OpenCode output failed validation after two attempts: {}".format(last_error))

    def _run_once(
        self,
        payload: Mapping[str, Any],
        validation_error: str,
        attempt: int,
        chunk_index: int,
    ) -> SemanticReport:
        evidence_path = _write_private_json(payload, self.repo_root)
        try:
            prompt_path = Path(__file__).resolve().parent / "prompts" / "evidence_review.md"
            message = prompt_path.read_text(encoding="utf-8").strip()
            if validation_error:
                message += (
                    " The previous response was rejected by deterministic validation: {!r}. "
                    "Correct only the schema or grouping error; do not invent missing facts."
                ).format(validation_error[:500])
            completed = self.runner(
                [
                    self.command,
                    "run",
                    "--format",
                    "json",
                    "--agent",
                    "regression-mail",
                    "--model",
                    self.model,
                    "--dir",
                    str(self.repo_root),
                    "--file",
                    str(evidence_path),
                    "--title",
                    "regression-mail-{}-{}-{}".format(
                        os.getpid(),
                        chunk_index + 1,
                        attempt + 1,
                    ),
                    message,
                ],
                cwd=str(self.repo_root),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout,
            )
            if len(completed.stdout) > 10 * 1024 * 1024:
                raise ValueError("OpenCode event stream exceeds 10 MiB")
            response_text = _extract_text_events(completed.stdout)
            return _parse_report(_extract_json(response_text))
        finally:
            try:
                evidence_path.unlink()
            except FileNotFoundError:
                pass
            try:
                evidence_path.parent.rmdir()
            except OSError:
                pass


def _build_evidence(
    version: str,
    workbook: WorkbookSnapshot,
    rc_status: Optional[RcStatus],
    git: Optional[GitResolution],
    deterministic: SemanticReport,
    include_internal_errors: bool,
) -> Dict[str, Any]:
    rows_by_id = {row.record_id: row for row in workbook.selected_rows}
    return {
        "schema_version": 1,
        "version": version,
        "image_branch": rc_status.image_branch if rc_status else "",
        "source_root": str(git.source_root) if git and git.source_root else "",
        "include_internal_errors": include_internal_errors,
        "rules": {
            "no_raw_exception_diagnosis": True,
            "empty_engineer_analysis_stays_empty": True,
            "comments_must_be_redmine_free": True,
            "every_input_record_exactly_once": True,
        },
        "failure_groups": [
            _group_evidence(group, rows_by_id) for group in deterministic.failure_groups
        ],
        "skip_groups": [
            _group_evidence(group, rows_by_id) for group in deterministic.skip_groups
        ],
        "required_output": {
            "schema_version": 1,
            "failure_groups": "list[group]",
            "skip_groups": "list[group]",
            "internal_error_groups": "list[group]",
            "executive_summary": "string",
            "group": {
                "group_id": "string",
                "member_ids": "list[source_group_id]; every supplied source group exactly once",
                "test_display": "string",
                "testbeds": "list[string]",
                "comments": "string without Redmine references",
                "internal_comments": "string",
                "redmine_urls": "list[canonical Redmine ticket URL]",
            },
        },
    }


def _chunk_report(
    report: SemanticReport,
    limit: int = _MAX_GROUPS_PER_CALL,
) -> List[SemanticReport]:
    tagged = [
        ("failure", group) for group in report.failure_groups
    ] + [
        ("skip", group) for group in report.skip_groups
    ]
    if not tagged:
        return [SemanticReport()]

    chunks: List[SemanticReport] = []
    for start in range(0, len(tagged), limit):
        subset = tagged[start : start + limit]
        chunks.append(
            SemanticReport(
                failure_groups=[
                    group for kind, group in subset if kind == "failure"
                ],
                skip_groups=[
                    group for kind, group in subset if kind == "skip"
                ],
            )
        )
    return chunks


def _group_evidence(
    group: SemanticGroup,
    rows_by_id: Mapping[str, Any],
) -> Dict[str, Any]:
    rows = [rows_by_id[member] for member in group.member_ids if member in rows_by_id]
    return {
        "source_group_id": group.group_id,
        "member_count": len(group.member_ids),
        "test_display": group.test_display,
        "testbeds": group.testbeds,
        "comments": group.comments,
        "internal_comments": group.internal_comments,
        "topologies": sorted({row.topology for row in rows if row.topology}),
        "hwskus": sorted({row.hwsku for row in rows if row.hwsku}),
        "platforms": sorted({row.platform for row in rows if row.platform}),
        "sample_test_names": sorted({row.test_name for row in rows})[:5],
    }


def _write_private_json(payload: Mapping[str, Any], repo_root: Path) -> Path:
    private_dir = repo_root / ".git" / "regression-mail-tmp"
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".regression-mail.json",
        prefix="sonic-",
        dir=str(private_dir),
        delete=False,
    )
    path = Path(handle.name)
    try:
        os.chmod(path, 0o600)
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    finally:
        handle.close()
    return path


def _extract_text_events(stream: str) -> str:
    parts: List[str] = []
    for line_number, line in enumerate(stream.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("invalid OpenCode JSON event at line {}".format(line_number)) from error
        if event.get("type") == "text":
            part = event.get("part") or {}
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        raise ValueError("OpenCode returned no text event")
    return "".join(parts).strip()


def _extract_json(text: str) -> Mapping[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("OpenCode response is not a JSON object")
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, Mapping):
        raise ValueError("OpenCode response must be a JSON object")
    return payload


def _parse_report(payload: Mapping[str, Any]) -> SemanticReport:
    schema_version = payload.get("schema_version")
    if schema_version not in (1, "1"):
        raise ValueError(
            "unsupported OpenCode schema_version {!r}; top-level keys={}".format(
                schema_version,
                sorted(str(key) for key in payload.keys())[:20],
            )
        )
    return SemanticReport(
        failure_groups=_parse_groups(payload.get("failure_groups"), "failure_groups"),
        skip_groups=_parse_groups(payload.get("skip_groups"), "skip_groups"),
        internal_error_groups=_parse_groups(
            payload.get("internal_error_groups"),
            "internal_error_groups",
        ),
        executive_summary=_required_string(payload.get("executive_summary", ""), "executive_summary"),
    )


def _validate_source_partitions(
    proposal: SemanticReport,
    deterministic: SemanticReport,
) -> None:
    _validate_source_partition(
        proposal.failure_groups,
        {group.group_id for group in deterministic.failure_groups},
        "failure",
    )
    _validate_source_partition(
        proposal.skip_groups,
        {group.group_id for group in deterministic.skip_groups},
        "skip",
    )
    if any(group.member_ids for group in proposal.internal_error_groups):
        raise ValueError("internal_error_groups must use empty member_ids")


def _restore_missing_sources(
    proposal: SemanticReport,
    deterministic: SemanticReport,
) -> SemanticReport:
    """Restore model-omitted source groups without inventing analysis."""

    return SemanticReport(
        failure_groups=_restore_partition(
            proposal.failure_groups,
            deterministic.failure_groups,
        ),
        skip_groups=_restore_partition(
            proposal.skip_groups,
            deterministic.skip_groups,
        ),
        internal_error_groups=proposal.internal_error_groups,
        executive_summary=proposal.executive_summary,
    )


def _restore_partition(
    proposals: Sequence[SemanticGroup],
    sources: Sequence[SemanticGroup],
) -> List[SemanticGroup]:
    source_by_id = {group.group_id: group for group in sources}
    members = [member for group in proposals for member in group.member_ids]
    counts = Counter(members)
    if set(members) - set(source_by_id) or any(count != 1 for count in counts.values()):
        return list(proposals)

    restored = list(proposals)
    for source in sources:
        if source.group_id in counts:
            continue
        restored.append(
            SemanticGroup(
                group_id="fallback-{}".format(source.group_id),
                member_ids=[source.group_id],
                test_display=source.test_display,
                testbeds=list(source.testbeds),
                comments=source.comments,
                internal_comments=source.internal_comments,
                redmine_urls=list(source.redmine_urls),
            )
        )
    return restored


def validate_semantic_report(
    report: SemanticReport,
    workbook: WorkbookSnapshot,
) -> None:
    """Reject omissions, duplication, invented records, and internal leakage."""

    _validate_record_partition(
        report.failure_groups,
        {row.record_id for row in workbook.failures},
        "failure",
    )
    _validate_record_partition(
        report.skip_groups,
        {row.record_id for row in workbook.skipped},
        "skip",
    )
    _validate_group_content(report)


def _validate_group_content(report: SemanticReport) -> None:
    group_ids: List[str] = []
    for group in (
        list(report.failure_groups)
        + list(report.skip_groups)
        + list(report.internal_error_groups)
    ):
        group_ids.append(group.group_id)
        if not group.group_id.strip():
            raise ValueError("OpenCode returned an empty group_id")
        if not group.test_display.strip() and not group.internal_comments.strip():
            raise ValueError("group {!r} has no display value".format(group.group_id))
        if _REDMINE_REFERENCE.search(group.comments):
            raise ValueError(
                "group {!r} leaked a Redmine reference into Comments".format(group.group_id)
            )
        for url in group.redmine_urls:
            if not _REDMINE_URL.fullmatch(url):
                raise ValueError(
                    "group {!r} returned invalid Redmine URL {!r}".format(group.group_id, url)
                )
    duplicates = [value for value, count in Counter(group_ids).items() if count != 1]
    if duplicates:
        raise ValueError("duplicate OpenCode group_id values: {}".format(", ".join(sorted(duplicates))))


def _validate_record_partition(
    groups: Sequence[SemanticGroup],
    expected: Set[str],
    label: str,
) -> None:
    members = [member for group in groups for member in group.member_ids]
    counts = Counter(members)
    unknown = sorted(set(members) - expected)
    missing = sorted(expected - set(members))
    repeated = sorted(member for member, count in counts.items() if count != 1)
    if unknown:
        raise ValueError("{} groups contain unknown record IDs: {}".format(label, _short(unknown)))
    if missing:
        raise ValueError("{} groups omitted record IDs: {}".format(label, _short(missing)))
    if repeated:
        raise ValueError("{} record IDs appear more than once: {}".format(label, _short(repeated)))


def _short(values: Iterable[str], limit: int = 5) -> str:
    items = list(values)
    text = ", ".join(items[:limit])
    if len(items) > limit:
        text += ", ..."
    return text


def _validate_source_partition(
    groups: Sequence[SemanticGroup],
    expected: Set[str],
    label: str,
) -> None:
    members = [member for group in groups for member in group.member_ids]
    counts = Counter(members)
    unknown = sorted(set(members) - expected)
    missing = sorted(expected - set(members))
    repeated = sorted(member for member, count in counts.items() if count != 1)
    if unknown or missing or repeated:
        raise ValueError(
            "{} source-group partition invalid: unknown={}, missing={}, repeated={}".format(
                label,
                unknown[:5],
                missing[:5],
                repeated[:5],
            )
        )


def _expand_proposal(
    proposal: SemanticReport,
    deterministic: SemanticReport,
) -> SemanticReport:
    failure_sources = {group.group_id: group for group in deterministic.failure_groups}
    skip_sources = {group.group_id: group for group in deterministic.skip_groups}
    return SemanticReport(
        failure_groups=_expand_groups(proposal.failure_groups, failure_sources),
        skip_groups=_expand_groups(proposal.skip_groups, skip_sources),
        internal_error_groups=proposal.internal_error_groups,
        executive_summary=proposal.executive_summary,
    )


def _expand_groups(
    proposals: Sequence[SemanticGroup],
    sources: Mapping[str, SemanticGroup],
) -> List[SemanticGroup]:
    expanded: List[SemanticGroup] = []
    for proposal in proposals:
        row_ids: List[str] = []
        for source_id in proposal.member_ids:
            row_ids.extend(sources[source_id].member_ids)
        expanded.append(
            SemanticGroup(
                group_id=proposal.group_id,
                member_ids=sorted(row_ids),
                test_display=proposal.test_display,
                testbeds=proposal.testbeds,
                comments=proposal.comments,
                internal_comments=proposal.internal_comments,
                redmine_urls=proposal.redmine_urls,
            )
        )
    return expanded


def _parse_groups(value: Any, field: str) -> List[SemanticGroup]:
    if not isinstance(value, list):
        raise ValueError("{} must be a list".format(field))
    groups: List[SemanticGroup] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError("{}[{}] must be an object".format(field, index))
        groups.append(
            SemanticGroup(
                group_id=_required_string(item.get("group_id"), "group_id"),
                member_ids=_string_list(item.get("member_ids"), "member_ids"),
                test_display=_required_string(item.get("test_display", ""), "test_display"),
                testbeds=_string_list(item.get("testbeds"), "testbeds"),
                comments=_required_string(item.get("comments", ""), "comments"),
                internal_comments=_required_string(
                    item.get("internal_comments", ""),
                    "internal_comments",
                ),
                redmine_urls=_string_list(item.get("redmine_urls"), "redmine_urls"),
            )
        )
    return groups


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError("{} must be a string".format(field))
    return value.strip()


def _string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("{} must be a list of strings".format(field))
    return [item.strip() for item in value]
