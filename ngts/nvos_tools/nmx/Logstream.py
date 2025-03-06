from typing import Dict

import allure
import logging
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType

logger = logging.getLogger()


class Logstream(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/log-stream')

    def action_update_cluster_log_stream(self, engine=None, stream='',
                                         expected_str="App log stream has been successfully updated"):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Update Log stream'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_update_cluster_log_stream,
                                                                expected_str, engine,
                                                                self.get_resource_path(), stream)

    def action_restore_cluster_log_stream(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Restore Log stream'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_restore_cluster_log_stream,
                                                                "App log stream has been successfully restored", engine,
                                                                self.get_resource_path())
