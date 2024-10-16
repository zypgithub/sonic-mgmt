import pytest
import allure
import logging
import random
import time
from retry.api import retry_call

from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from infra.tools.validations.traffic_validations.iperf.iperf_runner import IperfChecker
from ngts.common.checkers import is_feature_installed
from ngts.constants.constants import AppExtensionInstallationConstants, SonicConst, DoroceConsts

logger = logging.getLogger()

"""

 DoRoCE Test Cases

 Documentation: https://confluence.nvidia.com/display/SW/SONiC+NGTS+DoRoCE+Documentation

"""

IPERF_VALIDATION = {
    'server': 'ha',
    'client': 'hb',
    'client_args': {
        'server_address': '40.0.0.2',
        'duration': '5',
        'protocol': 'UDP',
        'tos': '104'
    },
    'expect': [
        {
            'parameter': 'bandwidth',
            'operator': '>',
            'type': 'int',
            'value': '1'
        }
    ]
}
PING_VALIDATION = {'sender': 'hb', 'args': {'count': 3, 'dst': '40.0.0.2'}}
RANDOM_CONFIG = random.choice(DoroceConsts.BUFFER_CONFIGURATIONS)
ROCE_PERCENTAGE = random.randint(1, 99)
NON_ROCE_PERCENTAGE = 100 - ROCE_PERCENTAGE


@pytest.fixture(scope='module')
def check_feature_status(cli_objects):
    """
    A fixture to check if DoRoCE or DoAI is installed and enabled
    """
    def check_doai_installed():
        doai_status, msg = is_feature_installed(cli_objects, AppExtensionInstallationConstants.DOAI)
        return doai_status, msg, AppExtensionInstallationConstants.DOAI

    with allure.step('Validating doroce feature is installed'):
        status, msg, ext_name = check_doai_installed()
        if status:
            # TODO: workaround for the issue https://redmine.mellanox.com/issues/2834968
            # happens in push_gate with reload
            # when will be fixed, must be left only reload_qos
            cli_objects.dut.app_ext.disable_app(ext_name, validate=False)
            cli_objects.dut.app_ext.enable_app(ext_name)
            cli_objects.dut.qos.clear_qos()
            time.sleep(10)
            cli_objects.dut.qos.reload_qos()
        else:
            pytest.skip(f"{msg} Skipping the test.")

    with allure.step(f'Validating {ext_name} docker is UP'):
        cli_objects.dut.general.verify_dockers_are_up(dockers_list=[ext_name])


@pytest.fixture(scope='module', autouse=True)
def check_no_roce_configuration(cli_objects, interfaces, players, is_simx, platform_params, check_feature_status):
    is_doroce_enabled = cli_objects.dut.doroce.is_doroce_configuration_enabled()
    if is_doroce_enabled:
        cli_objects.dut.doroce.disable_doroce()
    check_no_roce_configurations(cli_objects, interfaces, players, is_simx, platform_params.hwsku)

    yield

    cli_objects.dut.doroce.disable_doroce()
    check_no_roce_configurations(cli_objects, interfaces, players, is_simx, platform_params.hwsku)
    if is_doroce_enabled:
        cli_objects.dut.doroce.config_doroce_lossless_double_ipool()


@pytest.fixture(scope='module')
def doroce_conf_dict(cli_objects):
    doroce_conf_dict = {'lossless_double_ipool': cli_objects.dut.doroce.config_doroce_lossless_double_ipool,
                        'lossless_single_ipool': cli_objects.dut.doroce.config_doroce_lossless_single_ipool,
                        'lossy_double_ipool': cli_objects.dut.doroce.config_doroce_lossy_double_ipool}
    return doroce_conf_dict


@pytest.mark.physical_coverage
@pytest.mark.build
@pytest.mark.doroce
@pytest.mark.parametrize("configuration", DoroceConsts.BUFFER_CONFIGURATIONS)
@allure.title('DoRoCE test case')
def test_doroce(configuration, doroce_conf_dict, interfaces, cli_objects, players, is_simx):
    """
    Parametrized test, which running base DoRoCE test with different parameters
    :param configuration: DoRoCE configurations. {config:[expected pools]}
    :param doroce_conf_dict: dictionary with different doroce configuration methods
    :param interfaces: interfaces fixture
    :param cli_objects: cli_objects fixture
    :param players: players fixture
    :param is_simx: fixture, True if setup is SIMX, else False
    """
    pools = DoroceConsts.BUFFER_CONFIGURATIONS_DICT[configuration]
    do_doroce_test(configuration, pools, doroce_conf_dict, interfaces, cli_objects, players, is_simx)


