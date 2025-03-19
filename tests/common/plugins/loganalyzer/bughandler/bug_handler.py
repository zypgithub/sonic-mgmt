import re
import logging
import json
import os
import time
from optparse import OptionParser 
import argparse
import tarfile
import gzip
import paramiko
import six
import socket
from pathlib import Path
from argparse import RawTextHelpFormatter
from datetime import datetime
from tests.common.plugins.loganalyzer.bug_handler_helper import handle_log_analyzer_errors
from tests.common.plugins.loganalyzer.system_msg_handler import AnsibleLogAnalyzer
from tests.common.plugins.loganalyzer_dynamic_errors_ignore.la_dynamic_errors_ignore import get_ignore_list, get_extended_ignore_list
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
logger = logging.getLogger()
RM_URL = "https://redmine.mellanox.com/issues/"

DEFAULT_MATCH_FILE_LIST = ["loganalyzer_common_match.txt"]
DEFAULT_EXPECT_FILE_LIST = ["loganalyzer_common_expect.txt"]
DEFAULT_IGNORE_FILE_LIST = ["loganalyzer_common_ignore.txt"]

TMP_SYSLOG_FOLDER = "/tmp/syslogs"
TMP_TECHSUPPORT_DUMP = "/tmp/"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(filename)s:%(lineno)d][%(levelname)s]%(message)s",
    datefmt='%H:%M:%S'
)
# set the perscache log level to INFO to prevent log flooding
logging.getLogger('perscache').setLevel(logging.INFO)

def run_bug_handler(action):
    """
    If the run_log_analyzer_bug_handler is True, run this function to handle the err msg detected in the loganalyzer
    """
    system_type = ""
    test_description = ""
    pytest_cmd_args = ""
    detected_in_version = ""
    setup_name = ""
    allure_report_url = ""
    duthost = None
    cli_type = "Sonic"
    branch = "202311"
    test_name = ""
    if action:
        # TODO: need to update to use the action mode to create or update the ticket once we have the setup name, system type information. 
        bug_handler_actions = {
            'create': False,
            'update': False,
            'only_check': True
        }
    else:
        bug_handler_actions = {
            'create': False,
            'update': False,
            'only_check': True
        }
    bug_handler_dict = {'test_description': test_description,
                        'pytest_cmd_args': pytest_cmd_args,
                        'system_type': system_type,
                        'detected_in_version': detected_in_version,
                        'setup_name': setup_name,
                        'report_url': allure_report_url}
    log_analyzer_res = handle_log_analyzer_errors(cli_type,
                                                  branch, test_name, duthost,
                                                  bug_handler_dict, setup_name, bug_handler_actions)
    
    logger.info(f"Bug handler result: {json.dumps(log_analyzer_res, indent=2)}")
    print(f"Bug handler result: {json.dumps(log_analyzer_res, indent=2)}")
    summarize_results(action, log_analyzer_res[0])


def summarize_results(action, log_analyzer_res):
    if action:
         logger.info("Currently the standalone tool does not support to create or update the ticket, run in no action mode")
    # no action mode:
    new_err_msg_list = []
    existing_ticket_err_map = {}
    for item in log_analyzer_res["no action"]:
        if item["action"] == "create":
            new_err_msg_list.extend(item["la_error"])
        elif item["action"] == "update":
            ticket = item["bug_id"]
            if ticket in existing_ticket_err_map:
                existing_ticket_err_map[ticket].extend(item["la_error"])
            else:
                existing_ticket_err_map[ticket] = item["la_error"]
    tickets = list(existing_ticket_err_map.keys())
    print("********************************************************Summary************************************************")
    if len(new_err_msg_list):
        print("New err msg found: ")
        print("\n".join(new_err_msg_list))
    else:
        print("No new err msg found")
    
    if len(tickets):
        print(f"In general {len(tickets)} relevant RM ticket found for the err msgs: {tickets}")
        for k, v in existing_ticket_err_map.items():
            print(f'Ticket {RM_URL}{k} found for the err msgs: \n{"\n".join(v)}')
    else:
        print("No relevant RM ticket found")


