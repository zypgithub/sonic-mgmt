from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure


class Oiak(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/oiak')

    def action_import_tpm_oiak(self, data='', remote_url='', dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action generate for {self.get_resource_path()}'):
            engine = dut_engine if dut_engine else TestToolkit.get_engine()
            return SendCommandTool.execute_command(self._cli_wrapper.action_import_tpm_oiak, engine,
                                                   self.get_resource_path(), data, remote_url)
