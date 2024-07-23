from typing import Dict

import logging
import allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.nmx.Loglevel import Loglevel
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class Apps(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/apps')
        self.apps_name: Dict[str, AppsName] = DefaultDict(
            lambda apps_name: AppsName(parent=self, apps_name=apps_name))
        self.installed = BaseComponent(self, path='/installed')
        self.running = BaseComponent(self, path='/running')


class AppsName(BaseComponent):
    def __init__(self, parent, apps_name):
        super().__init__(parent=parent, path=f'/{apps_name}')
        self.loglevel = Loglevel(self)

    def action_start_cluster_apps(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Start App'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_start_cluster_apps,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path())

    def action_stop_cluster_apps(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Stop App'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_stop_cluster_apps,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path())