def save_matching_errors(result_log_errors):
    """
    save all the log errors in a file on the player.
    :param result_log_errors: list of all the errors we found in the log - result["match_messages"].values()
    """
    if result_log_errors:
        log_errors = ''
        log_errors += ''.join(result_log_errors)
        tmp_folder = "/tmp/loganalyzer/custom"
        os.makedirs(tmp_folder, exist_ok=True)
        cur_time = time.strftime("%d_%m_%Y_%H_%M_%S", time.gmtime())
        marker_prefix = "stand_alone_test"
        cleaned_marker_prefix = re.sub(r'[\\/\'"<>|]', '_', marker_prefix)
        log_errors_file_path = os.path.join(tmp_folder, "log_error_{}_{}.json".format(cleaned_marker_prefix, cur_time))
        logging.info("Log errors will be saved in file: {}".format(log_errors_file_path))
        data = {'log_errors': log_errors}
        with open(log_errors_file_path, "w+") as file:
            json.dump(data, file)

def is_compressed_file(file_path):
    file_name, file_extension = os.path.splitext(file_path)
    compressed_format = ['.tar', '.gz']
    return file_extension in compressed_format
    
def load_dynamic_errmsg(ignore_err_regex_list, regex_file_path):
    item = None
    # In the standalone tool, it will ignore checking the: effected test case, branch, platform, image, take it match all the branch, image, platform and test case name
    if regex_file_path != os.path.dirname(os.path.abspath(__file__)):
        os.environ["DYNAMIC_INGNORE_PATH"] = str(os.path.join(regex_file_path, "loganalyzer_dynamic_errors_ignore"))
    extended_ignore_list = get_extended_ignore_list(item)
    ignore_err_regex_list.extend(ignore_err_regex_list)


def get_ignore_regex(analyzer, options, regex_file_path):
    print("Start to load the ignore regex")
    ignore_file_list = [os.path.join(regex_file_path, f) for f in DEFAULT_IGNORE_FILE_LIST]
    ignore_file_list.extend(options.ignore_err_files)

    print(f"Loading the ignore regex from common ignore file {ignore_file_list}...")
    ignore_messages_regex, messages_regex_i = analyzer.create_msg_regex(ignore_file_list)
    messages_regex_i.extend(options.ignore_err_list)
    
    print(f"Loading the dynamic ignore regex ...")
    load_dynamic_errmsg(messages_regex_i, regex_file_path)

    ignore_messages_regex = re.compile('|'.join(messages_regex_i)) if len(messages_regex_i) else None
    return ignore_messages_regex

def get_log_files(options):
    log_file_list = []
    if options.log_files:
        for log_file in options.log_files:
            if is_compressed_file(log_file):
                print("==============Start to extract the syslog from the compressed file==============")
                log_file_list.extend(get_syslog_from_compressed_file(log_file))
            elif os.path.isfile(log_file):
                log_file_list.append(log_file)
            elif os.path.isdir(log_file):
                # this is path, take all the files under this folder
                for file in os.listdir(log_file):  
                    file_path = os.path.join(log_file, file)  
                    assert not os.path.isdir(file_path), "Internal file should not be a path"
                    log_file_list.append(file_path)  
            else:
                raise(f"The value of the log_files is not correct, please double check: {log_file}")
    elif options.dut:
        print("==============Get the syslog from the dut==============")
        log_file_list = extract_log_from_dut(options)
    else:
        raise("No syslog to analyze, please specify either the log files or the dut name, for the usage of the option please check with -h|--help")
    
    return log_file_list


