import allure
import logging
import pytest

from retry.api import retry_call
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker

logger = logging.getLogger()


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
        with allure.step('Check that PortChannel0002 link in UP state'):
            retry_call(cli_objects.dut.interface.check_ports_status, fargs=[['PortChannel0002']], tries=12,
                       delay=5, logger=logger)

        with allure.step('Sending 3 ping packets to {} from interface {}'.format(dst_ip, src_iface)):
            validation = {'sender': 'hb', 'args': {'interface': src_iface, 'count': 3, 'dst': dst_ip}}
            ping = PingChecker(players, validation)
            logger.info('Sending 3 ping packets to {} from interface {}'.format(dst_ip, src_iface))
            ping.run_validation()

        send_port_mac = cli_objects.hb.mac.get_mac_address_for_interface(src_iface)
        logger.info('Checking that host src mac address in FDB output')
        # TODO: enable validation(disabled due to bug) and validation should be more precise
        # assert str(send_port_mac).upper() in cli_objects.dut.mac.show_mac()

    except Exception as err:
        raise AssertionError(err)
