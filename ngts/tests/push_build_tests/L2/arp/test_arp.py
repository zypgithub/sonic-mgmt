import allure
import logging
import pytest

from ngts.helpers.arp_helper import clear_dynamic_arp_table_and_check_the_specified_arp_entry_deleted, \
    send_arp_request_and_check_update_corresponding_entry_into_arp_table

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
@pytest.mark.push_gate
@pytest.mark.build
@pytest.mark.parametrize("arp_request_type", ["broadcast", "unicast"])
@allure.title('DUT reply ARP request')
def test_dut_reply_arp_response(engines, cli_objects, players, interfaces, arp_request_type):
    """
    Verify DUT reply arp response as the following test steps traversing broadcast and unicast arp request
    1. DUT clear all arp table by conic-clear arp
    2. Host A sends ARP request for broadcast or unicast
    3. Verify Host A receives the arp response
    4. Verify DUT add the Host A's IP and MAC into the ARP table
    :param engines: engines fixture
    :param cli_objects: cli_objects fixture
    :param players: players fixture
    :param interfaces: interfaces fixture
    :param arp_request_type: arp request type: broadcast or unicast
    """
    interface_data = {"host_ip": "30.0.0.20", "dut_ip": "30.0.0.1", "host_interface": "bond0",
                      "dut_interface": "PortChannel0001",
                      "host_mac": cli_objects.ha.mac.get_mac_address_for_interface(interfaces.ha_dut_1),
                      "dut_mac": cli_objects.dut.mac.get_mac_address_for_interface(interfaces.dut_ha_1),
                      "dut_vlan_id": "-", "host_alias": "ha"}

    try:

        with allure.step("DUT clear all arp table by conic-clear arp, and check the specified arp has been clear"):
            clear_dynamic_arp_table_and_check_the_specified_arp_entry_deleted(cli_objects.dut, interface_data["host_ip"])

        with allure.step("Host sends ARP request to DUT and check results"):
            send_arp_request_and_check_update_corresponding_entry_into_arp_table(cli_objects.dut, players, interface_data,
                                                                                 arp_request_type)

    except Exception as err:
        raise AssertionError(err)
