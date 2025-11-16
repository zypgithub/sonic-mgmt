import logging
from typing import Dict, List, Optional

from typing_extensions import Union
from urllib.parse import urlencode, parse_qs

import requests

from ngts.scripts.code_coverage.code_coverage_consts import SharedConsts


logger = logging.getLogger(__name__)


class JenkinsParamsFormatter:
    """
    Helper to build and normalize Jenkins parameter strings.
    """

    def from_query_string(self, job_params: str) -> Dict[str, str]:
        logger.info(f"Original Jenkins parameters: {job_params}")
        items = parse_qs(job_params)
        clean_params: Dict[str, str] = {}
        for key, values in items.items():
            value = values[0] if values else ""
            clean_params[key] = self._normalize_path(value)
        logger.info(f"Cleaned parameters: {clean_params}")
        return clean_params

    def to_query_string(self, params: Dict[str, str]) -> str:
        normalized = self.normalize_params(params)
        return urlencode(normalized)

    def normalize_params(self, params: Dict[str, str]) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        for key, value in params.items():
            val = value if value is not None else ""
            val = self._normalize_path(val)
            normalized[key] = val
        return normalized

    def _normalize_path(self, value: str) -> str:
        # Remove double slashes in paths
        while '//' in value:
            value = value.replace('//', '/')
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
        self.jenkins_url = jenkins_base_url.rstrip('/') + '/' + project_job_path.lstrip('/').rstrip('/')
        self.user = user
        self.api_token = api_token
        self.status_code_success = status_code_success
        self.request_timeout = request_timeout
        self.verify_ssl = verify_ssl

    def trigger(self, job_name: str, params: Dict[str, str]) -> int:
        url = f"{self.jenkins_url}/{job_name}/buildWithParameters"
        response = requests.post(
            url,
            params=params,
            auth=(self.user, self.api_token),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=self.request_timeout,
            verify=self.verify_ssl,
        )
        logger.info("Triggered Jenkins job successfully '%s' -> %s", job_name, response.status_code)
        if response.status_code != self.status_code_success:
            logger.error("Jenkins response (%s): %s", response.status_code, response.text)
            raise RuntimeError(f"Failed to trigger Jenkins job '{job_name}'. Status code: {response.status_code}")
        return response.status_code

    def trigger_with_query(self, job_name: str, query: str, formatter: Optional[JenkinsParamsFormatter] = None) -> int:
        if formatter is None:
            formatter = JenkinsParamsFormatter()
        params = formatter.from_query_string(query)
        return self.trigger(job_name, params)


class JenkinsQueryBuilder:
    def __init__(
        self,
        formatter: Optional[JenkinsParamsFormatter] = None,
    ):
        self._params: Dict[str, str] = {}
        self._formatter = formatter or JenkinsParamsFormatter()

    def add(self, key: str, value: Union[str, int, None]) -> "JenkinsQueryBuilder":
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

    def version(self, value: Union[int, str]) -> "JenkinsQueryBuilder":
        return self.add("VERSION", value)

    def hits_files_dir(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("HITS_FILES_DIR", value)

    def token(self, value: str) -> "JenkinsQueryBuilder":
        return self.add("token", value)

    def mailing_list(self, value: List[str]) -> "JenkinsQueryBuilder":
        return self.add("MAILING_LIST", ",".join(value))

    def from_query(self, query: str) -> "JenkinsQueryBuilder":
        self._params.update(self._formatter.from_query_string(query))
        return self

    def as_dict(self) -> Dict[str, str]:
        return self._formatter.normalize_params(self._params)

    def build(self) -> str:
        return self._formatter.to_query_string(self._params)
