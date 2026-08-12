from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ngts.scripts.regression_mail.cli import main


class CliTest(unittest.TestCase):
    def test_accepts_only_documented_arguments_and_is_silent(self) -> None:
        captured = {}

        def runner(request, settings):
            captured["request"] = request
            return 0

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(
                [
                    "--excel",
                    "/tmp/results.xlsx",
                    "--version",
                    "202608_RC.17-deadbeef_Internal",
                    "--to",
                    "owner@nvidia.com",
                    "--cc",
                    "reviewer@nvidia.com",
                ],
                runner=runner,
            )

        self.assertEqual(0, result)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(("owner@nvidia.com",), captured["request"].to)
        self.assertEqual(("reviewer@nvidia.com",), captured["request"].cc)

    def test_rejects_header_injection_before_runner(self) -> None:
        called = []
        stderr = io.StringIO()
        with self.assertRaises(SystemExit) as context, redirect_stderr(stderr):
            main(
                [
                    "--excel",
                    "/tmp/results.xlsx",
                    "--version",
                    "202608_RC.17-deadbeef_Internal",
                    "--to",
                    "owner@nvidia.com\nBcc: attacker@example.com",
                ],
                runner=lambda request, settings: called.append(request),
            )
        self.assertEqual(2, context.exception.code)
        self.assertFalse(called)

    def test_rejects_unknown_public_option(self) -> None:
        stderr = io.StringIO()
        with self.assertRaises(SystemExit) as context, redirect_stderr(stderr):
            main(
                [
                    "--excel",
                    "/tmp/results.xlsx",
                    "--version",
                    "202608_RC.17-deadbeef_Internal",
                    "--to",
                    "owner@nvidia.com",
                    "--dry-run",
                ],
            )
        self.assertEqual(2, context.exception.code)


if __name__ == "__main__":
    unittest.main()
