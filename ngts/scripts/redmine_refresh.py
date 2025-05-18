#!/usr/bin/env python3
import json
import os
import pytest
import yaml
import glob
import logging
import re
import os
import sys
import subprocess

path = os.path.abspath(__file__)
sonic_mgmt_path = path.split('/ngts/')[0]
sys.path.append(sonic_mgmt_path)
if "/devts" not in sys.path:
    sys.path.append("/devts")

from datetime import datetime, timedelta
from gerrit.base import GerritClient
from ngts.constants.constants import Sonic_Cache, MarsConstants
from infra.tools.redmine.redmine_api import get_issues_active_status
from tests.common.plugins.loganalyzer_dynamic_errors_ignore.la_dynamic_errors_ignore import get_ignore_list, get_redmine_issues_status
from tests.common.plugins.conditional_mark.issue import get_conditions_redmine_issues_status, get_conditions_list
import tests.common.plugins.loganalyzer_dynamic_errors_ignore.la_dynamic_errors_ignore as la_dynamic_errors_ignore_module
import tests.common.plugins.conditional_mark.issue as issue_module

logger = logging.getLogger()


LA_DYNAMIC_LOGANALYZER = "tests/common/plugins/loganalyzer_dynamic_errors_ignore/dynamic_loganalyzer_ignores.yaml"
LA_DYNAMIC_IGNORE_PREFIX = "tests/common/plugins/loganalyzer_dynamic_errors_ignore/"
LA_DYNAMIC_IGNORE_PATH = os.path.join(MarsConstants.SONIC_MGMT_DIR, LA_DYNAMIC_IGNORE_PREFIX)
CONDITIONAL_MARK_PREFIX = "tests/common/plugins/conditional_mark/"
DEFAULT_CONDITIONS_FILE = os.path.join(MarsConstants.SONIC_MGMT_DIR + CONDITIONAL_MARK_PREFIX, "tests_mark_conditions*.yaml")
LA_DYNAMIC_FILES = [
    "tests/common/plugins/loganalyzer_dynamic_errors_ignore/dynamic_loganalyzer_ignores.yaml",
    "tests/common/plugins/loganalyzer_dynamic_errors_ignore/dynamic_loganalyzer_ignores_nvos.yaml"
]
CONDITIONAL_MARK_FILES = [
    "tests_mark_conditions.yaml",
    "tests_mark_conditions_acl.yaml",
    "tests_mark_conditions_cl_internal.yaml",
    "tests_mark_conditions_drop_packets.yaml",
    "tests_mark_conditions_nvidia_internal.yaml",
    "tests_mark_conditions_nvos_internal.yaml",
    "tests_mark_conditions_platform_tests.yaml",
    "tests_mark_conditions_skip_traffic_test.yaml",
]

DAYS_THRESHOLD = 7


def get_all_branches(client):
    """
    Get all branches from gerrit that match develop prefix.
    """
    all_branches = []
    skip = 0
    limit = 50
    branch_pattern = re.compile(r"^develop(-\d{6})?$")
    # pull branches from gerrit in batches of 50
    while True:
        branches = client.projects.get(Sonic_Cache.PROJECT_NAME).branches.list(limit=limit, skip=skip)
        if not branches:
            break
        matching_branches = [b['ref'].replace('refs/heads/', '') for b in branches if branch_pattern.match(b['ref'].replace('refs/heads/', ''))]
        all_branches.extend(matching_branches)
        skip += len(branches)

    return all_branches


def get_active_branches(client, all_branches):
    """
    Get all active develop branches from gerrit.
    """
    active_branches = []
    since_date = (datetime.utcnow() - timedelta(days=DAYS_THRESHOLD)).strftime('%Y-%m-%d')

    for branch_name in all_branches:
        query = f"project:{Sonic_Cache.PROJECT_NAME} branch:{branch_name} after:{since_date}"
        if client.changes.search(query):
            active_branches.append(branch_name)

    return active_branches


def redmine_issues_per_branch(client, branch):
    """
    Overwrite the existing LA files in sonic-mgmt with the latest version from the branch.
    Return the redmine issues status dict for the branch.
    """
    project = client.projects.get(Sonic_Cache.PROJECT_NAME)
    branch_obj = project.branches.get(branch)
    for la_file in LA_DYNAMIC_FILES:
        try:
            la_content = branch_obj.get_file_content(la_file, decode=True)
            la_local_path = os.path.join(MarsConstants.SONIC_MGMT_DIR, la_file)
            with open(la_local_path, "w") as f:
                yaml.dump(yaml.safe_load(la_content), f)
        except Exception as e:
            logger.error(f"Skipped missing or invalid file {la_file} in branch {branch}: {e}")
    la_issues_active_status_dict = la_dynamic_errors_ignore_module.get_redmine_issues_status()
    return la_issues_active_status_dict


def conditions_per_branch(client, branch):
    """
    Overwrite the existing conditions files in sonic-mgmt with the latest version from the branch.
    Return the conditional mark dict for the branch.
    """
    project = client.projects.get(Sonic_Cache.PROJECT_NAME)
    branch_obj = project.branches.get(branch)
    for file_path in CONDITIONAL_MARK_FILES:
        try:
            file_content = branch_obj.get_file_content(CONDITIONAL_MARK_PREFIX + file_path, decode=True)
            local_path = os.path.join(MarsConstants.SONIC_MGMT_DIR + CONDITIONAL_MARK_PREFIX, file_path)
            with open(local_path, "w") as f:
                yaml.dump(yaml.safe_load(file_content), f)
        except Exception as e:
            logger.error(f"Skipped missing or invalid file {file_path} in branch {branch}: {e}")
    conditional_mark_dict = issue_module.get_conditions_redmine_issues_status()
    return conditional_mark_dict


def generate_redmine_cache():
    """
    Generate the JSON file containing the redmine issues status for all active branches.
    """
    username = Sonic_Cache.gerrit_username
    token = Sonic_Cache.gerrit_api_token
    client = GerritClient(base_url=Sonic_Cache.GERRIT_API_URL, username=username, password=token)
    all_branches = get_all_branches(client)
    active_branches = get_active_branches(client, all_branches)
    la_dynamic_errors_ignore_module.get_ignore_list = get_ignore_list.__wrapped__
    issue_module.get_conditions_list = get_conditions_list.__wrapped__
    la_dynamic_errors_ignore_module.get_redmine_issues_status = get_redmine_issues_status.__wrapped__
    issue_module.get_conditions_redmine_issues_status = get_conditions_redmine_issues_status.__wrapped__
    combined_issues_status = {}
    for branch in active_branches:
        la_issues_active_status_dict = redmine_issues_per_branch(client, branch)
        conditional_mark_dict = conditions_per_branch(client, branch)
        branch_redmine_issues = merge_dicts(la_issues_active_status_dict, conditional_mark_dict)
        combined_issues_status.update(branch_redmine_issues)

    with open(Sonic_Cache.REDMINE_ISSUES_STATUS_CACHE, "w") as f:
        logger.info("Writing redmine_issues.json...")
        json.dump(combined_issues_status, f, indent=2)

    return combined_issues_status


def merge_dicts(dict1, dict2):
    return {**dict1, **{k: v for k, v in dict2.items() if k not in dict1}}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    try:
        # Run the main test function
        result = generate_redmine_cache()
        logger.info("Successfully generated Redmine cache")
        logger.info(f"Number of issues processed: {len(result)}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to generate Redmine cache: {str(e)}", exc_info=True)
        sys.exit(1)
