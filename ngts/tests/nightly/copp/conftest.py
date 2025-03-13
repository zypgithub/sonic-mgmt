import pytest
import logging
import allure

from retry.api import retry_call
from ngts.config_templates.ip_config_template import IpConfigTemplate


logger = logging.getLogger()
CONFIG_DB_COPP_CONFIG = '/etc/sonic/copp_cfg.json'


@pytest.fixture(scope='module', autouse=True)
def copp_configuration(topology_obj, engines, interfaces, cli_objects, setup_name, platform_params, is_air):
    """
    Pytest fixture which are doing configuration for test case based on copp config
    :param topology_obj: topology object fixture
    """
    logger.info('Starting CoPP Common configuration')

    with allure.step('Check that link in UP state'):
        retry_call(cli_objects.dut.interface.check_ports_status,
                   fargs=[[interfaces.dut_ha_1]],
                   tries=10,
                   delay=10,
                   logger=logger)

    # IP config which will be used in test
    ip_config_dict = {
        'dut': [{'iface': interfaces.dut_ha_1, 'ips': [('192.168.1.1', '24'), ('2001:db8:5::1', '60')]}],
        'ha': [{'iface': interfaces.ha_dut_1, 'ips': [('192.168.1.2', '24'), ('2001:db8:5::2', '60')]}]
    }

    logger.info('Disable periodic lldp traffic')
    cli_objects.ha.general.stop_service('lldpad')
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    logger.info('CoPP Common configuration completed')

    yield

    logger.info('Starting CoPP Common configuration cleanup')
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    cli_objects.ha.general.start_service('lldpad')

    cli_objects.dut.general.apply_basic_config(topology_obj, setup_name, platform_params, is_air=is_air)

    logger.info('CoPP Common cleanup completed')


@pytest.fixture(scope='session', autouse=True)
def is_trap_counters_supported(engines):
    """
    Pytest fixture which is verifies if Trap Counters supported on installed image
    """
    logger.info('Verify if Trap Counters supported on installed image')
    try:
        engines.dut.run_cmd('sudo counterpoll flowcnt-trap', validate=True)
        return True
    except BaseException:
        logger.info('The Trap Counters does not supported on this image. All related validations will be skipped')
        return False


@pytest.fixture(scope='module', autouse=True)
def flowcnt_trap_configuration(cli_objects, is_trap_counters_supported):
    """
    Pytest fixture which is doing configuration for test case based on flow counters config
    """
    if is_trap_counters_supported:
        cli_objects.dut.counterpoll.enable_flowcnt_trap()

    yield

    if is_trap_counters_supported:
        cli_objects.dut.counterpoll.disable_flowcnt_trap()
