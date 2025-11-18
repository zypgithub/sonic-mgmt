import logging
import os
import re
import sys
import requests
import argparse
import datetime
from retry import retry
from pathlib import Path
from argparse import ArgumentParser, Namespace

path = os.path.abspath(__file__)
sonic_mgmt_path = path.split('/ngts/')[0]
sys.path.append(sonic_mgmt_path)

from ngts.constants.constants import InfraConst, CliType, DbConstants  # noqa: E402
from infra.tools.sql.connect_to_mssql import ConnectMSSQL
from ngts.nvos_constants.constants_nvos import OperationTimeConsts, TopologyConsts

logger = logging.getLogger(Path(__file__).stem if __name__ == "__main__" else __name__)

_ALLURE_PROJECT_ID_SUFFIX: str = "-session-reports"
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

# Legacy constants for backwards compatibility
ALLURE_DOCKER_SERVICE = 'allure-docker-service'
SUITE_PATH = 'suite_path'
TEST_NAME = 'test_name'
STATUS = 'status'
DURATION = 'duration'
TEST_URL = 'test_url'
PASS_RATE = 'pass_rate'
VERSION = 'version'
EXECUTED = 'executed'
REPORT_URL = 'report_url'
DUT_HWSKU = 'dut_hwsku'
SESSION_ID = 'session_id'
PATH_TO_UPLOAD_URL = '/auto/sw_system_project/NVOS_INFRA/verification_files/'
BRANCH = 'branch'


def get_logger():
    log = logging.getLogger('UploadToPBI')
    log.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log


logger = get_logger()


class Args(Namespace):
    setup_name: str
    session_id: str
    target_version: str
    branch: str
    dut_hwsku: str
    allure_server_addr: str

    @property
    def allure_project_id(self) -> str:
        return self.setup_name.replace('_', '-').lower() + _ALLURE_PROJECT_ID_SUFFIX

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
    parser.add_argument('--target-version', default="", dest='target_version', help='Target version')
    parser.add_argument('--tarball', default="", dest='tarball', help='Tarball')
    parser.add_argument('--dut_hwsku', default="", dest='dut_hwsku', help='Switch Type')

    return parser.parse_args()


def parse_args():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--setup_name', dest='setup_name', help='Setup name')
    parser.add_argument('--session_id', default="", dest='session_id', help='Session id')
    parser.add_argument('--target-version', default="", dest='target_version', help='Target version')
    parser.add_argument('--tarball', default="", dest='tarball', help='Tarball')
    parser.add_argument('--dut_hwsku', default="", dest='dut_hwsku', help='Switch Type')

    return parser.parse_args()


def parse_branch_name(tarball_name):
    res = ""
    match = re.search(r'nvos_ver-\d{2}-\d{2}-\d{4}', tarball_name)
    if not match:
        match = re.search(r'develop', tarball_name)
    if match:
        res = match.group(0)
    return res


def parse_version(version_file_path):
    version = version_file_path.split("/")[-1].split(".bin")[0]
    marker = "nvos-amd64-"
    if marker in version:
        version = version.split(marker)[1]
    return version


