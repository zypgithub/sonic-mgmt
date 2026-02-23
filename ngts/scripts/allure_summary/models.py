"""
Data Models for Allure Summary Tool.

This module contains all data classes and models used throughout the application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class FailedTest:
    """Represents a failed or broken test."""
    name: str
    status: str  # "failed" or "broken"
    duration_ms: int
    error_message: str = ""
    suite: str = ""
    uid: str = ""  # Used for direct linking to test in Allure report

    def __post_init__(self):
        """Validate and clean data after initialization."""
        self.name = self.name.strip() if self.name else "Unknown"
        self.status = self.status.lower() if self.status else "unknown"
        self.error_message = self.error_message[:500] if self.error_message else ""


@dataclass
class FailureAnalysis:
    """Analysis result for a single test failure."""
    test: FailedTest
    bug_likelihood: int  # 0-100%
    classification: str  # "bug", "test_issue", "infra", "uncertain"
    reason: str  # Why we classified it this way

    @property
    def is_likely_bug(self) -> bool:
        """Returns True if this is likely a product bug (>=75%)."""
        return self.bug_likelihood >= 75

    @property
    def severity(self) -> str:
        """Returns severity level based on bug likelihood."""
        if self.bug_likelihood >= 85:
            return "high"
        elif self.bug_likelihood >= 75:
            return "medium"
        elif self.bug_likelihood >= 50:
            return "uncertain"
        elif self.bug_likelihood >= 30:
            return "low"
        return "very_low"


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

    @property
    def is_healthy(self) -> bool:
        """Returns True if pass rate is >= 80%."""
        return self.pass_rate >= 80.0

    @property
    def is_critical(self) -> bool:
        """Returns True if pass rate is < 60%."""
        return self.pass_rate < 60.0

    @property
    def failure_count(self) -> int:
        """Total number of failed + broken tests."""
        return self.failed + self.broken

    def get_status_emoji(self) -> str:
        """Returns an emoji representing the overall status."""
        if self.pass_rate >= 95:
            return "🟢"
        elif self.pass_rate >= 80:
            return "🟡"
        elif self.pass_rate >= 60:
            return "🟠"
        return "🔴"

    def __str__(self) -> str:
        """Human-readable summary string."""
        return (
            f"Report #{self.report_id}: {self.passed}/{self.total} passed "
            f"({self.pass_rate:.1f}%) | Failed: {self.failed}, Broken: {self.broken}"
        )


@dataclass
class EmailConfig:
    """Configuration for sending an email."""
    recipients: List[str]
    subject: str
    dry_run: bool = False

    def __post_init__(self):
        """Validate recipients."""
        if not self.recipients:
            raise ValueError("At least one recipient is required")
        # Clean up recipients
        self.recipients = [r.strip() for r in self.recipients if r.strip()]
