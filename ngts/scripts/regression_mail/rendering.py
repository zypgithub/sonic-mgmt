"""Deterministic plain-text and Outlook-compatible HTML rendering."""

from __future__ import annotations

import html
from typing import Iterable, List, Sequence

from ngts.scripts.regression_mail.models import GenerationError, ReportModel, RenderedMessage, SemanticGroup
from ngts.scripts.regression_mail.normalization import extract_public_issue_urls


class ReportRenderer:
    """Render the best available report without consulting external services."""

    def render(self, report: ReportModel) -> RenderedMessage:
        degraded = bool(report.errors)
        subject = "{}SONiC Regression Report - {}".format(
            "[Degraded] " if degraded else "",
            report.request.version,
        )
        return RenderedMessage(
            subject=subject,
            plain=self._plain(report),
            html=self._html(report),
        )

    def minimal(self, report: ReportModel, rendering_error: GenerationError) -> RenderedMessage:
        errors = list(report.errors)
        if rendering_error not in errors:
            errors.append(rendering_error)
        lines = [
            "SONiC Regression Report (degraded)",
            "Version: {}".format(report.request.version),
            "",
            "Generation Errors:",
        ]
        lines.extend(
            "- {}: {} Impact: {}".format(error.stage, error.message, error.impact)
            for error in errors
        )
        return RenderedMessage(
            subject="[Degraded] SONiC Regression Report - {}".format(report.request.version),
            plain="\n".join(lines) + "\n",
            html="",
        )

    def _plain(self, report: ReportModel) -> str:
        lines = [
            "SONiC Regression Report",
            "Version: {}".format(report.request.version),
        ]
        if report.errors:
            lines.extend(("", "Generation Errors:"))
            lines.extend(
                "- {}: {} Impact: {}".format(error.stage, error.message, error.impact)
                for error in report.errors
            )
        if report.dashboard:
            lines.extend(
                (
                    "",
                    "Coverage: {}".format(_percent(report.dashboard.coverage)),
                    "Pass rate: {}".format(_percent(report.dashboard.pass_rate)),
                )
            )
        if report.rc_status:
            lines.extend(
                (
                    "Image branch: {}".format(report.rc_status.image_branch),
                    "Image public hash: {}".format(report.rc_status.image_public_hash),
                )
            )
        if report.git:
            lines.extend(
                (
                    "sonic-mgmt branch: {}".format(report.git.internal_branch),
                    "sonic-mgmt public hash: {}".format(report.git.public_hash),
                )
            )
        if report.workbook:
            counts = report.workbook.result_counts
            lines.append(
                "Excel results: pass={pass_count}, fail={fail_count}, skipped={skip_count}".format(
                    pass_count=counts.get("pass", 0),
                    fail_count=counts.get("fail", 0),
                    skip_count=counts.get("skipped", 0),
                )
            )
        semantic = report.semantic
        if semantic:
            if semantic.executive_summary:
                lines.extend(("", "Summary:", semantic.executive_summary))
            lines.extend(_plain_groups("Failure Analysis", semantic.failure_groups))
            lines.extend(_plain_groups("The following tests were skipped", semantic.skip_groups))
            lines.extend(_plain_groups("Err msgs detected internally", semantic.internal_error_groups))
        return "\n".join(lines) + "\n"

    def _html(self, report: ReportModel) -> str:
        body: List[str] = [
            '<div style="font-family:Arial,sans-serif;color:#222;max-width:1200px">',
            "<h1>SONiC Regression Report</h1>",
            "<p><strong>Version:</strong> {}</p>".format(_e(report.request.version)),
        ]
        if report.errors:
            body.append(
                '<div style="border:2px solid #b91c1c;background:#fef2f2;padding:12px">'
                "<h2>Generation Errors</h2>{}</div>".format(_error_list(report.errors))
            )

        metadata = [
            ("Coverage", _percent(report.dashboard.coverage) if report.dashboard else ""),
            ("Pass rate", _percent(report.dashboard.pass_rate) if report.dashboard else ""),
            ("Image branch", report.rc_status.image_branch if report.rc_status else ""),
            ("Image public hash", report.rc_status.image_public_hash if report.rc_status else ""),
            ("sonic-mgmt branch", report.git.internal_branch if report.git else ""),
            ("sonic-mgmt public hash", report.git.public_hash if report.git else ""),
        ]
        body.extend(("<h2>Build Summary</h2>", _table(("Field", "Value"), metadata)))

        if report.workbook:
            hardware_rows = [
                (pair[0], pair[1], "", "")
                for pair in report.workbook.hardware_pairs
            ]
            body.extend(
                (
                    "<h2>Hardware reports</h2>",
                    _table(
                        ("HardwareSku", "Topology", "ReportId", "Internal Comments"),
                        hardware_rows,
                    ),
                )
            )

        semantic = report.semantic
        if semantic:
            if semantic.executive_summary:
                body.extend(
                    (
                        "<h2>Summary</h2>",
                        "<p>{}</p>".format(_e(semantic.executive_summary)),
                    )
                )
            body.extend(
                (
                    "<h2>Failure Analysis</h2>",
                    _group_table(semantic.failure_groups, ("Test", "Testbed")),
                    "<h2>The following tests were skipped</h2>",
                    _group_table(semantic.skip_groups, ("Test Names", "Testbeds")),
                    "<h2>Err msgs detected internally</h2>",
                    _group_table(semantic.internal_error_groups, ("Test Cases", "Testbeds")),
                )
            )

        coverage_rows = []
        if report.workbook:
            for row in report.workbook.skipped:
                for url in extract_public_issue_urls(row.message):
                    coverage_rows.append((url, row.test_name, row.message))
        body.extend(
            (
                "<h2>GitHub issues that affect tests coverage</h2>",
                _table(("Issue", "Test", "Reason"), coverage_rows),
                "<h2>Additional PR(s) on top of the public image hash</h2>",
                _table(
                    ("Pull Request",),
                    [(url,) for url in (report.rc_status.image_pr_urls if report.rc_status else [])],
                ),
                "<h2>Additional PR(s) on top of sonic-mgmt</h2>",
                _table(
                    ("Pull Request", "Title", "Author", "State"),
                    [(pr.url, pr.title, pr.author, pr.state) for pr in report.mgmt_prs],
                ),
            )
        )
        body.append("</div>")
        return "".join(body)


