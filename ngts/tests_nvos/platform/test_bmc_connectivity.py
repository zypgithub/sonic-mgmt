import logging

from ngts.nvos_tools.infra.BmcTool import BmcTool
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.acl.test_acl_basic import ping_from_switch
from ngts.tests_nvos.platform.constants import SETUPS_WITHOUT_IPV6_BMC

logger = logging.getLogger()


def test_bmc_ping(engines, devices, topology_obj, setup_name):
    """
     verify the network connectivity between a management system and bmc by sending a ping request to Ipv4 and Ipv6 addresses
    :param engines:
    :param devices:
    :param topology_obj:
    :param setup_name:
    :return:
    """
    with allure.step("get bmc addresses"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)

    with allure.step("Try to ping via all addresses"):
        for address_type, address in ip_addresses.items():
            logger.info(f"address_type: {address_type}, address: {address}, setup_name: {setup_name}")
            if address_type == "IPv6" and setup_name in SETUPS_WITHOUT_IPV6_BMC:
                continue
            with allure.independent_step(f"try to ping using {address_type}: {address}"):
                ping_from_switch(engines.dut, address, "eth0").verify_result()


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
