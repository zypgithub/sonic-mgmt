import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from .DhcpClient import DhcpClient

logger = logging.getLogger()


class IpV6(BaseComponent):
    """
    IPv6 interface configuration class
    Contains IPv6-specific properties and methods
    """

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/ipv6')

        # IPv6-specific properties
        self.address = BaseComponent(self, path='/address')
        self.gateway = BaseComponent(self, path='/gateway')
        self.autoconf = BaseComponent(self, path='/autoconf')

        # Enhanced DHCP client for IPv6
        self.dhcp_client = DhcpClient(self, protocol='ipv6')

    def action_renew_dhcp_client(self, dut_engine=None) -> ResultObj:
        """
        Renew IPv6 DHCP client (backward compatibility method)

        :param dut_engine: DUT engine to use
        :return: ResultObj
        """
        return self.dhcp_client.action_renew(dut_engine=dut_engine)

    def get_ip_addresses(self, dut_engine=None):
        """
        Get IPv6 addresses for the interface

        :param dut_engine: DUT engine to use
        :return: list of IP addresses
        """
        try:
            if not dut_engine:
                dut_engine = TestToolkit.engines.dut

            addresses_show = self.address.show(dut_engine=dut_engine)

            # Handle string (JSON string) - parse it to dict
            if isinstance(addresses_show, str):
                import json
                try:
                    addresses_show = json.loads(addresses_show)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse IPv6 address JSON string: {e}")
                    return []

            if isinstance(addresses_show, dict):
                return list(addresses_show.keys())
            elif isinstance(addresses_show, list):
                return addresses_show

            return []

        except Exception as e:
            logger.warning(f"Error getting IPv6 addresses: {e}")
            return []

    def get_primary_ip_address(self, dut_engine=None):
        """
        Get the primary IPv6 address for the interface
        Filters out localhost (::1) and link-local (fe80::) addresses

        :param dut_engine: DUT engine to use
        :return: str primary IP address or None
        """
        try:
            addresses = self.get_ip_addresses(dut_engine)

            if addresses:
                # Filter to find a global unicast address (not localhost, not link-local)
                for addr in addresses:
                    addr_clean = addr.split('/')[0] if '/' in addr else addr
                    # Skip localhost (::1) and link-local (fe80::) addresses
                    if addr_clean != '::1' and not addr_clean.lower().startswith('fe80:'):
                        # Prefer addresses with at least 32 characters (full IPv6 addresses)
                        if len(addr_clean) >= 32:
                            return addr_clean

                # If no global address found, return first non-localhost address
                for addr in addresses:
                    addr_clean = addr.split('/')[0] if '/' in addr else addr
                    if addr_clean != '::1':
                        return addr_clean

                # Last resort: return the first address
                primary_addr = addresses[0]
                if '/' in primary_addr:
                    return primary_addr.split('/')[0]
                return primary_addr

            return None

        except Exception as e:
            logger.warning(f"Error getting primary IPv6 address: {e}")
            return None

    def is_autoconf_enabled(self, dut_engine=None):
        """
        Check if IPv6 autoconf is enabled

        :param dut_engine: DUT engine to use
        :return: bool
        """
        try:
            if not dut_engine:
                dut_engine = TestToolkit.engines.dut

            autoconf_data = self.autoconf.show(dut_engine=dut_engine)
            return autoconf_data == 'enabled'

        except Exception as e:
            logger.info(f"Error checking IPv6 autoconf status: {e}")
            return False
