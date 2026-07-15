#!/usr/bin/env python

# Built-in modules
import sys
import re

from reg2_wrapper.common.error_code import ErrorCode
from reg2_wrapper.utils.parser.cmd_argument import RunningStage
from reg2_wrapper.test_wrapper.standalone_wrapper import StandaloneWrapper

from sig_term_handler.handler_mixin import TermHandlerMixin
from lib.utils import get_allure_project_id
import time

ErrorCode.NO_COLLECTION = 5


class RunPytest(TermHandlerMixin, StandaloneWrapper):

    def configure_parser(self):
        super(RunPytest, self).configure_parser()

        # Client arguments
        self.add_cmd_argument("--setup_name", required=True, dest="setup_name",
                              help="Specify setup name, for example: SONiC_tigris_r-tigris-06")
        self.add_cmd_argument("--sonic-topo", required=False, dest="sonic_topo",
                              help="Topology for SONiC testing, for example: t0, t1, t1-lag, ptf32, etc.")
        self.add_cmd_argument("--test_script", required=True, dest="test_script",
                              help="Path to the test script, example: /workspace/tests/")
        self.add_cmd_argument("--raw_options", nargs="?", default="", dest="raw_options",
                              help="All the other options that to be passed to py.test")
        self.add_cmd_argument("--test_type", required=False, default="", dest="test_type",
                              help="Decide the pytest marker we want to use in the CI test")
        self.add_cmd_argument("--dut_hwsku", required=False, default="", dest="dut_hwsku",
                              help="DUT hwsku")

        self.junit_report_file = None

    def run_pre_commands(self):
        """Enable the MARS monitor "mini case summary" feature so that the
        MARS statistics reflect the underlying pytest passed/failed/skipped
        counts instead of the single wrapper case.
        See: https://nvidia.atlassian.net/wiki/spaces/SW/pages/2899328410
        Prerequisites: MARS 4.4.3 / Ver SDK 1.4.185 (April 2025) or later.
        """
        rc = super(RunPytest, self).run_pre_commands()
        if hasattr(self, 'enable_mini_case_summary'):
            self.enable_mini_case_summary()
        else:
            self.Logger.info(
                "mini_case_summary: SDK does not expose enable_mini_case_summary(); "
                "feature disabled (requires MARS 4.4.3 / Ver SDK 1.4.185+).")
        return rc

    def run_commands(self):
        rc = ErrorCode.SUCCESS

        if self.test_type:
            if self.test_type != "default":
                self.raw_options = re.sub(r" -m \".+\"", "", self.raw_options)
                self.raw_options = re.sub(r" -m \S+", "", self.raw_options)
            if self.test_type == "yaml":
                self.raw_options += " -m yaml"

        if '--alluredir' not in self.raw_options:
            self.raw_options += ' --alluredir="/tmp/allure-results" '

        # Produce a junit xml report as the authoritative source for the mini
        # case summary counts. A single report path cannot be shared by
        # concurrent pytest processes, so with num_of_processes > 1 we rely on
        # the pytest terminal summary fallback instead.
        if self.num_of_processes == 1 and not any(
                opt in self.raw_options for opt in ('--junitxml', '--junit-xml')):
            self.junit_report_file = '/tmp/junit_{}_{}.xml'.format(self.session_id, self.mars_key_id)
            self.raw_options += ' --junitxml="{}"'.format(self.junit_report_file)

        # Append --remote_test_path only for NVOS tests that declare this option
        # to avoid pytest parse failures in other projects.
        if getattr(self, 'remote_test_path', None) and 'tests_nvos' in str(self.test_script):
            self.raw_options += f' --remote_test_path="{self.remote_test_path}"'

        self.target_cli_type = None
        allure_project_id_suffix = ""
        if "--target_cli_type" in self.raw_options:
            self.target_cli_type = re.search(r"--target_cli_type=(DVS|Sonic|NVUE)", self.raw_options).group(1)
            ip = "ipv6" if "is_ipv6" in self.raw_options else "ipv4"
            allure_project_id_suffix = "{}-{}".format(self.target_cli_type, ip)
        allure_project = get_allure_project_id(self.setup_name, self.test_script,
                                               allure_project_id_suffix=allure_project_id_suffix)
        random_seed = int(time.time())
        if self.sonic_topo:
            cmd_template = '/ngts_venv/bin/pytest {} --setup_name={} --dut_hwsku={} --sonic-topo={} --session_id={} --mars_key_id={} {} ' \
                           '--dynamic_update_skip_reason --allure_server_project_id={} --random_seed={} ' \
                           '--store_la_logs --ignore_la_failure'
            cmd = cmd_template.format(self.test_script, self.setup_name, self.dut_hwsku, self.sonic_topo, self.session_id,
                                      self.mars_key_id, self.raw_options, allure_project, random_seed)
        else:
            cmd_template = '/ngts_venv/bin/pytest {} --setup_name={} --dut_hwsku={} --session_id={} --mars_key_id={} {} ' \
                           '--dynamic_update_skip_reason --allure_server_project_id={} --random_seed={} ' \
                           '--store_la_logs --ignore_la_failure'
            cmd = cmd_template.format(self.test_script, self.setup_name, self.dut_hwsku, self.session_id,
                                      self.mars_key_id, self.raw_options, allure_project, random_seed)

        # when disabling one plugin, we also need to remove the relevant pytest argument
        if "no:ngts.tools.conditional_mark" in cmd:
            cmd = cmd.replace("--dynamic_update_skip_reason", "")
        if "no:ngts.tools.loganalyzer" in cmd:
            cmd = cmd.replace("--store_la_logs", "")
        if "no:ngts.tools.loganalyzer_dynamic_errors_ignore.la_dynamic_errors_ignore" in cmd:
            cmd = cmd.replace("--ignore_la_failure", "")

        for epoint in self.EPoints:
            dic_args = self._get_dic_args_by_running_stage(RunningStage.RUN)
            dic_args["epoint"] = epoint
            for _ in range(self.num_of_processes):
                epoint.Player.putenv("PYTHONPATH", "/devts/")
                epoint.Player.run_process(cmd, shell=True, disable_realtime_log=False, delete_files=False)

        for player in self.Players:
            rc = player.wait() or rc
            player.remove_remote_test_path(player.testPath)
        if rc == ErrorCode.NO_COLLECTION:
            rc = 0  # In case no tests are collected, should not fail mars step
        self._update_mini_case_summary()
        return rc

    def run_post_commands(self):
        # SDK base post-commands are invoked first so the mini case summary
        # tokens are written even if the allure upload later raises.
        super(RunPytest, self).run_post_commands()
        self.collect_allure_report_data()

    def _extract_test_stats_from_junit_xml(self):
        """Sum passed/failed/skipped counts from the junit xml reports
        produced on the players. Pytest "error" outcomes (fixture/collection
        errors) are counted as failed. Returns None when no report was
        requested or none could be fetched/parsed, so the caller can fall
        back to parsing the pytest terminal summary."""
        if not self.junit_report_file:
            return None
        try:
            from rpyc.utils.classic import connect
            from xml.etree import ElementTree
        except ImportError as exc:
            self.Logger.warning("mini_case_summary: junit imports unavailable: {}".format(exc))
            return None

        passed = failed = skipped = 0
        parsed_any = False
        for player in self.Players:
            try:
                conn = connect(player.player_ip)
            except Exception as exc:
                self.Logger.warning(
                    "mini_case_summary: failed to connect to player {}: {}".format(
                        player.player_ip, exc))
                continue
            try:
                content = conn.builtins.open(self.junit_report_file).read()
                conn.modules.os.remove(self.junit_report_file)
                root = ElementTree.fromstring(content)
            except Exception as exc:
                self.Logger.warning(
                    "mini_case_summary: failed to fetch/parse junit xml {} from player {}: {}".format(
                        self.junit_report_file, player.player_ip, exc))
                continue
            finally:
                conn.close()
            # Count per testcase instead of summing the <testsuite> attributes:
            # a test that both fails and errors (e.g. call failure + teardown
            # error) is counted once in "failures" and once in "errors", which
            # would inflate failed and drive passed below its real value.
            all_names, failed_names, skipped_names = set(), set(), set()
            for testcase in root.iter('testcase'):
                name = (testcase.get('classname', ''), testcase.get('name', ''))
                all_names.add(name)
                child_tags = {child.tag.lower() for child in testcase}
                if child_tags & {'failure', 'error'}:
                    failed_names.add(name)
                elif 'skipped' in child_tags:
                    skipped_names.add(name)
            failed += len(failed_names)
            skipped += len(skipped_names - failed_names)
            passed += len(all_names - failed_names - skipped_names)
            parsed_any = True
        return (passed, failed, skipped) if parsed_any else None

    def _extract_test_stats_from_output(self, output):
        """Aggregate passed/failed/skipped counts from every pytest summary
        line in the wrapper output. "error" outcomes are counted as failed.

        Pytest emits its final summary as an "=" framed line, for example:
            ============ 2 passed, 1 failed, 0 skipped in 1.23s =============
        With num_of_processes > 1 the wrapper log can contain several such
        lines, so we sum them.
        """
        totals = {'passed': 0, 'failed': 0, 'skipped': 0, 'error': 0}
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
        return totals['passed'], totals['failed'] + totals['error'], totals['skipped']

    def _update_mini_case_summary(self):
        """Push pytest passed/failed/skipped totals to the MARS monitor
        mini case summary. Counts are taken from the junit xml report when
        available, otherwise from the pytest terminal summary in the wrapper
        output. No-op when the SDK/MARS version is too old."""
        if not hasattr(self, 'set_mini_case_summary'):
            return
        stats = self._extract_test_stats_from_junit_xml()
        if stats is None:
            try:
                output = self.get_output()
            except Exception as exc:
                self.Logger.warning(
                    "mini_case_summary: failed to read wrapper output: {}".format(exc))
                return
            if not output:
                return
            stats = self._extract_test_stats_from_output(output)
        passed, failed, skipped = stats
        if passed == failed == skipped == 0:
            self.Logger.info(
                "mini_case_summary: no pytest summary detected; leaving MARS "
                "statistics as a single regular case.")
            return
        self.Logger.info(
            "mini_case_summary: passed={}, failed={}, skipped={}".format(
                passed, failed, skipped))
        self.set_mini_case_summary(passed, failed, skipped)

    def collect_allure_report_data(self):
        self.Logger.info('Going to upload allure data to server')

        sonic_mgmt_path = self.test_script.split('ngts')[0]
        cmd_suffix = "--cli_type {}".format(self.target_cli_type) if self.target_cli_type else ""
        cmd = 'PYTHONPATH=/devts /ngts_venv/bin/python {}/ngts/scripts/allure_reporter.py --action upload --setup_name {} {}'.format(sonic_mgmt_path, self.setup_name, cmd_suffix)
        self.Logger.info('Running cmd: {}'.format(cmd))
        self.EPoints[0].Player.run_process(cmd, shell=True, disable_realtime_log=False, delete_files=False)

        self.Players[0].wait()
        self.Logger.info('Finished upload allure data to server')


if __name__ == "__main__":
    run_pytest = RunPytest("RunPytest")
    run_pytest.execute(sys.argv[1:])
