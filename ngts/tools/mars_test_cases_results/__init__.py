#!/ngts_venv/bin/python

import os
import json
import logging
import re
import subprocess

from datetime import datetime
from ngts.constants.constants import CliType, DbConstants, BugHandlerConst

logger = logging.getLogger()
ALLURE_REPORT_URL = 'allure_report_url'
SESSION_ID = "session_id"
SETUP_NAME = "setup_name"
MARS_KEY_ID = "mars_key_id"
ALLURE_URL = "allure_url"
DUMP_INFO = "dump_info"
TEST_INSERTED_TIME = "test_inserted_time"
NAME = "name"
RESULT = "result"
SKIP_REASON = "skip_reason"
EXCEPTION = "exception"
EXCEPTION_REGEX = "exception_regex"
LA_REDMINE_ISSUES = "log_analyzer_redmine_issues"
SKYNET = "skynet"

SONIC_CI_SETUP_NAME_PATTERNS = r"CI_sonic(?:_simx)?_SPC(?:\d+)?_\d+"
SONIC_SETUP_NAME_PATTERN = rf"sonic_\S+_r-\S+-\S+|sonic_\S+_mtvr-\S+-\S+|sonic_simx_r-\S+-simx-\S+|\
sonic_simx_mtvr-\S+-simx-\S+|{SONIC_CI_SETUP_NAME_PATTERNS}|sonic_air_\S+-\S+"
SONIC_SWITCH_NAME_PATTERN = r"r-\S+|mtvr-\S+|r-\S+-simx-\S+|mtvr-\S+-simx-\S+"
MAC_PATTERN = r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}|[0-9A-Fa-f]{12}"
IPV4_PATTERN = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
IPV6_PATTERN = r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
BRACKETED_NUM_PATTERN = r"\[\s*\d+\.\d+\s*\]"  # match patterns like [123.1234], [ 123.54], [  13.45]

# will match patterns like 2024 Jun 12 21:51:00.718628 with optional UTC at the end
DATE_PATTERN1 = r"[A-Za-z]{3} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?(?: [A-Z]{3})?"
# will match patterns like 2024 Jun 12 21:51:00.718628 ATF with optional UTC at the end
DATE_PATTERN2 = r"\d{4} [A-Za-z]{3} \d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)(?: [A-Z]{3})?"
# will match patterns like Tue Apr 23 23:57:35 UTC 20194
DATE_PATTERN3 = r"\b[A-Za-z]{3} [A-Za-z]{3} \d{2} \d{2}:\d{2}:\d{2}?(?: [A-Z]{3})?(?: \d{4})?\b"
DATE_PATTERN = rf"{DATE_PATTERN1}|{DATE_PATTERN2}|{DATE_PATTERN3}"

HEX_NUM_PATTERN = r"0[xX][0-9a-fA-F]+|\b[0-9a-fA-F]*[0-9][0-9a-fA-F]*\b"
DIGIT_PATTERN = r"\d+"
QUOTE_PATTERN = r'"'

REDACTED_SONIC_SETUP_NAME = "REDACTED_SONIC_SETUP_NAME"
REDACTED_SONIC_SWITCH_NAME = "REDACTED_SONIC_SWITCH_NAME"
REDACTED_MAC = "REDACTED_MAC"
REDACTED_IP = "REDACTED_IP"
REDACTED_BRACKETED_NUM = "REDACTED_BRACKETED_NUM"
REDACTED_DATE = "REDACTED_DATE"
HEX_NUM_REPLACEMENT = "*"
DIGIT_REPLACEMENT = "*"
ESCAPED_QUOTE_REPLACEMENT = r'\"'
# The patterns are ordered so regex replacements are done correctly (i.e., replace full ip before digits)
GENERALIZE_EXCEPTION_TUPLES = [(SONIC_SETUP_NAME_PATTERN, REDACTED_SONIC_SETUP_NAME),
                               (SONIC_SWITCH_NAME_PATTERN, REDACTED_SONIC_SWITCH_NAME), (MAC_PATTERN, REDACTED_MAC),
                               (IPV4_PATTERN, REDACTED_IP), (IPV6_PATTERN, REDACTED_IP),
                               (BRACKETED_NUM_PATTERN, REDACTED_BRACKETED_NUM), (DATE_PATTERN, REDACTED_DATE),
                               (HEX_NUM_PATTERN, HEX_NUM_REPLACEMENT), (DIGIT_PATTERN, DIGIT_REPLACEMENT),
                               (QUOTE_PATTERN, ESCAPED_QUOTE_REPLACEMENT)]


