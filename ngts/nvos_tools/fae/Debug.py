import logging

from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.system.Files import Files
from ngts.tools.test_utils import allure_utils as allure


class Debug(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/debug")
        self.info = Info(self)


class Info(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/info")
        self.debug_image = DebugInfoComponent(self, 'debug-image')


class DebugInfoComponent(BaseComponent):
    def __init__(self, parent_obj=None, component_name=None):
        super().__init__(parent=parent_obj, path=f"/{component_name}")
        self.files = Files(self)
        self.component_name = component_name

    def action_generate(self, engine="", name="", test_name='', should_succeed=True):
        """
        Generate debug-image / customer-support.
        """
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut

        cmd_info, duration = OperationTime.save_duration(
            f'generate {self.component_name}', name, test_name,
            SendCommandTool.execute_command,
            self.api_obj[TestToolkit.tested_api].action_generate,
            engine, self.get_resource_path().replace('/files', ' '), name
        )

        logging.info(f"Generating debug token took {duration} seconds")
        cmd_info.verify_result(should_succeed)

    def action_delete_all(self):
        """nv action delete fae platform debug info {debug-image | customer-support} files"""
        with allure.step(f"Delete all files of {self.component_name}"):
            return self.action_deprecated(ActionConsts.DELETE, 'files')
