import logging
import os
import re
import sys
import requests
import argparse
import datetime
from retry import retry

path = os.path.abspath(__file__)
sonic_mgmt_path = path.split('/ngts/')[0]
sys.path.append(sonic_mgmt_path)

from ngts.constants.constants import InfraConst, CliType, DbConstants  # noqa: E402
from infra.tools.sql.connect_to_mssql import ConnectMSSQL
from ngts.nvos_constants.constants_nvos import OperationTimeConsts, TopologyConsts

ALLURE_DOCKER_SERVICE = 'allure-docker-service'
SUITE_PATH = 'suite_path'
TEST_NAME = 'test_name'
STATUS = 'status'
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
            value = f"('{setup_name}', '{result[SUITE_PATH]}', '{result[TEST_NAME]}', '{result[STATUS]}', '{session_id}', '{datetime.date.today()}', '{dut_hwsku}', '{result['test_url']}', '{branch}', '{version}')"
            values = f"{values}, {value}" if values else value

        if values:
            columns = f"({OperationTimeConsts.SETUP_COL}, {SUITE_PATH}, {TEST_NAME}, {STATUS}, {SESSION_ID}, {OperationTimeConsts.DATE_COL}, {DUT_HWSKU}, {REPORT_URL}, {BRANCH}, {VERSION})"
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


def parse_suites(node, base_url, suite_chain=[], results=[]):

    current_name = node.get("name", "Unknown")
    new_chain = suite_chain + [current_name]

    for child in node.get("children", []):
        # If child has a "status", it's a test node
        if "status" in child:
            test_uid = child.get("uid", "")
            # Build a direct URL for the test
            test_url = f"{base_url}/index.html#testresult/{test_uid}" if test_uid else None

            results.append({
                SUITE_PATH: " > ".join(new_chain),
                TEST_NAME: child["name"],
                STATUS: child["status"],
                TEST_URL: test_url  # new field
            })
        else:
            # Otherwise, it’s another suite node—recurse
            parse_suites(child, base_url, new_chain, results)

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
            suites_resp = requests.get(f"{base_url}/data/suites.json")
            suites_resp.raise_for_status()
            suites_data = suites_resp.json()

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
