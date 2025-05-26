import json
import logging
import traceback
import os

from ngts.constants.constants import Sonic_Cache
from infra.tools.redmine.redmine_api import get_issues_active_status, get_issues_status

logger = logging.getLogger(__name__)


def access_redmine_cache(redmine_issues_list, use_active_status=True):
    """
    Try to get issues status from cache first, if not available or missing issues, get from API.

    Args:
        issue_list (list): List of issue IDs to check
        use_active_status (bool): If True, use get_issues_active_status, else use get_issues_status
    returns:
        dict: Dictionary of issue statuses
    """
    # Check if any caller in the stack is from redmine_refresh.py, if yes, return active status
    stack = traceback.extract_stack()
    if any('redmine_refresh.py' in frame.filename for frame in stack):
        return get_issues_active_status(redmine_issues_list)

    missing_issues = []
    try:
        logger.info(f"Reading from cache: {Sonic_Cache.REDMINE_ISSUES_STATUS_CACHE}")
        with open(Sonic_Cache.REDMINE_ISSUES_STATUS_CACHE, "r") as file:
            redmine_cache_issues = json.load(file)
        issues_status_dict = {}
        for issue in redmine_issues_list:
            if str(issue) in redmine_cache_issues.keys():
                issues_status_dict[str(issue)] = redmine_cache_issues[str(issue)]
            else:
                missing_issues.append(issue)
                raise KeyError(f"Issue {issue} not in cache")
    except Exception:
        logger.info(f"Access to cache unsuccessful, missing issues: {missing_issues}")
        if use_active_status:
            issues_status_dict = get_issues_active_status(redmine_issues_list)
        else:
            issues_status_dict = get_issues_status(redmine_issues_list)
    return issues_status_dict
