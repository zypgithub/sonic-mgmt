import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode

import requests

from ngts.scripts.code_coverage.code_coverage_consts import SharedConsts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JenkinsBuildResult:
    """
    Final Jenkins build status.
    """

    job_name: str
    build_url: str
    build_number: int
    result: str


class JenkinsParamsFormatter:
    """
    Helper to build and normalize Jenkins parameter strings.
    """

    def from_query_string(self, job_params: str) -> dict[str, str]:
        logger.info(f"Original Jenkins parameters: {job_params}")
        items = parse_qs(job_params)
        clean_params: dict[str, str] = {}
        for key, values in items.items():
            value = values[0] if values else ""
            clean_params[key] = self._normalize_path(value)
        logger.info(f"Cleaned parameters: {clean_params}")
        return clean_params

    def to_query_string(self, params: dict[str, str]) -> str:
        normalized = self.normalize_params(params)
        return urlencode(normalized)

    def normalize_params(self, params: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in params.items():
            val = value if value is not None else ""
            val = self._normalize_path(val)
            normalized[key] = val
        return normalized

    def _normalize_path(self, value: str) -> str:
        # Remove double slashes in paths
        while "//" in value:
            value = value.replace("//", "/")
        return value


class JenkinsTool:
    """
    Client to trigger Jenkins jobs with parameters.
    """

    def __init__(
        self,
        jenkins_base_url: str = SharedConsts.JENKINS_BASE_URL,
        project_job_path: str = SharedConsts.JENKINS_SONAR_PROJECT_PATH,
        user: str = SharedConsts.JENKINS_USER,
        api_token: str = SharedConsts.JENKINS_API_TOKEN,
        status_code_success: int = 201,
        request_timeout: int = 30,
        verify_ssl: bool = True,
    ):
        self.jenkins_url = jenkins_base_url.rstrip("/") + "/" + project_job_path.lstrip("/").rstrip("/")
        self.user = user
        self.api_token = api_token
        self.status_code_success = status_code_success
        self.request_timeout = request_timeout
        self.verify_ssl = verify_ssl

    def trigger(self, job_name: str, params: dict[str, str]) -> int:
        response = self._trigger_request(job_name, params)
        status_code = response.status_code
        if status_code is None:
            raise RuntimeError(f"Jenkins did not return a status code for job '{job_name}'")
        return status_code

    def trigger_and_wait(
        self,
        job_name: str,
        params: dict[str, str],
        poll_interval: int = 30,
        timeout: int = 7200,
    ) -> JenkinsBuildResult:
        response = self._trigger_request(job_name, params)
        queue_url = response.headers.get("Location")
        if not queue_url:
            raise RuntimeError(f"Jenkins did not return a queue location for job '{job_name}'")

        logger.info("Jenkins job '%s' queued at %s", job_name, queue_url)
        executable = self._wait_for_queue_executable(queue_url, poll_interval, timeout)
        build_url = executable["url"]
        build_number = int(executable["number"])

        result = self._wait_for_build_result(build_url, poll_interval, timeout)
        return JenkinsBuildResult(
            job_name=job_name,
            build_url=build_url,
            build_number=build_number,
            result=result,
        )

    def trigger_with_query(
        self,
        job_name: str,
        query: str,
        formatter: JenkinsParamsFormatter | None = None,
    ) -> int:
        if formatter is None:
            formatter = JenkinsParamsFormatter()
        params = formatter.from_query_string(query)
        return self.trigger(job_name, params)

    def trigger_with_query_and_wait(
        self,
        job_name: str,
        query: str,
        formatter: JenkinsParamsFormatter | None = None,
        poll_interval: int = 30,
        timeout: int = 7200,
    ) -> JenkinsBuildResult:
        if formatter is None:
            formatter = JenkinsParamsFormatter()
        params = formatter.from_query_string(query)
        return self.trigger_and_wait(job_name, params, poll_interval=poll_interval, timeout=timeout)

    def _trigger_request(self, job_name: str, params: dict[str, str]) -> requests.Response:
        url = f"{self.jenkins_url}/{job_name}/buildWithParameters"
        response = requests.post(
            url,
            params=params,
            auth=(self.user, self.api_token),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.request_timeout,
            verify=self.verify_ssl,
        )
        logger.info("Jenkins trigger response for '%s' -> %s", job_name, response.status_code)
        if response.status_code != self.status_code_success:
            logger.error("Jenkins response (%s): %s", response.status_code, response.text)
            raise RuntimeError(f"Failed to trigger Jenkins job '{job_name}'. Status code: {response.status_code}")
        return response

    def _wait_for_queue_executable(self, queue_url: str, poll_interval: int, timeout: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            queue_info = self._get_json(queue_url)
            if queue_info.get("cancelled"):
                raise RuntimeError(f"Jenkins queue item was cancelled: {queue_url}")
            executable = queue_info.get("executable")
            if executable:
                return executable

            logger.info("Waiting for Jenkins queue item to start: %s", queue_url)
            time.sleep(poll_interval)

        raise TimeoutError(f"Timed out waiting for Jenkins queue item to start: {queue_url}")

    def _wait_for_build_result(self, build_url: str, poll_interval: int, timeout: int) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            build_info = self._get_json(build_url)
            if not build_info.get("building", False):
                result = build_info.get("result")
                if not result:
                    raise RuntimeError(f"Jenkins build finished without a result: {build_url}")
                logger.info("Jenkins build finished: %s result=%s", build_url, result)
                return result

            logger.info("Waiting for Jenkins build to finish: %s", build_url)
            time.sleep(poll_interval)

        raise TimeoutError(f"Timed out waiting for Jenkins build to finish: {build_url}")

    def _get_json(self, url: str) -> dict[str, Any]:
        api_url = url.rstrip("/") + "/api/json"
        response = requests.get(
            api_url,
            auth=(self.user, self.api_token),
            timeout=self.request_timeout,
            verify=self.verify_ssl,
        )
        if response.status_code != 200:
            logger.error("Jenkins response (%s): %s", response.status_code, response.text)
            raise RuntimeError(f"Failed to get Jenkins API data from '{api_url}'. Status code: {response.status_code}")
        return response.json()


class JenkinsQueryBuilder:
    def __init__(
        self,
        formatter: JenkinsParamsFormatter | None = None,
    ):
        self._params: dict[str, str] = {}
        self._formatter = formatter or JenkinsParamsFormatter()

    def add(self, key: str, value: str | int | None) -> "JenkinsQueryBuilder":
        self._params[key] = "" if value is None else str(value)
        return self

    def project(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("PROJECT", value)

    def coverage_folder(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("COVERAGE_FOLDER", value)

    def branch(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("BRANCH", value)

    def commit_id(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("COMMIT_ID", value)

    def version(self, value: int | str) -> "JenkinsQueryBuilder":
        return self.add("VERSION", value)

    def hits_files_dir(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("HITS_FILES_DIR", value)

    def token(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("token", value)

    def mailing_list(self, value: list[str]) -> "JenkinsQueryBuilder":
        return self.add("MAILING_LIST", ",".join(value))

    def from_query(self, query: str) -> "JenkinsQueryBuilder":
        self._params.update(self._formatter.from_query_string(query))
        return self

    def as_dict(self) -> dict[str, str]:
        return self._formatter.normalize_params(self._params)

    def build(self) -> str:
        return self._formatter.to_query_string(self._params)

    def include_file_path(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("INCLUDE_FILE_PATH", value)

    def exclude_file_path(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("EXCLUDE_FILE_PATH", value)
