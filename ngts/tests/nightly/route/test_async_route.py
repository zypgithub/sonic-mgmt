import json
import logging
import os
import random
import re

import allure
import pytest
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from retry.api import retry_call
from scapy.all import IP, UDP, Ether, IPv6, wrpcap

from ngts.tests.nightly.route.conftest import (ROUTE_APP_CONFIG_DEL_DUT_PATH,
                                               ROUTE_APP_CONFIG_SET_DUT_PATH,
                                               SX_API_ROUTES_FILE_NAME)

logger = logging.getLogger()


NUMBER_OF_MEASUREMENTS = 3
ADD = 'Add'
REMOVE = 'Remove'
TIMINGS_DB_FILE = 'timings_db.json'
SHARED_TIMINGS_DB_FILE = '/auto/sw_regression/system/SONIC/MARS/tmp/timings_db.json'
IPV4 = 'ipv4'
IPV6 = 'ipv6'
PCAP_FILE_PATH = '/tmp/1k_packets.pcap'
TCPDUMP_FILTER = 'udp src port 1234 and dst port 5678'
TIMING_THRESHOLD_PERCENTS = 10


def get_routes_count(dut_engine, ip_version):
    """
    Count the number of routes currently added in a hardware

    :param dut_engine: DUT engine object
    :param str ip_version: the version of IP routes to count
    :return int: number of routes
    """
    output = dut_engine.run_cmd(f'docker exec -t syncd bash -c "python3 /usr/bin/{SX_API_ROUTES_FILE_NAME}'
                                f' {ip_version}"')
    routes_count = -1
    if output:
        try:
            routes_count = int(re.search(r'IPv[46] UC Routes (\d+)', output).group(1))
        except Exception as e:
            raise Exception(f'Failed to parse the sx_api script output: {str(e)}')
    else:
        raise Exception('Failed to retrieve routes count')
    return routes_count


def get_routes_operation_duration(dut_engine, ip_version, initial_routes_count, expected_routes_count):
    """
    Run the sx_api script to measure the time to perform routes operation

    :param dut_engine: DUT engine object
    :param str ip_version: the version of IP routes to count
    :param int initial_routes_count: number of routes before the operation performed
    :param int expected_routes_count: expected number of routes after the operation performed
    :return float: time to perform the operation in sec
    """
    output = dut_engine.run_cmd(f'docker exec -t syncd bash -c "python3 /usr/bin/{SX_API_ROUTES_FILE_NAME}'
                                f' {ip_version} --initial_number_of_routes {initial_routes_count}'
                                f' --expected_number_of_routes {expected_routes_count}"')
    execution_time = -1
    if output:
        try:
            execution_time = float(re.search(r'Time to execute: ([\d\.]+)', output).group(1))
        except Exception as e:
            raise Exception(f'Failed to parse the sx_api script output: {str(e)}')
    else:
        raise Exception('Failed to retrieve routes operation duration')
    logger.info(f'Time to perform an operation {execution_time}')
    return execution_time


