import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from .DhcpClient import DhcpClient

logger = logging.getLogger()


class IpV4(BaseComponent):
    """
    IPv4 interface configuration class
    Contains IPv4-specific properties and methods
    """

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/ipv4')

        # IPv4-specific properties
        self.address = BaseComponent(self, path='/address')
        self.gateway = BaseComponent(self, path='/gateway')
        self.arp_timeout = BaseComponent(self, path='/arp-timeout')

        # Enhanced DHCP client for IPv4
        self.dhcp_client = DhcpClient(self, protocol='ipv4')

    def action_renew_dhcp_client(self, dut_engine=None) -> ResultObj:
        """
        Renew IPv4 DHCP client (backward compatibility method)

        :param dut_engine: DUT engine to use
        :return: ResultObj
        """
        return self.dhcp_client.action_renew(dut_engine=dut_engine)

    def get_ip_addresses(self, dut_engine=None):
        """
        Get IPv4 addresses for the interface

        :param dut_engine: DUT engine to use
        :return: list of IP addresses
        """
        try:
            if not dut_engine:
                dut_engine = TestToolkit.get_engine()

            addresses_show = self.address.show(dut_engine=dut_engine)
            addresses_dict = OutputParsingTool.parse_json_str_to_dictionary(addresses_show).get_returned_value()
            addresses = list(addresses_dict.keys())
            logger.info(f"IPv4 addresses found: {addresses}")
            return addresses

        except Exception as e:
            logger.info(f"Error getting IPv4 addresses: {e}")
            return []

    def get_primary_ip_address(self, dut_engine=None):
        """
        Get the primary IPv4 address for the interface

        :param dut_engine: DUT engine to use
        :return: str primary IP address or None
        """
        try:
            addresses = self.get_ip_addresses(dut_engine)
            if addresses:
                # Return the first address, removing any prefix
                primary_addr = addresses[0]
                if '/' in primary_addr:
                    primary_addr = primary_addr.split('/')[0]
                logger.info(f"Primary IPv4 address: {primary_addr}")
                return primary_addr
            logger.info("No IPv4 addresses found")
            return None

        except Exception as e:
            logger.info(f"Error getting primary IPv4 address: {e}")
            return None
