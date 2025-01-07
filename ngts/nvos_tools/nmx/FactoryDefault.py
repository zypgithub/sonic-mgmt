import allure

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime


class FactoryDefault(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli}, path='/factory-default')

    def action_reset(self, engine=None, param=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Execute Sdn factory reset'):
            return SendCommandTool.execute_command(self._cli_wrapper.action_reset,
                                                   engine,
                                                   self.get_resource_path(), param)