def pytest_addoption(parser):
    parser.addoption("--disable_exporting_results_to_mars_db", action="store_true", default=False,
                     help="Disable exporting cases results to MARS SQL database")


def create_metadata_dir(session_id, cli_type):
    """
    Create directory for test artifacts in shared location
    :param setup_name: name of the setup
    :param session_id: MARS session id
    :param suffix_path_name: End part of the directory name
    :param cli_type: the type of cli, whether its NVUE or SONIC
    :return: created directory path
    """

    folder_path = DbConstants.CLI_TYPE_PATH_MAPPING.get(cli_type)
    folder_path = os.path.join(folder_path, session_id)
    logger.info("Create folder: {} if it doesn't exist".format(folder_path))
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    logger.info("Created folder - {}".format(folder_path))
    return folder_path


def create_test_record(session_id, setup_name, mars_key_id, test_name, result, skipreason, exception, exception_regex,
                       la_redmine_issues, allure_url, dump_info, test_inserted_time):
    test_record = {}
    test_record.update({SESSION_ID: session_id})
    test_record.update({SETUP_NAME: setup_name})
    test_record.update({MARS_KEY_ID: mars_key_id})
    test_record.update({NAME: test_name})
    test_record.update({RESULT: result})
    test_record.update({SKIP_REASON: skipreason})
    test_record.update({EXCEPTION: exception})
    test_record.update({EXCEPTION_REGEX: exception_regex})
    test_record.update({LA_REDMINE_ISSUES: la_redmine_issues})
    test_record.update({ALLURE_URL: allure_url})
    test_record.update({DUMP_INFO: dump_info})
    test_record.update({TEST_INSERTED_TIME: test_inserted_time})
    return test_record


def pytest_sessionfinish(session, exitstatus):
    """
    Pytest hook which are executed after all tests before exist from program
    :param session: pytest builtin
    :param exitstatus: pytest builtin
    """
    if not session.config.getoption("--collectonly"):
        session_id = session.config.option.session_id
        mars_key_id = session.config.option.mars_key_id
        session.config.cache.set(SESSION_ID, session_id)
        session.config.cache.set(MARS_KEY_ID, mars_key_id)
        if hasattr(session.config.option, SETUP_NAME):
            session.config.cache.set(SETUP_NAME, session.config.getoption(SETUP_NAME))
        if hasattr(session.config.option, SKYNET):
            session.config.cache.set(SKYNET, session.config.getoption(SKYNET))


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if config.getoption("disable_exporting_results_to_mars_db"):
        logger.info("Export MARS cases result to SQL database is disabled")
        return

    json_obj = []
    report_url = config.cache.get(ALLURE_REPORT_URL, '')
    if report_url is None:
        report_url = ''
    session_id = config.cache.get(SESSION_ID, None)
    setup_name = config.cache.get(SETUP_NAME, '')
    mars_key_id = config.cache.get(MARS_KEY_ID, '')
    skynet = config.cache.get(SKYNET, None)
    la_redmine_issues = config.cache.get(BugHandlerConst.LA_RM_ISSUES_DICT, dict())
    logger.debug(f"la_issues = {la_redmine_issues}")
    cli_type = SKYNET if skynet else config.cache.get('CLI_TYPE', CliType.SONIC)
    if valid_tests_data(session_id, mars_key_id):
        tests_results, tests_skipreason, tests_exceptions = parse_tests_results(terminalreporter)
        for test_case_name, test_result in tests_results.items():
            test_exception, test_exception_regex, test_case_la_issues = update_exception_from_la_error(tests_exceptions,
                                                                                                       test_case_name,
                                                                                                       la_redmine_issues)
            logger.debug("The exception for {} is : {}".format(test_case_name, test_exception))
            logger.debug("The generalized regex for {} is : {}".format(test_case_name, test_exception_regex))
            now = datetime.now()
            test_inserted_time = now.strftime("%m/%d/%Y %H:%M:%S")
            dump_info = prepare_dump_dest_path(test_case_name, session_id)
            json_obj.append(create_test_record(session_id,
                                               setup_name,
                                               mars_key_id,
                                               test_case_name,
                                               test_result,
                                               tests_skipreason[test_case_name],
                                               test_exception,
                                               test_exception_regex,
                                               test_case_la_issues,
                                               report_url,
                                               dump_info,
                                               test_inserted_time))
        logger.debug("Tests results to be exported to SQL DB: {}".format(json_obj))
        dump_json_to_file(json_obj, session_id, mars_key_id, cli_type)
        export_data(session_id, mars_key_id, cli_type)


