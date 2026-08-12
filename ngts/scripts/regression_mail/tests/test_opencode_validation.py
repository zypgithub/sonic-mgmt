from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from ngts.scripts.regression_mail.grouping import build_deterministic_report
from ngts.scripts.regression_mail.models import ResultRow, SemanticGroup, SemanticReport, WorkbookSnapshot
from ngts.scripts.regression_mail.opencode import (
    OpenCodeClient,
    _chunk_report,
    validate_semantic_report,
)
from ngts.scripts.regression_mail.rc_status import parse_rc_status


VERSION = "202608_RC.17-deadbeef_Internal"


def _row(record_id: str, result: str, test_name: str) -> ResultRow:
    return ResultRow(
        record_id=record_id,
        excel_row=2,
        session_id="s",
        mars_key_id=record_id,
        testbed="tb",
        test_name=test_name,
        sanitized_testname=test_name,
        result=result,
        message="reason",
        topology="t0",
        host="dut",
        asic="spc",
        platform="x86",
        hwsku="sku",
        os_version=VERSION,
    )


def _snapshot() -> WorkbookSnapshot:
    return WorkbookSnapshot(
        source_path=Path("/tmp/results.xlsx"),
        sheet_name="community_tests",
        header_row=1,
        headers=(),
        selected_rows=[
            _row("failure-1", "fail", "tests/a.py::test_a[x]"),
            _row("skip-1", "skipped", "tests/b.py::test_b"),
        ],
        result_counts={"fail": 1, "pass": 0, "skipped": 1},
        hardware_pairs=[],
    )


class OpenCodeValidationTest(unittest.TestCase):
    def test_chunks_large_group_sets_without_loss(self) -> None:
        deterministic = build_deterministic_report(_snapshot())
        chunks = _chunk_report(deterministic, limit=1)
        self.assertEqual(2, len(chunks))
        self.assertEqual(1, len(chunks[0].failure_groups))
        self.assertEqual(1, len(chunks[1].skip_groups))

    def test_processes_independent_chunks_in_parallel(self) -> None:
        rows = [
            _row("failure-{}".format(index), "fail", "tests/test_{}.py::test_case".format(index))
            for index in range(51)
        ]
        snapshot = WorkbookSnapshot(
            source_path=Path("/tmp/results.xlsx"),
            sheet_name="community_tests",
            header_row=1,
            headers=(),
            selected_rows=rows,
            result_counts={"fail": len(rows), "pass": 0, "skipped": 0},
            hardware_pairs=[],
        )
        deterministic = build_deterministic_report(snapshot)
        barrier = threading.Barrier(2)
        event = json.dumps(
            {
                "type": "text",
                "part": {
                    "text": json.dumps(
                        {
                            "schema_version": 1,
                            "failure_groups": [],
                            "skip_groups": [],
                            "internal_error_groups": [],
                            "executive_summary": "",
                        }
                    )
                },
            }
        )

        def runner(args, **kwargs):
            barrier.wait(timeout=5)
            return subprocess.CompletedProcess(args, 0, stdout=event + "\n", stderr="")

        report = OpenCodeClient(
            command="opencode",
            model="model",
            repo_root=Path.cwd(),
            timeout=30,
            parallelism=2,
            runner=runner,
        ).analyze(VERSION, snapshot, None, None, deterministic)

        self.assertEqual(51, len(report.failure_groups))

    def test_parses_json_events_and_validates_partition(self) -> None:
        snapshot = _snapshot()
        deterministic = build_deterministic_report(snapshot)
        payload = {
            "schema_version": "1",
            "failure_groups": [
                {
                    "group_id": "f1",
                    "member_ids": [deterministic.failure_groups[0].group_id],
                    "test_display": "tests/a.py::test_a[*]",
                    "testbeds": ["tb"],
                    "comments": "Known human conclusion",
                    "internal_comments": "Known human conclusion",
                    "redmine_urls": [],
                }
            ],
            "skip_groups": [
                {
                    "group_id": "s1",
                    "member_ids": [deterministic.skip_groups[0].group_id],
                    "test_display": "tests/b.py::test_b",
                    "testbeds": ["tb"],
                    "comments": "reason",
                    "internal_comments": "",
                    "redmine_urls": [],
                }
            ],
            "internal_error_groups": [],
            "executive_summary": "",
        }
        event = json.dumps(
            {
                "type": "text",
                "part": {"text": json.dumps(payload)},
            }
        )
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout=event + "\n", stderr="")

        client = OpenCodeClient(
            command="opencode",
            model="model",
            repo_root=Path.cwd(),
            timeout=30,
            runner=runner,
        )
        report = client.analyze(VERSION, snapshot, None, None, deterministic)
        self.assertEqual(["failure-1"], report.failure_groups[0].member_ids)
        self.assertEqual(1, len(calls))
        self.assertIn("--format", calls[0])
        self.assertIn("json", calls[0])

    def test_restores_model_omitted_source_group(self) -> None:
        snapshot = _snapshot()
        deterministic = build_deterministic_report(snapshot)
        payload = {
            "schema_version": 1,
            "failure_groups": [
                {
                    "group_id": "f1",
                    "member_ids": [deterministic.failure_groups[0].group_id],
                    "test_display": "tests/a.py::test_a[*]",
                    "testbeds": ["tb"],
                    "comments": "",
                    "internal_comments": "",
                    "redmine_urls": [],
                }
            ],
            "skip_groups": [],
            "internal_error_groups": [],
            "executive_summary": "",
        }
        event = json.dumps(
            {"type": "text", "part": {"text": json.dumps(payload)}}
        )
        client = OpenCodeClient(
            command="opencode",
            model="model",
            repo_root=Path.cwd(),
            timeout=30,
            runner=lambda args, **kwargs: subprocess.CompletedProcess(
                args,
                0,
                stdout=event + "\n",
                stderr="",
            ),
        )
        report = client.analyze(
            VERSION,
            snapshot,
            None,
            None,
            deterministic,
        )
        self.assertEqual(["skip-1"], report.skip_groups[0].member_ids)
        self.assertTrue(report.skip_groups[0].group_id.startswith("chunk-1-fallback-"))

    def test_rejects_redmine_leak_in_comments(self) -> None:
        snapshot = _snapshot()
        report = SemanticReport(
            failure_groups=[
                SemanticGroup(
                    group_id="f",
                    member_ids=["failure-1"],
                    test_display="test",
                    testbeds=["tb"],
                    comments="See Redmine #123",
                )
            ],
            skip_groups=[
                SemanticGroup(
                    group_id="s",
                    member_ids=["skip-1"],
                    test_display="skip",
                    testbeds=["tb"],
                )
            ],
        )
        with self.assertRaisesRegex(ValueError, "leaked"):
            validate_semantic_report(report, snapshot)

    def test_rc_status_requires_exact_tag(self) -> None:
        markdown = """
# RC status

- **RC branch:** `202608_RC`
- **Tag:** `202608_RC.17`
- **Upstream base:** `deadbeef`

https://github.com/sonic-net/sonic-buildimage/pull/123
"""
        status = parse_rc_status(markdown, VERSION)
        self.assertEqual("202608_RC.17", status.tag)
        self.assertEqual("202608_RC", status.image_branch)
        self.assertEqual("deadbeef", status.image_public_hash)
        self.assertEqual(
            ["https://github.com/sonic-net/sonic-buildimage/pull/123"],
            status.image_pr_urls,
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            parse_rc_status(markdown, "202608_RC.18-other_Internal")


if __name__ == "__main__":
    unittest.main()
