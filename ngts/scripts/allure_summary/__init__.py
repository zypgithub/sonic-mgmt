"""
Allure Nightly Summary Tool

A professional tool for generating and sending Allure test report summaries.

Features:
- Fetches test results from Allure server
- Analyzes failures to determine bug vs test issues
- Generates beautiful HTML email reports
- Supports NVIDIA LLM Gateway for AI-powered analysis

Usage:
    from allure_summary import run_summary

    run_summary(
        project_name="my-project",
        email="user@nvidia.com"
    )

Command Line:
    python -m allure_summary --setup-name NVOS_juliet_10_7_145_52 --email user@nvidia.com

Author: NVOS Verification Team
"""

__version__ = "1.0.0"
__author__ = "NVOS Verification Team"

from ngts.scripts.allure_summary.models import ReportSummary, FailedTest, FailureAnalysis, EmailConfig
from ngts.scripts.allure_summary.allure_client import AllureClient, fetch_report_summary
from ngts.scripts.allure_summary.analyzer import analyze_all_failures, get_likely_bugs, get_test_issues
from ngts.scripts.allure_summary.llm_client import LLMGatewayClient, analyze_failures_with_llm
from ngts.scripts.allure_summary.email_sender import send_email
from ngts.scripts.allure_summary.config import MailList, get_mail_list

__all__ = [
    # Models
    "ReportSummary",
    "FailedTest",
    "FailureAnalysis",
    "EmailConfig",
    # Clients
    "AllureClient",
    "fetch_report_summary",
    "LLMGatewayClient",
    # Analysis
    "analyze_all_failures",
    "analyze_failures_with_llm",
    "get_likely_bugs",
    "get_test_issues",
    # Email
    "send_email",
    # Config
    "MailList",
    "get_mail_list",
]
