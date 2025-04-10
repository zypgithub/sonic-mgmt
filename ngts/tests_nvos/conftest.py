import concurrent.futures
import datetime
import logging
import os
import random
import smtplib
import time
from email.mime.text import MIMEText
from typing import Dict

import pexpect
import pytest
from dotted_dict import DottedDict
from retry import retry

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from infra.tools.exceptions.setup_issue import SetupIssue
from infra.tools.general_constants.constants import DefaultConnectionValues
from infra.tools.linux_tools.linux_tools import scp_file
from ngts.nvos_tools.infra.BmcTool import BmcTool
from infra.tools.sql.connect_to_mssql import ConnectMSSQL
from ngts.cli_wrappers.linux.linux_general_clis import LinuxGeneralCli
from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli
from ngts.cli_wrappers.openapi.openapi_command_builder import OpenApiRequest
from ngts.constants.constants import DbConstants, CliType, DebugKernelConsts, InfraConst, CoreDumpConsts
from ngts.nvos_constants.constants_nvos import ApiType, OperationTimeConsts, OutputFormat, NvosConst, TestConsts, \
    SyslogConsts
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
from ngts.nvos_tools.cli_coverage.nvue_cli_coverage import NVUECliCoverage
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool
from ngts.nvos_tools.infra import ExceptionTool
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.DiskTool import DiskTool
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.PexpectTool import PexpectTool
from ngts.nvos_tools.infra.RandomizationTool import random_api as get_random_api
from ngts.nvos_tools.infra.RegressionConfigurations import RegressionConfigurations
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.SerialConsoleTool import SerialConsoleTool
from ngts.nvos_tools.infra.TrafficGeneratorTool import TrafficGeneratorTool
from ngts.nvos_tools.system.System import System
from ngts.scripts.code_coverage.code_coverage_consts import NvosConsts
from ngts.scripts.code_coverage.test_code_coverage import extract_python_coverage_for_nvos
from ngts.tests.nightly.logging.test_log_analyzer_errors_during_deploy_sonic import get_oldest_syslog_id, \
    get_new_start_string, insert_new_start_string
from ngts.tests_nvos.helpers.pytest_helpers import is_cur_test_has_marker, get_marker_arg_value, is_cur_test_passed
from ngts.tests_nvos.helpers.pytest_items_filters import run_nvos_pytest_items_modification
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import wait_for_ldap_nvued_restart_workaround

logger = logging.getLogger()


def pytest_addoption(parser):
    """
    Parse NVOS pytest options
    :param parser: pytest build in
    """
    logger.info('Parsing NVOS pytest options')
    parser.addoption("--max_case_instances", action="store", type=int, default=None, help="Randomly select N test instances for each test function")
    parser.addoption('--release_name', action='store',
                     help='The name of the release to be tested. For example: 25.01.0630')
    parser.addoption("--restore_to_image",
                     action="store", default=None, help="restore image after error flow")
    parser.addoption("--traffic_available",
                     action="store", default='True', help="True to run traffic tests")
    parser.addoption("--tst_all_pwh_confs",
                     action="store", default='False', help="True to test functionality of all password hardening "
                                                           "configurations; False otherwise (only several random "
                                                           "configurations will be picked to testing)")
    parser.addoption("--disable_cli_coverage", action="store_true", default=False, help="Do not run cli coverage")
    parser.addoption("--security_post_checker", action="store_true", default=False, required=False,
                     help="Whether to run security post checker or not")
    parser.addoption("--check_output", action="store_true", default=False, help="Provide to check ib output")
    parser.addoption("--substrings_to_check", action="store", default=False, help="Provide which substrings to check")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    run_nvos_pytest_items_modification(config, items)


@pytest.fixture(autouse=True)
def check_log_size(request, engines):
    def __get_syslog_file_size_kb(filename='syslog') -> int:
        return int(engines.dut.run_cmd(f'du -k /var/log/{filename} | cut -f1'))
    marker_name = 'check_log_size'
    should_check = is_cur_test_has_marker(request, marker_name)
    if should_check:
        with allure.step('get syslog size before (in KB)'):
            size_before = __get_syslog_file_size_kb()
    yield
    if should_check:
        with allure.step('get syslog size after (in KB)'):
            size_after = __get_syslog_file_size_kb()
            if size_after <= size_before:
                logging.info('log was rotated')
                size_after += __get_syslog_file_size_kb('syslog.1')
            test_addition_to_syslog = size_after - size_before
        allure.attach('syslog sizes', f'before: {size_before}KB\nafter: {size_after}KB\ntest added: {test_addition_to_syslog}KB')
        if is_cur_test_passed(request):
            expected_threshold = get_marker_arg_value(request, marker_name, 'expect')
            if expected_threshold and isinstance(expected_threshold, int):
                with allure.step(f'make sure test addition is less than expected ({expected_threshold})'):
                    assert test_addition_to_syslog <= expected_threshold, f'test added {test_addition_to_syslog}KB to syslog. allowed: {expected_threshold}'


