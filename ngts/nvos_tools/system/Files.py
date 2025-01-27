import logging
from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class Files(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/files')
        self.file_name: Dict[str, File] = DefaultDict(lambda file_name: File(self, filename=file_name))

    def show_log_files(self, log_type='', param='', exit_cmd='', expected_str='', dut_engine=None):
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        with allure.step('Execute show for log file'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.show_log,
                                                                expected_str, TestToolkit.engines.dut, log_type,
                                                                param, exit_cmd).get_returned_value()

    def get_files(self, dut_engine=None):
        with allure.step("Get files"):
            files = OutputParsingTool.parse_json_str_to_dictionary(
                self.show(dut_engine=dut_engine)).get_returned_value()
            return files

    def verify_show_files_output(self, expected_files=[], unexpected_files=[], dut_engine=None):
        with allure.step("Verify files are as expected"):
            files = self.get_files(dut_engine=dut_engine)

            # If no expected files, ensure there are no files present
            if not expected_files and files:
                raise AssertionError(f"Expected no files, but got: {files}")

            for file in expected_files:
                assert file in files, "File: {} is not in the files output: {}".format(file, files)
            for file in unexpected_files:
                assert file not in files, "File: {} is in the files output {}".format(file, files)

    def delete_files(self, files_to_delete=[], expected_str='', engine=None):
        with allure.step("Delete files"):
            logging.info("Delete files: {}".format(files_to_delete))
            for file in files_to_delete:
                self.file_name[file].action_delete(expected_str, dut_engine=engine)

    def delete_all_existing_files(self, engine=None):
        with allure.step(f'delete all existing files of: {self.get_resource_path()}'):
            out: dict = OutputParsingTool.parse_json_str_to_dictionary(self.show(dut_engine=engine)).get_returned_value()
            self.delete_files(files_to_delete=list(out.keys()), engine=engine)


class File(BaseComponent):
    def __init__(self, parent=None, filename=''):
        super().__init__(parent=parent, path=f'/{filename}' if filename else '')
        self.file_name = filename

    def show_file(self, exit_cmd='', dut_engine=None) -> bool:
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        with allure.step(f'Execute show for file and exit cmd {exit_cmd}'):
            return SendCommandTool.execute_command(self._cli_wrapper.show_file, engine, self.file_name,
                                                   exit_cmd).get_returned_value()

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

    def action_rename(self, new_name, expected_str="", rewrite_file_name=True, dut_engine=None, should_succeed=True
                      ) -> bool:
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Rename file: {resource_path} to: {new_name}"):
            result = SendCommandTool.execute_command_expected_str(
                self._cli_wrapper.action_deprecated, expected_str,
                engine, action_type='rename', resource_path=resource_path,
                param_name='new-name', param_value=new_name).get_returned_value(should_succeed)
            if result and rewrite_file_name:
                parent: Files = self.parent_obj
                if self.file_name in parent.file_name:
                    del parent.file_name[self.file_name]
                parent.file_name[new_name] = self
                self.file_name = new_name
                self._resource_path = f'/{new_name}'
            return result

    def action_file_install(self, expected_str="", force=True, dut_engine=None, param_value='', deny_reboot=False) -> ResultObj:
        return self._action_file_install(False, expected_str, force, dut_engine, None, None, param_value, deny_reboot=deny_reboot)

    def action_file_install_with_reboot(self, expected_str="", force=True, engine=None, device=None,
                                        recovery_engine=None, topology_obj=None, param_value='',
                                        should_succeed=True, system_is_ready_timeout=None, track_boot_intervals=False, deny_reboot=False, press_y=False) -> ResultObj:
        return self._action_file_install(True, expected_str, force, engine, device, recovery_engine,
                                         topology_obj, param_value, should_succeed, system_is_ready_timeout, track_boot_intervals, deny_reboot=deny_reboot, press_y=press_y)

    def _action_file_install(self, with_reboot: bool, expected_str="", force=True, dut_engine=None, device=None,
                             recovery_engine=None, topology_obj=None, param_value='', should_succeed=True, system_is_ready_timeout=None, track_boot_intervals=False, deny_reboot=False, press_y=False) -> ResultObj:
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        device = device if device else TestToolkit.devices.dut
        topology_obj = topology_obj or TestToolkit.topology_obj
        resource_path = self.get_resource_path()
        no_force = ''
        if 'platform' in resource_path:
            no_force = 'skip-reboot'
        with allure.step(f"Install file: {resource_path}"):
            return SendCommandTool.execute_command_expected_str(
                self._cli_wrapper.action_deprecated, expected_str,
                engine, device, action_type='install', resource_path=resource_path,
                param_name='force' if force else no_force, param_value=param_value,
                expect_reboot=with_reboot, recovery_engine=recovery_engine, deny_reboot=deny_reboot,
                topology_obj=topology_obj, track_boot_intervals=track_boot_intervals, press_y=press_y,
                should_succeed=should_succeed, system_is_ready_timeout=system_is_ready_timeout,
                expected_output=expected_str)

    def rename_and_verify(self, new_name, expected_str="", dut_engine=None):
        original_name = self.file_name
        self.action_rename(new_name, expected_str, dut_engine=dut_engine)
        self.parent_obj.verify_show_files_output(expected_files=[new_name], unexpected_files=[original_name],
                                                 dut_engine=dut_engine)
