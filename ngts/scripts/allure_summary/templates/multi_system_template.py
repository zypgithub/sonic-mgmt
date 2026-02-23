"""
Multi-System HTML Email Template for Allure Summary Tool.

This module generates HTML emails that aggregate results from multiple test systems.
"""

from datetime import datetime
from typing import List, Optional

from ngts.scripts.allure_summary.config import Colors
from ngts.scripts.allure_summary.models import (
    MultiSystemSummary, SystemResult, CrossSystemFailure, FailureAnalysis
)
from ngts.scripts.allure_summary.templates.email_template import (
    get_pass_rate_color, format_duration, get_likelihood_color
)
from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()


def render_multi_system_header(summary: MultiSystemSummary) -> str:
    """Render the header for multi-system email."""
    status_emoji = summary.get_status_emoji()
    rate_color = get_pass_rate_color(summary.overall_pass_rate)

    return f"""
    <div style="background-color: #1a1a2e; padding: 25px; border-radius: 8px; text-align: center;">
        <h1 style="margin: 0; font-size: 26px; color: #ffffff !important;">
            🔬 Multi-System Nightly Summary
        </h1>
        <p style="margin: 10px 0 0 0; color: #7dd3fc !important; font-size: 16px;">
            📦 Image: <strong style="color: #7dd3fc;">{summary.image_version}</strong>
        </p>
        <p style="margin: 8px 0 0 0; font-size: 14px; color: #d1d5db !important;">
            {summary.system_count} Systems | {datetime.now().strftime('%Y-%m-%d %H:%M')}
        </p>
    </div>
    <div style="background-color: #f0f9ff; padding: 20px; border-radius: 8px; text-align: center;
                margin-top: 15px; border: 2px solid #0ea5e9;">
        <span style="font-size: 36px; font-weight: bold; color: {rate_color};">
            {status_emoji} {summary.overall_pass_rate:.1f}%
        </span>
        <span style="color: #374151; font-size: 16px; display: block; margin-top: 5px;">
            Overall Pass Rate ({summary.total_passed}/{summary.total_tests} tests across {summary.system_count} systems)
        </span>
    </div>
    """