def get_expected_timing(ip_version, platform, action, routes_count):
    """
    Retrieve expected timing value for particular ip_version, platform, action and routes_count

    :param str ip_version: IP version of routes
    :param str platform: name of the platform
    :param str action: name of the action performed. Could be ADD or REMOVE
    :param int routes_count: number of routes tested
    :return float: expected timing(in sec) to perform an action
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    timings_db_paths = [f'{current_dir}/{TIMINGS_DB_FILE}', SHARED_TIMINGS_DB_FILE]
    for timings_db_path in timings_db_paths:
        if os.path.exists(timings_db_path):
            with open(timings_db_path, 'r') as f:
                timings = json.loads(f.read())
                routes_count_key = str(routes_count)
                expected_timing = timings.get(ip_version, {}).get(platform, {}).get(routes_count_key, {}).get(action)
                if expected_timing:
                    if timings_db_path == SHARED_TIMINGS_DB_FILE:
                        logger.warning(f"Using shared timings DB file: {timings_db_path} for expected timing")
                    return expected_timing
    logger.warning(f'Expected execution time for {ip_version} {platform} {action} {routes_count} routes not found')


def set_expected_execution_time(ip_version, platform, action, routes_count, execution_time):
    """
    Updates shared timings DB with actual value of performing an action

    :param str ip_version: IP version of routes
    :param str platform: platform tested
    :param str action: routes action performed
    :param int routes_count: number of routes
    :param float execution_time: actual routes action execution time
    """
    if os.path.exists(SHARED_TIMINGS_DB_FILE):
        with open(SHARED_TIMINGS_DB_FILE, 'r') as f:
            timings = json.loads(f.read())
    else:
        timings = {}
    routes_count_key = str(routes_count)
    timings.setdefault(ip_version, {}).setdefault(platform, {}).setdefault(
        routes_count_key, {})[action] = execution_time
    with open(SHARED_TIMINGS_DB_FILE, 'w') as f:
        json.dump(timings, f, indent=4)

    logger.info(f'Shared timings file was updated: {SHARED_TIMINGS_DB_FILE}')


def do_traffic_validation(interfaces, routes_validation_list, players, ip_version, cli_objects, expected_packets_count):
    """
    This method will run traffic validation, it created to avoid code duplication above

    :param interfaces: interfaces fixture
    :param list[str] routes_validation_list: list of IPs to validate
    :param players: players fixture
    :param ip_version: IP version of routes to validate
    :param cli_objects: cli_objects fixture
    :param int expected_packets_count: number of packets expected to receive
    """
    dummy_mac = "00:01:02:03:04:05"
    dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(interfaces.dut_ha_1)
    if ip_version == IPV6:
        L3_pkt_info = IPv6(src='1500::2', dst=routes_validation_list)
    else:
        L3_pkt_info = IP(src='1.2.3.4', dst=routes_validation_list)
    packets = Ether(src=dummy_mac, dst=dut_mac) / L3_pkt_info / UDP(sport=1234, dport=5678)
    wrpcap(PCAP_FILE_PATH, packets)
    validation = {
        'sender': 'ha',
        'send_args': {
            'interface': interfaces.ha_dut_1,
            'pcap': PCAP_FILE_PATH,
            'count': 1
        },
        'receivers': [
            {
                'receiver': 'hb',
                'receive_args': {
                    'interface': interfaces.hb_dut_1,
                    'filter': TCPDUMP_FILTER,
                    'count': expected_packets_count,
                    'timeout': 20
                }
            },
        ]
    }
    logger.info('Sending traffic')
    scapy_checker = ScapyChecker(players, validation)
    retry_call(scapy_checker.run_validation, fargs=[], tries=5, delay=10, logger=logger)


@pytest.mark.parametrize(
    'ip_version,static_routes',
    [(IPV4, 'static_routes_ipv4'), (IPV6, 'static_routes_ipv6')]
)
def test_adding_routes(cli_objects, engines, platform_params, interfaces, players, ip_version, static_routes, request):
    static_routes = request.getfixturevalue(static_routes)
    new_routes_count = len(static_routes)
    platform = platform_params.platform
    expected_timing = get_expected_timing(ip_version, platform, ADD, new_routes_count)

    # creates a list of 1k randomly chosen routes to run traffic validation
    routes_validation_list = [static_routes[0], static_routes[-1]] + random.sample(static_routes, 998)
    initial_routes_count = get_routes_count(engines.dut, ip_version)
    timings = []

    for i in range(NUMBER_OF_MEASUREMENTS):
        with allure.step(f'Adding routes time measurement {i}'):
            expected_routes_count = initial_routes_count + new_routes_count
            cli_objects.dut.general.execute_command_in_docker(docker='swss',
                                                              command=f'swssconfig {ROUTE_APP_CONFIG_SET_DUT_PATH} &')
            execution_time = get_routes_operation_duration(engines.dut, ip_version, initial_routes_count,
                                                           expected_routes_count)
            with allure.step('Check added routes on switch by sending traffic'):
                do_traffic_validation(interfaces, routes_validation_list, players, ip_version, cli_objects,
                                      len(routes_validation_list))

            cli_objects.dut.general.execute_command_in_docker(docker='swss',
                                                              command=f'swssconfig {ROUTE_APP_CONFIG_DEL_DUT_PATH} &')
            get_routes_operation_duration(engines.dut, ip_version, expected_routes_count, initial_routes_count)
            with allure.step('Check removed routes on switch by sending traffic'):
                do_traffic_validation(interfaces, routes_validation_list, players, ip_version, cli_objects, 0)

            timings.append(execution_time)

    average_execution_time = round(sum(timings) / NUMBER_OF_MEASUREMENTS, 2)
    set_expected_execution_time(ip_version, platform, ADD, new_routes_count, average_execution_time)

    if expected_timing is None:
        pytest.skip(f'Missing timings DB info for {ip_version}|{platform}|{ADD}|{new_routes_count}. '
                    f'Please update {TIMINGS_DB_FILE} in test directory.')

    logger.info(f'Timing for adding {new_routes_count} routes: expected={expected_timing}, '
                f'actual={average_execution_time}')

    assert average_execution_time < (expected_timing * (100 + TIMING_THRESHOLD_PERCENTS) / 100), \
        (f'Actual time of adding {ip_version} {new_routes_count} routes = {average_execution_time}, '
         f'expected time = {expected_timing}')


@pytest.mark.parametrize(
    'ip_version,static_routes',
    [(IPV4, 'static_routes_ipv4'), (IPV6, 'static_routes_ipv6')]
)
def test_removing_routes(cli_objects, engines, platform_params, interfaces, players, ip_version, static_routes,
                         request):
    static_routes = request.getfixturevalue(static_routes)
    new_routes_count = len(static_routes)
    platform = platform_params.platform
    expected_timing = get_expected_timing(ip_version, platform, REMOVE, new_routes_count)

    routes_validation_list = [static_routes[0], static_routes[-1]] + random.sample(static_routes, 998)
    initial_routes_count = get_routes_count(engines.dut, ip_version)
    timings = []

    for i in range(NUMBER_OF_MEASUREMENTS):
        with allure.step(f'Removing routes time measurement {i}'):
            expected_routes_count = initial_routes_count + new_routes_count
            cli_objects.dut.general.execute_command_in_docker(docker='swss',
                                                              command=f'swssconfig {ROUTE_APP_CONFIG_SET_DUT_PATH} &')
            get_routes_operation_duration(engines.dut, ip_version, initial_routes_count, expected_routes_count)
            with allure.step('Check added routes on switch by sending traffic'):
                do_traffic_validation(interfaces, routes_validation_list, players, ip_version, cli_objects,
                                      len(routes_validation_list))

            cli_objects.dut.general.execute_command_in_docker(docker='swss',
                                                              command=f'swssconfig {ROUTE_APP_CONFIG_DEL_DUT_PATH} &')
            execution_time = get_routes_operation_duration(engines.dut, ip_version, expected_routes_count,
                                                           initial_routes_count)
            with allure.step('Check removed routes on switch by sending traffic'):
                do_traffic_validation(interfaces, routes_validation_list, players, ip_version, cli_objects, 0)
            timings.append(execution_time)

    average_execution_time = round(sum(timings) / NUMBER_OF_MEASUREMENTS, 2)
    set_expected_execution_time(ip_version, platform, REMOVE, new_routes_count, average_execution_time)

    if expected_timing is None:
        pytest.skip(f'Missing timings DB info for {ip_version}|{platform}|{REMOVE}|{new_routes_count}. '
                    f'Please update {TIMINGS_DB_FILE} in test directory.')

    logger.info(f'Timing for removing {new_routes_count} routes: expected={expected_timing}, '
                f'actual={average_execution_time}')

    assert average_execution_time < (expected_timing * (100 + TIMING_THRESHOLD_PERCENTS) / 100), \
        (f'Actual time of removing {ip_version} {new_routes_count} routes = {average_execution_time}, '
         f'expected time = {expected_timing}')
