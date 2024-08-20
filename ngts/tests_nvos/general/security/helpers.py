from typing import List


def add_issue_if(issue_cond, issues: List[str], issue_msg: str):
    if issue_cond:
        issues.append(issue_msg)


def assert_no_issues(header_prefix: str, issues: List[str], err_msg_header: str = ''):
    assert not issues, f'{header_prefix} - {err_msg_header}\nissues found:\n\t* ' + '\n\t* '.join(issues)
