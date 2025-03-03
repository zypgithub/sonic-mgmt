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


class Loglevel(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/log-level')

    def action_update_cluster_log_level(self, engine=None, level=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Update Log Level'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_update_cluster_log_level,
                                                                "App log level has been successfully updated", engine,
                                                                self.get_resource_path(), level)

    def action_restore_cluster(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Restore Log Level'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_restore_cluster,
                                                                "has been successfully restored", engine,
                                                                self.get_resource_path())