def extract_log_from_dut(options):
    if not (options.start_marker and options.end_marker):
        raise("End marker and start marker could not be empty")

    dut = options.dut
    username = options.username if options.username else os.getenv("DUT_USERNAME")
    password = options.password if options.password else os.getenv("DUT_PASSWORD")
    ssh_port = options.ssh_port
    sonic = LinuxSshEngine(ip=dut, username=username, password=password, ssh_port=ssh_port)

    timestamp = options.time_stamp_start
    find_syslog_cmd = f"sudo find /var/log -newermt \'{timestamp}\' | grep syslog"
    log_files = sonic.run_cmd(find_syslog_cmd).split('\n')

    os.makedirs(TMP_SYSLOG_FOLDER, exist_ok=True)
    print(f"All syslog files found: {log_files}")
    for log_file in log_files:
        if not log_file:
            continue
        sonic.run_cmd(f"sudo cp {log_file} /tmp/")
        log_file_name = log_file.split("/")[-1]
        tmp_log_file = f"/tmp/{log_file_name}"
        dest_syslog_file = f"{TMP_SYSLOG_FOLDER}/{log_file_name}"
        sonic.run_cmd(f"sudo chmod 777 {tmp_log_file}")
        sonic.copy_file(source_file=tmp_log_file, dest_file=dest_syslog_file, file_system="", direction='get')
    for fname in os.listdir(TMP_SYSLOG_FOLDER):
        if "gz" in fname:
            fname = f"{TMP_SYSLOG_FOLDER}/{fname}"
            tofile = fname.strip('.gz')
            with open(fname, 'rb') as inf, open(tofile, 'w', encoding='utf8') as tof:
                decom_str = gzip.decompress(inf.read()).decode('utf-8')
                tof.write(decom_str)
            os.system(f"rm -rf {fname}")
    return [os.path.join(TMP_SYSLOG_FOLDER, f) for f in os.listdir(TMP_SYSLOG_FOLDER)]

def get_dump_from_dut(options):
    dut = options.dut
    since = options.since
    username = options.username if options.username else os.getenv("DUT_USERNAME")
    password = options.password if  options.password else os.getenv("DUT_PASSWORD")
    if not username or not password:
        raise Exception("The username and password are required for access the dut, you can specify via the options or set the it as an linux env: DUT_USERNAME, DUT_PASSWORD")
    ssh_port = options.ssh_port
    sonic = LinuxSshEngine(ip=dut, username=username, password=password, ssh_port=ssh_port)
    if since:
        cmd = f'sudo generate_dump -s \"-{since} seconds\"'
    else:
        cmd = "show techsupport"
    print(f"==============Start to run techsupport on DUT: {cmd}")
    output_lines = sonic.run_cmd(cmd).split('\n')
    tar_file = output_lines[len(output_lines) - 1]
    print(f"tar_file is : {tar_file}")
    tarball_file_name = TMP_TECHSUPPORT_DUMP + str(tar_file.replace('/var/dump/', ''))

    print(f'start to fetch dump file from dut, saved to: {tarball_file_name}')
    sonic.copy_file(source_file=tar_file, dest_file=tarball_file_name,  file_system="", direction='get')
    sonic.run_cmd("sudo rm -rf {}".format(tar_file))
    return tarball_file_name

def get_syslog_from_compressed_file(compressed_file):
    if "tar.gz" in compressed_file:
        folder = Path(compressed_file).name.strip('.tar.gz')
        print(folder)
        try:
            with tarfile.open(compressed_file, "r:gz") as tar:
                syslogfiles = [tarinfo for tarinfo in tar.getmembers() if tarinfo.name.startswith(f"{folder}/log/syslog")]
                tar.extractall("./", syslogfiles)
            
            syslog_path = folder + "/log"
            print(syslog_path)
            for f in os.listdir(syslog_path):
                if "gz" in f:
                    fname = syslog_path + "/" + f
                    os.makedirs(TMP_SYSLOG_FOLDER, exist_ok=True)
                    tofile = f"{TMP_SYSLOG_FOLDER}/{f.strip('.gz')}"
                    with open(fname, 'rb') as inf, open(tofile, 'w', encoding='utf8') as tof:
                        decom_str = gzip.decompress(inf.read()).decode('utf-8')
                        tof.write(decom_str)
                else:
                    os.copy(f, TMP_SYSLOG_FOLDER)
            
        except Exception as err:
            raise err
        finally:
            delete_files(folder)
        return [os.path.join(TMP_SYSLOG_FOLDER, f) for f in os.listdir(TMP_SYSLOG_FOLDER)]
    return []

