import logging
import re
import time
from datetime import datetime

import allure
from retry import retry

from ngts.nvos_constants.constants_nvos import HealthConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.system.Files import Files

logger = logging.getLogger()


class Health(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/health')
        self.history = History(self)
        self.component = Component(self)

    @retry(Exception, tries=12, delay=30)
    def wait_until_health_status_change_after_reboot(self, expected_status):
        output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        assert output[HealthConsts.STATUS] == expected_status, f"health should be {expected_status} within 5 minutes after reboot"


class History(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/history')
        self.files = Files(self)

    def show(self, param='', exit_cmd='q'):
        with allure.step('Execute nv show system health history {param} and exit cmd {exit_cmd}'.format(param=param,
                                                                                                        exit_cmd=exit_cmd)):
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].show_health_report,
                                                   TestToolkit.get_engine(), self.get_resource_path(), param,
                                                   exit_cmd).get_returned_value()

    def show_health_report_file(self, file=HealthConsts.HEALTH_FIRST_FILE, exit_cmd='q'):
        return self.show(param="files {}".format(file), exit_cmd=exit_cmd)

    def search_line(self, line_to_search, file_output=None):
        if not file_output:
            file_output = self.show()
        return re.findall(line_to_search, file_output)

    @staticmethod
    def _parse_log_date(line):
        """Extract datetime from a health log line. Returns None if not parseable."""
        match = re.search(r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})', line)
        if not match:
            return None
        return datetime.strptime(f"{datetime.now().year} {match.group(1)}", "%Y %b %d %H:%M:%S")

    def _filter_lines_by_date(self, patterns, since_date, file_output):
        """Return log lines that match any pattern and are on or after since_date."""
        return [line.strip() for line in file_output.splitlines()
                if any(re.search(p, line) for p in patterns) and
                (self._parse_log_date(line) or datetime.min) >= since_date]

    def search_line_by_date(self, lines_to_search, since_date, expect_found=True, file_output=None):
        """Search for lines in health history filtered by date.

        Args:
            lines_to_search: a single regex pattern (str) or a list of regex patterns.
            since_date: datetime object - only lines on or after this date are considered.
            expect_found: if True, assert all patterns found; if False, assert none found.
            file_output: optional pre-fetched output; fetched via show() if None.
        """
        if isinstance(lines_to_search, str):
            lines_to_search = [lines_to_search]
        if not file_output:
            file_output = self.show()

        matched_lines = self._filter_lines_by_date(lines_to_search, since_date, file_output)

        if expect_found:
            missing = [p for p in lines_to_search if not any(re.search(p, m) for m in matched_lines)]
            assert not missing, \
                f"Expected all patterns to appear after {since_date}, but not found: {missing}"
        else:
            assert not matched_lines, \
                f"Expected '{lines_to_search}' NOT to appear after {since_date}, but found: {matched_lines}"

        logger.info(f"Found {len(matched_lines)} lines matching '{lines_to_search}' since {since_date}")
        return matched_lines

    def get_last_status_from_health_file(self, file_output=None):
        last_status = self.search_line(HealthConsts.ADD_STATUS_TO_SUMMARY_REGEX, file_output)
        assert len(last_status) > 0, "Didn't find summary line in the health history file"
        last_status = last_status[-1]
        logger.info("last status line is: \n {}".format(last_status))
        return HealthConsts.NOT_OK if HealthConsts.NOT_OK in last_status else HealthConsts.OK

    def wait_until_health_history_file_rotation(self, engine):
        with allure.step("Restart logrotate service..."):
            engine.run_cmd("sudo systemctl restart logrotate")
        time.sleep(10)
        line = self.search_line("health_history file deleted, creating new file")
        assert len(line) > 0, "expected a new health file to be created, but it was not generated"

    @retry(Exception, tries=10, delay=60)
    def validate_new_summary_line_in_history_file_after_boot(self, last_summary_line):
        health_history_output = self.show()
        assert self.search_line(HealthConsts.SUMMARY_REGEX_OK, health_history_output)[
            -1] != last_summary_line, "Didn't print new summary line after boot"
        assert "Monitoring service reboot, clearing issues history." in health_history_output, "expected a new summary line after boot, but it was missing"

    @retry(Exception, tries=12, delay=30)
    def retry_get_health_history_file_summary_line(self, summary_regex=HealthConsts.SUMMARY_REGEX_OK):
        return self.search_line(summary_regex)[-1]


class Component(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/component')
