#!/usr/bin/env python3
"""
Allure Nightly Regression Summary Script

Fetches Allure report summary and sends an HTML email with:
1. Per-setup summary table (passed/failed/broken/skipped/total + pass rate)
2. List of failed/broken test names with error messages
3. Links to the Allure reports

Usage:
    python allure_nightly_summary.py --project nvos-crocodile-10-245-21-19-session-reports --email user@nvidia.com
    python allure_nightly_summary.py --project nvos-crocodile-10-245-21-19-session-reports --report-id 201 --dry-run
"""

import argparse
import json
import logging
import os
import re
import smtplib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple

import requests
from requests.packages import urllib3

urllib3.disable_warnings()

# Configuration
ALLURE_BASE_URL = "https://allure.nvidia.com/allure-docker-service"
HTTP_TIMEOUT = 60
SSL_VERIFY = False
MAIL_SERVER = "mail.nvidia.com"
SENDER_EMAIL = "noreply-allure-summary@nvidia.com"

# NVIDIA LLM Gateway Configuration
# See: https://confluence.nvidia.com/display/LLMSVC/NVIDIA+LLM+Gateway
LLM_GATEWAY_URL = "https://prod.api.nvidia.com/llm/v1/azure"
LLM_OAUTH_TOKEN_URL = "https://prod.api.nvidia.com/oauth/api/v1/ssa/default/token"
LLM_DEFAULT_MODEL = "gpt-4o"
LLM_API_VERSION = "2024-02-15-preview"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


@dataclass
class FailedTest:
    """Represents a failed or broken test."""
    name: str
    status: str
    duration_ms: int
    error_message: str = ""
    suite: str = ""
    uid: str = ""  # Used for direct linking to test in Allure report


@dataclass
class ReportSummary:
    """Summary of an Allure report."""
    project_name: str
    report_id: int
    report_url: str
    passed: int = 0
    failed: int = 0
    broken: int = 0
    skipped: int = 0
    unknown: int = 0
    total: int = 0
    pass_rate: float = 0.0
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    duration_minutes: float = 0.0
    failed_tests: List[FailedTest] = field(default_factory=list)
    error: Optional[str] = None


class AllureClient:
    """Client for fetching data from Allure server."""

    def __init__(self, base_url: str = ALLURE_BASE_URL):
        self.base_url = base_url

    def _get(self, path: str) -> Optional[dict]:
        """Make a GET request to the Allure API."""
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT, verify=SSL_VERIFY)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Request failed for {path}: {e}")
            return None

    def get_latest_report_id(self, project_name: str) -> Optional[int]:
        """Get the latest report ID for a project."""
        data = self._get(f"/projects/{project_name}")
        if not data:
            return None

        reports = data.get("data", {}).get("project", {}).get("reports_id", [])
        numeric_ids = [int(r) for r in reports if str(r).isdigit()]
        return max(numeric_ids) if numeric_ids else None

    def get_report_summary(self, project_name: str, report_id: int) -> Optional[dict]:
        """Get summary.json for a report."""
        return self._get(f"/projects/{project_name}/reports/{report_id}/widgets/summary.json")

    def get_report_categories(self, project_name: str, report_id: int) -> Optional[dict]:
        """Get categories.json (failed/broken tests grouped by error)."""
        return self._get(f"/projects/{project_name}/reports/{report_id}/data/categories.json")

    def get_report_url(self, project_name: str, report_id: int) -> str:
        """Generate the full report URL."""
        return f"{self.base_url}/projects/{project_name}/reports/{report_id}/index.html"


