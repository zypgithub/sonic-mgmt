import logging
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.Files import Files

logger = logging.getLogger()


class Config(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/config')
        self.files = Files(self)
        self.auto_save = BaseComponent(self, path='/auto-save')

    def action_export(self, file_name, expected_str="", dut_engine=None):
        if not dut_engine:
            dut_engine = TestToolkit.engines.dut
        with allure.step('Trying to export the applied configuration to {}'.format(file_name)):
            return SendCommandTool.execute_command_expected_str(self.api_obj[TestToolkit.tested_api].action_export,
                                                                expected_str, dut_engine,
                                                                self.get_resource_path(), file_name).verify_result()
