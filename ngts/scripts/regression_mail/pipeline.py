"""Synchronous, error-isolated regression mail workflow."""

from __future__ import annotations

import sys
import re
from collections import defaultdict
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TextIO, Tuple

from ngts.scripts.regression_mail.config import Settings
from ngts.scripts.regression_mail.git_history import GitHistoryResolver
from ngts.scripts.regression_mail.grouping import build_deterministic_report
from ngts.scripts.regression_mail.jenkins import GitHubClient, JenkinsPrClient
from ngts.scripts.regression_mail.mail import SmtpTransport, build_message
from ngts.scripts.regression_mail.models import (
    DashboardAnalysis,
    ExitCode,
    GenerationError,
    ReportModel,
    RenderedMessage,
    RunRequest,
)
from ngts.scripts.regression_mail.normalization import normalize_text
from ngts.scripts.regression_mail.opencode import OpenCodeClient
from ngts.scripts.regression_mail.rc_status import RcStatusClient
from ngts.scripts.regression_mail.regression_api import RegressionReportClient
from ngts.scripts.regression_mail.rendering import ReportRenderer
from ngts.scripts.regression_mail.workbook import ArtifactWriter, WorkbookLoader


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization|api[-_ ]?key|token|password|secret)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)([?&](?:access_token|token|api_key|key)=)[^&\s]+"),
)
_WHITESPACE = re.compile(r"\s+")


@dataclass
class PipelineDependencies:
    """Injectable boundaries for offline and live-sink testing."""

    workbook: Any
    dashboard: Any
    rc_status: Any
    git: Any
    github: Any
    jenkins: Any
    opencode: Any
    artifacts: Any
    renderer: Any
    transport: Any
    mime_builder: Callable[..., EmailMessage] = build_message


def build_default_dependencies(settings: Settings) -> PipelineDependencies:
    return PipelineDependencies(
        workbook=WorkbookLoader(),
        dashboard=RegressionReportClient(
            settings.api_base_url,
            timeout=settings.http_timeout_seconds,
        ),
        rc_status=RcStatusClient(),
        git=GitHistoryResolver(settings.repo_root),
        github=GitHubClient(),
        jenkins=JenkinsPrClient(
            settings.jenkins_url,
            settings.jenkins_csv_path,
            settings.jenkins_ssh_host,
            settings.jenkins_ssh_user,
            settings.jenkins_user,
            settings.jenkins_api_token,
            timeout=settings.jenkins_timeout_seconds,
        ),
        opencode=OpenCodeClient(
            settings.opencode_command,
            settings.model,
            settings.repo_root,
            settings.opencode_timeout_seconds,
            settings.opencode_parallelism,
        ),
        artifacts=ArtifactWriter(),
        renderer=ReportRenderer(),
        transport=SmtpTransport(settings.smtp_host, settings.smtp_port),
    )


