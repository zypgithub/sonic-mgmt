import allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool


class Profile(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/profile')

    def action_profile_change(self, engine=None, device=None, params_dict={}):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            marker = TestToolkit.get_loganalyzer_marker(engine)

            res = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_profile_change, engine, device,
                                                  self.get_resource_path(), params_dict).verify_result()

            TestToolkit.add_loganalyzer_marker(engine, marker)

            DutUtilsTool.wait_for_nvos_to_become_functional(engine)
            return res
