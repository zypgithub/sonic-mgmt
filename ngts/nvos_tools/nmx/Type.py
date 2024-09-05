from typing import Dict

import allure
import logging
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.system.Files import Files
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli

logger = logging.getLogger()


class Type(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/type')
        self.file_type: Dict[str, FileType] = DefaultDict(
            lambda file_type: FileType(parent=self, file_type=file_type))


class FileType(BaseComponent):
    def __init__(self, parent, file_type):
        super().__init__(parent=parent, api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path=f'/{file_type}')

        self.files = Files(self)

    def action_generate_control_plane(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action generate for {self.get_resource_path()}'):
            engine = dut_engine if dut_engine else TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_generate, engine,
                                                   self.get_resource_path())

    def action_fetch_control_plane(self, url, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action fetch for {self.get_resource_path()}'):
            engine = dut_engine if dut_engine else TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_fetch, engine,
                                                   self.get_resource_path(), url)