@pytest.fixture(autouse=True)
def check_ib_output(request):
    """
    Method for getting check_ib_output and substrings_to_check from pytest arguments
    :param request: pytest builtin
    """
    if request.config.getoption("--check_output"):
        NvueBaseCli.check_output_strings = True
    if request.config.getoption("--substrings_to_check"):
        NvueBaseCli.sub_strings_to_search = request.config.getoption('--substrings_to_check').split(',')


@pytest.fixture(autouse=True)
def track_serial_console(request, topology_obj, engines, devices):
    """
    fixture to track serial console during test run,
        and if the test is failing, attach the serial console output to allure report (for better debug).

    This will apply for all test that has any of the defined interesting markers below.
    """
    interesting_markers = ['track_serial_console', 'reboot', 'factory_reset', 'reset_factory']
    should_track_serial_console = any(is_cur_test_has_marker(request, marker) for marker in interesting_markers)

    if should_track_serial_console:
        with allure.step('start tracking serial console into file'):
            serial_log_file_path = '/tmp/serial.log'
            serial_connection_cmd = SerialConsoleTool.get_serial_console_connection_command(topology_obj)
            logging.info('connect to serial console and save output into a file')
            cmd = f'script -c "{serial_connection_cmd}" {serial_log_file_path}'
            child = pexpect.spawn(cmd)

    yield

    if should_track_serial_console:
        with allure.step('end serial console session'):
            for _ in range(3):
                child.sendcontrol('z')
                time.sleep(0.5)
            for _ in range(3):
                child.sendcontrol('d')
                time.sleep(0.5)
            # child.expect(pexpect.EOF)
            child.close()
        if request.node.rep_call.failed:
            try:
                with allure.step('take log file content'):
                    with open(serial_log_file_path, 'r', errors='replace') as file:
                        serial_log_content = file.read()
                with allure.step('attach content to allure'):
                    allure.attach('Serial Console log during test', serial_log_content)
            except Exception as e:
                err = f'failed to attach serial output from {serial_log_file_path} : {ExceptionTool.format_traceback()}'
                logging.warning(err)
                allure.attach('Attachment Failure', err)
        else:
            with allure.step('test passed. not attaching serial console log'):
                pass


@pytest.fixture(scope='session')
def engines(topology_obj, devices):
    engines_data = DottedDict()
    engines_data.dut = topology_obj.players['dut']['engine']
    update_engine_dut_mgmt_port(topology_obj, engines_data.dut, devices.dut)
    # ha and hb are the traffic dockers
    if "ha" in topology_obj.players:
        engines_data.ha = topology_obj.players['ha']['engine']
        engines_data.ha_attr = topology_obj.players['ha']['attributes']
    if "hb" in topology_obj.players:
        engines_data.hb = topology_obj.players['hb']['engine']
        engines_data.hb_attr = topology_obj.players['hb']['attributes']

    # engines.hfnm refers to the VM connected to the FNM port if there is one, or to HA if there isn't
    if "hfnm" in topology_obj.players:
        engines_data.hfnm = topology_obj.players['hfnm']['engine']
        engines_data.hfnm_attr = topology_obj.players['hfnm']['attributes']
    elif "ha" in topology_obj.players:
        engines_data.hfnm = topology_obj.players['ha']['engine']
        engines_data.hfnm_attr = topology_obj.players['ha']['attributes']

    if "server" in topology_obj.players:
        engines_data.server = topology_obj.players['server']['engine']
    if "sonic-mgmt" in topology_obj.players:
        engines_data.sonic_mgmt = topology_obj.players['sonic-mgmt']['engine']

    TestToolkit.update_engines(engines_data)
    TestToolkit.update_topology_obj(topology_obj)
    return engines_data


def get_dut_hostname(engines):
    return engines.dut.run_cmd('hostname')


@pytest.fixture(scope='session')
def dut_hostname(engines):
    return get_dut_hostname(engines)


@pytest.fixture(scope='session')
def dut_ipv6_addr(engines, devices):
    dut_ipv6_addr = IpTool.get_dut_ipv6_addr_of_given_eth_interface_using_nv_cli(devices.dut.cur_mgmt_port_name, engines.dut)
    if not dut_ipv6_addr:
        dut_ipv6_addr = IpTool.get_player_ipv6_addr(engines.dut.ip, engines.dut)
    logging.info(f'dut ipv6 address: {dut_ipv6_addr}')
    return dut_ipv6_addr