def render_systems_comparison_table(summary: MultiSystemSummary) -> str:
    """Render a comparison table of all systems."""
    rows = []

    for sys in summary.systems:
        s = sys.summary
        rate_color = get_pass_rate_color(s.pass_rate)
        status_emoji = s.get_status_emoji()
        new_failures = len(sys.new_failures)

        new_badge = ""
        if new_failures > 0:
            new_badge = f'<span style="background: {Colors.FAILED}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin-left: 8px;">🆕 {new_failures} new</span>'

        rows.append(f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <a href="{s.report_url}" style="color: {Colors.LINK}; text-decoration: none; font-weight: bold;">
                    {status_emoji} {sys.short_name}
                </a>
                {new_badge}
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">
                <span style="font-weight: bold; color: {rate_color};">{s.pass_rate:.1f}%</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">
                <span style="color: {Colors.PASSED};">{s.passed}</span> /
                <span style="color: {Colors.TEXT_SECONDARY};">{s.total}</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">
                <span style="color: {Colors.FAILED};">{s.failed}</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">
                <span style="color: {Colors.BROKEN};">{s.broken}</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center; color: {Colors.TEXT_SECONDARY};">
                {format_duration(s.duration_minutes)}
            </td>
        </tr>
        """)

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.TEXT_PRIMARY}; font-size: 18px; margin-bottom: 15px;
                   border-left: 4px solid {Colors.ACCENT}; padding-left: 12px;">
            📊 Systems Overview
        </h2>
        <table style="width: 100%; border-collapse: collapse; background: white;
                      border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <thead>
                <tr style="background: {Colors.BACKGROUND};">
                    <th style="padding: 12px; text-align: left; font-size: 13px; color: {Colors.TEXT_SECONDARY};">System</th>
                    <th style="padding: 12px; text-align: center; font-size: 13px; color: {Colors.TEXT_SECONDARY};">Pass Rate</th>
                    <th style="padding: 12px; text-align: center; font-size: 13px; color: {Colors.TEXT_SECONDARY};">Passed/Total</th>
                    <th style="padding: 12px; text-align: center; font-size: 13px; color: {Colors.TEXT_SECONDARY};">Failed</th>
                    <th style="padding: 12px; text-align: center; font-size: 13px; color: {Colors.TEXT_SECONDARY};">Broken</th>
                    <th style="padding: 12px; text-align: center; font-size: 13px; color: {Colors.TEXT_SECONDARY};">Duration</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """


def render_new_failures_summary(summary: MultiSystemSummary) -> str:
    """Render the new failures section showing all regressions across systems."""
    if not summary.all_new_failures:
        return f"""
        <div style="margin: 25px 0; padding: 20px; background: #e8f5e9; border-radius: 8px;
                    border-left: 4px solid {Colors.PASSED};">
            <h3 style="margin: 0; color: {Colors.PASSED}; font-size: 16px;">
                ✅ No New Regressions Across All Systems
            </h3>
            <p style="margin: 10px 0 0 0; color: {Colors.TEXT_SECONDARY}; font-size: 14px;">
                All failures are known from previous runs.
            </p>
        </div>
        """

    # Group new failures by system and collect report URLs
    failures_by_system = {}
    for sys in summary.systems:
        for test in sys.new_failures:
            if test.name not in failures_by_system:
                failures_by_system[test.name] = {
                    "test": test,
                    "systems": [],
                    "report_url": sys.summary.report_url,
                    "uid": test.uid
                }
            failures_by_system[test.name]["systems"].append(sys.short_name)

    rows = []
    for name, data in failures_by_system.items():
        test = data["test"]
        systems = data["systems"]
        report_url = data["report_url"]
        uid = data["uid"]

        system_badges = " ".join([
            f'<span style="background: {Colors.SECONDARY}; color: white; padding: 2px 6px; '
            f'border-radius: 4px; font-size: 10px; margin-right: 4px;">{s}</span>'
            for s in systems
        ])

        error_preview = test.error_message[:100] + "..." if len(test.error_message) > 100 else test.error_message

        # Build test link
        test_link = f'{report_url}#testresult/{uid}' if uid else report_url
        test_name_html = f'<a href="{test_link}" style="color: {Colors.FAILED}; text-decoration: none; font-weight: bold;">{name}</a>'

        # Known bug info
        bug_info_html = ""
        if test.has_known_bug:
            bug = test.known_bug
            bug_info_html = f'''
                <div style="margin-top: 6px; padding: 6px 10px; background: #faf5ff; border-radius: 4px; border-left: 3px solid #8b5cf6;">
                    <span style="font-size: 11px; color: #6b21a8;">
                        🐛 <strong>Known Bug:</strong> 
                        <a href="{bug.bug_url}" style="color: #7c3aed; text-decoration: none;">#{bug.bug_id}</a>
                        {f" - {bug.description[:60]}..." if bug.description else ""}
                        {f" | Status: <strong>{bug.status}</strong>" if bug.status else ""}
                        {f" | Assigned: <strong>{bug.assigned_to}</strong>" if bug.assigned_to else ""}
                    </span>
                </div>
            '''

        rows.append(f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <div>{test_name_html}</div>
                <div style="font-size: 12px; color: {Colors.TEXT_MUTED}; margin-top: 4px;
                            font-family: monospace; white-space: nowrap; overflow: hidden;
                            text-overflow: ellipsis; max-width: 500px;">
                    {error_preview}
                </div>
                {bug_info_html}
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; white-space: nowrap;">
                {system_badges}
            </td>
        </tr>
        """)

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.FAILED}; font-size: 18px; margin-bottom: 15px;
                   border-left: 4px solid {Colors.FAILED}; padding-left: 12px;">
            🆕 New Failures (Regressions) - {len(summary.all_new_failures)} Total
        </h2>
        <table style="width: 100%; border-collapse: collapse; background: white;
                      border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """


def render_cross_system_failures(summary: MultiSystemSummary) -> str:
    """Render tests that fail on multiple systems."""
    if not summary.cross_system_failures:
        return ""

    # Build a lookup map for test -> (report_url, uid)
    test_links = {}
    for sys in summary.systems:
        for test in sys.summary.failed_tests:
            if test.name not in test_links and test.uid:
                test_links[test.name] = (sys.summary.report_url, test.uid)

    rows = []
    for csf in summary.cross_system_failures[:15]:  # Limit to top 15
        system_badges = " ".join([
            f'<span style="background: {Colors.SECONDARY}; color: white; padding: 2px 6px; '
            f'border-radius: 4px; font-size: 10px; margin-right: 4px;">{s}</span>'
            for s in csf.systems
        ])

        new_badge = ""
        if csf.is_new_on_any:
            new_badge = f'<span style="background: {Colors.FAILED}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 10px; margin-left: 8px;">🆕 NEW</span>'

        # Build clickable test name
        if csf.test_name in test_links:
            report_url, uid = test_links[csf.test_name]
            test_link = f'{report_url}#testresult/{uid}'
            test_name_html = f'<a href="{test_link}" style="font-weight: bold; color: {Colors.LINK}; text-decoration: none;">{csf.test_name}</a>'
        else:
            test_name_html = f'<span style="font-weight: bold; color: {Colors.TEXT_PRIMARY};">{csf.test_name}</span>'

        rows.append(f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                {test_name_html}
                {new_badge}
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">
                <span style="font-weight: bold; color: {Colors.WARNING};">{csf.failure_count}</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">
                {system_badges}
            </td>
        </tr>
        """)

    remaining = len(summary.cross_system_failures) - 15
    footer = ""
    if remaining > 0:
        footer = f'<p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin-top: 10px;">... and {remaining} more cross-system failures</p>'

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.WARNING}; font-size: 18px; margin-bottom: 15px;
                   border-left: 4px solid {Colors.WARNING}; padding-left: 12px;">
            🔗 Cross-System Failures ({len(summary.cross_system_failures)} tests fail on multiple systems)
        </h2>
        <p style="color: {Colors.TEXT_SECONDARY}; font-size: 13px; margin-bottom: 15px;">
            These tests fail on more than one system, indicating a likely product issue.
        </p>
        <table style="width: 100%; border-collapse: collapse; background: white;
                      border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <thead>
                <tr style="background: {Colors.BACKGROUND};">
                    <th style="padding: 12px; text-align: left; font-size: 13px; color: {Colors.TEXT_SECONDARY};">Test Name</th>
                    <th style="padding: 12px; text-align: center; font-size: 13px; color: {Colors.TEXT_SECONDARY};"># Systems</th>
                    <th style="padding: 12px; text-align: right; font-size: 13px; color: {Colors.TEXT_SECONDARY};">Affected Systems</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        {footer}
    </div>
    """


def render_per_system_details(summary: MultiSystemSummary) -> str:
    """Render collapsible details for each system."""
    sections = []

    for sys in summary.systems:
        s = sys.summary
        status_emoji = s.get_status_emoji()
        rate_color = get_pass_rate_color(s.pass_rate)

        # Build failure list for this system
        failure_items = []
        for test in s.failed_tests[:10]:
            status_color = Colors.FAILED if test.status == "failed" else Colors.BROKEN
            new_badge = '<span style="background: #ff6b6b; color: white; padding: 1px 5px; border-radius: 8px; font-size: 9px; margin-left: 6px;">NEW</span>' if test.is_new_failure else ""
            flaky_badge = '<span style="background: #ffd93d; color: #333; padding: 1px 5px; border-radius: 8px; font-size: 9px; margin-left: 6px;">FLAKY</span>' if test.flaky else ""

            # Known bug badge
            bug_badge = ""
            if test.has_known_bug:
                bug_id = test.known_bug.bug_id
                bug_url = test.known_bug.bug_url
                bug_status = test.known_bug.status or "Bug"
                bug_badge = f'<a href="{bug_url}" style="background: #8b5cf6; color: white; padding: 1px 5px; border-radius: 8px; font-size: 9px; margin-left: 6px; text-decoration: none;">🐛 {bug_id}</a>'

            failure_items.append(f"""
            <div style="padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px;">
                <span style="color: {status_color};">●</span>
                <a href="{s.report_url}#testresult/{test.uid}" style="color: {Colors.LINK}; text-decoration: none;">
                    {test.name}
                </a>
                {new_badge}{flaky_badge}{bug_badge}
            </div>
            """)

        remaining = len(s.failed_tests) - 10
        if remaining > 0:
            failure_items.append(f"""
            <div style="padding: 8px 12px; color: {Colors.TEXT_MUTED}; font-size: 12px;">
                ... and {remaining} more failures
            </div>
            """)

        failures_html = "".join(failure_items) if failure_items else f'<div style="padding: 12px; color: {Colors.TEXT_SECONDARY};">No failures</div>'

        sections.append(f"""
        <div style="margin-bottom: 20px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
            <div style="background: {Colors.BACKGROUND}; padding: 15px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <a href="{s.report_url}" style="font-size: 16px; font-weight: bold; color: {Colors.LINK}; text-decoration: none;">
                        {status_emoji} {sys.short_name}
                    </a>
                    <span style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin-left: 10px;">
                        Report #{s.report_id}
                    </span>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 18px; font-weight: bold; color: {rate_color};">{s.pass_rate:.1f}%</span>
                    <div style="font-size: 12px; color: {Colors.TEXT_SECONDARY};">
                        {s.passed}/{s.total} passed | {s.failed} failed | {s.broken} broken
                    </div>
                </div>
            </div>
            <div style="max-height: 300px; overflow-y: auto;">
                {failures_html}
            </div>
        </div>
        """)

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.TEXT_PRIMARY}; font-size: 18px; margin-bottom: 15px;
                   border-left: 4px solid {Colors.ACCENT}; padding-left: 12px;">
            📋 Per-System Details
        </h2>
        {''.join(sections)}
    </div>
    """


def render_multi_system_footer(summary: MultiSystemSummary) -> str:
    """Render the footer for multi-system email."""
    return f"""
    <div style="text-align: center; color: {Colors.TEXT_SECONDARY}; font-size: 12px;
                margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
        <span style="background: #667eea; color: white; padding: 2px 8px; border-radius: 10px;
                     font-size: 10px; margin-right: 8px;">📊 Multi-System</span>
        Generated by Allure Nightly Summary Tool | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """


def generate_multi_system_email(
    summary: MultiSystemSummary,
    all_analyses: Optional[List[FailureAnalysis]] = None,
    llm_analysis: Optional[str] = None
) -> str:
    """
    Generate complete HTML email for multi-system summary.

    Args:
        summary: MultiSystemSummary with aggregated data
        all_analyses: Optional combined failure analyses
        llm_analysis: Optional LLM-generated analysis HTML

    Returns:
        Complete HTML email string
    """
    logger.info(f"Generating multi-system HTML email for {summary.system_count} systems...")

    header = render_multi_system_header(summary)
    systems_table = render_systems_comparison_table(summary)
    new_failures = render_new_failures_summary(summary)
    cross_system = render_cross_system_failures(summary)
    per_system = render_per_system_details(summary)
    footer = render_multi_system_footer(summary)

    # AI analysis section if available
    analysis_section = llm_analysis if llm_analysis else ""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6;
             color: {Colors.TEXT_PRIMARY}; max-width: 950px; margin: 0 auto; padding: 20px;
             background-color: #fafafa;">
    {header}
    {systems_table}
    {new_failures}
    {cross_system}
    {analysis_section}
    {per_system}
    {footer}
</body>
</html>
"""

    logger.debug(f"Generated multi-system HTML email ({len(html)} bytes)")
    return html
