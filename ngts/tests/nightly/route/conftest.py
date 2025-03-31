import ipaddress
import os

import pytest
from infra.tools.yaml_tools.yaml_loops import ip_range

from ngts.cli_wrappers.sonic.sonic_route_clis import SonicRouteCli
from ngts.config_templates.ip_config_template import IpConfigTemplate

ROUTE_APP_CONFIG_SET = 'async_route_conf_set.json'
ROUTE_APP_CONFIG_SET_LOCAL_PATH = os.path.join('/tmp', ROUTE_APP_CONFIG_SET)
ROUTE_APP_CONFIG_SET_DUT_PATH = os.path.join('/etc/sonic', ROUTE_APP_CONFIG_SET)
ROUTE_APP_CONFIG_DEL = 'async_route_conf_del.json'
ROUTE_APP_CONFIG_DEL_LOCAL_PATH = os.path.join('/tmp', ROUTE_APP_CONFIG_DEL)
ROUTE_APP_CONFIG_DEL_DUT_PATH = os.path.join('/etc/sonic', ROUTE_APP_CONFIG_DEL)
SX_API_ROUTES_FILE_NAME = 'sx_api_routes.py'
SWSS_BULK_CONFIG_FILE_NAME = 'swss_bulk_config.py'
IPV4 = 'ipv4'
IPV6 = 'ipv6'

ROUTES_MAX_SCALE = {
    'SPC': {IPV4: 50000, IPV6: 10800},
    'SPC2': {IPV4: 100000, IPV6: 16000},
    'SPC3': {IPV4: 100000, IPV6: 16000},
    'SPC4': {IPV4: 100000, IPV6: 16000},
    'SPC5': {IPV4: 100000, IPV6: 16000}
}


def pytest_addoption(parser):
    """
    Adds options to pytest that are used by the route tests.

    :param parser: parser of pytest parameters
    """
    parser.addoption(
        "--max_scale",
        action="store_true",
        help="Use max scale routes, otherwise 10K routes will be used",
    )


def prepare_data_for_route_app_config_generation(ip_list, interface, ip_version):
    """
    Generates ip/mask/n_hop/ifaces lists for routes configuration

    :param ip_list: list with subnet addresses
    :param interface: interface which will be used in route app config as destination
    :param ip_version: IP version of ip_list entries, could be equal IPV4 or IPV6
    :return: few lists: ip_list - list with IPs, list with masks for each IP route, next_hop_list - list with next-hops
    for each IP route, ifaces_list - list with ifaces for each IP route
    """
    mask_list = (['32'] if ip_version == IPV4 else ['128']) * len(ip_list)
    n_hop_list = (['160.0.0.2'] if ip_version == IPV4 else ['1600::2']) * len(ip_list)
    ifaces_list = [interface] * len(ip_list)

    return ip_list, mask_list, n_hop_list, ifaces_list


def generate_test_config(interfaces, ip_list, ip_version):
    """
    Generate route scale test configuration

    :param interfaces: fixture interfaces
    :param ip_list: list with subnet routes
    :param ip_version: IP version of ip_list entries, could be equal IPV4 or IPV6
    """
    # Prepare lists with IPs(routes), route masks, route next hops, route interfaces and generate app configs
    ip_list, mask_list, n_hop_list, ifaces_list = prepare_data_for_route_app_config_generation(
        ip_list, interfaces.dut_hb_1, ip_version)

    SonicRouteCli.generate_route_app_data(ip_list, mask_list, n_hop_list, ifaces_list, ROUTE_APP_CONFIG_SET_LOCAL_PATH,
                                          op='SET')
    SonicRouteCli.generate_route_app_data(ip_list, mask_list, n_hop_list, ifaces_list, ROUTE_APP_CONFIG_DEL_LOCAL_PATH,
                                          op='DEL')


def get_last_ipv4_in_range(first_ip, ip_range=1000):
    """
    Calculates last IPv4 in range starting from first_ip

    :param str first_ip: IP range starts with
    :param int ip_range: number of IPs in range
    :return str: IP range ends with
    """
    first_ip_int = int(ipaddress.IPv4Address(first_ip))
    last_ip = str(ipaddress.IPv4Address(first_ip_int + ip_range - 1))
    return last_ip


