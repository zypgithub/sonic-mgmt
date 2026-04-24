#!/usr/bin/env python
import allure
import os
import pathlib
from os.path import join
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
import logging
from retry import retry
logger = logging.getLogger()


@allure.title('Start up dut to hosts port on SIMX switch')
def test_startup_simx_hosts_ports(topology_obj):
    """
    This script will startup dut to hosts port on SIMX switch by
    sending packet from hosts to switch.
    :param topology_obj: topology object fixture
    :return: raise assertion error in case of script failure
    """
    pcap_file_path = join(str(pathlib.Path(__file__).parent.absolute()), "simx_signal_peer_oper_up.pcap")
    ha_dut_1 = topology_obj.ports['ha-dut-1']
    ha_dut_2 = topology_obj.ports['ha-dut-2']
    hb_dut_1 = topology_obj.ports['hb-dut-1']
    hb_dut_2 = topology_obj.ports['hb-dut-2']
    ha_engine = topology_obj.players['ha']['engine']
    hb_engine = topology_obj.players['hb']['engine']
    try:
        logger.info("send simx signal peer oper up from hosts to dut.")
        with allure.step('send simx signal peer oper up from host {} interface {}'.format(ha_engine.ip, ha_dut_1)):
            validation = {'sender': 'ha', 'send_args': {'interface': ha_dut_1, 'pcap': pcap_file_path}}
            scapy = ScapyChecker(topology_obj.players, validation)
            scapy.run_validation()

        with allure.step('send simx signal peer oper up from host {} interface {}'.format(ha_engine.ip, ha_dut_2)):
            validation = {'sender': 'ha', 'send_args': {'interface': ha_dut_2, 'pcap': pcap_file_path}}
            scapy = ScapyChecker(topology_obj.players, validation)
            scapy.run_validation()

        with allure.step('send simx signal peer oper up from host {} interface {}'.format(hb_engine.ip, hb_dut_1)):
            validation = {'sender': 'hb', 'send_args': {'interface': hb_dut_1, 'pcap': pcap_file_path}}
            scapy = ScapyChecker(topology_obj.players, validation)
            scapy.run_validation()

        with allure.step('send simx signal peer oper up from host {} interface {}'.format(hb_engine.ip, hb_dut_2)):
            validation = {'sender': 'hb', 'send_args': {'interface': hb_dut_2, 'pcap': pcap_file_path}}
            scapy = ScapyChecker(topology_obj.players, validation)
            scapy.run_validation()

        validate_dut_to_hosts_port_up(topology_obj)

    except Exception as err:
        raise AssertionError(err)


@retry(Exception, tries=3, delay=10)
def validate_dut_to_hosts_port_up(topology_obj):
    """
    This function will validate with retries that all the ports from the switch to hosts are up
    after the pcap was sent.
    :param topology_obj: topology object fixture
    :return: raise assertion error in case of script failure
    """
    logger.info("Validate all the ports from the switch to hosts are up after the pcap was sent.")
    cli_object = topology_obj.players['dut']['cli']
    ports_list = [topology_obj.ports['dut-ha-1'],
                  topology_obj.ports['dut-ha-2'],
                  topology_obj.ports['dut-hb-1'],
                  topology_obj.ports['dut-hb-2']]
    cli_object.interface.check_ports_status(ports_list, expected_status='up')
