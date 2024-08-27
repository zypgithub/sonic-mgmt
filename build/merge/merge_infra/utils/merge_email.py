import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from build.merge.merge_infra.repo.repo_handler import MergeHistory
from build.merge.merge_infra.utils.model import MergeHintEnum

# from infra.tools.sql.constants import SkynetGeneralConstants

FROM = 'sonic-mgmt-daily-merge@nvidia.com'
SMTP_HOST = "mailgw.nvidia.com"
SMTP_HOST_PORT = 25


def read_unmerged_files(root_dir):
    result = {}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        if MergeHistory.unmerged_storage in filenames:
            unmerged_path = os.path.join(dirpath, MergeHistory.unmerged_storage)

            with open(unmerged_path, 'r', encoding='utf-8') as file:
                content = file.read()

            folder_name = os.path.basename(dirpath)
            result[folder_name] = content.split('\n')

    return result


def generate_email(recipients,
                   status,
                   result,
                   unmerged_path,
                   resolved_path,
                   conflict_path,
                   local_branch, remote_branch,
                   start_date,
                   end_date,
                   cr=""):
    """
    Generate email
    """
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Daily merge reports - {datetime.now().strftime("%d/%m")}'
    msg['From'] = FROM
    msg['To'] = recipients

    total_count = len(result)
    success_count = 0

    success_result = []
    failed_result = []
    no_changes = []

    for commit_id, res in result.items():
        if commit_id == 'LAST_TIME_UNMERGED':
            continue
        if res[1].hint is MergeHintEnum.NO_CHANGE:
            no_changes.append(res[1])
        elif res[0] is True:
            success_count += 1
            success_result.append(res[1])
        else:
            failed_result.append(res[1])

    failed_table = []
    for index, hint in enumerate(failed_result):
        pr_id = hint.pr_id if hint.pr_id else ""
        link = "https://github.com/sonic-net/sonic-mgmt/pull/" + hint.pr_id if hint.pr_id else ""
        failed_table.append(f'<tr><td>{str(index + 1)}</td><td><a href="{link}">{pr_id}</a></td><td>{hint.commit_id}</td><td>{hint.content}</td></tr>')

    failed_details = """
    <table style="border-collapse: collapse; width: 100%; height: 36px;" border="1">
    <tbody>
    <tr style="height: 18px; background-color: #777; color: white; font-weight: bold;">
    <th>Index</th>
    <th>GitHub PR</th>
    <th>Commit ID</th>
    <th>Reason</th>
    </tr>
    """ + "\n".join(failed_table) + """
    </table>
    """

    success_table = []
    for index, hint in enumerate(success_result):
        pr_id = hint.pr_id if hint.pr_id else ""
        link = "https://github.com/sonic-net/sonic-mgmt/pull/" + hint.pr_id if hint.pr_id else ""
        success_table.append(f'<tr><td>{str(index + 1)}</td><td><a href="{link}">{pr_id}</a></td><td>{hint.commit_id}</td></tr>')
    success_details = """
    <table style="border-collapse: collapse; width: 100%; height: 36px;" border="1">
    <tbody>
    <tr style="height: 18px; background-color: #777; color: white; font-weight: bold;">
    <th>Index</th>
    <th>GitHub PR</th>
    <th>Commit ID</th>
    </tr>
    """ + "\n".join(success_table) + """
    </tbody>
    </table>
    """

    no_table = []
    for index, hint in enumerate(no_changes):
        pr_id = hint.pr_id if hint.pr_id else ""
        link = "https://github.com/sonic-net/sonic-mgmt/pull/" + hint.pr_id if hint.pr_id else ""
        no_table.append(
            f'<tr><td>{str(index + 1)}</td><td><a href="{link}">{pr_id}</a></td><td>{hint.commit_id}</td></tr>')
    no_details = """
    <table style="border-collapse: collapse; width: 100%; height: 36px;" border="1">
    <tbody>
    <tr style="height: 18px; background-color: #777; color: white; font-weight: bold;">
    <th>Index</th>
    <th>GitHub PR</th>
    <th>Commit ID</th>
    </tr>
    """ + "\n".join(no_table) + """
    </tbody>
    </table>
    """

    email_content = f'''
    <strong>Branch</strong> : {local_branch} <br>
    <strong>Start Date</strong> : {start_date} <br>
    <strong>End Date</strong> : {end_date} <br>
    <strong>Status</strong> : {'Success' if status else 'Failed'} <br>
    <br>
    <strong>MERGED FAILED:</strong><br>
{failed_details}
    '''

    email_content += f'''
    <br>
    <strong>MERGED SUCCESS:</strong><br>
{success_details}
    <br>
    '''

    if len(no_changes) > 0:
        email_content += f'''
        <br>
        <strong>PR already merged when the tool executed</strong>
    {no_details}
        <br>
        '''

    unresolved = read_unmerged_files(MergeHistory.base_path)
    if len(unresolved) > 0:
        unresolved_table = []

        counter = 1
        for i, r in enumerate(unresolved.items()):
            date, ids = r
            for id in ids:
                if len(id) <= 10:
                    continue
                unresolved_table.append(f'<tr><td>{str(counter)}</td><td>{id}</td><td>{date}</td></tr>')
                counter += 1

        unresolved_details = """
            <table style="border-collapse: collapse; width: 100%; height: 36px;" border="1">
            <tbody>
            <tr style="height: 18px; background-color: #777; color: white; font-weight: bold;">
            <th>Index</th>
            <th>Commit ID</th>
            <th>Date</th>
            </tr>
            """ + "\n".join(unresolved_table) + """
            </tbody>
            </table>
            """
        email_content += f'''
        <br>
       <strong>Unresolved Uncommited</strong><br>
        {unresolved_details}
        <br>
        '''

    email_content += f'''
    <strong>More Information</strong><br>
    Unmerged commits saved to: {unmerged_path}<br>
    Merged commits saved to: {resolved_path}<br>
    File with conflicts saved to: {conflict_path}<br>
    <br>
    '''

    if len(cr) > 0:
        email_content += f"Gerrit Top CR: {cr}"
    else:
        email_content += f"No commit is merged."

    text_part = MIMEText(email_content, 'html')
    msg.attach(text_part)

    return msg


def send_report(report, recipients):
    """
    Send merge report
    """
    smtpserver = smtplib.SMTP(SMTP_HOST, SMTP_HOST_PORT)
    smtpserver.sendmail(FROM, recipients, report.as_string())
    smtpserver.quit()
