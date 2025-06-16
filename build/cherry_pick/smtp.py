from datetime import datetime, timezone
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re
import os
from logger import logger
from jinja2 import Environment, FileSystemLoader

FROM = 'sonic-mgmt-daily-merge@nvidia.com'
SMTP_HOST = "mailgw.nvidia.com"
SMTP_HOST_PORT = 25

env = Environment(loader=FileSystemLoader(
    os.path.join(os.path.dirname(__file__), 'templates')
))


def format_ts(value: str) -> str:
    """Format git commit author/committer timestamp to human readable string format."""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    except ValueError:
        return f"invalid timestamp: {value}"


def extract_pr_number(commit_subject: str) -> list[str]:
    return re.findall(r'#(\d+)', commit_subject)


def link_pr_in_subject(commit_subject: str, branch: str) -> str:
    base_url = "https://github.com/sonic-net/sonic-mgmt/pull"
    if branch == "202412":
        base_url = "https://github.com/Azure/sonic-mgmt.msft/pull"
    pr_number = extract_pr_number(commit_subject)
    if pr_number:
        return commit_subject.replace(
            f'#{pr_number[-1]}',
            f'<a href="{base_url}/{pr_number[-1]}">'
            f'#{pr_number[-1]}</a>'
        )
    return commit_subject


env.filters['format_ts'] = format_ts
env.filters['extract_pr_number'] = extract_pr_number
env.filters['link_pr_in_subject'] = link_pr_in_subject

report_template = env.get_template('report.html.j2')


def send_email(recipients: list[str], branch: str, **kwargs) -> None:
    """
    Send email notification for cherry pick result.
    Args:
        recipients: list of recipients
        branch: str, branch name
    Args: kwargs can include the below parameters:
        has_conflict: bool, True if there is a conflict
        commits: list of GitCommit that have been tried to cherry pick
        cr_on_top: str, CR link on top
        triggered_by: str, triggered by
        total_commits: int, total number of commits to cherry pick
        exception: Exception, exception if any
    """
    if not recipients:
        return
    msg = MIMEMultipart()
    msg['Subject'] = f'Daily merge report for branch {branch} - {datetime.now().strftime("%Y-%m-%d")}'
    msg['From'] = FROM
    msg['To'] = ",".join(recipients)
    html_content = report_template.render(
        kwargs,
        build_url=os.environ.get('BUILD_URL', ''),
        branch=branch,
    )
    # logger.debug(f"html content: \n{html_content}")
    text_part = MIMEText(html_content, 'html')
    msg.attach(text_part)
    smtpserver = smtplib.SMTP(SMTP_HOST, SMTP_HOST_PORT)
    send_err = smtpserver.sendmail(FROM, recipients, msg.as_string())
    if send_err:
        logger.error(f"error sending email: {send_err}")
    smtpserver.quit()
