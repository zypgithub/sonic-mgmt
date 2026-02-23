"""
HTML Email Templates for Allure Summary Tool.

This module contains all HTML/CSS templates for generating beautiful emails.
"""

import re
from datetime import datetime
from typing import List, Optional

from ngts.scripts.allure_summary.config import Colors, BugLikelihood
from ngts.scripts.allure_summary.models import ReportSummary, FailureAnalysis
from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()


def extract_ip_from_project(project_name: str) -> str:
    """
    Extract IP address from project name.

    Example: nvos-juliet-10-7-145-52 -> 10.7.145.52
    """
    # Look for pattern like 10-7-145-52 (IP with dashes)
    match = re.search(r'(\d+)-(\d+)-(\d+)-(\d+)(?:-|$)', project_name)
    if match:
        return f"{match.group(1)}.{match.group(2)}.{match.group(3)}.{match.group(4)}"
    return ""


def extract_device_name(project_name: str) -> str:
    """
    Extract device name from project name.

    Example: nvos-juliet-10-7-145-52 -> juliet
    """
    # Remove nvos- prefix and IP suffix
    name = project_name.replace("nvos-", "").replace("nvue-", "")
    # Remove IP part (digits with dashes at the end)
    name = re.sub(r'-?\d+-\d+-\d+-\d+.*$', '', name)
    return name.strip('-') or project_name


def get_pass_rate_color(pass_rate: float) -> str:
    """Get color based on pass rate percentage."""
    if pass_rate >= 95:
        return Colors.EXCELLENT
    elif pass_rate >= 80:
        return Colors.GOOD
    elif pass_rate >= 60:
        return Colors.WARNING
    return Colors.CRITICAL


def get_likelihood_color(likelihood: int) -> str:
    """Get color based on bug likelihood percentage."""
    if likelihood >= 85:
        return Colors.HIGH_BUG
    elif likelihood >= BugLikelihood.HIGH:
        return Colors.LIKELY_BUG
    elif likelihood >= BugLikelihood.MEDIUM:
        return Colors.UNCERTAIN
    elif likelihood >= BugLikelihood.LOW:
        return Colors.LIKELY_TEST
    return Colors.INFRA_ISSUE


def format_duration(minutes: float) -> str:
    """Format duration in human-readable format."""
    if minutes < 60:
        return f"{minutes:.0f} min"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours}h {mins}m"