def _plain_groups(title: str, groups: Sequence[SemanticGroup]) -> List[str]:
    lines = ["", "{}:".format(title)]
    if not groups:
        lines.append("(none)")
        return lines
    for group in groups:
        lines.append(
            "- {} | {} | {} | {}".format(
                group.test_display,
                ", ".join(group.testbeds),
                group.comments,
                group.internal_comments,
            )
        )
    return lines


def _group_table(groups: Sequence[SemanticGroup], leading: Sequence[str]) -> str:
    rows = [
        (
            group.test_display,
            ", ".join(group.testbeds),
            group.comments,
            group.internal_comments,
        )
        for group in groups
    ]
    return _table((leading[0], leading[1], "Comments", "Internal Comments"), rows)


def _error_list(errors: Sequence[GenerationError]) -> str:
    return "<ul>{}</ul>".format(
        "".join(
            "<li><strong>{}</strong>: {} <em>Impact: {}</em></li>".format(
                _e(error.stage),
                _e(error.message),
                _e(error.impact),
            )
            for error in errors
        )
    )


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    row_values = list(rows)
    style = 'border:1px solid #bbb;padding:6px;text-align:left;vertical-align:top'
    header_html = "".join("<th style=\"{}\">{}</th>".format(style, _e(value)) for value in headers)
    if not row_values:
        body_html = '<tr><td style="{}" colspan="{}">No data available</td></tr>'.format(
            style,
            len(headers),
        )
    else:
        body_html = "".join(
            "<tr>{}</tr>".format(
                "".join("<td style=\"{}\">{}</td>".format(style, _e(value)) for value in row)
            )
            for row in row_values
        )
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse;width:100%;margin-bottom:16px">'
        "<thead><tr>{}</tr></thead><tbody>{}</tbody></table>".format(header_html, body_html)
    )


def _percent(value: object) -> str:
    if value is None:
        return ""
    return "{:.2f}%".format(float(value))


def _e(value: object) -> str:
    return html.escape(str(value or ""), quote=True).replace("\n", "<br>")
