"""Internal/public sonic-mgmt history resolution without switching the caller's checkout."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ngts.scripts.regression_mail.models import GitResolution
from ngts.scripts.regression_mail.normalization import normalize_version


_TRAIN = re.compile(r"^(?:SONiC\.)?(\d{6})_RC\.")
_PUBLIC_REPO = "https://github.com/sonic-net/sonic-mgmt.git"


class GitHistoryResolver:
    """Resolve an exact stable-patch match and prepare an isolated source worktree."""

    def __init__(
        self,
        repo_root: Path,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        public_repo: str = _PUBLIC_REPO,
        history_limit: int = 500,
    ):
        self.repo_root = repo_root
        self.runner = runner
        self.public_repo = public_repo
        self.history_limit = history_limit

    def resolve(self, version: str) -> GitResolution:
        train = _release_train(version)
        self._git("rev-parse", "--show-toplevel")
        internal_branch = "develop-{}".format(train)
        run_key = "{}-{}".format(os.getpid(), train)
        internal_ref = "refs/regression-mail/{}/internal".format(run_key)
        temporary_refs = [internal_ref]
        self._git(
            "fetch",
            "--no-tags",
            "origin",
            "+refs/heads/{0}:{1}".format(internal_branch, internal_ref),
            timeout=300,
        )
        internal_hash = self._git("rev-parse", internal_ref).stdout.strip()

        try:
            candidates = self._public_branch_candidates(train)
            internal_patch_ids = self._patch_ids(internal_ref)
            internal_commits = self._lines(
                self._git(
                    "rev-list",
                    "--max-count={}".format(self.history_limit),
                    "--no-merges",
                    internal_ref,
                ).stdout
            )
        except Exception:
            self._delete_refs(temporary_refs)
            raise

        matched: Optional[Tuple[str, str, str]] = None
        for public_branch in candidates:
            public_ref = "refs/regression-mail/{}/public/{}".format(
                run_key,
                public_branch.replace("/", "_"),
            )
            try:
                self._git(
                    "fetch",
                    "--no-tags",
                    self.public_repo,
                    "+refs/heads/{0}:{1}".format(public_branch, public_ref),
                    timeout=300,
                )
            except subprocess.CalledProcessError:
                continue
            temporary_refs.append(public_ref)
            try:
                public_by_patch = self._patch_ids(public_ref)
            except Exception:
                continue
            for commit in internal_commits:
                patch_id = internal_patch_ids.get(commit)
                if patch_id and patch_id in public_by_patch:
                    matched = (public_branch, public_by_patch[patch_id], commit)
                    break
            if matched:
                break

        if not matched:
            self._delete_refs(temporary_refs)
            raise RuntimeError(
                "no exact stable patch-ID match found between {} and public sonic-mgmt history".format(
                    internal_branch
                )
            )
        public_branch, public_hash, internal_match = matched
        additional = []
        for commit in internal_commits:
            if commit == internal_match:
                break
            additional.append(commit)

        source_root = Path(
            tempfile.mkdtemp(
                prefix=".regression-mail-worktree-{}-".format(os.getpid()),
                dir=str(self.repo_root),
            )
        )
        shutil.rmtree(source_root)
        try:
            self._git("worktree", "add", "--detach", str(source_root), internal_ref, timeout=300)
        except Exception:
            shutil.rmtree(source_root, ignore_errors=True)
            self._delete_refs(temporary_refs)
            raise
        return GitResolution(
            internal_branch=internal_branch,
            internal_hash=internal_hash,
            public_branch=public_branch,
            public_hash=public_hash,
            source_root=source_root,
            additional_commit_hashes=additional,
            temporary_refs=temporary_refs,
        )

    def cleanup(self, resolution: Optional[GitResolution]) -> None:
        if not resolution or not resolution.source_root:
            return
        try:
            self._git("worktree", "remove", "--force", str(resolution.source_root), timeout=120)
        except Exception:
            shutil.rmtree(resolution.source_root, ignore_errors=True)
        self._delete_refs(resolution.temporary_refs)

    def _public_branch_candidates(self, train: str) -> List[str]:
        completed = self.runner(
            ["git", "ls-remote", "--heads", self.public_repo],
            cwd=str(self.repo_root),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        branches = []
        for line in completed.stdout.splitlines():
            ref = line.split("\t")[-1]
            if not ref.startswith("refs/heads/"):
                continue
            branch = ref[len("refs/heads/") :]
            if re.fullmatch(r"\d{6}", branch) and branch <= train:
                branches.append(branch)
        branches = sorted(set(branches), reverse=True)[:12]
        if "master" not in branches:
            branches.append("master")
        return branches

    def _patch_ids(self, ref: str) -> Dict[str, str]:
        log = subprocess.Popen(
            [
                "git",
                "log",
                "--no-merges",
                "--format=%H",
                "-p",
                "--max-count={}".format(self.history_limit),
                ref,
            ],
            cwd=str(self.repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        patch = subprocess.Popen(
            ["git", "patch-id", "--stable"],
            cwd=str(self.repo_root),
            stdin=log.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if log.stdout is not None:
            log.stdout.close()
        patch_stdout, patch_stderr = patch.communicate(timeout=300)
        _, log_stderr = log.communicate(timeout=300)
        if log.returncode or patch.returncode:
            detail = (log_stderr or b"").decode("utf-8", errors="replace")
            detail += patch_stderr or ""
            raise RuntimeError("git patch-id failed: {}".format(detail.strip()))
        by_commit: Dict[str, str] = {}
        by_patch: Dict[str, str] = {}
        for line in patch_stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2:
                patch_id, commit = fields[0], fields[1]
                by_commit[commit] = patch_id
                by_patch[patch_id] = commit
        if ref.endswith("/internal"):
            return by_commit
        return by_patch

    def _git(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return self.runner(
            ["git", *args],
            cwd=str(self.repo_root),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )

    def _delete_refs(self, refs: Sequence[str]) -> None:
        for ref in refs:
            try:
                self._git("update-ref", "-d", ref, timeout=30)
            except Exception:
                pass

    @staticmethod
    def _lines(value: str) -> List[str]:
        return [line.strip() for line in value.splitlines() if line.strip()]


def _release_train(version: str) -> str:
    match = _TRAIN.match(normalize_version(version))
    if not match:
        raise ValueError("cannot derive sonic-mgmt release train from {!r}".format(version))
    return match.group(1)
