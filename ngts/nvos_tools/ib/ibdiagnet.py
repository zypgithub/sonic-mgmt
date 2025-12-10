import allure
import logging
from ngts.cli_wrappers.nvue.nvue_ib_clis import NvueIbCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import IbConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class Ibdiagnet(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, api={ApiType.NVUE: NvueIbCli}, path='/ibdiagnet')

    def action_run(self, command="ibdiagnet", option="", expected_str=""):
        with allure.step("Create ibdiagnet files"):
            logging.info("Create ibdiagnet files")
            return SendCommandTool.execute_command_expected_str(self.api_obj[TestToolkit.tested_api].action_run,
                                                                expected_str, TestToolkit.get_engine(), '"' + command,
                                                                option + '"').get_returned_value()

    def action_upload(self, upload_path, file_name=IbConsts.IBDIAGNET_FILE_NAME):
        with allure.step("Upload ibdiagnet to '{path}".format(path=upload_path)):
            logging.info("Upload ibdiagnet to '{path} ".format(path=upload_path))
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_upload,
                                                   TestToolkit.get_engine(), self.get_resource_path() + ' files',
                                                   file_name, upload_path)

    def action_delete(self, file_name):
        with allure.step("Delete ibdiagnet"):
            logging.info("Delete ibdiagnet")
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_delete,
                                                   TestToolkit.get_engine(), self.get_resource_path() + ' files',
                                                   file_name)
