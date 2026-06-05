import allure
import os
import logging
import pytest
from ngts.constants.constants import PytestConst, InfraConst
from ngts.helpers.sanitizer_helper import get_asan_apps, get_sanitizer_dumps
from ngts.helpers.bug_handler.bug_handler_helper import handle_sanitizer_dumps, create_summary_html_report, \
    review_bug_handler_results
from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon
from ngts.common.util import get_dpu_engines

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
def test_sanitizer_bug_handler(topology_obj, setup_name, engines, cli_objects, dumps_folder, dpu_asan):
    switch_engine = topology_obj.players['dut']['engine']
    if dpu_asan:
        dut_engines = get_dpu_engines(topology_obj)
    else:
        dut_engines = [switch_engine]

    asan_apps = [] if dpu_asan else get_asan_apps(topology_obj, cli_objects.dut)
    branch = topology_obj.players['dut']['branch']
    cli_type = os.environ.get('CLI_TYPE')
    session_id = os.environ.get(InfraConst.ENV_SESSION_ID)
    os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "False"

    if dpu_asan:
        is_sanitizer = dut_engines[0].run_cmd("sonic-cfggen -y /etc/sonic/sonic_version.yml -v asan").strip() == "yes"
    else:
        is_sanitizer = topology_obj.players['dut']['sanitizer']

    for dut_engine in dut_engines:
        if dpu_asan:
            setup_name = dut_engine.dut_name
            sanitizer_dumps_paths = get_sanitizer_dumps(dumps_folder, setup_name)
        else:
            sanitizer_dumps_paths = get_sanitizer_dumps(dumps_folder)

        if sanitizer_dumps_paths:
            with allure.step("Call bug handler on found sanitizer dumps"):
                version = GeneralCliCommon(dut_engine).get_version(cli_type)
                bug_handler_dumps_results = handle_sanitizer_dumps(sanitizer_dumps_paths, cli_type, branch, version,
                                                                   setup_name, topology_obj)
                bug_handler_summary = create_summary_html_report(session_id, setup_name, dumps_folder,
                                                                 bug_handler_dumps_results)
                allure.attach.file(bug_handler_summary,
                                   attachment_type=allure.attachment_type.HTML,
                                   name="bug_handler_summary_report.html")
                review_bug_handler_results(bug_handler_dumps_results)
        else:
            if is_sanitizer or asan_apps:
                with allure.step(f"No sanitizer leaks were detected in previous"
                                 f"reboots or disable the apps for {setup_name}"):
                    continue
            else:
                with allure.step(f"Image doesn't include sanitizer for {setup_name}"):
                    continue
    return InfraConst.RC_SUCCESS
