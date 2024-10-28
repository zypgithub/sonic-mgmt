import allure
import logging
import pytest
import re
import collections
import json
from retry.api import retry_call

from ngts.cli_util.verify_cli_show_cmd import verify_show_cmd
logger = logging.getLogger()


@pytest.mark.lldp
@pytest.mark.push_gate
@allure.title('test show LLDP table information')
def test_show_lldp_table_output(topology_obj, engines):
    """
    Compare the LLDP info in the "show lldp table" to the topology expected connectivity
    :param topology_obj: topology object fixture
    :return: None, raise error in case of unexpected lldp result
    """
    with allure.step("Verifying the output of \"show lldp table\" command match the expected setup Noga topology"):

        dut_ports_interconnects = get_dut_ports_interconnects(topology_obj.ports_interconnects)
        retry_call(verify_lldp_ports_match_topology_ports, fargs=[dut_ports_interconnects, topology_obj], tries=6,
                   delay=5, logger=logger)

    with allure.step('Verifying LLDP neighbor ports data'):
        retry_call(verify_neighbour_ports, fargs=[topology_obj, engines, dut_ports_interconnects], tries=10, delay=5,
                   logger=logger)


def verify_neighbour_ports(topology_obj, engines, dut_ports_interconnects):
    """
    Verify LLDP neighbour ports info
    :param topology_obj: topology object
    :param engines: engines fixture
    :param dut_ports_interconnects: dut ports interconnects
    :return: Raise Assertion in case when failed
    """
    cli_object = topology_obj.players['dut']['cli']
    lldp_table_info = cli_object.lldp.parse_lldp_table_info()
    port_aliases_dict = cli_object.interface.parse_ports_aliases_on_sonic()
    dut_hostname = cli_object.chassis.get_hostname()
    for port_noga_alias, neighbor_port_noga_alias in dut_ports_interconnects.items():
        port = topology_obj.ports[port_noga_alias]
        port_neighbor = topology_obj.ports[neighbor_port_noga_alias]
        with allure.step("Validating topology neighbor ports {}: {} and {}: {}"
                         .format(port_noga_alias, port, neighbor_port_noga_alias, port_neighbor)):
            if is_port_connected_to_host(port_noga_alias):
                verify_lldp_table_info_for_host_port(topology_obj, lldp_table_info, port,
                                                     neighbor_port_noga_alias,
                                                     port_neighbor)
            else:
                topo_remote_port_id = port_aliases_dict[port_neighbor]
                verify_lldp_table_info_for_sonic_port(port, lldp_table_info, dut_hostname,
                                                      topo_remote_port_id, port_neighbor)


def get_dut_ports_interconnects(ports_interconnects):
    """
    :param ports_interconnects: a dictionary with all the setup connectivity,
    i.e. { 'dut-ha-1': 'ha-dut-1', 'ha-dut-1': 'dut-ha-1'}
    :return: a filtered dictionary with all the connectivity only on the dut side, i.e. {'dut-ha-1': 'ha-dut-1'}
    """
    dut_ports_interconnects = {}
    for port_noga_alias, neighbor_port_noga_alias in ports_interconnects.items():
        alias_prefix = port_noga_alias.split('-')[0]
        if alias_prefix == 'dut':
            dut_ports_interconnects[port_noga_alias] = neighbor_port_noga_alias
    return dut_ports_interconnects


def verify_lldp_ports_match_topology_ports(dut_ports_interconnects, topology_obj):
    """
    :param dut_ports_interconnects: a filtered dictionary with all the connectivity only on the dut side, i.e. {'dut-ha-1': 'ha-dut-1'}
    :param topology_obj: topology object fixture
    :return: None, raise assertion error if the topology ports list is not same as lldp ports list
    """
    with allure.step("Verifying topology ports list is same as lldp ports list"):
        cli_object = topology_obj.players['dut']['cli']
        lldp_table_info = cli_object.lldp.parse_lldp_table_info()
        logger.info("Verify topology ports list is same as lldp ports list")
        dut_ports = list(map(lambda x: topology_obj.ports[x], dut_ports_interconnects.keys()))
        lldp_ports = list(lldp_table_info.keys())
        msg = "Topology ports list: {} does not match \n lldp ports list: {}".format(dut_ports, lldp_ports)

        def compare(x, y): return collections.Counter(x) == collections.Counter(y)
        assert compare(lldp_ports, dut_ports), msg


