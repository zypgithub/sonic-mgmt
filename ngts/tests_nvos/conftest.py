import datetime
import logging
import random
import smtplib
import time
import os
from email.mime.text import MIMEText
from typing import Dict

import pytest
from dotted_dict import DottedDict
from retry import retry

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from infra.tools.sql.connect_to_mssql import ConnectMSSQL
from ngts.cli_wrappers.linux.linux_general_clis import LinuxGeneralCli
from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli
from ngts.cli_wrappers.openapi.openapi_command_builder import OpenApiRequest
from ngts.constants.constants import DbConstants, CliType, DebugKernelConsts, InfraConst
from ngts.nvos_constants.constants_nvos import ApiType, OperationTimeConsts, OutputFormat
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
from ngts.nvos_tools.Devices.EthDevice import EthSwitch
from ngts.nvos_tools.cli_coverage.nvue_cli_coverage import NVUECliCoverage
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.DiskTool import DiskTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.TrafficGeneratorTool import TrafficGeneratorTool
from ngts.nvos_tools.system.System import System
from ngts.scripts.code_coverage.code_coverage_consts import NvosConsts
from ngts.scripts.code_coverage.test_code_coverage import extract_python_coverage_for_nvos
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_config_utils import clear_conf
from ngts.tools.test_utils.nvos_general_utils import wait_for_ldap_nvued_restart_workaround, set_base_configurations, \
    set_base_configurations_cl

logger = logging.getLogger()


def pytest_addoption(parser):
    """
    Parse NVOS pytest options
    :param parser: pytest build in
    """
    logger.info('Parsing NVOS pytest options')
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
    if "server" in topology_obj.players:
        engines_data.server = topology_obj.players['server']['engine']
    if "sonic-mgmt" in topology_obj.players:
        engines_data.sonic_mgmt = topology_obj.players['sonic-mgmt']['engine']

    TestToolkit.update_engines(engines_data)
    return engines_data


def update_engine_dut_mgmt_port(topology, dut_engine: LinuxSshEngine, dut_device: BaseDevice):
    def attach_res_to_allure(available_ports_names, available_ports_ips, chosen_port_name, chosen_port_ip):
        attachment = (f'All ports: {available_ports_names} - {available_ports_ips}\n'
                      f'Chosen port: {chosen_port_name} - {chosen_port_ip}')
        allure.orig_allure.attach(attachment, 'dut_engine_mgmt_port_used_for_session', allure.orig_allure.attachment_type.TEXT)

    mgmt_ports = dut_device.get_mgmt_ports()
    if not mgmt_ports or len(mgmt_ports) == 1:
        logger.info('keep original dut engine ip')
        attach_res_to_allure(mgmt_ports, None, mgmt_ports[0] if mgmt_ports else None, dut_engine.ip)
        return

    dut_setup_specific_attributes: Dict[str, str] = topology.players['dut']['attributes'].noga_query_data['attributes']['Specific']
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
def start_sm(engines, traffic_available):
    """
    Starts OpenSM
    """
    if traffic_available:
        result = OpenSmTool.start_open_sm(engines)
        if not result.result:
            logging.warning("Failed to start openSM")
    else:
        logging.warning("Traffic is not available on this setup")


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


@pytest.fixture(scope='function', autouse=True)
def log_test_wrapper(request, engines):
    pytest.item = request.node
    test_name = request.module.__name__
    pytest.s_time = time.time()
    logging.info(' ---------------- TEST STARTED - {test_name} ---------------- '.format(test_name=test_name))
    if 'no_log_test_wrapper' in request.keywords:
        return
    try:
        SendCommandTool.execute_command(LinuxGeneralCli(engines.dut).clear_history)
    except BaseException as exc:
        logger.error(" the command 'history -c' failed and this is the exception info : {}".format(exc))
        # should not fail the test
        pass


@pytest.fixture(scope='session')
def interfaces(topology_obj):
    interfaces_data = DottedDict()
    interfaces_data.ha_dut_1 = topology_obj.ports['ha-dut-1']
    interfaces_data.hb_dut_1 = topology_obj.ports['hb-dut-1']
    return interfaces_data


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


def clear_config(markers=None):
    with allure.step("Clear config"):
        if isinstance(TestToolkit.devices.dut, EthSwitch):
            clear_switch_config(markers, set_base_config_function=set_base_configurations_cl)
        else:
            clear_switch_config(markers, set_base_config_function=set_base_configurations)


def clear_switch_config(markers=None, set_base_config_function=None):
    logging.info("Clear config")
    try:
        TestToolkit.update_apis(ApiType.NVUE)
        clear_conf(TestToolkit.engines.dut, markers, set_base_config_function)
    except Exception as err:
        logging.warning("Failed to clear config:" + str(err))
    finally:
        logging.info('Clear global OpenApi changeset and payload')
        OpenApiRequest.clear_changeset_and_payload()


def pytest_exception_interact(report):
    with allure.step("Handle exception"):
        if TestToolkit and hasattr(TestToolkit, 'engines') and TestToolkit.engines and TestToolkit.engines.dut:
            if isinstance(TestToolkit.devices.dut, EthSwitch):
                eth_handle_exception()
            else:
                ib_handle_exception()

        if pytest and hasattr(pytest, 'item') and pytest.item:
            save_results_and_clear_after_test(pytest.item)
        logging.error(f'----------- The test failed - an exception occurred: ----------- \n{report.longreprtext}')


def ib_handle_exception():
    try:
        logging.info("Handle ib exception")
        TestToolkit.engines.dut.run_cmd("docker ps")
        TestToolkit.engines.dut.run_cmd("systemctl --type=service")
    except BaseException as err:
        logging.warning(err)


def eth_handle_exception():
    logging.info("Handle eth exception")


@pytest.hookimpl(trylast=True)
def pytest_runtest_call(item):
    save_results_and_clear_after_test(item)


def save_results_and_clear_after_test(item):
    markers = item.keywords._markers
    try:
        logging.info(' ---------------- The test completed successfully ---------------- ')
        run_cli_coverage(item, markers)
    except KeyboardInterrupt:
        raise
    except Exception as err:
        logging.exception(' ---------------- The test failed - an exception occurred: ---------------- ')
        raise AssertionError(err)
    finally:
        if hasattr(item, 'active_remote_aaa_server') and item.active_remote_aaa_server:
            clear_security_config(item)
        clear_config(markers)


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
                extract_python_coverage_for_nvos(dest=NvosConsts.DEST_PATH, engines=engines, cli_obj=cli_obj)


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
