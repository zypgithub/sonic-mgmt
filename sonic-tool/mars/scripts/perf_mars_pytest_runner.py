#!/usr/bin/env python

# Built-in modules
import sys

from canonical_mars_pytest_runner import RunPytest


class RunPerfPytest(RunPytest):
    """Backwards-compatibility alias.

    The MARS monitor "mini case summary" functionality this class used to
    add is now part of the canonical ``RunPytest``. Kept so existing MARS
    steps that invoke perf_mars_pytest_runner.py keep working.
    """


if __name__ == "__main__":
    run_perf_pytest = RunPerfPytest("RunPerfPytest")
    run_perf_pytest.execute(sys.argv[1:])
