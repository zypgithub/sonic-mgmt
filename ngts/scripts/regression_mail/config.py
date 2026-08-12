"""Environment-backed configuration for regression mail."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class Settings:
    """Runtime settings that do not expand the public CLI surface."""

    smtp_host: str
    smtp_port: int
    sender: str
    model: str
    api_base_url: str
    jenkins_url: str
    jenkins_csv_path: str
    jenkins_ssh_host: str
    jenkins_ssh_user: str
    jenkins_authors: Tuple[str, ...]
    jenkins_user: str
    jenkins_api_token: str
    opencode_command: str
    opencode_timeout_seconds: int
    opencode_parallelism: int
    http_timeout_seconds: int
    jenkins_timeout_seconds: int
    repo_root: Path
    log_path: Optional[Path]

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        values = os.environ if env is None else env
        default_repo_root = Path(__file__).resolve().parents[3]
        log_value = values.get("REGRESSION_MAIL_LOG_PATH", "").strip()
        return cls(
            smtp_host=values.get("REGRESSION_MAIL_SMTP_HOST", "mailgw.nvidia.com").strip(),
            smtp_port=_positive_int(values, "REGRESSION_MAIL_SMTP_PORT", 25),
            sender=values.get(
                "REGRESSION_MAIL_SENDER",
                "nbu-system-sw-sonic-ver@exchange.nvidia.com",
            ).strip(),
            model=values.get(
                "REGRESSION_MAIL_MODEL",
                "nvidia-hub/azure/openai/gpt-5.6-sol",
            ).strip(),
            api_base_url=values.get(
                "REGRESSION_MAIL_API_BASE_URL",
                "https://regression-report.mec01-asgard.nvidia.com",
            ).rstrip("/"),
            jenkins_url=values.get(
                "REGRESSION_MAIL_JENKINS_URL",
                "https://nbuprod.blsm.nvidia.com/nbu-sws-sonic/job/sonic_github_pr_report",
            ).rstrip("/"),
            jenkins_csv_path=values.get(
                "REGRESSION_MAIL_JENKINS_CSV_PATH",
                "/tmp/csv/Github_sonic_open_pull_requests.csv",
            ).strip(),
            jenkins_ssh_host=values.get(
                "REGRESSION_MAIL_JENKINS_SSH_HOST",
                "fit74",
            ).strip(),
            jenkins_ssh_user=values.get(
                "REGRESSION_MAIL_JENKINS_SSH_USER",
                "",
            ).strip(),
            jenkins_authors=_csv_values(
                values.get("REGRESSION_MAIL_JENKINS_AUTHORS", "")
            ),
            jenkins_user=values.get(
                "REGRESSION_MAIL_JENKINS_USER",
                "",
            ).strip(),
            jenkins_api_token=values.get(
                "REGRESSION_MAIL_JENKINS_API_TOKEN",
                "",
            ).strip(),
            opencode_command=values.get("REGRESSION_MAIL_OPENCODE", "opencode").strip(),
            opencode_timeout_seconds=_positive_int(values, "REGRESSION_MAIL_OPENCODE_TIMEOUT", 900),
            opencode_parallelism=_positive_int(
                values,
                "REGRESSION_MAIL_OPENCODE_PARALLELISM",
                10,
            ),
            http_timeout_seconds=_positive_int(values, "REGRESSION_MAIL_HTTP_TIMEOUT", 60),
            jenkins_timeout_seconds=_positive_int(values, "REGRESSION_MAIL_JENKINS_TIMEOUT", 1800),
            repo_root=Path(values.get("REGRESSION_MAIL_REPO_ROOT", str(default_repo_root))).resolve(),
            log_path=Path(log_value).expanduser() if log_value else None,
        )


def _positive_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name)
    if raw is None or not str(raw).strip():
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError("{} must be a positive integer".format(name))
    return value


def _csv_values(value: str) -> Tuple[str, ...]:
    result = []
    for item in value.replace("\n", ",").split(","):
        normalized = item.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return tuple(result)
