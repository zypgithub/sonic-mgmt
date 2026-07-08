import tarfile
import logging
import re
import os
import allure
import smtplib
import time
from datetime import datetime
from retry.api import retry_call
from ngts.constants.constants import InfraConst, SonicConst, SanitizerConst
from email.mime.text import MIMEText

logger = logging.getLogger()


def get_asan_apps(topology_obj, cli_obj):
    asan_apps = []
    if not topology_obj.players['dut'].get('is_nvos', False):
        apps_dict = cli_obj.app_ext.parse_app_package_list_dict()
        for app_name in SanitizerConst.ASAN_APPS:
            if app_name in apps_dict.keys():
                version = apps_dict[app_name]['Version']
                if "asan" in version:
                    asan_apps.append(app_name)
    return asan_apps


def get_mail_address():
    """
    :return: the mail address to send the report to.
    """
    cli_type = os.environ.get('CLI_TYPE')
    return SanitizerConst.CLI_TYPE_MAIL[cli_type]


def disable_asan_apps(cli_objects, asan_apps):
    for app_name in asan_apps:
        with allure.step(f'Disable ASAN app: {app_name}'):
            cli_objects.dut.app_ext.disable_app(app_name)
    time.sleep(5)


def check_sanitizer_and_store_dump(dut_engine, dumps_folder, test_name):
    """
    :param dut_engine: ssh engine to DUT
    :param dumps_folder: path to session dump folder
    :param test_name: the name of the test being run
    :return: In case sanitizer found leaks, function will store a dump and call bug handler
    """
    if have_sanitizer_failed(dut_engine):
        logger.warning("SANITIZER FOUND MEMORY LEAKS AFTER REBOOT")
        logger.info(f"sanitizer files were found at {SonicConst.SANITIZER_FOLDER_PATH}")
        sanitizer_dump_path = create_sanitizer_dump(dut_engine, dumps_folder, test_name)
        return sanitizer_dump_path


def have_sanitizer_failed(dut_engine):
    """
    :param dut_engine: ssh engine object
    :return: return True if sanitizer had detected memory leaks
    """
    check_sanitizer_folder_cmd = \
        f"""[ "$(sudo ls -A {SonicConst.SANITIZER_FOLDER_PATH})" ] && echo 'Not Empty' || echo 'Empty'"""
    res = dut_engine.run_cmd(check_sanitizer_folder_cmd)
    return res == 'Not Empty'


def create_sanitizer_dump(dut_engine, dumps_folder, test_name):
    """
    create a dump for all sanitizer files and store it at dumps_folder
    :param dut_engine: ssh engine object
    :param dumps_folder:  dumps folder path
    :param test_name: the name of the test being run
    :return: sanitizer dump file location
    """
    with allure.step('Generating a dump with sanitizer files'):
        now = datetime.now()
        date_time = now.strftime("%m_%d_%Y_%H-%M-%S")
        dut_name = dut_engine.dut_name + "_" if hasattr(dut_engine, 'dut_name') else ''
        sanitizer_dump_filename = f"{dut_name}{test_name}_sanitizer_files_{date_time}.tar.gz".replace("::", "_")
        sanitizer_dump_path = f"/tmp/{sanitizer_dump_filename}"
        add_date_to_files_name(dut_engine)
        dut_engine.run_cmd(f"sudo tar -czvf {sanitizer_dump_path} -C {SonicConst.SANITIZER_FOLDER_PATH} .")
        retry_call(check_dump_was_created, fargs=[dut_engine, sanitizer_dump_path], tries=6,
                   delay=5, logger=logger)
        logger.info(f"Dump was created at: {sanitizer_dump_path}")
    with allure.step(f'Copy dump: {sanitizer_dump_path} to log folder {dumps_folder}'):
        dest_file = dumps_folder + '/dump_' + sanitizer_dump_filename
        logger.info('Copy sanitizer dump {} to dump folder {}'.format(sanitizer_dump_filename, dumps_folder))
        dut_engine.copy_file(source_file=sanitizer_dump_path,
                             dest_file=dest_file,
                             file_system='/',
                             direction='get',
                             overwrite_file=True,
                             verify_file=False)
        os.chmod(dest_file, 0o777)
        logger.warning('SANITIZER DUMP LOCATION: {}'.format(dest_file))
    with allure.step(f'Remove files from {SonicConst.SANITIZER_FOLDER_PATH}'):
        dut_engine.run_cmd(f"sudo rm {SonicConst.SANITIZER_FOLDER_PATH}/*")
    return dest_file


