from __future__ import annotations

import io
import json
import subprocess
import unittest

from ngts.scripts.regression_mail.jenkins import JenkinsPrClient
from ngts.scripts.regression_mail.regression_api import _extract_coverage, _extract_pass_rate


class _Response(io.BytesIO):
    def __init__(self, value=b"", headers=None):
        super().__init__(value)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class ExternalAdapterTest(unittest.TestCase):
    def test_dashboard_metrics_follow_contract_denominator(self) -> None:
        self.assertEqual(
            75.0,
            _extract_pass_rate(
                {
                    "groups": [
                        {"passed": 6, "failed": 2, "skipped": 100, "rmSkipped": 50},
                        {"passed": 3, "failed": 1},
                    ]
                }
            ),
        )
        self.assertEqual(88.5, _extract_coverage({"coverage": {"totals": {"coverage": "88.5"}}}))

    def test_jenkins_reads_current_jobs_fixed_csv_for_exact_build(self) -> None:
        calls = []

        def opener(request, timeout):
            url = request.full_url if hasattr(request, "full_url") else request
            calls.append(url)
            if url == "https://jenkins/crumbIssuer/api/json":
                self.assertEqual(
                    "Basic YnVpbGQtdXNlcjp0b2tlbg==",
                    request.headers["Authorization"],
                )
                return _Response(
                    json.dumps(
                        {
                            "crumbRequestField": "Jenkins-Crumb",
                            "crumb": "crumb-value",
                        }
                    ).encode(),
                    headers={"Set-Cookie": "JSESSIONID=node-1; Path=/; Secure"},
                )
            if "buildWithParameters" in url:
                self.assertEqual(
                    "Basic YnVpbGQtdXNlcjp0b2tlbg==",
                    request.headers["Authorization"],
                )
                self.assertEqual("crumb-value", request.headers["Jenkins-crumb"])
                self.assertEqual("JSESSIONID=node-1", request.headers["Cookie"])
                return _Response(headers={"Location": "https://jenkins/queue/item/7/"})
            if url == "https://jenkins/queue/item/7/api/json":
                return _Response(json.dumps({"executable": {"number": 42}}).encode())
            if url == "https://jenkins/job/report/42/api/json":
                return _Response(json.dumps({"building": False, "result": "SUCCESS"}).encode())
            raise AssertionError(url)

        def runner(args, **kwargs):
            self.assertIn("fit74", args)
            self.assertIn(
                "/tmp/csv/Github_sonic_open_pull_requests.csv",
                args[-1],
            )
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=(
                    b"broken,csv,https://github.com/sonic-net/sonic-mgmt/pull/123\n"
                    b"https://github.com/other/repo/pull/1\n"
                ),
                stderr=b"",
            )

        result = JenkinsPrClient(
            "https://jenkins/job/report",
            "/tmp/csv/Github_sonic_open_pull_requests.csv",
            "fit74",
            opener=opener,
            sleep=lambda seconds: None,
            runner=runner,
            username="build-user",
            api_token="token",
        ).collect(["alice", "bob"], "yanpengz@nvidia.com")
        self.assertEqual(42, result.build_number)
        self.assertEqual(
            "/tmp/csv/Github_sonic_open_pull_requests.csv",
            result.remote_path,
        )
        self.assertEqual(
            ["https://github.com/sonic-net/sonic-mgmt/pull/123"],
            result.pr_urls,
        )
        self.assertFalse(any("lastSuccessfulBuild" in call for call in calls))
        build_call = next(call for call in calls if "buildWithParameters" in call)
        self.assertIn("ORG_NAME=&", build_call)
        self.assertIn("OVERWRITE_USERS=alice%0Abob", build_call)
        self.assertIn("LITE=false", build_call)
        self.assertIn("EMAIL_RECIPIENTS=yanpengz%40nvidia.com", build_call)
        self.assertNotIn("FILE_PATH=", build_call)
        self.assertNotIn("REPO_NAME=", build_call)
        self.assertNotIn("NO_EMAIL=", build_call)

    def test_jenkins_rejects_unsafe_csv_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "safe absolute"):
            JenkinsPrClient("https://jenkins/job/report", "../result.csv", "fit74")


if __name__ == "__main__":
    unittest.main()