def render_pie_chart(summary: ReportSummary) -> str:
    """
    Render an SVG pie chart showing test results distribution.
    Uses SVG for maximum email client compatibility.
    """
    import math

    total = summary.total
    if total == 0:
        return ""

    # Data for the pie chart
    segments = [
        (summary.passed, Colors.PASSED, "Passed"),
        (summary.failed, Colors.FAILED, "Failed"),
        (summary.broken, Colors.BROKEN, "Broken"),
        (summary.skipped, Colors.SKIPPED, "Skipped"),
    ]

    # Filter out zero segments
    segments = [(count, color, label) for count, color, label in segments if count > 0]

    # SVG parameters
    cx, cy = 100, 100  # Center
    r = 80             # Radius

    # Calculate pie slices
    paths = []
    current_angle = -90  # Start from top (12 o'clock)

    for count, color, label in segments:
        if count == 0:
            continue

        percentage = count / total
        angle = percentage * 360

        # Calculate arc endpoints
        start_rad = math.radians(current_angle)
        end_rad = math.radians(current_angle + angle)

        x1 = cx + r * math.cos(start_rad)
        y1 = cy + r * math.sin(start_rad)
        x2 = cx + r * math.cos(end_rad)
        y2 = cy + r * math.sin(end_rad)

        # Large arc flag (1 if angle > 180)
        large_arc = 1 if angle > 180 else 0

        # Create SVG path
        if percentage >= 0.999:
            # Full circle - use two arcs
            paths.append(f'''
                <circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" />
            ''')
        else:
            paths.append(f'''
                <path d="M {cx} {cy} L {x1} {y1} A {r} {r} 0 {large_arc} 1 {x2} {y2} Z"
                      fill="{color}" />
            ''')

        current_angle += angle

    # Build legend
    legend_items = []
    y_offset = 15
    for count, color, label in segments:
        if count == 0:
            continue
        pct = (count / total) * 100
        legend_items.append(f'''
            <div style="display: flex; align-items: center; margin: 4px 0;">
                <div style="width: 12px; height: 12px; background: {color}; border-radius: 2px; margin-right: 8px;"></div>
                <span style="font-size: 13px; color: {Colors.TEXT_PRIMARY};">{label}: {count} ({pct:.1f}%)</span>
            </div>
        ''')

    # Pass rate color and status
    pass_rate = summary.pass_rate
    rate_color = get_pass_rate_color(pass_rate)
    status_emoji = "✅" if pass_rate >= 80 else "⚠️" if pass_rate >= 60 else "🔴"

    return f"""
    <div style="display: flex; align-items: center; justify-content: center; margin: 20px 0; flex-wrap: wrap;
                background: {Colors.BACKGROUND}; padding: 20px; border-radius: 8px;">
        <!-- Pie Chart -->
        <div style="flex-shrink: 0; margin: 10px 20px;">
            <svg width="200" height="200" viewBox="0 0 200 200">
                {''.join(paths)}
                <!-- Center circle for donut effect -->
                <circle cx="{cx}" cy="{cy}" r="45" fill="white" />
                <!-- Pass rate in center -->
                <text x="{cx}" y="{cy - 8}" text-anchor="middle"
                      style="font-size: 24px; font-weight: bold; fill: {rate_color};">
                    {pass_rate:.0f}%
                </text>
                <text x="{cx}" y="{cy + 15}" text-anchor="middle"
                      style="font-size: 12px; fill: {Colors.TEXT_SECONDARY};">
                    Pass Rate
                </text>
            </svg>
        </div>
        <!-- Legend -->
        <div style="margin: 10px 20px;">
            <div style="font-size: 16px; font-weight: bold; color: {Colors.TEXT_PRIMARY}; margin-bottom: 10px;">
                {status_emoji} Test Results
            </div>
            {''.join(legend_items)}
            <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd;">
                <span style="font-size: 14px; color: {Colors.TEXT_SECONDARY};">
                    <strong>Total:</strong> {total} tests
                </span>
            </div>
        </div>
    </div>
    """


def render_header(summary: ReportSummary) -> str:
    """Render the email header section."""
    ip_address = extract_ip_from_project(summary.project_name)
    device_name = extract_device_name(summary.project_name)

    # Build IP info line
    ip_line = f'<span style="font-size: 13px;">📍 IP: <strong>{ip_address}</strong></span>' if ip_address else ""

    return f"""
    <div style="background-color: #1a1a2e; padding: 25px; border-radius: 8px; text-align: center;">
        <h1 style="margin: 0; font-size: 24px; color: #ffffff;">🔬 Nightly Regression Summary</h1>
        <p style="margin: 10px 0 0 0; color: #e0e0e0; font-size: 16px;">
            <strong>{device_name.upper()}</strong> ({summary.project_name})
        </p>
        {f'<p style="margin: 8px 0 0 0; color: #a0d8ef;">{ip_line}</p>' if ip_line else ''}
        <p style="margin: 8px 0 0 0; font-size: 14px; color: #888888;">
            Report #{summary.report_id} | {datetime.now().strftime('%Y-%m-%d %H:%M')}
        </p>
    </div>
    """


