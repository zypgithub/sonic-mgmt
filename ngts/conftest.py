"""

conftest.py

Defines the methods and fixtures which will be used by pytest,
NOTE: Add here only fixtures and methods that can be used for canonical and community setups alike.

if your methods only apply for canonical setups please add them in ngts/tests/conftest.py

"""
import json
import logging
import os
import re
import time

import pytest
import requests
from dotted_dict import DottedDict
from paramiko.ssh_exception import SSHException

from ngts.tools.topology_tools.topology_by_setup import get_topology_by_setup_name_and_aliases
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli, SonicCliStub
from ngts.cli_wrappers.linux.linux_cli import LinuxCli, LinuxCliStub
from ngts.cli_wrappers.nvue.nvue_cli import NvueCli
from ngts.constants.constants import PytestConst, NvosCliTypes, DebugKernelConsts, \
    BugHandlerConst, InfraConst, PlayersAliases
from ngts.tools.infra import get_platform_info, get_devinfo, is_deploy_run, get_chip_type
from ngts.tests.nightly.app_extension.app_extension_helper import APP_INFO
from ngts.helpers.sonic_branch_helper import get_sonic_branch, update_branch_in_topology, update_sanitizer_in_topology, \
    get_sonic_image
from ngts.tools.allure_report.allure_report_attacher import add_fixture_end_tag, add_fixture_name, \
    clean_stored_cmds_with_fixture_scope, update_fixture_scope_list, enable_record_cmds
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.helpers.general_helper import get_all_setups

logger = logging.getLogger()


def pytest_sessionstart(session):
    """Clear cached variables from previous pytest session"""

    session.config.cache.set(PytestConst.LA_DYNAMIC_IGNORES_LIST, None)
    session.config.cache.set(PytestConst.CUSTOM_SKIP_IF_DICT, None)
    session.config.cache.set(PytestConst.CUSTOM_TEST_SKIP_PLATFORM_TYPE, None)
    session.config.cache.set(PytestConst.CUSTOM_TEST_SKIP_BRANCH_NAME, None)
    session.config.cache.set(PytestConst.CUSTOM_TEST_SKIP_IMAGE_TYPE, None)


def pytest_collection(session):
    topology = get_topology_by_setup_name_and_aliases(session.config.option.setup_name, slow_cli=False)
    logger.debug('Get switch devdescription from Noga')
    switch_attributes = topology.players['dut']['attributes'].noga_query_data['attributes']
    devinfo = get_devinfo(switch_attributes)

    platform = json.loads(devinfo).get('platform')
    session.config.cache.set(PytestConst.CUSTOM_TEST_SKIP_PLATFORM_TYPE, platform)
    if is_deploy_run():
        # Required for prevent SSH attempts into DUT at the beginning of deploy image test(in case when device in ONIE)
        branch = 'master'
        image = ''
        session.config.cache.set(PytestConst.IS_SANITIZER_IMAGE, False)
    else:
        branch = get_sonic_branch(topology)
        image = get_sonic_image(topology)

    session.config.cache.set(PytestConst.CUSTOM_TEST_SKIP_BRANCH_NAME, branch)
    session.config.cache.set(PytestConst.CUSTOM_TEST_SKIP_IMAGE_TYPE, image)


pytest_plugins = ('ngts.tools.sysdumps',
                  'ngts.tools.conditional_mark',
                  'ngts.tools.loganalyzer',
                  'ngts.tools.infra',
                  'pytester',
                  'ngts.tools.allure_report',
                  'ngts.tools.mars_test_cases_results',
                  'ngts.tools.loganalyzer_dynamic_errors_ignore.la_dynamic_errors_ignore',
                  'tests.common.plugins.collect_test_data_to_sql',
                  'ngts.tools.ports_modifier',
                  'tests.common.plugins.random_seed'
                  )