def dump_json_to_file(json_obj, session_id, mars_key_id, cli_type):
    folder_path = create_metadata_dir(session_id, cli_type)
    json_file_path = os.path.join(folder_path, "{}_mars_sql_data.json".format(mars_key_id))
    logger.info("Dump json test results to file")
    with open(json_file_path, 'w') as f:
        json.dump(json_obj, f)
    logger.info("Result were saved at file: {}".format(json_file_path))


def export_data(session_id, mars_key_id, cli_type):
    export_data_cmd = "/ngts_venv/bin/python /root/mars/workspace/sonic-mgmt/ngts/scripts/export_test_json_to_mars_db.py" \
                      " --session_id={SESSION_ID} --mars_key_id={MARS_KEY_ID} --cli_type={CLI_TYPE} --log-level=INFO " \
        .format(SESSION_ID=session_id, MARS_KEY_ID=mars_key_id, CLI_TYPE=cli_type)
    try:
        logger.info("Exporting json tests data with command:\n{}".format(export_data_cmd))
        subprocess.check_output(export_data_cmd, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.output.decode())
        raise Exception(f"Failed to export data to mars db using the command '{export_data_cmd}', "
                        f"please check the errors in the log for further details")


def valid_tests_data(session_id, mars_key_id):
    """
    This function return true only if the tests run as part of mars regression and have valid mars key id and session id.
    :param session_id: session id, i.e 1234567
    :param mars_key_id: mars key id, i.e 0.1.1.1.1.3.4.5
    :return: True, if all the parameters mention above are not None
    """
    return session_id and mars_key_id


def parse_tests_results(terminalreporter):
    """
    return a dict with the parsed tests name and their results
    :param terminalreporter: a pytest plugin
    :return: a dictionary with all the tests that run and their results
    {'tests/push_build_tests/L2/fdb/test_fdb.py::test_push_gate_fdb': 'passed'}
    """
    tests_results = {}
    tests_skipreason = {}
    tests_exceptions = {}
    stats_keys = ['skipped', 'passed', 'failed', 'error']
    for key in stats_keys:
        for test_obj in terminalreporter.stats.get(key, []):
            exception = ""
            exception_regex = ""
            skipreason = ""
            result = test_obj.outcome
            if key == "skipped":
                result, skipreason = get_skip_type_reason(test_obj)
            if key == "failed" or key == "error":
                exception, exception_regex = get_exception(test_obj)

            tests_results.update({test_obj.nodeid: result})
            tests_skipreason.update({test_obj.nodeid: skipreason})
            tests_exceptions.update({test_obj.nodeid: (exception, exception_regex)})
    return tests_results, tests_skipreason, tests_exceptions


def update_exception_from_la_error(tests_exceptions, test_case_name, la_redmine_issues):
    """
    The function updates the exceptions and LA issues list of the test case according to log analyzer errors
    :param tests_exceptions: a dictionary mapping between test cases to tuples of (exception, exception_regex)
    :param test_case_name: the name of the test case
    :param la_redmine_issues: a dictionary mapping between test cases to tuples of (la_issues_list, la_errors)
    :return: The exception, exception regex and LA issues list of the test case, updated according to the LA errors

    """
    exception_index = 0
    exception_regex_index = 1
    test_case_exception = tests_exceptions[test_case_name][exception_index]
    test_exception_regex = tests_exceptions[test_case_name][exception_regex_index]
    test_case_la_issues = []
    if test_case_name in la_redmine_issues:
        issue_list_index = 0
        la_exception_index = 1
        test_case_la_issues = la_redmine_issues[test_case_name][issue_list_index]
        test_case_la_exception = la_redmine_issues[test_case_name][la_exception_index]
        test_case_la_exception_str = str(test_case_la_exception)
        if test_case_la_exception_str.startswith(BugHandlerConst.BUG_HANDLER_FAILURE_EXCEPTION):
            # If the bug handler failed, we set the regex BugHandlerConst.BUG_HANDLER_FAILURE_EXCEPTION as a
            # unique identifier of the failure
            test_case_exception = str(test_case_la_exception)
            test_exception_regex = BugHandlerConst.BUG_HANDLER_FAILURE_EXCEPTION
        else:
            # If the bug handler didn't fail, test_case_la_exception will be a list of log errors.
            # We go through them separately, cutoff their prefix (until ERR) and turn them to regexes.
            test_exception_error_list = []
            log_error_prefix_pattern = re.compile(r'.*(ERR.*)')
            log_error_without_prefix_ind = 1
            for log_error in test_case_la_exception:
                match = log_error_prefix_pattern.match(log_error)
                log_error_regex = generalize_exception(match.group(log_error_without_prefix_ind))
                test_exception_error_list.append(log_error_regex)
            test_case_exception = test_case_la_exception_str
            test_exception_regex = "Log Analyzer Errors: " + "\n" + str(test_exception_error_list)

    # The SQL db doesn't allow strings with single quotes, so we escape them
    test_case_exception = test_case_exception.replace("'", "''")
    test_exception_regex = test_exception_regex.replace("'", "''")
    return test_case_exception, test_exception_regex, test_case_la_issues


