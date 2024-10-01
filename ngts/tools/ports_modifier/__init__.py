import pytest
import json
import os
import logging

from ngts.tools.topology_tools.topology_by_setup import get_topology_by_setup_name_and_aliases
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli
from ngts.constants.constants import InfraConst, PlatformTypesConstants
from ngts.helpers.config_db_utils import save_config_db_json
from ngts.tools.infra import get_platform_info

logger = logging.getLogger()

UNSUPPORTED_SPLIT_PLATFORMS = [PlatformTypesConstants.PLATFORM_ALLIGATOR]
REBOOT_TEST_NAME = 'test_push_gate_reboot_policer'
CONFIG_DB_DUT_PATH = '/etc/sonic/config_db.json'
CONFIG_DB_DUT_TEMP_PATH = '/tmp/config_db.json'
CONFIG_DB_COPY_NAME = 'config_db_copy.json'


def pytest_addoption(parser):

    parser.addoption('--ports_number', action='store', default=None,
                     help='Argument related to reboot test, based on it we can specify number of ports which '
                          'should be used in reboot tests')


def pytest_collection_modifyitems(session, config, items):
    """
    Max supported ports per platform on canonical setup(4 ports connected to hosts)
    msn2700  - 60
    msn3420  - 93
    msn3700  - 116
    msn3800  - 124
    msn4410  - 116
    msn4600  - 124
    msn4600c - 124
    msn4700  - 116
    sn5400   - 128
    sn5600   - 128
    """
    if len(items) == 1 and items[0].name == REBOOT_TEST_NAME and config.option.ports_number:
        minimum_ports_number = 4
        max_pors_num_per_platform = {PlatformTypesConstants.PLATFORM_PANTHER: 60,
                                     PlatformTypesConstants.PLATFORM_LIONFISH: 93,
                                     PlatformTypesConstants.PLATFORM_ANACONDA: 116,
                                     PlatformTypesConstants.PLATFORM_ANACONDA_C: 116,
                                     PlatformTypesConstants.PLATFORM_TIGRIS: 124,
                                     PlatformTypesConstants.PLATFORM_OCELOT: 116,
                                     PlatformTypesConstants.PLATFORM_LIGER: 124,
                                     PlatformTypesConstants.PLATFORM_TIGON: 124,
                                     PlatformTypesConstants.PLATFORM_LEOPARD: 116,
                                     PlatformTypesConstants.PLATFORM_HIPPO: 128,
                                     PlatformTypesConstants.PLATFORM_MOOSE: 128}

        setup_name = session.config.option.setup_name
        topology = get_topology_by_setup_name_and_aliases(session.config.option.setup_name, slow_cli=False)
        dut_engine = topology.players['dut']['engine']
        cli_object = SonicCli(topology)
        platform = get_platform_info(topology)['platform']
        if cli_object.im.is_im_enabled():
            skip = pytest.mark.skip(reason=f'SW control feature enabled at {platform} and port breakout '
                                    f'is not supported')
            for item in items:
                item.add_marker(skip)
                return
        if platform not in max_pors_num_per_platform.keys():
            skip = pytest.mark.skip(reason=f'{platform} platform does not support split to maximum ports')
            for item in items:
                item.add_marker(skip)
                return

        platform_max_ports_num = max_pors_num_per_platform[platform]
        if config.option.ports_number == "max":
            expected_ports_num = platform_max_ports_num
        else:
            expected_ports_num = int(config.option.ports_number)

        if expected_ports_num < minimum_ports_number:
            skip = pytest.mark.skip(reason=f'Expected number of ports: {expected_ports_num}, '
                                    f'but it must be >= {minimum_ports_number}')
            for item in items:
                item.add_marker(skip)
                return
        if expected_ports_num > platform_max_ports_num:
            skip = pytest.mark.skip(reason=f'Platform: {platform} expected number of ports: {expected_ports_num}, '
                                    f'but it must be <= {platform_max_ports_num}')
            for item in items:
                item.add_marker(skip)
                return
        logger.info(f'Setup will be configured with {expected_ports_num} ports')
        # Get config from shared location
        shared_path = f'{InfraConst.MARS_TOPO_FOLDER_PATH}{setup_name}'
        sonic_ver = cli_object.general.get_image_sonic_version()
        config_db_file_name = f'{sonic_ver}_config_db.json'
        orig_config_db_shared_path = os.path.join(shared_path, config_db_file_name)

        original_config_db = read_config_db_from_shared_location(orig_config_db_shared_path)
        existing_ports_num = len(original_config_db['PORT'])
        # Save available config_db.json from DUT to sonic-mgmt docker /tmp folder
        logger.info(f'Copy original config_db.json from DUT to sonic-mgmt /tmp folder')
        dut_engine.copy_file(source_file=f"{CONFIG_DB_DUT_PATH}",
                             dest_file=f'/tmp/{CONFIG_DB_COPY_NAME}', file_system='/tmp/', direction='get')

        if expected_ports_num != existing_ports_num:
            if platform in UNSUPPORTED_SPLIT_PLATFORMS:
                msg = f'Platform {platform} can\'t split ports to reach total number of ports: {expected_ports_num}'
                skip = pytest.mark.skip(reason=msg)
                for item in items:
                    item.add_marker(skip)
                    return

            dut_to_host_ports_list = [port for alias, port in topology.ports.items() if alias.startswith('dut-h')]
            modified_config = generate_config_db(original_config_db, dut_engine, expected_ports_num, platform,
                                                 dut_to_host_ports_list, topology)
            save_config_db_json(dut_engine, modified_config)
            cli_object.general.reload_configuration(force=True)
            cli_object.ip.apply_dns_servers_into_resolv_conf()