def add_date_to_files_name(dut_engine):
    rename_files_cmd = """for f in *; do
    fn=$(basename "$f")
    mv "$fn" "$(date -r "$f" +"%Y-%m-%d_%H-%M-%S")_$fn"
    done"""
    dut_engine.run_cmd_set(["sudo su", "cd /var/log/asan", rename_files_cmd, "exit"])


def check_dump_was_created(dut_engine, sanitizer_dump_filename):
    find_res = dut_engine.run_cmd(f"find {sanitizer_dump_filename}")
    assert find_res == sanitizer_dump_filename, f"file {sanitizer_dump_filename} was not created yet"


def get_sanitizer_dumps(dumps_folder, dut_name=None):
    sanitizer_dumps_paths = []
    existing_sanitizer_files = check_dump_folder_for_existing_sanitizer_files(dumps_folder)
    for file_name in existing_sanitizer_files:
        if dut_name and dut_name not in file_name:
            continue
        sanitizer_dump_path = os.path.join(dumps_folder, file_name)
        sanitizer_dumps_paths.append(sanitizer_dump_path)
    return sanitizer_dumps_paths


def check_dump_folder_for_existing_sanitizer_files(dumps_folder):
    cmd = f"ls -A {dumps_folder} | grep 'sanitizer_files'"
    files = os.popen(cmd).read()
    files_list = files.split('\n')
    files_list = [file for file in files_list if file]
    return files_list


def aggregate_asan_and_send_mail(mail_address, sanitizer_dump_path, extract_path, setup_name):
    """
    aggregate the asan files from the sanitizer_dump_path - its a tar file.
    extract it to extract_path
    send mail for each daemon with failures , and a summary mail to mail_address
    :param mail_address: mail address to send the mail to
    :param sanitizer_dump_path: the path of the tar file of the asan files
    :param extract_path: path of a directory to extract the file there
    :param setup_name: the setup name
    """
    extract_path = "{}/{}".format(extract_path, "asan")
    logger.info(f"extract files to {extract_path}")
    asan_files_dict = aggregate_asan_files(sanitizer_dump_path, extract_path)
    s = smtplib.SMTP(InfraConst.NVIDIA_MAIL_SERVER)
    try:
        for daemon in asan_files_dict.keys():
            email_contents = organize_email_content('\n\n'.join(asan_files_dict[daemon]),
                                                    f"Sanitizer errors on daemon {daemon}, on setup {setup_name}",
                                                    mail_address)
            logger.info(f"sending mail about daemon {daemon}")
            s.sendmail(SanitizerConst.SENDER_MAIL, email_contents['To'], email_contents.as_string())

        text = f'Sanitizer found errors on daemons: \n' \
            f'{asan_files_dict.keys()}\n' \
            f'You should get mail for each daemon\n' \
            f'All the ASAN files are here:\n' \
            f'{extract_path}\n' \
            f'Tar file:{sanitizer_dump_path}'
        summary_email_contents = organize_email_content(text,
                                                        f"Sanitizer report on setup {setup_name}",
                                                        mail_address)
        s.sendmail(SanitizerConst.SENDER_MAIL, summary_email_contents['To'], summary_email_contents.as_string())
    finally:
        s.quit()


def aggregate_asan_files(sanitizer_dump_path, extract_path):
    """
    aggregate all the asan files that are related to the same daemon and save it in a dictionary
    :param sanitizer_dump_path: the path of the tar file of the asan files
    :param extract_path: path of a directory to extract the file there
    :return:
        asan_files_dict = {
                    'syncd': 'sanitizer error ....',
                    'portsyncd' : 'sanitizer error ....',
                    }
    """
    tar = tarfile.open(sanitizer_dump_path, 'r')
    try:
        tar.extractall(extract_path)
        asan_files_dict = {}
        for file in tar:
            # take just the daemon name from the file name
            # i.e, for file:2022-05-29_07-59-20_syncd-asan.log.17 - daemon name is: syncd
            daemon_name = re.findall(r"([a-z]*)-asan", file.name)
            if daemon_name:
                daemon_name = daemon_name[0]
                file_path = extract_path + file.name.replace('./', '/')
                cmd = f"cat {file_path} "
                lines = f"file: {file_path}"
                lines += os.popen(cmd).read()
                tmp_list = asan_files_dict.get(daemon_name, [])
                tmp_list.append(lines)
                asan_files_dict[daemon_name] = tmp_list
    finally:
        tar.close()
    return asan_files_dict


def organize_email_content(content, subject, mail_address):
    email_contents = MIMEText(content)
    email_contents['Subject'] = subject
    email_contents['To'] = mail_address
    return email_contents