def is_port_connected_to_host(port_alias):
    """
    :param port_alias: port alias on noga i.e. 'dut-ha-1'
    :return: True if port is connected to host according to topology, Else false
    """
    dut_host_ports = ['dut-ha-1', 'dut-ha-2', 'dut-hb-1', 'dut-hb-2']
    return port_alias in dut_host_ports


def verify_lldp_table_info_for_host_port(topology_obj, lldp_table_info, port, neighbor_port_noga_alias, port_neighbor):
    """
    :param topology_obj: topology object fixture
    :param lldp_table_info: a dictionary with the parsed info from "show lldp table" command
    :param port: i.e. 'Ethernet252'
    :param neighbor_port_noga_alias: i.e. 'hb-dut-2'
    :param port_neighbor: i.e. enp5s0f0
    :return: None, raise assertion error if lldp table info doesn't match the expected output
    """
    host_name_alias = neighbor_port_noga_alias.split('-')[0]
    cli_object = topology_obj.players[host_name_alias]['cli']
    hostname = cli_object.chassis.get_hostname()
    host_port_mac = cli_object.mac.get_mac_address_for_interface(port_neighbor)
    verify_lldp_table_info_for_port(port, lldp_table_info,
                                    hostname,
                                    host_port_mac,
                                    port_neighbor, topo_neighbor_port_capability=["R", "O"])


def verify_lldp_table_info_for_sonic_port(port, lldp_table_info, topo_hostname,
                                          topo_remote_port_id, topo_neighbor_port_descr):
    """
    verify lldp info for port match expected topology
    :param port: i.e.  Ethernet80
    :param lldp_table_info: a dictionary with lldp info
    :param topo_hostname: hostname of neighbor port remote device in topology i.e. r-boxer-sw01
    :param topo_remote_port_id: remote port id in topology i.e.  port alias
    :param topo_neighbor_port_descr: port description in topology, enp5s0f1/ Ethernet84
    :return:  None, raise AssertionError in case of validation fails
    """
    verify_lldp_table_info_for_port(port, lldp_table_info, topo_hostname,
                                    topo_remote_port_id, topo_neighbor_port_descr, topo_neighbor_port_capability=["BR"])


def verify_lldp_table_info_for_port(port, lldp_table_info, topo_hostname, topo_remote_port_id,
                                    topo_neighbor_port_descr, topo_neighbor_port_capability):
    """
    verify lldp info for port match expected topology
    :param port: i.e.  Ethernet80
    :param lldp_table_info: a dictionary with lldp info
    :param topo_hostname: hostname of neighbor port remote device in topology i.e. r-boxer-sw01
    :param topo_remote_port_id: remote port id in topology i.e. port mac address / port alias
    :param topo_neighbor_port_descr: port description in topology, enp5s0f1/ Ethernet84
    :param topo_neighbor_port_capability: port capability in topology
    :return:  None, raise AssertionError in case of validation fails
    """
    lldp_hostname, lldp_remote_port_id, lldp_port_capabilities, lldp_neighbor_port_descr = lldp_table_info[port]
    logger.info("Neighbor of port {} according to LLDP is: RemoteDevice: {} RemotePortID: {} RemotePortDescr: {}"
                .format(port, lldp_hostname, lldp_remote_port_id, lldp_neighbor_port_descr))
    logger.info("Neighbor of port {} according to topology is: RemoteDevice: {} RemotePortID: {} RemotePortDescr: {}"
                .format(port, topo_hostname, topo_remote_port_id, topo_neighbor_port_descr))
    verify_hostname(topo_hostname, lldp_hostname)
    verify_port_id(topo_remote_port_id, lldp_remote_port_id)
    verify_port_descr(topo_neighbor_port_descr, lldp_neighbor_port_descr)
    verify_port_capability(topo_neighbor_port_capability, lldp_port_capabilities)


def verify_hostname(topo_hostname, lldp_hostname):
    """
    Verify the remote neighbor hostname match in LLDP and on topology
    :param topo_hostname: switch/host hostname from topology i.e. r-sonic-02-005/ r-panther-13
    :param lldp_hostname: switch/host hostname from lldp i.e. r-sonic-02-005/ r-panther-13
    :return: None, raise AssertionError in case of mismatch
    """
    assert topo_hostname == lldp_hostname, \
        "Assertion Error: Expected hostname is {}, LLDP hostname is {}" \
        .format(topo_hostname, lldp_hostname)


