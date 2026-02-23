"""
NVIDIA LLM Gateway Client for AI-Powered Analysis.

This module provides integration with NVIDIA's LLM Gateway for
intelligent test failure analysis.

Authentication Methods:
    1. NV-Auth: Long-lived JWT token (set via LLM_GATEWAY_TOKEN env var)
    2. SSA OAuth: Client ID + Secret (set via LLM_CLIENT_ID & LLM_CLIENT_SECRET)

Documentation: https://confluence.nvidia.com/display/LLMSVC/NVIDIA+LLM+Gateway
"""

import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import requests

from ngts.scripts.allure_summary.config import (
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
    Client for NVIDIA LLM Gateway.

    Supports two authentication methods:
    1. NV-Auth: Long-lived JWT token (set via LLM_GATEWAY_TOKEN env var)
    2. SSA OAuth: Client ID + Secret (set via LLM_CLIENT_ID & LLM_CLIENT_SECRET env vars)

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
        model: str = LLM_DEFAULT_MODEL
    ):
        """
        Initialize LLM Gateway client.

        Args:
            token: NV-Auth JWT token (or set LLM_GATEWAY_TOKEN env var)
            client_id: SSA OAuth client ID (or set LLM_CLIENT_ID env var)
            client_secret: SSA OAuth secret (or set LLM_CLIENT_SECRET env var)
            model: Model to use (default: gpt-4o)
        """
        self.model = model
        self.token = token or os.environ.get("LLM_GATEWAY_TOKEN")
        self.client_id = client_id or os.environ.get("LLM_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("LLM_CLIENT_SECRET")
        self._oauth_token = None

        logger.debug(f"LLMGatewayClient initialized: model={model}, "
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
        # NV-Auth token takes priority (it's long-lived)
        if self.token:
            logger.debug("Using NV-Auth token")
            return self.token
        # Try OAuth if credentials provided
        if self.client_id and self.client_secret:
            logger.debug("Using SSA OAuth credentials")
            return self._get_oauth_token()
        return None

    def is_available(self) -> bool:
        """Check if LLM Gateway credentials are configured."""
        available = bool(self.token or (self.client_id and self.client_secret))
        if not available:
            logger.debug("LLM Gateway credentials not configured")
        return available

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.3
    ) -> Optional[str]:
        """
        Send a chat completion request to LLM Gateway.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            max_tokens: Maximum tokens in the response
            temperature: Response randomness (0.0-1.0)

        Returns:
            The assistant's response text, or None on error
        """
        token = self.get_bearer_token()
        if not token:
            logger.warning("No LLM Gateway token available")
            return None

        logger.debug(f"Sending chat completion request: {len(messages)} messages, max_tokens={max_tokens}")

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
                "temperature": temperature,
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
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.debug(f"LLM response received: {len(content)} chars")
            return content

        except requests.exceptions.HTTPError as e:
            logger.error(f"LLM Gateway HTTP error: {e.response.status_code} - {e.response.text[:200]}")
            return None
        except requests.exceptions.Timeout:
            logger.error("LLM Gateway request timed out")
            return None
        except Exception as e:
            logger.error(f"LLM Gateway error: {type(e).__name__}: {e}")
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

    # Prepare failure summary for LLM (limit to 30 tests to avoid token limits)
    failure_lines = []
    for i, test in enumerate(summary.failed_tests[:30]):
        failure_lines.append(
            f"{i + 1}. [{test.status.upper()}] {test.name}\n   Error: {test.error_message[:200]}"
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

    messages = [
        {
            "role": "system",
            "content": "You are a senior QA engineer analyzing automated test results. Be concise, technical, and actionable."
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


def _markdown_to_html(markdown_text: str) -> str:
    """Convert basic markdown to HTML for email display."""
    html = markdown_text

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
