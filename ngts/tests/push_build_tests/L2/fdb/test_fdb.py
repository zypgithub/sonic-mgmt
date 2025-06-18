import allure
import logging
import pytest

from retry.api import retry_call
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker

logger = logging.getLogger()

# Constants
PORT_CHANNEL = 'PortChannel0002'

@pytest.mark.build
@pytest.mark.push_gate
@allure.title('PushGate FDB test case')
def test_push_gate_fdb(cli_objects, players):
    """
    Run PushGate FDB test case, test doing FDB validation - we check that MAC address which sent traffic available
    in FDB table on switch
    """
    try:
        src_iface = 'bond0.40'
        dst_ip = '40.0.0.1'
        with allure.step('Check that {} link in UP state'.format(PORT_CHANNEL)):
            retry_call(cli_objects.dut.interface.check_ports_status, fargs=[[PORT_CHANNEL]], tries=12,
                       delay=5, logger=logger)

        with allure.step('Sending 3 ping packets to {} from interface {}'.format(dst_ip, src_iface)):
            validation = {'sender': 'hb', 'args': {'interface': src_iface, 'count': 3, 'dst': dst_ip}}
            ping = PingChecker(players, validation)
            logger.info('Sending 3 ping packets to {} from interface {}'.format(dst_ip, src_iface))
            ping.run_validation()

        send_port_mac = cli_objects.hb.mac.get_mac_address_for_interface(src_iface)
        logger.info('Checking that host src mac address in FDB output')
        
        with allure.step('Verify MAC address is learned in FDB table with correct port'):
            fdb_table = cli_objects.dut.mac.parse_mac_table()
            mac_upper = str(send_port_mac).upper()
            found_entry = None
            for entry in fdb_table.values():
                if entry.get('MacAddress', '').upper() == mac_upper:
                    found_entry = entry
                    break
            if not found_entry:
                logger.error('MAC %s not found in FDB table. Available MACs: %s', 
                           mac_upper, [e.get('MacAddress') for e in fdb_table.values()])
                assert False, f"MAC address {mac_upper} not found in FDB table"
            logger.info('MAC %s found in FDB table', mac_upper)
            logger.info('FDB entry for MAC %s: %s', mac_upper, found_entry)
            logger.info('Verifying MAC %s is associated with %s...', mac_upper, PORT_CHANNEL)
            if found_entry['Port'] != PORT_CHANNEL:
                logger.error('MAC %s is associated with wrong port. Expected: %s, Got: %s',
                           mac_upper, PORT_CHANNEL, found_entry['Port'])
                assert found_entry['Port'] == PORT_CHANNEL, \
                    f"MAC {mac_upper} is associated with wrong port. Expected: {PORT_CHANNEL}, Got: {found_entry['Port']}"
            
            logger.info('Successfully verified MAC %s is learned on %s', mac_upper, PORT_CHANNEL)

    except Exception as err:
        logger.error('Test failed with error: %s', str(err))
        raise AssertionError(err)

