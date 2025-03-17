#!/usr/bin/env python3
import logging
import traceback
import os
import argparse
import sys
import ruamel.yaml
import json
import copy
import re
path = os.path.abspath(__file__)
sonic_mgmt_path = path.split('/ngts/')[0]
sys.path.append(sonic_mgmt_path)

from infra.tools.redmine.redmine_api import get_issues_status  # noqa F401
from ngts.constants.constants import LinuxConsts  # noqa F401
from ruamel.yaml.emitter import Emitter  # noqa F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

la_skips_relative_path = "../../tests/common/plugins/loganalyzer_dynamic_errors_ignore/dynamic_loganalyzer_ignores.yaml"
test_skips_relative_path = "../../tests/common/plugins/conditional_mark/tests_mark_conditions_nvidia_internal.yaml"
REDMINE_ISSUES_URL = 'https://redmine.mellanox.com/issues/'
STATEMENT_ACTIONS = ['skip', 'xfail']

project_files = {
    "sonic": {
        "tests_skips_path": os.path.join(os.getcwd(), test_skips_relative_path),
        "log_skips_path": os.path.join(os.getcwd(), la_skips_relative_path)
    }
}


def get_issues_from_log_data(log_data, issues_list):
    """
    return: list of redmine issues
    """
    for item in log_data:
        for obj in item["Conditions"]:
            if "Redmine" in obj.keys():
                for ticket in obj["Redmine"]:
                    if int(ticket) not in issues_list:
                        issues_list.append(int(ticket))


def check_for_redmine_link(str):
    """
    return: ticket if str contains a redmine link
    """
    link_start = REDMINE_ISSUES_URL
    pattern = re.compile(fr'{link_start}(\d+)')

    match = pattern.search(str)
    if match:
        ticket = match.group(1)
        return ticket
    return None


def get_issues_from_test_data(test_data, issues_list):
    """
    return: list of redmine issues
    """
    for _, statement in test_data.items():
        conditions = []
        for action in STATEMENT_ACTIONS:
            if action in statement:
                conditions = statement[action].get('conditions', [])
                break
        for elem in conditions:
            ticket = check_for_redmine_link(elem)
            if ticket is not None:
                if int(ticket) not in issues_list:
                    issues_list.append(int(ticket))


def get_closed_issues(issues_list):
    """
    :param issues_list: a list of the issues
    :return: list of closed redmine issues
    """
    problematic_issues = []
    issues_status = {}
    for issue in issues_list:
        try:
            status = get_issues_status([issue])
            issues_status.update(status)
        except json.decoder.JSONDecodeError:
            problematic_issues.append(issue)

    closed_issues = []
    for issue_id, status in issues_status.items():
        if "Closed" in status:
            closed_issues.append(issue_id)

    if problematic_issues:
        logger.warning("problematic issues were found: {}".format(problematic_issues))
    return closed_issues


def remove_closed_issues_from_test_data(test_data, closed_issues):
    """
    :return: test_data without closed redmine issues
    """
    updated_test_data = copy.deepcopy(test_data)
    for script, statement in test_data.items():
        conditions = []
        conditions_logical_operator = None
        statement_action = None
        for action in STATEMENT_ACTIONS:
            if action in statement:
                conditions = statement[action].get('conditions', [])
                conditions_logical_operator = statement[action].get('conditions_logical_operator')
                statement_action = action
                break
        if statement_action is None:
            raise Exception(f'Missing statement action for {script}')

        for elem in conditions:
            ticket = check_for_redmine_link(elem)
            if ticket is not None and str(ticket) in closed_issues:
                if conditions_logical_operator == "or" and len(conditions) > 1:
                    updated_test_data[script][statement_action]["conditions"].remove(elem)
                    updated_test_data[script][statement_action]["reason"] = "Needs to be updated"
                else:
                    try:
                        del updated_test_data[script]
                    except KeyError:
                        continue

    return updated_test_data


def remove_closed_issues_from_log_data(log_data, closed_issues):
    """
    :return: log_data without closed redmine issues
    """
    updated_log_data = copy.deepcopy(log_data)
    for item in log_data:
        for obj in item["Conditions"]:
            if "Redmine" in obj.keys():
                for ticket in obj["Redmine"]:
                    if str(ticket) in closed_issues:
                        updated_log_data.remove(item)
                        break

    return updated_log_data


def remove_redundant_skips(project_key):
    """/
    :return: original paths with updated skips files if changes were made
    """
    try:
        '''load data from yaml file'''

        yaml = ruamel.yaml.YAML(typ='rt')
        yaml.preserve_quotes = True
        yaml.width = 1024
        Emitter.MAX_SIMPLE_KEY_LENGTH = 1024
        issues_list = []
        test_skips_data = None
        log_skips_data = None
        if "tests_skips_path" in project_files[project_key].keys():
            test_skips_abs_path = project_files[project_key]["tests_skips_path"]

            with open(test_skips_abs_path, 'r') as yaml_file:
                test_skips_data = yaml.load(yaml_file)

            get_issues_from_test_data(test_skips_data, issues_list)

        if "log_skips_path" in project_files[project_key].keys():
            la_skips_abs_path = project_files[project_key]["log_skips_path"]

            with open(la_skips_abs_path, 'r') as yaml_file:
                log_skips_data = yaml.load(yaml_file)

            get_issues_from_log_data(log_skips_data, issues_list)

        closed_issues = get_closed_issues(issues_list)

        updated_test_data = None
        if "tests_skips_path" in project_files[project_key].keys():
            updated_test_data = remove_closed_issues_from_test_data(test_skips_data, closed_issues)

        updated_log_data = None
        if "log_skips_path" in project_files[project_key].keys():
            updated_log_data = remove_closed_issues_from_log_data(log_skips_data, closed_issues)

        if updated_test_data == test_skips_data and updated_log_data == log_skips_data:
            logger.info("There are no closed bugs in the files since last run of this script")
        else:

            if "log_skips_path" in project_files[project_key].keys():
                with open(la_skips_abs_path, 'w') as file:
                    yaml.dump(updated_log_data, file)

            if "tests_skips_path" in project_files[project_key].keys():
                with open(test_skips_abs_path, 'w') as file:
                    yaml.dump(updated_test_data, file)

            print("files have changed since the last run and were updated successfully")
            print("Review changes and push to git")
            print("If there are problematic issues, check them and delete if needed")

    except Exception as err:
        raise AssertionError(err)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description="Process a project.")
        parser.add_argument("--project_key", action="store", default="sonic",
                            help="Specify the key of the project to be processed.")

        args = parser.parse_args()
        remove_redundant_skips(args.project_key)
        logger.info('Script Finished!')

    except Exception:
        traceback.print_exc()
        sys.exit(LinuxConsts.error_exit_code)