def run_loganalyzer(options, regex_file_path):
    tokenizer = ','
    run_id = "bug_handler"
    start_marker = options.start_marker
    end_marker = options.end_marker

    if not (options.start_marker and options.end_marker):
        raise Exception("End marker and start marker could not be empty")

    analyzer = AnsibleLogAnalyzer(run_id, options.verbose, start_marker=start_marker, end_marker=end_marker)
    log_file_list = get_log_files(options)
    if not log_file_list:
        print("No syslog files found, skipping running the loganalyzer")
        return
    match_file_list = [os.path.join(regex_file_path, f) for f in DEFAULT_MATCH_FILE_LIST]
    expect_file_list = [os.path.join(regex_file_path, f) for f in DEFAULT_EXPECT_FILE_LIST]

    match_file_list.extend(options.match_err_files)
    expect_file_list.extend(options.expect_err_files)

    print(f"match_file_list:{match_file_list}")
    print(f"expect_file_list:{expect_file_list}")

    match_messages_regex, messages_regex_m = analyzer.create_msg_regex(
        match_file_list)
    expect_messages_regex, messages_regex_e = analyzer.create_msg_regex(
        expect_file_list)
    messages_regex_e.extend(options.expect_err_list)
    ignore_messages_regex = get_ignore_regex(analyzer, options, regex_file_path)


    print(f"Start to run loganayzer: {log_file_list}")
    result = analyzer.analyze_file_list(log_file_list, match_messages_regex,
                                        ignore_messages_regex, expect_messages_regex, require_marker=False)
    return result

def delete_files(fname, folder=True):
    if folder:
        print(f"Deleting the folder: {fname}")
        os.system(f"rm -rf {fname}")
        print(f"Deleted the folder: {fname}")
    else:
        print(f"Deleting the file: {fname}")
        os.system(f"rm -rf {fname}")
        print(f"Deleted the file: {fname}")

def prepare_files_for_regex(branch):
    tar_branch = branch if branch == "develop" else f"develop-{branch}"
    tarball_file = f"/auto/sw_regression/system/SONIC/MARS/tarballs/SONIC_CANONICAL-sonic-mgmt_{tar_branch}.db.1.tgz"
    current_folder = os.path.dirname(os.path.abspath(__file__))
    sonic_mgmt_unzip_folder = f"sonic-mgmt_{branch}-{int(datetime.now().timestamp())}"
    ignore_folder = current_folder + "/" + sonic_mgmt_unzip_folder
    if os.path.exists(tarball_file):
        dynamic_ignore = f"sonic-mgmt/tests/common/plugins/loganalyzer_dynamic_errors_ignore/"
        common_file_list = [
            f"sonic-mgmt/ansible/roles/test/files/tools/loganalyzer/loganalyzer_common_ignore.txt",
            f"sonic-mgmt/ansible/roles/test/files/tools/loganalyzer/loganalyzer_common_expect.txt",
            f"sonic-mgmt/ansible/roles/test/files/tools/loganalyzer/loganalyzer_common_match.txt"
        ]
        try:
            os.makedirs(ignore_folder, exist_ok=True)
            with tarfile.open(tarball_file, "r:gz") as tar:
                dynamic_ignore_files = [tarinfo for tarinfo in tar.getmembers() if tarinfo.name in common_file_list or tarinfo.name.startswith(dynamic_ignore)]
                tar.extractall(ignore_folder, dynamic_ignore_files)
            for common_file in common_file_list:
                f = os.path.join(ignore_folder, common_file)
                os.system(f"mv {f} {ignore_folder}")
            dynamic_ignore_file = os.path.join(ignore_folder, dynamic_ignore)
            os.system(f"mv {dynamic_ignore_file} {ignore_folder}")
        except Exception as err:
            delete_files(ignore_folder)
            raise err
    else:
        print(f"Could not find sonic-mgmt tarball: {tarball_file} for branch: {branch}, the branch value should be like: develop, 202311, 202305 ...Use the default ignore file")
    
    return ignore_folder


