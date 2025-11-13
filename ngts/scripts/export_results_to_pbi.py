from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
import dataclasses
import requests
import datetime
import logging
import retry
import sys
import os
import re

FILE_PATH = Path(__file__).resolve()
sonic_mgmt_path = FILE_PATH.parents[len(FILE_PATH.parts) - FILE_PATH.parts.index('ngts') - 1]
sys.path.append(str(sonic_mgmt_path))

from ngts.nvos_constants.constants_nvos import OperationTimeConsts, TopologyConsts  # noqa: E402
from ngts.constants.constants import InfraConst, CliType, DbConstants  # noqa: E402
from infra.tools.sql.connect_to_mssql import ConnectMSSQL  # noqa: E402

logger = logging.getLogger(Path(__file__).stem if __name__ == "__main__" else __name__)

_ALLURE_DOCKER_SERVICE: str = 'allure-docker-service'
_PATH_TO_UPLOAD_URL: Path = Path('/auto/sw_system_project/NVOS_INFRA/verification_files/')
_ALLURE_STATUSES = {"passed", "failed", "broken", "skipped", "unknown"}
_LA_TEST_REAL_OUTCOME = re.compile(r"la_failed\(.*outcome=(%s).+" % "|".join(_ALLURE_STATUSES))
_TEST_ANALYTICS_COLUMNS_QUERY = f"""\
    INSERT test_analytics (
        {OperationTimeConsts.SETUP_COL},
        suite_path,
        test_name,
        status,
        session_id,
        {OperationTimeConsts.DATE_COL},
        dut_hwsku,
        report_url,
        branch,
        version,
        duration
    )
    VALUES {{values}};
"""

_REGRESSION_MATRIX_COLUMNS_QUERY = f"""\
    INSERT regression_matrix (
        {OperationTimeConsts.SETUP_COL},
        pass_rate,
        version,
        executed,
        session_id,
        report_url,
        {OperationTimeConsts.DATE_COL},
        dut_hwsku,
        branch
    )
    VALUES {{values}};
"""


@dataclasses.dataclass
class TestResult:
    suite_path: str
    test_name: str
    status: str
    duration: float
    test_url: str

    def to_db_values(self, setup_name: str, session_id: str, dut_hwsku: str, branch: str, target_version: str) -> str:
        # escape single quotes in the URL for MSSQL
        escaped_url = self.test_url.replace("'", "''") if self.test_url is not None else ""
        return (
            f"('{setup_name}', '{self.suite_path}', '{self.test_name}', '{self.status}', '{session_id}', "
            f"'{datetime.date.today()!s}', '{dut_hwsku}', '{escaped_url}', '{branch}', '{target_version}', "
            f"'{self.duration}')"
        )


@dataclasses.dataclass
class Summary:
    report_url: str
    pass_rate: str = "N/A"
    executed: str = "N/A"
    passed: int = 0
    failed: int = 0
    la_failed: int = 0
    broken: int = 0
    unknown: int = 0
    skipped: int = 0

    def to_db_values(self, setup_name: str, target_version: str, session_id: str, dut_hwsku: str, branch: str) -> str:
        return (
            f"('{setup_name}', '{self.pass_rate}', '{target_version}', '{self.executed}', '{session_id}', "
            f"'{self.report_url}', '{datetime.date.today()!s}', '{dut_hwsku}', '{branch}')"
        )


class Args(Namespace):
    setup_name: str
    session_id: str
    target_version: str
    branch: str
    dut_hwsku: str
    allure_server_addr: str

    @property
    def allure_project_id(self) -> str:
        return self.setup_name.replace('_', '-').lower() + "-session-reports"

    @property
    def allure_server_base_url(self) -> str:
        return f"{self.allure_server_addr}/{_ALLURE_DOCKER_SERVICE}"


def _setup_logger(level: int = logging.DEBUG):
    logging.basicConfig(
        level=level,
        format='[%(asctime)s.%(msecs)03d][%(levelname)-7s][%(name)-22s %(lineno)4d] %(message)s'
    )