@pytest.fixture(scope='session')
def sonic_mgmt_ipv6_addr(engines):
    sonic_mgmt_ipv6_addr = IpTool.get_player_ipv6_addr(engines.sonic_mgmt.ip, engines.sonic_mgmt)
    logging.info(f'sonic_mgmt ipv6 address: {sonic_mgmt_ipv6_addr}')
    return sonic_mgmt_ipv6_addr


def update_engine_dut_mgmt_port(topology, dut_engine: LinuxSshEngine, dut_device: BaseDevice):
    def attach_res_to_allure(available_ports_names, available_ports_ips, chosen_port_name, chosen_port_ip):
        attachment = (f'All ports: {available_ports_names} - {available_ports_ips}\n'
                      f'Chosen port: {chosen_port_name} - {chosen_port_ip}')
        allure.orig_allure.attach(attachment, 'dut_engine_mgmt_port_used_for_session',
                                  allure.orig_allure.attachment_type.TEXT)

    mgmt_ports = dut_device.get_mgmt_ports()

    dut_device.update_mgmt_port(mgmt_ports[0], dut_engine.ip)
    TestToolkit.update_dut_eth0_ip(dut_engine.ip)

    if not mgmt_ports or len(mgmt_ports) == 1:
        logger.info('keep original dut engine ip')
        attach_res_to_allure(mgmt_ports, None, mgmt_ports[0] if mgmt_ports else None, dut_engine.ip)
        return

    dut_setup_specific_attributes: Dict[str, str] = topology.players['dut']['attributes'].noga_query_data['attributes'][
        'Specific']
    setup_mgmt_ips = [dut_setup_specific_attributes['ip_address'], dut_setup_specific_attributes['ip_address_2']]
    available_mgmt_ips = [ip for ip in setup_mgmt_ips if ip != '']
    if len(available_mgmt_ips) != len(mgmt_ports):
        logger.info('keep original dut engine ip')
        attach_res_to_allure(mgmt_ports, available_mgmt_ips, mgmt_ports[0] if mgmt_ports else None, dut_engine.ip)
        return

    logger.info(f'device mgmt ports names: {mgmt_ports}')
    logger.info(f'setup mgmt ports ips: {available_mgmt_ips}')

    chosen_mgmt_port = random.choice(mgmt_ports)
    chosen_mgmt_port_ip = available_mgmt_ips[mgmt_ports.index(chosen_mgmt_port)]
    logger.info(f'chosen mgmt port for dut engine: {chosen_mgmt_port} - {chosen_mgmt_port_ip}')
    dut_engine.ip = chosen_mgmt_port_ip
    dut_device.update_mgmt_port(chosen_mgmt_port, chosen_mgmt_port_ip)
    attach_res_to_allure(mgmt_ports, available_mgmt_ips, chosen_mgmt_port, dut_engine.ip)


@pytest.fixture(scope="session")
def mst_device(request, engines):
    return ""


@pytest.fixture(scope='session')
def original_version(engines):
    version = OutputParsingTool.parse_json_str_to_dictionary(System().version.show()).get_returned_value()[
        'image']
    return version


@pytest.fixture(scope='session', autouse=True)
def devices(topology_obj):
    devices = DeviceFactory.create_devices_object(topology_obj)
    TestToolkit.update_devices(devices)
    return devices


@pytest.fixture(scope='session', autouse=True)
def update_open_api_port(devices):
    TestToolkit.update_open_api_port(devices.dut.open_api_port)


@pytest.fixture
def traffic_available(request):
    """
    True is traffic functionality is available for current setup
    :param request: pytest builtin
    :return: True/False
    """
    return bool(request.config.getoption('--traffic_available'))


@pytest.fixture(scope='function')
def serial_engine(topology_obj, devices):
    """
    :return: serial connection
    """
    return ConnectionTool.create_serial_connection(topology_obj, devices)


@pytest.fixture
def tst_all_pwh_confs(request):
    """
    True to test functionality of all password hardening configurations;
        False otherwise (only several random configurations will be picked to testing)
    :param request: pytest builtin
    :return: True/False
    """
    param_val = request.config.getoption('--tst_all_pwh_confs')
    return True if param_val == 'True' else False


