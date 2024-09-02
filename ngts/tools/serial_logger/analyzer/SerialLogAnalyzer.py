"""
If you want to analyze the serial logs for a certain section of code, put it in `with serial_log_analyzer.stage(str)`.
Note that stages cannot be nested within each other.
Log-analysis will be executed when the test ends (not when exiting the context).
"""

import logging
import os
import re
import traceback
from contextlib import contextmanager
from typing import List, Dict, Tuple

from ngts.constants.constants import SerialLoggerConst
from ngts.nvos_tools.infra.ExceptionTool import log_traceback
from ..serial_log_script import get_session_serial_log_path, get_session_serial_logs_dir_path, SerialLogFileReader
# noinspection PyUnresolvedReferences
from tests.common.plugins.loganalyzer.loganalyzer import LogAnalyzer
# noinspection PyUnresolvedReferences
from tests.common.plugins.loganalyzer.bug_handler_helper import log_analyzer_bug_handler


SERIAL_ERRORS_MATCH_FILE = os.path.join(os.path.split(__file__)[0], "serial_errors_match.txt")
SERIAL_ERRORS_IGNORE_FILE = os.path.join(os.path.split(__file__)[0], "serial_errors_ignore.txt")
REGEX_FILE_LINE_FORMAT = {
    '#': lambda pattern: None,
    'i': lambda pattern: re.compile(re.escape(pattern), re.IGNORECASE),
    's': lambda pattern: re.compile(re.escape(pattern)),
    'r': lambda pattern: re.compile(pattern),
}
SERIAL_LOG_ANALYZER_ERROR_MESSAGE = "Error in serial log analyzer. Test will continue but analyzer can't run."
DUTHOSTS_MISSING_MESSAGE = "duthosts fixture not available in this context (this is expected in non-NVOS systems) so " \
                           "bug-handler won't be able to run."


