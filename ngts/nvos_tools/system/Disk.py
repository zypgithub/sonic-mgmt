from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj


class Disk(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/disk')

    def action_erase(self, dut_engine=None, device=None, force=None) -> ResultObj:
        with allure.step(f'Execute disk erase action {self.get_resource_path()}'):
            engine = dut_engine if dut_engine else TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_erase, engine, device,
                                                   self.get_resource_path(), force=force)