@pytest.fixture
def start_sm(engines, devices, traffic_available):
    """
    Starts OpenSM
    """
    if traffic_available:
        RegressionConfigurations.configure_ports_to_legacy(engine=engines.dut, apply=True, throw_exception=False)
        result = OpenSmTool.start_open_sm(engines, multiplanar=devices.dut.multi_planar)
        if not result.result:
            with allure.step('open_sm failed to start (possibly due to #4088479), attempting to recover'):
                with allure.step('Rebooting all traffic VMs'):
                    executor = concurrent.futures.ThreadPoolExecutor()
                    tasks = []
                    if hasattr(engines, 'ha'):
                        tasks.append(executor.submit(engines.ha.reload, ['sudo reboot']))
                    if hasattr(engines, 'hb'):
                        tasks.append(executor.submit(engines.hb.reload, ['sudo reboot']))
                    if hasattr(engines, 'hfnm') and (not hasattr(engines, 'ha') or engines.ha.ip != engines.hfnm.ip):
                        tasks.append(executor.submit(engines.hfnm.reload, ['sudo reboot']))
                    for task in tasks:
                        try:
                            task.result(timeout=300)
                        except Exception:
                            ExceptionTool.log_traceback()
                            raise Exception('Failed to reboot traffic VMs, see traceback in logs')
                    time.sleep(5)

                with allure.step('Retrying to start open_sm'):
                    OpenSmTool.start_open_sm(engines, multiplanar=devices.dut.multi_planar).verify_result()
    else:
        raise SetupIssue("Traffic is not available on this setup")


@pytest.fixture
def stop_sm(engines):
    """
    Stops OpenSM
    """
    result = OpenSmTool.stop_open_sm(engines)
    if not result.result:
        logging.warning("Failed to stop openSM")


@pytest.fixture(scope="session")
def release_name(request):
    """
    Method for getting release_name from pytest arguments
    :param request: pytest builtin
    :return: release_name
    """
    return request.config.getoption('--release_name')


@pytest.fixture(scope='session', autouse=True)
def api_type(nvos_api_type):
    apitype = ApiType.NVUE
    if nvos_api_type.lower() == "openapi":
        apitype = ApiType.OPENAPI

    logger.info('updating API type to: ' + apitype)
    TestToolkit.update_apis(apitype)


@pytest.fixture(scope='session')
def cli_objects(topology_obj):
    cli_obj_data = DottedDict()
    cli_obj_data.dut = topology_obj.players['dut']['cli']
    if "ha" in topology_obj.players:
        cli_obj_data.ha = topology_obj.players['ha']['cli']
    if "hb" in topology_obj.players:
        cli_obj_data.hb = topology_obj.players['hb']['cli']
    return cli_obj_data


def check_switch_capacity(engine):
    try:
        logger.info("Check used capacity for /var/lib/python/coverage")
        engine.run_cmd("df -h /var/lib/python/coverage/")
        engine.run_cmd("du -h /var/lib/python/coverage")
        engine.run_cmd("du -h /sonic")
    except BaseException as ex:
        logger.warning(str(ex))


@pytest.fixture(scope='session')
def interfaces(topology_obj):
    interfaces_data = DottedDict()
    interfaces_data.ha_dut_1 = topology_obj.ports['ha-dut-1']
    interfaces_data.hb_dut_1 = topology_obj.ports['hb-dut-1']
    return interfaces_data


def security_cleanup(ssh_session: PexpectTool) -> bool:
    success = False
    if not ssh_session or not isinstance(ssh_session, PexpectTool):
        return success
    with allure.step('Security cleanup'):
        with allure.step('check session still connected to switch'):
            session_is_live = False
            ssh_session.sendline('nv show system')

            while True:
                try:
                    i = ssh_session.expect(DefaultConnectionValues.DEFAULT_PROMPTS, timeout=15)
                    if i < len(DefaultConnectionValues.DEFAULT_PROMPTS) and ('product-name' in ssh_session.last_output):
                        session_is_live = True
                        logging.info("Session is live")
                        break

                except pexpect.exceptions.TIMEOUT:
                    logging.info("No more output detected due to timeout.")
                    break

        if session_is_live:
            with allure.step('unset authentication config to allow local connection'):
                cmds = TestToolkit.devices.dut.aaa_cleanup_cmds
                expect_timeout = 60
                ssh_session.sendline(' ; '.join(cmds))
                i = ssh_session.expect(DefaultConnectionValues.DEFAULT_PROMPTS, timeout=expect_timeout, raise_exception_for_timeout=False)
                assert i != PexpectTool.TIMEOUT, f'security cleanup failed: expect prompt after apply failed: exceeded expect timeout: {expect_timeout} seconds'
                success = i < len(DefaultConnectionValues.DEFAULT_PROMPTS) and any(
                    msg in ssh_session.last_output for msg in ['applied', 'config apply executed with no config diff'])
    return success


