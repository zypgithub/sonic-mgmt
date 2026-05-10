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

    # Build IP and version info
    ip_part = f'📍 IP: <strong>{ip_address}</strong>' if ip_address else ""
    version_part = f'📦 Image: <strong>{summary.image_version}</strong>' if summary.image_version else ""

    # Combine IP and version on same line
    info_parts = [p for p in [ip_part, version_part] if p]
    info_line = ' &nbsp;|&nbsp; '.join(info_parts) if info_parts else ""

    return f"""
    <div style="background-color: #1a1a2e; padding: 25px; border-radius: 8px; text-align: center;">
        <h1 style="margin: 0; font-size: 24px; color: #ffffff;">🔬 Nightly Regression Summary</h1>
        <p style="margin: 10px 0 0 0; color: #e0e0e0; font-size: 16px;">
            <strong>{device_name.upper()}</strong> ({summary.project_name})
        </p>
        {f'<p style="margin: 8px 0 0 0; color: #a0d8ef; font-size: 13px;">{info_line}</p>' if info_line else ''}
        <p style="margin: 8px 0 0 0; font-size: 14px; color: #888888;">
            Report #{summary.report_id} | {datetime.now().strftime('%Y-%m-%d %H:%M')}
        </p>
    </div>
    """


def render_version_info(summary: ReportSummary) -> str:
    """Render a concise firmware versions line."""
    if not summary.firmware_versions:
        return ""

    # Build simple inline list - core components first, then CPLDs
    core_items = []
    for name in ['ASIC', 'BIOS', 'BMC']:
        if name in summary.firmware_versions:
            core_items.append(f"<b>{name}</b>: {summary.firmware_versions[name]}")

    # Collect CPLD versions (simplified: just show count or first few)
    cpld_items = []
    for name, version in sorted(summary.firmware_versions.items()):
        if 'CPLD' in name.upper():
            # Shorten CPLD name: CPLD1, CPLD2, etc.
            short_name = name.replace('CPLD', '').strip() or name
            cpld_items.append(f"{short_name}:{version}")

    if not core_items and not cpld_items:
        return ""

    core_text = " | ".join(core_items)
    cpld_text = ""
    if cpld_items:
        cpld_text = f' | <b>CPLD</b>: {", ".join(cpld_items)}'

    return f"""
    <div style="margin: 10px 0; padding: 8px 16px; background: #f7fafc;
                border-radius: 6px; border: 1px solid #e2e8f0; text-align: center;">
        <span style="font-size: 11px; color: #4a5568;">
            🔧 {core_text}{cpld_text}
        </span>
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


def render_history_badge(test) -> str:
    """Render a history badge for a test."""
    if not test.history or test.history.total < 3:
        return ""

    h = test.history
    if h.is_flaky:
        return f'''<span style="background: #f6ad55; color: #744210; padding: 1px 6px;
                              border-radius: 8px; font-size: 10px; margin-left: 6px;"
                         title="Flaky: {h.ratio_str}">🎲 {h.pass_rate:.0f}%</span>'''
    elif h.is_consistently_failing:
        return f'''<span style="background: #fc8181; color: #742a2a; padding: 1px 6px;
                              border-radius: 8px; font-size: 10px; margin-left: 6px;"
                         title="Consistently failing: {h.ratio_str}">📉 {h.pass_rate:.0f}%</span>'''
    elif h.pass_rate >= 80:
        return f'''<span style="background: #9ae6b4; color: #276749; padding: 1px 6px;
                              border-radius: 8px; font-size: 10px; margin-left: 6px;"
                         title="Usually passes: {h.ratio_str}">📊 {h.pass_rate:.0f}%</span>'''
    else:
        return f'''<span style="background: #e2e8f0; color: #4a5568; padding: 1px 6px;
                              border-radius: 8px; font-size: 10px; margin-left: 6px;"
                         title="History: {h.ratio_str}">📊 {h.pass_rate:.0f}%</span>'''


def render_known_bug_badge(test) -> str:
    """Render a known bug badge for a test (no person names shown)."""
    if not hasattr(test, 'known_bug') or not test.known_bug:
        return ""

    kb = test.known_bug

    # Only show bug ID badges - no person names
    if kb.status.lower() == 'fixed' and kb.bug_id:
        return f'''<a href="{kb.bug_url}" style="text-decoration: none;">
                    <span style="background: #48bb78; color: white; padding: 1px 6px;
                                border-radius: 8px; font-size: 10px; margin-left: 6px;"
                          title="Fixed">✅ #{kb.bug_id}</span></a>'''
    elif kb.bug_id:
        return f'''<a href="{kb.bug_url}" style="text-decoration: none;">
                    <span style="background: #805ad5; color: white; padding: 1px 6px;
                                border-radius: 8px; font-size: 10px; margin-left: 6px;"
                          title="Known bug">🐛 #{kb.bug_id}</span></a>'''
    elif kb.status.lower() == 'test issue':
        return f'''<span style="background: #ed8936; color: white; padding: 1px 6px;
                              border-radius: 8px; font-size: 10px; margin-left: 6px;"
                         title="Test code issue">🔧 TEST</span>'''
    return ""


def render_commit_badges(commits, is_fix: bool = False) -> str:
    """Render commit correlation badges for a test."""
    if not commits:
        return ""

    badges = ""
    for commit in commits[:2]:  # Show max 2 commits
        pct = commit.probability_pct
        if pct < 20:
            continue

        # Color based on probability
        if pct >= 50:
            color = "#38a169" if is_fix else "#e53e3e"
        elif pct >= 30:
            color = "#68d391" if is_fix else "#fc8181"
        else:
            color = "#9ae6b4" if is_fix else "#feb2b2"

        icon = "✅" if is_fix else "🔍"
        repo_tag = "test" if commit.repo == "sonic-mgmt" else "nvos"

        # Truncate subject appropriately
        subject = commit.subject[:60] + "..." if len(commit.subject) > 60 else commit.subject

        badges += f'''
        <div style="margin-top: 4px; font-size: 11px;">
            <span style="background: {color}; color: white; padding: 1px 6px;
                        border-radius: 8px; font-size: 10px;"
                  title="{commit.reasons}">
                {icon} {pct}%
            </span>
            <span style="background: #718096; color: white; padding: 1px 4px;
                        border-radius: 4px; font-size: 9px; margin-left: 4px;">
                {repo_tag}
            </span>
            <span style="color: {Colors.TEXT_SECONDARY}; font-size: 11px; margin-left: 4px;">
                {subject}
            </span>
        </div>
        '''

    return badges


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
        history_badge = render_history_badge(test)
        known_bug_badge = render_known_bug_badge(test)
        new_badge = '<span style="background: #e53e3e; color: white; padding: 1px 6px; border-radius: 8px; font-size: 10px; margin-left: 6px;">🆕 NEW</span>' if test.is_new_failure else ""

        bug_rows += f"""
        <div style="background: #fff; border: 1px solid {Colors.BORDER};
                    border-left: 4px solid {likelihood_color}; border-radius: 6px; margin: 10px 0; padding: 12px;">
            <div style="margin-bottom: 8px;">
                <span style="background: {likelihood_color}; color: white; padding: 2px 8px;
                            border-radius: 10px; font-size: 11px; font-weight: bold;">
                    {analysis.bug_likelihood}% BUG
                </span>
                {known_bug_badge}
                {new_badge}
                {history_badge}
            </div>
            <div style="margin-bottom: 6px;">
                <a href="{test_link}" style="color: {Colors.TEXT_PRIMARY}; font-weight: bold;
                          text-decoration: none; font-size: 14px;">
                    {test.name}
                </a>
            </div>
            <div style="color: {Colors.TEXT_SECONDARY}; font-size: 13px;">
                <strong>Why:</strong> {analysis.reason}
            </div>
            <div style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin-top: 6px; font-family: monospace;
                        background: {Colors.BACKGROUND}; padding: 6px; border-radius: 4px;
                        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {error_preview}
            </div>
            {render_commit_badges(getattr(test, 'likely_cause_commits', []), is_fix=False) if test.is_new_failure else ''}
        </div>
        """

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.HIGH_BUG}; margin: 0 0 15px 0; font-size: 18px;">
            🐛 Likely Product Bugs ({len(likely_bugs)} tests)
        </h2>
        <p style="color: {Colors.TEXT_SECONDARY}; font-size: 13px; margin: 0 0 15px 0;">
            These failures show high confidence of being actual product bugs based on error analysis.
            🆕 = New regression | 🔍 = Likely cause commit
        </p>
        {bug_rows}
    </div>
    """