@pytest.mark.doroce
@allure.title('DoRoCE toggle ports test case')
def test_doroce_toggle_ports(doroce_conf_dict, interfaces, cli_objects, players, is_simx):
    """
    The Test toggling the related for traffic ports before running base DoRoCE test.
        The test will use random DoRoCE configurations.
    :param doroce_conf_dict: dictionary with different doroce configuration methods
    :param interfaces: interfaces fixture
    :param cli_objects: cli_objects fixture
    :param players: players fixture
    :param is_simx: fixture, True if setup is SIMX, else False
    """
    pools = DoroceConsts.BUFFER_CONFIGURATIONS_DICT[RANDOM_CONFIG]
    do_doroce_test(RANDOM_CONFIG, pools, doroce_conf_dict, interfaces,
                   cli_objects, players, is_simx, do_toggle_ports=True)


def do_doroce_test(conf, pools, doroce_conf_dict, interfaces, cli_objects, players, is_simx, do_toggle_ports=False):
    """
    Base DoRoCE test. Parametrized test, which running base DoRoCE test with different parameters
    """
    doroce_configuration_method = doroce_conf_dict[conf]
    if 'double' in doroce_configuration_method.__name__:
        doroce_configuration_method([ROCE_PERCENTAGE, NON_ROCE_PERCENTAGE])
        retry_call(validate_buffer_pools_percentage, fargs=[cli_objects, conf], tries=8, delay=5, logger=logger)
    else:
        doroce_configuration_method()

    if do_toggle_ports:
        toggle_ports(interfaces, cli_objects)

    cli_objects.dut.doroce.check_buffer_configurations(pools)
    run_ping(players)

    retry_call(validate_iperf_traffic, fargs=[cli_objects, interfaces, players, is_simx, DoroceConsts.ROCE_PG],
               tries=4, delay=5, logger=logger)
    validate_negative_config(doroce_configuration_method)


def run_ping(players):
    with allure.step('Check connectivity by ping traffic'):
        ping_checker = PingChecker(players, PING_VALIDATION)
        retry_call(ping_checker.run_validation, fargs=[], tries=18, delay=5, logger=logger)


def validate_iperf_traffic(cli_objects, interfaces, players, is_simx, prio_group=DoroceConsts.NO_ROCE_PG):
    if is_simx:
        logger.info('Skip traffic validation for SIMX devices')
    else:
        with allure.step('Sending iPerf traffic'):
            run_traffic(cli_objects, players)
        with allure.step('Validate buffers'):
            retry_call(validate_buffer, fargs=[cli_objects, interfaces, prio_group], tries=8, delay=10, logger=logger)


def run_traffic(cli_objects, players):
    cli_objects.dut.watermark.clear_watermarkstat()
    logger.info('Sending iPerf traffic')
    IperfChecker(players, IPERF_VALIDATION).run_validation()


def validate_buffer(cli_objects, interfaces, prio_group):
    stat_results = cli_objects.dut.watermark.show_and_parse_watermarkstat()
    assert stat_results[interfaces.dut_hb_2][prio_group] > DoroceConsts.WATERMARK_THRESHOLD, \
        f'Unexpected watermark value for ROCE traffic({prio_group}).' \
        f' Current: {stat_results[interfaces.dut_hb_2][prio_group]}.' \
        f' Expected threshold: {DoroceConsts.WATERMARK_THRESHOLD}'


def validate_negative_config(configuration_method, exp_err_msg='RoCE is already enabled'):
    with allure.step('Run negative validation'):
        if 'double' in configuration_method.__name__:
            output = configuration_method([ROCE_PERCENTAGE, NON_ROCE_PERCENTAGE])
        else:
            output = configuration_method()
        assert exp_err_msg in output, f'Negative validation failed.\nExpected error message:"{exp_err_msg}" '\
            f'not found in the output: {output}'
        logger.info('The negative validation passed')


def toggle_ports(interfaces, cli_objects):
    ports = [interfaces.dut_ha_2, interfaces.dut_hb_2]
    logger.info("Toggle ports: {}".format(ports))
    for port in ports:
        cli_objects.dut.interface.disable_interface(port)
        cli_objects.dut.interface.enable_interface(port)
    cli_objects.dut.interface.check_link_state(ports)


