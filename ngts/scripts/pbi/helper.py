from __future__ import annotations

from argparse import Namespace
from collections import defaultdict
import dataclasses
import datetime
import json
import logging
from pathlib import Path
import re

import requests

from ngts.nvos_constants.constants_nvos import OperationTimeConsts
from ngts.scripts.allure_reporter import ALLURE_PROJECT_ID_SUFFIX
from ngts.tools.mars_test_cases_results.Connect_to_MSSQL import ConnectMSSQL

logger = logging.getLogger(__name__)

_BUG_URL_PREFIX: str = "https://redmine.mellanox.com/issues/"
_ALLURE_DOCKER_SERVICE: str = "allure-docker-service"
_ALLURE_STATUSES = {"passed", "failed", "broken", "skipped", "unknown"}
_LA_TEST_REAL_OUTCOME = re.compile(r"la_failed\(.*outcome=(%s).+" % "|".join(_ALLURE_STATUSES))
_BUG_HANDLER_OUTPUT_MARKER = "Bug Handler Output:"
_ALLURE_BUG_HANDLER_TRACE_MARKER = "Allure step: Run Bug Handler on Log Analyzer error"
_LA_LOG_LINE_TS = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\]")
_PATH_TO_UPLOAD_URL: Path = Path("/auto/sw_system_project/NVOS_INFRA/verification_files/")

_TEST_ANALYTICS_COLUMNS_QUERY = f"""\
    INSERT test_analytics (
        {OperationTimeConsts.SETUP_COL},
        suite_path,
        test_name,
        status,
        session_id,
        {OperationTimeConsts.DATE_COL},
        dut_hwsku,
        report_url,
        branch,
        version,
        duration
    )
    VALUES {{values}};
"""

_REGRESSION_MATRIX_COLUMNS_QUERY = f"""\
    INSERT regression_matrix (
        {OperationTimeConsts.SETUP_COL},
        pass_rate,
        version,
        executed,
        session_id,
        report_url,
        {OperationTimeConsts.DATE_COL},
        dut_hwsku,
        branch
    )
    VALUES {{values}};
"""


_LA_BUG_COLUMNS_QUERY = f"""\
INSERT INTO la_bugs (
    test_name,
    test_url,
    test_runtime_mins,
    session_id,
    {OperationTimeConsts.SETUP_COL},
    setup_mins,
    test_body_mins,
    teardown_mins,
    la_runtime_mins,
    nvos_version,
    branch,
    {OperationTimeConsts.DATE_COL},

    -- Bug Level Data (The "Nested" Data)
    bug_id,
    bug_url,
    occurrences,
    bug_handler_runtime_mins
)
VALUES {{values}};
"""


@dataclasses.dataclass
class TestResult:
    suite_path: str
    test_name: str
    status: str
    duration: float
    test_url: str

    def to_db_values(self, setup_name: str, session_id: str, dut_hwsku: str, branch: str, target_version: str) -> str:
        escaped_url = self.test_url.replace("'", "''") if self.test_url is not None else ""
        return (
            f"('{setup_name}', '{self.suite_path}', '{self.test_name}', '{self.status}', '{session_id}', "
            f"'{datetime.date.today()!s}', '{dut_hwsku}', '{escaped_url}', '{branch}', '{target_version}', "
            f"'{self.duration}')"
        )


@dataclasses.dataclass
class LABug:
    test_name: str
    test_url: str
    test_runtime_mins: float
    setup_mins: float
    test_body_mins: float
    teardown_mins: float
    la_runtime_mins: float
    bug_id: str
    occurrences: int
    bug_handler_runtime_mins: float

    def to_db_values(self, session_id: str, setup_name: str, target_version: str, branch: str) -> str:
        return (
            f"('{self.test_name}', '{self.test_url}', {self.test_runtime_mins}, '{session_id}', '{setup_name}', {self.setup_mins}, "
            f"{self.test_body_mins}, {self.teardown_mins}, {self.la_runtime_mins}, "
            f"'{target_version}', '{branch}', '{datetime.date.today()!s}', "
            f"'{self.bug_id}', '{_BUG_URL_PREFIX}{self.bug_id}', '{self.occurrences}', {self.bug_handler_runtime_mins})"
        )