def clear_security_config(item):
    with allure.step("Clear security config"):
        TestToolkit.update_apis(ApiType.NVUE)

        try:
            local_dut_engine: ProxySshEngine = TestToolkit.engines.dut
            try:
                active_aaa_server = item.active_remote_aaa_server

                logging.info('Test configured aaa authentication. find remote admin user to use')
                remote_admin = [user for user in active_aaa_server.users if user.role == 'admin'][0]
                logging.info(f'Create engine with remote user: {remote_admin.username}')
                remote_admin_engine = ProxySshEngine(device_type=TestToolkit.engines.dut.device_type,
                                                     ip=TestToolkit.engines.dut.ip,
                                                     username=remote_admin.username,
                                                     password=remote_admin.password)

                logging.info('Clear authentication settings to allow local admin user engine continue')
                res = System().aaa.authentication.unset(op_param='order', apply=True, dut_engine=remote_admin_engine)
                assert 'verifyingreadying' in res.info, f'Expected to have "{"verifyingreadying"}" ' \
                    f'in output. Actual output: {res.info}'
            finally:
                item.active_remote_aaa_server = None
                wait_for_ldap_nvued_restart_workaround(item, engine_to_use=local_dut_engine)
        except Exception:
            local_dut_engine.disconnect()
            wait_for_ldap_nvued_restart_workaround(item, engine_to_use=local_dut_engine)

        # if isinstance(active_aaa_server, LdapServerInfo):
        #     logging.info('Remove LDAP users home directories')
        #     remote_usernames = [user.username for user in active_aaa_server.users]
        #     for username in remote_usernames:
        #         TestToolkit.engines.dut.run_cmd(f'sudo rm -rf /home/{username}')


@pytest.fixture(scope="session")
def root_dir(request):
    return request.config.rootdir


@pytest.fixture(scope="session")
def default_config_yml_path(engines, devices, root_dir):
    return devices.dut.get_default_config_yml(engines.dut, root_dir)


def pytest_exception_interact(report):
    logging.error(f'----------- The test failed - an exception occurred: ----------- \n{report.longreprtext}')
    TestToolkit.devices.dut.handle_exception(TestToolkit.engines.dut)


@pytest.fixture(scope="function")
def run_cli_coverage_flow(clear_config, request):
    yield

    try:
        item = request.node
        logging.info('------- Running CLI coverage -------')
        run_cli_coverage(item, item.keywords)
    except BaseException as err:
        logging.warning(f"CLI coverage flow failed- {err}")


def eth_handle_exception():
    logging.info("Handle eth exception")


@pytest.fixture(scope="function", autouse=True)
def list_of_executed_commands(engines, run_cli_coverage_flow, request, session_data):
    pytest.s_time = time.time()
    logging.info(f'------- TEST STARTED - {request.node.name} -------')
    if 'no_log_test_wrapper' not in request.keywords:
        try:
            SendCommandTool.execute_command(LinuxGeneralCli(engines.dut).clear_history)
        except BaseException as exc:
            logger.info(f"'history -c' failed - {exc}")

    yield

    try:
        with allure.step("List of executed commands"):
            commands_list = SendCommandTool.execute_command(
                LinuxGeneralCli(engines.dut).get_history).get_returned_value()
            allure.attach("List of commands", commands_list)

        session_data[request.node.name] = {"history": commands_list}

    except BaseException as err:
        logging.warning(f"Failed to get list of executed commands - {err}")


@pytest.fixture(scope="function")
def clear_config(request, devices, engines, default_config_yml_path, root_dir, markers=None):
    yield

    TestToolkit.tested_api = ApiType.NVUE
    test_result = request.node.rep_call.outcome
    logging.info(f"------- Test '{request.node.name}' {test_result} -------")

    if test_result == TestConsts.SKIPPED:
        pass

    try:
        with allure.step(f"Clear config for test {request.node.name}"):
            """ if hasattr(item, 'active_remote_aaa_server') and item.active_remote_aaa_server:
                 clear_security_config(item)
            if hasattr(item, 'security_pexpect_ssh_session') and item.security_pexpect_ssh_session:
                security_cleanup(item.security_pexpect_ssh_session)"""
            devices.dut.clear_config(engines.dut, markers, default_config_yml_path, root_dir)
    except Exception as err:
        logging.warning("Failed to clear config:" + str(err))
    finally:
        logging.info('Clear global OpenApi changeset and payload')
        OpenApiRequest.clear_changeset_and_payload()
        OpenApiRequest.update_client_certs_info(None)