def render_stats_cards(summary: ReportSummary) -> str:
    """Render the statistics cards section."""
    color = get_pass_rate_color(summary.pass_rate)

    return f"""
    <div style="display: flex; justify-content: space-between; margin: 20px 0; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px;
                    background: {Colors.BACKGROUND}; border-radius: 8px; border-left: 4px solid {Colors.PASSED};">
            <div style="font-size: 28px; font-weight: bold; color: {Colors.PASSED};">{summary.passed}</div>
            <div style="font-size: 12px; color: {Colors.TEXT_SECONDARY}; text-transform: uppercase;">Passed</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px;
                    background: {Colors.BACKGROUND}; border-radius: 8px; border-left: 4px solid {Colors.FAILED};">
            <div style="font-size: 28px; font-weight: bold; color: {Colors.FAILED};">{summary.failed}</div>
            <div style="font-size: 12px; color: {Colors.TEXT_SECONDARY}; text-transform: uppercase;">Failed</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px;
                    background: {Colors.BACKGROUND}; border-radius: 8px; border-left: 4px solid {Colors.BROKEN};">
            <div style="font-size: 28px; font-weight: bold; color: {Colors.BROKEN};">{summary.broken}</div>
            <div style="font-size: 12px; color: {Colors.TEXT_SECONDARY}; text-transform: uppercase;">Broken</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px;
                    background: {Colors.BACKGROUND}; border-radius: 8px; border-left: 4px solid {Colors.SKIPPED};">
            <div style="font-size: 28px; font-weight: bold; color: {Colors.SKIPPED};">{summary.skipped}</div>
            <div style="font-size: 12px; color: {Colors.TEXT_SECONDARY}; text-transform: uppercase;">Skipped</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px;
                    background: {Colors.BACKGROUND}; border-radius: 8px; border-left: 4px solid {color};">
            <div style="font-size: 28px; font-weight: bold; color: {color};">{summary.pass_rate:.1f}%</div>
            <div style="font-size: 12px; color: {Colors.TEXT_SECONDARY}; text-transform: uppercase;">Pass Rate</div>
        </div>
    </div>
    """


def render_info_box(summary: ReportSummary) -> str:
    """Render the info box with report details."""
    duration = format_duration(summary.duration_minutes)

    return f"""
    <div style="background: {Colors.BACKGROUND}; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Total Tests:</strong> {summary.total}</p>
        <p style="margin: 5px 0 0 0;"><strong>Duration:</strong> {duration}</p>
        <p style="margin: 5px 0 0 0;">
            <strong>Report Link:</strong>
            <a href="{summary.report_url}" style="color: {Colors.LINK};">{summary.report_url}</a>
        </p>
    </div>
    """


