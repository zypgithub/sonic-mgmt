"""Jenkins PR-report execution, remote CSV retrieval, and GitHub validation."""

from __future__ import annotations

import base64
import json
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterable, List, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ngts.scripts.regression_mail.models import JenkinsArtifact, PullRequest


_MGMT_PR = re.compile(r"https://github\.com/sonic-net/sonic-mgmt/pull/\d+")
_EXACT_MGMT_PR = re.compile(r"^https://github\.com/sonic-net/sonic-mgmt/pull/\d+$")
_SAFE_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9_./-]+\.csv$")


class JenkinsPrClient:
    """Run the existing shared job and immediately read its fixed CSV."""

    def __init__(
        self,
        job_url: str,
        csv_path: str,
        ssh_host: str,
        ssh_user: str = "",
        username: str = "",
        api_token: str = "",
        timeout: int = 1800,
        poll_interval: int = 10,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.job_url = job_url.rstrip("/")
        self.csv_path = _validate_csv_path(csv_path)
        self.ssh_host = ssh_host.strip()
        self.ssh_user = ssh_user.strip()
        self.username = username.strip()
        self.api_token = api_token.strip()
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.opener = opener
        self.sleep = sleep
        self.runner = runner

    def collect(
        self,
        authors: Sequence[str],
        email_recipient: str = "",
    ) -> JenkinsArtifact:
        normalized = _unique(author.strip() for author in authors if author.strip())
        if not normalized:
            raise ValueError("Jenkins PR report requires at least one GitHub login author")
        if not self.ssh_host:
            raise ValueError("Jenkins SSH host must not be empty")

        parameters = {
            "ORG_NAME": "",
            "OVERWRITE_USERS": "\n".join(normalized),
            "LITE": "false",
        }
        if email_recipient.strip():
            parameters["EMAIL_RECIPIENTS"] = email_recipient.strip()
        params = urlencode(parameters)
        request = Request(
            self.job_url + "/buildWithParameters?" + params,
            data=b"",
            headers=self._crumb_headers(),
            method="POST",
        )
        with self.opener(request, timeout=60) as response:
            queue_url = response.headers.get("Location", "").rstrip("/")
        if not queue_url:
            raise RuntimeError("Jenkins did not return a queue item URL")

        deadline = time.monotonic() + self.timeout
        build_number = self._wait_for_build_number(queue_url, deadline)
        build_url = "{}/{}".format(self.job_url, build_number)
        self._wait_for_completion(build_url, deadline)
        content = self._read_remote(self.csv_path)
        return JenkinsArtifact(
            build_number=build_number,
            build_url=build_url,
            remote_path=self.csv_path,
            pr_urls=_unique(_MGMT_PR.findall(content)),
        )

    def _read_remote(self, remote_path: str) -> str:
        target = "{}@{}".format(self.ssh_user, self.ssh_host) if self.ssh_user else self.ssh_host
        script = (
            "from pathlib import Path; import sys; "
            "p=Path(sys.argv[1]); "
            "data=p.read_bytes() if p.is_file() and p.stat().st_size else "
            "(_ for _ in ()).throw(RuntimeError('CSV missing or empty')); "
            "sys.stdout.buffer.write(data)"
        )
        remote_command = "python3 -c {} {}".format(
            shlex.quote(script),
            shlex.quote(remote_path),
        )
        completed = self.runner(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=30",
                target,
                remote_command,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        return completed.stdout.decode("utf-8", errors="replace")

    def _crumb_headers(self) -> Mapping[str, str]:
        url = self.job_url.split("/job/", 1)[0] + "/crumbIssuer/api/json"
        request = Request(url, headers=self._authentication_headers())
        with self.opener(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
            cookie = response.headers.get("Set-Cookie", "").split(";", 1)[0].strip()
        if not isinstance(payload, Mapping):
            raise ValueError("Jenkins crumb endpoint returned a non-object response")
        field = str(payload.get("crumbRequestField") or "").strip()
        value = str(payload.get("crumb") or "").strip()
        if not field or not value:
            raise RuntimeError("Jenkins did not return a valid CSRF crumb")
        headers = dict(self._authentication_headers())
        headers[field] = value
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _authentication_headers(self) -> Mapping[str, str]:
        if bool(self.username) != bool(self.api_token):
            raise ValueError(
                "Jenkins username and API token must be configured together"
            )
        if not self.username:
            return {}
        value = "{}:{}".format(self.username, self.api_token).encode("utf-8")
        return {
            "Authorization": "Basic " + base64.b64encode(value).decode("ascii")
        }

    def _wait_for_build_number(self, queue_url: str, deadline: float) -> int:
        while time.monotonic() < deadline:
            payload = self._get_json(queue_url + "/api/json")
            if payload.get("cancelled"):
                raise RuntimeError("Jenkins queue item was cancelled")
            executable = payload.get("executable") or {}
            if executable.get("number") is not None:
                return int(executable["number"])
            self.sleep(self.poll_interval)
        raise TimeoutError("timed out waiting for Jenkins queue item")

    def _wait_for_completion(self, build_url: str, deadline: float) -> None:
        while time.monotonic() < deadline:
            payload = self._get_json(build_url + "/api/json")
            if not payload.get("building", False):
                result = payload.get("result")
                if result != "SUCCESS":
                    raise RuntimeError("Jenkins build finished with result {!r}".format(result))
                return
            self.sleep(self.poll_interval)
        raise TimeoutError("timed out waiting for Jenkins build")

    def _get_json(self, url: str) -> Mapping[str, Any]:
        with self.opener(url, timeout=60) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("Jenkins returned a non-object JSON response")
        return value


class GitHubClient:
    """Fetch authoritative metadata for exact public sonic-mgmt PR URLs."""

    def __init__(
        self,
        gh_command: str = "gh",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.gh_command = gh_command
        self.runner = runner

    def get_mgmt_prs(self, urls: Iterable[str]) -> List[PullRequest]:
        result: List[PullRequest] = []
        for url in _unique(urls):
            if not _EXACT_MGMT_PR.fullmatch(url):
                raise ValueError("non-public or non-sonic-mgmt PR URL rejected: {!r}".format(url))
            completed = self.runner(
                [
                    self.gh_command,
                    "pr",
                    "view",
                    url,
                    "--json",
                    "url,title,author,state,baseRefName",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            payload = json.loads(completed.stdout)
            if payload.get("url") != url:
                raise ValueError("GitHub metadata URL mismatch for {!r}".format(url))
            author = payload.get("author") or {}
            result.append(
                PullRequest(
                    url=url,
                    title=str(payload.get("title") or "").strip(),
                    author=str(author.get("login") or "").strip(),
                    state=str(payload.get("state") or "").strip(),
                    base_branch=str(payload.get("baseRefName") or "").strip(),
                )
            )
        return result

    def pr_urls_from_commits(self, repo_root: Path, commits: Sequence[str]) -> List[str]:
        urls: List[str] = []
        for commit in commits:
            completed = self.runner(
                ["git", "show", "-s", "--format=%B", commit],
                cwd=str(repo_root),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            urls.extend(_MGMT_PR.findall(completed.stdout))
        return _unique(urls)


def _validate_csv_path(value: str) -> str:
    path = value.strip()
    if not _SAFE_REMOTE_PATH.fullmatch(path) or ".." in path.split("/"):
        raise ValueError("Jenkins CSV path must be a safe absolute .csv path")
    return path


def _unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