def _parse_args() -> Args:
    parser = ArgumentParser(description='Process some integers.')
    parser.set_defaults(
        allure_server_addr=InfraConst.ALLURE_SERVER_URL,
    )
    parser.add_argument('--setup_name', dest='setup_name', help='Setup name')
    parser.add_argument('--session_id', default="", dest='session_id', help='Session id')
    parser.add_argument('--target-version', type=parse_version, default="", dest='target_version', help='Target version')
    parser.add_argument('--tarball', type=parse_branch_name, default="", dest='branch', help='Tarball')
    parser.add_argument('--dut_hwsku', default="", dest='dut_hwsku', help='Switch Type')

    return parser.parse_args(namespace=Args())


def parse_branch_name(tarball_name: str) -> str:
    if not (match := re.search(r'nvos_ver-\d{2}-\d{2}-\d{4}', tarball_name)):
        match = re.search(r'develop', tarball_name)
    if match:
        return match.group(0)
    return ""


def parse_version(version_file_path: str) -> str:
    version = version_file_path.split("/")[-1].split(".bin")[0]
    marker = "nvos-amd64-"
    if marker in version:
        version = version.split(marker)[1]
    return version


@retry.retry(Exception, tries=3, delay=3)
def insert_data_to_pbi_db(args: Args, parsed_results: list[TestResult], summary: Summary) -> None:
    if not args.target_version:
        return

    mssql_connection_obj = None
    try:
        connections_params = DbConstants.CREDENTIALS[CliType.NVUE]
        mssql_connection_obj = ConnectMSSQL(**connections_params)
        mssql_connection_obj.connect_db()
        logger.info("Connection to DB was completed successfully")
        logger.info("Insert results to test_analytics DB")
        values = ""
        for result in parsed_results:
            value = result.to_db_values(args.setup_name, args.session_id, args.dut_hwsku, args.branch, args.target_version)
            values = f"{values}, {value}" if values else value

        if values:
            logger.info("Inserting data to test_analytics table")
            try:
                mssql_connection_obj.query_insert(q := _TEST_ANALYTICS_COLUMNS_QUERY.format(values=values))
                logger.info(f"Query: {q}")
                logger.info("--------- insert to test_analytics DB table successfully ---------\n")
            except Exception as e:
                print(f"FAILED TO INSERT DATA TO TEST_ANALYTICS, ERROR: {e}")

        logger.info("Insert results to regression_matrix DB")
        values = summary.to_db_values(args.setup_name, args.target_version, args.session_id, args.dut_hwsku, args.branch)
        logger.info("Inserting data to regression_matrix table")

        try:
            mssql_connection_obj.query_insert(q := _REGRESSION_MATRIX_COLUMNS_QUERY.format(values=values))
            logger.info(f"Query: {q}")
            logger.info("--------- insert to regression_matrix DB table successfully ---------\n")
        except Exception as e:
            print(f"FAILED TO INSERT DATA TO REGRESSION_MATRIX, ERROR: {e}")

    finally:
        if mssql_connection_obj:
            mssql_connection_obj.disconnect_db()


def _extract_la_actual_status(tags: list[str]) -> str | None:
    for tag in tags:
        if match := _LA_TEST_REAL_OUTCOME.match(tag):
            logger.info(f"LA actual status: {match.group(1).lower()}")
            return match.group(1).lower()
    return None