class LLMGatewayClient:
    """
    Client for NVIDIA LLM Gateway.

    Supports two authentication methods:
    1. NV-Auth: Long-lived JWT token (set via LLM_GATEWAY_TOKEN env var)
    2. SSA OAuth: Client ID + Secret (set via LLM_CLIENT_ID & LLM_CLIENT_SECRET env vars)

    Documentation: https://confluence.nvidia.com/display/LLMSVC/NVIDIA+LLM+Gateway
    """

    def __init__(self, token: Optional[str] = None, client_id: Optional[str] = None,
                 client_secret: Optional[str] = None, model: str = LLM_DEFAULT_MODEL):
        self.model = model
        self.token = token or os.environ.get("LLM_GATEWAY_TOKEN")
        self.client_id = client_id or os.environ.get("LLM_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("LLM_CLIENT_SECRET")
        self._oauth_token = None

    def _get_oauth_token(self) -> Optional[str]:
        """Get OAuth token using SSA credentials."""
        if not self.client_id or not self.client_secret:
            return None

        try:
            response = requests.post(
                LLM_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "scope": "azureopenai-readwrite"
                },
                auth=(self.client_id, self.client_secret),
                timeout=30
            )
            response.raise_for_status()
            self._oauth_token = response.json().get("access_token")
            return self._oauth_token
        except Exception as e:
            logger.error(f"Failed to get OAuth token: {e}")
            return None

    def get_bearer_token(self) -> Optional[str]:
        """Get the bearer token for API calls."""
        # NV-Auth token takes priority (it's long-lived)
        if self.token:
            return self.token
        # Try OAuth if credentials provided
        if self.client_id and self.client_secret:
            return self._get_oauth_token()
        return None

    def is_available(self) -> bool:
        """Check if LLM Gateway credentials are configured."""
        return bool(self.token or (self.client_id and self.client_secret))

    def chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 1500) -> Optional[str]:
        """
        Send a chat completion request to LLM Gateway.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            max_tokens: Maximum tokens in the response

        Returns:
            The assistant's response text, or None on error
        """
        token = self.get_bearer_token()
        if not token:
            logger.warning("No LLM Gateway token available")
            return None

        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "correlationId": f"allure-summary-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "dataClassification": "confidential",
                "dataSource": "internal-test-results"
            }

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max_tokens,
            }

            response = requests.post(
                f"{LLM_GATEWAY_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                verify=True
            )
            response.raise_for_status()

            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")

        except requests.exceptions.HTTPError as e:
            logger.error(f"LLM Gateway HTTP error: {e.response.status_code} - {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"LLM Gateway error: {e}")
            return None


def extract_failed_tests(categories_data: dict) -> List[FailedTest]:
    """Extract failed/broken tests from categories data."""
    failed_tests = []

    if not categories_data or "children" not in categories_data:
        return failed_tests

    def traverse(node, error_category=""):
        """Recursively traverse the categories tree."""
        if isinstance(node, dict):
            # Check if this is a test node (has status and name but no children with tests)
            if "status" in node and node.get("status") in ("failed", "broken"):
                failed_tests.append(FailedTest(
                    name=node.get("name", "Unknown"),
                    status=node.get("status", "unknown"),
                    duration_ms=node.get("time", {}).get("duration", 0),
                    error_message=error_category[:500] if error_category else "",  # Truncate long messages
                    suite=node.get("parentUid", ""),
                    uid=node.get("uid", "")  # Capture UID for direct linking
                ))

            # If this is an error category node (has name and children)
            if "children" in node:
                category_name = node.get("name", "")
                for child in node["children"]:
                    traverse(child, category_name if category_name else error_category)

    for category in categories_data.get("children", []):
        traverse(category)

    return failed_tests


def fetch_report_summary(client: AllureClient, project_name: str, report_id: Optional[int] = None) -> ReportSummary:
    """Fetch complete report summary."""

    # Get report ID if not provided
    if report_id is None:
        report_id = client.get_latest_report_id(project_name)
        if not report_id:
            return ReportSummary(
                project_name=project_name,
                report_id=0,
                report_url="",
                error="No reports found"
            )

    report_url = client.get_report_url(project_name, report_id)
    summary = ReportSummary(
        project_name=project_name,
        report_id=report_id,
        report_url=report_url
    )

    # Get summary statistics
    summary_data = client.get_report_summary(project_name, report_id)
    if summary_data:
        stats = summary_data.get("statistic", {})
        summary.passed = stats.get("passed", 0)
        summary.failed = stats.get("failed", 0)
        summary.broken = stats.get("broken", 0)
        summary.skipped = stats.get("skipped", 0)
        summary.unknown = stats.get("unknown", 0)
        summary.total = stats.get("total", 0)

        if summary.total > 0:
            summary.pass_rate = (summary.passed / summary.total) * 100

        # Parse time info
        time_info = summary_data.get("time", {})
        if "start" in time_info:
            summary.start_time = datetime.fromtimestamp(time_info["start"] / 1000)
        if "stop" in time_info:
            summary.stop_time = datetime.fromtimestamp(time_info["stop"] / 1000)
        if "duration" in time_info:
            summary.duration_minutes = time_info["duration"] / 1000 / 60
    else:
        summary.error = "Failed to fetch summary data"
        return summary

    # Get failed/broken tests
    categories_data = client.get_report_categories(project_name, report_id)
    if categories_data:
        summary.failed_tests = extract_failed_tests(categories_data)

    return summary


@dataclass
class FailureAnalysis:
    """Analysis of a single test failure."""
    test: FailedTest
    bug_likelihood: int  # 0-100%
    classification: str  # "bug", "test_issue", "infra", "unknown"
    reason: str  # Why we think this


def analyze_single_failure(test: FailedTest) -> FailureAnalysis:
    """
    Analyze a single test failure to determine if it's a bug or test issue.
    Returns bug likelihood (0-100) and reasoning.
    """
    error = test.error_message.lower()
    name = test.name.lower()

    # High confidence BUG indicators (75-95%)
    bug_patterns = [
        (r"assert.*==.*false|assert.*!=.*true", 95, "Assertion comparing actual vs expected value failed"),
        (r"expected.*but got|got.*instead of", 95, "Output mismatch - product returned unexpected value"),
        (r"should be.*but (is|was)", 90, "Behavioral mismatch detected"),
        (r"value.*mismatch|mismatch.*value", 90, "Value mismatch indicates incorrect behavior"),
        (r"failed.*validation|validation.*failed", 85, "Validation check failed on product output"),
        (r"incorrect|wrong|invalid.*response", 85, "Product returned incorrect response"),
        (r"missing.*field|field.*missing|key.*not found", 80, "Expected field missing from output"),
        (r"status.*error|error.*status|unexpected.*status", 80, "Unexpected status returned"),
        (r"resultobj.*failed", 75, "Test framework detected unexpected result"),
    ]

    # Test/Infrastructure issue indicators (low bug likelihood 10-40%)
    test_issue_patterns = [
        (r"netmikotimeout|ssh.*timeout|connection.*refused", 15, "SSH/Connection timeout - likely device or network issue"),
        (r"setup.*failed|fixture.*error|prerequisite", 20, "Test setup failed before test could run"),
        (r"cleanup.*failed|teardown.*error", 10, "Cleanup/teardown issue - not a product bug"),
        (r"file not found|no such file|filenotfounderror", 25, "Missing file - test environment issue"),
        (r"permission denied|access denied", 20, "Permission issue - infrastructure problem"),
        (r"out of memory|memory error|oom", 30, "Memory issue - may be product or environment"),
        (r"timeout.*waiting|wait.*timeout|timed out waiting", 40, "Timeout waiting for condition - could be either"),
        (r"device.*unreachable|cannot connect|connection.*lost", 10, "Device connectivity lost"),
    ]

    # Check for bug patterns first
    for pattern, likelihood, reason in bug_patterns:
        if re.search(pattern, error, re.IGNORECASE):
            return FailureAnalysis(
                test=test,
                bug_likelihood=likelihood,
                classification="bug" if likelihood >= 75 else "uncertain",
                reason=reason
            )

    # Check for test issue patterns
    for pattern, likelihood, reason in test_issue_patterns:
        if re.search(pattern, error, re.IGNORECASE):
            return FailureAnalysis(
                test=test,
                bug_likelihood=likelihood,
                classification="test_issue" if likelihood <= 30 else "uncertain",
                reason=reason
            )

    # Default analysis based on status
    if test.status == "failed":
        # "failed" status in Allure typically means assertion failure
        return FailureAnalysis(
            test=test,
            bug_likelihood=70,
            classification="uncertain",
            reason="Test assertion failed - likely a product issue but needs investigation"
        )
    else:
        # "broken" status typically means test infrastructure issue
        return FailureAnalysis(
            test=test,
            bug_likelihood=35,
            classification="uncertain",
            reason="Test broken during execution - may be test or environment issue"
        )


def analyze_all_failures(failed_tests: List[FailedTest]) -> List[FailureAnalysis]:
    """Analyze all failures and return sorted by bug likelihood."""
    analyses = [analyze_single_failure(test) for test in failed_tests]
    # Sort by bug likelihood descending
    analyses.sort(key=lambda a: a.bug_likelihood, reverse=True)
    return analyses


def analyze_failures_with_llm(summary: ReportSummary, llm_client: LLMGatewayClient) -> Optional[str]:
    """
    Use NVIDIA LLM Gateway to analyze test failures and generate insights.

    Returns an HTML-formatted analysis or None if LLM is unavailable.
    """
    if not llm_client.is_available():
        logger.warning("LLM Gateway not available - skipping AI analysis")
        return None

    if not summary.failed_tests:
        return None

    # Prepare failure summary for LLM
    failure_summary_lines = []
    for i, test in enumerate(summary.failed_tests[:30]):  # Limit to 30 tests to avoid token limits
        failure_summary_lines.append(
            f"{i + 1}. [{test.status.upper()}] {test.name}\n   Error: {test.error_message[:200]}"
        )

    failure_text = "\n".join(failure_summary_lines)

    # Calculate some stats for context
    ssh_timeout_count = sum(1 for t in summary.failed_tests if "NetmikoTimeout" in t.error_message or "SSH" in t.error_message)
    assertion_count = sum(1 for t in summary.failed_tests if "AssertionError" in t.error_message)

    prompt = f"""You are analyzing test results from a network switch regression test suite (NVOS/SONiC).

## Test Run Summary
- Total Tests: {summary.total}
- Passed: {summary.passed} ({summary.pass_rate:.1f}%)
- Failed: {summary.failed}
- Broken: {summary.broken}
- Duration: {summary.duration_minutes:.0f} minutes

## Failed/Broken Tests ({len(summary.failed_tests)} total):
{failure_text}

## Preliminary Analysis
- SSH/Timeout errors: {ssh_timeout_count}
- Assertion failures: {assertion_count}

## Your Task
Analyze these test failures and provide:

1. **Executive Summary** (2-3 sentences): What happened in this test run?

2. **Root Cause Analysis** (bullet points):
   - Identify the likely root causes
   - Group related failures together
   - Highlight any cascading failures (e.g., device crash causing multiple tests to fail)

3. **Priority Actions** (numbered list):
   - What should be investigated first?
   - Any critical issues that need immediate attention?

4. **Test Health Assessment**:
   - Are these product bugs, test issues, or infrastructure problems?

Be concise and actionable. Format your response in clear sections with markdown headers."""

    logger.info("Requesting LLM analysis from NVIDIA LLM Gateway...")

    messages = [
        {"role": "system", "content": "You are a senior QA engineer analyzing automated test results. Be concise, technical, and actionable."},
        {"role": "user", "content": prompt}
    ]

    response = llm_client.chat_completion(messages, max_tokens=1500)

    if not response:
        logger.warning("No response from LLM Gateway")
        return None

    logger.info("LLM analysis received successfully")

    # Convert markdown to HTML for email
    html_response = response
    # Basic markdown to HTML conversion
    html_response = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_response)
    html_response = re.sub(r'^\s*##\s+(.+)$', r'<h3 style="color: #333; margin-top: 15px;">\1</h3>', html_response, flags=re.MULTILINE)
    html_response = re.sub(r'^\s*###\s+(.+)$', r'<h4 style="color: #555; margin-top: 12px;">\1</h4>', html_response, flags=re.MULTILINE)
    html_response = re.sub(r'^\s*[-*]\s+(.+)$', r'<li>\1</li>', html_response, flags=re.MULTILINE)
    html_response = re.sub(r'^\s*(\d+)\.\s+(.+)$', r'<li>\2</li>', html_response, flags=re.MULTILINE)
    html_response = html_response.replace('\n\n', '</p><p>')
    html_response = f'<p>{html_response}</p>'

    return f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <h2 style="margin: 0 0 15px 0; font-size: 18px;">🤖 AI-Powered Analysis (via NVIDIA LLM Gateway)</h2>
        <div style="background: rgba(255,255,255,0.1); padding: 15px; border-radius: 6px; font-size: 14px; line-height: 1.6;">
            {html_response}
        </div>
        <p style="margin: 12px 0 0 0; font-size: 11px; opacity: 0.7;">
            Powered by NVIDIA LLM Gateway • Model: {llm_client.model}
        </p>
    </div>
    """


def generate_html_email(summary: ReportSummary, llm_analysis: Optional[str] = None) -> str:
    """Generate HTML email content."""

    def get_color(pass_rate: float) -> str:
        if pass_rate >= 95:
            return "#28a745"  # Green
        elif pass_rate >= 80:
            return "#ffc107"  # Yellow/warning
        elif pass_rate >= 60:
            return "#fd7e14"  # Orange
        return "#dc3545"  # Red

    def format_duration(minutes: float) -> str:
        if minutes < 60:
            return f"{minutes:.0f} min"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}m"

    def get_likelihood_color(likelihood: int) -> str:
        if likelihood >= 85:
            return "#c0392b"  # Dark red - very likely bug
        elif likelihood >= 75:
            return "#e74c3c"  # Red - likely bug
        elif likelihood >= 50:
            return "#f39c12"  # Orange - uncertain
        elif likelihood >= 30:
            return "#3498db"  # Blue - likely test issue
        return "#95a5a6"  # Gray - probably infra

    color = get_color(summary.pass_rate)
    duration = format_duration(summary.duration_minutes)

    # Analyze all failures
    analyses = analyze_all_failures(summary.failed_tests)

    # Separate likely bugs (>=75%) from other issues
    likely_bugs = [a for a in analyses if a.bug_likelihood >= 75]
    other_issues = [a for a in analyses if a.bug_likelihood < 75]

    # Build "Likely Bugs" section
    bugs_html = ""
    if likely_bugs:
        bug_rows = ""
        for analysis in likely_bugs:
            test = analysis.test
            test_link = f"{summary.report_url}#suites/{test.uid}" if test.uid else summary.report_url
            likelihood_color = get_likelihood_color(analysis.bug_likelihood)

            bug_rows += f"""
            <div style="background: #fff; border: 1px solid #e0e0e0; border-left: 4px solid {likelihood_color}; border-radius: 6px; margin: 10px 0; padding: 12px;">
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <span style="background: {likelihood_color}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;">
                        {analysis.bug_likelihood}% BUG
                    </span>
                    <a href="{test_link}" style="color: #333; font-weight: bold; margin-left: 10px; text-decoration: none; font-size: 14px;">
                        {test.name}
                    </a>
                </div>
                <div style="color: #555; font-size: 13px; margin-left: 4px;">
                    <strong>Why:</strong> {analysis.reason}
                </div>
                <div style="color: #888; font-size: 12px; margin-top: 6px; font-family: monospace; background: #f8f9fa; padding: 6px; border-radius: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    {test.error_message[:150]}{'...' if len(test.error_message) > 150 else ''}
                </div>
            </div>
            """

        bugs_html = f"""
        <div style="margin: 25px 0;">
            <h2 style="color: #c0392b; margin: 0 0 15px 0; font-size: 18px;">
                🐛 Likely Product Bugs ({len(likely_bugs)} tests)
            </h2>
            <p style="color: #666; font-size: 13px; margin: 0 0 15px 0;">
                These failures show high confidence of being actual product bugs based on error analysis.
                Each test is linked - click to view details in Allure.
            </p>
            {bug_rows}
        </div>
        """

    # Build "Other Issues" section (test/infra problems)
    other_html = ""
    if other_issues:
        other_rows = ""
        for analysis in other_issues[:15]:  # Limit display
            test = analysis.test
            test_link = f"{summary.report_url}#suites/{test.uid}" if test.uid else summary.report_url
            likelihood_color = get_likelihood_color(analysis.bug_likelihood)

            other_rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 8px; width: 70px;">
                    <span style="background: {likelihood_color}; color: white; padding: 2px 6px; border-radius: 8px; font-size: 10px;">
                        {analysis.bug_likelihood}%
                    </span>
                </td>
                <td style="padding: 8px;">
                    <a href="{test_link}" style="color: #007bff; text-decoration: none; font-size: 13px;">{test.name}</a>
                    <div style="color: #888; font-size: 11px; margin-top: 2px;">{analysis.reason}</div>
                </td>
            </tr>
            """

        more_text = ""
        if len(other_issues) > 15:
            more_text = f'<p style="color: #888; font-size: 12px; margin-top: 10px;">... and {len(other_issues) - 15} more tests</p>'

        other_html = f"""
        <div style="margin: 25px 0;">
            <h2 style="color: #666; margin: 0 0 15px 0; font-size: 16px;">
                🔧 Test/Infrastructure Issues ({len(other_issues)} tests)
            </h2>
            <p style="color: #888; font-size: 12px; margin: 0 0 10px 0;">
                Lower bug likelihood - may be test setup, environment, or timing issues.
            </p>
            <table style="width: 100%; border-collapse: collapse;">
                {other_rows}
            </table>
            {more_text}
        </div>
        """

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px;">

    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 25px; border-radius: 8px; text-align: center;">
        <h1 style="margin: 0; font-size: 24px;">🔬 Nightly Regression Summary</h1>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">{summary.project_name}</p>
        <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.7;">
            Report #{summary.report_id} | {datetime.now().strftime('%Y-%m-%d %H:%M')}
        </p>
    </div>

    <div style="display: flex; justify-content: space-between; margin: 20px 0; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #28a745;">
            <div style="font-size: 28px; font-weight: bold; color: #28a745;">{summary.passed}</div>
            <div style="font-size: 12px; color: #666; text-transform: uppercase;">Passed</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #dc3545;">
            <div style="font-size: 28px; font-weight: bold; color: #dc3545;">{summary.failed}</div>
            <div style="font-size: 12px; color: #666; text-transform: uppercase;">Failed</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #fd7e14;">
            <div style="font-size: 28px; font-weight: bold; color: #fd7e14;">{summary.broken}</div>
            <div style="font-size: 12px; color: #666; text-transform: uppercase;">Broken</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #6c757d;">
            <div style="font-size: 28px; font-weight: bold; color: #6c757d;">{summary.skipped}</div>
            <div style="font-size: 12px; color: #666; text-transform: uppercase;">Skipped</div>
        </div>
        <div style="flex: 1; min-width: 120px; text-align: center; padding: 15px; margin: 5px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid {color};">
            <div style="font-size: 28px; font-weight: bold; color: {color};">{summary.pass_rate:.1f}%</div>
            <div style="font-size: 12px; color: #666; text-transform: uppercase;">Pass Rate</div>
        </div>
    </div>

    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <p style="margin: 0;"><strong>Total Tests:</strong> {summary.total}</p>
        <p style="margin: 5px 0 0 0;"><strong>Duration:</strong> {duration}</p>
        <p style="margin: 5px 0 0 0;"><strong>Report Link:</strong> <a href="{summary.report_url}" style="color: #007bff;">{summary.report_url}</a></p>
    </div>

    {llm_analysis if llm_analysis else ""}

    {bugs_html}

    {other_html}

    <div style="text-align: center; color: #666; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
        Generated by Allure Nightly Summary Script | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