def run(
    request: RunRequest,
    settings: Settings,
    dependencies: Optional[PipelineDependencies] = None,
    stderr: TextIO = sys.stderr,
) -> int:
    deps = dependencies or build_default_dependencies(settings)
    report = ReportModel(request=request)
    message: Optional[EmailMessage] = None

    try:
        report.workbook = _attempt(
            report,
            "Excel",
            ExitCode.INVALID_INPUT,
            "Excel-derived report sections and attachment are unavailable.",
            lambda: deps.workbook.load(request.excel_path, request.version),
            settings,
        )

        if report.workbook:
            report.dashboard = _attempt(
                report,
                "Regression Report API",
                ExitCode.EXTERNAL_SOURCE,
                "Coverage, pass rate, and engineer analysis are unavailable.",
                lambda: deps.dashboard.fetch(request.version),
                settings,
            )
            if report.dashboard:
                apply_dashboard_analysis(report.workbook, report.dashboard)

        report.rc_status = _attempt(
            report,
            "RC_STATUS",
            ExitCode.EXTERNAL_SOURCE,
            "Image metadata and image pull requests are unavailable.",
            lambda: deps.rc_status.fetch(request.version),
            settings,
        )
        report.git = _attempt(
            report,
            "Git history",
            ExitCode.INVALID_INPUT,
            "sonic-mgmt branch, public hash, and source-dependent analysis are unavailable.",
            lambda: deps.git.resolve(request.version),
            settings,
        )

        _collect_mgmt_prs(report, deps, settings)

        if report.workbook:
            report.semantic = build_deterministic_report(report.workbook)
            semantic = _attempt(
                report,
                "OpenCode",
                ExitCode.OPENCODE,
                "Redmine review and AI-derived grouping remain unavailable; deterministic groups are used.",
                lambda: deps.opencode.analyze(
                    request.version,
                    report.workbook,
                    report.rc_status,
                    report.git,
                    report.semantic,
                ),
                settings,
            )
            if semantic:
                report.semantic = semantic

        if report.workbook and report.semantic:
            report.skips_path = _attempt(
                report,
                "skips.json",
                ExitCode.INVALID_INPUT,
                "The skip mapping file was not updated.",
                lambda: deps.artifacts.write_skips(report.workbook, report.semantic),
                settings,
            )
            report.attachment_path = _attempt(
                report,
                "Workbook attachment",
                ExitCode.INVALID_INPUT,
                "The enriched Excel workbook is not attached.",
                lambda: deps.artifacts.build_attachment(report.workbook, report.semantic),
                settings,
            )

        rendered = _render(report, deps, settings)
        message = _build_mime(report, rendered, deps, settings)
        if message is None:
            stderr.write("regression mail delivery failed: unable to construct minimal MIME message\n")
            return int(ExitCode.DELIVERY)

        try:
            deps.transport.send(message, request)
        except Exception as error:
            _write_diagnostic(settings, "SMTP", error)
            stderr.write("regression mail delivery failed: {}\n".format(str(error)[:300]))
            return int(ExitCode.DELIVERY)

        if report.errors:
            stderr.write(
                "regression mail sent in degraded mode; {} stage(s) failed; exit={}\n".format(
                    len(report.errors),
                    int(report.exit_code),
                )
            )
        return int(report.exit_code)
    finally:
        try:
            if hasattr(deps.git, "cleanup"):
                deps.git.cleanup(report.git)
        finally:
            if hasattr(deps.artifacts, "cleanup_attachment"):
                deps.artifacts.cleanup_attachment(report.attachment_path)


def _collect_mgmt_prs(
    report: ReportModel,
    deps: PipelineDependencies,
    settings: Settings,
) -> None:
    if not report.git:
        return
    if not report.git.additional_commit_hashes and not settings.jenkins_authors:
        return
    authors = list(settings.jenkins_authors)
    if not authors:
        commit_urls = _attempt(
            report,
            "GitHub commit PR references",
            ExitCode.EXTERNAL_SOURCE,
            "Authors needed for the Jenkins PR report could not be resolved.",
            lambda: deps.github.pr_urls_from_commits(
                settings.repo_root,
                report.git.additional_commit_hashes,
            ),
            settings,
        )
        if commit_urls is None:
            return
        seed_prs = _attempt(
            report,
            "GitHub pull requests",
            ExitCode.EXTERNAL_SOURCE,
            "Public sonic-mgmt pull request metadata is unavailable.",
            lambda: deps.github.get_mgmt_prs(commit_urls),
            settings,
        )
        if seed_prs is None:
            return
        authors = sorted({pr.author for pr in seed_prs if pr.author})
    artifact = _attempt(
        report,
        "Jenkins PR report",
        ExitCode.EXTERNAL_SOURCE,
        "Additional sonic-mgmt pull requests are unavailable.",
        lambda: deps.jenkins.collect(authors, report.request.to[0]),
        settings,
    )
    if not artifact:
        return
    validated = _attempt(
        report,
        "GitHub Jenkins PR validation",
        ExitCode.EXTERNAL_SOURCE,
        "Jenkins pull request URLs could not be validated against GitHub.",
        lambda: deps.github.get_mgmt_prs(artifact.pr_urls),
        settings,
    )
    if validated is not None:
        report.mgmt_prs = validated


def _render(
    report: ReportModel,
    deps: PipelineDependencies,
    settings: Settings,
) -> RenderedMessage:
    try:
        return deps.renderer.render(report)
    except Exception as error:
        rendering_error = generation_error(
            "HTML rendering",
            error,
            "A minimal diagnostic message is used.",
            ExitCode.INVALID_INPUT,
        )
        report.errors.append(rendering_error)
        _write_diagnostic(settings, "HTML rendering", error)
        try:
            return deps.renderer.minimal(report, rendering_error)
        except Exception as minimal_error:
            _write_diagnostic(settings, "Minimal rendering", minimal_error)
            return _hardcoded_minimal(report)