def pytest_addoption(parser):
    """
    Parse pytest options
    :param parser: pytest builtin
    """
    logger.info('Parsing pytest options')
    parser.addoption('--setup_name', action='store', required=True, default=None,
                     help='Setup name, example: sonic_tigris_r-tigris-06')
    parser.addoption('--base_version', action='store', default=None, help='Path to base SONiC version')
    parser.addoption('--target_version', action='store', default=None, help='Path to target SONiC version')
    parser.addoption('--wjh_deb_url', action='store', default=None, help='URL path to WJH deb package')
    parser.addoption("--session_id", action="store", default=None, help="Number of mars session id.")
    parser.addoption("--mars_key_id", action="store", default=None, help="mars key id.")
    parser.addoption("--test_name", action="store", default=None,
                     help="a parameter for script check_and_store_sanitizer_dump.py, "
                          "will check for sanitizer failures and store dump under test name")
    parser.addoption("--send_mail", action="store", default=False,
                     help="a boolean parameter for script check_and_store_sanitizer_dump.py, "
                          "will send mail with the sanitizer failures")
    parser.addoption("--skynet", action="store_true", default=False,
                     help="a boolean parameter for identify skynet tests")
    parser.addoption("--tech_support_duration", action="store", default=None, help="duration of tech support for test")
    parser.addoption(PytestConst.run_config_only_arg, action='store_true', help='If set then only the configuration '
                                                                                'part defined in the push_build '
                                                                                'conftest will be executed')
    parser.addoption(PytestConst.run_test_only_arg, action='store_true', help='If set then only the test(push_build) '
                                                                              'will be executed')
    parser.addoption(PytestConst.run_cleanup_only_arg, action='store_true', help='If set then only the cleanup part '
                                                                                 'defined in the push_build conftest '
                                                                                 'will be executed')
    parser.addoption('--app_extension_dict_path', action='store', required=False, default=None,
                     help='''Provide path to application extensions json file.
                          'Example of content: {"p4-sampling":"harbor.mellanox.com/sonic-p4/p4-sampling:0.2.0",
                                      "what-just-happened":"harbor.mellanox.com/sonic-wjh/docker-wjh:1.0.1"} ''')
    parser.addoption("--nvos_api_type", action="store", default='nvue', help="nvue/openapi")
    parser.addoption("--current_topo", dest="current_topo",
                     help="Current topology for example: t0, t1, t1-lag, ptf32, ...")
    parser.addoption("--expected_topo", dest="expected_topo",
                     help="Expected topology, for example: t0, t1, t1-lag, ptf32, ...")
    parser.addoption("--skip_auto_checks", action="store_true", default=False, required=False,
                     help="Whether to skip 'is debug-kernel/coverage/sanitizer' auto checks for the session, or not")
    parser.addoption("--sonic-topo", action="store",
                     help="The topo for SONiC testing, for example: t0, t1, t1-lag, ptf32, ...")
    parser.addoption('--default_pass_env_var', action='store', default='',
                     help='Which environment variable to use for default dut password')
    parser.addoption("--skip_bug_handler_action", action="store_true", default=False, required=False,
                     help="Whether to skip (True) log analyzer bug handler actions when loganalyzer is enabled, or not (False)")
    parser.addoption('--fail_install_if_secure_boot_off', action='store', default='yes',
                     help='Whether to fail NVOS installation due to disabled Secure-Boot')
    parser.addoption('--skip_weekend_cases', required=False, action='store', default="",
                     help='Parameter used to decide which kind of test case to run.'
                          'when it is "yes", it will only run "Daily" test case, '
                          'when it is "no", it will only run weekend test cases, '
                          'when it is other value, it will run both daily and weekend test cases,'
                          'user need to define which is daily and weekend test case')


def pytest_runtest_call(item):
    """
    Pytest hook which is executed at the calling of test case
    :param item: pytest builtin
    """
    topology_obj = item.funcargs.get('topology_obj')
    if topology_obj:
        add_fixture_end_tag(topology_obj)


def pytest_fixture_setup(fixturedef, request):
    """
    Pytest hook which is executed at the beginning of each fixture
    :param fixturedef: pytest builtin
    :param request: pytest builtin
    """
    func_name = request._pyfuncitem.name
    for func in request.session.items:
        if func.name == func_name and getattr(func, 'funcargs', None):
            topology_obj = func.funcargs.get('topology_obj')
            if topology_obj:
                add_fixture_name(topology_obj, request.fixturename, fixturedef.scope)


