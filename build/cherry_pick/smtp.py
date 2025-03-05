from datetime import datetime, timezone
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re
import os
from logger import logger
from repo import GitCommit

FROM = 'sonic-mgmt-daily-merge@nvidia.com'
SMTP_HOST = "mailgw.nvidia.com"
SMTP_HOST_PORT = 25

from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader(
    os.path.join(os.path.dirname(__file__), 'templates')
))


def format_ts(value: str):
    """format git commit author/committer timestamp to human readable string format"""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    except ValueError:
        return f"invalid timestamp: {value}"

def extract_pr_number(commit_subject:str):
    return re.findall(r'#(\d+)', commit_subject)

env.filters['format_ts'] = format_ts
env.filters['extract_pr_number'] = extract_pr_number

report_template = env.get_template('report.html.j2')

def send_email(recipients: list[str], has_conflict: bool, commits: list[GitCommit], cr_on_top: str,
               branch: str):
    if len(recipients) == 0:
        return
    msg = MIMEMultipart()
    msg['Subject'] = f'Daily merge report for branch {branch} - {datetime.now().strftime("%Y-%m-%d")}'
    msg['From'] = FROM
    msg['To'] = ",".join(recipients)
    html_content = report_template.render(has_conflict=has_conflict, commits=commits, cr_on_top=cr_on_top)
    # logger.debug(f"html content: \n{html_content}")
    text_part = MIMEText(html_content, 'html')
    msg.attach(text_part)
    smtpserver = smtplib.SMTP(SMTP_HOST, SMTP_HOST_PORT)
    send_err = smtpserver.sendmail(FROM, recipients, msg.as_string())
    if send_err:
        logger.error(f"error sending email: {send_err}")
    smtpserver.quit()