def init_parser():
    description = ('Functionalities of the script: \n'
                   '1. Restart existing containers(fast mode):\n'
                   '    a. Remove Old docker containers on hypervisor (if existed).\n'
                   '    b. Create new clean containers.\n'
                   '2. Full steps of installation:\n'
                   '    a. Install Docker (if not existed)\n'
                   '    b. Docker login to Harbor\n'
                   '    c. Pull image from nbu-harbor.gtm.nvidia.com\n'
                   '    d. Create docker MACVLAN network (if not existed).\n'
                   '    e. Remove Old docker containers on hypervisor (if existed).\n'
                   '    f. Create new clean containers.')
    epilog = ('The script works by given setup_name and existed Noga entry of this setup.')

    parser = argparse.ArgumentParser(description=description, epilog=epilog, formatter_class=RawTextHelpFormatter)
    parser.add_argument("-a", "--action", dest="action", default=False, action="store_true", help="bughandler action") 

    log_group = parser.add_mutually_exclusive_group(required=True)
    log_group.add_argument("-l", "--log-files", dest='log_files', nargs='*', help='log files')
    log_group.add_argument("-d", "--dut ", 
                    dest="dut", 
                    default="", 
                    help="the timestamp of the syslog that the tool start from where to do the analysis")
    parser.add_argument("-u", "--username", dest="username", default=None, help="The user name of the dut when want to collect the dump from the dut") 
    parser.add_argument("-p", "--password", dest="password", default=None, help="The password of the dut when want to collect the dump from the dut") 

    parser.add_argument("-s", "--since", dest="since", default=None, help="From when to collect the techsupport of the DUT. it is counted in seconds. for example, 10 means will collect dump from 10s ago") 
    
    parser.add_argument("-e", "--expect_err_files", dest="expect_err_files", nargs='*', default="", help="a list of files, in the file user could specify the expected err msg regex.") 

    parser.add_argument("-r", "--expect_err_list", dest="expect_err_list", nargs='*', default="",  help="a list of expected err msg regex, in the file user could specify the expected err msg regex.") 
    
    parser.add_argument("-m", "--match_err_files", dest="match_err_files", nargs='*',  default="", help="a list of files, in the file user could specify the regex that used to match the err msg.") 

    parser.add_argument("-i", "--ignore_err_files", dest="ignore_err_files", nargs='*', default="", help="a list of files, in the file user could specify the regex of the err msg that need to be ignored.") 

    parser.add_argument("-g", "--ignore_err_list", dest="ignore_err_list", nargs='*', default="", help="a list of  err msg regex that used to match the err msgs that need to be ignored.") 
    
    # TODO: support the start stop timestamp            
    parser.add_argument("-t", "--time_stamp_start",  dest="time_stamp_start", default="", help="the timestamp used to collect the syslog file from DUT, the tool will collect the syslog files only newer than the timestamp, it could be like: '12/7/2024 11:45:05', '1/7/2025 15:49:05'")

    #parser.add_argument("-n", "--time_stamp_end", dest="time_stamp_end", default="",  help=" the timestamp of the syslog that the tool till where to stop to do the analysis, it is not supported till now") 
    parser.add_argument("-b", "--branch", dest='branch', default="develop", help='the sonic-mgmt branch that used to get the skip yaml file')
    parser.add_argument("-v", "--verbose", action="store_true", dest="verbose",   default=False,  help="show details info")
    parser.add_argument("--start-marker", dest="start_marker", default="", help="It is the marker that you want to start to analyze the results, if could not find the marker in syslog, then will analyze all the content of the syslog")
    parser.add_argument("--end-marker", dest="end_marker", default="", help="It is the marker that you want to end to analyze the results, if could not find the marker in syslog, then will analyze all the content of the syslog")
    parser.add_argument("--ssh-port", dest="ssh_port", default=22, help="The ssh port used to connect to the DUT")

    arguments, unknown = parser.parse_known_args()
    if unknown:
        raise Exception("unknown argument(s): {}".format(unknown))
    return arguments


def main():
    args = init_parser()
    print("Start to handle the log files")
    print(f"===================================================================================================")
    print(args)
    print(f"===================================================================================================")
    regex_file_path = None
    try:
        regex_file_path = prepare_files_for_regex(args.branch)
        result = run_loganalyzer(args, regex_file_path)
        if not result:
            return
        result_log_errors = []
        for key, value in list(result.items()):
            matching_lines, expecting_lines = value
            result_log_errors.extend(matching_lines)

        if result_log_errors:
            err_count = len(result_log_errors)
            print(f"{err_count} Err msg found by the loganalzyer")
            save_matching_errors(result_log_errors)
            print(f"Start to run bug handler for the {err_count} Err msgs ... it take more time for more err msgs")
            run_bug_handler(args.action)
        else:
            print("NO err msg detected, no need to run bughandler")
    except Exception as err:
        raise err
    finally:
        delete_files(TMP_SYSLOG_FOLDER)
        if regex_file_path and regex_file_path != os.path.dirname(os.path.abspath(__file__)):
            delete_files(regex_file_path)


if __name__ == "__main__":
    main()