def render_likely_bugs_section(
    analyses: List[FailureAnalysis],
    report_url: str
) -> str:
    """Render the 'Likely Product Bugs' section."""
    likely_bugs = [a for a in analyses if a.bug_likelihood >= BugLikelihood.HIGH]

    if not likely_bugs:
        return ""

    logger.debug(f"Rendering {len(likely_bugs)} likely bugs")

    bug_rows = ""
    for analysis in likely_bugs:
        test = analysis.test
        test_link = f"{report_url}#suites/{test.uid}" if test.uid else report_url
        likelihood_color = get_likelihood_color(analysis.bug_likelihood)
        error_preview = test.error_message[:150] + "..." if len(test.error_message) > 150 else test.error_message

        bug_rows += f"""
        <div style="background: #fff; border: 1px solid {Colors.BORDER};
                    border-left: 4px solid {likelihood_color}; border-radius: 6px; margin: 10px 0; padding: 12px;">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="background: {likelihood_color}; color: white; padding: 2px 8px;
                            border-radius: 10px; font-size: 11px; font-weight: bold;">
                    {analysis.bug_likelihood}% BUG
                </span>
                <a href="{test_link}" style="color: {Colors.TEXT_PRIMARY}; font-weight: bold;
                          margin-left: 10px; text-decoration: none; font-size: 14px;">
                    {test.name}
                </a>
            </div>
            <div style="color: {Colors.TEXT_SECONDARY}; font-size: 13px; margin-left: 4px;">
                <strong>Why:</strong> {analysis.reason}
            </div>
            <div style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin-top: 6px; font-family: monospace;
                        background: {Colors.BACKGROUND}; padding: 6px; border-radius: 4px;
                        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {error_preview}
            </div>
        </div>
        """

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.HIGH_BUG}; margin: 0 0 15px 0; font-size: 18px;">
            🐛 Likely Product Bugs ({len(likely_bugs)} tests)
        </h2>
        <p style="color: {Colors.TEXT_SECONDARY}; font-size: 13px; margin: 0 0 15px 0;">
            These failures show high confidence of being actual product bugs based on error analysis.
            Click any test name to view details in Allure.
        </p>
        {bug_rows}
    </div>
    """


def render_test_issues_section(
    analyses: List[FailureAnalysis],
    report_url: str,
    max_display: int = 15
) -> str:
    """Render the 'Test/Infrastructure Issues' section."""
    test_issues = [a for a in analyses if a.bug_likelihood < BugLikelihood.HIGH]

    if not test_issues:
        return ""

    logger.debug(f"Rendering {len(test_issues)} test issues (showing max {max_display})")

    other_rows = ""
    for analysis in test_issues[:max_display]:
        test = analysis.test
        test_link = f"{report_url}#suites/{test.uid}" if test.uid else report_url
        likelihood_color = get_likelihood_color(analysis.bug_likelihood)

        other_rows += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 8px; width: 70px;">
                <span style="background: {likelihood_color}; color: white; padding: 2px 6px;
                            border-radius: 8px; font-size: 10px;">
                    {analysis.bug_likelihood}%
                </span>
            </td>
            <td style="padding: 8px;">
                <a href="{test_link}" style="color: {Colors.LINK}; text-decoration: none; font-size: 13px;">
                    {test.name}
                </a>
                <div style="color: {Colors.TEXT_MUTED}; font-size: 11px; margin-top: 2px;">
                    {analysis.reason}
                </div>
            </td>
        </tr>
        """

    more_text = ""
    if len(test_issues) > max_display:
        more_text = f'''
        <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin-top: 10px;">
            ... and {len(test_issues) - max_display} more tests
        </p>
        '''

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.TEXT_SECONDARY}; margin: 0 0 15px 0; font-size: 16px;">
            🔧 Test/Infrastructure Issues ({len(test_issues)} tests)
        </h2>
        <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin: 0 0 10px 0;">
            Lower bug likelihood - may be test setup, environment, or timing issues.
        </p>
        <table style="width: 100%; border-collapse: collapse;">
            {other_rows}
        </table>
        {more_text}
    </div>
    """


def render_footer() -> str:
    """Render the email footer."""
    return f"""
    <div style="text-align: center; color: {Colors.TEXT_SECONDARY}; font-size: 12px;
                margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
        Generated by Allure Nightly Summary Tool | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """


def generate_html_email(
    summary: ReportSummary,
    analyses: List[FailureAnalysis],
    llm_analysis: Optional[str] = None
) -> str:
    """
    Generate complete HTML email content.

    Args:
        summary: Report summary data
        analyses: List of failure analyses
        llm_analysis: Optional LLM-generated analysis HTML

    Returns:
        Complete HTML email string
    """
    logger.info("Generating HTML email content...")

    header = render_header(summary)
    pie_chart = render_pie_chart(summary)
    info = render_info_box(summary)
    bugs = render_likely_bugs_section(analyses, summary.report_url)
    issues = render_test_issues_section(analyses, summary.report_url)
    footer = render_footer()

    # Use LLM analysis if available, otherwise just show our analysis
    analysis_section = llm_analysis if llm_analysis else ""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6;
             color: {Colors.TEXT_PRIMARY}; max-width: 900px; margin: 0 auto; padding: 20px;">
    {header}
    {pie_chart}
    {info}
    {analysis_section}
    {bugs}
    {issues}
    {footer}
</body>
</html>
"""

    logger.debug(f"Generated HTML email ({len(html)} bytes)")
    return html
