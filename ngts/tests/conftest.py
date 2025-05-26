"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only canonical setups.

"""
import re
import json
import pytest
import os
import yaml
import logging
import allure

from dotted_dict import DottedDict
from deepdiff import DeepDiff
from enum import Enum

from ngts.cli_wrappers.nvue.nvue_cli import NvueCli
from ngts.cli_wrappers.sonic.sonic_general_clis import SonicGeneralCliDefault
from ngts.constants.constants import PytestConst
from ngts.helpers import json_file_helper
from ngts.helpers.config_db_utils import save_config_db_json
from ngts.tests.nightly.conftest import convert_speed_format_to_m_speed
from ngts.tools.ports_modifier import reload_config, MAX_PORTS_TEST_LIST
from ngts.scripts.sonic_deploy.os_upgrade_flag import is_os_upgraded

logger = logging.getLogger()
RAM_SYNCD_USAGE_ASAN_COEFFICIENT = 4
CPU_SDK_USAGE_SIMX_COEFFICIENT = 6


class NtpDaemon(Enum):
    NTP = 1
    NTPSEC = 2
    CHRONY = 3


@pytest.fixture(scope='session', autouse=True)
def get_dut_device_info(cli_objects):
    """
    Print show version output and running configuration to logs
    :param cli_objects: cli_objects fixture
    """
    cli_objects.dut.general.show_version()
    config_before_tests = cli_objects.dut.general.get_config_db_from_running_config()

    yield

    config_after_tests = cli_objects.dut.general.get_config_db_from_running_config()
    configs_diff = DeepDiff(config_before_tests, config_after_tests)

    new_items_added = configs_diff.get('dictionary_item_added')
    values_changed = configs_diff.get('values_changed')
    values_removed = configs_diff.get('dictionary_item_removed')

    logger.info(f'SONiC configuration diff before/after pytest session execution:\n'
                f'New items added: {new_items_added}\n'
                f'Values changed: {values_changed}\n'
                f'Values removed: {values_removed}\n')


@pytest.fixture(scope='session')
def interfaces(topology_obj):
    interfaces_data = DottedDict()
    interfaces_data.ha_dut_1 = topology_obj.ports.get('ha-dut-1')
    interfaces_data.ha_dut_2 = topology_obj.ports.get('ha-dut-2')
    interfaces_data.hb_dut_1 = topology_obj.ports.get('hb-dut-1')
    interfaces_data.hb_dut_2 = topology_obj.ports.get('hb-dut-2')
    interfaces_data.dut_ha_1 = topology_obj.ports.get('dut-ha-1')
    interfaces_data.dut_ha_2 = topology_obj.ports.get('dut-ha-2')
    interfaces_data.dut_hb_1 = topology_obj.ports.get('dut-hb-1')
    interfaces_data.dut_hb_2 = topology_obj.ports.get('dut-hb-2')
    return interfaces_data


@pytest.fixture(scope='session')
def ha_dut_1_mac(cli_objects, interfaces):
    """
    Pytest fixture which are returning mac address for link: ha-dut-1
    """
    return cli_objects.ha.mac.get_mac_address_for_interface(interfaces.ha_dut_1)


@pytest.fixture(scope='session')
def ha_dut_2_mac(cli_objects, interfaces):
    """
    Pytest fixture which are returning mac address for link: ha-dut-2
    """
    return cli_objects.ha.mac.get_mac_address_for_interface(interfaces.ha_dut_2)


@pytest.fixture(scope='session')
def hb_dut_1_mac(cli_objects, interfaces):
    """
    Pytest fixture which are returning mac address for link: hb-dut-1
    """
    return cli_objects.hb.mac.get_mac_address_for_interface(interfaces.hb_dut_1)


@pytest.fixture(scope='session')
def hb_dut_2_mac(cli_objects, interfaces):
    """
    Pytest fixture which are returning mac address for link: hb-dut-2
    """
    return cli_objects.hb.mac.get_mac_address_for_interface(interfaces.hb_dut_2)


@pytest.fixture(scope='session')
def dut_ha_1_mac(cli_objects, topology_obj):
    """
    Pytest fixture which are returning mac address for link: dut-ha-1
    """
    return cli_objects.dut.mac.get_mac_address_for_interface(topology_obj.ports['dut-ha-1'])


@pytest.fixture(scope='session')
def dut_hb_1_mac(cli_objects, topology_obj):
    """
    Pytest fixture which are returning mac address for link: dut-hb-1
    """
    return cli_objects.dut.mac.get_mac_address_for_interface(topology_obj.ports['dut-hb-1'])


@pytest.fixture(scope='session')
def dut_hb_2_mac(engines, cli_objects, topology_obj):
    """
    Pytest fixture which are returning mac address for link: dut-hb-2
    """
    return cli_objects.dut.mac.get_mac_address_for_interface(topology_obj.ports['dut-hb-2'])


@pytest.fixture(scope='session')
def run_config_only(request):
    """
    Method for get run_config_only from pytest arguments
    """
    return request.config.getoption(PytestConst.run_config_only_arg)


@pytest.fixture(scope='session')
def run_test_only(request):
    """
    Method for get run_test_only from pytest arguments
    """
    return request.config.getoption(PytestConst.run_test_only_arg)


@pytest.fixture(scope='session')
def run_cleanup_only(request):
    """
    Method for get run_cleanup_only from pytest arguments
    """
    return request.config.getoption(PytestConst.run_cleanup_only_arg)


def get_ntp_daemon_in_use(host):
    ntpsec_conf_stat = host.stat("/etc/ntpsec/ntp.conf")
    if ntpsec_conf_stat["exists"]:
        return NtpDaemon.NTPSEC
    chrony_conf_stat = host.stat("/etc/chrony/chrony.conf")
    if chrony_conf_stat["exists"]:
        return NtpDaemon.CHRONY
    ntp_conf_stat = host.stat("/etc/ntp.conf")
    if ntp_conf_stat["exists"]:
        return NtpDaemon.NTP
    pytest.fail("Unable to determine NTP daemon in use")


@pytest.fixture(scope="session")
def ntp_daemon_in_use(cli_objects):
    return get_ntp_daemon_in_use(cli_objects.dut.general)


@pytest.fixture(scope='session')
def expected_cpu_usage_dict(platform, sonic_branch, is_simx, chip_type, ntp_daemon_in_use):
    """
    Pytest fixture which used to return the expected cpu usage dictionary
    :param platform: platform fixture
    :param sonic_branch: sonic branch fixture
    :param is_simx: True if dut is a simx switch, else False
    :param chip_type: dut chip type
    :return: expected cpu usage dictionary
    """
    expected_cpu_usage_file = "expected_cpu_usage.yaml"
    return get_expected_cpu_or_ram_usage_dict(expected_cpu_usage_file, sonic_branch, platform, ntp_daemon_in_use,
                                              is_simx=is_simx, chip_type=chip_type)


@pytest.fixture(scope='session')
def expected_ram_usage_dict(platform, sonic_branch, is_sanitizer_image, ntp_daemon_in_use):
    """
    Pytest fixture which used to return the expected ram usage dictionary
    :param platform: platform fixture
    :param sonic_branch: sonic branch fixture
    :param is_sanitizer_image: True if dut has a sanitizer image, else False
    :return: expected ram usage dictionary
    """
    expected_ram_usage_file = "expected_ram_usage.yaml"
    return get_expected_cpu_or_ram_usage_dict(expected_ram_usage_file, sonic_branch,
                                              platform, ntp_daemon_in_use, is_sanitizer_image=is_sanitizer_image)


@pytest.fixture(scope='session')
def platform(platform_params):
    """
    get the platform value from the hwsku
    :param platform_params: platform_params fixture. Example of platform_params.hwsku: Mellanox-SN3800-D112C8
    """
    platform_index = 1
    return platform_params.hwsku.split('-')[platform_index]


def get_expected_cpu_or_ram_usage_dict(expected_cpu_or_ram_usage_file, sonic_branch, platform, ntp_daemon_in_use,
                                       is_sanitizer_image=False, is_simx=False, chip_type=None):
    """
    Get the expected cpu or ram usage dictionary
    :param expected_cpu_or_ram_usage_file: yaml file name
    :param sonic_branch: sonic branch
    :param platform: platform
    :param is_sanitizer_image: True if dut has a asan image, False otherwise
    :param is_simx: True if dut is a simx switch, else False
    :param chip_type: dut chip type
    :return: expected cpu or ram usage dictionary
    """
    file_folder = "push_build_tests/system/"
    current_folder = os.path.dirname(__file__)
    expected_cpu_or_ram_usage_file_path = os.path.join(current_folder, file_folder, expected_cpu_or_ram_usage_file)
    with open(expected_cpu_or_ram_usage_file_path) as raw_data:
        expected_cpu_or_ram_usage_dict = yaml.load(raw_data, Loader=yaml.FullLoader)
    default_branch = "master"
    branch = sonic_branch if sonic_branch in expected_cpu_or_ram_usage_dict.keys() else default_branch
    expected_cpu_or_ram_usage_dict = expected_cpu_or_ram_usage_dict[branch][platform]
    update_ram_usage_for_sanitizer_image(expected_cpu_or_ram_usage_file, is_sanitizer_image,
                                         expected_cpu_or_ram_usage_dict)
    update_cpu_usage_for_simx(expected_cpu_or_ram_usage_file, is_simx,
                              chip_type, expected_cpu_or_ram_usage_dict)
    if ntp_daemon_in_use == NtpDaemon.CHRONY:
        expected_cpu_or_ram_usage_dict['chronyd'] = expected_cpu_or_ram_usage_dict['ntpd']
        del expected_cpu_or_ram_usage_dict['ntpd']
    return expected_cpu_or_ram_usage_dict


def update_ram_usage_for_sanitizer_image(expected_cpu_or_ram_usage_file,
                                         is_sanitizer_image, expected_cpu_or_ram_usage_dict):
    """
    RAM usage for syncd on asan image is expected to be higher, that's why
    the fix is to update the threshold for syncd if it's a sanitizer image.
    :param expected_cpu_or_ram_usage_file: i.e, "expected_ram_usage.yaml" or "expected_cpu_usage.yaml"
    :param is_sanitizer_image: True if dut has a sanitizer image, else False
    :param expected_cpu_or_ram_usage_dict: a dictionary with expected ram usage/ cpu usage
    :return: none
    """
    if is_sanitizer_image and expected_cpu_or_ram_usage_file == "expected_ram_usage.yaml":
        expected_cpu_or_ram_usage_dict['syncd'] *= RAM_SYNCD_USAGE_ASAN_COEFFICIENT


def update_cpu_usage_for_simx(expected_cpu_or_ram_usage_file, is_simx, chip_type, expected_cpu_or_ram_usage_dict):
    """
    CPU usage for sx_sdk on SIMX spc3 setups is expected to be higher, that's why
    the fix is to update the threshold for sx_sdk if it's a simx and SPC3.
    :param expected_cpu_or_ram_usage_file: i.e, "expected_ram_usage.yaml" or "expected_cpu_usage.yaml"
    :param is_simx: True if dut is a simx switch, else False
    :param chip_type: dut chip type
    :param expected_cpu_or_ram_usage_dict: a dictionary with expected ram usage/ cpu usage
    :return: none
    """
    if is_simx and expected_cpu_or_ram_usage_file == "expected_cpu_usage.yaml" and chip_type == 'SPC3':
        expected_cpu_or_ram_usage_dict['sx_sdk'] *= CPU_SDK_USAGE_SIMX_COEFFICIENT


def get_dut_loopbacks(topology_obj, split=False):
    """
    :param split: look also for split ports.
    :return: a list of ports tuple which are connected as loopbacks on dut
    i.e,
    [('Ethernet4', 'Ethernet8'), ('Ethernet40', 'Ethernet36'), ...]
    """
    dut_loopbacks = {}
    pattern = r"dut-lb\d+-\d"
    if split:
        pattern = r"dut-lb.*"
    for alias, connected_alias in topology_obj.ports_interconnects.items():
        if dut_loopbacks.get(connected_alias):
            continue
        if re.search(pattern, alias):
            dut_loopbacks[alias] = connected_alias
    dut_loopback_aliases_list = dut_loopbacks.items()
    return list(map(lambda lb_tuple: (topology_obj.ports[lb_tuple[0]], topology_obj.ports[lb_tuple[1]]),
                    dut_loopback_aliases_list))


def get_dut_host_loopbacks(interfaces):
    """
    :param interfaces: interfaces fixture object
    :return: a list of loopbacks between dut ports and their matching host ports
    """
    return [(interfaces.dut_ha_1, interfaces.ha_dut_1), (interfaces.dut_ha_2, interfaces.ha_dut_2),
            (interfaces.dut_hb_1, interfaces.hb_dut_1), (interfaces.dut_hb_2, interfaces.hb_dut_2)]


@pytest.fixture(scope='session')
@pytest.mark.usefixtures("hosts_ports")
def split_mode_supported_speeds(topology_obj, engines, cli_objects, interfaces, hosts_ports, platform):
    """
    :param topology_obj: topology object fixture
    :param engines: setup engines fixture
    :param cli_objects: cli objects fixture
    :param interfaces: host <-> dut interfaces fixture
    :param hosts_ports: a dictionary with hosts engine, cli_object and ports
    :param platform: platform fixture
    :return: a dictionary with available breakout options on all setup ports (included host ports)
    format : {<port_name> : {<split type>: {[<supported speeds]}

    i.e,  {'Ethernet0': {1: {'100G', '50G', '40G', '10G', '25G'},
                        2: {'40G', '10G', '25G', '50G'},
                        4: {'10G', '25G'}},
          ...
          'enp131s0f1': {1: {'100G', '40G', '50G', '10G', '1G', '25G'}}}
    """
    platform_json_info = json_file_helper.get_platform_json(engines.dut, cli_objects.dut, fail_if_does_not_exist=False)
    split_mode_supported_speeds = cli_objects.dut.general.parse_platform_json(topology_obj, platform_json_info)

    # TODO: code below to convert 100(which we get from platform.json on DUT) to 100M, which is used by the test
    convert_speed_format_to_m_speed(split_mode_supported_speeds)

    for host_engine, host_info in hosts_ports.items():
        host_cli, host_ports = host_info
        for port in host_ports:
            port_ethtool_status = host_cli.interface.parse_show_interface_ethtool_status(port)
            port_supported_speeds = port_ethtool_status["supported speeds"]
            if '1G' in port_supported_speeds:
                port_supported_speeds.remove('1G')
                # TODO: bug 2966698 fix only on latest kernel - kernel update is unplanned for now
                # TODO: please remove this if statement once issue is resolved
            split_mode_supported_speeds[port] = \
                {1: port_supported_speeds}
    return split_mode_supported_speeds


@pytest.fixture(scope='session')
def hosts_ports(engines, cli_objects, interfaces):
    hosts_ports = {engines.ha: (cli_objects.ha, [interfaces.ha_dut_1, interfaces.ha_dut_2]),
                   engines.hb: (cli_objects.hb, [interfaces.hb_dut_1, interfaces.hb_dut_2])}
    return hosts_ports


def toggle_rsyslog_configurations(dut_engine, configurations, target, state):
    """
    This method enables/disables rsyslog configurations in the host or a container.
    The approach is to comment/uncomment config lines in /etc/rsyslog.conf.
    It does nothing if the config is not there originally.
       :param dut_engine: the dut ssh engine
       :param configurations: the configurations that to be enabled/disabled
       :param target: host or container in which the rsyslog config will be changed
       :param state: enable or disable
    """
    if target != "host":
        cmd_prefix = f"docker exec -i {target}"
        cmd_restart_rsyslogd = f"{cmd_prefix} supervisorctl restart rsyslogd"
    else:
        cmd_prefix = "sudo"
        cmd_restart_rsyslogd = "sudo systemctl restart rsyslog"

    for config in configurations:
        if state == "disable":
            origin_config = "\\" + config
            target_config = "\\#\\" + config
        elif state == "enable":
            origin_config = "\\#\\" + config
            target_config = "\\" + config
        cmd_toggle_config = f'{cmd_prefix} sed -e "s/{origin_config}/{target_config}/g"  -i /etc/rsyslog.conf'
        dut_engine.run_cmd(cmd_toggle_config)

    cmd_show_config = f'{cmd_prefix} cat /etc/rsyslog.conf'
    dut_engine.run_cmd(cmd_show_config)
    dut_engine.run_cmd(cmd_restart_rsyslogd)


@pytest.fixture(scope="module", autouse=True)
def config_check(engines, cli_objects, topology_obj, request, sonic_version, platform_params, chip_type):
    """
    Check if the running config (from redis db) is modified after the test case running.
    If so, we will reload the running config after test case running.
    """
    if request.node.get_closest_marker('skip_config_check'):
        logger.info("****************************Skipping config_check for module: %s****************************", request.node.name)
        yield None
        return

    is_skynet = request.config.getoption("skynet")
    if is_skynet:
        logger.info("config check is disabled on Skynet systems to prevent system reload")
        yield None
    else:
        dut_engine = engines.dut
        dut_hostname = cli_objects.dut.chassis.get_hostname()

        module_name = request.node.name
        dut_data = {}
        with allure.step(f"Collecting running config before test on {dut_hostname}"):
            logger.info(f"Collecting running config before test on {dut_hostname}, config info save in fixture config_check attachment")
            if request.session.items[0].name in MAX_PORTS_TEST_LIST:
                before_config_output = dut_engine.run_cmd("sudo cat /tmp/pre_running_config.json", print_output=False)
                dut_engine.run_cmd("sudo rm -f /tmp/pre_running_config.json")
            else:
                before_config_output = dut_engine.run_cmd("sonic-cfggen -d --print-data", print_output=False)
            allure.attach(before_config_output, f"before_test_running_config_{module_name}", allure.attachment_type.TEXT)
            dut_data["pre_running_config"] = json.loads(before_config_output)

        yield dut_data

        if request.session.items[0].name in MAX_PORTS_TEST_LIST:
            reload_config(request.session, platform_params, chip_type)

        with allure.step(f"Collecting running config after test on {dut_hostname}"):
            logger.info(f"Collecting running config after test on {dut_hostname}, config info save in fixture config_check attachment")
            after_config_output = dut_engine.run_cmd("sonic-cfggen -d --print-data", print_output=False)
            allure.attach(after_config_output, f"after_test_running_config_{module_name}", allure.attachment_type.TEXT)
            dut_data["cur_running_config"] = json.loads(after_config_output)

        pre_only_config = {}
        cur_only_config = {}
        inconsistent_config = {}

        # Ignore the following keys in the comparison as they are expected and are not considered as stale configurations.
        # after upgrading from 202411 to current master RC, the new OS will add
        # extra default configurations for KDUMP, we don't care about KDUMP configurations
        # for existed cases so far. If KDUMP configurations need to be considered,
        # please remove the key from the exclude_config_table_names list.
        exclude_config_table_names = {"LOGGER", "KDUMP"}
        ignore_keys = {
            "DEVICE_METADATA.localhost.timezone",
        }

        pre_running_config = dut_data["pre_running_config"]
        cur_running_config = dut_data["cur_running_config"]
        pre_running_config_keys = set(pre_running_config.keys())
        cur_running_config_keys = set(cur_running_config.keys())

        # Check if there are extra keys in pre running config
        pre_config_extra_keys = list(pre_running_config_keys - cur_running_config_keys - exclude_config_table_names)
        for key in pre_config_extra_keys:
            pre_only_config.update({key: pre_running_config[key]})

        # Check if there are extra keys in cur running config
        cur_config_extra_keys = list(cur_running_config_keys - pre_running_config_keys - exclude_config_table_names)
        for key in cur_config_extra_keys:
            cur_only_config.update({key: cur_running_config[key]})

        # Get common keys in pre running config and cur running config
        common_config_keys = list(pre_running_config_keys & cur_running_config_keys - exclude_config_table_names)

        # Check if the running config is modified after module running
        for key in common_config_keys:
            # TODO: remove these code when solve the problem of "FLEX_COUNTER_DELAY_STATUS"
            if key == "FLEX_COUNTER_TABLE":
                for sub_key, sub_value in list(pre_running_config[key].items()):
                    try:
                        pre_value = pre_running_config[key][sub_key]
                        cur_value = cur_running_config[key][sub_key]
                        if pre_value["FLEX_COUNTER_STATUS"] != cur_value["FLEX_COUNTER_STATUS"]:
                            inconsistent_config.update(
                                {
                                    key: {
                                        "pre_value": pre_running_config[key],
                                        "cur_value": cur_running_config[key]
                                    }
                                }
                            )
                    except KeyError:
                        inconsistent_config.update(
                            {
                                key: {
                                    "pre_value": pre_running_config[key],
                                    "cur_value": cur_running_config[key]
                                }
                            }
                        )
            elif not compare_running_config(pre_running_config[key], cur_running_config[key],
                                            current_key=[key], ignore_keys=ignore_keys):
                inconsistent_config.update(
                    {
                        key: {
                            "pre_value": pre_running_config[key],
                            "cur_value": cur_running_config[key]
                        }
                    }
                )

        if pre_only_config or cur_only_config or inconsistent_config:
            check_result = {
                "config_db_check": {
                    "pass": False,
                    "pre_only_config": pre_only_config,
                    "cur_only_config": cur_only_config,
                    "inconsistent_config": inconsistent_config
                }
            }

            config_check_error_message = (f"Config check failed for {module_name}, "
                                          f"diff summary: {DeepDiff(pre_running_config, cur_running_config)}\n "
                                          f"full results: {check_result}")
            logger.warning(config_check_error_message)
            logger.info(f"DUT contains stale configurations after running {module_name}, reloading DUT to configurations "
                        f"before the test")
            save_config_db_json(dut_engine, dut_data["pre_running_config"])
            if isinstance(cli_objects.dut, NvueCli):
                logger.info("reload flow is currently not supported for NVUE")
            else:
                cli_objects.dut.general.reload_flow(topology_obj=topology_obj, reload_force=True)
            if isinstance(cli_objects.dut.general, SonicGeneralCliDefault) and \
                    cli_objects.dut.general.get_image_sonic_release() == "none" and \
                    is_os_upgraded():
                # Current OS release is master RC and was upgraded in "Upgrade switch" step
                logger.warning(
                    "config check is disabled when upgrading to master RC, check the failure->\n"
                    f"{config_check_error_message}"
                )
                return
            raise Exception(config_check_error_message)
        else:
            logger.info("Config check passed for {}".format(module_name))


def key_path_pattern_match(pattern: str, key_path: str) -> bool:
    pattern_parts = pattern.split('.')
    key_parts = key_path.split('.')
    if len(pattern_parts) != len(key_parts):
        return False
    for p, k in zip(pattern_parts, key_parts):
        if p != '*' and p != k:
            return False
    return True


def compare_running_config(pre_running_config, cur_running_config,
                           current_key=[], ignore_keys=set()) -> bool:
    """
    Recursively compare two running configs, ignoring keys specified in ignore_keys.
    Each element in ignore_keys is a dot-separated path, e.g., "a.b.c", "a.*.c", "a.*.*.d", etc...
    * can be used as a wildcard to match any key.
    """
    key_path_str = '.'.join(current_key)
    for pattern in ignore_keys:
        if key_path_pattern_match(pattern, key_path_str):
            return True
    if not isinstance(pre_running_config, type(cur_running_config)):
        return False
    if pre_running_config == cur_running_config:
        return True
    else:
        if isinstance(pre_running_config, dict):
            pre_keys = set(pre_running_config.keys())
            cur_keys = set(cur_running_config.keys())
            if pre_keys != cur_keys:
                for key in pre_keys ^ cur_keys:
                    if not any(key_path_pattern_match(pattern, ".".join(current_key + [key])) for pattern in ignore_keys):
                        return False

            for key in pre_running_config.keys():
                # Recursively compare, appending the current key to the path
                if not compare_running_config(
                    pre_running_config[key],
                    cur_running_config[key],
                    current_key=current_key + [str(key)],
                    ignore_keys=ignore_keys
                ):
                    return False
            return True
        # We only have string in list in running config now, so we can ignore the order of the list.
        elif isinstance(pre_running_config, list):
            if set(pre_running_config) != set(cur_running_config):
                return False
            else:
                return True
        else:
            return False