def check_no_roce_configurations(cli_objects, interfaces, players, is_simx, hwsku):
    with allure.step('Check no RoCE configurations'):
        cli_objects.dut.doroce.check_buffer_configurations(hwsku=hwsku)
        run_ping(players)
        retry_call(validate_iperf_traffic, fargs=[cli_objects, interfaces, players, is_simx],
                   tries=4, delay=5, logger=logger)


def validate_buffer_pools_percentage(cli_objects, conf):
    buffer_info_pool_sizes_dict = cli_objects.dut.doroce.parse_and_show_buffer_information()
    doroce_status_pool_configs_dict = cli_objects.dut.doroce.parse_and_show_doroce_status()

    verifify_percentage(conf, doroce_status_pool_configs_dict)
    compare_sizes(conf, buffer_info_pool_sizes_dict, doroce_status_pool_configs_dict)


def get_pools_to_check(conf):
    """
    The pools changed according to configuration, take one random pool for RoCE and Non-RoCE pool
    :param conf: configuration
    :return: one RoCE and one Non-RoCE pools. Example: ingress_lossless_pool, egress_lossy_pool
    """
    # the pools changed according to configuration, take one random pool for RoCE and Non-RoCE pool
    roce_pools = DoroceConsts.PERCENTAGE_POOLS_DICT[conf][DoroceConsts.ROCE_POOLS]
    roce_pool = random.choice(roce_pools)
    non_roce_pools = DoroceConsts.PERCENTAGE_POOLS_DICT[conf][DoroceConsts.NON_ROCE_POOLS]
    non_roce_pool = random.choice(non_roce_pools)
    return roce_pool, non_roce_pool


def verifify_percentage(conf, doroce_status_pool_configs_dict):
    tested_roce_pool, tested_non_roce_pool = get_pools_to_check(conf)

    # Check the percentage values
    assert int(ROCE_PERCENTAGE) == int(doroce_status_pool_configs_dict[tested_roce_pool]['percentage']), \
        (f'The tested RoCE pool {tested_roce_pool} has unexpected percentage value.'
         f' Expected :{ROCE_PERCENTAGE}, Actual: {doroce_status_pool_configs_dict[tested_roce_pool]["percentage"]}')
    assert int(NON_ROCE_PERCENTAGE) == int(doroce_status_pool_configs_dict[tested_non_roce_pool]['percentage']), \
        (f'The tested Non RoCE pool {tested_roce_pool} has unexpected percentage value.'
         f' Expected :{NON_ROCE_PERCENTAGE}, Actual: {doroce_status_pool_configs_dict[tested_roce_pool]["percentage"]}')

    # Check the sizes affected from percentage values
    # Example: 900 is 90%, 100 is 10%
    #  900/90 is equal to 100/10 with deviation?
    roce_one_perc_size = int(doroce_status_pool_configs_dict[tested_roce_pool]['size']) / int(ROCE_PERCENTAGE)
    non_roce_one_perc_size = int(doroce_status_pool_configs_dict[tested_non_roce_pool]['size']) / int(NON_ROCE_PERCENTAGE)
    concurrent_deviation = abs(roce_one_perc_size - non_roce_one_perc_size)
    assert concurrent_deviation < DoroceConsts.ALLOWED_PERCENTAGE_DEVIATION, \
        (f'The current percentage deviation: {concurrent_deviation} is bigger'
         f' then allowed:{DoroceConsts.ALLOWED_PERCENTAGE_DEVIATION}')


def compare_sizes(conf, buffer_info_pool_sizes_dict, doroce_status_pool_configs_dict):
    tested_roce_pool, tested_non_roce_pool = get_pools_to_check(conf)
    # RoCE pool
    assert buffer_info_pool_sizes_dict[tested_roce_pool] == doroce_status_pool_configs_dict[tested_roce_pool]['size'], \
        (f'The sizes for pool {tested_roce_pool} are different, show buffer'
         f' information: {buffer_info_pool_sizes_dict[tested_roce_pool]},'
         f' show doroce status: {doroce_status_pool_configs_dict[tested_roce_pool]["size"]}')
    # Non RoCE pool
    assert buffer_info_pool_sizes_dict[tested_non_roce_pool] == doroce_status_pool_configs_dict[tested_non_roce_pool]['size'], \
        (f'The sizes for pool {tested_non_roce_pool} are different, show buffer'
         f' information: {buffer_info_pool_sizes_dict[tested_non_roce_pool]},'
         f' show doroce status: {doroce_status_pool_configs_dict[tested_non_roce_pool]["size"]}')
