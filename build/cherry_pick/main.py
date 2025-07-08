import os
import traceback
from repo import Repo, GitCommit, CherryPickStatus
from logger import logger
from args import init_arg_parser, Args
from smtp import send_email
from gerrit_api import extract_cr_links, add_topic_and_plus_2

_REMOTE_COMMUNITY_NAME = "upstream"
_REMOTE_COMMUNITY_URL = "https://github.com/sonic-net/sonic-mgmt.git"
_REMOTE_COMMUNITY_URL_202412 = "https://github.com/Azure/sonic-mgmt.msft.git"
_REMOTE_COMMUNITY_URL_202506 = "https://github.com/Azure/sonic-mgmt.msft.git"

def _update_last_success_file(file_path: str, last_success_commit: str):
    does_last_success_file_exist = os.path.isfile(file_path)
    with open(file_path, "w") as f:
        f.write(last_success_commit)
    if not does_last_success_file_exist:
        os.chmod(file_path, 0o666)

def _get_last_non_conflict_commit(commits: list[GitCommit]) -> GitCommit|None:  
    for commit in reversed(commits):
        if commit.cherry_pick_status != CherryPickStatus.ERROR:
            return commit
    return None

def main(args: Args, git_repo: Repo):
    logger.info(f"Parsed args as below: {args}")
    skip_commit_hashes = set()
    for skip_commit in args.skip.split(","):
        skip_commit = skip_commit.strip()
        if skip_commit:
            skip_commit_hashes.add(skip_commit)
    logger.debug(f"{len(skip_commit_hashes)} commit hashes to be skipped")
    if args.branch == "202412":
        git_repo.set_remote_url(_REMOTE_COMMUNITY_NAME, _REMOTE_COMMUNITY_URL_202412)
    elif args.branch == "202506":
        git_repo.set_remote_url(_REMOTE_COMMUNITY_NAME, _REMOTE_COMMUNITY_URL_202506)
    else:
        git_repo.set_remote_url(_REMOTE_COMMUNITY_NAME, _REMOTE_COMMUNITY_URL)
    logger.debug(
        f"fetch from upstream/{args.branch} output:\n"
        f"{git_repo.fetch_remote(_REMOTE_COMMUNITY_NAME, args.branch)}"
    )
    logger.info(
    f"change to branch {args.target_branch}: "
    f"{git_repo.change_to_branch(args.target_branch)}"
    )
    commits = []
    if args.last_successful_commit_hash:
        commits = git_repo.get_commits_since_commit_hash_until_date(
            args.last_successful_commit_hash,
            args.target_branch,
            f"{_REMOTE_COMMUNITY_NAME}/{args.branch}",
            args.until
        )
        logger.info(
            f"{len(commits)} found in source repo since "
            f"{args.last_successful_commit_hash} until {args.until}"
        )
    else:
        commits = git_repo.get_commits_by_range(
            args.since, args.until, args.target_branch, f"{_REMOTE_COMMUNITY_NAME}/{args.branch}"
        )
        logger.info(
            f"{len(commits)} found in source repo since "
            f"{args.since} until {args.until}"
        )

    skip_commits_list = [
        commit for commit in commits
        if commit.hash in skip_commit_hashes 
        or commit.hash[:8] in skip_commit_hashes
    ]
    for idx, skip_commit in enumerate(skip_commits_list):
        logger.info(f"[{idx:03d}]skip: {skip_commit}")
        
    non_skip_commits_list = [
        commit for commit in commits if commit not in skip_commits_list
    ]
    has_conflict, ready_for_review, tried_commits = git_repo.cherry_pick_commits(
        non_skip_commits_list
    )
    logger.info(
        f"has_conflict: {has_conflict}, ready_for_review: {ready_for_review}, "
        f"tried_commits: {len(tried_commits)}"
    )
    
    cr_on_top = ""
    if ready_for_review and not args.dry_run:
        review_output = git_repo.git_review()
        logger.info(f"review output: {review_output}")
        cr_links = extract_cr_links(review_output)
        add_topic_and_plus_2(cr_links)
        if cr_links:
            cr_on_top = cr_links[-1]
    if not args.dry_run:
        last_success_commit = _get_last_non_conflict_commit(tried_commits)
        if last_success_commit:
            _update_last_success_file(
                f"{args.branch}.LAST_SUCCESS",
                str(last_success_commit)
            )
    if len(args.recipients) > 0 and not args.dry_run:
        send_email(
            args.recipients,
            args.branch,
            has_conflict=has_conflict,
            commits=tried_commits,
            cr_on_top=cr_on_top,
            triggered_by=args.triggered_by,
            total_commits=len(non_skip_commits_list)
        )


if __name__ == "__main__":
    args = init_arg_parser()
    git_repo = Repo(args.repo_path)
    try:
        main(args, git_repo)
    except Exception as e:
        if len(args.recipients) > 0 and not args.dry_run:
            traceback_str = traceback.format_exc()
            send_email(
                args.recipients,
                args.branch,
                exception=traceback_str
            )
        raise e
    finally:
        if args.reset:
            output = git_repo.reset_hard(f"origin/{args.target_branch}")
            logger.info(
                f"hard reset to origin/{args.target_branch} output: {output}"
            )
