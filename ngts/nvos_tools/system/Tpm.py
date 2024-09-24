from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.OIAK import Oiak


class Tpm(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/tpm')
        self.oaik = Oiak(self)

    def action_generate_quote(self, pcrs='', nonce='', algorithm='', dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action generate for {self.get_resource_path()}'):
            engine = dut_engine if dut_engine else TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_generate_tpm_quote, engine,
                                                   self.get_resource_path(), pcrs, nonce, algorithm)

    def action_upload(self, file_name: str, remote_url: str, expected_str='', dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action upload for {self.get_resource_path()}'):
            engine = dut_engine if dut_engine else TestToolkit.engines.dut
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_upload_tpm_file, expected_str,
                                                                engine, self.get_resource_path(), file_name, remote_url)
