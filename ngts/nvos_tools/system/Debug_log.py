import logging
import allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.Files import Files
logger = logging.getLogger()


class DebugLog(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/debug-log')
        self.files = Files(self)
        self.rotation = BaseComponent(self, path='/rotation')

    def set(self, op_param_name="", op_param_value=""):
        raise Exception("set is not implemented for /debug_log")

    def show_log(self, log_type='', param='', exit_cmd='', expected_str=''):
        with allure.step('Execute nv show system {type}log {param} and exit_cmd {exit_cmd}'.format(type=log_type,
                                                                                                   param=param,
                                                                                                   exit_cmd=exit_cmd)):
            return SendCommandTool.execute_command_expected_str(self.api_obj[TestToolkit.tested_api].show_log,
                                                                expected_str, TestToolkit.engines.dut, log_type,
                                                                param, exit_cmd).get_returned_value()

    def write_to_log(self):
        with allure.step('Write content to debug-logs'):
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_write_to_debug_logs,
                                                   TestToolkit.engines.dut).get_returned_value()

    def rotate_logs(self):
        with allure.step('Rotate debug-logs'):
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_rotate_debug_logs,
                                                   TestToolkit.engines.dut).get_returned_value()
