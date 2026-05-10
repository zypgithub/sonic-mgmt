"""
NVIDIA LLM Client for AI-Powered Analysis.

This module provides integration with NVIDIA's inference services for
intelligent test failure analysis.

Supported Backends:
    1. Enterprise Inference Hub (recommended): Self-service, no onboarding required
       - Set INFERENCE_HUB_API_KEY env var
       - Documentation: https://inference.nvidia.com

    2. LLM Gateway (legacy): Requires service request for onboarding
       - Set LLM_GATEWAY_TOKEN env var (NV-Auth)
       - Or set LLM_CLIENT_ID & LLM_CLIENT_SECRET (SSA OAuth)
       - Documentation: https://confluence.nvidia.com/display/LLMSVC/NVIDIA+LLM+Gateway
"""

import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import requests

from ngts.scripts.allure_summary.config import (
    INFERENCE_HUB_URL,
    INFERENCE_HUB_DEFAULT_MODEL,
    LLM_GATEWAY_URL,
    LLM_OAUTH_TOKEN_URL,
    LLM_DEFAULT_MODEL,
    LLM_API_VERSION,
)
from ngts.scripts.allure_summary.models import ReportSummary
from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()


class LLMGatewayClient:
    """
    Client for NVIDIA LLM services.

    Supports multiple backends:
    1. Enterprise Inference Hub (recommended): Self-service, no onboarding
       - Set INFERENCE_HUB_API_KEY env var
    2. LLM Gateway NV-Auth: Long-lived JWT token
       - Set LLM_GATEWAY_TOKEN env var
    3. LLM Gateway SSA OAuth: Client ID + Secret
       - Set LLM_CLIENT_ID & LLM_CLIENT_SECRET env vars

    Usage:
        client = LLMGatewayClient()
        if client.is_available():
            response = client.chat_completion([
                {"role": "user", "content": "Analyze this error..."}
            ])
    """

    def __init__(
        self,
        token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        model: Optional[str] = None,
        inference_hub_key: Optional[str] = None
    ):
        """
        Initialize LLM client.

        Args:
            token: NV-Auth JWT token (or set LLM_GATEWAY_TOKEN env var)
            client_id: SSA OAuth client ID (or set LLM_CLIENT_ID env var)
            client_secret: SSA OAuth secret (or set LLM_CLIENT_SECRET env var)
            model: Model to use (auto-detected based on backend)
            inference_hub_key: Enterprise Inference Hub API key (or set INFERENCE_HUB_API_KEY env var)
        """
        # Enterprise Inference Hub (preferred - self-service)
        self.inference_hub_key = inference_hub_key or os.environ.get("INFERENCE_HUB_API_KEY")

        # LLM Gateway (legacy - requires onboarding)
        self.token = token or os.environ.get("LLM_GATEWAY_TOKEN")
        self.client_id = client_id or os.environ.get("LLM_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("LLM_CLIENT_SECRET")
        self._oauth_token = None

        # Determine backend and model
        if self.inference_hub_key:
            self.backend = "inference_hub"
            self.model = model or INFERENCE_HUB_DEFAULT_MODEL
            self.base_url = INFERENCE_HUB_URL
        else:
            self.backend = "llm_gateway"
            self.model = model or LLM_DEFAULT_MODEL
            self.base_url = LLM_GATEWAY_URL

        logger.debug(f"LLMGatewayClient initialized: backend={self.backend}, model={self.model}, "
                     f"has_inference_hub_key={bool(self.inference_hub_key)}, "
                     f"has_token={bool(self.token)}, has_oauth={bool(self.client_id)}")

    def _get_oauth_token(self) -> Optional[str]:
        """Get OAuth token using SSA credentials."""
        if not self.client_id or not self.client_secret:
            return None

        logger.debug("Requesting OAuth token from SSA...")

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
            logger.debug("OAuth token obtained successfully")
            return self._oauth_token
        except requests.exceptions.HTTPError as e:
            logger.error(f"OAuth token request failed: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Failed to get OAuth token: {e}")
            return None

    def get_bearer_token(self) -> Optional[str]:
        """Get the bearer token for API calls."""
        # Enterprise Inference Hub takes priority (self-service, no onboarding)
        if self.inference_hub_key:
            logger.debug("Using Enterprise Inference Hub API key")
            return self.inference_hub_key
        # NV-Auth token (long-lived)
        if self.token:
            logger.debug("Using NV-Auth token")
            return self.token
        # Try OAuth if credentials provided
        if self.client_id and self.client_secret:
            logger.debug("Using SSA OAuth credentials")
            return self._get_oauth_token()
        return None

    def is_available(self) -> bool:
        """Check if LLM credentials are configured."""
        available = bool(self.inference_hub_key or self.token or (self.client_id and self.client_secret))
        if not available:
            logger.debug("No LLM credentials configured (set INFERENCE_HUB_API_KEY or LLM_GATEWAY_TOKEN)")
        return available

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.3
    ) -> Optional[str]:
        """
        Send a chat completion request to the configured LLM backend.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            max_tokens: Maximum tokens in the response
            temperature: Response randomness (0.0-1.0)

        Returns:
            The assistant's response text, or None on error
        """
        token = self.get_bearer_token()
        if not token:
            logger.warning("No LLM token available")
            return None

        logger.debug(f"Sending chat completion request via {self.backend}: {len(messages)} messages, max_tokens={max_tokens}")

        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Add extra headers for LLM Gateway
            if self.backend == "llm_gateway":
                headers.update({
                    "correlationId": f"allure-summary-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "dataClassification": "confidential",
                    "dataSource": "internal-test-results"
                })

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                verify=True
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.debug(f"LLM response received: {len(content)} chars")
            return content

        except requests.exceptions.HTTPError as e:
            logger.error(f"LLM HTTP error: {e.response.status_code} - {e.response.text[:200]}")
            return None
        except requests.exceptions.Timeout:
            logger.error("LLM request timed out")
            return None
        except Exception as e:
            logger.error(f"LLM error: {type(e).__name__}: {e}")
            return None