def _build_mime(
    report: ReportModel,
    rendered: RenderedMessage,
    deps: PipelineDependencies,
    settings: Settings,
) -> Optional[EmailMessage]:
    try:
        return deps.mime_builder(
            rendered,
            report.request,
            settings.sender,
            report.attachment_path,
        )
    except Exception as error:
        attachment_error = generation_error(
            "MIME attachment",
            error,
            "The diagnostic email is sent without the workbook attachment.",
            ExitCode.INVALID_INPUT,
        )
        report.errors.append(attachment_error)
        _write_diagnostic(settings, "MIME attachment", error)
        try:
            try:
                minimal = deps.renderer.minimal(report, attachment_error)
            except Exception as rendering_error:
                _write_diagnostic(settings, "Minimal rendering", rendering_error)
                minimal = _hardcoded_minimal(report)
            return deps.mime_builder(minimal, report.request, settings.sender, None)
        except Exception as minimal_error:
            _write_diagnostic(settings, "Minimal MIME", minimal_error)
            return None


def _attempt(
    report: ReportModel,
    stage: str,
    exit_code: ExitCode,
    impact: str,
    operation: Callable[[], Any],
    settings: Settings,
) -> Any:
    try:
        return operation()
    except Exception as error:
        effective_code = exit_code
        if stage == "OpenCode" and _looks_like_redmine_failure(error):
            effective_code = ExitCode.EXTERNAL_SOURCE
        report.errors.append(generation_error(stage, error, impact, effective_code))
        _write_diagnostic(settings, stage, error)
        return None


def _looks_like_redmine_failure(error: Exception) -> bool:
    value = str(error).lower()
    return "redmine" in value or ("mcp" in value and "validation" not in value)


def _hardcoded_minimal(report: ReportModel) -> RenderedMessage:
    lines = [
        "SONiC Regression Report (degraded)",
        "Version: {}".format(report.request.version),
        "",
        "Generation Errors:",
    ]
    lines.extend(
        "- {}: {} Impact: {}".format(error.stage, error.message, error.impact)
        for error in report.errors
    )
    return RenderedMessage(
        subject="[Degraded] SONiC Regression Report - {}".format(report.request.version),
        plain="\n".join(lines) + "\n",
        html="",
    )


def apply_dashboard_analysis(workbook: Any, dashboard: Any) -> Dict[str, str]:
    """Join exact human analysis to Excel failures without cross-version guessing."""

    index: Dict[Tuple[str, str, str], List[DashboardAnalysis]] = defaultdict(list)
    for analysis in dashboard.analyses:
        key = (
            normalize_text(analysis.session_id),
            normalize_text(analysis.key_id),
            normalize_text(analysis.test_name),
        )
        index[key].append(analysis)

    comments: Dict[str, str] = {}
    for row in workbook.failures:
        matched: List[DashboardAnalysis] = []
        for test_name in row.join_names:
            key = (
                normalize_text(row.session_id),
                normalize_text(row.mars_key_id),
                normalize_text(test_name),
            )
            matched.extend(index.get(key, []))
        values: List[str] = []
        for analysis in matched:
            value = normalize_text(analysis.analysis)
            if value and value not in values:
                values.append(value)
        comments[row.record_id] = "\n".join(values)
    workbook.row_comments.update(comments)
    return comments


def generation_error(
    stage: str,
    error: object,
    impact: str,
    exit_code: ExitCode,
) -> GenerationError:
    return GenerationError(
        stage=stage,
        message=sanitize_error(error),
        impact=sanitize_error(impact),
        exit_code=exit_code,
        detail=str(error),
    )


def sanitize_error(value: object, limit: int = 300) -> str:
    text = _WHITESPACE.sub(" ", str(value or "")).strip()
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)([?&]"):
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    if not text:
        return "unspecified error"
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _write_diagnostic(settings: Settings, stage: str, error: object) -> None:
    if settings.log_path is None:
        return
    try:
        settings.log_path.parent.mkdir(parents=True, exist_ok=True)
        with settings.log_path.open("a", encoding="utf-8") as handle:
            handle.write("{}: {}\n".format(stage, sanitize_error(error, limit=2000)))
    except OSError:
        pass