@dataclasses.dataclass
class Summary:
    report_url: str
    pass_rate: str = "N/A"
    executed: str = "N/A"
    passed: int = 0
    failed: int = 0
    la_failed: int = 0
    broken: int = 0
    unknown: int = 0
    skipped: int = 0

    def to_db_values(self, setup_name: str, target_version: str, session_id: str, dut_hwsku: str, branch: str) -> str:
        return (
            f"('{setup_name}', '{self.pass_rate}', '{target_version}', '{self.executed}', '{session_id}', "
            f"'{self.report_url}', '{datetime.date.today()!s}', '{dut_hwsku}', '{branch}')"
        )

    def summarize_test_run(tests: list[TestResult], report_url: str) -> Summary:
        summary = Summary(report_url=report_url)

        for t in tests:
            status = t.status
            if status == "passed":
                summary.passed += 1
            elif status == "LA_failed":
                summary.la_failed += 1
            elif status == "skipped":
                summary.skipped += 1
            elif status == "failed":
                summary.failed += 1
            elif status == "broken":
                summary.broken += 1
            else:
                summary.unknown += 1

        total_fail = summary.failed + summary.la_failed + summary.broken + summary.unknown
        total_count_for_pass_rate = summary.passed + total_fail

        summary.pass_rate = (summary.passed / total_count_for_pass_rate) * 100.0 if total_count_for_pass_rate > 0 else 0.0
        summary.executed = f"{summary.passed}/{summary.passed + summary.failed + summary.la_failed} ({summary.broken + summary.unknown + summary.skipped})"

        logger.info(f"Passed = {summary.passed}")
        logger.info(f"Failed = {summary.failed}")
        logger.info(f"LA Failed = {summary.la_failed}")
        logger.info(f"Broken = {summary.broken}")
        logger.info(f"Unknown = {summary.unknown}")
        logger.info(f"Skipped = {summary.skipped}")
        logger.info(f"Pass Rate = {summary.pass_rate}%")
        logger.info(f"Executed = {summary.executed}")

        return summary


class Args(Namespace):
    setup_name: str
    session_id: str
    target_version: str
    branch: str
    dut_hwsku: str
    allure_server_addr: str

    @property
    def allure_project_id(self) -> str:
        return self.setup_name.replace("_", "-").lower() + ALLURE_PROJECT_ID_SUFFIX

    @property
    def allure_server_base_url(self) -> str:
        return f"{self.allure_server_addr}/{_ALLURE_DOCKER_SERVICE}"


class Parser:
    @staticmethod
    def parse_branch_name(tarball_name: str) -> str:
        if not (match := re.search(r"nvos_ver-\d{2}-\d{2}-\d{4}", tarball_name)):
            match = re.search(r"develop", tarball_name)
        if match:
            return match.group(0)
        return ""

    @staticmethod
    def parse_version(version_file_path: str) -> str:
        version = version_file_path.split("/")[-1].split(".bin")[0]
        marker = "nvos-amd64-"
        if marker in version:
            version = version.split(marker)[1]
        return version

    @staticmethod
    def parse_timestamp(timestamp: str) -> datetime.datetime | None:
        for time_format in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.datetime.strptime(timestamp, time_format)
            except ValueError:
                continue
        return None

    @staticmethod
    def parse_allure_step(test: TestResult, base_url: str, stage: str, step_name: str) -> dict | None:
        test_uid = test.test_url.rstrip("/").split("/")[-1]
        test_resp = requests.get(f"{base_url}/data/test-cases/{test_uid}.json")
        test_resp.raise_for_status()
        test_json = test_resp.json()

        parsed_step = None
        for curr_stage in test_json.get(stage) or []:
            stage_name = (curr_stage.get("name") or "").lower()
            if step_name in stage_name:
                if curr_stage.get("attachments"):
                    parsed_step = curr_stage.get("attachments")[0]
                break
        return parsed_step

    @staticmethod
    def parse_suites(
        node: dict[str, str | list[dict]], base_url: str, suite_chain: list[str], results: list[TestResult]
    ) -> list[TestResult]:
        current_name = node.get("name", "Unknown")
        new_chain = suite_chain + [current_name]

        for child in node.get("children", []):
            if "status" in child:
                test_uid = child.get("uid", "")
                test_url = f"{base_url}/index.html#testresult/{test_uid}" if test_uid else None

                status = child["status"]
                logger.debug(f"{child['name']:<70} - {status}")
                logger.debug(f"Tags: {child.get('tags', [])}")
                la_actual_status = LaHelper.extract_la_actual_status(child.get("tags", []))
                if la_actual_status == "passed":
                    status = "LA_failed"

                results.append(
                    TestResult(
                        suite_path=" > ".join(new_chain),
                        test_name=child["name"],
                        status=status,
                        duration=child["time"]["duration"] / 60000,
                        test_url=test_url,
                    )
                )
            else:
                Parser.parse_suites(child, base_url, new_chain, results)

        return results


