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


class Partition(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/partition')
        self.partition_id: Dict[str, PartitionId] = DefaultDict(
            lambda partition_id: PartitionId(parent=self, partition_id=partition_id))


class PartitionId(BaseComponent):
    def __init__(self, parent, partition_id):
        super().__init__(parent=parent, path=f'/{partition_id}')

    def action_create_partition_id(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Create partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_create_partition,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path())

    def action_update_partition(self, engine=None, uuid='', location=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Update partition'):
            if uuid != '':
                return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_update_partition_uuid,
                                                                    "Action succeeded", engine,
                                                                    self.get_resource_path())
            else:
                return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_update_partition_location,
                                                                    "Action succeeded", engine,
                                                                    self.get_resource_path())

    def action_restore_partition(self, engine=None, uuid='', location=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Restore partition'):
            if uuid != '':
                return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_restore_partition_uuid,
                                                                    "Action succeeded", engine,
                                                                    self.get_resource_path())
            else:
                return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_restore_partition_location,
                                                                    "Action succeeded", engine,
                                                                    self.get_resource_path())

    def action_delete_partition(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Delete partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_delete,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path())
