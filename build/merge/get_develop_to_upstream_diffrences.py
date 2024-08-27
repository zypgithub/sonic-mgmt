"""
Python3 file
"""
import os
import subprocess
import argparse
import datetime


def get_all_different_file_name_list(expected_diff_file_name_list):
    git_diff_command = 'git --no-pager diff  --name-status develop..upstream/master | egrep "^M"'
    rc, git_diff_output = subprocess.getstatusoutput(git_diff_command)
    git_diff_output_file_list = git_diff_output.split('\n')

    if rc != 0:
        raise Exception(git_diff_output)

    return [format_file_name(file_name) for file_name in git_diff_output_file_list if
            format_file_name(file_name) not in expected_diff_file_name_list]


def format_file_name(file_name):
    return file_name.lstrip('M').lstrip('\t')


def get_expected_diff_file_name_list():
    expected_diff_file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_overwrite_conflicts")
    with open(expected_diff_file_name) as f:
        return [file_name.strip('\n') for file_name in f.readlines()]
    return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.description = "Please input the parameter of last merge date"
    parser.add_argument("-l", "--last_merge_date", help="last merge date in format YYYY-MM-DD", default="")
    args = parser.parse_args()

    expected_diff_file_name_list = get_expected_diff_file_name_list()
    different_file_name_list = get_all_different_file_name_list(expected_diff_file_name_list)
    print("----------------------------File number is {0} ---------------------------".format(len(different_file_name_list)))
    for file_name in different_file_name_list:
        print(file_name)

    default_last_merge_date = (datetime.datetime.now() + datetime.timedelta(days=-7)).strftime("%Y-%m-%d")
    last_merge_date = args.last_merge_date if args.last_merge_date else default_last_merge_date
    get_pr_file_name = 'get_github_prs.py'
    get_pr_file_folder_path = os.path.dirname(__file__)
    get_pr_file_path = os.path.join(get_pr_file_folder_path, get_pr_file_name)
    try:
        os.system(f'python {get_pr_file_path} -l {last_merge_date}')
    except Exception as e:
        print(f"Failed to execute {get_pr_file_path}")
