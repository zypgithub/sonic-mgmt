import logging

from ngts.nvos_tools.infra.BmcTool import BmcTool
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


def test_bmc_ping(engines, devices, topology_obj):
    """
     verify the network connectivity between a management system and bmc by sending a ping request to Ipv4 and Ipv6 addresses
    :param engines:
    :param devices:
    :param topology_obj:
    :return:
    """
    with allure.step("get bmc addresses"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)

    with allure.step("Try to ping via all addresses"):
        for address_type, address in ip_addresses.items():
            with allure.independent_step(f"try to ping using {address_type}: {address}"):
                ping_till_alive(should_be_alive=True, destination_host=address, tries=5)


def test_bmc_curl_request_via_ipv6(engines, devices, topology_obj):
    """
    verify the network connectivity between a management system and bmc by sending a curl request to Ipv6 address
    :param engines:
    :param devices:
    :param topology_obj:
    :return:
    """
    with allure.step("get bmc addresses"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)

    with allure.step("Sending a curl request via BMC IPv6 address"):
        curl_request = f'curl -s -k -u {BmcTool.USER_NAME}:{BmcTool._get_bmc_password(engines.dut)} https://[{ip_addresses["IPv6"]}]/redfish/v1/Managers/BMC_0/EthernetInterfaces/eth0 | python3 -m json.tool'
        eth0_details = OutputParsingTool.parse_json_str_to_dictionary(engines.dut.run_cmd(curl_request)).verify_result()
        assert "IPv6Addresses" in eth0_details, "we expect to have Ipv6 address"