def render_special_issues_section(
    analyses: List[FailureAnalysis],
    report_url: str
) -> str:
    """Render a special section highlighting timeout and invalid parameter issues."""
    # Filter for timeout and invalid parameter issues
    timeout_issues = [a for a in analyses if a.is_timeout]
    invalid_param_issues = [a for a in analyses if a.is_invalid_param]

    if not timeout_issues and not invalid_param_issues:
        return ""

    sections = ""

    # Timeout section
    if timeout_issues:
        timeout_rows = ""
        for analysis in timeout_issues:
            test = analysis.test
            test_link = f"{report_url}#suites/{test.uid}" if test.uid else report_url
            timeout_rows += f"""
            <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; margin: 8px 0; padding: 10px;">
                <div style="display: flex; align-items: center;">
                    <span style="font-size: 18px; margin-right: 8px;">⏱️</span>
                    <a href="{test_link}" style="color: {Colors.TEXT_PRIMARY}; font-weight: bold; text-decoration: none; font-size: 14px;">
                        {test.name}
                    </a>
                </div>
                <div style="color: #856404; font-size: 12px; margin-top: 6px; margin-left: 26px;">
                    {test.error_message[:200] if test.error_message else 'Test exceeded timeout limit'}
                </div>
            </div>
            """
        sections += f"""
        <div style="margin-bottom: 15px;">
            <h3 style="color: #856404; margin: 0 0 10px 0; font-size: 15px;">
                ⏱️ Timeout Issues ({len(timeout_issues)} tests)
            </h3>
            <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin: 0 0 8px 0;">
                Tests that exceeded their timeout limit. May indicate slow environment, long-running operations, or tests that need timeout adjustment.
            </p>
            {timeout_rows}
        </div>
        """

    # Invalid parameter section
    if invalid_param_issues:
        invalid_rows = ""
        for analysis in invalid_param_issues:
            test = analysis.test
            test_link = f"{report_url}#suites/{test.uid}" if test.uid else report_url
            # Extract relevant part of error message
            error_preview = test.error_message[:300] if test.error_message else 'Invalid parameter/command error'
            invalid_rows += f"""
            <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px; margin: 8px 0; padding: 10px;">
                <div style="display: flex; align-items: center;">
                    <span style="font-size: 18px; margin-right: 8px;">⚠️</span>
                    <a href="{test_link}" style="color: {Colors.TEXT_PRIMARY}; font-weight: bold; text-decoration: none; font-size: 14px;">
                        {test.name}
                    </a>
                </div>
                <div style="color: #721c24; font-size: 12px; margin-top: 6px; margin-left: 26px; font-family: monospace;
                            background: rgba(255,255,255,0.5); padding: 6px; border-radius: 4px; white-space: pre-wrap; word-break: break-word;">
                    {error_preview}
                </div>
            </div>
            """
        sections += f"""
        <div style="margin-bottom: 15px;">
            <h3 style="color: #721c24; margin: 0 0 10px 0; font-size: 15px;">
                ⚠️ Invalid Parameter/Command Issues ({len(invalid_param_issues)} tests)
            </h3>
            <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin: 0 0 8px 0;">
                Tests using incorrect CLI syntax or parameters. These are likely test issues that need CLI command updates.
            </p>
            {invalid_rows}
        </div>
        """

    return f"""
    <div style="margin: 25px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6;">
        <h2 style="color: {Colors.TEXT_PRIMARY}; margin: 0 0 15px 0; font-size: 17px;">
            🔍 Special Attention Required
        </h2>
        {sections}
    </div>
    """


