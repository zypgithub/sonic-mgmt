#!/usr/bin/env python

# Built-in modules
import sys
import re

from reg2_wrapper.test_wrapper.standalone_wrapper import StandaloneWrapper

from canonical_mars_pytest_runner import RunPytest


class RunPerfPytest(RunPytest):
    """Performance-verification variant of RunPytest.

    Adds the MARS monitor "mini case summary" feature so that the MARS
    statistics for performance tests reflect the underlying pytest
    passed/failed/skipped counts instead of the single wrapper case.
    See: https://nvidia.atlassian.net/wiki/spaces/SW/pages/2899328410
    Prerequisites: MARS 4.4.3 / Ver SDK 1.4.185 (April 2025) or later.
    """

    def run_pre_commands(self):
        rc = super(RunPerfPytest, self).run_pre_commands() or 0
        if hasattr(self, 'enable_mini_case_summary'):
            self.enable_mini_case_summary()
        else:
            self.Logger.info(
                "mini_case_summary: SDK does not expose enable_mini_case_summary(); "
                "feature disabled (requires MARS 4.4.3 / Ver SDK 1.4.185+).")
        return rc

    def run_commands(self):
        rc = super(RunPerfPytest, self).run_commands()
        self._update_mini_case_summary()
        return rc

    def run_post_commands(self):
        # RunPytest.run_post_commands does not chain to super(), which
        # skips the SDK base post-commands where the mini case summary
        # is finalized retroactively from the case log. Call the SDK
        # base first (so the summary is written even if the allure
        # upload below raises), then RunPytest's allure upload.
        StandaloneWrapper.run_post_commands(self)
        super(RunPerfPytest, self).run_post_commands()

    def _extract_test_stats_from_output(self, output):
        """Aggregate passed/failed/skipped counts from every pytest summary
        line in the wrapper output.

        Pytest emits its final summary as an "=" framed line, for example:
            ============ 2 passed, 1 failed, 0 skipped in 1.23s =============
        With num_of_processes > 1 the wrapper log can contain several such
        lines, so we sum them.
        """
        totals = {'passed': 0, 'failed': 0, 'skipped': 0}
        for line in output.split('\n'):
            if '=====' not in line:
                continue
            lowered = line.lower()
            if not any(kw in lowered for kw in totals):
                continue
            for kw in totals:
                match = re.search(r'(\d+)\s+' + kw, lowered)
                if match:
                    totals[kw] += int(match.group(1))
        return totals['passed'], totals['failed'], totals['skipped']

    def _update_mini_case_summary(self):
        """Push pytest passed/failed/skipped totals to the MARS monitor
        mini case summary. No-op when the SDK/MARS version is too old."""
        if not hasattr(self, 'set_mini_case_summary'):
            return
        try:
            output = self.get_output() if hasattr(self, 'get_output') else ''
        except Exception as exc:
            self.Logger.warning(
                "mini_case_summary: failed to read wrapper output: {}".format(exc))
            return
        if not output:
            return
        passed, failed, skipped = self._extract_test_stats_from_output(output)
        if passed == failed == skipped == 0:
            self.Logger.info(
                "mini_case_summary: no pytest summary detected; leaving MARS "
                "statistics as a single regular case.")
            return
        self.Logger.info(
            "mini_case_summary: passed={}, failed={}, skipped={}".format(
                passed, failed, skipped))
        self.set_mini_case_summary(passed, failed, skipped)


if __name__ == "__main__":
    run_perf_pytest = RunPerfPytest("RunPerfPytest")
    run_perf_pytest.execute(sys.argv[1:])
