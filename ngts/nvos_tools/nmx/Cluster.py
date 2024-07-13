import logging

import ngts.tools.test_utils.allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.nmx.App import App
from ngts.nvos_tools.nmx.Apps import Apps
from ngts.nvos_tools.nmx.Manager import Manager

logger = logging.getLogger()


class Cluster(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/cluster')
        self.app = App(self)
        self.apps = Apps(self)
        self.manager = Manager(self)

    def action_update(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action update for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_update_cluster_manager_property, engine,
                                                   self.get_resource_path())

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action restore for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_cluster_manager_property, engine,
                                                   self.get_resource_path())
