#!/usr/bin/env python3

"""
Python 3 compatible standalone version of unpack_sysdump.py
This script can unpack sysdump files and combine log files without any external dependencies
from the sx_fit_regression repository.
"""

import os
import sys
import re
import tempfile
import shutil
import tarfile
import gzip
import argparse
import subprocess
import warnings

# Suppress SSL warnings for Redmine connections
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

try:
    from redminelib import Redmine
    from redminelib.exceptions import ResourceNotFoundError
    REDMINE_AVAILABLE = True
except ImportError as e:
    REDMINE_AVAILABLE = False
    Redmine = None
    ResourceNotFoundError = Exception

REDMINE_URL = 'https://redmine-api.mellanox.com'
REDMINE_KEY = '4ad65ee94655687090deec6247b0d897f05443e3'

LOG_FILE_SEQUENCE_ID_IDX = 1


def get_redmine_connection():
    """
    Return a Redmine connection object.
    This requires the python-redmine package to be installed.
    Returns:
        Redmine: Connection object to Redmine API
    """
    if not REDMINE_AVAILABLE:
        print("ERROR: python-redmine package is not installed.")
        print("Please install it using: sudo pip3 install python-redmine")
        sys.exit(1)

    return Redmine(REDMINE_URL, key=REDMINE_KEY, requests={'verify': False})


