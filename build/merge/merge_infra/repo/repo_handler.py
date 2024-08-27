import copy
import re
import subprocess

import requests
import logging

import os
import json

from requests.auth import HTTPBasicAuth

from build.merge.get_develop_to_upstream_diffrences import get_expected_diff_file_name_list
from build.merge.merge_infra.confict_resolver.utils import conflict_parser, conflict_differ, conflict_merger
from build.merge.merge_infra.utils.model import MergeHintHandler, MergeHintEnum, MergeHint

BASE_URL = "https://api.github.com"
BASE_PR_SEARCH_URL = "https://api.github.com/repos/sonic-net/sonic-mgmt/commits?"

GITHUB_USER = os.getenv('GITHUB_USER')
GITHUB_API_TOKEN = os.getenv('GITHUB_PASSWORD')
MERGE_OVERWRITE_CONFLICT_FILES = get_expected_diff_file_name_list()

logger = logging.getLogger()

print("GITHUB_CREDS", GITHUB_USER, GITHUB_API_TOKEN)


def init_all_path():
    paths = [
        MergeHistory.base_path,
        GerritHandler.tmp_dir,
        GerritHandler.data_path
    ]

    for path in paths:
        if os.path.exists(path):
            os.makedirs(path, exist_ok=True)


class MergeHistory:
    base_path = '/auto/sw_regression/system/SONIC/MARS/community_merge/logs'
    storage_path = base_path
    last_merged_storage = "last_merged"
    unmerged_storage = "unmerged"

    @staticmethod
    def get_last_merged():
        expected_diff_file_name = os.path.join(MergeHistory.storage_path, MergeHistory.last_merged_storage)
        if os.path.exists(expected_diff_file_name):
            with open(expected_diff_file_name) as f:
                return [file_name.strip('\n') for file_name in f.readlines()]
        else:
            return []

    @staticmethod
    def get_unmerged():
        expected_diff_file_name = os.path.join(MergeHistory.storage_path, MergeHistory.unmerged_storage)
        if os.path.exists(expected_diff_file_name):
            with open(expected_diff_file_name) as f:
                return [file_name.strip('\n') for file_name in f.readlines()]
        else:
            return []

    @staticmethod
    def save_unmerged(unmerged):
        if len(MergeHistory.storage_path) > 0:
            os.makedirs(MergeHistory.storage_path, exist_ok=True)
        expected_diff_file_name = os.path.join(MergeHistory.storage_path, MergeHistory.unmerged_storage)
        with open(expected_diff_file_name, 'w') as f:
            f.write("\n".join(unmerged))

    @staticmethod
    def save_last_merged(last_merged):
        if len(MergeHistory.storage_path) > 0:
            os.makedirs(MergeHistory.storage_path, exist_ok=True)
        expected_diff_file_name = os.path.join(MergeHistory.storage_path, MergeHistory.last_merged_storage)
        with open(expected_diff_file_name, 'w') as f:
            f.write("\n".join(last_merged))

    @staticmethod
    def check_unmerged(unmerged):
        pr_list = GerritHandler.get_recent_commits()
        new_unmerged = []
        for unmerged_pr_id in unmerged:
            if unmerged_pr_id not in pr_list:
                new_unmerged.append(unmerged_pr_id)
        return new_unmerged


def get_pr_id(message):
    pattern = r'\(#(\d+)\)'
    matches = re.findall(pattern, message)
    if matches:
        return str(matches[0])
    return ''


