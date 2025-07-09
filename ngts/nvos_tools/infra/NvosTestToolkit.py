import logging
import math
import re
from datetime import datetime

import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.openapi.openapi_command_builder import OpenApiCommandHelper
from ngts.cli_wrappers.openapi.openapi_general_clis import OpenApiGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, NvosConst, CumulusConsts
from ngts.nvos_tools.infra import ExceptionTool
from ngts.tests.nightly.logging.test_log_analyzer_errors_during_deploy_sonic import get_oldest_syslog_id, \
    insert_new_start_string
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class TestToolkit:
    tested_ports = None
    engines = None
    devices = None
    tested_api = ApiType.NVUE
    GeneralApi = {ApiType.NVUE: NvueGeneralCli, ApiType.OPENAPI: OpenApiGeneralCli}
    loganalyzer_duts = None
    topology_obj = None
    dut_eth0_ip = ""
    is_dut_eth = None

    @staticmethod
    def update_tested_ports(tested_ports):
        with allure.step("Update tested ports in TestTookit"):
            logging.info("Testes port/s: " + str(tested_ports))
            TestToolkit.tested_ports = tested_ports

    @staticmethod
    def update_open_api_port(port_num):
        OpenApiCommandHelper.update_open_api_port(port_num)

    @staticmethod
    def update_topology_obj(topology_obj):
        with allure.step("Update topology_obj in TestTookit"):
            TestToolkit.topology_obj = topology_obj

    @staticmethod
    def update_engines(engines):
        with allure.step("Update engines object in TestTookit"):
            TestToolkit.engines = engines

    @staticmethod
    def update_dut_eth0_ip(ip):
        TestToolkit.dut_eth0_ip = ip

    @staticmethod
    def update_devices(devices):
        with allure.step("Update devices object in TestTookit"):
            TestToolkit.devices = devices

    @staticmethod
    def update_apis(api_type):
        with allure.step("Update api in TestTookit to " + api_type):
            TestToolkit.tested_api = api_type
            logging.info("API updated to: " + api_type)

    @staticmethod
    def update_port_output_dictionary(port_obj, engine=None):
        with allure.step("Run 'show' command and update output dictionary"):
            logging.info("Run 'show' command and update output dictionary")
            port_obj.update_output_dictionary(engine if engine else TestToolkit.engines.dut)

    @staticmethod
    def date_time_string_to_datetime_obj(date_time_str):
        """
        return datetime object from date time string
        example : date_time_string_to_datetime_obj(Feb 23 10:31:21)  => 2023-02-23 10:31:21
        """
        datetime_obj = datetime.strptime(date_time_str, "%b %d %H:%M:%S")
        current_year = datetime.now().year
        datetime_obj = datetime_obj.replace(year=current_year)
        return datetime_obj

    @staticmethod
    def get_date_and_time_from_line(line):
        date_time = re.findall(NvosConst.DATE_TIME_REGEX[0], line)
        assert len(date_time) > 0, "Did not find date and time regex {} in line: {}".format(NvosConst.DATE_TIME_REGEX[0],
                                                                                            line)
        return TestToolkit.date_time_string_to_datetime_obj(date_time[0].split(".")[0])

    @staticmethod
    def search_line_after_a_specific_date_time(line_to_search, text, since_date_time):
        """
        search line in the txt and return just the lines that find that happen after a specific time
        :param line_to_search: regex of line to search
        :param text: txt to search in
        :param since_date_time: datatime object
        :return: list of the relevant line appearance
        """
        lines = re.findall(line_to_search, text)
        res = []
        for line in lines:
            line_date_time = TestToolkit.get_date_and_time_from_line(line)
            if since_date_time < line_date_time:
                res.append(line)
        return res

    @staticmethod
    def is_special_run():
        """
        check if this run is special run (sanitizer / code coverage / debug kernel)
        :param topology_obj:
        :return: True is this is a special run , else False
        """
        return pytest.is_sanitizer or pytest.is_code_coverage or pytest.is_debug_kernel

    @staticmethod
    def get_version_num(version):
        if not re.match(TestToolkit.devices.dut.full_version_pattern, version):
            return ''

        match = re.search(TestToolkit.devices.dut.version_number_pattern, version)
        version_number = match.group()
        return version_number

    @staticmethod
    def version_to_release(version):
        """
        return the relevant release according to the version param.
        if its private version or unknown will return ''
        examples:
            from  'nvos-25.02.2000'  to 'nvos-25-02-2000'
            from 'nvos-25.02.1910-014' to  'nvos-25-02-2000'
            from 'nvos-25.02.1320-014' to  'nvos-25-02-1400'
        """
        if not re.match(TestToolkit.devices.dut.full_version_pattern, version):
            return ''

        pattern = r'(\d+)-(\d+)$'
        match = re.search(pattern, version)
        if match:
            num_str = match.group(1)  # extract the number string '0930' from 'nvos-25.02.0930-011'
            rounded_num = math.ceil(int(num_str) / 100) * 100  # round up to the nearest hundred
            rounded_num_str = str(rounded_num).zfill(
                len(num_str))  # convert the rounded number back to string with leading zeros
            result = re.sub(pattern, f'{rounded_num_str}', version)
        else:
            result = version
        result = result.replace('.', '-')
        return result

    @staticmethod
    def run_log_analyzer_bug_handler():
        """
        check if all the following conditions are met
            * it is not special run (sanitizer /code coverage)
            * it is mars run
        :param topology_obj: topology object
        :param setup_name: name of the setup
        :return: True if all the conditions are met, else false
        """
        return pytest.is_mars_run and not TestToolkit.is_special_run()

    @staticmethod
    def get_loganalyzer_marker(engine, get_full_line=False) -> str:
        """
        Returns the most recent log-analyzer test-start marker from the logs. If get_full_line is false, returns only
        the line contents; otherwise returns the full line from the log, including timestamp, hostname, etc. .
        """
        try:
            with allure.step("Get log analyzer marker"):
                markers = engine.run_cmd('grep " start-LogAnalyzer-" /var/log/syslog')
                last_marker = markers.split("\n")[-1]
                return last_marker if get_full_line else re.findall(r'\bstart-LogAnalyzer-\S+', last_marker)[0]
        except BaseException as e:
            ExceptionTool.log_exception(e)
            return ""

    @staticmethod
    def add_loganalyzer_marker(engine, marker):
        """Injects the log-analyzer test-start marker at the current position in the log."""
        try:
            with allure.step("Add log analyzer marker"):
                if marker:
                    engine.run_cmd(f"logger -p info '{marker}'")
        except BaseException as e:
            logging.warning("Failed to add log analyzer marker: " + ExceptionTool.format_exception(e))

    @staticmethod
    def add_loganalyzer_marker_at_beginning(engine, marker):
        """
        Creates a new "log" file that contains `marker` and zips it into syslog.n.gz so it would appear to be the oldest
        log file. `marker` must be a full log line (containing the timestamp, hostname, etc.).
        """
        try:
            with allure.step("Adding log analyzer marker as the first log line"):
                oldest_syslog_id = get_oldest_syslog_id(engine)
                insert_new_start_string(engine, oldest_syslog_id, marker)
        except BaseException as e:
            ExceptionTool.log_exception(e)

    @staticmethod
    def start_code_section_loganalyzer_ignore():
        if TestToolkit.loganalyzer_duts:
            logging.info('Start Loganalyzer ignore')
            for loganalyzer_dut in TestToolkit.loganalyzer_duts.values():
                loganalyzer_dut.add_start_ignore_mark()

    @staticmethod
    def end_code_section_loganalyzer_ignore():
        if TestToolkit.loganalyzer_duts:
            logging.info('End Loganalyzer ignore')
            for loganalyzer_dut in TestToolkit.loganalyzer_duts.values():
                loganalyzer_dut.add_end_ignore_mark()

    @staticmethod
    def is_eth_dut(dut_device=None) -> bool:
        if TestToolkit.is_dut_eth is None:
            if not dut_device and not TestToolkit.devices:
                TestToolkit.is_dut_eth = False
            else:
                dut_device = dut_device or TestToolkit.devices.dut
                TestToolkit.is_dut_eth = (dut_device.switch_type == CumulusConsts.ETH_SWITCH_TYPE)
        return TestToolkit.is_dut_eth