def analyze_failures_with_llm(
    summary: ReportSummary,
    llm_client: LLMGatewayClient
) -> Optional[str]:
    """
    Use NVIDIA LLM Gateway to analyze test failures and generate insights.

    Args:
        summary: The report summary with failed tests
        llm_client: Configured LLM Gateway client

    Returns:
        HTML-formatted analysis string, or None if unavailable
    """
    if not llm_client.is_available():
        logger.warning("LLM Gateway not available - skipping AI analysis")
        return None

    if not summary.failed_tests:
        logger.info("No failed tests to analyze")
        return None

    logger.info(f"Analyzing {len(summary.failed_tests)} failures with LLM...")

    # Prepare failure summary for LLM - at least 10 tests, max 15
    failure_lines = []
    for i, test in enumerate(summary.failed_tests[:15]):
        bug_note = f" [Known Bug: #{test.known_bug.bug_id}]" if test.has_known_bug else ""
        history_note = f" [Pass rate: {test.history.pass_rate:.0f}%]" if test.history else ""
        failure_lines.append(
            f"{i + 1}. [{test.status.upper()}] {test.name}{bug_note}{history_note}\n   Error: {test.error_message[:250]}"
        )

    failure_text = "\n".join(failure_lines)

    # Calculate stats for context
    ssh_timeout_count = sum(
        1 for t in summary.failed_tests
        if "NetmikoTimeout" in t.error_message or "SSH" in t.error_message.upper()
    )
    assertion_count = sum(
        1 for t in summary.failed_tests
        if "AssertionError" in t.error_message
    )

    prompt = f"""You are a SENIOR TEST VERIFICATION ENGINEER analyzing NVOS (NVIDIA Network OS) regression test failures.

## Test Run Summary
- Image: {summary.image_version or 'Unknown'}
- Total: {summary.total} tests | Passed: {summary.passed} ({summary.pass_rate:.1f}%) | Failed: {summary.failed} | Broken: {summary.broken}

## Failed/Broken Tests ({len(summary.failed_tests)} total):
{failure_text}

## Quick Stats
- SSH/Timeout errors: {ssh_timeout_count}
- Assertion failures: {assertion_count}

## YOUR TASK - Provide ACTIONABLE Analysis

For EACH major failure pattern, suggest a SPECIFIC action like a senior engineer would:

**Example actions:**
- "Fix the expected value in test - should be 'VL0-VL7' not 'VL0-VL1'"
- "Clarify with design team: is MTU 9100 correct for aggregated ports?"
- "Likely timing issue - add retry or increase timeout"
- "Connection issue - re-run to verify, check device health"
- "Test parameter issue - 'image' is not a valid parameter for this CLI"
- "Cascading failure from deploy - fix deploy first, others will pass"
- "Known flaky test - check history, may need stabilization"
- "Product regression - compare with previous passing version"

## Required Output Format:

### 🎯 Executive Summary
(2 sentences max - what happened?)

### 🔍 Failure Analysis & Recommendations
For each failure or group:
- **[Test Name]**: [Specific actionable recommendation]

### ⚡ Priority Actions
1. [Most critical action first]
2. [Second priority]
3. [Third priority]

### 📊 Assessment
- Product bugs: X
- Test issues: X
- Infra/Timing: X

Be SPECIFIC and ACTIONABLE. No generic advice."""

    messages = [
        {
            "role": "system",
            "content": "You are a senior test verification engineer at NVIDIA. You analyze test failures and provide SPECIFIC, ACTIONABLE recommendations. You know the difference between product bugs, test issues, and infrastructure problems. You suggest concrete fixes, not generic advice. Be direct and technical."
        },
        {"role": "user", "content": prompt}
    ]

    logger.info("Requesting LLM analysis from NVIDIA LLM Gateway...")
    response = llm_client.chat_completion(messages, max_tokens=1500)

    if not response:
        logger.warning("No response from LLM Gateway")
        return None

    logger.info("✅ LLM analysis received successfully")

    # Convert markdown to HTML for email
    html_response = _markdown_to_html(response)

    return f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px; border-radius: 8px; margin: 20px 0;">
        <h2 style="margin: 0 0 15px 0; font-size: 18px; color: white;">
            🤖 AI-Powered Analysis
        </h2>
        <div style="background: rgba(255,255,255,0.95); padding: 15px; border-radius: 6px;
                    font-size: 14px; line-height: 1.6; color: #333;">
            {html_response}
        </div>
        <p style="margin: 12px 0 0 0; font-size: 11px; color: rgba(255,255,255,0.7);">
            Powered by NVIDIA LLM Gateway • Model: {llm_client.model}
        </p>
    </div>
    """


def analyze_with_commit_correlation(
    summary: ReportSummary,
    llm_client: LLMGatewayClient,
    commit_summary: str = ""
) -> Optional[str]:
    """
    Enhanced analysis with commit correlation for deeper insights.

    Args:
        summary: The report summary with failed tests
        llm_client: Configured LLM client
        commit_summary: Summary of recent commits (from CommitAnalyzer)

    Returns:
        HTML-formatted analysis with commit correlations
    """
    if not llm_client.is_available():
        logger.warning("LLM not available - skipping commit correlation analysis")
        return None

    if not summary.failed_tests:
        return None

    # Separate NEW failures from flaky/pre-existing
    new_failures = [t for t in summary.failed_tests if t.is_new_failure]
    flaky_failures = [t for t in summary.failed_tests if t.flaky or (t.history and t.history.is_flaky)]
    other_failures = [t for t in summary.failed_tests if not t.is_new_failure and t not in flaky_failures]

    logger.info(f"Analyzing failures: {len(new_failures)} NEW, {len(flaky_failures)} flaky, {len(other_failures)} other")

    # If no new failures, return a simple positive message
    if not new_failures:
        return f"""
    <div style="margin: 20px 0; padding: 16px; background: linear-gradient(135deg, #ecfdf5, #d1fae5);
                border-radius: 10px; border: 2px solid #10b981; text-align: center;">
        <span style="font-size: 28px;">✅</span>
        <p style="color: #065f46; font-size: 17px; font-weight: 700; margin: 10px 0 5px 0;">
            No New Regressions in This Build
        </p>
        <p style="color: #047857; font-size: 13px; margin: 0;">
            {len(summary.failed_tests)} failures detected, but all are pre-existing ({len(flaky_failures)} flaky, {len(other_failures)} other).
            No new issues introduced by this image.
        </p>
    </div>
    """

    # Prepare failures for analysis - prioritize new failures, then high-impact ones
    # Analyze up to 5 tests total (keep it concise)
    all_to_analyze = new_failures[:5]  # Up to 5 new failures
    remaining_slots = 5 - len(all_to_analyze)

    # Add other failures sorted by history (most stable = likely real bugs)
    other_sorted = sorted(
        flaky_failures + other_failures,
        key=lambda t: t.history.pass_rate if t.history else 50,
        reverse=True  # Higher pass rate = was more stable = likely real regression
    )
    all_to_analyze.extend(other_sorted[:remaining_slots])

    failure_lines = []
    for i, test in enumerate(all_to_analyze[:5]):
        is_new = test in new_failures
        tag = "NEW REGRESSION" if is_new else ("FLAKY" if test in flaky_failures else "FAILING")
        history_context = ""
        if test.history:
            history_context = f" | History: {test.history.pass_rate:.0f}% pass rate over {test.history.total} runs"
        bug_context = ""
        if test.has_known_bug:
            bug_context = f" | Known bug: #{test.known_bug.bug_id}"
        failure_lines.append(
            f"{i + 1}. [{tag}] {test.name}{history_context}{bug_context}\n   Error: {test.error_message[:250]}"
        )
    new_failure_text = "\n".join(failure_lines) if failure_lines else "No failures to analyze"

    # Summary of remaining failures
    remaining = len(summary.failed_tests) - len(all_to_analyze)
    other_failure_text = f"{remaining} additional failures not shown (flaky or lower priority)" if remaining > 0 else "All failures shown above"

    # Prepare newly passing tests (correlate with sonic-mgmt commits for fixes)
    newly_passing_lines = []
    if hasattr(summary, 'newly_passed_tests') and summary.newly_passed_tests:
        for t in summary.newly_passed_tests[:10]:
            streak = f" (was failing {t.consecutive_failures} runs)" if t.consecutive_failures > 1 else ""
            newly_passing_lines.append(f"- ✅ {t.name}{streak}")
    newly_passing_text = "\n".join(newly_passing_lines) if newly_passing_lines else "None detected"

    prompt = f"""Analyze NVOS test failures concisely. Image: {summary.image_version or 'Unknown'}

