import os
import pytest
import logging
import random

from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.config_templates.frr_config_template import FrrConfigTemplate
from ngts.helpers.adaptive_routing_helper import ArHelper
from ngts.common.checkers import is_feature_installed
from ngts.constants.constants import AppExtensionInstallationConstants, SonicConst
from ngts.tests.nightly.adaptive_routing.constants import ArConsts
from ngts.helpers.reboot_reload_helper import get_supported_reboot_reload_types_list
from ngts.tests.conftest import get_dut_loopbacks
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from infra.tools.redmine.redmine_api import is_redmine_issue_active


logger = logging.getLogger()
ar_helper = ArHelper()


@pytest.fixture(scope='module')
def is_ar_supported(chip_type, sonic_branch):
    """
    This method is to verify if AR supported at chip type
    :param chip_type: chip_type fixture
    :param sonic_branch: sonic_branch fixture
    """
    if chip_type == 'SPC' or chip_type == 'SPC2' or chip_type == 'SPC3':
        pytest.skip('Adaptive Routing feature is supported on SPC4 and higher chip types')
    if sonic_branch in ['201911', '202012', '202205', '202211']:
        pytest.skip('Adaptive Routing feature is supported at 202305 and higher')


@pytest.fixture(scope='module')
def wa_for_orchagent_issue(cli_objects, engines, platform_params):
    """
    This method is applying workaround due to RM #3606485, and adds a SAI parameter to the sai profile.
    """
    if is_redmine_issue_active([3606485]):
        platform = platform_params['platform']
        hwsku = platform_params['hwsku']
        sai_profile_dir = SonicConst.SAI_PROFILE_FILE_PATH.format(PLATFORM=platform, HWSKU=hwsku)
        sai_flag = "SAI_HOSTIF_OPER_STATUS_UPDATE_BY_APP=1"
        sai_profile_backup = sai_profile_dir + ".bk"
        # Create and save a backup file for SAI profile
        engines.dut.run_cmd(f'sudo bash -c \'cp {sai_profile_dir} {sai_profile_backup}\'')
        # ADD the WA script and reload
        engines.dut.run_cmd(f'sudo bash -c \'echo "{sai_flag}" >> {sai_profile_dir}\'')
        cli_objects.dut.general.reload_configuration(force=True)

        yield
        # Restore the original SAI profile and reload
        engines.dut.run_cmd(f'sudo bash -c \'cp {sai_profile_backup} {sai_profile_dir}\'')
        cli_objects.dut.general.reload_configuration(force=True)


@pytest.fixture(scope='module')
def set_config_db_split_mode(cli_objects, topology_obj):
    """
    This method is to set split mode for config_db.json
    :param cli_objects: cli_objects fixture
    :param topology_obj: topology_obj fixture
    @yield: configures split mode (before test)
    """
    logger.info('Setting "docker_routing_config_mode": "split" in config_db.json')
    cli_objects.dut.general.update_config_db_docker_routing_config_mode(topology_obj)
    yield
    logger.info('Restore original mode in config_db.json')
    cli_objects.dut.general.save_configuration()
    cli_objects.dut.general.update_config_db_docker_routing_config_mode(topology_obj,
                                                                        remove_docker_routing_config_mode=True)


@pytest.fixture(scope='module', autouse=True)
def check_feature_status(cli_objects, is_ar_supported):
    """
    This method is to verify if doAI service installed
    :param cli_objects: cli_objects fixture
    :param is_ar_supported: is_ar_supported fixture
    """
    logger.info('Validating doAI service is installed')
    doai_status, msg = is_feature_installed(cli_objects, AppExtensionInstallationConstants.DOAI)
    if not doai_status:
        pytest.skip(f"{msg} Skipping the test.")