class GerritAPIHandler:
    api_username = 'nhe'
    api_password = 'FRS545Qx2ORW2yjCy1nBS0qIoLCJtcLrxr1vsqYW3A'

    relation_chain = 'https://git-nbu-sw.nvidia.com/r/a/changes/switchx%2Fsonic%2Fsonic-mgmt~{0}/revisions/1/related?o=SUBMITTABLE'
    topic = 'https://git-nbu-sw.nvidia.com/r/a/changes/switchx%2Fsonic%2Fsonic-mgmt~{0}/topic'
    review = 'https://git-nbu-sw.nvidia.com/r/a/changes/switchx%2Fsonic%2Fsonic-mgmt~{0}/revisions/1/review'

    @staticmethod
    def make_gerrit_request(url):
        """
        Send API request to gerrit
        :param url: gerrit api url
        :return: dictionary with data
        """
        auths = HTTPBasicAuth(GerritAPIHandler.api_username, GerritAPIHandler.api_password)
        response = requests.get(url, auth=auths)
        response.raise_for_status()
        content = response.content.decode('utf-8').strip(")]}'")
        return json.loads(content)

    @staticmethod
    def make_gerrit_put(url, data=None):
        """
        Send API request to gerrit
        """
        auths = HTTPBasicAuth(GerritAPIHandler.api_username, GerritAPIHandler.api_password)
        response = requests.put(url,
                                auth=auths,
                                json=data,
                                headers={'Content-Type': 'application/json',
                                         'charset': 'UTF-8'})
        response.raise_for_status()
        return response.content.decode('utf-8')

    @staticmethod
    def make_gerrit_post(url, data=None):
        """
        Send API request to gerrit
        :param url: gerrit api url
        :return: dictionary with data
        """
        auths = HTTPBasicAuth(GerritAPIHandler.api_username, GerritAPIHandler.api_password)
        response = requests.post(url,
                                 auth=auths,
                                 json=data,
                                 headers={'Content-Type': 'application/json',
                                          'charset': 'UTF-8'})
        response.raise_for_status()
        return response.content.decode('utf-8')

    @staticmethod
    def get_relation_chain(cr):
        api = GerritAPIHandler.relation_chain.format(cr)
        data = GerritAPIHandler.make_gerrit_request(api)
        return data['changes']

    @staticmethod
    def set_topic(cr, topic):
        datas = {'topic': topic}
        api = GerritAPIHandler.topic.format(cr)
        status = GerritAPIHandler.make_gerrit_put(api, datas)
        return status

    @staticmethod
    def set_review(cr, status):
        r = {
            "message": "Automatically +2 by merge tool.",
            "labels": {
                "Code-Review": status
            }
        }
        api = GerritAPIHandler.review.format(cr)
        status = GerritAPIHandler.make_gerrit_post(api, r)
        return status

    @staticmethod
    def only_ci_top_relation_chain(target_cr):
        crs = GerritAPIHandler.get_relation_chain(target_cr)
        for cr in crs:
            if cr['_change_number'] == target_cr:
                continue
            if cr['status'] != 'NEW':
                continue
            GerritAPIHandler.set_topic(cr['_change_number'], 'IGNORE')
        GerritAPIHandler.set_topic(target_cr, 'SKIP_BEAUTIFIER,SKIP_SPELLCHECK')

    @staticmethod
    def review_plus_2(target_cr):
        crs = GerritAPIHandler.get_relation_chain(target_cr)
        plus_2_crs = []
        for cr in crs:
            if cr['_change_number'] > int(target_cr):
                continue
            if cr['status'] != 'NEW':
                continue
            plus_2_crs.append(cr['_change_number'])
        plus_2_crs = [int(i) for i in plus_2_crs]
        if target_cr not in plus_2_crs:
            plus_2_crs.append(target_cr)
        plus_2_crs = sorted(list(map(int, plus_2_crs)))
        for cr in plus_2_crs:
            GerritAPIHandler.set_review(cr, 2)