def get_last_ipv6_in_range(first_ip, ip_range=1000):
    """
    Calculates last IPv6 in range starting from first_ip

    :param str first_ip: IP range starts with
    :param int ip_range: number of IPs in range
    :return str: IP range ends with
    """
    first_ip_int = int(ipaddress.IPv6Address(first_ip))
    last_ip = str(ipaddress.IPv6Address(first_ip_int + ip_range - 1))
    return last_ip


def copy_route_app_configs_to_dut(engine):
    """
    Copy route application config to from host DUT

    :param engine: dut engine
    """
    engine.copy_file(source_file=ROUTE_APP_CONFIG_SET_LOCAL_PATH, dest_file=ROUTE_APP_CONFIG_SET,
                     file_system='/tmp', overwrite_file=True, verify_file=False)
    engine.run_cmd(f'sudo mv {ROUTE_APP_CONFIG_SET_LOCAL_PATH} {ROUTE_APP_CONFIG_SET_DUT_PATH}')
    engine.copy_file(source_file=ROUTE_APP_CONFIG_DEL_LOCAL_PATH, dest_file=ROUTE_APP_CONFIG_DEL,
                     file_system='/tmp', overwrite_file=True, verify_file=False)
    engine.run_cmd(f'sudo mv {ROUTE_APP_CONFIG_DEL_LOCAL_PATH} {ROUTE_APP_CONFIG_DEL_DUT_PATH}')


@pytest.fixture(scope='module')
def number_of_routes(request, chip_type):
    """
    Returns number of routes to test based on parsed pytest flag

    :param request: request object
    :param chip_type: fixture to detect chip type
    :return int, int: number for routes to test for IPv4, number of routes to test for IPv6
    """
    max_scale = request.config.getoption('--max_scale')
    ipv4_max_scale = ROUTES_MAX_SCALE.get(chip_type).get(IPV4)
    ipv6_max_scale = ROUTES_MAX_SCALE.get(chip_type).get(IPV6)
    if max_scale:
        return ipv4_max_scale, ipv6_max_scale
    else:
        return 20000, ipv6_max_scale


@pytest.fixture
def static_routes_ipv4(interfaces, engines, topology_obj, number_of_routes):
    """
    Generates config for IPv4 routes testing

    :param interfaces: fixture containing all the interfaces of setup
    :param engines: engines fixture
    :param topology_obj: fixture containing topology object
    :param number_of_routes: fixture to retrieve number of routes to run tests with
    :yield list[str]: list of IPv4 addresses to test with
    """
    first_ip = '100.0.0.1'
    ipv4_routes_num, _ = number_of_routes
    last_ip = get_last_ipv4_in_range(first_ip, ipv4_routes_num)

    ip_list = ip_range(first_ip, last_ip, ip_type='ipv4', step=1)

    generate_test_config(interfaces, ip_list, IPV4)

    copy_route_app_configs_to_dut(engines.dut)

    # IP config which will be used in test
    ip_config_dict = {
        'dut': [
            {'iface': interfaces.dut_ha_1, 'ips': [('150.0.0.1', '24')]},
            {'iface': interfaces.dut_hb_1, 'ips': [('160.0.0.1', '24')]},
            {'iface': interfaces.dut_ha_2, 'ips': [('170.0.0.1', '24')]},
            {'iface': interfaces.dut_hb_2, 'ips': [('180.0.0.1', '24')]}
        ],
        'ha': [
            {'iface': interfaces.ha_dut_1, 'ips': [('150.0.0.2', '24')]},
            {'iface': interfaces.ha_dut_2, 'ips': [('170.0.0.2', '24')]}
        ],
        'hb': [
            {'iface': interfaces.hb_dut_1, 'ips': [('160.0.0.2', '24')]},
            {'iface': interfaces.hb_dut_2, 'ips': [('180.0.0.2', '24')]},
        ]
    }
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)

    yield ip_list

    engines.dut.run_cmd(f'sudo rm -f {ROUTE_APP_CONFIG_SET_DUT_PATH}')
    engines.dut.run_cmd(f'sudo rm -f {ROUTE_APP_CONFIG_DEL_DUT_PATH}')
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)


