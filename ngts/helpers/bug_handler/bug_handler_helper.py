import os
import re
import subprocess
import yaml
import json
import logging
import allure
import math
import pathlib

from retry.api import retry
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timedelta
from ngts.constants.constants import BugHandlerConst, InfraConst
from ngts.nvos_constants.constants_nvos import SystemConsts


TIMESTAMP_FORMATS = ["%b %d %H:%M:%S", "%Y %b %d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]
TIMESTAMP_LENGTH = [len(datetime.now().strftime(format)) for format in TIMESTAMP_FORMATS]

logger = logging.getLogger()


def handle_sanitizer_dumps(dump_paths, cli_type, branch, version, setup_name, topology_obj):
    """
    Call bug handler on all sanitizer files in each dump in dump_paths,
    and return list with results
    :param dump_paths: a list of sanitizer dumps paths which were created during the session
    :param cli_type: i.e, Sonic
    :param branch: i.e 202211
    :param version: i.e, SONiC-OS-202211_RC15.1-7ceec30cc_Internal
    :param setup_name: i.e, sonic_lionfish_r-lionfish-14
    :return: A list of dictionaries with results for each dump
    i.e., [{'dump_name': 'dump_test_lags_scale_sanitizer_files_06_21_2022_23_27_04.tar.gz',
    'test_name': 'test_lags_scale',
    'results':
    [{'file_name': '2022-06-21_23-24-07_orchagent-asan.log.40',
    'messages': ['INFO:handle_bug:reading configuration from', ...],
    'rc': 0,
    'decision': 'update'},...]
    },...]
    """
    bug_handler_dumps_results = []
    session_id = os.environ.get(InfraConst.ENV_SESSION_ID)
    create_session_tmp_folder(session_id)
    redmine_project = BugHandlerConst.CLI_TYPE_REDMINE_PROJECT[cli_type]
    conf_path = BugHandlerConst.BUG_HANDLER_CONF_FILE[redmine_project]
    for sanitizer_dump_path in dump_paths:
        with allure.step(f"Run Bug Handler on Sanitizer Dump: {sanitizer_dump_path}"):
            bug_handler_dumps_results.append(handle_sanitizer_dump(conf_path, sanitizer_dump_path, redmine_project,
                                                                   branch, version, setup_name))
    clear_files(session_id)
    return bug_handler_dumps_results


def create_session_tmp_folder(session_id):
    os.system(f"sudo mkdir /tmp/{session_id}")
    os.system(f"sudo chmod 777 /tmp/{session_id}")
    return f"/tmp/{session_id}"


def clear_files(session_id):
    os.system(f"sudo rm -rf /tmp/{session_id}")
    os.system("rm -rf /tmp/parsed_sanitizer_dumps/")


def handle_sanitizer_dump(conf_path, dump_path, redmine_project, branch, version, setup_name):
    """
    Call bug handler with ASAN dump files and send email with results
    :param conf_path: i.e, /tmp/sonic_bug_handler.conf
    :param dump_path: path to sanitizer dump
    :param redmine_project: i.e, SONiC-Design
    :param branch: i.e 202205
    :param version: i.e 202205_sai_integration.2-36792dcfc_Internal
    :param setup_name: i.e, sonic_lionfish_r-lionfish-14
    :return: dictionary with bug handler results for dump, i.e,
    {'dump_name': 'dump_test_lags_scale_sanitizer_files_06_21_2022_23_27_04.tar.gz',
    'test_name': 'test_lags_scale',
    'results':
    [{'file_name': '2022-06-21_23-24-07_orchagent-asan.log.40',
    'messages': ['INFO:handle_bug:reading configuration from', ...],
    'rc': 0,
    'decision': 'update'},...]
    }
    """
    bug_handler_dump_result = dict()
    bug_handler_dump_result["dump_name"] = Path(dump_path).name
    bug_handler_dump_result["test_name"] = get_test_name_from_sanitizer_dump(bug_handler_dump_result["dump_name"])
    bug_handler_dump_result["results"] = list()
    yaml_parsed_files_dict = parse_sanitizer_dump(dump_path, redmine_project, version, setup_name)
    for sanitizer_file_name, yaml_parsed_file in yaml_parsed_files_dict.items():
        with allure.step(f"Run Bug Handler on sanitizer file: {sanitizer_file_name}"):
            bug_handler_dump_result["results"].append(bug_handler_wrapper(conf_path,
                                                                          redmine_project, branch, sanitizer_file_name,
                                                                          yaml_parsed_file,
                                                                          BugHandlerConst.BUG_HANDLER_SANITIZER_USER,
                                                                          BugHandlerConst.BUG_HANDLER_SCRIPT))
    return bug_handler_dump_result


def get_test_name_from_sanitizer_dump(dump_name):
    regex = r"dump_(.*)_sanitizer_files_.*\.tar\.gz"
    return re.search(regex, dump_name).group(1)


def parse_sanitizer_dump(dump_path, project, version, setup_name):
    """
    :param dump_path: path to sanitizer dump
    :param project: i.e SONiC-Design
    :param version: i.e 202205_sai_integration.2-36792dcfc_Internal
    :param setup_name: i.e, sonic_lionfish_r-lionfish-14
    :return: a dictionary with parsed dump files paths for bug handler
    i.e, {'2022-06-21_23-24-07_orchagent-asan.log.40':
    '/tmp/parsed_sanitizer_dumps/dump_..._extracted/yaml_parsed_files/2022-06-21_23-24-07_orchagent-asan.log.40.yaml',
    ...}
    """
    yaml_parsed_files_dict = {}
    dump_base_dir, dump_file_name = os.path.split(dump_path)
    extracted_dump_dir = os.path.join(BugHandlerConst.SANITIZER_PARSED_DUMPS_FOLDER, f"{dump_file_name}_extracted")
    logger.info("Create folder: {} if it doesn't exist".format(extracted_dump_dir))
    Path(extracted_dump_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Created folder - {}".format(extracted_dump_dir))
    with allure.step("Parse sanitizer dump contents"):
        os.system(f"tar -xzvf {dump_path} -C {extracted_dump_dir}")
        for filename in os.listdir(extracted_dump_dir):
            file_path = os.path.join(extracted_dump_dir, filename)
            if os.path.isfile(file_path):
                with allure.step(f"Parse sanitizer dump file: {filename}"):
                    yaml_file_path = parse_sanitizer_file(file_path, dump_path, project, version, setup_name)
                    yaml_parsed_files_dict.update({filename: yaml_file_path})
    return yaml_parsed_files_dict


def parse_sanitizer_file(file_path, dump_path, project, version, setup_name):
    """
    The function will create a YAML file in the needed format for bug handler script
    :param file_path: path to sanitizer file
    :param dump_path: path to sanitizer dump
    :param project: i.e SONiC-Design
    :param version: i.e 202205_sai_integration.2-36792dcfc_Internal
    :param setup_name: i.e, sonic_lionfish_r-lionfish-14
    :return: path to parsed YAML file
    """
    file_base_dir, file_name = os.path.split(file_path)
    yaml_file_dir = os.path.join(file_base_dir, "yaml_parsed_files")
    yaml_file_path = os.path.join(file_base_dir, "yaml_parsed_files", f"{file_name}.yaml")
    Path(yaml_file_dir).mkdir(parents=True, exist_ok=True)
    contents = Path(file_path).read_text()
    contents_without_prefix = remove_error_prefix_from_sanitizer_file(contents)
    yaml_content_as_dict = {'description': contents_without_prefix,
                            'project': project,
                            'uploads': [file_path, dump_path],
                            'detected_in_version': version,
                            'session_id': os.environ.get(InfraConst.ENV_SESSION_ID),
                            'setup_name': setup_name,
                            'test_name': get_test_name_from_sanitizer_dump(dump_path),
                            'system_type': os.environ.get('CLI_TYPE')}
    yaml_content = yaml.dump(yaml_content_as_dict)
    with open(yaml_file_path, "a") as file:
        file.write(yaml_content)
    return yaml_file_path


def remove_error_prefix_from_sanitizer_file(contents):
    error_prefix_regex = r"(.*\n*=+\n*=+\d+=*ERROR:\s+)"
    error_prefix = re.search(error_prefix_regex, contents, re.IGNORECASE).group(1)
    contents_without_prefix = contents.replace(error_prefix, "")
    return contents_without_prefix


def bug_handler_wrapper(conf_path, redmine_project, branch, upload_file_path, yaml_parsed_file, user, bug_handler_path):
    """
    call bug handler on sanitizer or log analyzer file and return results as dictionary
    :param conf_path: i.e, /tmp/sonic_bug_handler.conf
    :param redmine_project: i.e SONiC-Design
    :param branch: i.e 202205
    :param upload_file_path: i.e, 2023-04-02_16-35-19_wjhd-asan.log.22
    :param yaml_parsed_file: i.e, 2023-04-02_16-35-19_wjhd-asan.log.22.yaml
    :param user: i.e log_analyzer
    :param bug_handler_path: i.e /auto/sw_tools/Internal/BugHandling/bin/handle_bug.py
    :return: dictionary with bug handler results,
    i.e,
    {'file_name': '2022-06-21_23-24-07_orchagent-asan.log.40',
    'messages': ['INFO:handle_bug:reading configuration from', ...],
    'rc': 0,
    'action': 'update',
    'bug_id': '1122554'}
    """
    bug_handler_file_result = run_bug_handler_tool(conf_path, redmine_project, branch, yaml_parsed_file, user,
                                                   bug_handler_path)

    bug_handler_file_result["file_name"] = upload_file_path
    logger.info(f"Bug Handler RC: {bug_handler_file_result[BugHandlerConst.BUG_HANDLER_RC]}")
    logger.info(f"Bug Handler Status: {bug_handler_file_result[BugHandlerConst.BUG_HANDLER_STATUS]}")
    logger.info(f"Bug Handler Action: {bug_handler_file_result[BugHandlerConst.BUG_HANDLER_ACTION]}")
    return bug_handler_file_result


def run_bug_handler_tool(conf_path, redmine_project, branch, yaml_parsed_file, user, bug_handler_path):

    bug_handler_cmd = f"env LOG_FORMAT_JSON=1 {bug_handler_path} --cfg {conf_path} --project {redmine_project} " \
        f"--user {user} --branch {branch} --debug_level 2 --parsed_data '{yaml_parsed_file}'"

    logger.info(f"Running Bug Handler CMD: {bug_handler_cmd}")
    bug_handler_output = subprocess.run(bug_handler_cmd, shell=True, capture_output=True).stdout
    logger.info(bug_handler_output)
    bug_handler_file_result = json.loads(bug_handler_output)

    return bug_handler_file_result


def bug_handler_wrapper_err_msg(conf_path, redmine_project, branch, yaml_parsed_file, user,
                                bug_handler_path, bug_handler_action={}, bug_handler_params={}):
    """
    call bug handler on sanitizer or log analyzer file and return results as dictionary
    :param conf_path: i.e, /tmp/sonic_bug_handler.conf
    :param redmine_project: i.e SONiC-Design
    :param branch: i.e 202205
    :param yaml_parsed_file: i.e, 2023-04-02_16-35-19_wjhd-asan.log.22.yaml
    :param user: i.e log_analyzer
    :param bug_handler_path: i.e /auto/sw_tools/Internal/BugHandling/bin/handle_bug.py
    :param bug_handler_action: a dictionary that defined the actions for the bughandler
    :param bug_handler_params: a dictionary to define the params of the bughandler
    :return: dictionary with bug handler results,
    i.e,
    {'file_name': '2022-06-21_23-24-07_orchagent-asan.log.40',
    'messages': ['INFO:handle_bug:reading configuration from', ...],
    'rc': 0,
    'action': 'update',
    'bug_id': '1122554'}
    """

    bug_handler_file_result = run_err_msg_bug_handler_tool(conf_path, redmine_project, branch, yaml_parsed_file, user,
                                                           bug_handler_path, bug_handler_action, bug_handler_params)

    logger.info(f"Bug Handler RC: {bug_handler_file_result[BugHandlerConst.BUG_HANDLER_RC]}")
    logger.info(f"Bug Handler Status: {bug_handler_file_result[BugHandlerConst.BUG_HANDLER_STATUS]}")
    logger.info(f"Bug Handler Action: {bug_handler_file_result[BugHandlerConst.BUG_HANDLER_ACTION]}")
    return bug_handler_file_result


def run_err_msg_bug_handler_tool(conf_path, redmine_project, branch, yaml_parsed_file, user, bug_handler_path,
                                 bug_handler_action={}, bug_handler_params={}):

    bug_handler_create_action = bug_handler_action.get("create", False)
    bug_handler_update_action = bug_handler_action.get("update", False)
    bug_handler_no_action = not bug_handler_create_action and not bug_handler_update_action

    no_action = '--no_action' if bug_handler_no_action else ''

    update_only = not bug_handler_action["create"] and bug_handler_action["update"]
    update_only_mode = '--update_only' if update_only else ''

    bug_handler_cmd = f"env LOG_FORMAT_JSON=1 {bug_handler_path} --cfg {conf_path} --project {redmine_project} " \
        f"--user {user} --branch {branch} --debug_level 2 " \
        f"--parsed_data '{yaml_parsed_file}' {no_action} {update_only_mode}"

    logger.info(f"Running Bug Handler CMD: {bug_handler_cmd}")
    bug_handler_output = subprocess.run(bug_handler_cmd, shell=True, capture_output=True).stdout
    logger.info(bug_handler_output)
    bug_handler_file_result = json.loads(bug_handler_output)
    if is_attachment_needed(bug_handler_file_result, update_only, bug_handler_no_action, yaml_parsed_file):
        ticket_id = get_ticket_id(bug_handler_file_result)
        tar_file_path = get_tech_support_from_switch(bug_handler_params)

        upload_script = BugHandlerConst.BUG_HANDLER_UPLOAD_ATTACHMENT_SCRIPT
        upload_cmd = f"env LOG_FORMAT_JSON=1 {upload_script} --bug_id {ticket_id}  --attachments {tar_file_path}"
        logger.info(f"Running uploading attchment command: {upload_cmd}")
        upload_attachment_output = subprocess.run(upload_cmd, shell=True, capture_output=True).stdout
        logger.info(upload_attachment_output)
        upload_attachment_result = json.loads(upload_attachment_output)
        if "error" in upload_attachment_result:
            logger.error(f"Failed to upload the file: {upload_attachment_result}")
        bug_handler_file_result["file_name"] = tar_file_path
    return bug_handler_file_result


def is_attachment_needed(bug_handler_file_result, update_only, bug_handler_no_action, yaml_parsed_file):
    if (update_only and bug_handler_file_result["action"] == "create") or bug_handler_no_action or \
            bug_handler_file_result["action"] == "skip":
        return False
    else:
        with open(yaml_parsed_file, 'r') as stream:
            data = yaml.safe_load(stream)
            return not data['attachments']


def get_ticket_id(bug_handler_file_result):
    if bug_handler_file_result['action'] == "update":
        msgs = bug_handler_file_result['messages']
        duplicated_reg = r"\[INFO\] found root bug: ([0-9]+) for duplicate bug:"
        for msg in msgs:
            match_res = re.search(duplicated_reg, msg)
            if match_res:
                ticket_id = match_res.group(1)
                bug_handler_file_result['bug_id'] = ticket_id

    return bug_handler_file_result['bug_id']


def get_tech_support_from_switch(bug_handler_params):
    """
    generate tech support from the switch and copy it to player
    :param bug_handler_params: bug_handler_params
    :return: file path
    """
    duthost = bug_handler_params['duthost']
    testbed = bug_handler_params['testbed']
    session_id = bug_handler_params['session_id']
    cli_type = bug_handler_params['cli_type']

    if cli_type == "Sonic":
        tar_file_path_on_switch = _generate_sonic_techsupport(duthost)
    elif cli_type == "NVUE":
        tar_file_path_on_switch = _generate_nvue_techsupport(duthost)
    else:
        raise Exception(f"No such cli_type: {cli_type}")

    tar_file_name = tar_file_path_on_switch.split('/')[-1]
    dumps_folder = os.environ.get(InfraConst.ENV_LOG_FOLDER)
    if not dumps_folder:  # default value is empty string, defined in steps file
        dumps_folder = create_result_dir(testbed, session_id, InfraConst.CASES_DUMPS_DIR)

    tar_file_path = dumps_folder + '/'

    duthost.fetch(src=tar_file_path_on_switch, dest=tar_file_path, flat=True)
    return os.path.join(dumps_folder, tar_file_name)


def create_result_dir(testbed, session_id, suffix_path_name):
    """
    Create directory for test artifacts in shared location
    :param testbed: name of the testbed
    :param session_id: MARS session id
    :param suffix_path_name: End part of the directory name
    :return: created directory path
    """
    folder_path = '/'.join([InfraConst.REGRESSION_SHARED_RESULTS_DIR, testbed, session_id, suffix_path_name])
    logging.info("Create folder: {} if it doesn't exist".format(folder_path))
    pathlib.Path(folder_path).mkdir(parents=True, exist_ok=True)
    logging.info("Created folder - {}".format(folder_path))
    return folder_path


def get_test_duration(duthost):
    """
    Get duration of test case. Init time + test body time + 120 seconds
    :param item: pytest build-in
    :return: integer, test duration
    """
    item = duthost.loganalyzer.request.node
    duration = math.ceil(item.rep_setup.duration) + 120
    if hasattr(item, "rep_call"):
        duration = duration + math.ceil(item.rep_call.duration)
    if hasattr(item, "rep_teardown"):
        duration = duration + math.ceil(item.rep_teardown.duration)
    return duration


@retry(Exception, tries=5, delay=20)
def _generate_sonic_techsupport(duthost):
    duration = get_test_duration(duthost)
    return duthost.shell(f'sudo generate_dump -s \"-{duration} seconds\"')["stdout_lines"][-1]


def _generate_nvue_techsupport(duthost):
    dump_file = duthost.shell('nv action generate system tech-support')["stdout_lines"][-2].split(' ')[-1]
    return SystemConsts.TECHSUPPORT_FILES_PATH + dump_file


def get_recommended_action_for_user(bug_handler_rc, bug_handler_decision, bug_handler_messages):
    recommended_action = "Unknown scenario, please debug bug handler output."
    if bug_handler_decision == BugHandlerConst.BUG_HANDLER_DECISION_UPDATE:
        recommended_action = "Bug handler updated an existing bug, no additional action needed"
    elif bug_handler_decision == BugHandlerConst.BUG_HANDLER_DECISION_CREATE:
        bug_id = get_created_bug_id(bug_handler_messages)
        recommended_action = f"Bug handler had created a new bug for this issue,<br>" \
            f" Please review ticket and update missing info.<br>" \
            f"Bug id: {bug_id}."
    elif bug_handler_decision == BugHandlerConst.BUG_HANDLER_DECISION_ABORT:
        recommended_action = f"Bug handler could not compare signature in sanitizer log.<br>" \
            f"1. If sanitizer log is missing traceback, update sanitizer tool owner.<br>" \
            f"2. If sanitizer log does not missing traceback, <br>" \
            f"update bug handler owner team that bug handler " \
            f"could not parse sanitizer output correctly.<br>" \
            f"3. Open bug manually for this leak, if an open issue does not exist."
    elif bug_handler_decision == BugHandlerConst.BUG_HANDLER_DECISION_REOPEN:
        recommended_action = "Bug handler had changed the status of an existing bug from fixed/closed to assigned." \
                             "<br>Review the bug and alert the bug owner that fix is not working or merged."
    elif bug_handler_rc is not InfraConst.RC_SUCCESS:
        recommended_action = f"Bug handler had failed, please review bug handler output.<br>" \
            f"1. If needed, consult with bug handler owner team about reason for failure.<br>" \
            f"2. Rerun bug handler after fix or review sanitizer leak manually."
    return recommended_action


def get_created_bug_id(bug_handler_messages):
    bug_id = "could not find bug id in bug handler output, please review regex pattern"
    result = re.search(r"\[INFO\] created bug with id=(\d+)", bug_handler_messages)
    if result:
        bug_id = result.group(1)
    return bug_id


def create_summary_html_report(session_id, setup_name, dumps_folder, dumps_info):
    bug_handler_summary_template = get_xml_template('bug_handler_summary_template.j2')
    bug_handler_summary_output = bug_handler_summary_template.render(session_id=session_id,
                                                                     setup_name=setup_name,
                                                                     dumps_folder=dumps_folder,
                                                                     dumps_info=dumps_info)
    bug_handler_summary_path = os.path.join(dumps_folder, f"bug_handler_summary_report_session_{session_id}.html")
    f = open(bug_handler_summary_path, "w+")
    f.write(bug_handler_summary_output)
    f.close()
    return bug_handler_summary_path


def get_xml_template(template_name):
    p = Path(__file__).parent
    file_loader = FileSystemLoader(str(p))
    env = Environment(loader=file_loader)
    env.trim_blocks = True
    env.lstrip_blocks = True
    env.rstrip_blocks = True
    template = env.get_template(template_name)
    return template


def review_bug_handler_results(bug_handler_results):
    for dump_info in bug_handler_results:
        for bug_handler_result in dump_info["results"]:
            if bug_handler_result["action"] not in [BugHandlerConst.BUG_HANDLER_DECISION_UPDATE,
                                                    BugHandlerConst.BUG_HANDLER_DECISION_SKIP]\
                    or bug_handler_result["rc"] != InfraConst.RC_SUCCESS:
                raise AssertionError("Bug handler found undetected issues, please review summary attached to allure")


def get_log_analyzer_yaml_path(test_name, dump_path):
    yaml_file_dir = os.path.join(dump_path, "yaml_parsed_files")
    Path(yaml_file_dir).mkdir(parents=True, exist_ok=True)
    date_time = datetime.now().strftime("%m_%d_%Y_%H-%M-%S-%f")
    file_name = f"{test_name}_log_analyzer_files_{date_time}".replace("::", "_")
    yaml_file_path = os.path.join(yaml_file_dir, f"{file_name}.yaml")
    return yaml_file_path


def create_log_analyzer_yaml_file(log_errors, dump_path, project, test_name, hostname,
                                  bug_info_dictionary, bug_handler_params, bug_handler_dumps_results):
    """
    The function will create a YAML file in the needed format for bug handler script
    :param log_errors: list with log errors
    :param dump_path: path to dumps
    :param project: i.e, NVOS - Design
    :param test_name: name of the test
    :param bug_info_dictionary: a dictionary to save the content that the bug handler script required
    :param bug_handler_params: a dictionary to define the params of the bughandler
    :param hostname: i.e, gorilla-153
    :return: path to parsed YAML file
    """
    tar_file_path = None
    for bug_handler_dumps_result in bug_handler_dumps_results:
        if "file_name" in bug_handler_dumps_result:
            tar_file_path = bug_handler_dumps_result["file_name"]
            break

    yaml_file_path = get_log_analyzer_yaml_path(test_name, dump_path)
    # remove date, time and hostname before creating the regex!

    if re.findall(hostname, log_errors[0]):
        hostname_regex = hostname
        if re.findall(f"{hostname}-{SystemConsts.MGMT2_HOSTNAME}", log_errors[0]):
            hostname_regex = f"{hostname}-{SystemConsts.MGMT2_HOSTNAME}"
    elif re.findall(r"\d sonic ", log_errors[0]):
        hostname_regex = "sonic"
    else:
        hostname_regex = r'\S+'
    bug_title = create_bug_title(hostname_regex, log_errors[0])
    bug_regex = '.*' + error_to_regex(bug_title) + '.*'
    description = f'| \n{bug_title}\n' + '\n'.join(log_errors)
    bug_info_dictionary.update({'search_regex': bug_regex,
                                'bug_title': bug_title,
                                'description': f"{description}",
                                'project': project,
                                'attachments': [tar_file_path] if tar_file_path else None,
                                'session_id': os.environ.get(InfraConst.ENV_SESSION_ID),
                                'test_name': test_name})
    yaml_content = yaml.dump(bug_info_dictionary)
    yaml_content = yaml_content.replace(bug_regex, f"\"{bug_regex}\"")
    logger.info("yaml file content: {}".format(yaml_content))
    with open(yaml_file_path, "w+") as file:
        file.write(yaml_content)

    return yaml_file_path


def create_bug_title(hostname_regex, first_line):
    time_pattern = r'.*\w+\s+\d+\s+\d+:\d+:\d+\.\d+\s+'
    if not re.findall(time_pattern, first_line):
        time_pattern = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+.*'
    log_prefix = time_pattern + hostname_regex + r'\s'
    bug_title = re.sub(log_prefix, '', first_line)
    bug_title = re.sub(r'message repeated \d+ times: \[ (.*?)\]', r'\1', bug_title)
    if len(bug_title) > BugHandlerConst.BUG_TITLE_LIMIT:
        bug_title = bug_title[:BugHandlerConst.BUG_TITLE_LIMIT]
    return bug_title


def error_to_regex(error_string):
    """
    @summary: Converts a (list of) strings to one regular expression.
    @param error_string:    the string(s) to be converted
                            into a regular expression
    @return: A SINGLE regular expression string
    """
    if len(error_string) > BugHandlerConst.BUG_TITLE_LIMIT:
        error_string = error_string[:BugHandlerConst.BUG_TITLE_LIMIT]
    # -- Escapes out of all the meta characters --#
    error_string = re.escape(error_string)
    error_string = error_string.replace("\\", "\\\\")
    # -- Replaces [123.1234], [ 123.1234], [   123.1234] to one regex
    error_string = re.sub(r"\\\\\[(\\\\\s)*\d+\\\\\.\d+\\\\\]", r"\\\\[\\\\s*\\\\d+\\\\.\\\\d+\\\\]", error_string)
    # -- Replaces a white space with the white space regular expression
    error_string = re.sub(r"(\\\s+)+", "\\\\s+", error_string)
    # -- Replaces date time with regular expressions
    error_string = re.sub(r" [A-Za-z]{3} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [A-Z]{3} ",
                          r" [A-Za-z]{3} \\\\d{4}-\\\\d{2}-\\\\d{2} \\\\d{2}:\\\\d{2}:\\\\d{2} [A-Z]{3} ", error_string)
    # -- Replaces a hex number with the hex regular expression
    error_string = re.sub(r"0x[0-9a-fA-F]+", r"0x[\\\\d+a-fA-F]+", error_string)
    error_string = re.sub(r"\b[0-9a-fA-F]{3,}\b", r"[\\\\d+a-fA-F]+", error_string)
    # -- Replaces any remaining digits with the digit regular expression
    error_string = re.sub(r"\d+", r"\\\\d+", error_string)
    error_string = re.sub(r'"', r'\"', error_string)
    return error_string


def group_log_errors_by_timestamp(log_errors):
    """
    Group the log errors by timestamp: new group starts if it is bigger than 5 sec from the first line in the group.
    so we will consider it as different bug.
    :param log_errors: list of log errors
    :return: error_groups, list of lists. each list is the log errors bug that related to a bug.
    """
    error_line_list = [line for line in log_errors.splitlines() if line.strip()]
    error_groups = []   # list of optional bugs, each element here is a list with log errors.
    current_group = []  # single bug log errors
    prev_timestamp = get_timestamp_from_log_line(error_line_list[0])

    for line in error_line_list:
        timestamp = get_timestamp_from_log_line(line)

        if (timestamp - prev_timestamp) > timedelta(seconds=5):
            # close the group and create new one
            error_groups.append(current_group)
            current_group = []
            prev_timestamp = timestamp

        current_group.append(line)

    if current_group:
        error_groups.append(current_group)
    return error_groups


def get_timestamp_from_log_line(line: str) -> datetime:
    result = None
    for format, length in zip(TIMESTAMP_FORMATS, TIMESTAMP_LENGTH):
        try:
            if "%Y" in format:
                result = datetime.strptime(line[:length], format)
            else:
                # If the timestamp doesn't show the year then we need this workaround to make sure it doesn't crash on
                # February 29 because it's an invalid date. We specify 2020 because it was a leap year.
                result = datetime.strptime("2020 " + line[:length], "%Y " + format)
        except ValueError:
            pass
    if not result:
        raise ValueError(f"Failed to parse time stamp of the following log line: {line}")
    return result


def summarize_la_bug_handler(la_bug_handler_result, bug_handler_action):
    """
    summarize the log analyzer bug handler result.
    :param la_bug_handler_result: result from the la bug handler function.
    :return: dictionary
            {
                new_bugs: {<bug_id>: <errors>},
                existing_bugs: {
                                    update_bug: {<bug_id>: <errors>},
                                    skip_update_bug: {<bug_id>: <errors>}
                                }
            }
    """
    no_action_mode = False
    create_and_update_bugs_dict = {BugHandlerConst.BUG_HANDLER_DECISION_CREATE: {},
                                   BugHandlerConst.BUG_HANDLER_DECISION_UPDATE: {},
                                   BugHandlerConst.BUG_HANDLER_DECISION_SKIP: {},
                                   BugHandlerConst.BUG_HANDLER_FAILURE: [],
                                   BugHandlerConst.NO_ACTION_MODE: [],
                                   BugHandlerConst.UPDATE_ONLY: []}
    update_only = not bug_handler_action["create"] and bug_handler_action["update"]

    for bug_handler_result_dict in la_bug_handler_result:
        bug_handler_status = bug_handler_result_dict[BugHandlerConst.BUG_HANDLER_STATUS]
        bug_handler_action = bug_handler_result_dict[BugHandlerConst.BUG_HANDLER_ACTION]
        bug_id = bug_handler_result_dict[BugHandlerConst.BUG_HANDLER_BUG_ID]
        no_action_mode = no_action_mode or bug_handler_status == 'no_action mode'
        if no_action_mode:
            no_action_errs = {
                BugHandlerConst.LA_ERROR: bug_handler_result_dict[BugHandlerConst.LA_ERROR],
                BugHandlerConst.BUG_HANDLER_ACTION: bug_handler_action
            }
            if bug_handler_action == BugHandlerConst.BUG_HANDLER_DECISION_UPDATE:
                no_action_errs[BugHandlerConst.BUG_HANDLER_BUG_ID] = bug_id
            else:
                no_action_errs[BugHandlerConst.BUG_HANDLER_BUG_ID] = ""
            create_and_update_bugs_dict[BugHandlerConst.NO_ACTION_MODE].append(no_action_errs)
        elif update_only and bug_handler_action == BugHandlerConst.BUG_HANDLER_DECISION_CREATE:
            update_only_action_errs = {
                BugHandlerConst.LA_ERROR: bug_handler_result_dict[BugHandlerConst.LA_ERROR],
                BugHandlerConst.BUG_HANDLER_ACTION: bug_handler_action
            }
            create_and_update_bugs_dict[BugHandlerConst.UPDATE_ONLY].append(update_only_action_errs)
        elif bug_handler_action in BugHandlerConst.BUG_HANDLER_SUCCESS_ACTIONS_LIST\
                and bug_handler_result_dict[BugHandlerConst.BUG_HANDLER_STATUS] in ['done', 'no_action mode']:

            create_and_update_bugs_dict[bug_handler_action].update(
                {bug_id: bug_handler_result_dict[BugHandlerConst.LA_ERROR]})
        else:
            create_and_update_bugs_dict[BugHandlerConst.BUG_HANDLER_FAILURE].append(bug_handler_result_dict)

    logger.info(f"-------create_and_update_bugs_dict is : {create_and_update_bugs_dict}-------")
    logger.info(f"-------la_bug_handler_result is : {la_bug_handler_result}-------")

    return create_and_update_bugs_dict
