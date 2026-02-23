"""
Allure API Client for fetching report data.

This module handles all communication with the Allure server.
"""

import logging
from datetime import datetime
from typing import List, Optional

import requests
from requests.packages import urllib3

from ngts.scripts.allure_summary.config import ALLURE_BASE_URL, HTTP_TIMEOUT, SSL_VERIFY
from ngts.scripts.allure_summary.models import FailedTest, ReportSummary
from ngts.scripts.allure_summary.logger import get_logger, DebugContext

urllib3.disable_warnings()

logger = get_logger()


class AllureClient:
    """Client for fetching data from Allure server."""

    def __init__(self, base_url: str = ALLURE_BASE_URL):
        """
        Initialize Allure client.

        Args:
            base_url: Base URL of the Allure server
        """
        self.base_url = base_url
        logger.debug(f"AllureClient initialized with base_url={base_url}")

    def _get(self, path: str) -> Optional[dict]:
        """
        Make a GET request to the Allure API.

        Args:
            path: API endpoint path

        Returns:
            JSON response as dict, or None on error
        """
        url = f"{self.base_url}{path}"

        with DebugContext(logger, "HTTP GET", url=url):
            try:
                response = requests.get(url, timeout=HTTP_TIMEOUT, verify=SSL_VERIFY)
                response.raise_for_status()
                logger.debug(f"GET {path} -> {response.status_code} ({len(response.content)} bytes)")
                return response.json()
            except requests.exceptions.Timeout:
                logger.error(f"[TIMEOUT] Request timed out after {HTTP_TIMEOUT}s: {url}")
                return None
            except requests.exceptions.ConnectionError as e:
                logger.error(f"[CONNECTION ERROR] Failed to connect: {url} | {e}")
                return None
            except requests.exceptions.HTTPError as e:
                logger.error(f"[HTTP ERROR] {e.response.status_code}: {url}")
                return None
            except requests.exceptions.RequestException as e:
                logger.error(f"[REQUEST ERROR] {type(e).__name__}: {e}")
                return None
            except ValueError as e:
                logger.error(f"[JSON ERROR] Failed to parse response: {e}")
                return None

    def get_latest_report_id(self, project_name: str) -> Optional[int]:
        """
        Get the latest report ID for a project.

        Args:
            project_name: Allure project name

        Returns:
            Latest report ID, or None if not found
        """
        logger.info(f"Fetching latest report ID for project: {project_name}")

        data = self._get(f"/projects/{project_name}")
        if not data:
            logger.error(f"Failed to fetch project info for: {project_name}")
            return None

        reports = data.get("data", {}).get("project", {}).get("reports_id", [])
        logger.debug(f"Found {len(reports)} reports for project {project_name}")

        numeric_ids = [int(r) for r in reports if str(r).isdigit()]
        if not numeric_ids:
            logger.error(f"No valid report IDs found for project: {project_name}")
            return None

        latest_id = max(numeric_ids)
        logger.info(f"Latest report ID: {latest_id}")
        return latest_id

    def get_report_summary(self, project_name: str, report_id: int) -> Optional[dict]:
        """
        Get summary.json for a report.

        Args:
            project_name: Allure project name
            report_id: Report ID

        Returns:
            Summary data as dict, or None on error
        """
        logger.debug(f"Fetching summary for {project_name}/report/{report_id}")
        return self._get(f"/projects/{project_name}/reports/{report_id}/widgets/summary.json")

    def get_report_categories(self, project_name: str, report_id: int) -> Optional[dict]:
        """
        Get categories.json (failed/broken tests grouped by error).

        Args:
            project_name: Allure project name
            report_id: Report ID

        Returns:
            Categories data as dict, or None on error
        """
        logger.debug(f"Fetching categories for {project_name}/report/{report_id}")
        return self._get(f"/projects/{project_name}/reports/{report_id}/data/categories.json")

    def get_report_url(self, project_name: str, report_id: int) -> str:
        """
        Generate the full report URL.

        Args:
            project_name: Allure project name
            report_id: Report ID

        Returns:
            Full URL to the Allure report
        """
        return f"{self.base_url}/projects/{project_name}/reports/{report_id}/index.html"


def extract_failed_tests(categories_data: dict) -> List[FailedTest]:
    """
    Extract failed/broken tests from categories data.

    Args:
        categories_data: Raw categories.json data from Allure

    Returns:
        List of FailedTest objects
    """
    failed_tests = []

    if not categories_data or "children" not in categories_data:
        logger.warning("No categories data or empty children in response")
        return failed_tests

    def traverse(node, error_category=""):
        """Recursively traverse the categories tree."""
        if isinstance(node, dict):
            # Check if this is a test node
            if "status" in node and node.get("status") in ("failed", "broken"):
                test = FailedTest(
                    name=node.get("name", "Unknown"),
                    status=node.get("status", "unknown"),
                    duration_ms=node.get("time", {}).get("duration", 0),
                    error_message=error_category[:500] if error_category else "",
                    suite=node.get("parentUid", ""),
                    uid=node.get("uid", "")
                )
                failed_tests.append(test)
                logger.debug(f"Found {test.status} test: {test.name}")

            # Traverse children
            if "children" in node:
                category_name = node.get("name", "")
                for child in node["children"]:
                    traverse(child, category_name if category_name else error_category)

    for category in categories_data.get("children", []):
        traverse(category)

    logger.info(f"Extracted {len(failed_tests)} failed/broken tests")
    return failed_tests


def get_project_name_variants(project_name: str) -> List[str]:
    """
    Get all possible project name variants to try.

    Some setups use '-session-reports' suffix, some don't.

    Args:
        project_name: Base project name

    Returns:
        List of project names to try
    """
    variants = [project_name]

    # If doesn't already have -session-reports, add variant with it
    if not project_name.endswith("-session-reports"):
        variants.append(f"{project_name}-session-reports")

    return variants


def fetch_report_summary(
    client: AllureClient,
    project_name: str,
    report_id: Optional[int] = None
) -> ReportSummary:
    """
    Fetch complete report summary including failed tests.

    Args:
        client: AllureClient instance
        project_name: Allure project name
        report_id: Specific report ID, or None for latest

    Returns:
        ReportSummary with all data populated
    """
    logger.info(f"Fetching report summary for project: {project_name}")

    # Get report ID if not provided - try multiple project name variants
    if report_id is None:
        # Try different project name patterns
        for variant in get_project_name_variants(project_name):
            logger.debug(f"Trying project variant: {variant}")
            report_id = client.get_latest_report_id(variant)
            if report_id:
                project_name = variant  # Use the working variant
                logger.info(f"Found reports in project: {variant}")
                break

        if not report_id:
            logger.error("Failed to get latest report ID from any project variant")
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
    logger.debug("Fetching summary statistics...")
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

        logger.info(f"Summary: {summary}")
    else:
        summary.error = "Failed to fetch summary data"
        logger.error(summary.error)
        return summary

    # Get failed/broken tests
    logger.debug("Fetching failed/broken tests...")
    categories_data = client.get_report_categories(project_name, report_id)
    if categories_data:
        summary.failed_tests = extract_failed_tests(categories_data)
    else:
        logger.warning("No categories data available")

    return summary
