from infra.tools.redmine.redmine_api import is_redmine_issue_active


def is_bug_active(bug_id) -> bool:
    """
    check whether a single bug in redmine is active or not
    """
    issue_active_res = is_redmine_issue_active([bug_id])
    return bool(issue_active_res and issue_active_res[0])
