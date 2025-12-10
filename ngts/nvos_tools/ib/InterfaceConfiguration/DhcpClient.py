import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from .Lease import Lease

logger = logging.getLogger()


class DhcpClient(BaseComponent):
    """
    Enhanced DHCP client class with new lease structure and actions
    Supports both IPv4 and IPv6 DHCP clients
    """

    def __init__(self, parent_obj=None, protocol='ipv4'):
        # Set path based on protocol
        if protocol in ['ipv4', 'ipv6']:
            path = '/dhcp-client'

        BaseComponent.__init__(self, parent=parent_obj, path=path)
        self.protocol = protocol

        # Core DHCP client properties
        self.state = BaseComponent(self, path='/state')
        self.set_hostname = BaseComponent(self, path='/set-hostname')

        # New lease structure
        self.lease = Lease(self, protocol=protocol)

    def action_renew(self, dut_engine=None):
        """
        Renew DHCP client

        :param dut_engine: DUT engine to use
        :return: ResultObj
        """
        if not dut_engine:
            dut_engine = TestToolkit.get_engine()
        try:
            result_obj = SendCommandTool.execute_command(
                self.api_obj[TestToolkit.tested_api].action_renew_dhcp_client,
                dut_engine,
                self.get_resource_path()
            )
            return result_obj
        except Exception as e:
            logger.info(f"Error executing DHCP renew action: {e}")
            return ResultObj(False, str(e))