def verify_port_id(topo_remote_port_id, lldp_remote_port_id):
    """
    Verify the remote neighbor port id match in LLDP and on topology
    :param topo_remote_port_id: switch/host port id from topology i.e. port mac/ port sonic alias
    :param lldp_remote_port_id: switch/host port id from lldp i.e. port mac/ port sonic alias
    :return: None, raise AssertionError in case of mismatch
    """
    assert topo_remote_port_id == lldp_remote_port_id, \
        "Assertion Error: Expected neighbor port  ID is {}, LLDP neighbor id is {}" \
        .format(topo_remote_port_id, lldp_remote_port_id)


def verify_port_descr(topo_neighbor_port_descr, lldp_neighbor_port_descr):
    """
    Verify the remote neighbor port description match in LLDP and on topology
    :param topo_neighbor_port_descr: switch/host port description from topology i.e. enp5s0f1/ Ethernet84
    :param lldp_neighbor_port_descr:  switch/host port description from lldp i.e. enp5s0f1/ Ethernet84
    :return:  None, raise AssertionError in case of mismatch
    """
    assert re.search(topo_neighbor_port_descr, lldp_neighbor_port_descr, re.IGNORECASE), \
        "Assertion Error: Expected neighbor port description is {}, LLDP neighbor description is {}" \
        .format(topo_neighbor_port_descr, lldp_neighbor_port_descr)


def verify_port_capability(topo_neighbor_port_capability, lldp_neighbor_port_capability):
    """
    Verify the remote neighbor port description match in LLDP and on topology
    :param topo_neighbor_port_capability: switch/host port capability from topology
    :param lldp_neighbor_port_capability:  switch/host port capability from lldp
    :return:  None, raise AssertionError in case of mismatch
    """
    assert lldp_neighbor_port_capability in topo_neighbor_port_capability, \
        "Assertion Error: Expected neighbor port capability is one of {}, LLDP neighbor port capability is {}" \
        .format(topo_neighbor_port_capability, lldp_neighbor_port_capability)


@pytest.mark.lldp
@allure.title('test show LLDP neighbors information')
def test_show_lldp_neighbors_output(topology_obj, engines):
    """
    Compare the LLDP info in the "show lldp neighbors" command to the topology expected connectivity
    :param topology_obj: topology object fixture
    :return: None, raise assertion error if lldp neighbors info doesn't match the expected output
    """
    with allure.step("Verifying the output of \"show lldp neighbors\" command"
                     " match the expected setup Noga topology"):
        cli_object = topology_obj.players['dut']['cli']
        dut_ports_interconnects = get_dut_ports_interconnects(topology_obj.ports_interconnects)
        dut_hostname = cli_object.chassis.get_hostname()
        dut_mac = cli_object.mac.get_mac_address_for_interface("eth0")
        for port_noga_alias, neighbor_port_noga_alias in dut_ports_interconnects.items():
            retry_call(verify_lldp_neighbor_info,
                       fargs=[topology_obj, cli_object, engines, port_noga_alias,
                              neighbor_port_noga_alias, dut_hostname, dut_mac],
                       tries=13, delay=10, logger=logger)


def verify_lldp_neighbor_info(topology_obj, cli_object, engines,
                              port_noga_alias, neighbor_port_noga_alias, dut_hostname, dut_mac):
    """
    Compare the LLDP info in the "show lldp neighbors" command to the topology expected connectivity
    :return: None, raise assertion error if lldp neighbors info doesn't match the expected output
    """
    port = topology_obj.ports[port_noga_alias]
    port_neighbor = topology_obj.ports[neighbor_port_noga_alias]
    lldp_info = cli_object.lldp.parse_lldp_info_for_specific_interface(port)
    with allure.step("Validating topology neighbor ports {}: {} and {}: {}"
                     .format(port_noga_alias, port, neighbor_port_noga_alias, port_neighbor)):
        if is_port_connected_to_host(port_noga_alias):
            verify_lldp_neighbor_info_for_host_port(topology_obj, lldp_info, port,
                                                    neighbor_port_noga_alias, port_neighbor)
        else:
            verify_lldp_neighbor_info_for_sonic_port(port, lldp_info, dut_hostname, dut_mac, port_neighbor)