def render_flaky_tests_section(
    analyses: List[FailureAnalysis],
    report_url: str
) -> str:
    """Render a section highlighting flaky tests."""
    # Find flaky tests (tests with history showing inconsistent results)
    flaky_tests = [a for a in analyses if a.test.history and a.test.history.is_flaky]

    if not flaky_tests:
        return ""

    logger.debug(f"Rendering {len(flaky_tests)} flaky tests")

    flaky_rows = ""
    for analysis in flaky_tests[:10]:
        test = analysis.test
        h = test.history
        test_link = f"{report_url}#suites/{test.uid}" if test.uid else report_url

        flaky_rows += f"""
        <div style="background: #fffaf0; border: 1px solid #f6ad55; border-radius: 6px; margin: 8px 0; padding: 10px;">
            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px;">
                <a href="{test_link}" style="color: {Colors.TEXT_PRIMARY}; font-weight: 600; text-decoration: none; font-size: 13px;">
                    {test.name}
                </a>
                <span style="background: #f6ad55; color: #744210; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;">
                    {h.pass_rate:.0f}% pass rate
                </span>
                <span style="color: {Colors.TEXT_MUTED}; font-size: 11px;">
                    ({h.passed} passed / {h.failed + h.broken} failed of {h.total} runs)
                </span>
            </div>
        </div>
        """

    return f"""
    <div style="margin: 25px 0; padding: 15px; background: #fffaf0; border-radius: 8px; border: 1px solid #f6ad55;">
        <h2 style="color: #c05621; margin: 0 0 10px 0; font-size: 16px;">
            🎲 Flaky Tests ({len(flaky_tests)} tests)
        </h2>
        <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin: 0 0 10px 0;">
            These tests show inconsistent results across runs (20-80% pass rate). May need investigation for timing issues or test stability.
        </p>
        {flaky_rows}
        {f'<p style="color: {Colors.TEXT_MUTED}; font-size: 11px; margin-top: 8px;">... and {len(flaky_tests) - 10} more flaky tests</p>' if len(flaky_tests) > 10 else ''}
    </div>
    """