def parse_suites(node: dict[str, str | list[dict]], base_url: str, suite_chain: list[str], results: list[TestResult]) -> list[TestResult]:

    current_name = node.get("name", "Unknown")
    new_chain = suite_chain + [current_name]

    for child in node.get("children", []):
        # If child has a "status", it's a test node
        if "status" in child:
            test_uid = child.get("uid", "")
            # Build a direct URL for the test
            test_url = f"{base_url}/index.html#testresult/{test_uid}" if test_uid else None

            status = child["status"]
            logger.debug(f"{child['name']:<70} - {status}")
            logger.debug(f"Tags: {child.get('tags', [])}")
            la_actual_status = _extract_la_actual_status(child.get("tags", []))
            if la_actual_status == "passed":
                status = "LA_failed"

            results.append(TestResult(
                suite_path=" > ".join(new_chain),
                test_name=child["name"],
                status=status,
                duration=child["time"]["duration"] / 60000,
                test_url=test_url  # new field
            ))
        else:
            # Otherwise, it’s another suite node—recurse
            parse_suites(child, base_url, new_chain, results)

    return results


def summarize_test_run(tests: list[TestResult], report_url: str) -> Summary:
    """
    Summarize pass/fail/skip/etc. based on your rules:
      - pass_rate = passed / (passed + failed + broken + unknown)
      - skip does NOT count in denominator
      - broken, unknown => counted as failed
    Returns a dict with the stats.
    """
    # Counters
    summary = Summary(report_url=report_url)

    for t in tests:
        status = t.status
        if status == "passed":
            summary.passed += 1
        elif status == "LA_failed":
            summary.la_failed += 1
        elif status == "skipped":
            summary.skipped += 1
        elif status == "failed":
            summary.failed += 1
        elif status == "broken":
            summary.broken += 1
        else:
            # Treat 'unknown' or anything else as failed
            summary.unknown += 1

    # Combine failed + broken + unknown for the "fail" category
    total_fail = summary.failed + summary.la_failed + summary.broken + summary.unknown
    # The pass-rate denominator excludes skipped, so it's the total of passed + fail
    total_count_for_pass_rate = summary.passed + total_fail

    summary.pass_rate = (summary.passed / total_count_for_pass_rate) * 100.0 if total_count_for_pass_rate > 0 else 0.0
    summary.executed = f"{summary.passed}/{summary.passed + summary.failed + summary.la_failed} ({summary.broken + summary.unknown + summary.skipped})"

    logger.info(f"Passed = {summary.passed}")
    logger.info(f"Failed = {summary.failed}")
    logger.info(f"LA Failed = {summary.la_failed}")
    logger.info(f"Broken = {summary.broken}")
    logger.info(f"Unknown = {summary.unknown}")
    logger.info(f"Skipped = {summary.skipped}")
    logger.info(f"Pass Rate = {summary.pass_rate}%")
    logger.info(f"Executed = {summary.executed}")

    return summary


def summarize_results_and_upload(report_url: str, args: Args) -> None:
    if TopologyConsts.NVOS.lower() not in args.allure_project_id.lower():
        logger.info(f"Skipping upload for {args.allure_project_id} because it is not a NVOS project")
        return

    try:
        base_url = os.path.dirname(report_url.rstrip('/'))
        logger.debug(f"Base URL: {base_url}")
        suites_resp = requests.get(f"{base_url}/data/suites.json")
        suites_resp.raise_for_status()
        suites_data = suites_resp.json()

        logger.info("Parse run results:")
        parsed_results = parse_suites(suites_data, base_url, [], [])

        logger.info("Summarize run's results:")
        summary = summarize_test_run(parsed_results, report_url)

        insert_data_to_pbi_db(args, parsed_results, summary)
    except Exception as e:
        logger.error(f"Failed with the following issue: {e}")
        logger.exception(e)


def main():
    args = _parse_args()
    _setup_logger()

    file_path = _PATH_TO_UPLOAD_URL / f"{args.allure_project_id}.txt"
    logger.info(f"File Path: {file_path}")
    if not (report_url := file_path.read_text().strip()):
        file_path.unlink()
        raise ValueError(f"Failed to retrieve report URL from {file_path}")

    logger.info(f"Retrieved URL: {report_url}")
    file_path.unlink()

    summarize_results_and_upload(report_url, args)


if __name__ == "__main__":
    main()