class GerritHandler:
    branch = 'develop'
    tmp_dir = f"sonic_tmp"
    git_ssh_url = "ssh://git-nbu-sw.nvidia.com:12024/switchx/sonic/sonic-mgmt"
    github_url = "https://github.com/sonic-net/sonic-mgmt.git"
    gerrit_url = "https://fangyic@git-nbu-sw.nvidia.com/r/a/switchx/sonic/sonic-mgmt"

    data_path = "/auto/sw_regression/system/SONIC/MARS/community_merge/conflicts"

    max_merged_length = 100

    @staticmethod
    def get_range_commits(since, until):
        result = subprocess.run(
            f'git log --pretty=format:%H|%s|%cs --since="{since}" --until="{until}"',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=GerritHandler.tmp_dir,
        )

        logger.debug("Successfully get all logs.")

        if result.returncode != 0:
            raise Exception(f"Git command failed with error: {result.stderr}")

        res = []

        text = result.stdout

        if isinstance(text, bytes):
            text = text.decode('utf-8')

        for index, line in enumerate(text.splitlines()):
            logger.debug(f"Log Line {index}")
            commit_hash, commit_message, author_date = line.split('|', 2)
            pr_id = get_pr_id(commit_message)
            if len(pr_id) > 0 and str(pr_id).isdigit():
                pr_dict = {}
                pr_dict['sha'] = commit_hash
                pr_dict['commit_date'] = author_date
                pr_dict['pr_id'] = pr_id
                res.append(pr_dict)

        logger.debug("Successfully get all prs.")

        res.sort(key=lambda x: x['commit_date'])

        return res

    @staticmethod
    def get_recent_commits(count=100):
        try:
            result = subprocess.run(
                ['git', 'log', '-n', str(count), '--pretty=format:%H|%s|%cs'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=GerritHandler.tmp_dir,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"Git command failed with error: {result.stderr}")

            commits = set()
            for line in result.stdout.splitlines():
                commit_hash, commit_message, commit_date = line.split('|')
                pr_id = get_pr_id(commit_message)
                if len(pr_id) > 0 and str(pr_id).isdigit():
                    commits.add(pr_id)

            return commits

        except Exception as e:
            print(f"An error occurred: {e}")
            return set()

    @staticmethod
    def git_review(do_review=False):
        try:
            process = subprocess.run("git review -Ry", cwd=GerritHandler.tmp_dir, shell=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            return False, ""

        # get CR
        pattern = r'git-nbu-sw.nvidia.com/r/c/switchx/sonic/sonic-mgmt/\+/\d+'
        links = re.findall(pattern, process.stdout.decode('utf-8'))

        if len(links) > 0:
            crs = [int(cr.split('/')[-1]) for cr in links]
            crs = sorted(crs)
            top_cr = crs[-1]
            GerritAPIHandler.only_ci_top_relation_chain(top_cr)
            if do_review:
                print("Automatically plus 2")
                GerritAPIHandler.review_plus_2(top_cr)
            return True, links[-1]
        else:
            return False, ""

    @staticmethod
    def copy_commit_hook():
        if not os.path.exists(os.path.join(GerritHandler.tmp_dir, ".git/hooks/commit-msg")):
            p = subprocess.run(
                f'scp -p -P 12024 git-nbu-sw.nvidia.com:hooks/commit-msg "{os.path.join(GerritHandler.tmp_dir, ".git/hooks/")}"',
                cwd=GerritHandler.tmp_dir, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            print("Commit Hook Result:", p.stderr)

    @staticmethod
    def get_untracked_files():
        process = subprocess.run("git ls-files --others --exclude-standard", cwd=GerritHandler.tmp_dir, shell=True,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 check=True)
        res = process.stdout.decode("utf-8").strip().split('\n')
        return [i for i in res if len(i) > 0]

    @staticmethod
    def clone(force=False):
        print(f"Git Cloning")

        if os.path.exists(GerritHandler.tmp_dir):
            if not force:
                return
            os.system(f"rm -rf {GerritHandler.tmp_dir}")

        os.makedirs(GerritHandler.tmp_dir)

        cmd = f'git clone "{GerritHandler.git_ssh_url}" {GerritHandler.tmp_dir}'

        try:
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            print(process.stdout)
            print(process.stderr)
        except subprocess.CalledProcessError as e:
            print("Command running error:", e.stderr)

    @staticmethod
    def upstream(source="github"):
        print(f"Set Upstream to {source}")

        if source == "github":
            url = GerritHandler.github_url
        else:
            url = GerritHandler.gerrit_url

        upstream_cmd = f'git remote add upstream {url} && git fetch upstream'
        try:
            process = subprocess.run(upstream_cmd, cwd=GerritHandler.tmp_dir, shell=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
            print(process.stdout)
            if process.stderr:
                logger.error(process.stderr)
        except subprocess.CalledProcessError as e:
            print("Command running error:", e.stderr)

    @staticmethod
    def cherry_pick(prs, remote_branch, local_branch, ignore_list=None):
        last_merged = set(MergeHistory.get_last_merged())
        unmerged = set(MergeHistory.get_unmerged())

        hints = []
        for pr in prs:
            if pr['sha'] in last_merged:
                continue

            if pr['sha'] in ignore_list:
                continue

            state, hint = GerritHandler.cherry_pick_sha(pr['sha'], pr['pr_id'])
            hint.pr = pr

            hints.append(hint)
            for conflict_file in hint.conflict_files:
                print(f"{conflict_file} is set to our version due to conflict.")
                GerritHandler.ours(conflict_file)

            # Keep our file
            for file in hint.affected_files:
                if file in MERGE_OVERWRITE_CONFLICT_FILES:
                    print(f"{file} is taken out from cherry-pick cause it is in merge_overwrite_conflicts.")
                    GerritHandler.ours(file)

            untracked = GerritHandler.get_untracked_files()
            for file in untracked:
                if file not in MERGE_OVERWRITE_CONFLICT_FILES:
                    print(f"Adding untracked files {file}")
                    GerritHandler.add(file)
                else:
                    GerritHandler.ours(file)

            unstaged = GerritHandler.get_unstaged_changes()
            for file in unstaged:
                if file not in MERGE_OVERWRITE_CONFLICT_FILES:
                    print(f"Adding unstaged files {file}")
                    GerritHandler.add(file)
                else:
                    GerritHandler.ours(file)

            GerritHandler.generate_change_id()
            GerritHandler.commit(f"Resolve conflict of '{pr['sha']}' on merging {remote_branch} into {local_branch}.")
            GerritHandler.cherry_pick_continue()

        summary = MergeHintHandler.summary_by_commit(hints)
        summary['LAST_TIME_UNMERGED'] = list(unmerged)

        for commit_id, info in summary.items():
            if commit_id in ['LAST_TIME_UNMERGED']:
                continue
            status, hint = info
            if hint.hint.status is False:
                unmerged.add(hint.pr_id)
            else:
                last_merged.add(hint.pr_id)

        unmerged = list(MergeHistory.check_unmerged(unmerged))
        MergeHistory.save_unmerged(list(unmerged))
        MergeHistory.save_last_merged(list(last_merged)[:GerritHandler.max_merged_length])

        if len(unmerged) > 0:
            status = False
        else:
            status = True

        return status, summary

    @staticmethod
    def ours(filename):
        try:
            subprocess.run(['git', 'checkout', '--ours', filename], check=True, cwd=GerritHandler.tmp_dir)
        except subprocess.CalledProcessError as e:
            print(f"Error: Could not keep our file '{filename}'. Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    @staticmethod
    def add(filename):
        try:
            subprocess.run(["git", "add", filename], check=True, cwd=GerritHandler.tmp_dir)
        except subprocess.CalledProcessError as e:
            print(f"Error: Could not add file '{filename}'. Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    @staticmethod
    def commit(message):
        print(f"Trying to make a commit.")

        try:
            subprocess.run(["git", "commit", "-m", message], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                           cwd=GerritHandler.tmp_dir)
            GerritHandler.generate_change_id()
        except subprocess.CalledProcessError as e:
            logger.warning(f"Skip this commit. Error: Could not commit changes. Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    @staticmethod
    def generate_change_id():
        print(f"Trying to generate a change id for cherry-pick.")

        try:
            subprocess.run(["git", "commit", "--amend", "--no-edit"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           check=True, cwd=GerritHandler.tmp_dir)
        except subprocess.CalledProcessError as e:
            logger.error(f"Can not generate change id: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    @staticmethod
    def checkout(branch):
        def check_branch_exists(branch_name):
            try:
                res = subprocess.run(["git", "rev-parse", "--verify", branch_name], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, check=True, cwd=GerritHandler.tmp_dir)
                if res.stderr:
                    logger.warning(res.stderr)
                return True
            except subprocess.CalledProcessError:
                return False

        if not check_branch_exists(branch):
            subprocess.run(["git", "branch", branch, f"remotes/origin/{branch}"], check=True, cwd=GerritHandler.tmp_dir)

        subprocess.run(["git", "checkout", branch], check=True, cwd=GerritHandler.tmp_dir)
        subprocess.run(["git", "fetch", "--progress"], stderr=subprocess.PIPE, cwd=GerritHandler.tmp_dir)
        subprocess.run(["git", "pull", "--force", "--progress"], check=True, cwd=GerritHandler.tmp_dir)

    @staticmethod
    def add_safe():
        subprocess.run(f"git config --global --add safe.directory {GerritHandler.tmp_dir}", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, cwd=GerritHandler.tmp_dir)

    @staticmethod
    def git_config(email, username):
        subprocess.run(f'git config --global user.email "{email}"', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, cwd=GerritHandler.tmp_dir)
        subprocess.run(f'git config --global user.email "{username}"', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, cwd=GerritHandler.tmp_dir)

    @staticmethod
    def leading_commits(local_branch, remote_branch):
        leading_branches = []

        # Check if the local branch is ahead of its remote counterpart
        merge_base = subprocess.run(["git", "merge-base", local_branch, f"remotes/origin/{local_branch}"],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, check=True, cwd=GerritHandler.tmp_dir)
        merge_base = merge_base.stdout.decode('utf-8').strip()
        commits = subprocess.run(["git", "rev-list", f"{merge_base}..{local_branch}"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, cwd=GerritHandler.tmp_dir)
        commits = commits.stdout.decode('utf-8').strip()

        if commits:
            leading_branches.extend(commits.splitlines())

        return leading_branches

    @staticmethod
    def detect_pr_id(pr):
        pr_id = pr['pr_id']
        print(f"Detecting if {pr_id} exist")

        result = subprocess.run(
            f'git log --pretty=format:%s --grep="{pr_id}"',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=GerritHandler.tmp_dir,
        )

        result = [get_pr_id(pr) for pr in result.stdout.decode('utf-8').splitlines()]
        result = [int(pr) for pr in result if pr != '']

        return pr_id in result

    @staticmethod
    def cherry_pick_sha(sha, pr=''):
        print(f"Cherry picking {sha}")

        conflict_files = []
        result = subprocess.run(['git', 'cherry-pick', sha], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=GerritHandler.tmp_dir)
        modified_files = GerritHandler.modified_files()

        def get_affected_files():
            affected_files = []
            for file in modified_files:
                if file not in conflict_files and file not in MERGE_OVERWRITE_CONFLICT_FILES:
                    affected_files.append(file)
            return affected_files

        state = True
        hint = MergeHintEnum.MERGE_SUCCESSFULLY

        if result.returncode != 0:
            if result.stderr and "error: could not apply" in result.stderr.decode("utf-8"):
                conflicted_files = GerritHandler.get_conflicted_files()
                flag = True
                skip = False
                for file in conflicted_files:
                    if file in MERGE_OVERWRITE_CONFLICT_FILES:
                        skip = True
                        subprocess.run(['git', 'checkout', '--ours', file], cwd=GerritHandler.tmp_dir)
                    else:
                        flag = False
                        conflict_files.append(file)
                if flag:
                    state = True
                    hint = MergeHintEnum.KEEP_US
                else:
                    if skip:
                        state = False
                        hint = MergeHintEnum.PARTLY_KEEP_US
                    else:
                        state = False
                        hint = MergeHintEnum.TOTAL_CONFLICT
            elif result.stderr and "you have unmerged" in result.stderr.decode("utf-8"):
                state = False
                hint = MergeHintEnum.TOTAL_CONFLICT
            elif result.stdout and ("nothing to commit" in result.stdout.decode("utf-8") or "nothing to commit" in result.stdout.decode("utf-8")):
                state = True
                hint = MergeHintEnum.NO_CHANGE
            else:
                state = False
                hint = MergeHintEnum.MERGE_FAILED

        for i in range(len(conflict_files)):
            if isinstance(conflict_files[i], bytes):
                conflict_files[i] = conflict_files[i].decode("utf-8")

        if state is False:
            resolved_files, unresolved_files = AutoConflictHandler.resolve_conflicts(conflict_files, sha)
            conflict_files = unresolved_files
            if len(resolved_files) > 0 and len(unresolved_files) == 0:
                state = True

        return state, MergeHint(hint=hint, commit_id=sha, pr_id=pr,
                                conflict_files=conflict_files,
                                affected_files=get_affected_files(),
                                error=result.stdout)

    @staticmethod
    def get_conflicted_files():
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=GerritHandler.tmp_dir)
        conflicted_files = result.stdout.splitlines()
        return conflicted_files

    @staticmethod
    def get_unstaged_changes():
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=GerritHandler.tmp_dir)
        conflicted_files = result.stdout.splitlines()
        return conflicted_files

    @staticmethod
    def cherry_pick_continue():
        res = subprocess.run(['git', 'cherry-pick', '--continue'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=GerritHandler.tmp_dir)
        if res.stderr:
            logger.error(f"Cherry-pick continue failed. {str(res.stderr)}")
            GerritHandler.cherry_pick_abort()

    @staticmethod
    def cherry_pick_abort():
        try:
            subprocess.run(['git', 'cherry-pick', '--abort'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           check=True,
                           cwd=GerritHandler.tmp_dir)
        except BaseException:
            print("Cherry-pick abort failed, due to conflict resolve. Skip.")

    @staticmethod
    def modified_files():
        command = f'git show HEAD --pretty="%f" --name-only'
        output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True,
                                cwd=GerritHandler.tmp_dir)
        files = [line.strip() for line in output.stdout.decode("utf-8").split('\n')[1:] if line.strip()]
        return files


class AutoConflictHandler:
    @staticmethod
    def resolve_conflicts(conflict_files, commit):
        resolved_files = []
        unresolved_files = []
        for filename in conflict_files:
            filepath = os.path.join(GerritHandler.tmp_dir, filename)
            filepath = filepath.replace("\\", "/")
            with open(filepath, 'r', encoding='utf-8') as input_file:
                content = input_file.read()
                content = content.split("\n")
                conflicts = conflict_parser(content)

                # Make a backup
                origin_conflicts = copy.deepcopy(conflicts)
                origin_content = copy.deepcopy(content)

                handle_result, unresolved = conflict_differ(conflicts, content, else_handler="ours")
            with open(filepath, 'w', encoding='utf-8') as output_file:
                output_file.write(conflict_merger(handle_result))

            if unresolved > 0:
                # Save unmerged backup to
                os.makedirs(os.path.join(GerritHandler.data_path, commit), exist_ok=True)
                tmp_backup = open(os.path.join(GerritHandler.data_path, commit, f'CONFLICT_{filename.replace("/", "_")}'),
                                  'w', encoding='utf-8')
                unmerged_result, _ = conflict_differ(origin_conflicts, origin_content, else_handler="no")
                tmp_backup.write(conflict_merger(origin_content))

                unresolved_files.append(filename)
            else:
                resolved_files.append(filename)

        return resolved_files, unresolved_files


class GitHubApi:
    """
    This class allows user to search github prs
    Usage example:
    github = GitHubApi('user', 'api_token')
    github.get_pr_open_from_nvidia_verification_team()
    github.get_pr_merged_after_last_merge()
    """

    def __init__(self, github_username, api_token):
        self.auth = (github_username, api_token)

    def make_github_request(self, url):
        """
        Send API request to github
        :param url: github api url
        :return: dictionary with data
        """
        response = requests.get(url, auth=self.auth)
        response.raise_for_status()
        return response.json()

    def get_pr_merged(self, **kwargs):
        url = self.get_github_merged_pr_url(**kwargs)
        return self.get_pr_and_related_files(url)

    @staticmethod
    def get_github_merged_pr_url(last_merge_date=None, until_date=None, status="merged", sha=None):
        """
        Return the URL used to get the prs merged since last merge date
        :param last_merge_date: last merge date
        :param until_date: end date of prs
        :param status: the status of the prs
        :return: URL used to get the prs merged since last merge date
        """
        url = f"{BASE_PR_SEARCH_URL}is:{status}"
        if last_merge_date:
            url += f"&since={last_merge_date}"
        if until_date:
            url += f"&until={until_date}"
        if sha:
            url += f"&sha={sha}"
        return url

    def get_pr_and_related_files(self, pr_search_url):
        """
        Get PRs and the files modified in the every pr
        :param pr_search_url: the url used to search the prs
        :return: None
        """
        pr_search_res = self.make_github_request(pr_search_url)
        pr_url_iter = []
        for pr in pr_search_res:
            message = pr['commit']['message']
            pattern = r'\(#(\d+)\)'
            pr_dict = {}
            matches = re.findall(pattern, message)
            pr_dict['sha'] = pr['sha']
            pr_dict['commit_date'] = pr['commit']['committer']['date']
            if matches:
                pr_dict['pr_id'] = str(matches[0])
            else:
                pr_dict['pr_id'] = ''
            pr_url_iter.append(pr_dict)
        return pr_url_iter