def pytest_fixture_post_finalizer(fixturedef, request):
    """
    Pytest hook which is executed at the beginning of each fixture
    :param fixturedef: pytest builtin
    :param request: pytest builtin
    """
    func_name = request._pyfuncitem.name
    for func in request.session.items:
        if func.name == func_name and getattr(func, 'funcargs', None):
            topology_obj = func.funcargs.get('topology_obj')
            if topology_obj:
                if getattr(func, 'rep_setup', None) and getattr(func, 'rep_call',
                                                                None) and func.rep_setup.passed and func.rep_call.failed:
                    update_fixture_scope_list(topology_obj, fixturedef.argname, fixturedef.scope)
                else:
                    clean_stored_cmds_with_fixture_scope(topology_obj, fixturedef.argname, fixturedef.scope)


@pytest.fixture(scope="package")
def app_extension_dict_path(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: app_extension_dict
    """
    return request.config.getoption('--app_extension_dict_path')


@pytest.fixture(scope="session")
def verify_secure_boot(request):
    """
    For NVOS, understand whether the user wants not to fail installation if Secure-Boot is disabled.
    user can skip this check only if this execution line option is given with value 'no'/'false' (no case sensitivity)

    :return: True if should fail installation if Secure-Boot is disabled; False, otherwise (when user specifies it)
    """
    value = request.config.getoption('--fail_install_if_secure_boot_off')
    value = value.lower() if value and isinstance(value, str) else ''
    return value not in ['no', 'false']


@pytest.fixture(scope="session")
def base_version(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: base_version argument value
    """
    return request.config.getoption('--base_version')


@pytest.fixture(scope="session")
def target_version(request):
    """
    Method for getting target version from pytest arguments
    :param request: pytest builtin
    :return: target_version argument value
    """
    return request.config.getoption('--target_version')


@pytest.fixture(scope="session")
def wjh_deb_url(request):
    """
    Method for getting what-just-happened deb file URL from pytest arguments
    :param request: pytest builtin
    :return: wjh_deb_url argument value
    """
    return request.config.getoption('--wjh_deb_url')


@pytest.fixture(scope='session')
def setup_name(request):
    """
    Method for get setup name from pytest arguments
    :param request: pytest builtin
    :return: setup name
    """
    return request.config.getoption('--setup_name')


@pytest.fixture(scope="session")
def skip_weekend_cases(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: base_version argument value
    """
    return request.config.getoption('--skip_weekend_cases')


@pytest.fixture(scope='session', autouse=True)
def topology_obj(setup_name, request):
    """
    Fixture which create topology object before run tests and doing cleanup for ssh engines after test executed
    :param setup_name: example: sonic_tigris_r-tigris-06
    :param request: pytest builtin
    """
    logger.debug('Creating topology object')
    topology = get_topology_by_setup_name_and_aliases(setup_name, slow_cli=False)
    # Update CLI classes according to the current SONiC branch
    branch = request.session.config.cache.get(PytestConst.CUSTOM_TEST_SKIP_BRANCH_NAME, None)
    update_branch_in_topology(topology, branch)
    is_sanitizer = request.session.config.cache.get(PytestConst.IS_SANITIZER_IMAGE, None)
    update_sanitizer_in_topology(topology, is_sanitizer=is_sanitizer)
    update_topology_with_cli_class(topology, request)
    export_cli_type_to_cache(topology, request)
    enable_record_cmds(topology)

    if request.config.option.ports_number == "max":
        # This is used for the fast reboot with max ports
        config_db = topology.players['dut']['cli'].general.get_config_db()
        topology.players_all_ports['dut'] = list(config_db['PORT'].keys())
    yield topology

    logger.debug('Cleaning-up the topology object')
    for player_name, player_attributes in topology.players.items():
        player_attributes['engine'].disconnect()


def update_default_password(dut, request):
    default_password_env_var = request.config.getoption('--default_pass_env_var')
    if default_password_env_var:
        dut_password = os.getenv(default_password_env_var)
        assert dut_password is not None, 'Default environment password variable is not provided'
        dut['engine'] = LinuxSshEngine(dut['engine'].ip, dut['engine'].username,
                                       dut_password)


def update_topology_for_mlnxos_setups(topology):
    if 'sl_serial' in topology.players.keys():
        topology.players['dut_serial'] = topology.players.pop('sl_serial')
    if 'vm_player' in topology.players.keys():
        topology.players['server'] = topology.players.pop('vm_player')


@pytest.fixture(scope='session')
def cli_objects(topology_obj):
    cli_obj_data = DottedDict()
    for player in topology_obj.players:
        cli_obj_data[player] = topology_obj.players[player]['cli']
    return cli_obj_data


def export_cli_type_to_cache(topology, request):
    """
    This function will cache set a variable called CLI_TYPE that indicates what is the Cli Type, NVUE Or Sonic.
    :param topology: topology object
    :param request: pytest builtin
    """
    cli_type = topology[0]['dut']['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE']
    request.session.config.cache.set('CLI_TYPE', cli_type)
    os.environ['CLI_TYPE'] = cli_type


def update_topology_with_cli_class(topology, request=None):
    # TODO: determine player type by topology attribute, rather than alias
    nvos_setup = False
    for player_key, player_info in topology.players.items():
        if player_key == 'dut':
            if player_info['attributes'].noga_query_data['attributes']['Topology Conn.'][
                    'CLI_TYPE'] in NvosCliTypes.NvueCliTypes:
                update_nvos_topology(topology, player_info, request)
                nvos_setup = True
            else:
                player_info['cli'] = SonicCli(topology, dut_alias=player_key)
                player_info.update({'stub_cli': SonicCliStub(topology)})
        elif player_key == 'dut-b':
            player_info['cli'] = SonicCli(topology, dut_alias='dut-b')

        elif player_key == 'left_tg' or player_key == 'right_tg':
            player_info['cli'] = SonicCli(topology, dut_alias=player_key)
            player_info.update({'stub_cli': SonicCliStub(topology)})
        else:
            player_info['cli'] = LinuxCli(player_info['engine'])
            player_info.update({'stub_cli': LinuxCliStub(player_info['engine'])})

    if nvos_setup:
        update_topology_for_mlnxos_setups(topology)  # for NVOS setups only


def update_nvos_topology(topology, player_info, request):
    if player_info['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE'] != "NVUE":
        player_info['engine'] = LinuxSshEngine(player_info['engine'].ip, player_info['engine'].username,
                                               player_info['engine'].password)
        player_info['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE'] = "NVUE"
        player_info['attributes'].noga_query_data['attributes']['Common']['Description'] = "dut"
    player_info['cli'] = NvueCli(topology)
    player_info['is_nvos'] = True
    switch_type = player_info['attributes'].noga_query_data['attributes']['Specific'].get('TYPE', '')
    if switch_type == NvosCliTypes.CumulusCliType:
        player_info['is_cumulus'] = True
    update_default_password(player_info, request)


@pytest.fixture(scope='session')
def show_platform_summary(topology_obj):
    return get_platform_info(topology_obj)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Pytest hook which are executed in all phases: Setup, Call, Teardown
    :param item: pytest builtin
    :param call: pytest builtin
    """
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # set a report attribute for phase of a call, which can
    # be "setup", "call", "teardown"

    setattr(item, "rep_" + rep.when, rep)


@pytest.fixture(scope='session')
def dut_mac(engines, cli_objects):
    """
    Fixture which get DUT mac address from DUT config_db.json file
    :param engines: engines fixture
    :param cli_objects: cli_objects fixture
    :return: dut mac address
    """
    logger.info('Getting DUT mac address')
    config_db = cli_objects.dut.general.get_config_db()
    dut_mac = config_db.get('DEVICE_METADATA').get('localhost').get('mac')
    logger.info('DUT mac address is: {}'.format(dut_mac))
    return dut_mac


@pytest.fixture(scope='session')
def chip_type(topology_obj):
    switch_attributes = topology_obj.players['dut']['attributes'].noga_query_data['attributes']
    return get_chip_type(switch_attributes)


@pytest.fixture(scope='session')
def sonic_version(engines):
    """
    Pytest fixture which are returning current SONiC installed version
    :param engines: dictionary with available engines
    :return: string with current SONiC version
    """
    sonic_version_output = engines.dut.run_cmd('sudo sonic-cfggen -y /etc/sonic/sonic_version.yml -v build_version')
    sonic_ver = sonic_version_output.strip()
    return sonic_ver


@pytest.fixture(scope='session')
def sonic_branch(topology_obj):
    """
    Pytest fixture which are returning current SONiC branch which defined in the /etc/sonic/sonic_version.yml
    :param topology_obj: topology_obj fixture
    :return: the branch name
    """
    return get_sonic_branch(topology_obj)


@pytest.fixture(scope='session', autouse=True)
def should_skip_checking_fixture(request):
    if request.config.getoption("--skip_auto_checks"):
        logger.info('NVOS: Should skip auto test pre-checks')
        return True
    else:
        return False


@pytest.fixture(scope='session', autouse=True)
def is_sanitizer_image(topology_obj, should_skip_checking_fixture):
    pytest.is_sanitizer = False

    if should_skip_checking_fixture:
        logger.info('NVOS: Skip sanitizer run check')
        return pytest.is_sanitizer

    update_sanitizer_in_topology(topology_obj)
    pytest.is_sanitizer = topology_obj.players['dut']['sanitizer']
    return pytest.is_sanitizer


@pytest.fixture(scope='session', autouse=True)
def is_code_coverage_run(topology_obj, should_skip_checking_fixture):
    pytest.is_code_coverage = False

    if should_skip_checking_fixture:
        logger.info('NVOS: Skip coverage run check')
        return pytest.is_code_coverage

    try:
        pytest.is_code_coverage = bool(topology_obj.players['dut']['cli'].general.echo('${COVERAGE_FILE}'))
        logger.info(f'Code coverage image: {pytest.is_code_coverage}')
    except SSHException as err:
        logger.warning(f'Unable to check if its code coverage run. Assuming that the device is not reachable. '
                       f'Setting the is_code_coverage_run as False, '
                       f'Got error: {err}')
    return pytest.is_code_coverage


@pytest.fixture(scope='session', autouse=True)
def is_debug_kernel_run(engines, should_skip_checking_fixture):
    pytest.is_debug_kernel = False

    if should_skip_checking_fixture:
        logger.info('NVOS: Skip debug kernel run check')
        return pytest.is_debug_kernel

    try:
        output = engines.dut.run_cmd(f"sudo ls {DebugKernelConsts.KMEMLEAK_PATH}")
        pytest.is_debug_kernel = False if "No such file or directory" in output else True  # only in debug kernel version we have this file
    except SSHException as err:
        logger.warning(f'Unable to check if its debug kernel run. Assuming that the device is not reachable. '
                       f'Setting the is_debug_kernel_run as False, '
                       f'Got error: {err}')
    return pytest.is_debug_kernel


@pytest.fixture(scope='session', autouse=True)
def is_ci_run(setup_name):
    pytest.is_ci_run = "_CI_" in setup_name
    return pytest.is_ci_run


@pytest.fixture(scope="session", autouse=True)
def mars_key_id(request):
    return request.config.getoption("--mars_key_id")


@pytest.fixture(scope='session', autouse=True)
def is_mars_run(mars_key_id):
    pytest.is_mars_run = True if mars_key_id else False
    return pytest.is_mars_run


@pytest.fixture(scope='session', autouse=True)
def dynamic_ignore_set():
    pytest.dynamic_ignore_set = set()


@pytest.fixture(scope='session')
def platform_params(show_platform_summary, setup_name, topology_obj):
    """
    Method for getting all platform related data
    :return: dictionary with platform data
    """
    platform_data = DottedDict()
    platform_data.platform = show_platform_summary['platform']
    platform_data.filtered_platform = re.search(
        r"(msn\d{4}a\w?|msn\d{4}c|msn\d{4}|sn\d{4}|qm\d{4}|q\d{4}|mqm\d{4}|mbf.*c|900.*a|N5110_LD|N5100_LD)",
        show_platform_summary['platform'], re.IGNORECASE).group(1)
    platform_data.hwsku = show_platform_summary['hwsku']
    platform_data.setup_name = setup_name
    platform_data.asic_type = show_platform_summary["asic_type"]
    platform_data.asic_count = show_platform_summary["asic_count"]
    platform_data.host_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
    return platform_data


@pytest.fixture(scope="session")
def upgrade_params(base_version, target_version, wjh_deb_url):
    """
    Method for getting all upgrade related parameters
    :return: dictionary with upgrade parameters
    """
    upgrade_data = DottedDict()

    upgrade_data.base_version = base_version
    upgrade_data.target_version = target_version
    upgrade_data.wjh_deb_url = wjh_deb_url
    upgrade_data.is_upgrade_required = False
    if base_version and target_version:
        upgrade_data.is_upgrade_required = True
    else:
        logger.info('Either one or all the upgrade arguments is missing, skipping the upgrade flow')
    return upgrade_data


@pytest.fixture(scope="session")
def shared_params():
    shared_dict = DottedDict()
    shared_dict.app_ext_is_app_ext_supported = False
    shared_dict.app_ext_app_name = APP_INFO["name"]
    shared_dict.app_ext_app_repository_name = APP_INFO["repository"]
    shared_dict.app_ext_version = APP_INFO["shut_down"]["version"]

    return shared_dict


@pytest.fixture(scope="session")
def players(topology_obj):
    return topology_obj.players


@pytest.fixture(scope="session")
def is_simx(platform_params, is_air):
    is_simx_setup = False
    if re.search('simx', platform_params.setup_name):
        is_simx_setup = True
    if is_air:
        is_simx_setup = True
    return is_simx_setup


@pytest.fixture(scope="session")
def is_performance(platform_params):
    is_perf_setup = False
    if re.search('performance', platform_params.setup_name):
        is_perf_setup = True
    return is_perf_setup


@pytest.fixture(scope='session')
def is_air(platform_params):
    is_air_setup = False
    if re.search('air', platform_params.setup_name.lower()):
        is_air_setup = True
    return is_air_setup


def cleanup_last_config_in_stack(cleanup_list):
    """
    Execute the last function in the cleanup stack
    :param cleanup_list: list with functions to cleanup
    :return: None
    """
    func, args = cleanup_list.pop()
    func(*args)


@pytest.fixture(scope="session")
def nvos_api_type(request):
    """
    Method for getting nvos_api_type from pytest arguments
    :param request: pytest builtin
    :return: nvos_api_type argument value
    """
    return request.config.getoption('--nvos_api_type')


@pytest.fixture(scope='session')
def engines(topology_obj):
    engines_data = DottedDict()
    for player in topology_obj.players:
        engines_data[player] = topology_obj.players[player]['engine']
    return engines_data


@pytest.fixture(scope='function', autouse=True)
def test_name(request):
    """
    Method for getting the test name parameter
    :param request: pytest builtin
    :return: the test name, i.e, push_gate
    """
    pytest.test_name = request.node.name
    return pytest.test_name


@pytest.fixture(scope='function', autouse=True)
def disable_loganalyzer(request):
    if request.config.getoption("--disable_loganalyzer", default=False) \
            or "disable_loganalyzer" in request.keywords:
        logging.info("Log analyzer is disabled")
        return True
    return False


@pytest.fixture(scope='function', autouse=True)
def should_skip_bug_handler_action(request, disable_loganalyzer):
    if disable_loganalyzer or request.config.getoption("--skip_bug_handler_action"):
        logger.info('Bug handler WILL skip actions for LA errors')
        return True
    else:
        logger.info('Bug handler will NOT skip actions for LA errors')
        return False


@pytest.fixture(autouse=False)
def setups_list():
    return get_all_setups()
