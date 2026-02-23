"""
Multi-System Aggregation for Allure Summary Tool.

This module handles fetching and aggregating test results from multiple
test systems that run the same image version but different test suites.
"""

from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from ngts.scripts.allure_summary.models import (
    MultiSystemSummary, SystemResult, ReportSummary, FailureAnalysis
)
from ngts.scripts.allure_summary.allure_client import AllureClient, fetch_report_summary
from ngts.scripts.allure_summary.analyzer import analyze_all_failures
from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()


def setup_name_to_project(setup_name: str) -> str:
    """
    Convert MARS setup name to Allure project name.

    Example: NVOS_juliet_10_7_145_52 -> nvos-juliet-10-7-145-52
    """
    return setup_name.lower().replace("_", "-")


def fetch_system_result(
    client: AllureClient,
    setup_name: str,
    report_id: Optional[int] = None
) -> Optional[SystemResult]:
    """
    Fetch and analyze results for a single system.

    Args:
        client: AllureClient instance
        setup_name: MARS setup name (e.g., NVOS_juliet_10_7_145_52)
        report_id: Specific report ID, or None for latest

    Returns:
        SystemResult with summary and analyses, or None on error
    """
    project_name = setup_name_to_project(setup_name)
    logger.info(f"Fetching results for {setup_name} ({project_name})...")

    try:
        # Try with -session-reports suffix first (more common)
        summary = fetch_report_summary(client, project_name, report_id)

        if summary.error:
            logger.warning(f"Failed to fetch {setup_name}: {summary.error}")
            return None

        # Enrich with known bugs from Confluence
        try:
            from ngts.scripts.allure_summary.known_bugs import get_known_bugs_database
            from ngts.scripts.allure_summary.models import KnownBugInfo

            bugs_db = get_known_bugs_database()
            for test in summary.failed_tests:
                mapping = bugs_db.find_bug_for_test(test.name)
                if mapping:
                    bug_info = KnownBugInfo(
                        bug_id=mapping.bug.bug_id if mapping.bug else "",
                        bug_url=mapping.bug.url if mapping.bug else "",
                        description=mapping.bug.description if mapping.bug else "",
                        assigned_to=mapping.assigned_to,
                        status=mapping.status,
                        notes=mapping.notes
                    )
                    test.known_bug = bug_info
        except Exception as e:
            logger.debug(f"Known bugs enrichment not available: {e}")

        # Analyze failures
        analyses = analyze_all_failures(summary.failed_tests)

        return SystemResult(
            setup_name=setup_name,
            summary=summary,
            analyses=analyses
        )

    except Exception as e:
        logger.error(f"Error fetching {setup_name}: {e}")
        return None


def fetch_all_systems(
    setup_names: List[str],
    report_ids: Optional[List[int]] = None,
    max_workers: int = 4
) -> List[SystemResult]:
    """
    Fetch results from multiple systems in parallel.

    Args:
        setup_names: List of MARS setup names
        report_ids: Optional list of report IDs (same length as setup_names)
        max_workers: Maximum parallel requests

    Returns:
        List of SystemResult objects (excludes failed fetches)
    """
    client = AllureClient()
    results = []

    if report_ids is None:
        report_ids = [None] * len(setup_names)

    logger.info(f"Fetching results from {len(setup_names)} systems...")

    # Use ThreadPoolExecutor for parallel fetching
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_setup = {
            executor.submit(fetch_system_result, client, name, rid): name
            for name, rid in zip(setup_names, report_ids)
        }

        for future in as_completed(future_to_setup):
            setup_name = future_to_setup[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                    logger.info(
                        f"  ✅ {result.short_name}: {result.summary.pass_rate:.1f}% "
                        f"({result.summary.passed}/{result.summary.total})"
                    )
            except Exception as e:
                logger.error(f"  ❌ {setup_name}: {e}")

    # Sort by setup name for consistent ordering
    results.sort(key=lambda r: r.setup_name)

    return results


def aggregate_multi_system(
    systems: List[SystemResult],
    image_version: Optional[str] = None
) -> MultiSystemSummary:
    """
    Aggregate results from multiple systems into a single summary.

    Args:
        systems: List of SystemResult objects
        image_version: Override image version (auto-detected if not provided)

    Returns:
        MultiSystemSummary with aggregated statistics
    """
    if not systems:
        logger.warning("No systems to aggregate")
        return MultiSystemSummary(image_version=image_version or "Unknown")

    # Auto-detect image version from first system with a version
    if not image_version:
        for sys in systems:
            if sys.summary.image_version:
                image_version = sys.summary.image_version
                break
        image_version = image_version or "Unknown"

    summary = MultiSystemSummary(
        image_version=image_version,
        systems=systems
    )

    # Compute all aggregate statistics
    summary.compute_aggregates()

    logger.info(f"Aggregated {len(systems)} systems:")
    logger.info(f"  Total: {summary.total_passed}/{summary.total_tests} passed ({summary.overall_pass_rate:.1f}%)")
    logger.info(f"  New failures: {summary.new_failure_count}")
    logger.info(f"  Cross-system failures: {len(summary.cross_system_failures)}")

    return summary


def fetch_and_aggregate(
    setup_names: List[str],
    report_ids: Optional[List[int]] = None,
    image_version: Optional[str] = None
) -> Tuple[MultiSystemSummary, List[FailureAnalysis]]:
    """
    Convenience function to fetch all systems and aggregate.

    Args:
        setup_names: List of MARS setup names
        report_ids: Optional list of report IDs
        image_version: Override image version

    Returns:
        Tuple of (MultiSystemSummary, combined_analyses)
    """
    # Fetch all systems
    systems = fetch_all_systems(setup_names, report_ids)

    if not systems:
        logger.error("No systems were successfully fetched")
        return MultiSystemSummary(image_version=image_version or "Unknown"), []

    # Aggregate
    summary = aggregate_multi_system(systems, image_version)

    # Combine all analyses, sorted by bug likelihood
    all_analyses = []
    for sys in systems:
        all_analyses.extend(sys.analyses)
    all_analyses.sort(key=lambda a: a.bug_likelihood, reverse=True)

    return summary, all_analyses