def render_new_failures_section(summary: 'ReportSummary', report_url: str) -> str:
    """Render a section highlighting NEW failures (regressions) in this build."""
    new_failures = [t for t in summary.failed_tests if t.is_new_failure]

    if not new_failures:
        return ""

    logger.debug(f"Rendering {len(new_failures)} new failures")

    rows = ""
    for test in new_failures[:10]:
        test_link = f"{report_url}#testresult/{test.uid}" if test.uid else report_url

        # Get history context
        history_text = ""
        if test.history:
            history_text = f'<span style="color: {Colors.TEXT_MUTED}; font-size: 11px;">Was: {test.history.pass_rate:.0f}% pass rate</span>'

        # Get cause commit badges if available
        cause_badges = render_commit_badges(getattr(test, 'likely_cause_commits', []), is_fix=False)

        # Known bug badge
        bug_badge = ""
        if test.has_known_bug and test.known_bug:
            bug_badge = f'<span style="background: #fc8181; color: #742a2a; padding: 2px 6px; border-radius: 8px; font-size: 10px;">🐛 #{test.known_bug.bug_id}</span>'

        rows += f"""
        <div style="background: #fef2f2; border: 1px solid #fc8181; border-radius: 6px; margin: 8px 0; padding: 10px;">
            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px;">
                <span style="background: #e53e3e; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;">
                    🆕 NEW FAILURE
                </span>
                <a href="{test_link}" style="color: {Colors.TEXT_PRIMARY}; font-weight: 600; text-decoration: none; font-size: 13px;">
                    {test.name}
                </a>
                {bug_badge}
            </div>
            <div style="margin-top: 6px; display: flex; gap: 12px; flex-wrap: wrap;">
                {history_text}
            </div>
            <div style="margin-top: 4px; color: #742a2a; font-size: 12px;">
                {test.error_message[:150]}{'...' if len(test.error_message) > 150 else ''}
            </div>
            {cause_badges}
        </div>
        """

    remaining = len(new_failures) - 10
    more_text = f'<p style="color: {Colors.TEXT_MUTED}; font-size: 11px; margin-top: 8px;">... and {remaining} more new failures</p>' if remaining > 0 else ''

    return f"""
    <div style="margin: 25px 0; padding: 15px; background: #fef2f2; border-radius: 8px; border: 2px solid #e53e3e;">
        <h2 style="color: #c53030; margin: 0 0 10px 0; font-size: 16px;">
            🆕 New Failures - Regressions ({len(new_failures)} tests)
        </h2>
        <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin: 0 0 10px 0;">
            These tests were passing before but are now failing. Requires immediate investigation!
            🔍 = Suspected cause commit
        </p>
        {rows}
        {more_text}
    </div>
    """


