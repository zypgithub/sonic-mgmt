import logging
from typing import Dict

import allure

from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class Uuid(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/uuid')
        self.uuid_value: Dict[str, UuidVal] = DefaultDict(
            lambda uuid_value: UuidVal(parent=self, uuid_value=uuid_value))


class UuidVal(BaseComponent):
    def __init__(self, parent, uuid_value):
        super().__init__(parent=parent, path=f'/{uuid_value}')

    def action_update_partition(self, engine=None, reroute_param=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Update partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_update_partition,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path(), reroute_param)

    def action_restore_partition(self, engine=None, reroute_param=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Restore partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_restore_partition,
                                                                "has been successfully restored", engine,
                                                                self.get_resource_path(), reroute_param)