class SerialLogAnalyzer:
    def __init__(self, logging_active: bool, test_name: str, setup_name: str, mars_session_id: str,
                 temp_dir_path, request, target_ip: str, can_analyze: bool = True):
        logging.info(f"Initializing serial log analyzer for {target_ip=}, {setup_name=}")
        self.test_name = test_name
        self.target_ip = target_ip
        self.setup_name = setup_name
        self.mars_session_id = mars_session_id

        self._logging_active = logging_active
        self._request = request
        self._temp_dir_path = temp_dir_path
        self._stages: List[str] = []
        self._ignore_stages = set()
        self._log_dir = get_session_serial_logs_dir_path(setup_name, mars_session_id)
        self._log_path = get_session_serial_log_path(self._log_dir, target_ip)

        self._can_analyze = can_analyze
        if can_analyze:
            try:
                logging.info("Reading serial-error ignore patterns")
                self.ignore_regexes = self.load_regexes(SERIAL_ERRORS_IGNORE_FILE)
                logging.info("Reading serial-error match patterns")
                self.error_regexes = self.load_regexes(SERIAL_ERRORS_MATCH_FILE)
            except Exception as e:
                self._log_exception()
        else:
            logging.error(f"Instance created for unexpected {target_ip=}. Test will continue to run but an exception "
                          f"will be raised when it finishes. Stack trace: {traceback.format_stack()}")

    def _log_exception(self):
        # Must be called inside `except` clause. If there's an error in serial-logger during test, we don't want to stop
        # the test immediately. The test will fail after it ends, once self.analyze() is called.
        self._can_analyze = False
        logging.error(SERIAL_LOG_ANALYZER_ERROR_MESSAGE + "\n" + traceback.format_exc())

    @staticmethod
    def load_regexes(file_path: str) -> List[re.Pattern]:
        """Returns a list of complied regexes. See the regex txt files for documentation."""
        output = []
        with open(file_path) as file:
            lines = file.readlines()
        for line in lines:
            if not line.strip():
                continue  # skip empty lines
            specifier, _, pattern = line.partition(" ")
            try:
                regex = REGEX_FILE_LINE_FORMAT[specifier](pattern.strip())
            except KeyError:
                logging.error(f"Error reading patterns from {file_path}. Each line must begin with one of "
                              f"{list(REGEX_FILE_LINE_FORMAT.keys())} followed by a space, so the following line is "
                              f"illegal: {line}")
                raise
            if regex:
                output.append(regex)
        logging.info("Found regexes: " + str([regex.pattern for regex in output]))
        return output

    @contextmanager
    def stage(self, name: str):
        """See documentation at the top of this file."""
        self._stages.append(name)
        if self._logging_active and self._can_analyze:
            self.inject_log_line(self._stage_start_string(name))
            try:
                yield
            finally:
                self.inject_log_line(self._stage_end_string(name))

        else:
            logging.info(f"Start {name} stage (but serial logging is inactive)")
            yield
            logging.info(f"End {name} stage (but serial logging is inactive)")
            return

    def inject_log_line(self, line: str):
        """Appends line to the serial log file."""
        logging.info(f"On {self.target_ip} injecting the following line to serial logs: {line.strip()}")
        if line[-1] != '\n':
            line += '\n'
        try:
            with open(self._log_path, 'a') as f:
                f.write(line)
        except Exception as e:
            self._log_exception()

    def analyze(self, dut_host, only_check):
        """Finds error messages in the serial log and calls bug-handler."""
        if not self._can_analyze:
            raise Exception(f"Cannot analyze. Search the logs above for '{SERIAL_LOG_ANALYZER_ERROR_MESSAGE}'.")

        logging.info(f"Serial-logger in {self.target_ip} for {self.test_name} - searching for these stages: " +
                     str(self.list_stages(include_ignored=False)))
        errors_by_stage = self.get_errors_by_stage()
        for stage_name, error_lines in errors_by_stage.items():
            logging.info(f"Analyzing serial logs for {stage_name} stage")
            logging.info(f"Found {len(error_lines)} error lines:\n" + ''.join(error_lines))
            if error_lines:
                error_file_path = self._temp_dir_path / f"{self.target_ip.replace('.', '_')}_{stage_name}.json"
                LogAnalyzer.write_errors_to_file(error_file_path, error_lines)

        if dut_host is NotImplemented:  # meaning we're in SONIC
            logging.info(DUTHOSTS_MISSING_MESSAGE)
        elif dut_host is None:
            logging.error("Can't run bug-handler because duthost object doesn't exist, probably due to a network "
                          "error. This could also happen when running the test locally (not in MARS).")
        else:
            logging.info("Starting bug-handler")
            if only_check:
                logging.info("Bug-handler will not open bugs, but will print to the log any found bugs.")
            # Currently serial LA runs only for deploy & upgrade. If it fails the entire regression is canceled;
            # the try-except is here to avoid it.
            try:
                log_analyzer_bug_handler(dut_host, self._request, self._temp_dir_path, only_check, is_serial_log=True)
            except Exception:
                log_traceback()

    def _stage_start_string(self, stage_name: str) -> str:
        return SerialLoggerConst.START_STAGE.format(test=self.test_name, stage=stage_name)

    def _stage_end_string(self, stage_name: str) -> str:
        return SerialLoggerConst.END_STAGE.format(test=self.test_name, stage=stage_name)

    def get_errors_by_stage(self) -> Dict[str, List[str]]:
        """
        Iterates over self.list_stages(include_ignored=False) and returns {stage_name: [error_lines_found_in_stage]}.
        The start- and end-string for each stage must be found in the serial-log file and in the same order as the
        order of self._stages, otherwise EOFError is raised. This is never supposed to happen if everything is managed
        by the self.stage context-manager.
        """
        output = {}
        logging.info(f"Searching for error lines in {self._log_path}")
        with SerialLogFileReader(self._log_path) as f:
            for stage in self.list_stages(include_ignored=False):
                logging.info(f"Scanning serial logs for stage {stage}")
                try:
                    while f.read_line() != self._stage_start_string(stage):
                        pass
                    logging.info(f"Found {self._stage_start_string(stage).strip()}")
                    output[stage] = []
                    line = f.read_line()
                    while line != self._stage_end_string(stage):
                        if self._is_error_line(line):
                            output[stage].append(line)
                        line = f.read_line()
                    logging.info(f"Found {self._stage_end_string(stage).strip()}")
                except EOFError:
                    logging.error("Unexpectedly reached end of serial log file")
                    raise
        return output

    def _is_error_line(self, line: str) -> bool:
        """Returns whether the given line is considered an error message, according to the regexes provided at init."""
        for regex in self.ignore_regexes:
            if regex.search(line):
                logging.info(f"Ignore-pattern '{regex.pattern}' is found in line: {line.strip()}")
                return False
        for regex in self.error_regexes:
            if regex.search(line):
                logging.error(f"Serial-log error found: pattern '{regex.pattern}' is found in line: {line.strip()}")
                return True
        return False

    def list_stages(self, include_ignored=True) -> Tuple[str]:
        """Returns an ordered list of the names of stages defined using `with self.stage()`, except ignored ones."""
        return tuple(stage for stage in self._stages if include_ignored or stage not in self._ignore_stages)

    def ignore_stage(self, stage: str):
        """Instructs the analyzer to ignore the stage with the given name."""
        assert stage in self._stages, f"Stage {stage} is not in the list of stages: {self._stages}"
        self._ignore_stages.add(stage)
        logging.info(f"Stage {stage} will be ignored when the serial log is analyzed for {self.target_ip}")