FAILURES:
{new_failure_text}

RECENT COMMITS:
{commit_summary if commit_summary else "No commit data"}

---
Generate a CONCISE report in this EXACT format:

BUILD: [Good/Mixed/Concerning] - [one sentence summary of main issues]

Then for the TOP 5 most important failures only:

CRITICAL: [test_name]
[One line: what failed and why]
-> [One line: specific action to take]

For remaining failures, just add:
WATCH: [X] more failures ([brief description])

Example output:
BUILD: Concerning - 3 new regressions in port handling after commit abc123

CRITICAL: test_split_port_timings
IndexError accessing port data - likely caused by commit 58536a01d removing counters
-> Review commit 58536a01d, restore counter access if needed

CRITICAL: test_interface_speed
Speed mismatch 100M vs 10M - flaky (40% pass rate), hardware config issue
-> Re-run test, check cable/hardware if persists

WATCH: 8 more failures (mostly flaky transceiver tests)

Keep it SHORT. No more than 2 lines per test. Focus on actionable insights."""

    messages = [
        {
            "role": "system",
            "content": "You are a senior test verification engineer writing investigation reports. Write in plain English, no emojis. Be thorough but clear. Each test analysis should tell a story: what failed, why it matters, what might have caused it, and what to do next. Use the test history and commit data to provide real insights."
        },
        {"role": "user", "content": prompt}
    ]

    response = llm_client.chat_completion(messages, max_tokens=2000, temperature=0.2)

    if not response:
        return None

    logger.info("✅ Commit correlation analysis received")

    html_response = _markdown_to_html(response)

    return f"""
    <div style="margin: 24px 0;">
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); padding: 14px 18px; border-radius: 10px 10px 0 0;">
            <span style="font-size: 18px; margin-right: 10px;">🔬</span>
            <span style="color: #fff; font-size: 17px; font-weight: 700; letter-spacing: 0.3px;">Failure Investigation Report</span>
            <span style="float: right; background: #38a169; color: white; padding: 3px 12px;
                        border-radius: 14px; font-size: 11px; font-weight: 600;">AI-Powered</span>
        </div>
        <div style="background: #f8fafc; padding: 8px 16px 16px 16px; border: 1px solid #cbd5e1;
                    border-top: none; border-radius: 0 0 10px 10px;">
            {html_response}
            <div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid #e2e8f0;
                        font-size: 10px; color: #94a3b8; text-align: right;">
                Analysis by {llm_client.model}
            </div>
        </div>
    </div>
    """


def _markdown_to_html(markdown_text: str) -> str:
    """Convert concise AI format to HTML for email display."""
    html = markdown_text

    # BUILD: line at the top - make it prominent
    html = re.sub(
        r'BUILD:\s*([^\n]+)',
        r'<div style="background: #1e293b; color: #f8fafc; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 14px;"><strong>📊 BUILD:</strong> \1</div>',
        html
    )

    # CRITICAL: test entries - red accent
    html = re.sub(
        r'CRITICAL:\s*([^\n]+)\n([^\n]+)\n->\s*([^\n]+)',
        r'<div style="border-left: 4px solid #dc2626; background: #fef2f2; padding: 10px 14px; margin: 10px 0; border-radius: 0 6px 6px 0;"><div style="color: #991b1b; font-weight: 700; font-size: 13px; font-family: monospace;">🔴 \1</div><div style="color: #7f1d1d; font-size: 12px; margin: 4px 0;">\2</div><div style="color: #166534; font-size: 12px; background: #dcfce7; padding: 4px 8px; border-radius: 4px; margin-top: 6px;">→ \3</div></div>',
        html
    )

    # WATCH: summary line - yellow accent
    html = re.sub(
        r'WATCH:\s*([^\n]+)',
        r'<div style="border-left: 4px solid #f59e0b; background: #fffbeb; padding: 10px 14px; margin: 10px 0; border-radius: 0 6px 6px 0; font-size: 12px; color: #92400e;"><strong>🟡 WATCH:</strong> \1</div>',
        html
    )

    # Bold
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

    # Headers
    html = re.sub(
        r'^\s*##\s+(.+)$',
        r'<h3 style="color: #333; margin-top: 15px; margin-bottom: 8px;">\1</h3>',
        html, flags=re.MULTILINE
    )
    html = re.sub(
        r'^\s*###\s+(.+)$',
        r'<h4 style="color: #555; margin-top: 12px; margin-bottom: 6px;">\1</h4>',
        html, flags=re.MULTILINE
    )

    # Lists
    html = re.sub(r'^\s*[-*]\s+(.+)$', r'<li style="margin: 4px 0;">\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'^\s*(\d+)\.\s+(.+)$', r'<li style="margin: 4px 0;">\2</li>', html, flags=re.MULTILINE)

    # Paragraphs
    html = html.replace('\n\n', '</p><p style="margin: 10px 0;">')
    html = f'<p style="margin: 10px 0;">{html}</p>'

    return html


def analyze_multi_system(
    multi_summary: 'MultiSystemSummary',
    llm_client: LLMGatewayClient
) -> Optional[str]:
    """
    AI analysis for multi-system summary providing broad insights.

    Args:
        multi_summary: MultiSystemSummary with aggregated data
        llm_client: Configured LLM client

    Returns:
        HTML-formatted analysis with cross-system insights
    """
    from ngts.scripts.allure_summary.models import MultiSystemSummary

    if not llm_client.is_available():
        logger.warning("LLM not available - skipping multi-system analysis")
        return None

    if not multi_summary.systems:
        return None

    # Build system overview
    system_lines = []
    for sys in multi_summary.systems:
        s = sys.summary
        new_count = len(sys.new_failures)
        new_tag = f" - {new_count} NEW REGRESSIONS" if new_count > 0 else ""
        system_lines.append(
            f"- {sys.short_name}: {s.pass_rate:.1f}% ({s.passed}/{s.total}){new_tag}"
        )
    systems_text = "\n".join(system_lines)

    # Collect all unique failures and separate by known bug status
    all_failures_map = {}
    for sys in multi_summary.systems:
        for test in sys.summary.failed_tests:
            if test.name not in all_failures_map:
                all_failures_map[test.name] = {
                    "systems": [],
                    "error": test.error_message,
                    "has_bug": test.has_known_bug,
                    "bug_id": test.known_bug.bug_id if test.has_known_bug else None,
                    "is_new": test.is_new_failure
                }
            all_failures_map[test.name]["systems"].append(sys.short_name)

    # Separate covered (with bugs) from uncovered failures
    covered_failures = []
    uncovered_failures = []
    for name, data in all_failures_map.items():
        if data["has_bug"]:
            covered_failures.append(f"- {name} (Bug #{data['bug_id']}) - {len(data['systems'])} systems")
        elif len(data["systems"]) > 1:  # Cross-system, no bug = priority
            uncovered_failures.append(f"- ⚠️ {name} (NO BUG LINKED) - fails on {len(data['systems'])} systems: {', '.join(data['systems'])}")

    covered_text = "\n".join(covered_failures[:10]) if covered_failures else "None"
    uncovered_text = "\n".join(uncovered_failures[:10]) if uncovered_failures else "None - all cross-system failures have bugs linked"

    # New failures breakdown
    new_with_bugs = []
    new_without_bugs = []
    for sys in multi_summary.systems:
        for test in sys.new_failures:
            if test.has_known_bug:
                if test.name not in [n.split(" (Bug")[0].replace("- ", "") for n in new_with_bugs]:
                    new_with_bugs.append(f"- {test.name} (Bug #{test.known_bug.bug_id}) ✅ TRACKED")
            else:
                if test.name not in [n.split(" - ")[0].replace("- ⚠️ ", "") for n in new_without_bugs]:
                    new_without_bugs.append(f"- ⚠️ {test.name} - NEEDS INVESTIGATION")

    new_failures_text = ""
    if new_with_bugs or new_without_bugs:
        new_failures_text = "TRACKED (have bugs):\n" + ("\n".join(new_with_bugs[:5]) if new_with_bugs else "None")
        new_failures_text += "\n\nNEEDS ATTENTION (no bug linked):\n" + ("\n".join(new_without_bugs[:5]) if new_without_bugs else "None")
    else:
        new_failures_text = "No new regressions across any system."

    prompt = f"""You are a senior QA engineer analyzing nightly test results from multiple test systems running the same software image.

