import logging
import pytest
import random
import allure
import time
from tests.common.helpers.assertions import pytest_assert
from ptf import testutils

pytestmark = [
    pytest.mark.topology('t0')
]

logger = logging.getLogger(__name__)
PKT_NUM = 100
LOSSLESS_DSCP = [3, 4]
LOSSY_DSCP = list(range(0, 3)) + list(range(5, 64))


@pytest.fixture(scope='module')
def mg_facts(duthost, tbinfo):
    return duthost.get_extended_minigraph_facts(tbinfo)


@pytest.fixture(scope='module', autouse=True)
def config_counter_poll_interval(duthost):
    """
    Set counter poll interval to 100ms to ensure that the counters are updated in time
    """
    origin_queue_interval = duthost.get_counter_poll_status()['PORT_STAT']['interval']
    duthost.set_counter_poll_interval('PORT_STAT', 100)

    yield

    duthost.set_counter_poll_interval('PORT_STAT', origin_queue_interval)


@pytest.mark.parametrize(
    "param", [('broadcast', 'ff:ff:ff:ff:ff:ff'),
              ('unkonwn_unicast', '11:22:33:44:55:66'),
              ('multicast', '01:00:5e:00:00:01')])
def test_lossless_bum_traffic_drop(duthost, ptfhost, tbinfo, ptfadapter, mg_facts, param):
    """
    This test is to verify the issue in RM#3322173.
    When BUM(broadcast/unknown unicast/multicast) traffic is received in a vlan, whether it should be dropped or flooded
    in the vlan depends on the priority. Lossless traffic should be discarded, while lossy traffic should be
    flooded to the other ports in the vlan.
    """
    with allure.step('Preparing test variables.'):
        # Find the downlink vlan in case po2vlan topo
        vlan_name = sorted(mg_facts['minigraph_vlans'].keys())[-1]
        vlan_members = []
        ptf_receive_ports = []
        for interface in mg_facts['minigraph_vlans'][vlan_name]['members']:
            # Only use the physical port vlan members in case po2vlan topo
            if 'PortChannel' not in interface:
                vlan_members.append(interface)
                ptf_receive_ports.append(mg_facts['minigraph_ptf_indices'][interface])
        send_port = vlan_members.pop(0)
        ptf_send_port = mg_facts['minigraph_ptf_indices'][send_port]
        lossless_pkt_dscp = random.choice(LOSSLESS_DSCP)
        lossy_pkt_dscp = random.choice(LOSSY_DSCP)
        traffic_type, dst_mac = param
    with allure.step('Verify lossless {} traffic.'.format(traffic_type)):
        logger.info('Sending lossless {} traffic from interface {} with dst_mac:{}, dscp:{}. '
                    'Traffic is expected to be dropped by dut.'
                    .format(traffic_type, send_port, dst_mac, lossless_pkt_dscp))
        lossless_pkt = testutils.simple_tcp_packet(
            eth_dst=dst_mac,
            eth_src='00:00:00:11:11:11',
            ip_src='1.1.1.1',
            ip_dst='2.2.2.2',
            ip_dscp=lossless_pkt_dscp)
        duthost.shell('sonic-clear counters')
        testutils.send(ptfadapter, ptf_send_port, lossless_pkt, PKT_NUM)
        logger.info('Verify the lossless {} traffic is dropped.'.format(traffic_type))
        testutils.verify_no_packet_any(ptfadapter, lossless_pkt, ptf_receive_ports)
        # wait for the interfaces counters to update
        time.sleep(2)
        verify_interfaces_counters(duthost, vlan_members, 'tx_drp', PKT_NUM, '==')

    with allure.step('Verify lossy {} traffic.'.format(traffic_type)):
        logger.info('Sending lossy {} traffic from interface {} with dst_mac:{}, dscp:{}. '
                    'Traffic is expected to be flooded to all other vlan members'
                    .format(traffic_type, send_port, dst_mac, lossy_pkt_dscp))
        lossy_pkt = testutils.simple_tcp_packet(
            eth_dst=dst_mac,
            eth_src='00:00:00:11:11:11',
            ip_src='1.1.1.1',
            ip_dst='2.2.2.2',
            ip_dscp=lossy_pkt_dscp)
        duthost.shell('sonic-clear counters')
        testutils.send(ptfadapter, ptf_send_port, lossy_pkt, PKT_NUM)
        logger.info('Verify the lossy {} traffic is flooded.'.format(traffic_type))
        # wait for the interfaces counters to update
        time.sleep(2)
        verify_interfaces_counters(duthost, vlan_members, 'tx_ok', PKT_NUM, '>=')


def verify_interfaces_counters(duthost, interfaces_to_check, counter_name, expected_value, operator):
    """
    Verify the given counter values of the given interfaces are as expected.
    This method only supports the counters with integer values.
    Args:
        duthost: duthost fixture
        interfaces_to_check: the interfaces need to verify
        counter_name: the counter need to verify
        expected_value: the expected value
        operator: the comparison operator between the actual value and the expected value
    """
    counters = get_interfaces_counters(duthost)
    for interface in interfaces_to_check:
        pytest_assert(interface in counters.keys(), "No counters entry for interface {}.".format(interface))
        actual_value = counters[interface][counter_name].replace(',', '')
        pytest_assert(eval(actual_value + operator + str(expected_value)),
                      'The {} counter value of interface {} is not as expected. '
                      'The actual: {}, the expected: {}, operator: {}'.format(
                          counter_name, interface, actual_value, expected_value, operator))


def get_interfaces_counters(duthost):
    """
    Get the parsed output of "show interfaces counters" command.
    Args:
        duthost: duthost fixture
    Returns:
        A dictionary whose keys are the interface names. And for each interface, the value is a dictionary of the other
        columns in the "show interfaces counters" output.
        for example:
        {'Ethernet0':{'state':'U', 'rx_ok':'1,000', ... , 'tx_ovr':'0'},
         'Ethernet2':{'state':'U', 'rx_ok':'0', ... , 'tx_ovr':'0'},
         ...
        }
    """
    parsed_output = duthost.show_and_parse('show interfaces counters')
    result = {}
    for item in parsed_output:
        result[item.pop('iface')] = item
    return result
