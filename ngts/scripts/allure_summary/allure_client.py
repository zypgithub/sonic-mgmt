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
from ngts.scripts.allure_summary.models import FailedTest, ReportSummary, TestHistory
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
        """
        logger.debug(f"Fetching categories for {project_name}/report/{report_id}")
        return self._get(f"/projects/{project_name}/reports/{report_id}/data/categories.json")

    def get_report_environment(self, project_name: str, report_id: int) -> Optional[list]:
        """
        Get environment.json (test environment info including image version).
        """
        logger.debug(f"Fetching environment for {project_name}/report/{report_id}")
        return self._get(f"/projects/{project_name}/reports/{report_id}/widgets/environment.json")

    def get_suites(self, project_name: str, report_id: int) -> Optional[dict]:
        """
        Get suites.json to find test cases.
        """
        logger.debug(f"Fetching suites for {project_name}/report/{report_id}")
        return self._get(f"/projects/{project_name}/reports/{report_id}/data/suites.json")

    def get_test_case(self, project_name: str, report_id: int, test_uid: str) -> Optional[dict]:
        """
        Get detailed test case data including attachments.
        """
        logger.debug(f"Fetching test case {test_uid}")
        return self._get(f"/projects/{project_name}/reports/{report_id}/data/test-cases/{test_uid}.json")

    def get_attachment(self, project_name: str, report_id: int, source: str) -> Optional[str]:
        """
        Get attachment content.
        """
        url = f"{self.base_url}/projects/{project_name}/reports/{report_id}/data/attachments/{source}"
        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT, verify=SSL_VERIFY)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.debug(f"Failed to get attachment {source}: {e}")
            return None

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


def extract_image_version_from_attachment(content: str) -> str:
    """
    Extract product-release version from setup_versions attachment.

    The attachment contains output like:
        SYSTEM VERSION:
        ...
        product-release  25.03.0106
        ...

    Args:
        content: Raw text content of setup_versions attachment

    Returns:
        Version string or empty string if not found
    """
    import re
    # Look for product-release line
    match = re.search(r'product-release\s+(\S+)', content)
    if match:
        return match.group(1)
    return ""


def extract_firmware_versions_from_attachment(content: str) -> dict:
    """
    Extract firmware versions from setup_versions attachment.

    The attachment contains output like:
        PLATFORM FIRMWARE:
        Name         Actual FW           Part Number            FW Source
        -----------  ------------------  ---------------------  ---------
        ASIC         35.2016.3046        920-9B36P-00RX-8S0_Ax  default
        BIOS         0ACQF_06.01.006     N/A                    default
        ...

    Args:
        content: Raw text content of setup_versions attachment

    Returns:
        Dict of {component_name: firmware_version}
    """
    import re
    firmware = {}

    # Find PLATFORM FIRMWARE section
    fw_match = re.search(r'PLATFORM FIRMWARE:\s*\n(.*?)(?:\n\n|\nFAE|\Z)', content, re.DOTALL)
    if not fw_match:
        return firmware

    fw_section = fw_match.group(1)

    # Parse each line - looking for rows with firmware data
    # Skip header lines (Name, dashes)
    for line in fw_section.split('\n'):
        line = line.strip()
        if not line or line.startswith('Name') or line.startswith('---'):
            continue

        # Parse line: Name  Actual_FW  Part_Number  FW_Source
        # Use regex to extract first two columns
        match = re.match(r'^(\S+)\s+(\S+)', line)
        if match:
            name = match.group(1)
            version = match.group(2)
            # Skip N/A versions
            if version and version != 'N/A':
                firmware[name] = version

    return firmware


def find_setup_versions_attachment(test_case: dict) -> Optional[dict]:
    """
    Recursively find setup_versions attachment in test case data.

    Args:
        test_case: Test case data from Allure API

    Returns:
        Attachment dict with 'source' field, or None if not found
    """
    def search_attachments(obj):
        if isinstance(obj, dict):
            # Check if this object has attachments
            for att in obj.get('attachments', []):
                if att.get('name') == 'setup_versions':
                    return att
            # Recursively search children
            for key, value in obj.items():
                if key != 'attachments':
                    result = search_attachments(value)
                    if result:
                        return result
        elif isinstance(obj, list):
            for item in obj:
                result = search_attachments(item)
                if result:
                    return result
        return None

    return search_attachments(test_case)


def find_deploy_test_uid(suites_data: dict) -> Optional[str]:
    """
    Find the UID of the deploy/upgrade test case which contains setup_versions attachment.

    Args:
        suites_data: Suites data from Allure API

    Returns:
        Test UID or None if not found
    """
    def find_deploy(node):
        if isinstance(node, dict):
            name = node.get('name', '').lower()
            status = node.get('status')
            # Look for deploy and upgrade test - must have a status (actual test, not suite)
            if status and 'deploy' in name and ('upgrade' in name or 'image' in name):
                return node.get('uid')
            # Recursively search children
            for child in node.get('children', []):
                uid = find_deploy(child)
                if uid:
                    return uid
        return None

    # First try to find deploy test
    deploy_uid = find_deploy(suites_data)
    if deploy_uid:
        return deploy_uid

    # Fallback to first test if deploy not found
    def find_first(node):
        if isinstance(node, dict):
            if 'uid' in node and 'status' in node and node.get('status'):
                return node.get('uid')
            for child in node.get('children', []):
                uid = find_first(child)
                if uid:
                    return uid
        return None

    return find_first(suites_data)


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


def extract_newly_passed_tests(
    client: 'AllureClient',
    project_name: str,
    report_id: int,
    suites_data: dict,
    max_tests: int = 20
) -> List['NewlyPassedTest']:
    """
    Extract tests that were previously failing but now pass.

    Uses newPassed flag from Allure test cases.

    Args:
        client: AllureClient instance
        project_name: Allure project name
        report_id: Report ID
        suites_data: Suites data from Allure API
        max_tests: Maximum number of tests to return

    Returns:
        List of NewlyPassedTest objects
    """
    from ngts.scripts.allure_summary.models import NewlyPassedTest

    # Find ALL passed tests with UIDs (not just a subset)
    passed_tests = []

    def find_passed(node):
        if isinstance(node, dict):
            if node.get('status') == 'passed' and 'uid' in node:
                passed_tests.append({
                    'name': node.get('name', 'Unknown'),
                    'uid': node.get('uid'),
                })
            for child in node.get('children', []):
                find_passed(child)

    find_passed(suites_data)
    logger.debug(f"Found {len(passed_tests)} passed tests to check for newPassed flag")

    newly_passed = []

    # Check all passed tests for newPassed flag
    for test_info in passed_tests:
        if len(newly_passed) >= max_tests:
            break

        try:
            tc_data = client.get_test_case(project_name, report_id, test_info['uid'])
            if not tc_data:
                continue

            # Check if this test is newly passed
            if tc_data.get('newPassed', False):
                # Get history to understand how long it was failing
                history = tc_data.get('extra', {}).get('history', {})
                stat = history.get('statistic', {})
                items = history.get('items', [])

                # Count consecutive failures before this pass
                consecutive_failures = 0
                for item in items:
                    if item.get('status') in ['failed', 'broken']:
                        consecutive_failures += 1
                    else:
                        break

                # Calculate pass rate
                total = stat.get('total', 1)
                passed = stat.get('passed', 0)
                pass_rate = (passed / total * 100) if total > 0 else 0

                # Get previous status from first history item
                previous_status = items[0].get('status', 'unknown') if items else 'unknown'

                newly_passed.append(NewlyPassedTest(
                    name=test_info['name'],
                    uid=test_info['uid'],
                    previous_status=previous_status,
                    consecutive_failures=consecutive_failures,
                    history_pass_rate=pass_rate
                ))

        except Exception as e:
            logger.debug(f"Failed to check {test_info['name']}: {e}")

    if newly_passed:
        logger.info(f"Found {len(newly_passed)} newly passing tests")

    return newly_passed


def enrich_tests_with_history(
    client: 'AllureClient',
    project_name: str,
    report_id: int,
    failed_tests: List[FailedTest],
    max_tests: int = 50
) -> None:
    """
    Enrich failed tests with history data from test case details.

    Args:
        client: AllureClient instance
        project_name: Allure project name
        report_id: Report ID
        failed_tests: List of failed tests to enrich (modified in place)
        max_tests: Maximum number of tests to fetch details for (API limit)
    """
    logger.info(f"Fetching history data for up to {min(len(failed_tests), max_tests)} tests...")

    enriched = 0
    for test in failed_tests[:max_tests]:
        if not test.uid:
            continue

        try:
            tc_data = client.get_test_case(project_name, report_id, test.uid)
            if not tc_data:
                continue

            # Get flaky and newFailed flags
            test.flaky = tc_data.get('flaky', False)
            test.is_new_failure = tc_data.get('newFailed', False)

            # Get history from extra field
            extra = tc_data.get('extra', {})
            history_data = extra.get('history', {})
            if history_data:
                stat = history_data.get('statistic', {})
                test.history = TestHistory(
                    total=stat.get('total', 0),
                    passed=stat.get('passed', 0),
                    failed=stat.get('failed', 0),
                    broken=stat.get('broken', 0)
                )
                enriched += 1

        except Exception as e:
            logger.debug(f"Failed to get history for {test.name}: {e}")

    logger.info(f"Enriched {enriched} tests with history data")


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
        # Enrich with history data
        if summary.failed_tests:
            enrich_tests_with_history(client, project_name, report_id, summary.failed_tests)
    else:
        logger.warning("No categories data available")

    # Get newly passed tests (tests that were failing but now pass)
    logger.debug("Checking for newly passing tests...")
    suites_data = client.get_suites(project_name, report_id)
    if suites_data:
        summary.newly_passed_tests = extract_newly_passed_tests(
            client, project_name, report_id, suites_data, max_tests=15
        )

    # Get image version from environment
    env_data = client.get_report_environment(project_name, report_id)
    if env_data:
        for item in env_data:
            # Handle case where API returns unexpected format (e.g., strings instead of dicts)
            if not isinstance(item, dict):
                logger.debug(f"Skipping non-dict environment item: {type(item)}")
                continue
            name = item.get("name", "").lower()
            if "version" in name or "image" in name or "build" in name:
                summary.image_version = item.get("values", [""])[0]
                logger.debug(f"Found image version from environment: {summary.image_version}")
                break

    # If no version from environment, try to extract from setup_versions attachment
    if not summary.image_version:
        logger.debug("No version in environment, trying setup_versions attachment...")
        try:
            # Get suites to find deploy test (which has setup_versions attachment)
            suites_data = client.get_suites(project_name, report_id)
            if suites_data:
                deploy_test_uid = find_deploy_test_uid(suites_data)
                if deploy_test_uid:
                    logger.debug(f"Found deploy test UID: {deploy_test_uid}")
                    test_case = client.get_test_case(project_name, report_id, deploy_test_uid)
                    if test_case:
                        attachment = find_setup_versions_attachment(test_case)
                        if attachment:
                            source = attachment.get('source', '')
                            logger.debug(f"Found setup_versions attachment: {source}")
                            content = client.get_attachment(project_name, report_id, source)
                            if content:
                                # Extract image version
                                summary.image_version = extract_image_version_from_attachment(content)
                                if summary.image_version:
                                    logger.info(f"Found image version from attachment: {summary.image_version}")

                                # Extract firmware versions
                                summary.firmware_versions = extract_firmware_versions_from_attachment(content)
                                if summary.firmware_versions:
                                    logger.info(f"Found {len(summary.firmware_versions)} firmware versions")
                                    for name, ver in summary.firmware_versions.items():
                                        logger.debug(f"  {name}: {ver}")
        except Exception as e:
            logger.debug(f"Failed to extract version from attachment: {e}")

    return summary
