#!/usr/bin/env python
import allure
import csv
import logging
import json
import pytest
from collections import defaultdict
from ngts.constants.constants import SonicConst
from ngts.scripts.test_rpc_check_and_set_topology import run_testbed_cli_script
from ngts.scripts.sonic_deploy.test_deploy_and_upgrade import get_info_from_topology


logger = logging.getLogger()


@pytest.fixture(scope="function", autouse=True)
def confirm_setup_ready(cli_objects):
    admin_up_ports = cli_objects.dut.interface.get_admin_up_ports()

    yield

    cli_objects.dut.general.verify_dockers_are_up()
    cli_objects.dut.interface.check_link_state(ifaces=admin_up_ports)


def read_csv_config(csv_path, dut_name):
    """
    Read link csv file
    :param csv_path: csv file path
    :param dut_name: dut name
    :return: port configuration dict
    """
    port_config = defaultdict(dict)
    default_autoneg_on = False
    logger.info(f"Read {csv_path}")
    with open(csv_path, 'r') as csv_file:
        reader = csv.reader(csv_file)
        header = next(reader)
        assert 'StartDevice' in header
        assert 'StartPort' in header
        assert 'BandWidth' in header
        if 'AutoNeg' not in header:
            default_autoneg_on = True
        else:
            autoneg_index = header.index('AutoNeg')
        device_index = header.index('StartDevice')
        port_index = header.index('StartPort')
        bandwidth_index = header.index('BandWidth')

        for row in reader:
            if row and row[device_index] == dut_name:
                port_config[row[port_index]]['speed'] = row[bandwidth_index]
                if default_autoneg_on:
                    port_config[row[port_index]]['autoneg'] = 'on'
                else:
                    port_config[row[port_index]]['autoneg'] = row[autoneg_index]

    return port_config


def update_config_db(dut_engine, csv_port_config, passive_ports):
    """
    Update the config_db json file on PORT config part
    1.Update the port speed based on the link csv file
    2.Update the port autoneg based on the link csv file
    """
    logger.info(f"Copy {SonicConst.CONFIG_DB_JSON_PATH} from DUT to ngts docker")
    dut_engine.copy_file(source_file=SonicConst.CONFIG_DB_JSON_PATH, dest_file='/tmp/' + SonicConst.CONFIG_DB_JSON,
                         overwrite_file=True, verify_file=False, direction='get', file_system='/tmp/')

    logger.info("Update speed and autoneg values according to the definition in the link csv file")
    with open(f'/tmp/{SonicConst.CONFIG_DB_JSON}', 'r') as config_file:
        config_data = json.load(config_file)
        for port in config_data['PORT']:
            if port in passive_ports:
                config_data['PORT'][port]['admin_status'] = 'down'
            if port in csv_port_config:
                config_data['PORT'][port]['speed'] = csv_port_config[port]['speed']
                config_data['PORT'][port]['autoneg'] = csv_port_config[port]['autoneg']

    with open(f'/tmp/{SonicConst.CONFIG_DB_JSON}', 'w') as config_file:
        json.dump(config_data, config_file, indent=4)

    logger.info(f"Copy {SonicConst.CONFIG_DB_JSON_PATH} from ngts docker to DUT")
    dut_engine.copy_file(source_file='/tmp/' + SonicConst.CONFIG_DB_JSON, dest_file=SonicConst.CONFIG_DB_JSON,
                         overwrite_file=True, verify_file=False, file_system='/tmp/')

    logger.info(f"Replace the default {SonicConst.CONFIG_DB_JSON_PATH}")
    dut_engine.run_cmd(f'sudo mv /tmp/{SonicConst.CONFIG_DB_JSON} {SonicConst.CONFIG_DB_JSON_PATH}', validate=True)


@allure.title('Deploy L2 mode')
def test_deploy_l2_mode(cli_objects, engines, topology_obj, workspace_path):
    """
    This test will deploy l2 mode on the dut
    """

    dut_name = cli_objects.dut.chassis.get_hostname()
    setup_info = get_info_from_topology(topology_obj, workspace_path)
    csv_path = setup_info['ansible_path'] + 'files/sonic_nvidia_links.csv'
    ansible_cmd = f"ansible-playbook -i lab testbed_set_l2_mode.yml --vault-password-file=vault -l {dut_name} -vvv"
    csv_port_config = read_csv_config(csv_path, dut_name)
    passive_phy_ports = cli_objects.dut.interface.get_passive_phy_ports()

    with allure.step("Deploy L2 mode"):
        run_testbed_cli_script(ansible_cmd, setup_info['ansible_path'])

    with allure.step("Update port speed and autoneg configuration based on link csv file"):
        update_config_db(engines.dut, csv_port_config, passive_phy_ports)
        cli_objects.dut.general.reload_configuration(force=True)


@allure.title('Restore default mode')
def test_restore_default_mode(cli_objects, sonic_topo, topology_obj, workspace_path, platform_params, is_air):
    """
    This test will restore the default mode
    """
    dut_name = cli_objects.dut.chassis.get_hostname()
    setup_info = get_info_from_topology(topology_obj, workspace_path)
    ansible_cmd = f"./testbed-cli.sh deploy-mg {dut_name}-{sonic_topo} lab vault -vvv"

    with allure.step("Deploy minigraph"):
        run_testbed_cli_script(ansible_cmd, setup_info['ansible_path'])
    with allure.step('Apply DNS servers configuration'):
        for dut in setup_info['duts']:
            general_cli_obj = dut['cli_obj']
            topology_obj.players[dut['dut_alias']]['engine'].disconnect()
            general_cli_obj.cli_obj.ip.apply_dns_servers_into_resolv_conf(is_air_setup=is_air)
            general_cli_obj.save_configuration()
