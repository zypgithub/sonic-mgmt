from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from ngts.scripts.regression_mail.config import Settings
from ngts.scripts.regression_mail.grouping import build_deterministic_report
from ngts.scripts.regression_mail.mail import CapturingTransport
from ngts.scripts.regression_mail.models import (
    DashboardSnapshot,
    GitResolution,
    RcStatus,
    ResultRow,
    RunRequest,
    WorkbookSnapshot,
)
from ngts.scripts.regression_mail.pipeline import PipelineDependencies, run
from ngts.scripts.regression_mail.rendering import ReportRenderer


VERSION = "202608_RC.17-deadbeef_Internal"


class _Workbook:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def load(self, path, version):
        if isinstance(self.snapshot, Exception):
            raise self.snapshot
        return self.snapshot


class _Dashboard:
    def fetch(self, version):
        return DashboardSnapshot(coverage=91.2, pass_rate=98.4)


class _Rc:
    def fetch(self, version):
        return RcStatus(tag=version, image_branch="202608_RC", image_public_hash="deadbeef")


class _Git:
    def __init__(self):
        self.cleaned = False

    def resolve(self, version):
        return GitResolution(
            internal_branch="develop-202608",
            internal_hash="abc",
            public_branch="202605",
            public_hash="def",
        )

    def cleanup(self, resolution):
        self.cleaned = True


class _Unused:
    def __getattr__(self, name):
        raise AssertionError("{} must not be called".format(name))


class _OpenCode:
    def __init__(self, error=None):
        self.error = error

    def analyze(self, version, workbook, rc_status, git, deterministic):
        if self.error:
            raise self.error
        return deterministic


class _Artifacts:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.cleaned = False

    def write_skips(self, workbook, semantic):
        path = self.directory / "skips.json"
        path.write_text("{}\n", encoding="utf-8")
        return path

    def build_attachment(self, workbook, semantic):
        path = self.directory / "results_with_internal_comments.xlsx"
        path.write_bytes(b"xlsx")
        return path

    def cleanup_attachment(self, path):
        self.cleaned = True


class _FailingTransport:
    def send(self, message, request):
        raise RuntimeError("SMTP unavailable")


class _BrokenRenderer:
    def render(self, report):
        raise RuntimeError("HTML failed")

    def minimal(self, report, error):
        raise RuntimeError("minimal renderer failed")


def _snapshot(path: Path) -> WorkbookSnapshot:
    row = ResultRow(
        record_id="failure-1",
        excel_row=2,
        session_id="s",
        mars_key_id="k",
        testbed="tb",
        test_name="tests/a.py::test_a",
        sanitized_testname="tests/a.py::test_a",
        result="fail",
        message="failure",
        topology="t0",
        host="dut",
        asic="spc",
        platform="x86",
        hwsku="sku",
        os_version=VERSION,
    )
    return WorkbookSnapshot(
        source_path=path,
        sheet_name="community_tests",
        header_row=1,
        headers=(),
        selected_rows=[row],
        result_counts={"pass": 0, "fail": 1, "skipped": 0},
        hardware_pairs=[("sku", "t0")],
        row_comments={"failure-1": "Existing engineer analysis"},
    )


def _settings(repo_root: Path) -> Settings:
    return Settings(
        smtp_host="smtp.invalid",
        smtp_port=25,
        sender="sender@nvidia.com",
        model="model",
        api_base_url="https://dashboard.invalid",
        jenkins_url="https://jenkins.invalid/job/report",
        jenkins_csv_path="/tmp/csv/Github_sonic_open_pull_requests.csv",
        jenkins_ssh_host="fit74",
        jenkins_ssh_user="",
        jenkins_authors=(),
        jenkins_user="",
        jenkins_api_token="",
        opencode_command="opencode",
        opencode_timeout_seconds=30,
            opencode_parallelism=2,
        http_timeout_seconds=30,
        jenkins_timeout_seconds=30,
        repo_root=repo_root,
        log_path=None,
    )


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.request = RunRequest(
            excel_path=root / "results.xlsx",
            version=VERSION,
            to=("owner@nvidia.com",),
            cc=("reviewer@nvidia.com",),
        )
        self.settings = _settings(root)

    def _dependencies(self, transport, opencode=None, workbook=None):
        git = _Git()
        artifacts = _Artifacts(self.temp_dir.name)
        dependencies = PipelineDependencies(
            workbook=_Workbook(workbook or _snapshot(self.request.excel_path)),
            dashboard=_Dashboard(),
            rc_status=_Rc(),
            git=git,
            github=_Unused(),
            jenkins=_Unused(),
            opencode=opencode or _OpenCode(),
            artifacts=artifacts,
            renderer=ReportRenderer(),
            transport=transport,
        )
        return dependencies, git, artifacts

    def test_full_success_is_silent_and_delivers_attachment(self) -> None:
        transport = CapturingTransport()
        dependencies, git, artifacts = self._dependencies(transport)
        stderr = io.StringIO()
        result = run(self.request, self.settings, dependencies, stderr=stderr)

        self.assertEqual(0, result)
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(1, len(transport.messages))
        message = transport.messages[0][0]
        self.assertEqual("owner@nvidia.com", message["To"])
        self.assertEqual("reviewer@nvidia.com", message["Cc"])
        self.assertTrue(any(part.get_filename() for part in message.iter_attachments()))
        self.assertTrue(git.cleaned)
        self.assertTrue(artifacts.cleaned)

    def test_opencode_failure_sends_deterministic_degraded_message(self) -> None:
        transport = CapturingTransport()
        dependencies, _, _ = self._dependencies(
            transport,
            opencode=_OpenCode(RuntimeError("invalid model output")),
        )
        stderr = io.StringIO()
        result = run(self.request, self.settings, dependencies, stderr=stderr)

        self.assertEqual(5, result)
        self.assertEqual(1, len(transport.messages))
        self.assertIn("degraded mode", stderr.getvalue())
        self.assertIn("[Degraded]", transport.messages[0][0]["Subject"])

    def test_invalid_excel_still_sends_minimal_report(self) -> None:
        transport = CapturingTransport()
        dependencies, _, _ = self._dependencies(
            transport,
            workbook=ValueError("no matching rows"),
        )
        stderr = io.StringIO()
        result = run(self.request, self.settings, dependencies, stderr=stderr)
        self.assertEqual(3, result)
        self.assertEqual(1, len(transport.messages))

    def test_smtp_failure_overrides_generation_status(self) -> None:
        dependencies, _, _ = self._dependencies(_FailingTransport())
        stderr = io.StringIO()
        result = run(self.request, self.settings, dependencies, stderr=stderr)
        self.assertEqual(6, result)
        self.assertIn("delivery failed", stderr.getvalue())

    def test_renderer_failure_uses_hardcoded_minimal_message(self) -> None:
        transport = CapturingTransport()
        dependencies, _, _ = self._dependencies(transport)
        dependencies.renderer = _BrokenRenderer()
        stderr = io.StringIO()
        result = run(self.request, self.settings, dependencies, stderr=stderr)
        self.assertEqual(3, result)
        message = transport.messages[0][0]
        self.assertIn("Generation Errors", message.get_body(preferencelist=("plain",)).get_content())


if __name__ == "__main__":
    unittest.main()
