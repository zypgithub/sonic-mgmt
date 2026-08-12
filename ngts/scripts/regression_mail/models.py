"""Domain models shared by the regression mail workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, Sequence, TypeVar


class ExitCode(IntEnum):
    """Public process exit codes."""

    SUCCESS = 0
    INVALID_ARGUMENTS = 2
    INVALID_INPUT = 3
    EXTERNAL_SOURCE = 4
    OPENCODE = 5
    DELIVERY = 6


@dataclass(frozen=True)
class RunRequest:
    """Validated command-line request."""

    excel_path: Path
    version: str
    to: Sequence[str]
    cc: Sequence[str] = ()


@dataclass(frozen=True)
class GenerationError:
    """A sanitized error that can be rendered in the generated email."""

    stage: str
    message: str
    impact: str
    exit_code: ExitCode
    detail: str = field(default="", repr=False, compare=False)


T = TypeVar("T")


@dataclass
class StageResult(Generic[T]):
    """Value and isolated errors produced by one workflow stage."""

    value: Optional[T] = None
    errors: List[GenerationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ResultRow:
    """A selected workbook result row."""

    record_id: str
    excel_row: int
    session_id: str
    mars_key_id: str
    testbed: str
    test_name: str
    sanitized_testname: str
    result: str
    message: str
    topology: str
    host: str
    asic: str
    platform: str
    hwsku: str
    os_version: str
    values: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def join_names(self) -> Sequence[str]:
        names = [self.test_name]
        if self.sanitized_testname and self.sanitized_testname not in names:
            names.append(self.sanitized_testname)
        return names


@dataclass
class WorkbookSnapshot:
    """Read-only projection of the selected workbook version."""

    source_path: Path
    sheet_name: str
    header_row: int
    headers: Sequence[str]
    selected_rows: List[ResultRow]
    result_counts: Dict[str, int]
    hardware_pairs: List[Sequence[str]]
    row_comments: Dict[str, str] = field(default_factory=dict)
    record_excel_rows: Dict[str, List[int]] = field(default_factory=dict, repr=False)

    @property
    def failures(self) -> List[ResultRow]:
        return [row for row in self.selected_rows if row.result == "fail"]

    @property
    def skipped(self) -> List[ResultRow]:
        return [row for row in self.selected_rows if row.result == "skipped"]


@dataclass(frozen=True)
class DashboardAnalysis:
    """Human analysis returned by the regression dashboard."""

    record_key: str
    session_id: str
    key_id: str
    test_name: str
    analysis: str
    owner: str = ""
    redmine_url: str = ""


@dataclass
class DashboardSnapshot:
    """Dashboard summary and failure-analysis overlay."""

    coverage: Optional[float] = None
    pass_rate: Optional[float] = None
    analyses: List[DashboardAnalysis] = field(default_factory=list)
    collection_name: str = ""


@dataclass
class RcStatus:
    """Metadata parsed from an exact RC_STATUS.md document."""

    tag: str = ""
    image_branch: str = ""
    image_public_hash: str = ""
    image_pr_urls: List[str] = field(default_factory=list)
    raw_markdown: str = field(default="", repr=False)


@dataclass
class GitResolution:
    """Internal/public sonic-mgmt history resolution."""

    internal_branch: str = ""
    internal_hash: str = ""
    public_branch: str = ""
    public_hash: str = ""
    source_root: Optional[Path] = None
    additional_commit_hashes: List[str] = field(default_factory=list)
    temporary_refs: List[str] = field(default_factory=list, repr=False)


@dataclass(frozen=True)
class PullRequest:
    """Validated public GitHub pull request."""

    url: str
    title: str = ""
    author: str = ""
    state: str = ""
    base_branch: str = ""


@dataclass
class JenkinsArtifact:
    """Unique CSV output produced by one exact Jenkins build."""

    build_number: int
    build_url: str
    remote_path: str = ""
    pr_urls: List[str] = field(default_factory=list)


@dataclass
class SemanticGroup:
    """Validated model proposal for one rendered report row."""

    group_id: str
    member_ids: List[str]
    test_display: str
    testbeds: List[str]
    comments: str = ""
    internal_comments: str = ""
    redmine_urls: List[str] = field(default_factory=list)


@dataclass
class SemanticReport:
    """Validated OpenCode output."""

    failure_groups: List[SemanticGroup] = field(default_factory=list)
    skip_groups: List[SemanticGroup] = field(default_factory=list)
    internal_error_groups: List[SemanticGroup] = field(default_factory=list)
    executive_summary: str = ""


@dataclass
class ReportModel:
    """Complete best-effort input to rendering and delivery."""

    request: RunRequest
    workbook: Optional[WorkbookSnapshot] = None
    dashboard: Optional[DashboardSnapshot] = None
    rc_status: Optional[RcStatus] = None
    git: Optional[GitResolution] = None
    semantic: Optional[SemanticReport] = None
    mgmt_prs: List[PullRequest] = field(default_factory=list)
    errors: List[GenerationError] = field(default_factory=list)
    attachment_path: Optional[Path] = None
    skips_path: Optional[Path] = None

    @property
    def exit_code(self) -> ExitCode:
        if not self.errors:
            return ExitCode.SUCCESS
        return max(error.exit_code for error in self.errors)


@dataclass(frozen=True)
class RenderedMessage:
    """Rendered message bodies before MIME construction."""

    subject: str
    plain: str
    html: str