@pytest.fixture
def static_routes_ipv6(interfaces, engines, topology_obj, number_of_routes):
    """
    Generates config for IPv6 routes testing

    :param interfaces: fixture containing all the interfaces of setup
    :param engines: engines fixture
    :param topology_obj: fixture containing topology object
    :param number_of_routes: fixture to retrieve number of routes to run tests with
    :yield list[str]: list of IPv6 addresses to test with
    """
    first_ip = '2000::1'
    _, ipv6_routes_num = number_of_routes
    last_ip = get_last_ipv6_in_range(first_ip, ipv6_routes_num)

    ip_list = ip_range(first_ip, last_ip, ip_type='ipv6', step=1)

    generate_test_config(interfaces, ip_list, 'v6')

    copy_route_app_configs_to_dut(engines.dut)

    # IP config which will be used in test
    ip_config_dict = {
        'dut': [
            {'iface': interfaces.dut_ha_1, 'ips': [('1500::1', '64')]},
            {'iface': interfaces.dut_hb_1, 'ips': [('1600::1', '64')]},
            {'iface': interfaces.dut_ha_2, 'ips': [('1700::1', '64')]},
            {'iface': interfaces.dut_hb_2, 'ips': [('1800::1', '64')]},
        ],
        'ha': [
            {'iface': interfaces.ha_dut_1, 'ips': [('1500::2', '64')]},
            {'iface': interfaces.ha_dut_2, 'ips': [('1700::2', '64')]}
        ],
        'hb': [
            {'iface': interfaces.hb_dut_1, 'ips': [('1600::2', '64')]},
            {'iface': interfaces.hb_dut_2, 'ips': [('1800::2', '64')]}
        ]
    }
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)

    yield ip_list

    engines.dut.run_cmd(f'sudo rm -f {ROUTE_APP_CONFIG_SET_DUT_PATH}')
    engines.dut.run_cmd(f'sudo rm -f {ROUTE_APP_CONFIG_DEL_DUT_PATH}')
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)


@pytest.fixture(autouse=True, scope='module')
def copy_sx_api_router_routes(engines):
    """
    Copies SX_API_ROUTES_FILE_NAME file from localhost to DUT

    :param engines: engines fixture
    """
    base_dir = os.path.dirname(os.path.realpath(__file__))
    get_port_cap_file = os.path.join(base_dir, SX_API_ROUTES_FILE_NAME)
    engines.dut.copy_file(source_file=get_port_cap_file,
                          file_system='/tmp',
                          dest_file=SX_API_ROUTES_FILE_NAME,
                          overwrite_file=True)
    cmd_copy_file_to_syncd = f"docker cp /tmp/{SX_API_ROUTES_FILE_NAME} syncd:/usr/bin"
    engines.dut.run_cmd(cmd_copy_file_to_syncd)

    yield

    engines.dut.run_cmd(f'docker exec syncd bash -c "rm -f /usr/bin/{SX_API_ROUTES_FILE_NAME}"')


@pytest.fixture(autouse=True, scope='module')
def copy_swss_bulk_config(engines):
    """
    Copies swss_bulk_config.py file from localhost to DUT

    :param engines: engines fixture
    """
    base_dir = os.path.dirname(os.path.realpath(__file__))
    swss_bulk_config_file = os.path.join(base_dir, SWSS_BULK_CONFIG_FILE_NAME)
    engines.dut.copy_file(source_file=swss_bulk_config_file,
                          file_system='/tmp',
                          dest_file=SWSS_BULK_CONFIG_FILE_NAME,
                          overwrite_file=True)

    yield

    engines.dut.run_cmd(f'sudo rm -f /tmp/{SWSS_BULK_CONFIG_FILE_NAME}')
