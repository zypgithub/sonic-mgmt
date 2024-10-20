
import logging
from contextlib import contextmanager
from typing import Dict
from ngts.nvos_constants.constants_nvos import HealthConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
logger = logging.getLogger()


def get_issues() -> Dict[str, str]:
    return OutputParsingTool.parse_json_str_to_dictionary(System().health.show()).get_returned_value()[HealthConsts.ISSUES]


class HealthStatus:
    def __init__(self):
        self.baseline_issues = get_issues()

    def compare(self):
        issues = get_issues()
        assert issues.keys() <= self.baseline_issues.keys(), (
            f"Found unexpected health issues. Baseline health issues were: {self.baseline_issues}\n"
            f"But current issues are: {issues}")


@contextmanager
def check_health_baseline():
    """
    Context manager for asserting that the device health at the end of the test is not worse than at the beginning.
    The intended use-case is for tests where we want to assert the health is ok at the end of the test, but we wish
    to ignore "background issues" that may have existed before the test even started (due to some unrelated bug).
    It will make sure that no *new* health issues exist at the end that did not exist at the beginning, and can also
    check the health on-demand in-between. Usage example:
        with check_health_baseline() as baseline:
            # do some actions ...
            baseline.compare()  # make sure there are currently no new issues that did not previously exist
            # do more actions
        # when exiting the 'with' block, check again that there are currently no new issues
    """
    baseline = HealthStatus()
    yield baseline
    baseline.compare()  # This line is not reached if there was any error inside the 'with' clause