</body>
</html>
"""
    return html


def send_email(recipients: List[str], subject: str, html_body: str, dry_run: bool = False) -> bool:
    """Send HTML email."""
    if dry_run:
        logger.info(f"[DRY RUN] Would send email to: {recipients}")
        logger.info(f"[DRY RUN] Subject: {subject}")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = ", ".join(recipients)

        msg.attach(MIMEText("Please view this email in an HTML-capable client.", "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(MAIL_SERVER) as server:
            server.sendmail(SENDER_EMAIL, recipients, msg.as_string())

        logger.info(f"Email sent successfully to: {recipients}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def parse_allure_url(url: str) -> Tuple[str, Optional[int]]:
    """
    Parse an Allure report URL to extract project name and report ID.

    Examples:
        https://allure.nvidia.com/allure-docker-service/projects/nvos-crocodile-10-245-21-19-session-reports/reports/201/index.html
        -> ('nvos-crocodile-10-245-21-19-session-reports', 201)

        https://allure.nvidia.com/allure-docker-service/projects/my-project-session-reports/reports/latest/index.html
        -> ('my-project-session-reports', None)
    """
    # Pattern to match Allure URLs
    pattern = r'/projects/([^/]+)/reports/(\d+|latest)'
    match = re.search(pattern, url)

    if not match:
        raise ValueError(f"Could not parse Allure URL: {url}")

    project_name = match.group(1)
    report_id_str = match.group(2)
    report_id = int(report_id_str) if report_id_str.isdigit() else None

    return project_name, report_id


def parse_args():
    parser = argparse.ArgumentParser(
        description="Allure Nightly Regression Summary",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using full URL (easiest - just copy from browser):
  python allure_nightly_summary.py --url "https://allure.nvidia.com/.../projects/my-project/reports/201/index.html" --output report.html

  # Using project name (gets latest report):
  python allure_nightly_summary.py --project my-project-session-reports --output report.html

  # With specific report ID:
  python allure_nightly_summary.py --project my-project-session-reports --report-id 201 --email user@nvidia.com

  # With LLM analysis (requires LLM_GATEWAY_TOKEN env var):
  export LLM_GATEWAY_TOKEN="your-nvauth-token"
  python allure_nightly_summary.py --url "..." --use-llm --output report.html

LLM Gateway Authentication:
  Option 1 - NV-Auth (recommended, long-lived token):
    Set LLM_GATEWAY_TOKEN environment variable
    Get token from: https://nv-auth.nvidia.com/

  Option 2 - SSA OAuth (short-lived):
    Set LLM_CLIENT_ID and LLM_CLIENT_SECRET environment variables

  Documentation: https://confluence.nvidia.com/display/LLMSVC/NVIDIA+LLM+Gateway
        """
    )

    # Input options (mutually exclusive-ish, URL takes precedence)
    parser.add_argument("--url", help="Full Allure report URL (easiest - just copy from browser)")
    parser.add_argument("--project", help="Allure project name (e.g., nvos-crocodile-10-245-21-19-session-reports)")
    parser.add_argument("--setup-name", help="MARS setup name (e.g., NVOS_juliet_10_7_145_52) - auto-converts to Allure project")
    parser.add_argument("--report-id", type=int, help="Specific report ID (default: latest)")

    # LLM options
    parser.add_argument("--use-llm", action="store_true",
                        help="Enable AI-powered analysis via NVIDIA LLM Gateway (requires LLM_GATEWAY_TOKEN or LLM_CLIENT_ID/LLM_CLIENT_SECRET env vars)")
    parser.add_argument("--llm-model", default=LLM_DEFAULT_MODEL,
                        help=f"LLM model to use (default: {LLM_DEFAULT_MODEL})")

    # Output options
    parser.add_argument("--email", help="Comma-separated list of email recipients")
    parser.add_argument("--dry-run", action="store_true", help="Don't send email, just print results")
    parser.add_argument("--output", help="Save HTML to file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Validate that we have either URL, project, or setup-name
    if not args.url and not args.project and not args.setup_name:
        parser.error("Either --url, --project, or --setup-name is required")

    return args


def setup_name_to_project(setup_name: str) -> str:
    """
    Convert MARS setup name to Allure project name.

    Example: NVOS_juliet_10_7_145_52 -> nvos-juliet-10-7-145-52
    """
    return setup_name.lower().replace("_", "-")


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse URL if provided, otherwise use project/setup-name/report-id
    if args.url:
        try:
            project_name, report_id = parse_allure_url(args.url)
            logger.info(f"Parsed URL: project={project_name}, report_id={report_id or 'latest'}")
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)
    elif args.setup_name:
        project_name = setup_name_to_project(args.setup_name)
        report_id = args.report_id
        logger.info(f"Converted setup name '{args.setup_name}' to project '{project_name}'")
    else:
        project_name = args.project
        report_id = args.report_id

    logger.info(f"Fetching report for project: {project_name}")

    # Fetch report data
    client = AllureClient()
    summary = fetch_report_summary(client, project_name, report_id)

    if summary.error:
        logger.error(f"Error: {summary.error}")
        sys.exit(1)

    # Print summary
    logger.info(f"Report #{summary.report_id}: {summary.passed}/{summary.total} passed ({summary.pass_rate:.1f}%)")
    logger.info(f"Failed: {summary.failed}, Broken: {summary.broken}, Skipped: {summary.skipped}")
    logger.info(f"Duration: {summary.duration_minutes:.1f} minutes")
    logger.info(f"Failed/Broken tests: {len(summary.failed_tests)}")

    for test in summary.failed_tests[:5]:  # Show first 5
        logger.info(f"  [{test.status.upper()}] {test.name}")
    if len(summary.failed_tests) > 5:
        logger.info(f"  ... and {len(summary.failed_tests) - 5} more")

    # LLM Analysis (optional)
    llm_analysis = None
    if args.use_llm:
        llm_client = LLMGatewayClient(model=args.llm_model)
        if llm_client.is_available():
            llm_analysis = analyze_failures_with_llm(summary, llm_client)
            if llm_analysis:
                logger.info("LLM analysis completed successfully")
            else:
                logger.warning("LLM analysis failed, falling back to pattern-based analysis")
        else:
            logger.warning("LLM Gateway credentials not found. Set LLM_GATEWAY_TOKEN or LLM_CLIENT_ID/LLM_CLIENT_SECRET env vars")
            logger.info("Falling back to pattern-based analysis")

    # Generate HTML
    html = generate_html_email(summary, llm_analysis)

    # Save to file if requested
    if args.output:
        with open(args.output, "w") as f:
            f.write(html)
        logger.info(f"HTML saved to: {args.output}")

    # Send email
    if args.email:
        recipients = [r.strip() for r in args.email.split(",")]
        subject = f"Nightly Regression Summary - {project_name} - {summary.pass_rate:.1f}% Pass Rate"
        send_email(recipients, subject, html, dry_run=args.dry_run)
    elif not args.output:
        logger.info("No --email or --output specified. Use --output to save HTML or --email to send.")


if __name__ == "__main__":
    main()
