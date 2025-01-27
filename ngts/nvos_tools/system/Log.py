import logging
from typing import Dict

import allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict

logger = logging.getLogger()


class BaseLog(BaseComponent):
    def __init__(self, parent_obj=None, path=''):
        super().__init__(parent=parent_obj, path=path)
        self.file = File(self)
        self.rotation = BaseComponent(self, path='/rotation')

    def rotate_logs(self):
        """
        Shared rotate_logs implementation for log rotation.
        """
        with allure.step('Rotate logs'):
            resource_path = self.get_resource_path()
            return SendCommandTool.execute_command(
                self.api_obj[TestToolkit.tested_api].action_rotate_logs,
                TestToolkit.engines.dut,
                resource_path
            ).get_returned_value()


class Log(BaseLog):
    def __init__(self, parent_obj=None):
        super().__init__(parent_obj=parent_obj, path='/log')
        self.component = Component(self)

    def write_to_log(self):
        with allure.step('Write content to logs'):
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_write_to_logs,
                                                   TestToolkit.engines.dut).get_returned_value()

    def verify_expected_logs(self, logs_to_find, engine=None, only_latest_log=False):
        """
        :param logs_to_find: list of logs to find
        :param engine: system engine
        :param only_latest_log: verify in only latest log file, instead of all in log files.
        :return:
        """
        with allure.step('Verify expected logs'):
            log_search_errors: Dict[str, str] = {log: f'log "{log}" was not found' for log in logs_to_find}
            grep_logs = '|'.join(logs_to_find)

            if only_latest_log:
                log_files = ['syslog']
            else:
                log_files = OutputParsingTool.parse_json_str_to_dictionary(
                    self.file.show()).get_returned_value().keys()

            for log_file in log_files:
                if not log_search_errors:
                    break

                output = self.file.file_id[log_file].show(op_param=f'| grep -E "{grep_logs}"', output_format='',
                                                          dut_engine=engine)
                if output:
                    for log in logs_to_find:
                        if log in output and log in log_search_errors:
                            del log_search_errors[log]

            err = ',\n'.join(list(log_search_errors.values()))
            assert not log_search_errors, f"The following logs weren't found:\n{err}"


class File(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/file')
        self.file_id: Dict[str, FileId] = DefaultDict(
            lambda file_id: FileId(parent=self, file_id=file_id))

    def show_log(self, param='', exit_cmd='', expected_str=''):
        with allure.step('Show logs'):
            resource_path = self.get_resource_path()
            return SendCommandTool.execute_command_expected_str(self.api_obj[TestToolkit.tested_api].show_log,
                                                                expected_str, TestToolkit.engines.dut, resource_path,
                                                                param, exit_cmd).get_returned_value()


class FileId(BaseComponent):
    def __init__(self, parent, file_id):
        super().__init__(parent=parent, path=f'/{file_id}')
        self.filename = file_id

    def action_upload(self, upload_path, expected_str="", dut_engine=None, should_succeed=True) -> bool:
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Upload file {resource_path} to '{upload_path}'"):
            return SendCommandTool.execute_command_expected_str(
                self._cli_wrapper.action_deprecated, expected_str,
                engine, action_type='upload', resource_path=resource_path,
                param_name='remote-url', param_value=upload_path).get_returned_value(should_succeed)

    def action_delete(self, expected_str="", dut_engine=None, should_succeed=True) -> bool:
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Delete file: {resource_path}"):
            return SendCommandTool.execute_command_expected_str(
                self._cli_wrapper.action_deprecated, expected_str,
                engine, action_type='delete', resource_path=resource_path).get_returned_value(should_succeed)


class Component(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/component')
        self.component_id: Dict[str, ComponentId] = DefaultDict(
            lambda component_id: ComponentId(parent=self, component_id=component_id))


class ComponentId(BaseLog):
    def __init__(self, parent, component_id):
        super().__init__(parent_obj=parent, path=f'/{component_id}')
        self.level = BaseComponent(self, path='/level')
