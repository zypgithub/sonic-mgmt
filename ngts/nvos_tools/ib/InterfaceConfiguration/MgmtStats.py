from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
import allure


class MgmtStats(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/counters')

    def clear_stats(self, dut_engine=None, fae_param=""):
        """
        Clears interface counters
        """
        if not dut_engine:
            dut_engine = TestToolkit.get_engine()

        with allure.step('Clear stats for {port_name}'.format(port_name=self.parent_obj.parent_obj.parent_obj.name)):
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].clear_stats,
                                                   dut_engine, self.parent_obj.parent_obj.parent_obj.name, fae_param)