class SqlHelper:
    @staticmethod
    def sql_str(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    @staticmethod
    def sql_float(value: float | None) -> str:
        return "NULL" if value is None else str(float(value))


class AllureHelper:
    @staticmethod
    def get_stage_runtime_mins(test: TestResult, base_url: str) -> tuple[float, float, float]:
        """
            Returns (setup, test_body, teardown) in minutes: beforeStages, testStage, afterStages.
        """
        test_uid = test.test_url.rstrip("/").split("/")[-1]
        test_resp = requests.get(f"{base_url}/data/test-cases/{test_uid}.json")
        test_resp.raise_for_status()
        test_json = test_resp.json()

        before_ms = after_ms = body_ms = 0

        before_ms = sum(s.get("time").get("duration", 0) for s in (test_json.get("beforeStages") or []))
        body_ms = sum(s.get("time").get("duration", 0) for s in (test_json.get("testStage").get("steps") or []))
        after_ms = sum(s.get("time").get("duration", 0) for s in (test_json.get("afterStages") or []))

        return before_ms / 60000.0, body_ms / 60000.0, after_ms / 60000.0

    @staticmethod
    def get_allure_step_runtime_mins(test: TestResult, base_url: str, stage: str, step_name: str | None = None) -> float:
        test_uid = test.test_url.rstrip("/").split("/")[-1]
        test_resp = requests.get(f"{base_url}/data/test-cases/{test_uid}.json")
        test_resp.raise_for_status()
        test_json = test_resp.json()

        steps = test_json.get(stage) or []
        if step_name is None:
            total_ms = sum(s.get("time", {}).get("duration", 0) for s in steps)
            return total_ms / 60000.0

        for step in steps:
            name_lower = (step.get("name") or "").lower()
            if step_name.lower() in name_lower:
                return step.get("time", {}).get("duration", 0) / 60000.0
        return 0.0


class DataBaseHelper:
    @staticmethod
    def insert_regression_matrix_data_to_pbi_db(args: Args, mssql_connection_obj: ConnectMSSQL, summary: Summary) -> None:
        values = summary.to_db_values(args.setup_name, args.target_version, args.session_id, args.dut_hwsku, args.branch)
        logger.info("Inserting data to regression_matrix table")

        try:
            mssql_connection_obj.query_insert(q := _REGRESSION_MATRIX_COLUMNS_QUERY.format(values=values))
            logger.info(f"Query: {q}")
            logger.info("--------- insert to regression_matrix DB table successfully ---------\n")
        except Exception as e:
            print(f"FAILED TO INSERT DATA TO REGRESSION_MATRIX, ERROR: {e}")

    @staticmethod
    def insert_test_analytics_data_to_pbi_db(args: Args, mssql_connection_obj: ConnectMSSQL, parsed_results: list[TestResult]) -> None:
        values = ""
        for result in parsed_results:
            value = result.to_db_values(args.setup_name, args.session_id, args.dut_hwsku, args.branch, args.target_version)
            values = f"{values}, {value}" if values else value

        if values:
            logger.info("Inserting data to test_analytics table")
            try:
                mssql_connection_obj.query_insert(q := _TEST_ANALYTICS_COLUMNS_QUERY.format(values=values))
                logger.info(f"Query: {q}")
                logger.info("--------- insert to test_analytics DB table successfully ---------\n")
            except Exception as e:
                print(f"FAILED TO INSERT DATA TO TEST_ANALYTICS, ERROR: {e}")


class LaHelper:
    @staticmethod
    def parse_loganalyzer_bugs(tests: list[TestResult], base_url: str) -> list[LABug]:
        result: list[LABug] = []

        for test in tests:
            loganalyzer_step = Parser.parse_allure_step(test, base_url, "afterStages", "loganalyzer::0")
            if not loganalyzer_step:
                continue
            src = loganalyzer_step["source"]
            r = requests.get(f"{base_url}/data/attachments/{src}")
            r.raise_for_status()
            loganalyzer_log = r.text

            slices = LaHelper._get_bug_handler_trace_slices(loganalyzer_log)
            if not slices:
                continue

            bugs_occurrences: defaultdict[str, int] = defaultdict(int)
            bug_handler_runtime_mins: defaultdict[str, float] = defaultdict(float)

            for start, end in slices:
                trace = loganalyzer_log[start - 30:end]
                trace_handling_mins = LaHelper._trace_handling_runtime_mins(trace)
                for bug_id_str in LaHelper._iter_bug_handler_output_segments(trace):
                    bug_id = int(bug_id_str)
                    bugs_occurrences[bug_id] += 1
                    bug_handler_runtime_mins[bug_id] = bug_handler_runtime_mins.get(bug_id, 0.0) + trace_handling_mins

            setup_mins, test_body_mins, teardown_mins = AllureHelper.get_stage_runtime_mins(test, base_url)
            loganalyzer_runtime_mins = AllureHelper.get_allure_step_runtime_mins(test, base_url, "afterStages", "loganalyzer::0")

            for bug_id, occurrences in bugs_occurrences.items():
                result.append(
                    LABug(
                        test_name=test.test_name,
                        test_url=test.test_url,
                        test_runtime_mins=setup_mins + test_body_mins + teardown_mins,
                        setup_mins=setup_mins,
                        test_body_mins=test_body_mins,
                        teardown_mins=teardown_mins,
                        la_runtime_mins=loganalyzer_runtime_mins,
                        bug_id=bug_id,
                        occurrences=occurrences,
                        bug_handler_runtime_mins=bug_handler_runtime_mins.get(bug_id),
                    )
                )

        return result

    @staticmethod
    def insert_loganalyzer_bugs_data_to_pbi_db(
        args: Args,
        mssql_connection_obj: ConnectMSSQL,
        loganalyzer_bugs_summary: list[LABug],
    ) -> None:

        values = ""
        for bug in loganalyzer_bugs_summary:
            value = bug.to_db_values(args.session_id, args.setup_name, args.target_version, args.branch)
            values = f"{values}, {value}" if values else value

        if values:
            logger.info("Inserting data to test_analytics table")
            try:
                mssql_connection_obj.query_insert(q := _LA_BUG_COLUMNS_QUERY.format(values=values))
                logger.info(f"Query: {q}")
                logger.info("--------- insert to loganalyzer_bug DB table successfully ---------\n")
            except Exception as e:
                print(f"FAILED TO INSERT DATA TO LOGANALYZER_BUG, ERROR: {e}")

    @staticmethod
    def extract_la_actual_status(tags: list[str]) -> str | None:
        for tag in tags:
            if match := _LA_TEST_REAL_OUTCOME.match(tag):
                logger.info(f"LA actual status: {match.group(1).lower()}")
                return match.group(1).lower()
        return None

    # ***********************************************************************************************
    # * Private Methods                                                                           *
    # ***********************************************************************************************

    @staticmethod
    def _get_bug_handler_trace_slices(la_log: str) -> list[tuple[int, int]] | None:
        starts = LaHelper._collect_marker_positions(la_log, _ALLURE_BUG_HANDLER_TRACE_MARKER)
        if not starts:
            return None
        out: list[tuple[int, int]] = []
        for j, s in enumerate(starts):
            e = starts[j + 1] if j + 1 < len(starts) else len(la_log)
            out.append((s, e))
        return out

    @staticmethod
    def _trace_handling_runtime_mins(chunk: str) -> float:
        stamps: list[datetime.datetime] = []
        for m in _LA_LOG_LINE_TS.finditer(chunk):
            parsed = Parser.parse_timestamp(m.group(1))
            if parsed is not None:
                stamps.append(parsed)
        if not stamps or len(stamps) == 1:
            return 0.0
        tmp = max(stamps) - min(stamps)
        mins = (max(stamps) - min(stamps)).total_seconds() / 60
        return round((max(stamps) - min(stamps)).total_seconds() / 60, 2)

    @staticmethod
    def _iter_bug_handler_output_segments(text: str) -> list[str]:
        out: list[str] = []
        pos = 0
        while True:
            idx = text.find(_BUG_HANDLER_OUTPUT_MARKER, pos)
            if idx < 0:
                break
            brace = text.find("{", idx + len(_BUG_HANDLER_OUTPUT_MARKER))
            if brace < 0:
                pos = idx + len(_BUG_HANDLER_OUTPUT_MARKER)
                continue
            end = LaHelper._json_object_end(text, brace)
            if end is None:
                pos = idx + len(_BUG_HANDLER_OUTPUT_MARKER)
                continue
            try:
                payload = json.loads(text[brace:end])
            except json.JSONDecodeError:
                pos = brace + 1
                continue
            if isinstance(payload, dict):
                raw = payload.get("bug_id")
                if raw is not None and raw != "":
                    out.append(str(raw).strip())
            pos = end
        return out

    @staticmethod
    def _collect_marker_positions(log: str, marker: str) -> list[int]:
        starts: list[int] = []
        pos = 0
        len_m = len(marker)
        while True:
            i = log.find(marker, pos)
            if i < 0:
                break
            starts.append(i)
            pos = i + len_m
        return starts

    @staticmethod
    def _json_object_end(text: str, open_brace_idx: int) -> int | None:
        depth = 0
        in_str = False
        esc = False
        str_quote: str | None = None
        for i in range(open_brace_idx, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == str_quote:
                    in_str = False
                continue
            if c in "\"'":
                in_str = True
                str_quote = c
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
        return None