@pytest.fixture(scope='function', autouse=True)
def teardown_collect_code_coverage(topology_obj, engines):
    yield
    if pytest.is_code_coverage:
        collect_coverage = False

        with allure.step("Check coverage folder capacity"):
            cli_obj = topology_obj.players['dut']['cli']
            try:
                capacity_percentage = DiskTool.get_path_available_capacity_percentage(engines.dut,
                                                                                      NvosConst.COVERAGE_PATH)
                logging.info(f"Coverage folder capacity: {capacity_percentage}%")
                collect_coverage = int(capacity_percentage) >= NvosConst.MAX_COVERAGE_PATH_CAPACITY_PERCENTAGE
            except BaseException:
                collect_coverage = True
                cli_obj.general.coverage_combine()

        if collect_coverage:
            with allure.step(f"Collect python coverage (folder capacity {capacity_percentage}%"):
                extract_python_coverage_for_nvos(dest=NvosConsts.DEST_PATH, engines=engines, cli_obj=cli_obj,
                                                 topology_obj=topology_obj)


@pytest.fixture(scope='function', autouse=True)
def debug_kernel_check(engines, test_name, setup_name, session_id):
    yield
    if pytest.is_debug_kernel:
        engines.dut.run_cmd("sudo dmesg | grep {}".format(DebugKernelConsts.KMEMLEAK))
        engines.dut.run_cmd("sudo echo scan | sudo tee {}".format(DebugKernelConsts.KMEMLEAK_PATH))
        mem_leaks_output = engines.dut.run_cmd("sudo cat {}".format(DebugKernelConsts.KMEMLEAK_PATH))
        if mem_leaks_output:
            logger.info("kernel memory leaks were found, will send mail with the leaks")
            context = f"Kernel memory leaks were found during test:{test_name}\n" \
                f"Setup: {setup_name}\n" \
                f"Session ID: {session_id}\n" \
                f"{mem_leaks_output}"
            try:
                s = smtplib.SMTP(InfraConst.NVIDIA_MAIL_SERVER)
                email_contents = MIMEText(context)
                email_contents['Subject'] = "debug kernel issue nvos"
                email_contents['To'] = ", ".join(['bshpigel@nvidia.com', 'ncaro@nvidia.com', 'yport@nvidia.com'])
                s.sendmail('noreply@debugkernel.com', email_contents['To'], email_contents.as_string())
                logger.info("Mail was sent to: {}".format(email_contents['To']))
            finally:
                s.quit()

            engines.dut.run_cmd("sudo echo clear | sudo tee {}".format(DebugKernelConsts.KMEMLEAK_PATH))


@pytest.fixture(scope='function', autouse=True)
def coredump_check(engines, test_name, setup_name, dumps_folder, session_id):
    files = engines.dut.run_cmd(f"sudo ls {CoreDumpConsts.COREDUMP_PATH}").strip().split("\n")

    if not files or files == ['']:
        logger.info(f'No core dumps found in {pytest.test_name}')
    else:
        for file in files:
            file_path = os.path.join(CoreDumpConsts.COREDUMP_PATH, file)
            logger.info('Copy dump {} to log folder {}'.format(file_path, dumps_folder))
            dest_file = dumps_folder + '/' + file
            scp_file(engines.dut, file_path, dest_file, download_from_remote=True)
            os.chmod(dest_file, 0o655)
            logger.info('Dump file location: {}'.format(dest_file))
            logger.info('Delete coredump {} from the switch'.format(file_path))
            engines.dut.run_cmd(f"sudo rm -f {file_path}")
            logger.info("Core dump were found, will send mail with the leaks")
            context = f"Core dump were found during test:{test_name}\n" \
                f"Setup: {setup_name}\n" \
                f"Session ID: {session_id}\n" \
                f"Test: {pytest.test_name}\n" \
                f"Core dump file location: {dest_file}"
            try:
                s = smtplib.SMTP(InfraConst.NVIDIA_MAIL_SERVER)
                email_contents = MIMEText(context)
                email_contents['Subject'] = "Core dump issue NVOS"
                email_contents['To'] = ", ".join(['sviatoslavd@nvidia.com', 'ncaro-org@exchange.nvidia.com',
                                                  'yport@nvidia.com', 'nadeemn@nvidia.com'])
                s.sendmail('noreply@nvidia.com', email_contents['To'], email_contents.as_string())
                logger.info("Mail was sent to: {}".format(email_contents['To']))
            finally:
                s.quit()
        pytest.fail(f"Coredump found and uploaded to {dest_file}")


@pytest.fixture(scope="session", autouse=True)
def insert_operation_time_to_db(setup_name, session_id, platform_params, topology_obj):
    '''
    @summary:   insert operation times to operation_time table DB.
    during the tests we will add to pytest.operation_list the operations that we want to measure,
    and at the end of the test we will insert it to the DB.
    '''
    pytest.operation_list = []
    yield
    if len(pytest.operation_list) > 0:
        try:
            type = platform_params['filtered_platform']
            version = OutputParsingTool.parse_json_str_to_dictionary(System().version.show()).get_returned_value()[
                'image']
            release_name = TestToolkit.version_to_release(version)
            if not TestToolkit.is_special_run() and pytest.is_mars_run and release_name and not pytest.is_ci_run:
                insert_operation_duration_to_db(setup_name, type, version, session_id, release_name)
        except Exception as err:
            logger.warning("Failed to save operation duration data, because: {}".format(err))


