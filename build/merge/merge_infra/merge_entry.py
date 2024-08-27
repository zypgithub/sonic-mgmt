import argparse
import datetime
import os

from build.merge.merge_infra.repo.repo_handler import GitHubApi, GITHUB_USER, GITHUB_API_TOKEN, GerritHandler, \
    MergeHistory, init_all_path
from build.merge.merge_infra.utils.merge_email import generate_email, send_report


def daily_merge(remote_branch, local_branch, start_date, end_date, recipients=None, ignore_list=None):
    if ignore_list is None:
        ignore_list = []
    if recipients is None:
        recipients = []
    recipients = ",".join(recipients)

    init_all_path()

    GerritHandler.clone(force=True)

    # GerritHandler.add_safe()
    # GerritHandler.git_config('community_auto_merge@nvidia.com', 'Auto Merger')

    GerritHandler.copy_commit_hook()
    GerritHandler.upstream(source="github")
    GerritHandler.upstream(source="gerrit")

    '''
    Use git log instead of rest api
    '''
    # github_api = GitHubApi(GITHUB_USER, GITHUB_API_TOKEN)
    # prs = github_api.get_pr_merged(sha=remote_branch, last_merge_date=start_date, until_date=end_date)
    GerritHandler.checkout(remote_branch)
    prs = GerritHandler.get_range_commits(start_date, end_date)

    GerritHandler.checkout(local_branch)

    prs = [pr for pr in prs if not GerritHandler.detect_pr_id(pr)]
    print(prs)

    status, summary = GerritHandler.cherry_pick(prs, local_branch, remote_branch, ignore_list)
    review_status, crs = GerritHandler.git_review(status)
    # review_status, crs = True,[]
    status = status and review_status
    send_report(generate_email(recipients, status, summary,
                               os.path.join(MergeHistory.storage_path, MergeHistory.unmerged_storage),
                               os.path.join(MergeHistory.storage_path, MergeHistory.last_merged_storage),
                               GerritHandler.data_path,
                               local_branch,
                               remote_branch,
                               start_date,
                               end_date,
                               crs), recipients)
    print(summary)


def init_parser():
    description = ('Functionality of the script: \n'
                   'Automatically merge code form community.\n')

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument('--result_storage_path', default=None,
                        help='The path to store the result of merging.')

    parser.add_argument('--branch', default='master',
                        help='The branch of gerrit.')

    # parser.add_argument('--gerrit_branch', default='develop',
    #                     help='The branch of gerrit.')
    #
    # parser.add_argument('--github_branch', required=True,
    #                     help='The branch of github.')

    parser.add_argument('--repo_path', default=None,
                        help='The temp path of repo.')

    parser.add_argument('--recipients', nargs='*', default=list(),
                        help='Recipients for report email')

    parser.add_argument('--start_date',
                        default=(datetime.datetime.now() + datetime.timedelta(days=-10)).strftime("%Y-%m-%d"),
                        help='Start date of PRs in YYYY-mm-dd. e.g. 2024-05-01')

    parser.add_argument('--end_date', default=(datetime.datetime.now()).strftime("%Y-%m-%d"),
                        help='End date of PRs in YYYY-mm-dd. e.g. 2024-05-01')

    parser.add_argument('--ignore_prs', nargs='*', default=list(),
                        help='PRs which should be ignored.')

    args, unknown = parser.parse_known_args()

    if unknown:
        raise Exception("unknown argument(s): {}".format(unknown))

    return args


if __name__ == '__main__':
    # daily_merge('202405', 'develop-202405', start_date='2024-07-20', end_date='2024-08-05', recipients=['fangyic@nvidia.com'])
    args = init_parser()

    if args.branch == 'master':
        local_branch = 'develop'
    else:
        local_branch = f'develop-{args.branch}'

    if args.result_storage_path:
        MergeHistory.storage_path = args.result_storage_path
    if args.repo_path:
        GerritHandler.tmp_dir = args.repo_path
    GerritHandler.branch = local_branch
    MergeHistory.storage_path = os.path.join(MergeHistory.storage_path, local_branch)
    daily_merge(remote_branch=args.branch, local_branch=local_branch, start_date=args.start_date,
                end_date=args.end_date, recipients=args.recipients, ignore_list=args.ignore_prs)