def render_newly_passing_section(summary: 'ReportSummary', report_url: str) -> str:
    """Render a section highlighting tests that started passing (were failing before)."""
    if not summary.newly_passed_tests:
        return ""

    logger.debug(f"Rendering {len(summary.newly_passed_tests)} newly passing tests")

    rows = ""
    for test in summary.newly_passed_tests[:10]:
        test_link = f"{report_url}#testresult/{test.uid}" if test.uid else report_url

        # Show how many consecutive failures before passing
        streak_text = ""
        if test.consecutive_failures > 1:
            streak_text = f'<span style="color: #276749; font-size: 11px;">🔥 Was failing for {test.consecutive_failures} runs!</span>'

        # Get fix commit badges
        fix_badges = render_commit_badges(getattr(test, 'likely_fix_commits', []), is_fix=True)

        rows += f"""
        <div style="background: #f0fff4; border: 1px solid #48bb78; border-radius: 6px; margin: 8px 0; padding: 10px;">
            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 8px;">
                <span style="background: #48bb78; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;">
                    ✅ NOW PASSING
                </span>
                <a href="{test_link}" style="color: {Colors.TEXT_PRIMARY}; font-weight: 600; text-decoration: none; font-size: 13px;">
                    {test.name}
                </a>
            </div>
            <div style="margin-top: 6px; display: flex; gap: 12px; flex-wrap: wrap;">
                <span style="color: {Colors.TEXT_MUTED}; font-size: 11px;">
                    Was: <strong style="color: #c53030;">{test.previous_status}</strong>
                </span>
                <span style="color: {Colors.TEXT_MUTED}; font-size: 11px;">
                    History: {test.history_pass_rate:.0f}% pass rate
                </span>
                {streak_text}
            </div>
            {fix_badges}
        </div>
        """

    return f"""
    <div style="margin: 25px 0; padding: 15px; background: #f0fff4; border-radius: 8px; border: 1px solid #48bb78;">
        <h2 style="color: #276749; margin: 0 0 10px 0; font-size: 16px;">
            🎉 Newly Passing Tests ({len(summary.newly_passed_tests)} tests)
        </h2>
        <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin: 0 0 10px 0;">
            These tests were previously failing but are now passing!
            ✅ = Likely fix commit (from nvos or sonic-mgmt repo)
        </p>
        {rows}
        {f'<p style="color: {Colors.TEXT_MUTED}; font-size: 11px; margin-top: 8px;">... and {len(summary.newly_passed_tests) - 10} more newly passing tests</p>' if len(summary.newly_passed_tests) > 10 else ''}
    </div>
    """


def render_test_issues_section(
    analyses: List[FailureAnalysis],
    report_url: str,
    max_display: int = 15
) -> str:
    """Render the 'Test/Infrastructure Issues' section - only tests with known bugs."""
    # Exclude timeout and invalid_param issues as they have their own section
    test_issues = [a for a in analyses
                   if a.bug_likelihood < BugLikelihood.HIGH and
                   not a.is_timeout and
                   not a.is_invalid_param]

    if not test_issues:
        return ""

    # Only show tests with known bugs in detail
    issues_with_bugs = [a for a in test_issues if a.test.has_known_bug]
    issues_without_bugs = len(test_issues) - len(issues_with_bugs)

    logger.debug(f"Test issues: {len(issues_with_bugs)} with bugs, {issues_without_bugs} without")

    if not issues_with_bugs:
        # Just show a summary count if no tests have known bugs
        return f"""
        <div style="margin: 25px 0; padding: 12px; background: #f7fafc; border-radius: 6px;">
            <span style="color: {Colors.TEXT_SECONDARY}; font-size: 14px;">
                🔧 <b>{len(test_issues)}</b> other test/infrastructure issues (no known bugs linked)
            </span>
        </div>
        """

    other_rows = ""
    for analysis in issues_with_bugs[:max_display]:
        test = analysis.test
        test_link = f"{report_url}#suites/{test.uid}" if test.uid else report_url
        likelihood_color = get_likelihood_color(analysis.bug_likelihood)
        icon = analysis.issue_icon
        history_badge = render_history_badge(test)
        known_bug_badge = render_known_bug_badge(test)

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
                    {icon + ' ' if icon else ''}{test.name}
                </a>
                {known_bug_badge}
                {history_badge}
                <div style="color: {Colors.TEXT_MUTED}; font-size: 11px; margin-top: 2px;">
                    {analysis.reason}
                </div>
            </td>
        </tr>
        """

    # Show count of remaining issues without bugs
    more_text = ""
    if issues_without_bugs > 0:
        more_text = f'''
        <p style="color: {Colors.TEXT_MUTED}; font-size: 12px; margin-top: 10px;">
            + {issues_without_bugs} other issues without known bugs
        </p>
        '''

    return f"""
    <div style="margin: 25px 0;">
        <h2 style="color: {Colors.TEXT_SECONDARY}; margin: 0 0 15px 0; font-size: 16px;">
            🔧 Tests with Known Bugs ({len(issues_with_bugs)} tests)
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