@retry(Exception, tries=3, delay=3)
def insert_operation_duration_to_db(setup_name, type, version, session_id, release_name):
    connections_params = DbConstants.CREDENTIALS[CliType.NVUE]
    mssql_connection_obj = ConnectMSSQL(connections_params['server'], connections_params['database'],
                                        connections_params['username'], connections_params['password'])
    mssql_connection_obj.connect_db()
    logger.info("Insert {} operations info to operation_time DB".format(len(pytest.operation_list)))
    try:
        values = ""
        for operation in pytest.operation_list:
            value = "('{operation}', '{command}', '{duration}', '{setup_name}', '{type}', '{version}', " \
                    "'{release}', '{session_id}', '{test_name}', '{date}')".format(
                        operation=operation[OperationTimeConsts.OPERATION_COL],
                        command=operation[OperationTimeConsts.PARAMS_COL],
                        duration=operation[OperationTimeConsts.DURATION_COL], setup_name=setup_name, type=type,
                        version=version, release=release_name, session_id=session_id,
                        test_name=operation[OperationTimeConsts.TEST_NAME_COL], date=datetime.date.today())

            values = values + ', ' + value if values else value

        if values:
            columns = "({operation_col}, {params_col}, {duration_col}, {setup_name_col}, {type_col}, {version_col}," \
                      " {release_col}, {session_id_col}, {test_name_col}, {date_col})".format(
                          operation_col=OperationTimeConsts.OPERATION_COL, params_col=OperationTimeConsts.PARAMS_COL,
                          duration_col=OperationTimeConsts.DURATION_COL, setup_name_col=OperationTimeConsts.SETUP_COL,
                          type_col=OperationTimeConsts.TYPE_COL, version_col=OperationTimeConsts.VERSION_COL,
                          release_col=OperationTimeConsts.RELEASE_COL, session_id_col=OperationTimeConsts.SESSION_ID_COL,
                          test_name_col=OperationTimeConsts.TEST_NAME_COL, date_col=OperationTimeConsts.DATE_COL)
            query = "INSERT operation_time {columns} values {values};".format(columns=columns, values=values)

        mssql_connection_obj.query_insert(query)
        logger.info("--------- insert to operation time DB table successfully ---------\n")
    finally:
        mssql_connection_obj.disconnect_db()


@pytest.fixture(scope="session")
def session_data():
    """
    Fixture to hold session-wide data for executed commands and additional metadata.

    This fixture acts as a centralized storage for data that needs to persist throughout the test session.
    It can be used for various purposes, such as:
    - Holding log outputs or diagnostic information for bug handling after running loganalyzer.
    - Keeping track of test-related context data.
    """
    return {}


@pytest.fixture(autouse=True)
def disable_cli_coverage(request):
    """
    Method for getting disable_cli_coverage from pytest arguments
    :param request: pytest builtin
    """
    pytest.disable_cli_coverage = request.config.getoption('--disable_cli_coverage')


def run_cli_coverage(item, markers):
    if TestToolkit.tested_api == ApiType.NVUE and \
            'no_cli_coverage_run' not in markers and \
            not pytest.is_sanitizer and \
            pytest.is_mars_run and \
            not pytest.disable_cli_coverage:
        logging.info("API type is NVUE and is it not a sanitizer version, so CLI coverage script will run")
        NVUECliCoverage.run(item=item, start_time=pytest.s_time,
                            project=TestToolkit.devices.dut.cli_coverage_project_name, department='verification',
                            nvue_dir=TestToolkit.devices.dut.cli_coverage_path)


@pytest.fixture(autouse=True)
def security_post_checker(request):
    """
    Method for getting security_post_checker from pytest arguments
    :param request: pytest builtin
    """
    if request.config.getoption("--security_post_checker"):
        logger.info('Security Post Checker')
        return True
    else:
        return False


@pytest.fixture(scope='session', autouse=True)
def store_and_manage_loganalyzer(request):
    ignore_failure = request.config.getoption("--ignore_la_failure")
    store_la_logs = request.config.getoption("--store_la_logs")
    if not ignore_failure:
        request.config.option.ignore_la_failure = True
    if not store_la_logs:
        request.config.option.store_la_logs = True


