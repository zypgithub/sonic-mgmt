"""
Data Models for Allure Summary Tool.

This module contains all data classes and models used throughout the application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TestHistory:
    """Historical stats for a test."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    broken: int = 0

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate percentage."""
        return (self.passed / self.total * 100) if self.total > 0 else 0.0

    @property
    def fail_rate(self) -> float:
        """Calculate fail rate percentage."""
        return ((self.failed + self.broken) / self.total * 100) if self.total > 0 else 0.0

    @property
    def is_flaky(self) -> bool:
        """Test is flaky if it has mixed results (20-80% pass rate)."""
        return self.total >= 5 and 20 < self.pass_rate < 80

    @property
    def is_consistently_failing(self) -> bool:
        """Test consistently fails (pass rate < 20% with enough history)."""
        return self.total >= 5 and self.pass_rate < 20

    @property
    def ratio_str(self) -> str:
        """Human readable ratio string."""
        return f"{self.passed}/{self.total} ({self.pass_rate:.0f}%)"


@dataclass
class KnownBugInfo:
    """Information about a known bug linked to a test."""
    bug_id: str  # e.g., "4463449" or "5721616"
    bug_url: str  # Link to nvbugs
    description: str = ""
    assigned_to: str = ""
    status: str = ""  # Bug, Fixed, Assigned, Test Issue, WIP
    notes: str = ""


@dataclass
class CommitMatch:
    """A commit that might be related to a test result."""
    short_hash: str
    subject: str
    probability: float  # 0.0 to 1.0
    reasons: str  # Why we think it's related
    repo: str = "nvos"  # "nvos" or "sonic-mgmt"

    @property
    def probability_pct(self) -> int:
        return int(self.probability * 100)


@dataclass
class FailedTest:
    """Represents a failed or broken test."""
    name: str
    status: str  # "failed" or "broken"
    duration_ms: int
    error_message: str = ""
    suite: str = ""
    uid: str = ""  # Used for direct linking to test in Allure report
    history: Optional[TestHistory] = None  # Historical pass/fail data
    is_new_failure: bool = False  # newFailed flag from Allure
    flaky: bool = False  # flaky flag from Allure
    known_bug: Optional[KnownBugInfo] = None  # Known bug information from Confluence
    likely_cause_commits: List[CommitMatch] = field(default_factory=list)  # Commits that might have caused this failure

    def __post_init__(self):
        """Validate and clean data after initialization."""
        self.name = self.name.strip() if self.name else "Unknown"
        self.status = self.status.lower() if self.status else "unknown"
        self.error_message = self.error_message[:500] if self.error_message else ""

    @property
    def has_known_bug(self) -> bool:
        """Returns True if this test has a known bug."""
        return self.known_bug is not None and self.known_bug.bug_id

    @property
    def is_being_worked_on(self) -> bool:
        """Returns True if someone is assigned to this test."""
        return self.known_bug is not None and self.known_bug.assigned_to

    @property
    def is_marked_fixed(self) -> bool:
        """Returns True if the known bug is marked as Fixed."""
        return self.known_bug is not None and self.known_bug.status.lower() == 'fixed'

    @property
    def has_likely_cause(self) -> bool:
        """Returns True if we found likely cause commits."""
        return len(self.likely_cause_commits) > 0 and self.likely_cause_commits[0].probability > 0.2


@dataclass
class FailureAnalysis:
    """Analysis result for a single test failure."""
    test: FailedTest
    bug_likelihood: int  # 0-100%
    classification: str  # "bug", "test_issue", "infra", "uncertain"
    reason: str  # Why we classified it this way
    issue_type: str = ""  # Specific issue type: "timeout", "invalid_param", "connection", etc.

    @property
    def is_likely_bug(self) -> bool:
        """Returns True if this is likely a product bug (>=75%)."""
        return self.bug_likelihood >= 75

    @property
    def is_timeout(self) -> bool:
        """Returns True if this is a timeout issue."""
        return self.issue_type == "timeout"

    @property
    def is_invalid_param(self) -> bool:
        """Returns True if this is an invalid parameter/command issue."""
        return self.issue_type == "invalid_param"

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

    @property
    def issue_icon(self) -> str:
        """Returns an icon for the specific issue type."""
        icons = {
            "timeout": "⏱️",
            "invalid_param": "⚠️",
            "connection": "🔌",
            "setup": "🔧",
            "teardown": "🧹",
            "environment": "🖥️",
        }
        return icons.get(self.issue_type, "")


@dataclass
class NewlyPassedTest:
    """Represents a test that was previously failing but now passes."""
    name: str
    uid: str = ""
    previous_status: str = ""  # What it was before (failed, broken)
    consecutive_failures: int = 0  # How many times it failed before passing
    history_pass_rate: float = 0.0  # Overall pass rate from history
    likely_fix_commits: List[CommitMatch] = field(default_factory=list)  # Commits that might have fixed it


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
    newly_passed_tests: List[NewlyPassedTest] = field(default_factory=list)  # Tests that started passing
    error: Optional[str] = None
    image_version: str = ""  # Target image version (product-release)
    firmware_versions: dict = field(default_factory=dict)  # Firmware versions {name: version}
    ai_available: bool = False  # Whether AI/LLM was available for analysis

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


@dataclass
class SystemResult:
    """Result from a single system in multi-system mode."""
    setup_name: str  # Original setup name (e.g., NVOS_juliet_10_7_145_52)
    summary: ReportSummary
    analyses: List['FailureAnalysis'] = field(default_factory=list)

    @property
    def short_name(self) -> str:
        """Short display name for the system."""
        # Extract meaningful part with friendly names, all lowercase
        # NVOS_bm_10_7_148_248 -> mamba-248
        # NVOS_bm_dgx_10_7_145_81 -> mamba-dgx-81
        # NVOS_crocodile_10_7_148_94 -> croc-94
        name = self.setup_name.lower().replace("nvos_", "")
        parts = name.split("_")

        # Get last IP octet for disambiguation
        last_octet = parts[-1] if parts[-1].isdigit() else ""

        # Map device names to friendly short names
        if name.startswith("bm_dgx_"):
            device = "mamba-dgx"
        elif name.startswith("bm_"):
            device = "mamba"
        elif name.startswith("crocodile_"):
            device = "croc"
        elif name.startswith("juliet_"):
            device = "juliet"
        elif name.startswith("rosalind_"):
            device = "rosalind"
        else:
            # Default: use first part
            device = parts[0] if parts else name

        if last_octet:
            return f"{device}-{last_octet}"
        return device

    @property
    def new_failures(self) -> List[FailedTest]:
        """Get new failures (regressions) for this system."""
        return [t for t in self.summary.failed_tests if t.is_new_failure]


@dataclass
class CrossSystemFailure:
    """A test that fails on multiple systems."""
    test_name: str
    systems: List[str]  # System names where it fails
    error_messages: dict = field(default_factory=dict)  # {system: error_message}
    is_new_on_any: bool = False  # Is it a new failure on any system?

    @property
    def failure_count(self) -> int:
        return len(self.systems)

    @property
    def is_cross_system(self) -> bool:
        """Returns True if fails on multiple systems."""
        return len(self.systems) > 1


@dataclass
class MultiSystemSummary:
    """Aggregated summary across multiple test systems."""
    image_version: str
    systems: List[SystemResult] = field(default_factory=list)

    # Will be computed after systems are added
    total_passed: int = 0
    total_failed: int = 0
    total_broken: int = 0
    total_skipped: int = 0
    total_tests: int = 0

    # Cross-system analysis
    cross_system_failures: List[CrossSystemFailure] = field(default_factory=list)
    all_new_failures: List[FailedTest] = field(default_factory=list)

    @property
    def overall_pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.total_passed / self.total_tests) * 100

    @property
    def system_count(self) -> int:
        return len(self.systems)

    @property
    def all_healthy(self) -> bool:
        """Returns True if all systems have >= 80% pass rate."""
        return all(s.summary.is_healthy for s in self.systems)

    @property
    def any_critical(self) -> bool:
        """Returns True if any system has < 60% pass rate."""
        return any(s.summary.is_critical for s in self.systems)

    @property
    def new_failure_count(self) -> int:
        """Total new failures across all systems."""
        return len(self.all_new_failures)

    def get_status_emoji(self) -> str:
        """Returns an emoji representing the overall status."""
        if self.overall_pass_rate >= 95:
            return "🟢"
        elif self.overall_pass_rate >= 80:
            return "🟡"
        elif self.overall_pass_rate >= 60:
            return "🟠"
        return "🔴"

    def compute_aggregates(self):
        """Compute aggregate statistics from all systems."""
        self.total_passed = sum(s.summary.passed for s in self.systems)
        self.total_failed = sum(s.summary.failed for s in self.systems)
        self.total_broken = sum(s.summary.broken for s in self.systems)
        self.total_skipped = sum(s.summary.skipped for s in self.systems)
        self.total_tests = sum(s.summary.total for s in self.systems)

        # Collect all new failures
        seen_names = set()
        for sys in self.systems:
            for test in sys.new_failures:
                if test.name not in seen_names:
                    self.all_new_failures.append(test)
                    seen_names.add(test.name)

        # Find cross-system failures
        self._compute_cross_system_failures()

    def _compute_cross_system_failures(self):
        """Identify tests that fail on multiple systems."""
        # Map test name -> list of (system_name, test)
        failure_map: dict = {}

        for sys in self.systems:
            for test in sys.summary.failed_tests:
                if test.name not in failure_map:
                    failure_map[test.name] = []
                failure_map[test.name].append((sys.short_name, test))

        # Create CrossSystemFailure for tests failing on 2+ systems
        for test_name, occurrences in failure_map.items():
            if len(occurrences) > 1:
                systems = [occ[0] for occ in occurrences]
                error_messages = {occ[0]: occ[1].error_message for occ in occurrences}
                is_new = any(occ[1].is_new_failure for occ in occurrences)

                self.cross_system_failures.append(CrossSystemFailure(
                    test_name=test_name,
                    systems=systems,
                    error_messages=error_messages,
                    is_new_on_any=is_new
                ))

        # Sort by number of systems affected (descending)
        self.cross_system_failures.sort(key=lambda x: x.failure_count, reverse=True)