def download_issue_attachments(issue_num, output_dir):
    """
    Download all attachments from a Redmine issue.
    Args:
        issue_num: Redmine issue number
        output_dir: Directory to save attachments to
    """
    rm = get_redmine_connection()

    try:
        issue = rm.issue.get(int(issue_num))
    except ResourceNotFoundError as err:
        raise Exception("%s, bug %s does not exist in Redmine" % (err, issue_num))

    for attach in issue['attachments']:
        dl = attach['content_url']

        # Use subprocess instead of os.system to prevent command injection
        try:
            subprocess.run(
                ['curl', '--insecure', '-O', '-H',
                 'X-Redmine-API-Key: %s' % REDMINE_KEY, dl],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print("Warning: Failed to download attachment: %s" % e)
            continue

    if issue['attachments']:
        print("\nIssue %d attachments were downloaded to %s" % (issue_num, output_dir))


def get_sysdumps_and_messages_dirs(output_dir):
    """
    Parse directory to find sysdump files and message directories.
    Args:
        output_dir: Directory to search in
    Returns:
        tuple: (list of sysdump paths, list of message directory paths)
    """
    sysdumps = []
    messages_dirs = []
    files = os.listdir("./")

    for file_name in files:
        if file_name.endswith(".tgz"):
            # should match sysdump_10_210_24_156_MSN2700-Panther.tgz / sysdump-tarantula108-20160223-110202.tgz
            # / sysdump-switch-645c6a-20150209-080412.tgz / sysdump-ptr-vcl-02-20160505-144036.tgz
            if re.match(r'^sysdump\S+\.tgz$', file_name):
                sysdumps.append(os.path.abspath(file_name))

            # should match 10_224_13_185_sysdump.tgz
            elif re.match(r'^(\d+|_)+sysdump.tgz$', file_name):
                sysdumps.append(os.path.abspath(file_name))

            # should match 10.224.22.161.tgz
            elif re.match(r'^(\d+|\.)+tgz$', file_name):
                unzipped_dir = file_name.strip(".tgz")
                os.mkdir(unzipped_dir)
                shutil.move(file_name, "%s/%s" % (unzipped_dir, file_name))
                os.chdir(unzipped_dir)

                tar = tarfile.open(file_name)
                tar.extractall()
                tar.close()

                for inner_file in os.listdir('./'):
                    if re.match('^sysdump', inner_file):
                        sysdumps.append(os.path.abspath(inner_file))
                    if re.match('^messages', inner_file):
                        dir_path = os.path.dirname(os.path.realpath(inner_file))
                        if dir_path not in messages_dirs:
                            messages_dirs.append(dir_path)

                # delete original zip file
                os.remove(file_name)
                os.chdir(output_dir)

            else:
                pass

        elif file_name.endswith("tar.gz"):
            # should match SONiC dump files
            sysdumps.append(os.path.abspath(file_name))

    return sysdumps, messages_dirs


def atoi(text):
    """
    Convert text to integer if it's a digit, otherwise return 0.
    """
    if text.isdigit():
        return int(text)
    else:
        return 0


def get_sequence_id(file_name):
    """
    Extract sequence ID from log file name.
    Args:
        file_name: Name of the log file
    Returns:
        int: Sequence ID
    """
    name_parts = re.split(r'(\d+)', file_name)

    if len(name_parts) == 1:
        # handle files without sequence id e.g. 'syslog.gz'.
        # split a string by digit when there is no digit in the string will return list that contains the original string, name_parts will be [syslog.gz]
        sequence_id = 0
    elif len(name_parts) > 1:
        # handle files with sequence id e.g. 'syslog.1.gz', name_parts will be ['syslog.', '1', '.gz']
        sequence_id = atoi(name_parts[LOG_FILE_SEQUENCE_ID_IDX])
    else:
        raise Exception("Failed to parse sequence id of file %s" % (file_name))

    return sequence_id


def combine_messages(messages_dir):
    """
    Combine all log files in a directory into single files per log type.
    Args:
        messages_dir: Directory containing log files
    """
    log_files_prefixes = ['teamd', 'syslog', 'zebra', 'telemetry', 'cron', 'bgpd', 'auth',
                          'swss.rec', 'sairedis.rec', 'responsepublisher', 'messages',
                          'debug', 'web_access_log', 'opensm_infiniband-default']
    os.chdir(messages_dir)

    for prefix in log_files_prefixes:
        log_files_combined = prefix + '_combined.txt'
        log_files = []
        for file_name in os.listdir('./'):
            if file_name.startswith(prefix):
                log_files.append(file_name)
        combine_files(log_files, log_files_combined)


def combine_files(files_to_combine, dst_file):
    """
    Combine multiple files into a single destination file.
    Args:
        files_to_combine: List of files to combine
        dst_file: Destination file path
    """
    if files_to_combine == []:
        return

    dst_fd = open(dst_file, 'a')

    files_to_combine.sort(key=get_sequence_id, reverse=True)

    for file_name in files_to_combine:
        if file_name.endswith(".gz"):
            src_fd = gzip.open(file_name, 'rt')
        else:
            src_fd = open(file_name, 'r')
        for line in src_fd.readlines():
            dst_fd.write(line)
        src_fd.close()

    dst_fd.close()
    print("%s" % (dst_file))


def extract_sysdumps_combine_messages(sysdumps, messages_dirs, output_dir, issue_num=0):
    """
    Extract sysdump files and combine their log files.
    Args:
        sysdumps: List of sysdump file paths
        messages_dirs: List of message directory paths
        output_dir: Output directory
        issue_num: Redmine issue number (optional, default: 0)
    """
    if sysdumps == [] and messages_dirs == []:
        shutil.rmtree(output_dir)
        print("No sysdumps found in Redmine issue %d" % (issue_num))

    for sysdump_path in sysdumps:
        try:
            sysdump_dir = os.path.dirname(os.path.realpath(sysdump_path))
            sysdump_file = os.path.basename(sysdump_path)
            tmp_dir = tempfile.mkdtemp()

            shutil.move(sysdump_path, "%s/%s" % (tmp_dir, sysdump_file))
            os.chdir(tmp_dir)

            # extract sysdump file
            tar = tarfile.open(sysdump_file)
            try:
                # Validate tar members to prevent path traversal attacks
                for member in tar.getmembers():
                    # Check for absolute paths or path traversal attempts
                    if os.path.isabs(member.name) or ".." in member.name:
                        raise Exception("Unsafe tar member detected: %s. Possible path traversal attempt." % member.name)

                # Safe to extract after validation
                tar.extractall()
            except OSError:
                print("\nUnpacking %s requires root permissions. Please rerun with user root or with sudo privilege" % (sysdump_file))
                continue
            finally:
                tar.close()

            # delete original sysdump file
            os.remove(sysdump_file)

            # remove symbolic links
            os.system('find -type l -delete')

            dir_list = os.listdir('./')
            if len(dir_list) > 0:
                unzipped_sysdump = dir_list[0]
                unzipped_sysdump_path = os.path.abspath(unzipped_sysdump)
            else:
                raise Exception("Can not get path to unzipped sysdump")

            # create file messages_combine.txt that contain all messages files
            log_folder = ''
            if 'sonic' in unzipped_sysdump_path:
                log_folder = '/log'

            print("\nThe following files created under: %s/%s%s" % (sysdump_dir, unzipped_sysdump, log_folder))
            combine_messages(unzipped_sysdump_path + log_folder)

            shutil.move(unzipped_sysdump_path, "%s/%s" % (sysdump_dir, unzipped_sysdump))
            os.chdir(output_dir)
            shutil.rmtree(tmp_dir)
        except Exception as error:
            print('Exception received [%s] while trying to handle file [%s]' % (error, sysdump_path))
            continue

    for messages_dir in messages_dirs:
        print("\nThe following files created under %s" % (messages_dir))
        combine_messages(messages_dir)


def create_output_dir(suffix, from_redmine=True):
    """
    Create output directory for unpacked files.
    Args:
        suffix: Suffix for directory name (issue number or sysdump name)
        from_redmine: Whether this is from a Redmine issue
    Returns:
        str: Path to created output directory
    """
    if from_redmine:
        output_dir = "/tmp/redmine_%s_attachments" % (suffix)
    else:
        basename = os.path.basename(suffix)
        sysdump = basename.split('.')[0]
        output_dir = "/tmp/%s/" % (sysdump)

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.mkdir(output_dir)
    return output_dir


def get_args():
    """
    Parse command line arguments.
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Use option --redmine_issue_number to download attachments from "
                    "Redmine issue and extract all sysdump files. For each sysdump, "
                    "combine all log files into a single file.\n"
                    "Use option --sysdump to extract given sysdump file and combine "
                    "all log files into a single file.\n"
                    "Use option --dir to create a single file from all log "
                    "files that exist in the given extracted sysdump (log folder expected).\n",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-r', '--redmine_issue_number', type=int, help='Redmine issue number', required=False)
    parser.add_argument('-s', '--sysdump', type=str, help='Path to sysdump file', required=False)
    parser.add_argument('-d', '--dir', type=str, help='Path to extracted sysdump directory', required=False)

    options = parser.parse_args()
    if not options.redmine_issue_number and not options.dir and not options.sysdump:
        parser.error("One of --redmine_issue_number or --dir or --sysdump must be given")
    return options


if __name__ == '__main__':
    try:
        # parse user arguments
        options = get_args()

        if (options.sysdump is not None):
            # option --sysdump used
            path_to_sysdump = os.path.abspath(options.sysdump)
            output_dir = create_output_dir(path_to_sysdump, from_redmine=False)
            shutil.copy(path_to_sysdump, output_dir)
            os.chdir(output_dir)

            sysdump_file = os.path.basename(path_to_sysdump)
            sysdumps = [os.path.join(output_dir, sysdump_file)]

            # extract sysdump file and create combined log files
            extract_sysdumps_combine_messages(sysdumps, [], output_dir)

        elif (options.dir is not None):
            # option --dir used
            messages_dir = os.path.abspath(options.dir)

            # create combined messages file
            extract_sysdumps_combine_messages([], [messages_dir], [])

        elif (options.redmine_issue_number is not None):
            # option --redmine_issue_number used
            output_dir = create_output_dir(options.redmine_issue_number)
            os.chdir(output_dir)

            # download attachments
            download_issue_attachments(options.redmine_issue_number, output_dir)

            # parse attachments to get path of all sysdumps files and independent folders that hold messages files
            sysdumps, messages_dirs = get_sysdumps_and_messages_dirs(output_dir)

            # extract sysdump files and create combined log files
            extract_sysdumps_combine_messages(sysdumps, messages_dirs, output_dir, options.redmine_issue_number)

    except Exception as e:
        print("%% %s" % e)
        sys.exit(1)