@pytest.fixture(scope='class')
def ar_base_config_default_vrf(topology_obj, cli_objects, interfaces, engines):
    """
    This method is to apply DUT basic configuration
    :param topology_obj: topology_obj fixture
    :param cli_objects: cli_objects fixture
    :param interfaces: interfaces fixture
    :param engines: interfaces fixture
    :return: transceiver port
    """
    ecmp_tx_port_list = [interfaces.dut_hb_1, interfaces.dut_hb_2]
    ip_config_dict = {
        'dut': [
            {'iface': interfaces.dut_ha_1,
             'ips': [(ArConsts.V4_CONFIG['dut_ha_1'], '24'), (ArConsts.V6_CONFIG['dut_ha_1'], '64')]},
            {'iface': interfaces.dut_hb_1,
             'ips': [(ArConsts.V4_CONFIG['dut_hb_1'], '24'), (ArConsts.V6_CONFIG['dut_hb_1'], '64')]},
            {'iface': interfaces.dut_hb_2,
             'ips': [(ArConsts.V4_CONFIG['dut_hb_2'], '24'), (ArConsts.V6_CONFIG['dut_hb_2'], '64')]},
        ],
        'ha': [
            {'iface': interfaces.ha_dut_1,
             'ips': [(ArConsts.V4_CONFIG['ha_dut_1'], '24'), (ArConsts.V6_CONFIG['ha_dut_1'], '64')]}
        ],
        'hb': [
            {'iface': interfaces.hb_dut_1,
             'ips': [(ArConsts.V4_CONFIG['hb_dut_1'], '24'), (ArConsts.V6_CONFIG['hb_dut_1'], '64')]},
            {'iface': interfaces.hb_dut_2,
             'ips': [(ArConsts.V4_CONFIG['hb_dut_2'], '24'), (ArConsts.V6_CONFIG['hb_dut_2'], '64')]}
        ]
    }

    base_folder = os.path.dirname(os.path.abspath(__file__)) + '/' + ArConsts.FRR_CONFIG_FOLDER
    frr_config_dict = {
        'dut': {
            'configuration': {'config_name': 'dut_frr_config.conf', 'path_to_config_file': base_folder},
            'cleanup': ['configure terminal', 'no router bgp', 'exit', 'exit']},
        'ha': {
            'configuration': {'config_name': 'ha_frr_config.conf', 'path_to_config_file': base_folder},
            'cleanup': ['configure terminal', 'no router bgp', 'exit', 'exit']},
        'hb': {
            'configuration': {'config_name': 'hb_frr_config.conf', 'path_to_config_file': base_folder},
            'cleanup': ['configure terminal', 'no router bgp', 'exit', 'exit']}
    }

    ar_helper.enable_doai_service(cli_objects)
    ar_helper.enable_ar_function(cli_objects)
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    ar_helper.add_dummy_interface_hb(cli_objects)
    logger.info('Cleanup frr config, in case there is useless bgp configuration exist')
    FrrConfigTemplate.cleanup(topology_obj, frr_config_dict)
    FrrConfigTemplate.configuration(topology_obj, frr_config_dict)

    logger.info('Verify bgp neighbor  established')
    ar_helper.verify_bgp_neighbor(cli_objects)
    logger.info('Verify ecmp routes')
    ar_helper.verify_ecmp_route(cli_objects, interfaces)
    tx_port = ar_helper.get_tx_port_in_ecmp(cli_objects, ecmp_tx_port_list, ArConsts.PACKET_NUM_SMALLEST)
    ar_helper.enable_ar_port(cli_objects, ecmp_tx_port_list, restart_swss=True)
    logger.info('Config save and reload, then check dockers and ports status')
    ar_helper.config_save_reload(cli_objects, topology_obj, reload_force=True)
    ar_helper.verify_bgp_neighbor(cli_objects)

    yield tx_port

    ar_helper.disable_ar_port(cli_objects, ecmp_tx_port_list)
    FrrConfigTemplate.cleanup(topology_obj, frr_config_dict)
    ar_helper.del_dummy_interface_hb(cli_objects, ArConsts.DUMMY_INTF['name'])
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    ar_helper.disable_ar(cli_objects)
    ar_helper.disable_doai_service(cli_objects)


@pytest.fixture(scope='class')
def ar_max_ports_config(topology_obj, cli_objects, interfaces, engines):
    """
    This method is to apply L3 config for all DUT ports
    :param topology_obj: topology_obj fixture
    :param cli_objects: cli_objects fixture
    :param interfaces: interfaces fixture
    :param engines: interfaces fixture
    """
    ar_helper.enable_doai_service(cli_objects)
    ar_helper.enable_ar_function(cli_objects)
    ports_list = ar_helper.get_all_ports(topology_obj)
    dut_ports_config = []
    for number, iface_name in enumerate(ports_list):
        dut_ports_config.append({'iface': iface_name, 'ips': [(f"10.10.{number}.1", '24')]})
    ip_config_dict = {
        'dut': dut_ports_config
    }
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    ar_helper.enable_ar_port(cli_objects, ports_list)
    cli_objects.dut.general.save_configuration()

    yield ports_list

    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    ar_helper.disable_ar_port(cli_objects, ports_list)
    ar_helper.disable_ar(cli_objects)
    ar_helper.disable_doai_service(cli_objects)
    ar_helper.config_save_reload(cli_objects, topology_obj, reload_force=True)


@pytest.fixture(scope='function')
def config_ecmp_ports_speed_as_10G(interfaces, cli_objects):
    """
    This method is to configure ecmp ports speed to 10G
    :param interfaces: interfaces fixture
    :param cli_objects: cli_objects fixture
    """
    logger.info(f'Get original port speed of {interfaces.dut_hb_1, interfaces.dut_hb_2}')
    original_intf_speeds = cli_objects.dut.interface.get_interfaces_speed(
        [interfaces.dut_hb_1, interfaces.dut_hb_2])
    ar_helper.config_ecmp_ports_speed_to_10G(cli_objects, interfaces)

    yield

    ar_helper.restore_ecmp_ports_speed(cli_objects, original_intf_speeds)


@pytest.fixture(scope='function')
def config_vlan_intf(cli_objects):
    """
    This method is to configure vlan interface
    :param cli_objects: cli_objects fixture
    """
    ar_helper.add_dummy_vlan_intf(cli_objects)

    yield

    ar_helper.del_dummy_vlan_intf(cli_objects)