## Multi-System Test Summary
- Image Version: {multi_summary.image_version}
- Total Systems: {multi_summary.system_count}
- Overall Pass Rate: {multi_summary.overall_pass_rate:.1f}% ({multi_summary.total_passed}/{multi_summary.total_tests})
- Total New Failures: {multi_summary.new_failure_count}

## Per-System Results:
{systems_text}

## New Regressions:
{new_failures_text}

## Cross-System Failures Analysis:
COVERED (have linked bugs - being tracked):
{covered_text}

UNCOVERED (NO bug linked - need attention):
{uncovered_text}

CRITICAL RULES:
1. DO NOT mention tests that have linked bugs - they are ALREADY TRACKED and being worked on
2. ONLY focus on UNCOVERED failures (tests with NO bug linked)
3. If a test has a bug number like "(Bug #1234)" - DO NOT recommend action on it

Please provide a BRIEF executive summary (150-200 words max) covering:
1. Overall health assessment (one sentence)
2. Systems needing attention (lowest pass rates)
3. ONLY list uncovered failures that need NEW bug tickets
4. Skip any test that already has a bug linked

Use markdown formatting. Be direct. Only actionable items for UNCOVERED issues."""

    try:
        response = llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )

        if not response:
            return None

        # Convert to HTML
        html_content = _markdown_to_html(response)

        # Build clickable links for uncovered failures
        uncovered_links_html = ""
        if uncovered_failures:
            links = []
            for failure_line in uncovered_failures[:8]:
                # Extract test name from "- ⚠️ test_name - NEEDS..."
                test_name = failure_line.replace("- ⚠️ ", "").split(" (NO BUG")[0].split(" - fails on")[0].strip()
                # Find which systems have this test and get a report URL
                for sys in multi_summary.systems:
                    for test in sys.summary.failed_tests:
                        if test.name == test_name and test.uid:
                            url = f"{sys.summary.report_url}#testresult/{test.uid}"
                            links.append(f'<li><a href="{url}" style="color: #dc2626; text-decoration: none; font-weight: 500;">{test_name}</a> <span style="color: #6b7280; font-size: 12px;">({len(all_failures_map.get(test_name, {}).get("systems", []))} systems)</span></li>')
                            break
                    else:
                        continue
                    break
            if links:
                uncovered_links_html = f'''
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #bfdbfe;">
                    <strong style="color: #dc2626;">⚠️ Uncovered Failures (need bug tickets):</strong>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        {"".join(links)}
                    </ul>
                </div>
                '''

        return f"""
    <div style="margin: 25px 0; padding: 20px; background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
                border-radius: 12px; border: 2px solid #0ea5e9;">
        <h3 style="margin: 0 0 15px 0; color: #0369a1; font-size: 16px;">
            🤖 AI Multi-System Analysis
        </h3>
        <div style="color: #1e40af; font-size: 14px; line-height: 1.6;">
            {html_content}
        </div>
        {uncovered_links_html}
    </div>
    """

    except Exception as e:
        logger.error(f"Multi-system LLM analysis failed: {e}")
        return None
