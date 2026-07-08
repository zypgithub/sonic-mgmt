from __future__ import annotations

import datetime
import logging
import re

from ngts.scripts.pbi.models import TestResult

logger = logging.getLogger(__name__)

_ALLURE_STATUSES = {"passed", "failed", "broken", "skipped", "unknown"}
_LA_TEST_REAL_OUTCOME = re.compile(r"la_failed\(.*outcome=(%s).+" % "|".join(_ALLURE_STATUSES))


# **********************************************************************************************************************
# Parser Helper Functions
# **********************************************************************************************************************
def parse_branch_name(tarball_name: str) -> str:
    if not (match := re.search(r"nvos_ver-\d{2}-\d{2}-\d{4}", tarball_name)):
        match = re.search(r"develop", tarball_name)
    if match:
        return match.group(0)
    return ""


def parse_version(version_file_path: str) -> str:
    version = version_file_path.split("/")[-1].split(".bin")[0]
    marker = "nvos-amd64-"
    if marker in version:
        version = version.split(marker)[1]
    return version


def parse_timestamp(timestamp: str) -> datetime.datetime | None:
    for time_format in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(timestamp, time_format)
        except ValueError:
            continue
    return None


def extract_la_actual_status(tags: list[str]) -> str | None:
    for tag in tags:
        if match := _LA_TEST_REAL_OUTCOME.match(tag):
            logger.info(f"LA actual status: {match.group(1).lower()}")
            return match.group(1).lower()
    return None


def parse_suites(
    node: dict[str, str | list[dict]], base_url: str, suite_chain: list[str], results: list[TestResult]
) -> list[TestResult]:
    current_name = node.get("name", "Unknown")
    new_chain = suite_chain + [current_name]

    for child in node.get("children", []):
        if "status" in child:
            test_uid = child.get("uid", "")
            test_url = f"{base_url}/index.html#testresult/{test_uid}" if test_uid else None

            status = child["status"]
            logger.debug(f"{child['name']:<70} - {status}")
            logger.debug(f"Tags: {child.get('tags', [])}")
            la_actual_status = extract_la_actual_status(child.get("tags", []))
            if la_actual_status == "passed":
                status = "LA_failed"

            results.append(
                TestResult(
                    suite_path=" > ".join(new_chain),
                    test_name=child["name"],
                    status=status,
                    duration=child["time"]["duration"] / 60000,
                    test_url=test_url,
                    test_uid=test_uid,
                )
            )
        else:
            parse_suites(child, base_url, new_chain, results)

    return results