@pytest.fixture(scope='function')
def config_lag(cli_objects, topology_obj):
    """
    This method is to configure LAG interface
    :param cli_objects: cli_objects fixture
    :param topology_obj: topology_obj fixture
    """
    lb = get_dut_loopbacks(topology_obj)
    ar_helper.add_lacp_intf(cli_objects, lb)

    yield

    ar_helper.del_lacp_intf(cli_objects, lb[0][0])


@pytest.fixture(scope='function')
def configure_port_shaper(cli_objects, interfaces, engines, topology_obj):
    """
    This fixture is to config the a small shaper value on the egress port to create the buffer congestion.
    :param cli_objects: cli_objects fixture
    :param interfaces: interfaces fixture
    :param engines fixture
    :param topology_obj: topology_obj fixture
    """
    cli_objects.dut.general.save_configuration()
    logger.info('Copy actual config_db.json to DUT home dir')
    engines.dut.run_cmd(f'sudo cp {ArConsts.CONFIG_DB_FILE_PATH}{ArConsts.CONFIG_DB_FILE_NAME} '
                        f'{ArConsts.DUT_HOME_DIR}')

    logger.info('Configure port scheduler')
    port_scheduler = "port_scheduler"
    with allure.step("Config the shaper of the port"):
        cli_objects.dut.interface.config_port_scheduler(port_scheduler, 1)
        cli_objects.dut.interface.config_port_qos_map(interfaces.dut_hb_1, port_scheduler)

    logger.info('Disable packet aging')
    ar_helper.disable_packet_aging(engines)

    yield

    logger.info('Enable back packet aging')
    ar_helper.enable_packet_aging(engines)
    logger.info('Configure port scheduler to default params')
    cli_objects.dut.interface.config_port_scheduler(port_scheduler, 0)

    logger.info(f'Move file {ArConsts.CONFIG_DB_FILE_NAME} from {ArConsts.DUT_HOME_DIR} to '
                f'{ArConsts.CONFIG_DB_FILE_PATH}')
    engines.dut.run_cmd(f'sudo mv {ArConsts.DUT_HOME_DIR}{ArConsts.CONFIG_DB_FILE_NAME} {ArConsts.CONFIG_DB_FILE_PATH}')
    cli_objects.dut.general.reload_flow(topology_obj=topology_obj, reload_force=True)


@pytest.fixture(scope='function')
def get_reboot_type(platform_params, is_simx):
    """
    This fixture is to randomly get reboot type to be performed at DUT
    :param platform_params: platform_params fixture
    :param is_simx: is_simx fixture
    :return: reboot type
    """
    supported_reboot_reload_list = get_supported_reboot_reload_types_list(platform_params.platform)

    # TODO- remove WA after bug is solved
    if "warm-reboot" in supported_reboot_reload_list and is_redmine_issue_active([3821130]):
        supported_reboot_reload_list.remove("warm-reboot")

    reboot_type = random.choice(supported_reboot_reload_list)
    if is_simx:
        reboot_type = random.choice(ArConsts.SIMX_REBOOT_TYPES)
    return reboot_type


@pytest.fixture(scope='function')
def configure_global_util(cli_objects):
    # Configure AR port with low link utilization rate
    with allure.step(f'Configure link utilization grade to {ArConsts.PORT_UTIL_CUSTOM_PERCENT}%'):
        ar_helper.enable_global_link_utilization(cli_objects, threshold=ArConsts.PORT_UTIL_CUSTOM_PERCENT, restart_swss=True)
        cli_objects.dut.general.verify_dockers_are_up()
    # Wait for bgp neighbor come up
    ar_helper.verify_bgp_neighbor(cli_objects)
    ar_helper.add_routes_to_host(cli_objects)

    yield

    # Return link utilization to previous state
    ar_helper.disable_link_utilization(cli_objects, restart_swss=True)
    ar_helper.del_routes_from_host(cli_objects)


@pytest.fixture(scope='function')
def config_ar_profile(cli_objects, engines, topology_obj):
    # Copy AR custom profile to dut
    logger.info('Copy and load AR custom profile')
    ar_profile_config_folder_path = os.path.dirname(os.path.abspath(__file__)) + '/' + ArConsts.AR_CONFIG_FOLDER
    ar_helper.copy_and_load_profile_config(engines, cli_objects, ar_profile_config_folder_path,
                                           ArConsts.AR_CUSTOM_PROFILE_JSON)
    # Enable AR custom profile
    with allure.step(f'Enable {ArConsts.CUSTOM_PROFILE_NAME} profile'):
        ar_helper.enable_ar_profile(cli_objects, ArConsts.CUSTOM_PROFILE_NAME)
        ar_helper.config_save_reload(cli_objects, topology_obj, reload_force=True)
        ar_helper.verify_bgp_neighbor(cli_objects)

    yield

    with allure.step(f'Return to default profile {ArConsts.GOLDEN_PROFILE0} at the end of the test'):
        ar_helper.enable_ar_profile(cli_objects, ArConsts.GOLDEN_PROFILE0)
        ar_helper.config_save_reload(cli_objects, topology_obj, reload_force=True)
        ar_helper.verify_bgp_neighbor(cli_objects)