def verify_lldp_neighbor_info_for_host_port(topology_obj, lldp_neighbor_info, port, neighbor_port_noga_alias, port_neighbor):
    """
    :param topology_obj: topology object fixture
    :param lldp_neighbor_info: a dictionary with parsed output of show lldp neighbors info
    :param port: i.e. 'Ethernet252'
    :param neighbor_port_noga_alias: i.e. 'hb-dut-2'
    :param port_neighbor: i.e. enp5s0f0
    :return:  None, raise AssertionError in case of validation fails
    """
    host_name_alias = neighbor_port_noga_alias.split('-')[0]
    host_engine = topology_obj.players[host_name_alias]['engine']
    cli_object = topology_obj.players[host_name_alias]['cli']
    hostname = cli_object.chassis.get_hostname()
    host_mac = cli_object.mac.get_mac_address_for_interface(port_neighbor)
    verify_lldp_neighbor_info_for_port(port, lldp_neighbor_info, hostname, host_mac, port_neighbor)


def verify_lldp_neighbor_info_for_sonic_port(port, lldp_neighbor_info, topo_hostname, topo_remote_id, topo_neighbor_port_descr):
    """
    verify lldp info for port match expected topology
    :param port: i.e.  Ethernet80
    :param lldp_neighbor_info: a dictionary with lldp info
    :param topo_hostname: hostname of neighbor port remote device in topology i.e. r-panther-13
    :param topo_remote_id: remote device id in topology i.e. device mac address
    :param topo_neighbor_port_descr: port description in topology, Ethernet84
    :return:  None, raise AssertionError in case of validation fails
    """
    verify_lldp_neighbor_info_for_port(port, lldp_neighbor_info, topo_hostname, topo_remote_id, topo_neighbor_port_descr)


def verify_lldp_neighbor_info_for_port(port, lldp_neighbor_info, topo_hostname, topo_remote_id, topo_neighbor_port_descr):
    """
    verify lldp info for port match expected topology
    :param port: i.e.  Ethernet80
    :param lldp_neighbor_info: a dictionary with lldp info
    :param topo_hostname: hostname of neighbor port remote device in topology i.e. r-boxer-sw01
    :param topo_remote_id: remote device id in topology i.e. device mac address
    :param topo_neighbor_port_descr: port description in topology, enp5s0f1/ Ethernet84
    :return:  None, raise AssertionError in case of validation fails
    """
    port_id = lldp_neighbor_info['Port']['PortID']
    chassis_id = lldp_neighbor_info['Chassis']['ChassisID']
    mac_in_lldp = port_id if 'mac' in port_id else chassis_id
    hostname_in_lldp = lldp_neighbor_info['Chassis']['SysName']
    port_description_in_lldp = lldp_neighbor_info['Port']['PortDescr']
    logger.info("Neighbor of port {} according to LLDP is: RemoteDeviceName: {} RemoteDeviceID: {} RemotePortDescr: {}"
                .format(port, hostname_in_lldp, mac_in_lldp, port_description_in_lldp))
    logger.info("Neighbor of port {} according to topology is: "
                "RemoteDeviceName: {} RemoteDeviceID: {} RemotePortDescr: {}"
                .format(port, topo_hostname, topo_remote_id, topo_neighbor_port_descr))
    verify_hostname(topo_hostname, hostname_in_lldp)
    verify_remote_device_id(topo_remote_id, mac_in_lldp)
    verify_port_descr(topo_neighbor_port_descr, port_description_in_lldp)


def verify_remote_device_id(topo_remote_device_id, lldp_remote_device_id):
    """
    Verify the remote neighbor device id  match in LLDP and on topology
    :param topo_remote_device_id:  switch/host device id from topology i.e. device mac address
    :param lldp_remote_device_id: switch/host device id from lldp i.e. device mac address
    :return:  None, raise AssertionError in case of mismatch
    """
    assert re.search(topo_remote_device_id, lldp_remote_device_id, re.IGNORECASE), \
        "Assertion Error: Expected Remote Device ID is {}, LLDP Remote Device id is {}" \
        .format(topo_remote_device_id, lldp_remote_device_id)