@retry(Exception, tries=3, delay=3)
def insert_data_to_pbi_db(setup_name, version, session_id, parsed_results, summary, dut_hwsku, branch):
    if not version:
        return
    try:
        connections_params = DbConstants.CREDENTIALS[CliType.NVUE]
        mssql_connection_obj = ConnectMSSQL(connections_params['server'], connections_params['database'],
                                            connections_params['username'], connections_params['password'])
        mssql_connection_obj.connect_db()
        logger.info("Connection to DB was completed successfully")
        logger.info("Insert results to test_analytics DB")
        values = ""
        for result in parsed_results:
            value = f"('{setup_name}', '{result[SUITE_PATH]}', '{result[TEST_NAME]}', '{result[STATUS]}', '{session_id}', '{datetime.date.today()}', '{dut_hwsku}', '{result['test_url']}', '{branch}', '{version}', '{result[DURATION]}')"
            values = f"{values}, {value}" if values else value

        if values:
            columns = f"({OperationTimeConsts.SETUP_COL}, {SUITE_PATH}, {TEST_NAME}, {STATUS}, {SESSION_ID}, {OperationTimeConsts.DATE_COL}, {DUT_HWSKU}, {REPORT_URL}, {BRANCH}, {VERSION}, {DURATION})"
            query = "INSERT test_analytics {columns} values {values};".format(columns=columns, values=values)
            logger.info("Inserting data to test_analytics table")
            try:
                mssql_connection_obj.query_insert(query)
                logger.info("--------- insert to test_analytics DB table successfully ---------\n")
            except Exception as e:
                print(f"FAILED TO INSERT DATA TO TEST_ANALYTICS, ERROR: {e}")

        logger.info("Insert results to regression_matrix DB")
        values = f"('{setup_name}', '{summary['pass_rate']}', '{version}', '{summary['executed']}', '{session_id}', '{summary['report_url']}', '{datetime.date.today()}', '{dut_hwsku}', '{branch}')"
        columns = f"({OperationTimeConsts.SETUP_COL}, {PASS_RATE}, {VERSION}, {EXECUTED}, {SESSION_ID}, {REPORT_URL}, {OperationTimeConsts.DATE_COL}, {DUT_HWSKU}, {BRANCH})"
        query = "INSERT regression_matrix {columns} values {values};".format(columns=columns, values=values)
        logger.info("Inserting data to regression_matrix table")
        try:
            mssql_connection_obj.query_insert(query)
            logger.info("--------- insert to regression_matrix DB table successfully ---------\n")
        except Exception as e:
            print(f"FAILED TO INSERT DATA TO REGRESSION_MATRIX, ERROR: {e}")

    finally:
        mssql_connection_obj.disconnect_db()


def _extract_la_actual_status(tags: list[str]) -> str | None:
    for tag in tags:
        if match := _LA_TEST_REAL_OUTCOME.match(tag):
            logger.info(f"LA actual status: {match.group(1).lower()}")
            return match.group(1).lower()
    return None


def _fetch_test_case_data(base_url: str, uid: str) -> dict:
    """Fetch a single test-case JSON by uid. Returns {} on failure."""
    if not uid:
        return {}
    test_case_url = f"{base_url}/data/test-cases/{uid}.json"
    try:
        resp = requests.get(test_case_url, timeout=10)
        resp.raise_for_status()
        return resp.json() or {}
    except Exception:
        return {}


def _append_test_result(results: list, suite_chain: list, base_url: str, node: dict):
    """Append a normalized test result, fetching per-test JSON if needed."""
    uid = node.get("uid", "")
    name = node.get("name", "Unknown")
    status = node.get("status")
    duration_ms = None
    time_block = node.get("time") or {}
    if isinstance(time_block, dict):
        duration_ms = time_block.get("duration")

    # Fallback: read from test-case JSON when status/duration are missing in suites
    if status is None or duration_ms is None:
        tc = _fetch_test_case_data(base_url, uid)
        if status is None:
            status = tc.get("status")
        if duration_ms is None:
            time_block = tc.get("time") or {}
            if isinstance(time_block, dict):
                duration_ms = time_block.get("duration")

    # Check for LA actual status from tags
    tags = node.get('tags', [])
    logger.debug(f"Tags: {tags}")
    la_actual_status = _extract_la_actual_status(tags)
    if la_actual_status == "passed":
        status = "LA_failed"

    duration_min = (duration_ms / 60000.0) if isinstance(duration_ms, (int, float)) else 0.0
    test_url = f"{base_url}/index.html#testresult/{uid}" if uid else None

    results.append({
        SUITE_PATH: " > ".join(suite_chain),
        TEST_NAME: name,
        STATUS: status or "unknown",
        DURATION: duration_min,
        TEST_URL: test_url,
    })


def parse_suites(node, base_url, suite_chain=None, results=None):
    """Recursively parse an Allure suites tree, robust to different layouts."""
    if results is None:
        results = []
    if suite_chain is None:
        suite_chain = []

    # Handle top-level list of nodes
    if isinstance(node, list):
        for child in node:
            parse_suites(child, base_url, suite_chain, results)
        return results

    if not isinstance(node, dict):
        return results

    current_name = node.get("name", "Unknown")
    new_chain = suite_chain + [current_name]

    children = node.get("children")
    if isinstance(children, list) and children:
        for child in children:
            grand_children = child.get("children") if isinstance(child, dict) else None
            is_leaf = not grand_children or (isinstance(child, dict) and child.get("type") == "test")
            if is_leaf and isinstance(child, dict):
                _append_test_result(results, new_chain, base_url, child)
            else:
                parse_suites(child, base_url, new_chain, results)
    else:
        if isinstance(node, dict) and "uid" in node:
            _append_test_result(results, suite_chain, base_url, node)

    return results


