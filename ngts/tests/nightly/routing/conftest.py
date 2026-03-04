import pytest
import logging
import allure
import os
import json

from ngts.config_templates.ip_config_template import IpConfigTemplate
from ngts.config_templates.route_config_template import RouteConfigTemplate
from ngts.config_templates.frr_config_template import FrrConfigTemplate
from ngts.constants.constants import InfraConst


logger = logging.getLogger()
CONFIGS_FOLDER = os.path.dirname(os.path.abspath(__file__))


def prepare_dut_bgp_config():
    """
    Prepare config for BGP which will be loaded on DUT and save locally
    :return: path to BGP config file
    """

    bgp_conf = {"BGP_NEIGHBOR": {"20.0.0.2": {"admin_status": "up", "asn": "501", "holdtime": "10", "keepalive": "3",
                                              "local_addr": "20.0.0.1", "name": "HA", "nhopself": "0", "rrclient": "0"},
                                 "30.0.0.2": {"admin_status": "up", "asn": "501", "holdtime": "10", "keepalive": "3",
                                              "local_addr": "30.0.0.1", "name": "HB", "nhopself": "0", "rrclient": "0"}
                                 },
                "DEVICE_METADATA": {"localhost": {"bgp_asn": "500"}}
                }

    bgp_conf_file_path = os.path.join(CONFIGS_FOLDER, 'dut_bgp_conf.json')

    with open(bgp_conf_file_path, 'w') as bgp_conf_file:
        json.dump(bgp_conf, bgp_conf_file, indent=4)

    dummy_bgp_conf_file_path = os.path.join(CONFIGS_FOLDER, 'dummy_dut_bgp_conf.json')
    with open(dummy_bgp_conf_file_path, 'w') as dummy_bgp_conf_file:
        pass
    return bgp_conf_file_path, dummy_bgp_conf_file_path