@pytest.mark.lldp
@pytest.mark.push_gate
@allure.title('test LLDP after disable on dut')
def test_lldp_after_disable_on_dut(topology_obj, engines, cli_objects):
    """
    Verify LLDP is up after being disabled.
    Lldp should be disabled after a disabled command and should be up after enable in 30 sec or less
    :param topology_obj: topology object fixture
    :param engines: setup engines fixture
    :param cli_objects: setup cli_objects fixture
    :return: None, raise assertion error if lldp info doesn't match the expected output
    """
    try:
        cli_objects.dut.lldp.disable_lldp()
        logger.info("Verify lldp is disabled in \"show_feature_status\"")
        check_lldp_feature_status(engines.dut, cli_objects.dut, expected_res=r"lldp\s+disabled")
        with allure.step("Expect test LLDP to fail after being disabled"):
            retry_call(validate_no_lldp_info_is_available, fargs=[topology_obj], tries=4, delay=5, logger=logger)
        cli_objects.dut.lldp.enable_lldp()
        logger.info("Verify LLDP service start")
        check_lldp_feature_status(engines.dut, cli_objects.dut)
        with allure.step("Expect test LLDP to pass after LLDP is enabled"):
            retry_call(verify_lldp_info_for_dut_host_ports, fargs=[topology_obj], tries=8, delay=5, logger=logger)
    finally:
        cli_objects.dut.lldp.enable_lldp()


def validate_no_lldp_info_is_available(topology_obj):
    try:
        verify_lldp_info_for_dut_host_ports(topology_obj)
        raise Exception("Test passed when expected to fail")
    except AssertionError as e:
        logger.info("Test failed as expected")


def check_lldp_feature_status(dut_engine, cli_object, expected_res=r"lldp\s+enabled"):
    with allure.step("Verifying the output of \"show feature status\" command"):
        feature_status = cli_object.general.show_feature_status()
        expected_output = [(expected_res, True)]
        verify_show_cmd(feature_status, expected_output)


def verify_lldp_info_for_dut_host_ports(topology_obj):
    """
    verify lldp information for dut-host ports with "show lldp neighbors" command.
    :param topology_obj: topology object fixture
    :return: None, raise AssertionError in case of validation fails
    """
    try:
        ports_for_validation = {'host_ports': ['ha-dut-1', 'ha-dut-2', 'hb-dut-1', 'hb-dut-2'],
                                'dut_ports': ['dut-ha-1', 'dut-ha-2', 'dut-hb-1', 'dut-hb-2']}

        cli_object = topology_obj.players['dut']['cli']
        for host_dut_port in zip(ports_for_validation['host_ports'], ports_for_validation['dut_ports']):
            host_port_alias = host_dut_port[0]
            host_name_alias = host_port_alias.split('-')[0]
            host_cli_object = topology_obj.players[host_name_alias]['cli']
            host_port_mac = host_cli_object.mac.get_mac_address_for_interface(topology_obj.ports[host_port_alias])
            dut_port = topology_obj.ports[host_dut_port[1]]
            with allure.step('Checking peer MAC address via LLDP in interface {}'.format(dut_port)):
                lldp_info = cli_object.lldp.parse_lldp_info_for_specific_interface(dut_port)
                logger.info('Checking that peer device mac address in LLDP output')
                assert host_port_mac in lldp_info['Port']['PortID'], \
                    '{} was not found in {}'.format(host_port_mac, lldp_info)

    except Exception as err:
        raise AssertionError(err)


@pytest.mark.lldp
@pytest.mark.push_gate
@allure.title('test LLDP after disable on host')
def test_lldp_after_disable_on_host(topology_obj, engines, interfaces):
    """
    :param topology_obj: topology object fixture
    :return: None, raise AssertionError in case of validation fails
    """
    cli_object = topology_obj.players['ha']['cli']
    try:
        cli_object.lldp.disable_lldp_on_interface(interfaces.ha_dut_1)
        with allure.step("Expect test LLDP to fail after LLDP was disabled on host interface"):
            try:
                verify_lldp_info_for_dut_host_ports(topology_obj)
                raise Exception("Test passed when expected to fail")
            except AssertionError as e:
                logger.info("Test failed as expected")
        logger.info("Start LLDP on host interface")
        cli_object.lldp.enable_lldp_on_interface(interfaces.ha_dut_1)
        with allure.step("Expect test LLDP to pass after LLDP is enabled on host interface"):
            retry_call(verify_lldp_info_for_dut_host_ports, fargs=[topology_obj], tries=4, delay=10, logger=logger)

    except Exception as err:
        raise AssertionError(err)

    finally:
        # cleanup
        cli_object.lldp.enable_lldp_on_interface(interfaces.ha_dut_1)