def render_no_new_failures_message(summary: ReportSummary) -> str:
    """Render a positive message when there are no new failures."""
    new_failures = [t for t in summary.failed_tests if t.is_new_failure]

    # Also check if there are any failures at all
    if not summary.failed_tests:
        return """
    <div style="margin: 20px 0; padding: 20px; background: linear-gradient(135deg, #f0fff4, #dcfce7);
                border-radius: 12px; border: 2px solid #22c55e; text-align: center;">
        <span style="font-size: 32px;">🎉</span>
        <p style="color: #166534; font-size: 18px; font-weight: 700; margin: 10px 0 5px 0;">
            All Tests Passed!
        </p>
        <p style="color: #15803d; font-size: 14px; margin: 0;">
            No failures detected in this test run.
        </p>
    </div>
    """

    if new_failures:
        return ""  # There are new failures, don't show this message

    return """
    <div style="margin: 20px 0; padding: 16px; background: linear-gradient(135deg, #ecfdf5, #d1fae5);
                border-radius: 10px; border: 2px solid #10b981; text-align: center;">
        <span style="font-size: 28px;">✅</span>
        <p style="color: #065f46; font-size: 17px; font-weight: 700; margin: 10px 0 5px 0;">
            No New Regressions!
        </p>
        <p style="color: #047857; font-size: 13px; margin: 0;">
            All failures are pre-existing or flaky tests - no action needed for this build.
        </p>
    </div>
    """


def render_footer(ai_available: bool = False) -> str:
    """Render the email footer with AI status."""
    ai_badge = ""
    if ai_available:
        ai_badge = '<span style="background: #48bb78; color: white; padding: 2px 8px; border-radius: 10px; font-size: 10px; margin-right: 8px;">🤖 AI-Powered</span>'
    else:
        ai_badge = '<span style="background: #718096; color: white; padding: 2px 8px; border-radius: 10px; font-size: 10px; margin-right: 8px;">📊 Heuristic</span>'

    return f"""
    <div style="text-align: center; color: {Colors.TEXT_SECONDARY}; font-size: 12px;
                margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
        {ai_badge}
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
    version_info = render_version_info(summary)
    pie_chart = render_pie_chart(summary)
    info = render_info_box(summary)
    no_new_failures = render_no_new_failures_message(summary)
    new_failures = render_new_failures_section(summary, summary.report_url)
    newly_passing = render_newly_passing_section(summary, summary.report_url)
    special_issues = render_special_issues_section(analyses, summary.report_url)
    flaky_tests = render_flaky_tests_section(analyses, summary.report_url)
    issues = render_test_issues_section(analyses, summary.report_url)
    footer = render_footer(ai_available=getattr(summary, 'ai_available', False))

    # AI analysis provides deeper insights when available
    if llm_analysis:
        analysis_section = llm_analysis
        bugs = ""  # AI covers the bugs analysis
    else:
        analysis_section = ""
        bugs = render_likely_bugs_section(analyses, summary.report_url)

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
    {version_info}
    {pie_chart}
    {info}
    {no_new_failures}
    {new_failures}
    {newly_passing}
    {analysis_section}
    {bugs}
    {special_issues}
    {flaky_tests}
    {issues}
    {footer}
</body>
</html>
"""

    logger.debug(f"Generated HTML email ({len(html)} bytes)")
    return html
