"""
Failure Analysis Engine for Allure Summary Tool.

This module analyzes test failures to determine if they are likely bugs
or test/infrastructure issues.
"""

import re
from typing import List

from ngts.scripts.allure_summary.config import BUG_PATTERNS, TEST_ISSUE_PATTERNS, BugLikelihood
from ngts.scripts.allure_summary.models import FailedTest, FailureAnalysis
from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()


def analyze_single_failure(test: FailedTest) -> FailureAnalysis:
    """
    Analyze a single test failure to determine if it's a bug or test issue.

    Args:
        test: The failed test to analyze

    Returns:
        FailureAnalysis with bug likelihood and reasoning
    """
    error = test.error_message.lower()
    name = test.name.lower()

    logger.debug(f"Analyzing test: {test.name} (status={test.status})")

    # Check for bug patterns first (high likelihood)
    for pattern_info in BUG_PATTERNS:
        if re.search(pattern_info["pattern"], error, re.IGNORECASE):
            likelihood = pattern_info["likelihood"]
            reason = pattern_info["reason"]
            logger.debug(f"  Matched BUG pattern: {pattern_info['pattern'][:30]}... -> {likelihood}%")
            return FailureAnalysis(
                test=test,
                bug_likelihood=likelihood,
                classification="bug" if likelihood >= BugLikelihood.HIGH else "uncertain",
                reason=reason
            )

    # Check for test issue patterns (low likelihood)
    for pattern_info in TEST_ISSUE_PATTERNS:
        if re.search(pattern_info["pattern"], error, re.IGNORECASE):
            likelihood = pattern_info["likelihood"]
            reason = pattern_info["reason"]
            logger.debug(f"  Matched TEST_ISSUE pattern: {pattern_info['pattern'][:30]}... -> {likelihood}%")
            return FailureAnalysis(
                test=test,
                bug_likelihood=likelihood,
                classification="test_issue" if likelihood <= BugLikelihood.LOW else "uncertain",
                reason=reason
            )

    # Default analysis based on status
    if test.status == "failed":
        # "failed" status in Allure typically means assertion failure
        logger.debug(f"  No pattern match, status=failed -> 70% (default)")
        return FailureAnalysis(
            test=test,
            bug_likelihood=70,
            classification="uncertain",
            reason="Test assertion failed - likely a product issue but needs investigation"
        )
    else:
        # "broken" status typically means test infrastructure issue
        logger.debug(f"  No pattern match, status=broken -> 35% (default)")
        return FailureAnalysis(
            test=test,
            bug_likelihood=35,
            classification="uncertain",
            reason="Test broken during execution - may be test or environment issue"
        )


def analyze_all_failures(failed_tests: List[FailedTest]) -> List[FailureAnalysis]:
    """
    Analyze all failures and return sorted by bug likelihood.

    Args:
        failed_tests: List of failed tests to analyze

    Returns:
        List of FailureAnalysis sorted by bug likelihood (descending)
    """
    if not failed_tests:
        logger.info("No failed tests to analyze")
        return []

    logger.info(f"Analyzing {len(failed_tests)} failed tests...")

    analyses = []
    for test in failed_tests:
        try:
            analysis = analyze_single_failure(test)
            analyses.append(analysis)
        except Exception as e:
            logger.error(f"Error analyzing test '{test.name}': {e}")
            # Create a default analysis on error
            analyses.append(FailureAnalysis(
                test=test,
                bug_likelihood=50,
                classification="uncertain",
                reason=f"Analysis error: {e}"
            ))

    # Sort by bug likelihood descending
    analyses.sort(key=lambda a: a.bug_likelihood, reverse=True)

    # Log summary
    likely_bugs = sum(1 for a in analyses if a.bug_likelihood >= BugLikelihood.HIGH)
    test_issues = sum(1 for a in analyses if a.bug_likelihood < BugLikelihood.LOW)
    uncertain = len(analyses) - likely_bugs - test_issues

    logger.info(f"Analysis complete: {likely_bugs} likely bugs, {test_issues} test issues, {uncertain} uncertain")

    return analyses


def get_likely_bugs(analyses: List[FailureAnalysis]) -> List[FailureAnalysis]:
    """
    Filter analyses to return only likely bugs (>=75% likelihood).

    Args:
        analyses: List of failure analyses

    Returns:
        List of analyses with bug likelihood >= 75%
    """
    return [a for a in analyses if a.bug_likelihood >= BugLikelihood.HIGH]


def get_test_issues(analyses: List[FailureAnalysis]) -> List[FailureAnalysis]:
    """
    Filter analyses to return only test/infra issues (<75% likelihood).

    Args:
        analyses: List of failure analyses

    Returns:
        List of analyses with bug likelihood < 75%
    """
    return [a for a in analyses if a.bug_likelihood < BugLikelihood.HIGH]
