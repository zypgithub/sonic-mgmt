import argparse
import logging
import math
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Dict

from infra.tools.redmine.redmine_api import REDMINE_STATUS_NAME_ID_MAPPING, get_issues, close_issue
from infra.tools.sql.constants import SkynetGeneralConstants


def send_report(report, recipients):
    """
    Send weekly report
    """
    smtpserver = smtplib.SMTP(SkynetGeneralConstants.SMTP_HOST, SkynetGeneralConstants.SMTP_HOST_PORT)
    smtpserver.sendmail(SkynetGeneralConstants.FROM, recipients, report.as_string())
    smtpserver.quit()


class BugHandlerAutoCloserConst:
    LOGANALYZER_USER_ID = 7680
    REJECTED_FIELD_ID = 46
    ISSUE_NUMBER_PER_BATCH = 10


class AutoClosedRedmineStatus(Enum):
    FIXED = "Fixed"
    REJECTED = "Rejected"

    @staticmethod
    def get_list():
        # Don't return Rejected. Rejected issue should not be `Closed`, but `Closed(Rejected)`
        return [item.value for item in AutoClosedRedmineStatus if item != AutoClosedRedmineStatus.REJECTED]

    @property
    def detail(self):
        issue_closed_reason_mapping = {
            AutoClosedRedmineStatus.FIXED: "Issue has been fixed",
        }
        return issue_closed_reason_mapping[self]

    @property
    def redmine_id(self):
        return REDMINE_STATUS_NAME_ID_MAPPING[self.value]


class AutoClosedRejectedReason(Enum):
    DUPLICATE_ISSUE = "Duplicate issue"
    NOT_REPRODUCED = "Not reproduced"

    @staticmethod
    def get_list():
        return [item.value for item in AutoClosedRejectedReason]

    @property
    def detail(self):
        issue_closed_reason_mapping = {
            AutoClosedRejectedReason.DUPLICATE_ISSUE: "Issue is a duplicate issue.",
            AutoClosedRejectedReason.NOT_REPRODUCED: "Issue is not reproduced.",
        }
        return issue_closed_reason_mapping[self]


def get_rejected_reason(issue: Dict):
    if "custom_fields" not in issue:
        return None
    for field in issue["custom_fields"]:
        if field["id"] == BugHandlerAutoCloserConst.REJECTED_FIELD_ID:
            return field["value"]
    return None


def close_target_issues(issue_ids_reason_mapping, rejected=False):
    success = 0
    result = {}
    for issue_id, reason in issue_ids_reason_mapping.items():
        try:
            msg = f"Successfully closed{' and rejected' if rejected else ''}. Note: {reason}"
            close_issue(issue_id, detail=reason, rejected=rejected)
            success += 1
            result[issue_id] = (True, msg)
        except Exception as e:
            msg = f"Failed to close issue: {issue_id}, {str(e)}"
            logging.error(f"Failed to close issue: {issue_id}, {str(e)}")
            result[issue_id] = (False, msg)

        logging.debug(msg)

    logging.info(f"Issues closed : {success}/{len(issue_ids_reason_mapping)}")
    return result


def get_issues_create_by_bughandler(status_id, project_id):
    def handle_batch_of_issues(issues):
        c_i = {}
        c_a_r = {}
        for issue in issues:
            status_name = issue['status']['name']
            issue_id = issue['id']
            # Judge if issue should be `Closed` or `Closed(Rejected)`
            if status_name in AutoClosedRedmineStatus.get_list():
                c_i[issue_id] = AutoClosedRedmineStatus(status_name).detail
            elif status_name == AutoClosedRedmineStatus.REJECTED.value:
                reason = get_rejected_reason(issue)
                if reason in AutoClosedRejectedReason.get_list():
                    c_a_r[issue_id] = AutoClosedRejectedReason(reason).detail
        return c_i, c_a_r

    _, total_count, _, _ = get_issues(author_id=BugHandlerAutoCloserConst.LOGANALYZER_USER_ID, status_id=status_id,
                                      project_id=project_id, limit=1, )

    closed_issues = {}
    closed_and_rejected_issues = {}

    per_batch = BugHandlerAutoCloserConst.ISSUE_NUMBER_PER_BATCH

    for i in range(math.ceil(total_count / per_batch)):
        logging.debug(f"Getting {i} batch of issues.")

        batch_issues, total_count, _, _ = get_issues(author_id=BugHandlerAutoCloserConst.LOGANALYZER_USER_ID,
                                                     status_id=status_id,
                                                     project_id=project_id,
                                                     offset=i * per_batch,
                                                     limit=per_batch)

        batch_closed_issues, batch_closed_and_rejected_issues = handle_batch_of_issues(batch_issues)
        closed_issues.update(batch_closed_issues)
        closed_and_rejected_issues.update(batch_closed_and_rejected_issues)

    logging.info(f"Closed issues : {','.join(map(str, closed_issues.keys()))}")
    logging.info(f"Closed and Rejected issues : {','.join(map(str, closed_and_rejected_issues.keys()))}")

    return closed_issues, closed_and_rejected_issues


def generate_email(recipients, result):
    """
    Generate email
    """
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Automatically close issue reports - {datetime.now().strftime("%d/%m")}'
    msg['From'] = "issue_reproduce@nvidia.com"
    msg['To'] = recipients

    total_count = len(result)
    success_count = 0

    success_result = {}
    failed_result = {}

    for issue_id, res in result.items():
        if res[0] is True:
            # Successfully closed.
            success_count += 1
            success_result[issue_id] = res[1]
        else:
            failed_result[issue_id] = res[1]

    success_details = "\n".join(
        [f"\t[Success]\tIssue {issue_id}\t{detail}" for issue_id, detail in success_result.items()])
    failed_details = "\n".join(
        [f"\t[Failed]\tIssue {issue_id}\t{detail}" for issue_id, detail in failed_result.items()])

    email_content = f'''
    [This is an automated email.]
    Time : {str(datetime.now())}
    Issues Detected : {total_count}
    Successfully Closed Issues: {success_count}

    Detailed:
{success_details}

{failed_details}
    '''

    text_part = MIMEText(email_content, 'plain')
    msg.attach(text_part)

    return msg


def init_parser():
    description = ('Functionality of the script: \n'
                   'Automatically close issues.\n')

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument('--recipients', nargs='*', default=list(),
                        help='Recipients for report email')

    parser.add_argument('--project_id', default="6219",
                        help='Project ID. Default: 6219')

    args, unknown = parser.parse_known_args()

    if unknown:
        raise Exception("unknown argument(s): {}".format(unknown))

    return args


def main():
    logging.basicConfig(level=logging.DEBUG)
    args = init_parser()
    recipients = args.recipients

    result = {}
    for status in AutoClosedRedmineStatus:
        logging.info(f"Start to handle {status.value} issue.")
        closed_issues, closed_and_rejected_issues = get_issues_create_by_bughandler(status.redmine_id, args.project_id)
        result.update(close_target_issues(closed_issues, rejected=False))
        result.update(close_target_issues(closed_and_rejected_issues, rejected=True))

    if len(recipients) > 0:
        recipients = ", ".join(recipients)
        email = generate_email(recipients, result)
        send_report(email, recipients)


if __name__ == '__main__':
    main()
