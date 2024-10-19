import allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.openapi.openapi_system_clis import OpenApiSystemCli


class Ztp(BaseComponent):

    def __init__(self, parent_obj):
        BaseComponent.__init__(self, parent=parent_obj, path='/ztp')

    def action_run_ztp(self, engine=None, device=None, params_dict={}, reboot_expected=False):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            marker = TestToolkit.get_loganalyzer_marker(engine)

            res = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_run_ztp, engine, device,
                                                  self.get_resource_path(), params_dict)

            TestToolkit.add_loganalyzer_marker(engine, marker)
            if reboot_expected:
                DutUtilsTool.wait_on_system_reboot(TestToolkit.engines.dut)
                DutUtilsTool.wait_for_nvos_to_become_functional(engine)
            return res

    def action_abort_ztp(self, engine=None, device=None, params_dict={}):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            marker = TestToolkit.get_loganalyzer_marker(engine)

            res = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_run_ztp, engine, device,
                                                  self.get_resource_path(), params_dict)

            return res

    def action_run_ztp_url(self, engine=None, device=None, params_dict={}, url=''):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            marker = TestToolkit.get_loganalyzer_marker(engine)
            res = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_run_ztp_url, engine, device,
                                                  self.get_resource_path(), params_dict, url)

            return res

    def action_enable_ztp(self, engine=None, device=None, params_dict={}):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            marker = TestToolkit.get_loganalyzer_marker(engine)

            res = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_enable_ztp, engine, device,
                                                  self.get_resource_path(), params_dict)

            return res

    def action_disable_ztp(self, engine=None, device=None, params_dict={}):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            marker = TestToolkit.get_loganalyzer_marker(engine)

            res = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_disable_ztp, engine, device,
                                                  self.get_resource_path(), params_dict)

            return res