def summarize_test_run(tests, report_url):
    """
    Summarize pass/fail/skip/etc. based on your rules:
      - pass_rate = passed / (passed + failed + broken + unknown)
      - skip does NOT count in denominator
      - broken, unknown => counted as failed
    Returns a dict with the stats.
    """
    # Counters
    passed = skipped = failed = broken = unknown = 0

    for t in tests:
        status = t["status"]
        if status == "passed":
            passed += 1
        elif status == "skipped":
            skipped += 1
        elif status == "failed":
            failed += 1
        elif status == "broken":
            broken += 1
        else:
            # Treat 'unknown' or anything else as failed
            unknown += 1

    # Combine failed + broken + unknown for the "fail" category
    total_fail = failed + broken + unknown
    # The pass-rate denominator excludes skipped, so it's the total of passed + fail
    total_count_for_pass_rate = passed + total_fail

    pass_rate = (passed / total_count_for_pass_rate) * 100.0 if total_count_for_pass_rate > 0 else 0.0

    logger.info(f"Passed = {passed}")
    logger.info(f"Failed = {failed}")
    logger.info(f"Broken = {broken}")
    logger.info(f"Unknown = {unknown}")
    logger.info(f"Skipped = {skipped}")
    logger.info(f"Pass Rate = {pass_rate}%")
    logger.info(f"Executed = {passed}/{passed + failed} ({broken + unknown + skipped})")

    return {
        "passed": passed,
        "failed": failed,
        "broken": broken,
        "unknown": unknown,
        "skipped": skipped,
        "pass_rate": str(pass_rate) + '%',
        "report_url": report_url,
        "executed": f"{passed}/{passed + failed} ({broken + unknown + skipped})"
    }


def summarize_results_and_upload(report_url, allure_project, session_id, target_version, setup_name, dut_hwsku, branch):
    if TopologyConsts.NVOS.lower() in allure_project.lower():
        try:
            base_url = os.path.dirname(report_url.rstrip('/'))
            logger.debug(f"Base URL: {base_url}")

            # Try common paths for suites data
            suites_data = None
            for suites_path in ("data/suites.json", "widgets/suites.json"):
                try:
                    suites_resp = requests.get(f"{base_url}/{suites_path}", timeout=10)
                    suites_resp.raise_for_status()
                    suites_data = suites_resp.json()
                    break
                except Exception:
                    continue
            if suites_data is None:
                raise Exception("Could not retrieve suites data from Allure report")

            logger.info("Parse run results:")
            parsed_results = parse_suites(suites_data, base_url)

            logger.info("Summarize run's results:")
            summary = summarize_test_run(parsed_results, report_url)

            insert_data_to_pbi_db(setup_name, target_version, session_id, parsed_results, summary, dut_hwsku, branch)
        except Exception as e:
            logger.info(f"Failed with the following issue: {e}")


if __name__ == "__main__":
    args = parse_args()
    allure_server_addr = InfraConst.ALLURE_SERVER_URL
    setup_name = args.setup_name
    session_id = args.session_id
    target_version = parse_version(args.target_version)
    dut_hwsku = args.dut_hwsku
    branch = parse_branch_name(args.tarball)
    allure_project_id = setup_name.replace('_', '-').lower() + "-session-reports"
    allure_server_base_url = '{}/{}'.format(allure_server_addr, ALLURE_DOCKER_SERVICE)

    report_url = ''
    file_path = os.path.join(PATH_TO_UPLOAD_URL, f"{allure_project_id}.txt")
    logger.info(f"File Path: {file_path}")
    with open(file_path, "r") as f:
        report_url = f.read().strip()
    logger.info(f"Retrieved URL: {report_url}")
    os.remove(file_path)

    if report_url:
        summarize_results_and_upload(report_url, allure_project_id, session_id, target_version, setup_name, dut_hwsku, branch)