def pytest_sessionfinish(session, exitstatus):

    if len(session.items) == 1 and session.items[0].name == REBOOT_TEST_NAME and session.config.option.ports_number:
        skip_marker = [marker for marker in session.items[0].own_markers if marker.name == "skip"]
        if len(skip_marker):
            return  # No need to do cleanup, test skipped

        topology = get_topology_by_setup_name_and_aliases(session.config.option.setup_name, slow_cli=False)
        dut_engine = topology.players['dut']['engine']
        cli_object = SonicCli(topology)
        logger.info(f'Copy original config_db.json file from sonic-mgmt /tmp folder to  DUT /tmp/ folder')
        dut_engine.copy_file(source_file=f"/tmp/{CONFIG_DB_COPY_NAME}",
                             dest_file=CONFIG_DB_DUT_TEMP_PATH, file_system='/tmp/',
                             overwrite_file=True, verify_file=False)
        logger.info(f'Copy db file from DUT /tmp folder to DUT {CONFIG_DB_DUT_PATH}')
        dut_engine.run_cmd(f'sudo cp {CONFIG_DB_DUT_TEMP_PATH} {CONFIG_DB_DUT_PATH}')
        cli_object.general.reload_configuration(force=True)


def read_config_db_from_shared_location(config_db_path):
    # Get config from shared location
    with open(config_db_path) as conf_obj:
        config_db = json.load(conf_obj)
    return config_db


def get_dut_physical_ports_config(engine, platform):
    platform_ini_name = f'{platform}.ini'
    port_ini_local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'port_configs', platform_ini_name)
    engine.copy_file(source_file=port_ini_local_path, dest_file=platform_ini_name,
                     file_system='/tmp', overwrite_file=True, verify_file=False)

    port_ini_dut_path = f'/tmp/{platform_ini_name}'
    cmd = f'sonic-cfggen -k none -p {port_ini_dut_path} --print-data'
    res = json.loads(engine.run_cmd(cmd))
    physical_dut_ports = res['PORT']

    return physical_dut_ports


def modify_lanes_per_platform(platform, port_lanes, split_x2=False):
    lanes_4_spit_x2_x2_lanes = False
    lanes_8_spit_x2_x4_lanes = False
    lanes_8_spit_x4_x2_lanes = False

    four_lanes_x2_split_platforms = [PlatformTypesConstants.PLATFORM_PANTHER, PlatformTypesConstants.PLATFORM_TIGRIS,
                                     PlatformTypesConstants.PLATFORM_TIGON, PlatformTypesConstants.PLATFORM_LIGER]
    lanes_4_spit_x2_x2_lanes = platform in four_lanes_x2_split_platforms

    eight_lanes_x4_split_platforms = [PlatformTypesConstants.PLATFORM_OCELOT, PlatformTypesConstants.PLATFORM_LEOPARD,
                                      PlatformTypesConstants.PLATFORM_MOOSE, PlatformTypesConstants.PLATFORM_HIPPO]

    if platform in [PlatformTypesConstants.PLATFORM_MOOSE, PlatformTypesConstants.PLATFORM_HIPPO] and split_x2:
        lanes_8_spit_x2_x4_lanes = True
    else:
        lanes_8_spit_x4_x2_lanes = platform in eight_lanes_x4_split_platforms

    if lanes_4_spit_x2_x2_lanes:  # 4 lanes, can be split into x2 with 2 lanes each port
        port_lanes = [','.join(port_lanes[0:2]), ','.join(port_lanes[2:4])]
    if lanes_8_spit_x4_x2_lanes:  # 8 lanes, can be split into x4 with 2 lanes each port
        port_lanes = [','.join(port_lanes[0:2]), ','.join(port_lanes[2:4]),
                      ','.join(port_lanes[4:6]), ','.join(port_lanes[6:8])]
    if lanes_8_spit_x2_x4_lanes:  # 8 lanes, can be split into x2 with 4 lanes each port
        port_lanes = [','.join(port_lanes[0:4]), ','.join(port_lanes[4:8])]

    return port_lanes