@pytest.fixture(scope='function', autouse=True)
def extend_log_analyzer_match_regex(loganalyzer):
    """
    Extend the loganalyzer match_regex list and ignore_regex list.
    """
    if loganalyzer:
        for hostname in loganalyzer.keys():
            loganalyzer[hostname].ignore_regex.extend(list(pytest.dynamic_ignore_set))
            loganalyzer[hostname].match_regex.extend(["\\.*\\s+WARNING\\s+\\.*", "\\.*\\s+segfault\\s+\\.*"])


@pytest.fixture(scope='session', autouse=True)
def disable_loganalyzer_rotate_logs(request):
    request.config.option.loganalyzer_rotate_logs = False


@pytest.fixture(scope='function', autouse=True)
def initialize_testtoolkit_loganalyzer(loganalyzer):
    TestToolkit.loganalyzer_duts = loganalyzer


@pytest.fixture
def prepare_traffic(engines, setup_name):
    """
    - Bring up traffic containers in case are in down state.
    - Starts OpenSM
    """
    with allure.step('Prepare traffic containers...'):
        TrafficGeneratorTool.bring_up_traffic_containers(engines, setup_name)


@pytest.fixture
def output_format(test_api):
    return OutputFormat.auto if test_api == ApiType.NVUE else OutputFormat.json


@pytest.fixture(scope='session')
def target_version_realpath(target_version):
    assert target_version is not None, "No target image is specified"
    cmd_runner = CmdRunner()
    with allure.step('get real full path of target version'):
        target_version_path = cmd_runner.run_cmd(f'realpath {target_version}')
        logging.info(f'target version path: {target_version_path}')
    return target_version_path


@pytest.fixture(scope='session')
def base_version_realpath(base_version):
    assert base_version is not None, "No base image is specified"
    cmd_runner = CmdRunner()
    with allure.step('get real full path of target version'):
        base_version_path = cmd_runner.run_cmd(f'realpath {base_version}')
        logging.info(f'base version path: {base_version_path}')
    return base_version_path


@pytest.fixture(scope='session')
def downgrade_version_realpath(downgrade_version, base_version):
    version = downgrade_version or base_version
    if not version:
        raise SetupIssue('Must specify downgrade_version or base_version in command-line')
    cmd_runner = CmdRunner()
    with allure.step('get real full path of version'):
        version_path = cmd_runner.run_cmd(f'realpath {version}')
        logging.info(f'{version_path=}')
    return version_path


@pytest.fixture(params=ApiType.ALL_TYPES)
def test_api(request):
    """This fixture runs the test twice (once for each api)."""
    TestToolkit.tested_api = request.param
    return request.param


@pytest.fixture(params=[get_random_api()])
def random_api(request):
    """Causes the test to run on a randomly-chosen API. The fixture also returns the name of the used API."""
    TestToolkit.tested_api = request.param
    return request.param


@pytest.fixture(scope='module')
def nv_command() -> NvCommand:
    return NvCommand()


@pytest.fixture(autouse=True)
def verify_result_objects():
    yield
    errors = [obj._get_fail_message() for obj in ResultObj._pop_all_instances() if not obj.result]
    if errors:
        raise Exception(f'There are {len(errors)} ResultObj instances that contain a failed result (see documentation '
                        f'of ResultObj class):\n\n' + ('\n' + '-' * 80 + '\n\n').join(errors))


@pytest.fixture(scope='session', autouse=True)
def update_fw_versions_json_file(fw_versions_json_file):
    logging.info(f'fw_versions_json_file path: {fw_versions_json_file}')
    BmcTool.set_fw_versions_json_file(fw_versions_json_file)
    return fw_versions_json_file


@pytest.fixture
def handle_la_marker_in_manufacture(engines, loganalyzer):
    """
    When the test ends, injects the log-analyzer test-start marker as the first line in the log.
    This is intended for tests that cause all log files to be deleted, e.g. by manufacture or factory-reset.
    This fixture calls the 'loganalyzer' fixture just to ensure that these 2 fixtures run in the correct order.
    """
    try:
        marker = engines.dut.run_cmd(r"grep -oE '\S+ \S+ start-LogAnalyzer-.*' " + SyslogConsts.SYSLOG_LOG_PATH,
                                     validate=True).splitlines()[-1]
        marker_find_exception = None
    except BaseException as e:
        marker_find_exception = e
        logger.warning("Failed to find LA start marker. LA will fail after the test finishes.")
    yield

    if marker_find_exception:
        raise marker_find_exception
    oldest_syslog_id = get_oldest_syslog_id(engines.dut)
    new_marker = get_new_start_string(engines.dut, oldest_syslog_id, marker)
    insert_new_start_string(engines.dut, oldest_syslog_id, new_marker)
