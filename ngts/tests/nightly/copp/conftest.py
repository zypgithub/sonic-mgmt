import pytest
import logging
import allure

from retry.api import retry_call
from ngts.config_templates.ip_config_template import IpConfigTemplate


logger = logging.getLogger()
CONFIG_DB_COPP_CONFIG = '/etc/sonic/copp_cfg.json'

# LLDP configuration constants
LLDP_PAUSE_PROTOCOLS = ['LLDP', 'LLDP_REBOOT']
LLDP_PAUSE_PLATFORMS = ['sn5640']


@pytest.fixture(scope='module', autouse=True)
def copp_configuration(topology_obj, engines, interfaces, cli_objects, setup_name, platform_params, is_air):
    """
    Pytest fixture which are doing configuration for test case based on copp config
    :param topology_obj: topology object fixture
    """
    logger.info('Starting CoPP Common configuration')
    cli_objects.dut.engine.run_cmd("sudo cp /etc/sonic/config_db.json /etc/sonic/config_db.json.bak")

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

    logger.info("restore config db")
    cli_objects.dut.engine.run_cmd("sudo cp /etc/sonic/config_db.json.bak /etc/sonic/config_db.json")
    cli_objects.dut.general.reload_flow(topology_obj=topology_obj, reload_force=True)


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


@pytest.fixture(autouse=True)
def pause_lldp_before_copp_test(protocol, platform_params, cli_objects):
    platform = platform_params.filtered_platform
    if need_to_pause_lldp(protocol, platform):
        logger.info(f"Pausing LLDP for {platform} platform")
        cli_objects.dut.lldp.pause_lldp()
        yield
        logger.info(f"Enabling LLDP for {platform} platform")
        cli_objects.dut.lldp.resume_lldp()
    else:
        yield


def need_to_pause_lldp(protocol, platform):
    return protocol.upper() in LLDP_PAUSE_PROTOCOLS and platform in LLDP_PAUSE_PLATFORMS


def pause_lldp_after_reboot(protocol, platform, dut_cli_object):
    if need_to_pause_lldp(protocol, platform):
        dut_cli_object.lldp.pause_lldp()
        logger.info(f"Pausing LLDP for {platform} platform after reboot")