def generate_config_db(config_db, engine, expected_num_of_ports, platform, dut_host_ports, topology):
    # Get DUT physical ports
    physical_dut_ports = get_dut_physical_ports_config(engine, platform)

    # Remove breakout related data
    config_db.pop('BREAKOUT_CFG')
    port_speed = '25000'
    if platform == PlatformTypesConstants.PLATFORM_MOOSE:
        # Remove service port from list of ports which will be split
        physical_dut_ports.pop('Ethernet512')
        port_speed = "100000"
    if platform == PlatformTypesConstants.PLATFORM_HIPPO:
        # Remove service port from list of ports which will be split
        physical_dut_ports.pop('Ethernet512', None)
        physical_dut_ports.pop('Ethernet520', None)
        port_speed = "100000"
    if platform == PlatformTypesConstants.PLATFORM_LEOPARD:
        port_speed = "100000"
    nonsplitable_ports = get_nonsplitable_ports(platform, topology, physical_dut_ports)
    target_ports = {}
    # Add ports connected from DUT to hosts
    for port in dut_host_ports:
        target_ports[port] = config_db['PORT'][port]
        physical_dut_ports.pop(port)

    aliases_list = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    added_ports_counter = len(target_ports)
    # Add loopback split ports
    for port in physical_dut_ports:
        port_data = physical_dut_ports[port]
        port_index = port_data['index']
        port_alias = port_data['alias']
        port_speed = port_speed
        port_mtu = '9100'
        port_lanes = port_data['lanes'].split(',')
        if port in nonsplitable_ports:
            if len(port_lanes) == 1:
                port_lanes = port_lanes
            else:
                port_lanes = [','.join(port_lanes)]
        else:
            if (platform in [PlatformTypesConstants.PLATFORM_MOOSE, PlatformTypesConstants.PLATFORM_HIPPO] and
                    expected_num_of_ports - added_ports_counter <= 4):
                port_lanes = modify_lanes_per_platform(platform, port_lanes, split_x2=True)
            else:
                port_lanes = modify_lanes_per_platform(platform, port_lanes)

        for lane in port_lanes:
            if expected_num_of_ports != added_ports_counter:

                lane_index = port_lanes.index(lane)
                first_port_lane = lane.split(',')[0]
                # 4600c has specific lanes(not one by one) config: "Ethernet0 0,1,2,3", "Ethernet4 8,9,10,11"
                if platform in [PlatformTypesConstants.PLATFORM_TIGON, PlatformTypesConstants.PLATFORM_LIGER]:
                    first_port_lane = int(first_port_lane) // 2

                port_name = f'Ethernet{first_port_lane}'
                alias_symbol = aliases_list[lane_index]
                new_port_alias = f'{port_alias}{alias_symbol}'

                # In case when port with single lane - do not change port alias, use original
                if len(port_lanes) == 1:
                    new_port_alias = port_alias

                port_data = {'index': port_index, 'lanes': lane, 'mtu': port_mtu, 'alias': new_port_alias,
                             'admin_status': 'up', 'speed': port_speed}

                target_ports[port_name] = port_data
                added_ports_counter += 1

    config_db['PORT'] = target_ports

    return config_db


def get_nonsplitable_ports(platform, topology, physical_dut_ports):
    nonsplitable_ports = []
    if platform == PlatformTypesConstants.PLATFORM_LIONFISH:
        for noga_alias, peer_noga_alias in topology.ports_interconnects.items():
            if noga_alias.startswith("dut") and peer_noga_alias.startswith("dut"):
                port = topology.ports[noga_alias]
                peer_port = topology.ports[peer_noga_alias]

                if port in nonsplitable_ports or peer_port in nonsplitable_ports:
                    continue
                if port not in physical_dut_ports or peer_port not in physical_dut_ports:
                    continue

                port_lanes = physical_dut_ports[port]['lanes'].split(',')
                peer_port_lanes = physical_dut_ports[peer_port]['lanes'].split(',')

                if len(port_lanes) != len(peer_port_lanes):
                    nonsplitable_ports.append(port)
                    nonsplitable_ports.append(peer_port)

    return nonsplitable_ports
