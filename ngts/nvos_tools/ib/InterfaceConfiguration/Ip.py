import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


class Ip(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/ip')
        self.address = BaseComponent(self, path='/address')
        self.gateway = BaseComponent(self, path='/gateway')
        self.dhcp_client = BaseComponent(self, path='/dhcp-client')
        self.dhcp_client6 = BaseComponent(self, path='/dhcp-client6')

    def action_renew_dhcp_client(self, dut_engine=None, ipv6=False) -> ResultObj:
        """
        Renew DHCP client for IPv4 or IPv6.

        :param dut_engine: DUT engine to use
        :param ipv6: If True, renew DHCPv6 client; otherwise, DHCPv4
        :return: ResultObj
        """
        if not dut_engine:
            dut_engine = TestToolkit.get_engine()
        dhcp_client_obj = self.dhcp_client6 if ipv6 else self.dhcp_client
        return SendCommandTool.execute_command(
            self.api_obj[TestToolkit.tested_api].action_renew_dhcp_client,
            dut_engine,
            dhcp_client_obj.get_resource_path()
        )