def generalize_exception(error_string):
    """
    @summary: Converts a string to a more generalized form of the string (i.e., remove numbers)
    @param error_string: The string to be converted into a generalized exception
    @return: A more-generalized version of the string, turning different patterns to predefined constants
    """
    for regex_pattern, replacement in GENERALIZE_EXCEPTION_TUPLES:
        error_string = re.sub(regex_pattern, replacement, error_string)
    return error_string


def get_exception(test_obj):
    exception = ""
    exception_regex = ""
    if hasattr(test_obj.longrepr, 'reprcrash') and hasattr(test_obj.longrepr.reprcrash, 'message'):
        exception = test_obj.longrepr.reprcrash.message
        exception_regex = generalize_exception(exception)
    elif hasattr(test_obj.longrepr, 'errorstring'):
        # In some cases like fixture look-up errors, the error is presented in the errorstring variable
        # The first element of the split contains the relevant data
        exception = test_obj.longrepr.errorstring.split('\n', maxsplit=1)[0]
        exception_regex = generalize_exception(exception)

    return exception, exception_regex


def get_skip_type_reason(test_obj):
    skipped_flavors = {
        "skipped_rm": ["https://redmine.mellanox.com"],
        "skipped_github": ["https://github.com"],
        "skipped_branch": ["release"],
        "skipped_platform": ["platform", "asic_type"],
        "skipped_topo": ["topo_name", "topo_type", "test requires topology in Mark"]
    }

    _, _, skipreason = test_obj.longrepr
    logger.debug("The skip reason for {} is : {}".format(test_obj.nodeid, skipreason))
    if skipreason.startswith("Skipped: "):
        skipreason = skipreason[9:].replace("'", "")

    skipped_flavor = get_updated_skipped_type(test_obj.outcome, skipped_flavors, skipreason)
    logger.debug("The skip type for {} is : {}".format(test_obj.nodeid, skipped_flavor))
    return skipped_flavor, str(skipreason)


def get_updated_skipped_type(skipped_type, skipped_flavors, skip_reason):
    """
    Check if it is one of the defined skip flavor based on the skip_reason.
    :param skipped_type: defined skip type
    :param skipped_flavors: the skipped flavor dict.
    :param skip_reason: the skip reason
    :return: skip flavor.
    """
    for skipped_flavor, skipreason_keys in skipped_flavors.items():
        for skipreason_key in skipreason_keys:
            if skipreason_key in skip_reason:
                return skipped_flavor
    return skipped_type


def prepare_dump_dest_path(test_case_full_name, session_id):
    """
    Prepare the dump of failed test.
    For CI and nightly regression the path is different.
        Nightly dump: the dump will be inside tar file of all the mars session.
                    In this case will be provided session tar file path(the tar will be generated at the end of
                    Mars session) and path to test dump inside this tar file.
        CI: the dump file will not compressed to tar file. Providing  the path to dump file
    :param test_case_full_name: test case full name, tests/push_build_tests/system/test_cpu_ram_hdd_usage.py::
                                                        TestCpuRamHddUsage::test_cpu_usage'
    :param session_id: mars session_id
    :return: string with dump info
        Example:
            In case of CI: '/path/to/dump'
            Regular Mars session: 'mars_tar_file: /path/to/tar_file,
                                   dump_path_in_mars_tar_file':'path/to/dump/into/tar_file'
    """
    dump_dest_info = ''
    test_case_name = test_case_full_name.split('::')[-1]
    dump_dest = os.environ.get(test_case_name, None)
    if dump_dest:
        # in CI run, one of parameters is 'LOG_FOLDER' for dump files.
        # this parameter doesn't contain the 'cases_dumps' directory
        if 'cases_dumps' not in dump_dest:
            dump_dest_info = dump_dest
        else:
            tar_path, dump_file_name = dump_dest.split('cases_dumps')
            tar_file = '{}{}.tgz'.format(tar_path, session_id)
            path_in_tar_file = 'cases_dumps{}'.format(dump_file_name)
            dump_dest_info = 'mars_tar_file: {}, dump_path_in_mars_tar_file: {}'.format(tar_file, path_in_tar_file)
    return dump_dest_info