@pytest.fixture(scope='class', autouse=True)
def configuration(topology_obj, cli_objects, engines, interfaces, platform_params, setup_name,
                  ha_dut_1_mac, hb_dut_1_mac, dut_ha_1_mac, dut_hb_1_mac, asic_count, tested_asic_index):
    """
    Pytest fixture which are doing configuration for routing tests
    Configuration schema:
     ----------------           ---------------             ---------------
    |AS 501         |      -----|20.0.0.1/24   |           |AS 501         |
    |               |    BGP    |    AS 500    |    BGP    |               |
    |    20.0.0.2/24|-----      |10.10.10.10/32|      -----|30.0.0.2/24    |
    |               |           |              |     |     |               |
    |               |           |   30.0.0.1/24|-----      |               |
     ---------------            ---------------             ---------------
    DUT has static routes:
    50.0.0.0/24 via 20.0.0.2
    50.0.0.1/32 via 30.0.0.2
    :param topology_obj: topology object fixture
    :param cli_objects: cli_objects fixture
    :param engines: engines fixture
    :param interfaces: interfaces fixture
    :param platform_params: platform_params fixture
    :param setup_name: setup_name fixture
    """
    # IP config which will be used in test
    ip_config_dict = {
        'dut': [{'iface': interfaces.dut_ha_1, 'ips': [('20.0.0.1', '24')]},
                {'iface': interfaces.dut_hb_1, 'ips': [('30.0.0.1', '24')]},
                {'iface': 'Loopback0', 'ips': [('10.10.10.10', '32')]}
                ],
        'ha': [{'iface': interfaces.ha_dut_1, 'ips': [('20.0.0.2', '24')]}
               ],
        'hb': [{'iface': interfaces.hb_dut_1, 'ips': [('30.0.0.2', '24')]}
               ]
    }

    static_route_config_dict = {
        'dut': [{'dst': '50.0.0.0', 'dst_mask': 24, 'via': ['20.0.0.2']},
                {'dst': '50.0.0.1', 'dst_mask': 32, 'via': ['30.0.0.2']}]
    }

    frr_config_dict = {
        'ha': {'configuration': {'config_name': 'ha_frr.conf', 'path_to_config_file': CONFIGS_FOLDER},
               'cleanup': ['configure terminal', 'no router bgp 501', 'exit', 'exit']},
        'hb': {'configuration': {'config_name': 'hb_frr.conf', 'path_to_config_file': CONFIGS_FOLDER},
               'cleanup': ['configure terminal', 'no router bgp 501', 'exit', 'exit']}
    }
    IpConfigTemplate.configuration(topology_obj, ip_config_dict)
    RouteConfigTemplate.configuration(topology_obj, static_route_config_dict)

    # config below for ARP must be removed later, it's temporary workaround
    dut_ip_cli = cli_objects.dut.ip
    dut_ip_cli.add_ip_neigh('20.0.0.2', ha_dut_1_mac, interfaces.dut_ha_1, action='add')
    dut_ip_cli.add_ip_neigh('20.0.0.2', ha_dut_1_mac, interfaces.dut_ha_1, action='change')
    dut_ip_cli.add_ip_neigh('30.0.0.2', hb_dut_1_mac, interfaces.dut_hb_1, action='add')
    dut_ip_cli.add_ip_neigh('30.0.0.2', hb_dut_1_mac, interfaces.dut_hb_1, action='change')

    engines.ha.run_cmd(f'sudo ip neigh add 20.0.0.1 dev {interfaces.ha_dut_1} lladdr {dut_ha_1_mac}')
    engines.ha.run_cmd(f'sudo ip neigh change 20.0.0.1 dev {interfaces.ha_dut_1} lladdr {dut_ha_1_mac}')

    engines.hb.run_cmd(f'sudo ip neigh add 30.0.0.1 dev {interfaces.hb_dut_1} lladdr {dut_hb_1_mac}')
    engines.hb.run_cmd(f'sudo ip neigh change 30.0.0.1 dev {interfaces.hb_dut_1} lladdr {dut_hb_1_mac}')

    FrrConfigTemplate.configuration(topology_obj, frr_config_dict)
    load_dut_bgp_config(engines, asic_count, tested_asic_index)
    cmd_extetion_in_case_of_multi_asic = cli_objects.dut.multi_asic_cli.multi_asic_config_cmd_ext
    engines.dut.run_cmd(f'sudo sonic-cfggen {cmd_extetion_in_case_of_multi_asic} -j /tmp/dut_bgp_conf.json -w')
    cli_objects.dut.general.save_configuration()

    cli_objects.dut.bgp.restart_bgp_service()
    cli_objects.dut.general.verify_dockers_are_up(dockers_list=['bgp'], running_config=False, platform_params=platform_params)

    yield

    FrrConfigTemplate.cleanup(topology_obj, frr_config_dict)

    # Remove BGP related data from config_db.json
    engines.dut.run_cmd(f'sudo sonic-db-cli {cmd_extetion_in_case_of_multi_asic} CONFIG_DB DEL "BGP_NEIGHBOR|20.0.0.2"')
    engines.dut.run_cmd(f'sudo sonic-db-cli {cmd_extetion_in_case_of_multi_asic} CONFIG_DB DEL "BGP_NEIGHBOR|30.0.0.2"')
    engines.dut.run_cmd(f'sudo sonic-db-cli {cmd_extetion_in_case_of_multi_asic} CONFIG_DB HDEL "DEVICE_METADATA|localhost" "bgp_asn"')

    RouteConfigTemplate.cleanup(topology_obj, static_route_config_dict)
    IpConfigTemplate.cleanup(topology_obj, ip_config_dict)
    cli_objects.dut.general.save_configuration()

    cli_objects.dut.frr.remove_frr_config_files()
    cli_objects.dut.bgp.restart_bgp_service()
    cli_objects.dut.general.verify_dockers_are_up(dockers_list=['bgp'], running_config=False, platform_params=platform_params)
    cli_objects.dut.general.wait_for_frr_daemons_ready()

    # config below for ARP must be removed later, it's temporary workaround
    dut_ip_cli.ip_neigh_flush(interfaces.dut_ha_1)
    dut_ip_cli.ip_neigh_flush(interfaces.dut_hb_1)

    engines.ha.run_cmd(f'sudo ip neigh flush dev {interfaces.ha_dut_1}')

    engines.hb.run_cmd(f'sudo ip neigh flush dev {interfaces.hb_dut_1}')


def load_dut_bgp_config(engines, asic_count, tested_asic_index):
    dut_bgp_conf_file_path, dummy_bgp_conf_file_path = prepare_dut_bgp_config()
    engines.dut.copy_file(source_file=dut_bgp_conf_file_path, file_system='/tmp', dest_file='dut_bgp_conf.json')
    engines.dut.copy_file(source_file=dummy_bgp_conf_file_path, file_system='/tmp', dest_file='dummy_dut_bgp_conf.json')
    config_files = []
    for asic_index in range(0, asic_count):
        if asic_index != tested_asic_index:
            config_files.append('/tmp/dummy_dut_bgp_conf.json')
        else:
            config_files.append('/tmp/dut_bgp_conf.json')
    config_load_cmd = f"sudo config load -y {','.join(config_files)}"
    engines.dut.run_cmd(config_load_cmd)