@pytest.mark.lldp
@pytest.mark.push_gate
@allure.title('test LLDP when changing tx-interval on dut')
def test_lldp_change_transmit_delay(topology_obj, engines):
    """
    this test changes the lldp transmit interval and
    verify lldp information update on neighbor host within the configured interval.
    :param topology_obj: topology object fixture
    :return: None, raise AssertionError in case of validation fails
    """
    # dut_engine = topology_obj.players['dut']['engine']
    cli_object = topology_obj.players['dut']['cli']
    checked_intervals = [120, 60, 30]
    for interval in checked_intervals:
        with allure.step("Check lldp when changing transmit delay to {} seconds.".format(interval)):
            cli_object.lldp.change_lldp_tx_interval(interval=interval)
            cli_object.lldp.verify_lldp_tx_interval(expected_transmit_interval=interval)
            cli_object.lldp.pause_lldp()
            cli_object.lldp.resume_lldp()
            logger.info("Verify LLDP service resume within {} seconds".format(interval))
            with allure.step("Expect test LLDP to pass within {} seconds after LLDP is resume".format(interval)):
                retry_call(verify_lldp_info_for_host_dut_ports, fargs=[topology_obj],
                           tries=int(interval / 10) + 1, delay=10, logger=logger)


def verify_lldp_info_for_host_dut_ports(topology_obj):
    """
    verify lldp information for dut-host ports with "show lldp neighbors" command.
    :param topology_obj: topology object fixture
    :return: None, raise AssertionError in case of validation fails
    """
    try:
        ports_for_validation = {'host_ports': ['ha-dut-1', 'ha-dut-2', 'hb-dut-1', 'hb-dut-2'],
                                'dut_ports': ['dut-ha-1', 'dut-ha-2', 'dut-hb-1', 'dut-hb-2']}
        cli_object = topology_obj.players['dut']['cli']
        dut_mgmt_ip = cli_object.ip.get_mgmt_interface_ipv4_address()
        dut_hostname = cli_object.chassis.get_hostname()
        for host_port_alias, dut_host_port_alias in zip(ports_for_validation['host_ports'], ports_for_validation['dut_ports']):
            host_name_alias = host_port_alias.split('-')[0]
            dut_port = topology_obj.ports[dut_host_port_alias]
            host_port = topology_obj.ports[host_port_alias]
            host_cli_object = topology_obj.players[host_name_alias]['cli']
            host_hostname = host_cli_object.chassis.get_hostname()
            port_lldp_output = host_cli_object.lldp.show_lldp_info_for_specific_interface(host_port)
            parsed_lldp_output_dict = host_cli_object.lldp.parse_lldp_info_for_specific_interface(port_lldp_output)
            with allure.step('Checking LLDP Info in host {} for interface {}'.format(host_hostname, host_port)):
                neighbor_port = parsed_lldp_output_dict["neighbor_port"]
                neighbor_hostname = parsed_lldp_output_dict["neighbor_hostname"]
                neighbor_mgmt_ip = parsed_lldp_output_dict["neighbor_mgmt_ip"]
                verify_port_descr(dut_port, neighbor_port)
                verify_hostname(dut_hostname, neighbor_hostname)
                verify_mgmt_ip(dut_mgmt_ip, neighbor_mgmt_ip)

    except Exception as err:
        raise AssertionError(err)


def verify_mgmt_ip(topo_remote_device_mgmt_ip, lldp_remote_device_mgmt_ip):
    """
    Verify the remote neighbor device mgmt ip match in LLDP and on topology
    :param topo_remote_device_mgmt_ip: switch/host device mgmt ip from topology
    :param lldp_remote_device_mgmt_ip: switch/host device mgmt ip from lldp
    :return: None, raise AssertionError in case of mismatch
    """
    assert topo_remote_device_mgmt_ip == lldp_remote_device_mgmt_ip, \
        "Assertion Error: Expected Remote Device Management Address is {}, LLDP Remote Device Management Address is {}"\
        .format(topo_remote_device_mgmt_ip, lldp_remote_device_mgmt_ip)
