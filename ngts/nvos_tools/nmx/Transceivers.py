import logging
import allure

from typing import Dict
from collections import defaultdict as DefaultDict
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


class Transceivers(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/transceivers')
        self.transceiver: Dict[str, Transceiver] = DefaultDict(lambda transceiver_id: Transceiver(self, transceiver_id=transceiver_id))


class Transceiver(BaseComponent):
    def __init__(self, parent, transceiver_id):
        super().__init__(parent=parent, path=f'/{transceiver_id}')
        self.name = transceiver_id

    def action_update_maintenance_state(self, maintenance_state='', expected_err_msgs=(), engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Update transceiver maintenance state'):
            return SendCommandTool.execute_command(self._cli_wrapper.action_update_sdn_transceiver_maintenance_state,
                                                   engine, self.get_resource_path(), maintenance_state, exempted_err_msgs=expected_err_msgs)

    def action_restore_maintenance_state(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Restore transceiver maintenance state'):
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_sdn_transceiver_maintenance_state,
                                                   engine, self.get_resource_path())
