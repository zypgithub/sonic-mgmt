"""
Configuration and Constants for Allure Summary Tool.

This module contains all configuration values, mail distribution lists,
and constants used throughout the application.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


# =============================================================================
# API CONFIGURATION
# =============================================================================

ALLURE_BASE_URL = "https://allure.nvidia.com/allure-docker-service"
HTTP_TIMEOUT = 60
SSL_VERIFY = False

# NVIDIA LLM Gateway Configuration
# Documentation: https://confluence.nvidia.com/display/LLMSVC/NVIDIA+LLM+Gateway
LLM_GATEWAY_URL = "https://prod.api.nvidia.com/llm/v1/azure"
LLM_OAUTH_TOKEN_URL = "https://prod.api.nvidia.com/oauth/api/v1/ssa/default/token"
LLM_DEFAULT_MODEL = "gpt-4o"
LLM_API_VERSION = "2024-02-15-preview"


# =============================================================================
# EMAIL CONFIGURATION
# =============================================================================

MAIL_SERVER = "mail.nvidia.com"
MAIL_PORT = 25
SENDER_EMAIL = "noreply-allure-summary@nvidia.com"
SENDER_NAME = "Allure Nightly Summary"


# =============================================================================
# MAIL DISTRIBUTION LISTS
# =============================================================================
# Easy to maintain - just add/remove emails here

class MailList(Enum):
    """Pre-defined mail distribution lists."""

    # Core team - just maintainer
    CORE_TEAM = [
        "itkoren@nvidia.com",
        "ncaro@nvidia.com",
    ]

    # XDR team
    XDR_TEAM = [
        "itkoren@nvidia.com",
    ]

    # Security team
    SECURITY_TEAM = [
        "itkoren@nvidia.com",
    ]

    # NVLink team
    NVLINK_TEAM = [
        "itkoren@nvidia.com",
    ]

    # All stakeholders (ncaro org distribution list)
    ALL = [
        "ncaro-org@exchange.nvidia.com",
    ]


def get_mail_list(list_name: str) -> List[str]:
    """
    Get email addresses for a named distribution list.

    Args:
        list_name: Name of the list (e.g., 'CORE_TEAM', 'ALL')

    Returns:
        List of email addresses
    """
    try:
        return MailList[list_name.upper()].value
    except KeyError:
        return []


# =============================================================================
# BUG LIKELIHOOD THRESHOLDS
# =============================================================================

class BugLikelihood:
    """Thresholds for bug likelihood classification."""

    HIGH = 75      # >= 75% = Likely a bug
    MEDIUM = 50    # 50-74% = Uncertain
    LOW = 30       # 30-49% = Probably test issue
    VERY_LOW = 0   # < 30% = Infrastructure issue


# =============================================================================
# ERROR PATTERNS FOR ANALYSIS
# =============================================================================
# Patterns to identify bug vs test issue

BUG_PATTERNS = [
    {
        "pattern": r"assert.*==.*false|assert.*!=.*true",
        "likelihood": 95,
        "reason": "Assertion comparing actual vs expected value failed"
    },
    {
        "pattern": r"expected.*but got|got.*instead of",
        "likelihood": 95,
        "reason": "Output mismatch - product returned unexpected value"
    },
    {
        "pattern": r"should be.*but (is|was)",
        "likelihood": 90,
        "reason": "Behavioral mismatch detected"
    },
    {
        "pattern": r"value.*mismatch|mismatch.*value",
        "likelihood": 90,
        "reason": "Value mismatch indicates incorrect behavior"
    },
    {
        "pattern": r"failed.*validation|validation.*failed",
        "likelihood": 85,
        "reason": "Validation check failed on product output"
    },
    {
        "pattern": r"incorrect|wrong|invalid.*response",
        "likelihood": 85,
        "reason": "Product returned incorrect response"
    },
    {
        "pattern": r"missing.*field|field.*missing|key.*not found",
        "likelihood": 80,
        "reason": "Expected field missing from output"
    },
    {
        "pattern": r"status.*error|error.*status|unexpected.*status",
        "likelihood": 80,
        "reason": "Unexpected status returned"
    },
    {
        "pattern": r"resultobj.*failed",
        "likelihood": 75,
        "reason": "Test framework detected unexpected result"
    },
]

TEST_ISSUE_PATTERNS = [
    {
        "pattern": r"netmikotimeout|ssh.*timeout|connection.*refused",
        "likelihood": 15,
        "reason": "SSH/Connection timeout - likely device or network issue"
    },
    {
        "pattern": r"setup.*failed|fixture.*error|prerequisite",
        "likelihood": 20,
        "reason": "Test setup failed before test could run"
    },
    {
        "pattern": r"cleanup.*failed|teardown.*error",
        "likelihood": 10,
        "reason": "Cleanup/teardown issue - not a product bug"
    },
    {
        "pattern": r"file not found|no such file|filenotfounderror",
        "likelihood": 25,
        "reason": "Missing file - test environment issue"
    },
    {
        "pattern": r"permission denied|access denied",
        "likelihood": 20,
        "reason": "Permission issue - infrastructure problem"
    },
    {
        "pattern": r"out of memory|memory error|oom",
        "likelihood": 30,
        "reason": "Memory issue - may be product or environment"
    },
    {
        "pattern": r"timeout.*waiting|wait.*timeout|timed out waiting",
        "likelihood": 40,
        "reason": "Timeout waiting for condition - could be either"
    },
    {
        "pattern": r"device.*unreachable|cannot connect|connection.*lost",
        "likelihood": 10,
        "reason": "Device connectivity lost"
    },
]


# =============================================================================
# UI/UX COLOR SCHEME
# =============================================================================

class Colors:
    """Color palette for email UI."""

    # Status colors
    PASSED = "#28a745"      # Green
    FAILED = "#dc3545"      # Red
    BROKEN = "#fd7e14"      # Orange
    SKIPPED = "#6c757d"     # Gray

    # Pass rate colors
    EXCELLENT = "#28a745"   # >= 95%
    GOOD = "#ffc107"        # >= 80%
    WARNING = "#fd7e14"     # >= 60%
    CRITICAL = "#dc3545"    # < 60%

    # Bug likelihood colors
    HIGH_BUG = "#c0392b"    # >= 85% - Dark red
    LIKELY_BUG = "#e74c3c"  # >= 75% - Red
    UNCERTAIN = "#f39c12"   # >= 50% - Orange
    LIKELY_TEST = "#3498db"  # >= 30% - Blue
    INFRA_ISSUE = "#95a5a6"  # < 30% - Gray

    # UI colors
    PRIMARY = "#1a1a2e"
    SECONDARY = "#16213e"
    ACCENT = "#667eea"
    BACKGROUND = "#f8f9fa"
    BORDER = "#e0e0e0"
    TEXT_PRIMARY = "#333333"
    TEXT_SECONDARY = "#666666"
    TEXT_MUTED = "#888888"
    LINK = "#007bff"


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL_DEFAULT = "INFO"
LOG_LEVEL_DEBUG = "DEBUG"
