import logging
from dataclasses import dataclass
import argparse
from pathlib import Path

from logger import logger

_SUPPORTED_BRANCHES = ["master", "202411"]
_LOG_LEVEL_MAPPING = {
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "ERROR": logging.ERROR,
    "WARN": logging.WARN,
}

@dataclass
class Args:
    branch: str         # source branch, e.g. 202411, 202405, master, etc...
    target_branch: str  # derived from the source branch
    since: str
    until: str
    skip: str
    recipients: list[str]
    last_successful_commit_hash: str|None = None
    log_level: str = "INFO"
    dry_run:bool = True
    reset:bool = True   # whether to hard reset to remote branch in the end
    repo_path: str = "repo_path"  # the path to hold repo code

    def __str__(self)->str:
        return f"""
            source branch: {self.branch}
            target branch: {self.target_branch}
            since:{self.since}
            until:{self.until}
            skip:{self.skip}
            last_successful_commit_hash: {self.last_successful_commit_hash}
            log_level: {self.log_level}
            recipients: {self.recipients}
            dry_run: {self.dry_run},
            reset: {self.reset},
            repo_path: {self.repo_path}"""

def init_arg_parser()->Args:
    parser = argparse.ArgumentParser(description="Utility to cherry pick commits from sonic_mgmt community")
    parser.add_argument("-b", "--branch", type=str, help="the branch name of sonic_mgmt repo in gerrit",
                        default="202411")
    parser.add_argument("-s", "--since", type=str, help="commits more recent than the specific date,\
                        only valid when last cherry pick commit unavailable", default="2025-01-01")
    parser.add_argument("-u", "--until", type=str, help="commits older than the specific date",
                        default="now")
    parser.add_argument("--skip", type=str, help="Commit IDs to be skipped(Optional), separate with comma",
                        default="")
    parser.add_argument("--loglevel", type=str, help="Choose from INFO,DEBUG,WARN,ERROR, default: INFO",
                        default="INFO")
    parser.add_argument("--recipients", type=str, help="comma separated recipients of report")
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run",
                        help="no git review, no email notification for dry run")
    parser.add_argument("--no-reset", action="store_false", dest="reset",
                        help="no hard reset in the end, will keep all the cherry picked commits locally")
    parser.add_argument("--repo_path", type=str, help="repository path", default="repo_path")
    parsed_args = parser.parse_args()
    assert parsed_args.branch in _SUPPORTED_BRANCHES, \
        f"{parsed_args.branch} not in supported branch list: {_SUPPORTED_BRANCHES}"
    target_branch = f"develop-{parsed_args.branch}"
    if parsed_args.branch == "master":
        target_branch = "develop"
    args = Args(branch=parsed_args.branch, target_branch=target_branch, since=parsed_args.since,
                until=parsed_args.until, skip=parsed_args.skip, log_level=parsed_args.loglevel,
                recipients=parsed_args.recipients.split(",") if parsed_args.recipients else "",
                dry_run=parsed_args.dry_run,
                reset=parsed_args.reset,
                repo_path=parsed_args.repo_path)
    last_successful_commit_file = Path(f"{args.branch}.LAST_SUCCESS")
    if last_successful_commit_file.exists() and last_successful_commit_file.is_file():
        lines = last_successful_commit_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, f"Expect 1 line to be in file {last_successful_commit_file}"
        fields = lines[0].split("|", maxsplit=3)
        assert len(fields) == 4, f"Expect 4 fields to be in file {last_successful_commit_file}"
        args.last_successful_commit_hash = fields[2]
    logger.setLevel(_LOG_LEVEL_MAPPING[args.log_level] if args.log_level in _LOG_LEVEL_MAPPING else logging.INFO)
    return args
